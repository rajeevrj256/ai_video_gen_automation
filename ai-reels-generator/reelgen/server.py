"""Local app server: `python -m reelgen serve`.

Runs on your computer, keeps every video on your disk (output/), and serves a
mobile-friendly web app. Open it on the computer, or on your phone over the same
Wi-Fi (scan the QR code printed at start-up) and "Add to Home Screen" to use it
like an app.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import shutil
import socket
import threading
import time
import uuid
from collections import deque
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from .config import EDITABLE, PROJECT_ROOT, Config, load_settings, save_settings
from .llm import INSTALL_HELP, describe_backend
from .pipeline import run
from .script_writer import ReelScript

log = logging.getLogger(__name__)
WEB_DIR = PROJECT_ROOT / "web"
MAX_BATCH = 15  # videos per Generate click
MEDIA_FILES = {"reel.mp4", "thumbnail.jpg", "review_frames.jpg"}


# ---------- background jobs ----------

class JobManager:
    """Runs generation jobs one at a time on a worker thread."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.jobs: deque[dict] = deque(maxlen=20)
        self.lock = threading.Lock()
        self.wake = threading.Event()
        threading.Thread(target=self._worker, daemon=True).start()

    def submit(self, topic: str | None, count: int, trigger: str) -> dict:
        job = {"id": uuid.uuid4().hex[:8], "topic": topic, "count": count, "trigger": trigger,
               "status": "queued", "log": [], "created": time.time(), "results": []}
        with self.lock:
            self.jobs.appendleft(job)
        self.wake.set()
        return job

    def busy(self) -> bool:
        return any(j["status"] in ("queued", "running") for j in self.jobs)

    def _next(self) -> dict | None:
        with self.lock:
            queued = [j for j in self.jobs if j["status"] == "queued"]
            return queued[-1] if queued else None

    def _worker(self) -> None:
        while True:
            job = self._next()
            if job is None:
                self.wake.wait(5)
                self.wake.clear()
                continue
            job["status"] = "running"

            def progress(msg: str, job=job) -> None:
                job["log"].append({"t": time.time(), "msg": msg})
                log.info("[job %s] %s", job["id"], msg)

            try:
                reports = run(load_settings(Config()), job["count"], job["topic"], progress)
                job["results"] = [r["id"] for r in reports]
                made = len(reports)
                job["status"] = "done" if made == job["count"] else ("partial" if made else "failed")
            except Exception as exc:  # never kill the worker thread
                progress(f"Error: {exc}")
                job["status"] = "failed"
            job["finished"] = time.time()


def scheduler(jobs: JobManager) -> None:
    """Daily auto-generation at the time set in Settings (local time)."""
    last_run_day = None
    while True:
        cfg = load_settings(Config())
        now = datetime.now()
        if cfg.schedule_time and now.strftime("%H:%M") == cfg.schedule_time and last_run_day != now.date():
            last_run_day = now.date()
            jobs.submit(None, max(1, min(cfg.schedule_count, MAX_BATCH)), "schedule")
        time.sleep(20)


# ---------- helpers ----------

def lan_ips() -> list[str]:
    ips = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # no packet is sent; picks the LAN interface
            ips.add(s.getsockname()[0])
    except OSError:
        pass
    try:
        ips.update(i[4][0] for i in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET))
    except OSError:
        pass
    return sorted(ip for ip in ips if not ip.startswith("127."))


