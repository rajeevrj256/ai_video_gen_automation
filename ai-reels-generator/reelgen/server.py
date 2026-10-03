"""Local app server: `python -m reelgen serve`.

Runs on your computer, keeps every video on your disk (output/), and serves a
mobile-friendly web app. Open it on the computer, or on your phone over the same
Wi-Fi (scan the QR code printed at start-up) and "Add to Home Screen" to use it
like an app.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import os
import re
import secrets
import shutil
import socket
import subprocess
import threading
import time
import uuid
from collections import deque
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from . import tunnel
from .categories import CATEGORIES, categorize
from .config import EDITABLE, PROJECT_ROOT, Config, load_settings, save_settings
from .llm import INSTALL_HELP, describe_backend
from .pipeline import run
from .script_writer import ReelScript

log = logging.getLogger(__name__)
WEB_DIR = PROJECT_ROOT / "web"
MAX_BATCH = 15  # videos per Generate click
MAX_LONG_BATCH = 5  # long videos take much longer to make
MEDIA_FILES = {"reel.mp4", "thumbnail.jpg", "review_frames.jpg", "reel-myvoice.mp4", "thumbnail-youtube.jpg"}
THUMB_FILES = {"frames.jpg", "picture.jpg", "with-words.jpg"}


# ---------- background jobs ----------

class JobManager:
    """Runs generation jobs one at a time on a worker thread."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.jobs: deque[dict] = deque(maxlen=20)
        self.lock = threading.Lock()
        self.wake = threading.Event()
        threading.Thread(target=self._worker, daemon=True).start()

    def submit(self, topic: str | None, count: int, trigger: str, style: str | None = None,
               length: str = "short", resume: list[str] | None = None, **extra) -> dict:
        job = {"id": uuid.uuid4().hex[:8], "topic": topic, "count": count, "trigger": trigger, "resume": resume or [],
               "style": style or load_settings(Config()).video_style, "length": length,
               "status": "queued", "log": [], "created": time.time(), "results": [], **extra}
        with self.lock:
            self.jobs.appendleft(job)
        self.wake.set()
        return job

    def busy(self) -> bool:
        return any(j["status"] in ("queued", "running") for j in self.jobs)

    def _next(self) -> dict | None:
        with self.lock:
            queued = [j for j in self.jobs if j["status"] == "queued" and not j.get("started")]
            return queued[-1] if queued else None

    def _worker(self) -> None:
        while True:
            job = self._next()
            if job is None:
                self.wake.wait(5)
                self.wake.clear()
                continue
            # Each job runs in its own thread; pipeline.run's shared video slots decide how many
            # videos actually work at once. The job shows "Waiting" until its first video starts.
            job["started"] = True
            threading.Thread(target=self._run_job, args=(job,), daemon=True).start()

    def _run_job(self, job: dict) -> None:
        def progress(msg: str, job=job) -> None:
            job["status"] = "running"
            if "§usage " in msg or "§done " in msg or "§skip " in msg:  # token counts / finished video: data, not a log line
                tag, _, rest = msg.partition("§")
                kind, _, payload = rest.partition(" ")
                m = re.match(r"\[V(\d+)\]", tag.strip())
                try:
                    data = {**json.loads(payload), "video": int(m[1]) if m else 1}
                except ValueError:
                    return
                if kind == "skip":
                    job["skipped"] = job.get("skipped", 0) + 1
                else:
                    job.setdefault("usage" if kind == "usage" else "videos", []).append(data)
                return
            if "Saving progress in " in msg:  # remember each video's folder, to resume it later
                job.setdefault("folders", []).append(msg.rsplit("Saving progress in ", 1)[1].strip())
            job["log"].append({"t": time.time(), "msg": msg})
            log.info("[job %s] %s", job["id"], msg)

        progress.should_pause = lambda job=job: bool(job.get("pause"))  # checked at every step boundary
        try:
            cfg = load_settings(Config())
            cfg.video_style = job["style"]
            if job.get("captions") is not None:
                cfg.captions = bool(job["captions"])
            if job.get("voice"):  # a Script Video's own voice choice
                cfg.long_voice = job["voice"]
            if job.get("story_form"):
                cfg.story_form = job["story_form"]
            if job.get("myvoice"):
                from .myvoice import finish
                r = job["myvoice"]
                reports = [finish(cfg, video_dir(cfg, r["id"]), r["mode"], r["fit"], progress)]
            elif job.get("rerender"):
                from .rerender import rerender
                r = job["rerender"]
                reports = [rerender(cfg, video_dir(cfg, r["id"]), r.get("voice"), r.get("captions"), progress)]
            elif job.get("resume"):
                from .pipeline import resume_batch
                reports = resume_batch(cfg, job["resume"], progress)
                fresh = job["count"] - len(job["resume"])  # videos that never started before the pause
                if fresh > 0 and not job.get("pause"):
                    if job.get("stick_input"):
                        from .stickstory import StickRequest, run_stick_job
                        reports += run_stick_job(cfg, StickRequest(**job["stick_input"]), fresh, progress)
                    elif job.get("script_input"):  # stopped before its storyboard was saved: start it again
                        from .scriptvideo import ScriptInput, run_script_job
                        reports += run_script_job(cfg, ScriptInput(**job["script_input"]), progress)
                    elif job.get("length") in ("long", "medium"):
                        from .longform import run_long_batch
                        reports += run_long_batch(_long_cfg(cfg, job), fresh, job["topic"], progress)
                    else:
                        reports += run(cfg, fresh, job["topic"], progress)
            elif job.get("stick_input"):  # Stick Stories: stick-figure comedy episodes and Shorts
                from .stickstory import StickRequest, run_stick_job
                reports = run_stick_job(cfg, StickRequest(**job["stick_input"]), job["count"], progress)
            elif job.get("script_input"):  # Script Video: the user's own script through the long pipeline
                from .scriptvideo import ScriptInput, run_script_job
                reports = run_script_job(cfg, ScriptInput(**job["script_input"]), progress)
            elif job.get("length") in ("long", "medium"):
                from .longform import run_long_batch
                reports = run_long_batch(_long_cfg(cfg, job), job["count"], job["topic"], progress)
            else:
                reports = run(cfg, job["count"], job["topic"], progress)
            job["results"] = [r["id"] for r in reports]
            made = len(reports)
            job["status"] = ("done" if made == job["count"] else "paused" if job.get("pause")
                             else "partial" if made else "failed")
        except Exception as exc:  # never kill the worker thread
            progress(f"Error: {exc}")
            job["status"] = "failed"
        job["finished"] = time.time()
        try:
            from . import runlog
            runlog.record_job(self.cfg, job)
        except Exception:
            log.exception("Couldn't save the run history")


def _long_cfg(cfg: Config, job: dict) -> Config:
    """Medium jobs are long videos written for 5-6 minutes (fewer, shorter chapters)."""
    from dataclasses import replace

    from .longform import MEDIUM_MINUTES
    return replace(cfg, long_minutes=MEDIUM_MINUTES) if job.get("length") == "medium" else cfg


def scheduler(jobs: JobManager) -> None:
    """Runs every automation (Settings -> Automations) at its time, local time."""
    from . import automations

    while True:
        try:
            cfg = load_settings(Config())
            for a in automations.due(cfg, datetime.now()):
                jobs.submit(a.topic or None, a.count, f"automation: {a.name}", a.style, a.length, captions=a.captions)
        except Exception:  # a bad file must not stop the scheduler for good
            log.exception("Automation check failed")
        time.sleep(20)


# ---------- helpers ----------

def allowed_networks(spec: str) -> list:
    """REEL_ALLOWED_IPS ('100.101.102.103, 192.168.1.0/24') as networks; a bad entry is skipped with a warning."""
    nets = []
    for part in re.split(r"[,\s]+", spec or ""):
        if not part:
            continue
        try:
            nets.append(ipaddress.ip_network(part, strict=False))
        except ValueError:
            log.warning("REEL_ALLOWED_IPS: '%s' is not an IP address or network; ignored", part)
    return nets