def list_videos(cfg: Config) -> list[dict]:
    videos = []
    if cfg.output_dir.exists():
        for report in cfg.output_dir.glob("*/report.json"):
            try:
                data = json.loads(report.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            data["id"] = report.parent.name
            data.pop("checks", None)
            videos.append(data)
    return sorted(videos, key=lambda v: v.get("created_at", ""), reverse=True)


def video_dir(cfg: Config, video_id: str) -> Path:
    path = (cfg.output_dir / video_id).resolve()
    if path.parent != cfg.output_dir.resolve() or not (path / "report.json").exists():
        raise HTTPException(404, "video not found")
    return path


# ---------- app ----------

class GenerateRequest(BaseModel):
    topic: str | None = None
    count: int = 1


class PostEdit(BaseModel):
    caption: str = ""
    hashtags: list[str] = []
    youtube_title: str = ""
    youtube_description: str = ""
    youtube_hashtags: list[str] = []
    youtube_tags: list[str] = []


class LoginRequest(BaseModel):
    pin: str


def create_app(cfg: Config) -> FastAPI:
    app = FastAPI(title="Reel Studio", docs_url=None, redoc_url=None)
    jobs = JobManager(cfg)
    threading.Thread(target=scheduler, args=(jobs,), daemon=True).start()
    # Cookie value is a random session secret, so the PIN itself is never stored in the browser.
    session_token = secrets.token_urlsafe(24)

    @app.middleware("http")
    async def require_pin(request: Request, call_next):
        path = request.url.path
        public = not path.startswith(("/api/", "/media/")) or path == "/api/login"
        if cfg.app_pin and not public and request.cookies.get("reel_session") != session_token:
            return JSONResponse({"detail": "pin required"}, status_code=401)
        return await call_next(request)

    @app.post("/api/login")
    def login(body: LoginRequest):
        if not cfg.app_pin or not secrets.compare_digest(body.pin, cfg.app_pin):
            raise HTTPException(403, "wrong PIN")
        resp = JSONResponse({"ok": True})
        resp.set_cookie("reel_session", session_token, max_age=60 * 60 * 24 * 365, httponly=True, samesite="strict")
        return resp

    @app.get("/api/status")
    def status():
        current = load_settings(Config())
        return {
            "backend": describe_backend(current.ai_backend),
            "claude_code_installed": shutil.which("claude") is not None,
            "api_key_set": bool(os.environ.get("ANTHROPIC_API_KEY")),
            "pexels": bool(current.pexels_api_key),
            "telegram": bool(current.telegram_bot_token and current.telegram_chat_id),
            "urls": [f"http://{ip}:{cfg.port}" for ip in lan_ips()],
            "busy": jobs.busy(),
            "storage": str(current.output_dir),
        }

    @app.get("/api/videos")
    def videos():
        return list_videos(cfg)

    @app.get("/api/videos/{video_id}")
    def video(video_id: str):
        return json.loads((video_dir(cfg, video_id) / "report.json").read_text(encoding="utf-8"))

    @app.post("/api/videos/{video_id}/post-text")
    def write_post_text(video_id: str):
        """(Re)write the Instagram/YouTube text for a video, e.g. one made before this existed."""
        from .post_copy import apply_post_copy

        folder = video_dir(cfg, video_id)
        script = ReelScript.model_validate_json((folder / "script.json").read_text(encoding="utf-8"))
        report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
        try:
            apply_post_copy(report, script, load_settings(Config()), folder)
        except Exception as exc:
            raise HTTPException(502, f"Couldn't write the post text: {exc}")
        (folder / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        return report

    @app.put("/api/videos/{video_id}/post-text")
    def edit_post_text(video_id: str, body: PostEdit):
        """Save the user's edits to the caption, title, description, hashtags and tags."""
        from .post_copy import clean_tags, save_post_text

        folder = video_dir(cfg, video_id)
        report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
        report.update({
            "caption": body.caption.strip(),
            "hashtags": clean_tags(body.hashtags),
            "youtube_title": body.youtube_title.strip(),
            "youtube_description": body.youtube_description.strip(),
            "youtube_hashtags": clean_tags(body.youtube_hashtags),
            "youtube_tags": [t.strip() for t in body.youtube_tags if t.strip()],
            "post_edited": True,
        })
        save_post_text(report, folder)
        (folder / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        return report

    @app.delete("/api/videos/{video_id}")
    def delete_video(video_id: str):
        shutil.rmtree(video_dir(cfg, video_id))
        return {"ok": True}

    @app.get("/media/{video_id}/{name}")
    def media(video_id: str, name: str):
        if name not in MEDIA_FILES:
            raise HTTPException(404)
        path = video_dir(cfg, video_id) / name
        if not path.exists():
            raise HTTPException(404)
        return FileResponse(path)  # supports Range requests, which iPhone video playback needs

    @app.post("/api/generate")
    def generate(body: GenerateRequest):
        return jobs.submit((body.topic or "").strip() or None, max(1, min(body.count, MAX_BATCH)), "manual")

    @app.get("/api/jobs")
    def list_jobs():
        return list(jobs.jobs)

    @app.get("/api/settings")
    def get_settings():
        current = load_settings(Config())
        return {k: getattr(current, k) for k in EDITABLE}

    @app.post("/api/settings")
    def update_settings(updates: dict):
        current = save_settings(load_settings(Config()), updates)
        return {k: getattr(current, k) for k in EDITABLE}

    @app.get("/")
    def index():
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/{name}")
    def static_file(name: str):
        path = WEB_DIR / name
        if name in {"manifest.webmanifest", "sw.js", "icon-192.png", "icon-512.png"} and path.exists():
            return FileResponse(path)
        raise HTTPException(404)

    return app


def print_banner(cfg: Config) -> None:
    urls = [f"http://{ip}:{cfg.port}" for ip in lan_ips()]
    print("\n  Reel Studio is running")
    print(f"  On this computer:  http://localhost:{cfg.port}")
    for url in urls:
        print(f"  On your phone:     {url}   (same Wi-Fi)")
    print(f"  Videos are saved in: {cfg.output_dir}")
    ai = describe_backend(cfg.ai_backend)
    print(f"  AI: {ai}")
    if ai == "missing":
        print(f"  WARNING: {INSTALL_HELP}")
    if not cfg.app_pin:
        print("  Tip: set REEL_APP_PIN in .env so only you can use the app on your network.")
    if urls:
        try:
            import qrcode

            qr = qrcode.QRCode(border=1)
            qr.add_data(urls[0])
            print("\n  Scan with your phone camera:")
            qr.print_ascii(invert=True)
        except ImportError:
            pass
    print()


def serve(cfg: Config) -> None:
    import uvicorn

    cfg = load_settings(cfg)
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    print_banner(cfg)
    uvicorn.run(create_app(cfg), host="0.0.0.0", port=cfg.port, log_level="warning")