def client_ip(request: Request) -> str:
    """Who is asking. A request through the Cloudflare tunnel arrives from this computer (cloudflared),
    with the visitor's real address in CF-Connecting-IP: that address counts, never 'this computer'."""
    host = request.client.host if request.client else ""
    forwarded = request.headers.get("cf-connecting-ip", "").strip()
    try:
        if forwarded and ipaddress.ip_address(host or "0.0.0.0").is_loopback:
            return forwarded
    except ValueError:
        pass
    return host


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
            data["category"] = categorize(data)  # saved one, or a keyword guess for older videos
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
    style: str | None = None  # facts | story | comedy | mix; empty = the style in Settings
    length: str = "short"  # "short" (30s, 9:16), "medium" (5-6 min) or "long" (8-10 min), both 16:9 animated
    captions: bool | None = None  # subtitles; empty = the Settings value
    story_form: str = "auto"  # long/medium: longform.STORY_FORMS key, or auto


class LicenceEdit(BaseModel):
    licence: str
    credit: str = ""


class LicenceAll(BaseModel):
    licence: str
    only_unknown: bool = True


class StickRequestBody(BaseModel):
    """Stick Stories: a stick-figure comedy episode (16:9) or Short (9:16)."""
    idea: str = ""
    format: str = "long"
    minutes: float = 5
    language: str = "english"
    speed: float = 1.5
    style: str = "comedy"  # comedy | fiction | facts
    cast: str = ""
    count: int = 1


class ScriptVideoRequest(BaseModel):
    """Script Video: the user's own finished, fact-checked title, description, hook and script."""
    title: str
    description: str = ""
    hook: str = ""
    script: str
    voice: str | None = None  # empty = the long-video voice in Settings
    captions: bool | None = None


class PostEdit(BaseModel):
    caption: str = ""
    hashtags: list[str] = []
    youtube_title: str = ""
    youtube_description: str = ""
    youtube_hashtags: list[str] = []
    youtube_tags: list[str] = []


class LoginRequest(BaseModel):
    pin: str


SAMPLES_DIR = PROJECT_ROOT.parent / "sample-videos"


def import_samples(cfg: Config) -> None:
    """Copy the example videos that come with the repo (sample-videos/<id>/) into the
    library once, so they show on the Videos page. One you delete stays deleted."""
    done_file = cfg.output_dir / "samples_imported.json"
    done = set(json.loads(done_file.read_text(encoding="utf-8"))) if done_file.exists() else set()
    for folder in sorted(SAMPLES_DIR.glob("*/report.json")) if SAMPLES_DIR.exists() else []:
        sample = folder.parent
        if sample.name in done:
            continue
        dest = cfg.output_dir / sample.name
        if not dest.exists():
            try:
                shutil.copytree(sample, dest)
                log.info("Added the sample video %s to the library", sample.name)
            except OSError as exc:
                log.warning("Couldn't add sample video %s: %s", sample.name, exc)
                shutil.rmtree(dest, ignore_errors=True)  # a half copy would show as a broken video
                continue
        done.add(sample.name)
        done_file.parent.mkdir(parents=True, exist_ok=True)
        done_file.write_text(json.dumps(sorted(done)), encoding="utf-8")


def _renderer() -> str:
    """Which browser draws the video frames, as this running app read it from .env at start."""
    chrome = os.environ.get("REEL_CHROME", "").strip()
    gl = os.environ.get("REEL_GL", "").strip()
    gl = "" if gl.startswith("#") else gl
    if chrome.lower() == "chrome-for-testing":
        browser = "Chrome for Testing (can use the GPU)"
    elif chrome:
        browser = f"Chrome at {chrome}"
    else:
        browser = "headless shell (draws on the CPU on Windows)"
    return f"{browser} · REEL_GL={gl or 'empty'}"


def create_app(cfg: Config) -> FastAPI:
    app = FastAPI(title="Reel Studio", docs_url=None, redoc_url=None)
    jobs = JobManager(cfg)
    import_samples(cfg)
    # Which code this server is running (shown in Settings), so a git pull without a
    # restart is easy to spot: the running app keeps the code it started with.
    try:
        running_version = subprocess.run(["git", "log", "-1", "--format=%h %cd", "--date=format:%d %b %H:%M"],
                                         cwd=Path(__file__).resolve().parent, capture_output=True, text=True,
                                         timeout=10).stdout.strip() or "unknown"
    except Exception:
        running_version = "unknown"
    threading.Thread(target=scheduler, args=(jobs,), daemon=True).start()
    # Cookie value is a random session secret, so the PIN itself is never stored in the browser.
    session_token = secrets.token_urlsafe(24)

    networks = allowed_networks(cfg.allowed_ips)
    failed: dict[str, list[float]] = {}  # wrong PINs per address, for the lockout

    @app.middleware("http")
    async def require_pin(request: Request, call_next):
        # Only the addresses in REEL_ALLOWED_IPS (and this computer) get anything at all, the page included.
        if networks:
            try:
                ip = ipaddress.ip_address(client_ip(request) or "0.0.0.0")
            except ValueError:
                ip = None
            if ip is None or not (ip.is_loopback or any(ip in n for n in networks)):
                return JSONResponse({"detail": "not allowed from this address"}, status_code=403)
        path = request.url.path
        public = not path.startswith(("/api/", "/media/")) or path == "/api/login"
        if cfg.app_pin and not public and request.cookies.get("reel_session") != session_token:
            return JSONResponse({"detail": "pin required"}, status_code=401)
        return await call_next(request)

    @app.post("/api/login")
    def login(body: LoginRequest, request: Request):
        # 5 wrong PINs from one address lock it out for 15 minutes, and 20 from anywhere lock out every
        # address but this computer's, so a PIN can't be guessed from many addresses either.
        who = client_ip(request) or "?"
        now = time.time()
        recent = [t for t in failed.get(who, []) if now - t < 900]
        everyone = sum(1 for k, ts in failed.items() if not k.startswith(("127.", "::1")) for t in ts if now - t < 900)
        try:
            local = ipaddress.ip_address(who).is_loopback
        except ValueError:
            local = False
        if len(recent) >= 5 or (everyone >= 20 and not local):
            raise HTTPException(429, "Too many wrong PINs. Try again in 15 minutes.")
        if not cfg.app_pin or not secrets.compare_digest(body.pin, cfg.app_pin):
            failed[who] = recent + [now]
            raise HTTPException(403, "wrong PIN")
        failed.pop(who, None)
        resp = JSONResponse({"ok": True})
        https = request.headers.get("x-forwarded-proto") == "https" or request.url.scheme == "https"
        resp.set_cookie("reel_session", session_token, max_age=60 * 60 * 24 * 365, httponly=True, samesite="strict",
                        secure=https)
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
            "public_url": tunnel.state["url"], "public_error": tunnel.state["error"],
            "busy": jobs.busy(),
            "storage": str(current.output_dir),
            "version": running_version,
            "renderer": _renderer(),
        }

    @app.get("/api/videos")
    def videos():
        import_samples(cfg)  # cheap when nothing is new; a refresh picks up samples a pull added
        return list_videos(cfg)

    @app.get("/api/videos/{video_id}")
    def video(video_id: str):
        report = json.loads((video_dir(cfg, video_id) / "report.json").read_text(encoding="utf-8"))
        report["category"] = categorize(report)
        return report

    @app.post("/api/videos/{video_id}/post-text")
    def write_post_text(video_id: str):
        """(Re)write the Instagram/YouTube text for a video, e.g. one made before this existed."""
        from .post_copy import apply_post_copy, save_post_text

        folder = video_dir(cfg, video_id)
        report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
        if report.get("format") == "long":  # long videos have their own script and chapters
            from .longform import LongScript, write_long_post

            long_script = LongScript.model_validate_json((folder / "script.json").read_text(encoding="utf-8"))
            try:
                report.update(write_long_post(long_script, {"chapters": report.get("chapters", [])}, load_settings(Config())))
            except Exception as exc:
                raise HTTPException(502, f"Couldn't write the post text: {exc}")
            report.pop("post_text_error", None)
            save_post_text(report, folder)
            (folder / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
            return report
        data = json.loads((folder / "script.json").read_text(encoding="utf-8"))
        for field in ("subject", "hook_question", "answer"):  # scripts saved before these fields existed
            data.setdefault(field, "")
        if data.get("category") not in CATEGORIES:
            data["category"] = categorize(report)
        script = ReelScript.model_validate(data)
        report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
        try:
            apply_post_copy(report, script, load_settings(Config()), folder)
        except Exception as exc:
            raise HTTPException(502, f"Couldn't write the post text: {exc}")
        (folder / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        return report

    @app.get("/api/history")
    def run_history():
        from . import runlog

        return runlog.history(cfg)

    @app.post("/api/videos/{video_id}/rerender")
    def rerender_video(video_id: str, body: dict):
        """New voice and/or subtitles on or off: same script and footage, no Claude tokens."""
        report = json.loads((video_dir(cfg, video_id) / "report.json").read_text(encoding="utf-8"))
        if any(j.get("rerender", {}).get("id") == video_id for j in jobs.jobs if j["status"] in ("queued", "running")):
            raise HTTPException(409, "This video is already being re-made")
        return jobs.submit(f"Re-make: {report.get('title', video_id)}", 1, "rerender", report.get("style"),
                           report.get("format", "short"),
                           rerender={"id": video_id, "voice": body.get("voice") or None,
                                     "captions": None if body.get("captions") is None else bool(body.get("captions"))})

    # ---- your own voiceover ----
    @app.get("/api/videos/{video_id}/myvoice")
    def my_voice_state(video_id: str):
        from . import myvoice

        return myvoice.segments(video_dir(cfg, video_id))

    @app.post("/api/videos/{video_id}/myvoice/take")
    async def my_voice_take(video_id: str, part: str, name: str, request: Request):
        """One recording (the raw file is the body): part 'all' for one take, or a line number."""
        from . import myvoice

        folder = video_dir(cfg, video_id)
        if part != "all" and not part.isdigit():
            raise HTTPException(400, "part must be 'all' or a line number")
        try:
            saved = myvoice.save_take(folder, part, name, await request.body())
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        return {"file": saved, "takes": myvoice.takes(folder)}

    @app.get("/api/videos/{video_id}/myvoice/file/{name}")
    def my_voice_file(video_id: str, name: str):
        from . import myvoice

        path = video_dir(cfg, video_id) / myvoice.TAKES / Path(name).name
        if not path.is_file():
            raise HTTPException(404)
        return FileResponse(path)

    @app.post("/api/videos/{video_id}/myvoice/finish")
    def my_voice_finish(video_id: str, body: dict):
        report = json.loads((video_dir(cfg, video_id) / "report.json").read_text(encoding="utf-8"))
        if any(j.get("myvoice", {}).get("id") == video_id for j in jobs.jobs if j["status"] in ("queued", "running")):
            raise HTTPException(409, "Your voice version of this video is already being made")
        mode = "all" if body.get("mode") == "all" else "parts"
        fit = "slides" if body.get("fit") == "slides" else "mine"
        return jobs.submit(f"My voice: {report.get('title', video_id)}", 1, "myvoice", report.get("style"),
                           report.get("format", "short"), myvoice={"id": video_id, "mode": mode, "fit": fit})

    @app.get("/api/categories")
    def list_categories():
        return list(CATEGORIES)

    @app.post("/api/videos/{video_id}/category")
    def set_category(video_id: str, body: dict):
        if body.get("category") not in CATEGORIES:
            raise HTTPException(400, "Unknown category")
        folder = video_dir(cfg, video_id)
        report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
        report["category"] = body["category"]
        (folder / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        return {"category": report["category"]}

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

    @app.get("/api/videos/{video_id}/used")
    def video_media_used(video_id: str):
        from .used import media_used

        return media_used(load_settings(Config()), video_dir(cfg, video_id))

    @app.get("/media/{video_id}/sound/{path:path}")
    def video_sound(video_id: str, path: str):
        """A music or sound-effect file of a video, to preview it from the effects list."""
        folder = video_dir(cfg, video_id).resolve()
        file = (folder / path).resolve()
        if file.parent not in (folder, folder / "sfx", folder / "music") or file.suffix.lower() not in (".wav", ".mp3", ".ogg", ".m4a"):
            raise HTTPException(404)
        if not file.is_file():
            raise HTTPException(404)
        return FileResponse(file)

    @app.get("/media/{video_id}/thumb/{name}")
    def thumb_media(video_id: str, name: str):
        from .thumbnail import FOLDER

        path = video_dir(cfg, video_id) / FOLDER / name
        if name not in THUMB_FILES or not path.exists():
            raise HTTPException(404)
        return FileResponse(path)

    # ---- YouTube thumbnail (reelgen/thumbnail.py): Claude plans, Gemini draws, Claude checks ----
    @app.post("/api/videos/{video_id}/thumbnail/plan")
    def plan_thumbnail(video_id: str):
        from . import thumbnail

        try:
            return thumbnail.plan(load_settings(Config()), video_dir(cfg, video_id))
        except Exception as exc:
            raise HTTPException(502, f"Couldn't design the thumbnail: {exc}")

    @app.post("/api/videos/{video_id}/thumbnail/upload")
    async def upload_thumbnail(video_id: str, request: Request, words: bool = True):
        from starlette.concurrency import run_in_threadpool

        from . import thumbnail

        folder = video_dir(cfg, video_id)
        data = await request.body()
        try:
            return await run_in_threadpool(thumbnail.upload, load_settings(Config()), folder, data, words)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        except Exception as exc:
            raise HTTPException(502, f"Couldn't check the thumbnail: {exc}")

    @app.post("/api/generate")
    def generate(body: GenerateRequest):
        style = body.style if body.style in ("facts", "story", "comedy", "mix") else None
        length = body.length if body.length in ("long", "medium") else "short"
        return jobs.submit((body.topic or "").strip() or None, max(1, min(body.count, MAX_BATCH if length == "short" else MAX_LONG_BATCH)),
                           "manual", style, length, captions=body.captions,
                           story_form=body.story_form if length != "short" else None)

    @app.get("/api/stick/voices")
    def stick_voices():
        from .stickstory import VOICE_NAMES, VOICE_POOLS

        return {"names": VOICE_NAMES, "pools": VOICE_POOLS}

    @app.get("/api/stick/voice-preview")
    def stick_voice_preview(voice: str, speed: float = 1.5, name: str = ""):
        from .stickstory import voice_preview

        try:
            return FileResponse(voice_preview(cfg, voice, speed, name[:30]), media_type="audio/wav")
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        except Exception as exc:
            raise HTTPException(502, f"Couldn't make the sample: {exc}")

    @app.post("/api/stick")
    def stick(body: StickRequestBody):
        from .stickstory import DEFAULT_CAST

        fmt = "short" if body.format == "short" else "long"
        given = {"idea": body.idea.strip()[:1000], "format": fmt, "minutes": min(8.0, max(2.0, float(body.minutes))),
                 "language": body.language if body.language in ("english", "hindi") else "english",
                 "speed": min(2.0, max(0.8, float(body.speed))), "cast": body.cast.strip() or DEFAULT_CAST,
                 "style": body.style if body.style in ("comedy", "fiction", "facts") else "comedy"}
        return jobs.submit(body.idea.strip()[:80] or None, max(1, min(body.count, 5)), "stick",
                           {"facts": "facts", "fiction": "story"}.get(given["style"], "comedy"),
                           "stick-short" if fmt == "short" else "stick", stick_input=given, captions=False)

    @app.post("/api/script-video")
    def script_video(body: ScriptVideoRequest):
        from .scriptvideo import parse_script

        title, script = body.title.strip(), body.script.strip()
        if not title or not script:
            raise HTTPException(400, "The title and the script are needed.")
        if not parse_script(script)[0]:
            raise HTTPException(400, "The script has no lines to read.")
        given = {"title": title, "description": body.description.strip(), "hook": body.hook.strip(), "script": script}
        return jobs.submit(title, 1, "script", None, "script", script_input=given, voice=body.voice or None,
                           captions=body.captions)

    @app.get("/api/jobs")
    def list_jobs():
        now = time.time()  # lets the page run its timers on this computer's clock
        return [{**j, "now": now} for j in jobs.jobs]

    def busy_folders() -> set[str]:
        return {f for j in jobs.jobs if j["status"] in ("queued", "running") for f in j.get("folders", []) + j.get("resume", [])}

    @app.delete("/api/jobs/{job_id}")
    def remove_job(job_id: str, discard: bool = False):
        """Take a finished or failed job off the list; `discard` also deletes the files of
        videos it left unfinished (they can't be resumed after that)."""
        from .pipeline import CHECKPOINT
        with jobs.lock:
            job = next((j for j in jobs.jobs if j["id"] == job_id), None)
            if job is None:
                raise HTTPException(404, "No such job")
            if job["status"] in ("queued", "running"):
                raise HTTPException(409, "Pause it first; a running job can't be removed")
            jobs.jobs.remove(job)
        if discard:
            busy = busy_folders()
            for f in set(job.get("folders", []) + job.get("resume", [])) - busy:
                path = (cfg.output_dir / f).resolve()
                if path.parent == cfg.output_dir.resolve() and (path / CHECKPOINT).exists():
                    shutil.rmtree(path, ignore_errors=True)
        return {"ok": True}

    @app.post("/api/jobs/clear")
    def clear_jobs():
        """Remove every job that has finished (done, failed, partial or paused) from the list."""
        with jobs.lock:
            keep = [j for j in jobs.jobs if j["status"] in ("queued", "running")]
            jobs.jobs.clear()
            jobs.jobs.extend(keep)
        return {"ok": True}

    @app.delete("/api/unfinished/{folder_id}")
    def discard_unfinished(folder_id: str):
        from .pipeline import CHECKPOINT
        path = (cfg.output_dir / folder_id).resolve()
        if path.parent != cfg.output_dir.resolve() or not (path / CHECKPOINT).exists():
            raise HTTPException(404, "Not an unfinished video")
        if folder_id in busy_folders():
            raise HTTPException(409, "It's being made right now")
        shutil.rmtree(path, ignore_errors=True)
        return {"ok": True}

    @app.get("/api/unfinished")
    def list_unfinished():
        """Videos that stopped part-way (failed, or the app was closed) and can be resumed."""
        from .pipeline import unfinished

        busy = busy_folders()
        return [u for u in unfinished(cfg) if u["id"] not in busy]

    @app.post("/api/resume")
    def resume(body: dict):
        from .pipeline import unfinished

        available = {u["id"] for u in unfinished(cfg)} - busy_folders()
        folders = [f for f in body.get("folders", []) if f in available]
        if not folders:
            raise HTTPException(400, "Nothing saved to resume for these videos; generate them again.")
        return jobs.submit(None, len(folders), "resume", resume=folders)

    @app.post("/api/jobs/{job_id}/pause")
    def pause_job(job_id: str):
        """Stop after the step each video is on; its progress is saved for Resume."""
        job = next((j for j in jobs.jobs if j["id"] == job_id), None)
        if job is None:
            raise HTTPException(404, "No such job")
        if job["status"] == "queued" and not job.get("started"):
            job["status"] = "paused"
        job["pause"] = True
        return {"ok": True}

    @app.post("/api/jobs/{job_id}/resume")
    def resume_job(job_id: str):
        from .pipeline import unfinished

        job = next((j for j in jobs.jobs if j["id"] == job_id), None)
        if job is None:
            raise HTTPException(404, "No such job")
        available = {u["id"] for u in unfinished(cfg)} - busy_folders()
        folders = list(dict.fromkeys(f for f in job.get("folders", []) if f in available))
        fresh = job.get("skipped", 0) + (job["count"] if job["status"] == "paused" and not job.get("started") else 0)
        if not folders and not fresh:
            raise HTTPException(400, "Nothing saved to resume for these videos; generate them again.")
        return jobs.submit(job["topic"], len(folders) + fresh, "resume", job.get("style"), job.get("length", "short"),
                           resume=folders, script_input=job.get("script_input"), stick_input=job.get("stick_input"),
                           voice=job.get("voice"),
                           captions=job.get("captions"), story_form=job.get("story_form"))

    @app.get("/api/automations")
    def list_automations():
        from . import automations

        now = datetime.now()
        return [{**a.model_dump(), "next": automations.next_run(a, now)} for a in automations.load(cfg)]

    @app.post("/api/automations")
    def save_automation(body: dict):
        from . import automations

        try:
            return automations.upsert(cfg, automations.Automation(**body)).model_dump()
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    @app.delete("/api/automations/{automation_id}")
    def delete_automation(automation_id: str):
        from . import automations

        automations.delete(cfg, automation_id)
        return {"ok": True}

    @app.post("/api/automations/{automation_id}/run")
    def run_automation_now(automation_id: str):
        from . import automations

        a = next((x for x in automations.load(cfg) if x.id == automation_id), None)
        if a is None:
            raise HTTPException(404, "No such automation")
        return jobs.submit(a.topic or None, a.count, f"automation: {a.name}", a.style, a.length, captions=a.captions)

    @app.get("/api/library")
    def library():
        from . import media

        return media.listing(cfg)

    @app.get("/api/library/licences")
    def library_licences():
        from . import media

        return media.LICENCES

    @app.put("/api/library/licences")
    def set_all_library_licences(body: LicenceAll):
        from . import media

        try:
            return {"changed": media.set_all_licences(cfg, body.licence, body.only_unknown)}
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    @app.post("/api/library/{kind}")
    async def upload_to_library(kind: str, name: str, request: Request, licence: str = "unknown", credit: str = ""):
        # The raw file is the request body (no form encoding), so no extra upload package is needed.
        from . import media

        try:
            path = media.save_upload(cfg, kind, name, await request.body(), licence, credit)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        return {"file": path.name, "name": media.slug(path.name)}

    @app.get("/api/library/{kind}/{name}")
    def library_file(kind: str, name: str):
        from . import media

        if kind not in media.KINDS:
            raise HTTPException(404)
        path = media.folder(cfg, kind) / Path(name).name
        if not path.is_file():
            raise HTTPException(404)
        return FileResponse(path)

    @app.put("/api/library/{kind}/{name}/licence")
    def set_library_licence(kind: str, name: str, body: LicenceEdit):
        from . import media

        try:
            media.set_licence(cfg, kind, name, body.licence, body.credit)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        return {"ok": True}

    @app.delete("/api/library/{kind}/{name}")
    def delete_from_library(kind: str, name: str):
        from . import media

        media.remove(cfg, kind, name)
        return {"ok": True}

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
        # Always ask for the page again: after an update the browser must not show the old one.
        return FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-cache"})

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
    if cfg.allowed_ips:
        print(f"  Only these addresses may open it: {cfg.allowed_ips} (and this computer)")
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
    tunnel.start(cfg)
    uvicorn.run(create_app(cfg), host="0.0.0.0", port=cfg.port, log_level="warning")
