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
import sys
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

# A video (or a whole job) that failed: also sent on Telegram, so it's seen away from the computer.
FAIL_LINE = re.compile(r"(?:^|\]\s*)(Video \d+ failed: |Error: )")


class PowerBody(BaseModel):
    on: bool


class UpdateBody(BaseModel):
    force: bool = False  # stop running videos too


def job_label(job: dict) -> str:
    inp = (job.get("anim_input") or job.get("toon_input") or job.get("stick_input") or job.get("script_input")
           or job.get("story_input") or job.get("shoot_input") or {})
    what = job.get("title") or inp.get("title") or inp.get("topic") or inp.get("idea") or job.get("topic") or "automatic topic"
    kind = ("Animated" if job.get("anim_input") else "Toon" if job.get("toon_input") else "Stick" if job.get("stick_input") else "Script Video" if job.get("script_input")
            else "Shorts Studio" if job.get("story_input") else "Shoot" if job.get("shoot_input")
            else "New hook" if job.get("rehook") else "Re-make" if job.get("rerender") else "My voice" if job.get("myvoice") else str(job.get("length") or "short").title())
    return f"{what} · {kind}"


def alert(text: str) -> None:
    """Send a Telegram message in the background (no-op without a bot token)."""
    from .notifier import send_text

    current = load_settings(Config())
    if current.telegram_bot_token and current.telegram_chat_id:
        threading.Thread(target=send_text, args=(current.telegram_bot_token, current.telegram_chat_id, text), daemon=True).start()


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
            if "§live " in msg:  # what the current step is doing right now: shown, never logged
                job["live"] = {"msg": msg.replace("§live ", ""), "t": time.time()}
                return
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
            if FAIL_LINE.search(msg) and not job.get("cancel") and msg not in job.setdefault("alerted", []):
                job["alerted"].append(msg)
                alert(f"⚠️ Reel Studio: a video failed\n{job_label(job)}\n\n{msg[:1500]}\n\n"
                      + ("Open the app and press 'Resume from where it stopped' (nothing done so far is redone)."
                         if job.get("folders") else "Open the app to see the full log."))

        progress.should_pause = lambda job=job: bool(job.get("pause"))  # checked at every step boundary
        # Stop and remove: kills the Claude call or render running now (reelgen/stopper.py).
        progress.should_pause.stop = lambda job=job: bool(job.get("cancel"))
        try:
            cfg = load_settings(Config())
            cfg.video_style = job["style"]
            if job.get("captions") is not None:
                cfg.captions = bool(job["captions"])
            if job.get("voice"):  # a Script Video's own voice choice
                cfg.long_voice = job["voice"]
            if job.get("story_form"):
                cfg.story_form = job["story_form"]
            if job.get("memes") in ("off", "some", "lots"):  # memes.LEVELS: this video's own choice
                cfg.memes = job["memes"]
            if job.get("hook_template") in ("auto", "kinetic", "rapid", "stakes", "cinematic"):  # cinehook.TEMPLATES: how this video opens
                cfg.hook_template = job["hook_template"]
            if re.fullmatch(r"[+-]\d{1,2}%", str(job.get("voice_rate") or "")):  # a Script Video's own speaking pace
                cfg.long_voice_rate = job["voice_rate"]
            if job.get("myvoice"):
                from .myvoice import finish
                r = job["myvoice"]
                reports = [finish(cfg, video_dir(cfg, r["id"]), r["mode"], r["fit"], progress)]
            elif job.get("anim_hd"):  # a finished animated video, its clips upscaled and re-edited
                from .animated import sharpen_video
                reports = [sharpen_video(cfg, video_dir(cfg, job["anim_hd"]["id"]), progress)]
            elif job.get("sound_remove"):  # a sound taken out of a finished video (reelgen/remix.py)
                from .remix import remove_sound
                r = job["sound_remove"]
                reports = [remove_sound(cfg, video_dir(cfg, r["id"]), r["name"], progress)]
            elif job.get("anim_music"):  # a finished animated video, its music made by ACE-Step again
                from .animated import redo_music
                reports = [redo_music(cfg, video_dir(cfg, job["anim_music"]["id"]), progress)]
            elif job.get("rehook"):  # a finished video copied to a new one with a new hook (reelgen/rehook.py)
                from .rehook import save_as_new
                reports = [save_as_new(cfg, video_dir(cfg, job["rehook"]["id"]), job["rehook"]["key"], progress)]
            elif job.get("rerender"):
                from .rerender import rerender
                r = job["rerender"]
                reports = [rerender(cfg, video_dir(cfg, r["id"]), r.get("voice"), r.get("captions"), progress, r.get("pace"))]
            elif job.get("anim_input"):  # Animated videos (reelgen/animated.py), new or resumed
                from .animated import AnimRequest, run_anim_job
                reports = run_anim_job(cfg, AnimRequest(**job["anim_input"]), job["count"], progress, job.get("anim_resume"))
            elif job.get("story_input"):  # Story Shorts (reelgen/storyshorts.py), new or resumed
                from .storyshorts import StoryRequest, run_story_job
                reports = run_story_job(cfg, StoryRequest(**job["story_input"]), progress, job.get("story_resume"))
            elif job.get("toon_input"):  # Toon Explainers (reelgen/toon.py), new or resumed
                from .toon import ToonRequest, run_toon_job
                reports = run_toon_job(cfg, ToonRequest(**job["toon_input"]), job["count"], progress, job.get("toon_resume"))
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
                    elif job.get("shoot_input"):  # stopped before its folder was made: start it again
                        from .shoot import run_shoot_job
                        reports += run_shoot_job(cfg, job["shoot_input"]["id"], progress)
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
            elif job.get("shoot_input"):  # Shoot: the user's own filmed takes through the long pipeline
                from .shoot import run_shoot_job
                reports = run_shoot_job(cfg, job["shoot_input"]["id"], progress)
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


def _video_folders(cfg: Config, job: dict, n: int) -> list[Path]:
    """Video n's folders from its job log, newest first: the finished video (§done), then the working
    folder ('Saving progress in ...')."""
    cur, found = 1, []
    for entry in job.get("log", []):
        msg = entry.get("msg", "")
        tag = re.match(r"^\[V(\d+)\] (.*)$", msg, re.S)
        k = cur
        if tag:
            k, msg = int(tag.group(1)), tag.group(2)
        mark = re.match(r"^=== Video (\d+)/", msg)
        if mark:
            cur = k = int(mark.group(1))
        if k != n:
            continue
        saving = re.match(r"^Saving progress in (\S+)", msg)
        if saving:
            found.append(cfg.output_dir / saving.group(1))
        if msg.startswith("§done "):
            try:
                found.append(cfg.output_dir / json.loads(msg[6:])["id"])
            except (ValueError, KeyError):
                pass
    root = cfg.output_dir.resolve()
    return [f for f in reversed(found) if f.resolve().parent == root and f.is_dir()]


def _latest_script(folder: Path) -> dict | None:
    """The newest script in a video folder: the draft written right after Claude, the checkpoint's
    (after fixes), the finished script.json, or a stick episode."""
    best, when = None, -1.0
    for name in ("draft.json", "checkpoint.json", "script.json", "episode.json"):
        path = folder / name
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if name == "checkpoint.json":
            data = data.get("script")
        if isinstance(data, dict) and path.stat().st_mtime > when:
            best, when = data, path.stat().st_mtime
    return best


def script_view(d: dict) -> dict:
    """Any of the pipelines' scripts as {title, about, sections: [{heading, lines: [{who, text, note}]}]}."""
    sections, hook_text = [], ""
    if "chapters" in d:  # medium/long video or Script Video
        hook = [{"text": h.get("line") or "(no words: picture and sound)", "note": h.get("text") and f"on screen: {h['text']}"}
                for h in d.get("hook") or []]
        if hook:
            sections.append({"heading": "Hook", "lines": hook})
        for i, c in enumerate(d.get("chapters") or [], 1):
            sections.append({"heading": f"{i}. {c.get('title', '')}", "lines": [
                {"text": b.get("narration", ""), "note": ((b.get("visual") or {}).get("type") or "")
                 + (f": {(b.get('visual') or {}).get('headline')}" if (b.get("visual") or {}).get("headline") else "")}
                for b in c.get("beats") or []]})
        title = d.get("youtube_title") or d.get("topic", "")
    elif "cold_open" in d and "chapters" in d:  # Animated video (reelgen/animated.py)
        for name, shots in [("Cold open", d.get("cold_open") or [])] + [
                (f"{i}. {c.get('title', '')}", c.get("shots") or []) for i, c in enumerate(d.get("chapters") or [], 1)]:
            sections.append({"heading": name, "lines": [
                {"text": sh.get("line", ""), "note": sh.get("scene", "")[:140]} for sh in shots]})
        title = d.get("title", "")
    elif "segments" in d:  # Toon Explainer (reelgen/toon.py)
        for i, seg in enumerate(d.get("segments") or [], 1):
            head = (f"#{seg['number']} " if seg.get("number") else f"{i}. ") + (seg.get("heading") or "")
            sections.append({"heading": head.strip(), "lines": [
                {"text": sh.get("line", ""), "note": " · ".join(x for x in (sh.get("action", ""), sh.get("backdrop", ""),
                                                                            sh.get("slam") and f"slam: {sh['slam']}") if x)}
                for sh in seg.get("shots") or []]})
        title = d.get("title", "")
    elif d.get("scenes") and "lines" in (d["scenes"][0] or {}):  # stick story
        for i, sc in enumerate(d["scenes"], 1):
            sections.append({"heading": f"Scene {i} · {sc.get('setting', '')}", "lines": [
                {"who": "" if ln.get("speaker") in ("none", "") else ln.get("speaker"),
                 "text": ln.get("line") or "(a silent beat)", "note": ln.get("emotion", "") if ln.get("line") else ""}
                for ln in sc.get("lines") or []]})
        title = d.get("title", "")
    else:  # a Short
        sections.append({"heading": "Scenes", "lines": [
            {"text": sc.get("narration", ""), "note": ((sc.get("graphic") or {}).get("type") or "") if (sc.get("graphic") or {}).get("type") not in (None, "none") else ""}
            for sc in d.get("scenes") or []]})
        title = d.get("youtube_title") or d.get("title", "")
        hook_text = d.get("title", "")  # the on-screen hook of the first seconds
    about = d.get("subject") or d.get("logline") or d.get("why_chosen") or ""
    words = sum(len(str(l.get("text", "")).split()) for s_ in sections for l in s_["lines"])
    return {"title": title, "about": about, "hook": hook_text, "sections": sections, "words": words}


def _code_stamp() -> float:
    """Newest change to the app's Python code on disk."""
    return max((p.stat().st_mtime for p in Path(__file__).resolve().parent.glob("*.py")), default=0.0)


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
    memes: str = ""  # long/medium: off | some | lots (reelgen/memes.py); empty = the Settings value
    hook_template: str = ""  # long/medium: cinehook.TEMPLATES key or auto; empty = the Settings value


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
    seconds: int = 0  # Short length: 15, 30, 45 (0 = 25-50 s)
    language: str = "english"
    speed: float = 1.5
    style: str = "comedy"  # comedy | fiction | facts
    cast: str = ""
    count: int = 1


class ToonRequestBody(BaseModel):
    """Toon Explainers: a flat-animated explainer (16:9) with cartoon people and a mascot."""
    topic: str = ""
    minutes: float = 3
    form: str = "auto"
    voice: str = "en-US-AndrewMultilingualNeural"
    speed: int = 12
    captions: bool = True
    watermark: str = ""
    count: int = 1


class MusicTestBody(BaseModel):
    """Anim tab, "Try the music model": one track from ACE-Step, described in words."""
    caption: str
    seconds: float = 30
    bpm: int | None = None


class StoryBody(BaseModel):
    """Shorts Studio: 9:16 Shorts (one or a series), any mix of source, kind, voice language and look."""
    source: str = "ai"  # ai | script
    topic: str = ""
    kind: str = "story"  # story | facts | explainer | news | comedy
    script: str = ""
    title: str = ""
    parts: int = 3
    split: str = "auto"  # your script: auto (natural length, parts at 'Part 2') | length | one
    seconds: int = 30
    language: str = "english"  # english | hinglish | hindi
    screen_text: str = "english"  # english | voice
    visuals: str = "anim"  # anim | key | pictures | footage | graphics
    memes: str = ""  # the graphics look: off | some | lots (reelgen/memes.py); empty = the Settings value
    style: str = "auto"
    quality: str = "auto"
    upscale: bool = True
    voice: str = ""
    speed: int = 8
    captions: bool = False
    watermark: str = ""


class AnimRequestBody(BaseModel):
    """Animated videos: every shot an AI picture and clip, made on this computer (reelgen/animated.py)."""
    topic: str = ""
    minutes: float = 7
    style: str = "auto"
    motion: str = "full"  # full | key | stills
    quality: str = "auto"  # auto | fast | standard | high (animated.CLIP_SIZES)
    upscale: bool = True  # sharpen clips and pictures to full HD (AI upscaler)
    voice: str = "en-US-AndrewMultilingualNeural"
    speed: int = 8
    captions: bool = False
    watermark: str = ""
    count: int = 1


class SoundRemoveBody(BaseModel):
    name: str  # the sound as the Effects & media used panel names it


class ShootBody(BaseModel):
    """A Shoot project (reelgen/shoot.py): your script, filmed by you shot by shot."""
    title: str
    description: str = ""
    hook: str = ""
    script: str
    language: str = "english"  # english | hinglish | hindi (speech following and transcription)
    format: str = "long"  # long (16:9) | short (9:16)
    screen_text: str = "english"


class ShootMakeBody(BaseModel):
    captions: bool | None = None


class ShootVoiceBody(BaseModel):
    clean: bool | None = None  # noise, hum and room taken out of your takes
    fix: bool | None = None  # words you skipped rebuilt in your voice
    choices: dict[str, bool] | None = None  # 'Rebuild in my voice' ticks on take cards ("shot|line:word": on/off)


class ScriptVideoRequest(BaseModel):
    """Script Video: the user's own finished, fact-checked title, description, hook and script."""
    title: str
    description: str = ""
    hook: str = ""
    script: str
    voice: str | None = None  # empty = the long-video voice in Settings
    captions: bool | None = None
    screen_text: str = "english"  # words on screen: English (a Hinglish script still speaks Hinglish) or 'script'
    memes: str = ""  # off | some | lots (reelgen/memes.py); empty = the Settings value
    hook_template: str = ""  # cinehook.TEMPLATES key or auto; empty = the Settings value
    voice_rate: str = ""  # speaking pace, e.g. '-5%'; empty = Settings > Speaking pace (long and Script videos)


class PostEdit(BaseModel):
    caption: str = ""
    hashtags: list[str] = []
    youtube_title: str = ""
    youtube_description: str = ""
    youtube_hashtags: list[str] = []
    youtube_tags: list[str] = []


class ReviewBody(BaseModel):
    decision: str  # accept | reject


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
    from .media import forget_removed
    forget_removed(cfg)  # sounds you asked to have deleted from your library
    # Which code this server is running (shown in Settings), so a git pull without a
    # restart is easy to spot: the running app keeps the code it started with.
    try:
        running_version = subprocess.run(["git", "log", "-1", "--format=%h %cd", "--date=format:%d %b %H:%M"],
                                         cwd=Path(__file__).resolve().parent, capture_output=True, text=True,
                                         timeout=10).stdout.strip() or "unknown"
    except Exception:
        running_version = "unknown"
    started_code = _code_stamp()  # outside the try: always set
    # The result of an update made from the app (reelgen/updater.py), told once on Telegram.
    from .updater import RESULT, last_result
    last_update = last_result(cfg.output_dir)
    if last_update and not last_update.get("notified"):
        alert(("✅ Reel Studio updated and restarted: " if last_update.get("ok") else "⚠️ Reel Studio restarted, update failed: ")
              + str(last_update.get("message", "")) + f" (branch {last_update.get('branch')}, now {running_version})")
        try:
            (cfg.output_dir / RESULT).write_text(json.dumps({**last_update, "notified": True}), encoding="utf-8")
        except OSError:
            pass
    threading.Thread(target=scheduler, args=(jobs,), daemon=True).start()
    from . import poweroff
    threading.Thread(target=poweroff.watch, args=(jobs.busy, alert), daemon=True).start()
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
            # The page is read from disk on every load, the Python code only when the app starts: after a
            # pull the page can show buttons the running app doesn't know yet ('Not Found').
            "restart_needed": _code_stamp() > started_code,
            "renderer": _renderer(),
            "last_update": last_update,
            "poweroff": poweroff.view(),
        }

    @app.post("/api/poweroff")
    def power_when_done(body: PowerBody):
        """Shut the computer down once no job is queued or running (reelgen/poweroff.py); off cancels."""
        return poweroff.arm(body.on)

    # ---------- update and restart (reelgen/updater.py) ----------

    @app.get("/api/update/check")
    def update_check():
        from . import updater
        return updater.check()

    @app.post("/api/update")
    def update_now(body: UpdateBody):
        """Stop running videos (they resume later), hand over to the updater, quit; it pulls and starts the app again."""
        from . import updater

        active = [j for j in jobs.jobs if j["status"] in ("queued", "running")]
        if active and not body.force:
            raise HTTPException(409, {"jobs": [job_label(j) for j in active]})
        for j in active:
            j.update(pause=True, cancel=True)  # stopper.py kills the Claude call / render now; checkpoints stay
            j["log"].append({"t": time.time(), "msg": "Stopped for the app update; resume it after the restart"})
        deadline = time.time() + 25
        while any(j.get("started") and not j.get("finished") for j in active) and time.time() < deadline:
            time.sleep(0.5)
        argv = sys.argv[1:]
        serve_args = argv[1:] if argv[:1] == ["serve"] else []
        updater.start(cfg.output_dir, cfg.port, serve_args)

        from . import anim_engine
        anim_engine.music_test["stop"] = True  # a music test's worker is killed like a video's

        def quit_soon() -> None:
            time.sleep(1.5)  # let this answer reach the page first
            try:
                tunnel.stop()
            finally:
                updater.hard_exit(75)  # start.bat closes its window on 75 instead of waiting for a key

        threading.Thread(target=quit_soon, daemon=True).start()
        return {"ok": True, "stopped": len(active)}

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
                                     "captions": None if body.get("captions") is None else bool(body.get("captions")),
                                     "pace": body.get("pace") if re.fullmatch(r"[+-]\d{1,2}%", str(body.get("pace") or "")) else None})

    # ---- A 15-20 s demo of a re-make before making it (rerender.demo): one at a time, kept per video ----
    demo_state: dict[str, dict] = {}  # "<video id>/<key>" -> {state: waiting/running/failed, line, error}
    demo_lock = threading.Lock()

    def remaking(video_id: str) -> bool:
        return any(j.get("rerender", {}).get("id") == video_id for j in jobs.jobs if j["status"] in ("queued", "running"))

    @app.get("/api/videos/{video_id}/demos")
    def list_demos(video_id: str):
        from . import rerender
        from .longform import LongScript

        folder = video_dir(cfg, video_id)
        original = None
        try:
            script = LongScript.model_validate_json((folder / "script.json").read_text(encoding="utf-8"))
            window = rerender.demo_window(script, json.loads((folder / "props.json").read_text(encoding="utf-8")))
            original = list(window[1:]) if window else None
        except (OSError, ValueError):
            pass
        made = rerender.demos(folder)
        keys = {d["key"] for d in made}
        busy = [{"key": k.split("/", 1)[1], **e} for k, e in list(demo_state.items())
                if k.startswith(video_id + "/") and k.split("/", 1)[1] not in keys]
        return {"original": original, "demos": made, "busy": busy}

    @app.post("/api/videos/{video_id}/demo")
    def make_demo(video_id: str, body: dict):
        """The re-make's settings tried on the story's first 15-20 s (nothing generated, no Claude)."""
        from . import rerender

        folder = video_dir(cfg, video_id)
        report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
        if report.get("format") != "long":
            raise HTTPException(400, "Demos are made for long, medium and Script videos")
        if remaking(video_id):
            raise HTTPException(409, "This video is being re-made; try a demo when it's done")
        pace = body.get("pace") if re.fullmatch(r"[+-]\d{1,2}%", str(body.get("pace") or "")) else None
        voice = str(body.get("voice") or "") or None
        captions = None if body.get("captions") is None else bool(body.get("captions"))
        settings, pace_used, _, _ = rerender._settings(load_settings(Config()), report, voice, pace, captions)
        key = rerender.demo_key(settings.long_voice, pace_used, settings.captions)
        if (folder / rerender.DEMOS / f"{key}.mp4").exists():
            return {"key": key, "state": "done"}
        entry = demo_state.get(f"{video_id}/{key}")
        if entry and entry["state"] in ("waiting", "running"):
            return {"key": key, **entry}
        entry = {"state": "waiting", "line": "Waiting for the demo before it", "error": "", "pace": pace_used}
        demo_state[f"{video_id}/{key}"] = entry

        def work():
            with demo_lock:
                entry.update(state="running", line="Starting")
                try:
                    if remaking(video_id):
                        raise RuntimeError("This video is being re-made; try a demo when it's done")
                    rerender.demo(load_settings(Config()), folder, voice, pace, captions,
                                  progress=lambda m: entry.update(line=str(m)))
                    demo_state.pop(f"{video_id}/{key}", None)
                except Exception as exc:  # noqa: BLE001 - shown on the video page
                    log.warning("Demo of %s failed: %s", video_id, exc)
                    entry.update(state="failed", error=str(exc)[:300])

        threading.Thread(target=work, daemon=True).start()
        return {"key": key, **entry}

    # ---- Re-create only the hook, as a new separate video (reelgen/rehook.py) ----
    hook_state: dict[str, dict] = {}  # "<video id>/<template>" -> {state, line, error, template}

    @app.get("/api/videos/{video_id}/hooks")
    def list_hooks(video_id: str):
        from . import cinehook, rehook

        folder = video_dir(cfg, video_id)
        report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
        hook = {}
        try:
            hook = json.loads((folder / "props.json").read_text(encoding="utf-8")).get("hook") or {}
        except (OSError, ValueError):
            pass
        return {"why_not": rehook.why_not(folder), "yours": report.get("source") == "script",
                "current": hook.get("template") or ("cinematic" if hook.get("cine") else "trailer"),
                "seconds": round(float(hook.get("duration") or 0), 2),
                "templates": [{"key": k, "name": n, "desc": d} for k, (n, d) in cinehook.TEMPLATES.items()],
                "made": rehook.hooks(folder),
                "busy": [{"template": k.split("/", 1)[1], **e} for k, e in list(hook_state.items()) if k.startswith(video_id + "/")],
                "saving": [j["id"] for j in jobs.jobs if j.get("rehook", {}).get("id") == video_id and j["status"] in ("queued", "running")]}

    @app.post("/api/videos/{video_id}/hooks")
    def make_hook_route(video_id: str, body: dict):
        """A new hook for this video in the template asked for, rendered on its own (a preview, ~2-5 min)."""
        from . import cinehook, rehook

        folder = video_dir(cfg, video_id)
        reason = rehook.why_not(folder)
        if reason:
            raise HTTPException(400, reason)
        template = str(body.get("template") or "")
        if template not in cinehook.TEMPLATES:
            raise HTTPException(400, "Pick a hook template")
        k = f"{video_id}/{template}"
        if hook_state.get(k, {}).get("state") in ("waiting", "running"):
            return hook_state[k]
        entry = {"state": "waiting", "line": "Waiting for the edit before it", "error": "", "template": template}
        hook_state[k] = entry

        def work():
            with demo_lock:  # one preview edit at a time (demos and hooks)
                entry.update(state="running", line="Starting")
                try:
                    pace = str(body.get("pace") or "")
                    rehook.make_hook(load_settings(Config()), folder, template, bool(body.get("rewrite", True)),
                                     progress=lambda m: entry.update(line=str(m)),
                                     pace=pace if re.fullmatch(r"[+-]\d{1,2}%", pace) else None)
                    hook_state.pop(k, None)
                except Exception as exc:  # noqa: BLE001 - shown on the video page
                    log.warning("New hook for %s failed: %s", video_id, exc)
                    entry.update(state="failed", error=str(exc)[:300])

        threading.Thread(target=work, daemon=True).start()
        return entry

    @app.post("/api/videos/{video_id}/hooks/{key}/save")
    def save_hook_route(video_id: str, key: str):
        """A new, separate video: this one copied with that hook in place of its own (the original stays as it is)."""
        folder = video_dir(cfg, video_id)
        if not re.fullmatch(r"[a-z]+-[0-9a-f]{6}", key) or not (folder / "hooks" / f"{key}.mp4").exists():
            raise HTTPException(404, "That hook isn't there any more")
        report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
        return jobs.submit(f"New hook: {report.get('title', video_id)}", 1, "rerender", report.get("style"),
                           report.get("format", "long"), rehook={"id": video_id, "key": key})

    sample_state: dict[str, dict] = {}  # template -> {state, line, error}

    @app.get("/api/hook-samples/{template}")
    def hook_sample(template: str):
        """An example of a hook template (rehook.make_sample): made once on first ask (1-3 min), then kept."""
        from . import cinehook, rehook

        if template not in cinehook.TEMPLATES:
            raise HTTPException(404)
        settings = load_settings(Config())
        if rehook.sample_path(settings, template).exists():
            return {"ready": True, "url": f"/api/hook-samples/{template}/video?v={rehook.SAMPLE_VERSION}"}
        entry = sample_state.get(template)
        if entry and entry["state"] in ("waiting", "running"):
            return entry
        entry = {"state": "waiting", "line": "Waiting for the edit before it", "error": ""}
        sample_state[template] = entry

        def work():
            with demo_lock:
                entry.update(state="running", line="Making the example")
                try:
                    rehook.make_sample(load_settings(Config()), template, progress=lambda m: entry.update(line=str(m)))
                    sample_state.pop(template, None)
                except Exception as exc:  # noqa: BLE001
                    log.warning("Hook example %s failed: %s", template, exc)
                    entry.update(state="failed", error=str(exc)[:300])

        threading.Thread(target=work, daemon=True).start()
        return entry

    @app.get("/api/hook-samples/{template}/video")
    def hook_sample_video(template: str):
        from . import cinehook, rehook

        path = rehook.sample_path(load_settings(Config()), template)
        if template not in cinehook.TEMPLATES or not path.exists():
            raise HTTPException(404)
        return FileResponse(path)

    @app.get("/media/{video_id}/hook/{name}")
    def hook_media(video_id: str, name: str):
        path = video_dir(cfg, video_id) / "hooks" / name
        if not re.fullmatch(r"[a-z]+-[0-9a-f]{6}\.mp4", name) or not path.is_file():
            raise HTTPException(404)
        return FileResponse(path)

    @app.get("/media/{video_id}/demo/{name}")
    def demo_media(video_id: str, name: str):
        from .rerender import DEMOS

        path = video_dir(cfg, video_id) / DEMOS / name
        if not re.fullmatch(r"[0-9a-f]{10}\.mp4", name) or not path.is_file():
            raise HTTPException(404)
        return FileResponse(path)

    @app.post("/api/videos/{video_id}/sharpen")
    def sharpen_video_route(video_id: str):
        """An animated video re-edited with its clips and pictures upscaled to full HD (animated.sharpen_video)."""
        from . import anim_engine
        report = json.loads((video_dir(cfg, video_id) / "report.json").read_text(encoding="utf-8"))
        if report.get("source") != "anim":
            raise HTTPException(400, "Only animated videos can be sharpened this way")
        if not anim_engine.installed():
            raise HTTPException(400, "Install the AI engine first (Anim tab).")
        if any(j.get("anim_hd", {}).get("id") == video_id for j in jobs.jobs if j["status"] in ("queued", "running")):
            raise HTTPException(409, "This video is already being sharpened")
        return jobs.submit(f"Full HD: {report.get('title', video_id)}", 1, "rerender", "facts", "anim",
                           anim_hd={"id": video_id})

    @app.post("/api/videos/{video_id}/music")
    def redo_music_route(video_id: str):
        """An animated video whose music was composed (or partly so) gets ACE-Step's tracks: the ones already made
        are kept, the missing ones generated, the soundtrack mixed under the same picture (animated.redo_music)."""
        from . import anim_engine
        from .animated import music_redoable
        report = json.loads((video_dir(cfg, video_id) / "report.json").read_text(encoding="utf-8"))
        if not music_redoable(report):
            raise HTTPException(400, "This video's music is already generated (or your own track)")
        if not anim_engine.installed():
            raise HTTPException(400, "Install the AI engine first (Anim tab).")
        if any(j.get(k, {}).get("id") == video_id for j in jobs.jobs for k in ("anim_music", "anim_hd")
               if j["status"] in ("queued", "running")):
            raise HTTPException(409, "This video is already being worked on")
        return jobs.submit(f"New music: {report.get('title', video_id)}", 1, "rerender", "facts", "anim",
                           anim_music={"id": video_id})

    @app.post("/api/videos/{video_id}/sounds/remove")
    def remove_sound_route(video_id: str, body: SoundRemoveBody):
        """Take one sound effect out of a finished video: its cues dropped, the sound mixed again under the same
        picture (a Short is edited again). reelgen/remix.py."""
        folder = video_dir(cfg, video_id)
        if not (folder / "props.json").exists():
            raise HTTPException(400, "This video was made before its sounds were saved, so they can't be changed")
        if any(j.get(k, {}).get("id") == video_id for j in jobs.jobs for k in ("sound_remove", "anim_music", "anim_hd")
               if j["status"] in ("queued", "running")):
            raise HTTPException(409, "This video is already being worked on: try again when that's done")
        report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
        return jobs.submit(f"Without '{body.name}': {report.get('title', video_id)}", 1, "rerender", "facts",
                           report.get("length") or report.get("format") or "short", sound_remove={"id": video_id, "name": body.name})

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

    @app.post("/api/videos/{video_id}/review")
    def review_video(video_id: str, body: ReviewBody):
        """Accept keeps the video and marks it accepted (what happens next comes later); reject deletes it."""
        folder = video_dir(cfg, video_id)
        if body.decision == "reject":
            shutil.rmtree(folder)
            return {"ok": True, "deleted": True}
        if body.decision != "accept":
            raise HTTPException(400, "decision must be accept or reject")
        path = folder / "report.json"
        report = json.loads(path.read_text(encoding="utf-8"))
        report["review"] = {"decision": "accepted", "at": datetime.now().isoformat(timespec="seconds")}
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        return {"ok": True, "review": report["review"]}

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
        style = body.style if body.style in ("facts", "news", "story", "comedy", "mix") else None
        length = body.length if body.length in ("long", "medium") else "short"
        return jobs.submit((body.topic or "").strip() or None, max(1, min(body.count, MAX_BATCH if length == "short" else MAX_LONG_BATCH)),
                           "manual", style, length, captions=body.captions,
                           story_form=body.story_form if length != "short" else None,
                           memes=body.memes if length != "short" and body.memes in ("off", "some", "lots") else None,
                           hook_template=body.hook_template if length != "short" and body.hook_template in ("auto", "kinetic", "rapid", "stakes", "cinematic") else None)

    @app.get("/api/stick/voices")
    def stick_voices():
        from .stickstory import VOICE_NAMES, VOICE_POOLS

        return {"names": VOICE_NAMES, "pools": VOICE_POOLS}

    @app.post("/api/voice-test")
    def voice_test(body: dict):
        """One line spoken by a voice, as the video would say it (Roman Hinglish in mixed script for the Hindi and
        multilingual voices when `mix`), so voices can be compared by ear before a video is made."""
        import asyncio
        import hashlib

        from . import hinglish
        from .voice import _edge_synthesize

        voice, text = str(body.get("voice") or ""), str(body.get("text") or "").strip()[:2000]  # Sarvam takes 2500
        if not (re.fullmatch(r"[a-z]{2}-[A-Z]{2}-\w+Neural", voice) or re.fullmatch(r"sarvam:[a-z_]{2,40}", voice)) or not text:
            raise HTTPException(400, "Pick a voice and type a line")
        from . import sarvam

        mix = bool(body.get("mix", True))
        from .numbers import speakable

        mixed = mix and hinglish.needs_mixing(voice, [text], least=0)
        # as the video will say it: an English line's numbers in English words (a Multilingual voice reads digits in Hindi)
        spoken = (hinglish.to_speech([text])[0] if mixed else text if hinglish.is_hindi_voice(voice) else speakable(text))
        rate = str(body.get("rate") or "")  # the Script tab's pace; else the long videos' pace setting
        pct = int(re.sub(r"[^\d-]", "", rate if re.fullmatch(r"[+-]\d{1,2}%", rate) else cfg.long_voice_rate) or 0)
        level = str(body.get("delivery") or "normal")
        temperature, factor = sarvam.delivery(level if level in sarvam.DELIVERY else "normal")
        key = hashlib.sha1(f"{voice}|{pct}|{sarvam.pace() if sarvam.is_sarvam(voice) else ''}|{level}|lv1|{spoken}".encode()).hexdigest()[:16]
        path = cfg.output_dir / "voice-tests" / f"{key}.mp3"
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                if sarvam.is_sarvam(voice):  # levelled like the video's takes, so the sample sounds like the video
                    raw = path.with_suffix(".wav")
                    raw.write_bytes(sarvam.say(spoken, sarvam.speaker_of(voice), min(2.0, sarvam.pace() * factor * (1 + pct / 100)),
                                               temperature=temperature))
                    sarvam.level_file(raw, path)
                    raw.unlink(missing_ok=True)
                else:
                    asyncio.run(_edge_synthesize(spoken, voice, f"{pct:+d}%", "+0Hz", path))
            except Exception as exc:  # noqa: BLE001
                path.unlink(missing_ok=True)
                raise HTTPException(502, f"The voice didn't answer: {exc}")
        return {"audio": f"/api/voice-test/{key}.mp3", "spoken": spoken, "mixed": spoken != text}

    @app.get("/api/keys")
    def keys_state():
        """Which voice keys are saved (never the keys themselves)."""
        return {"sarvam": bool(os.environ.get("SARVAM_API_KEY", "").strip())}

    @app.put("/api/keys/sarvam")
    def save_sarvam_key(body: dict):
        """Settings > Voices: the Sarvam API key goes into .env on this computer (and the running app); empty removes it."""
        from .config import PROJECT_ROOT

        value = str(body.get("key") or "").strip()
        if value and not re.fullmatch(r"[A-Za-z0-9_\-.]{8,200}", value):
            raise HTTPException(400, "That doesn't look like a Sarvam API key")
        env = PROJECT_ROOT / ".env"
        lines = env.read_text(encoding="utf-8").splitlines() if env.exists() else []
        lines = [x for x in lines if not re.match(r"\s*SARVAM_API_KEY\s*=", x)]
        if value:
            lines.append(f"SARVAM_API_KEY={value}")
            os.environ["SARVAM_API_KEY"] = value
        else:
            os.environ.pop("SARVAM_API_KEY", None)
        env.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return {"sarvam": bool(value)}

    @app.get("/api/voice-test/{key}.mp3")
    def voice_test_audio(key: str):
        path = cfg.output_dir / "voice-tests" / f"{key}.mp3"
        if not re.fullmatch(r"[0-9a-f]{16}", key) or not path.exists():
            raise HTTPException(404, "no such sample")
        return FileResponse(path, media_type="audio/mpeg")

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
        given = {"idea": body.idea.strip()[:1000], "format": fmt, "minutes": min(8.0, max(2.0, float(body.minutes))), "seconds": body.seconds if body.seconds in (15, 30, 45) else 0,
                 "language": body.language if body.language in ("english", "hindi") else "english",
                 "speed": min(2.0, max(0.8, float(body.speed))), "cast": body.cast.strip() or DEFAULT_CAST,
                 "style": body.style if body.style in ("comedy", "fiction", "facts") else "comedy"}
        return jobs.submit(body.idea.strip()[:80] or None, max(1, min(body.count, 5)), "stick",
                           {"facts": "facts", "fiction": "story"}.get(given["style"], "comedy"),
                           "stick-short" if fmt == "short" else "stick", stick_input=given, captions=False)

    @app.get("/api/toon/options")
    def toon_options():
        from .toon import FORMS, VOICES

        return {"forms": FORMS, "voices": VOICES}

    @app.post("/api/toon")
    def toon(body: ToonRequestBody):
        from .toon import FORMS, VOICES

        given = {"topic": body.topic.strip()[:300], "minutes": min(10.0, max(1.0, float(body.minutes))),
                 "form": body.form if body.form in FORMS else "auto",
                 "voice": body.voice if body.voice in VOICES else "en-US-AndrewMultilingualNeural",
                 "speed": max(0, min(40, int(body.speed))), "captions": bool(body.captions),
                 "watermark": body.watermark.strip()[:40]}
        return jobs.submit(given["topic"][:80] or None, max(1, min(body.count, 5)), "toon", "facts", "toon",
                           toon_input=given, captions=given["captions"])

    @app.get("/api/anim/options")
    def anim_options():
        from .animated import ART_STYLES
        from .toon import VOICES

        return {"styles": {k: v[0] for k, v in ART_STYLES.items()}, "voices": VOICES}

    @app.get("/api/anim/setup")
    def anim_setup():
        from . import anim_engine
        return anim_engine.status()

    @app.post("/api/anim/setup")
    def anim_install():
        from . import anim_engine
        if not anim_engine.install():
            raise HTTPException(409, "Already installing")
        return {"ok": True}

    @app.get("/api/anim/music-test")
    def music_test_state():
        from . import anim_engine
        st = {k: v for k, v in anim_engine.music_test.items() if k != "stop"}
        st["elapsed"] = round(time.time() - st["started"]) if st["running"] else 0
        return {**st, "tests": anim_engine.music_tests(cfg.output_dir)}

    @app.post("/api/anim/music-test")
    def music_test_start(body: MusicTestBody):
        from . import anim_engine
        if not anim_engine.installed():
            raise HTTPException(400, "Install the AI engine first (the panel above).")
        caption = body.caption.strip()[:500]
        if not caption:
            raise HTTPException(400, "Describe the music first.")
        bpm = body.bpm if body.bpm and 40 <= body.bpm <= 220 else None
        if not anim_engine.start_music_test(cfg.output_dir, caption, min(240.0, max(10.0, float(body.seconds))), bpm):
            raise HTTPException(409, "A track is being made already.")
        return {"ok": True}

    @app.delete("/api/anim/music-test")
    def music_test_stop():
        from . import anim_engine
        anim_engine.music_test["stop"] = True
        return {"ok": True}

    @app.get("/api/anim/music-test/{name}/track.wav")
    def music_test_file(name: str):
        from . import anim_engine
        path = cfg.output_dir / anim_engine.TEST_DIR / name / "track.wav"
        if not re.fullmatch(r"\d{8}-\d{6}", name) or not path.exists():
            raise HTTPException(404, "No such track")
        return FileResponse(path, media_type="audio/wav")

    @app.post("/api/anim")
    def anim(body: AnimRequestBody):
        from . import anim_engine
        from .animated import ART_STYLES, QUALITIES
        from .toon import VOICES

        if not anim_engine.installed():
            raise HTTPException(400, "Install the AI engine first (the panel above the button).")
        given = {"topic": body.topic.strip()[:300], "minutes": min(10.0, max(1.0, float(body.minutes))),
                 "style": body.style if body.style in ART_STYLES else "auto",
                 "motion": body.motion if body.motion in ("full", "key", "stills") else "full",
                 "quality": body.quality if body.quality in QUALITIES else "auto", "upscale": bool(body.upscale),
                 "voice": body.voice if body.voice in VOICES else "en-US-AndrewMultilingualNeural",
                 "speed": max(0, min(40, int(body.speed))), "captions": bool(body.captions),
                 "watermark": body.watermark.strip()[:40]}
        return jobs.submit(given["topic"][:80] or None, max(1, min(body.count, 3)), "anim", "facts", "anim",
                           anim_input=given, captions=given["captions"])

    @app.post("/api/story")
    def story(body: StoryBody):
        from . import anim_engine
        from .animated import ART_STYLES, QUALITIES
        from .storyshorts import KINDS, LANGUAGES, MAX_PARTS, VISUALS, split_parts

        visuals = body.visuals if body.visuals in VISUALS else "anim"
        if visuals in ("anim", "key", "pictures") and not anim_engine.installed():
            raise HTTPException(400, "AI pictures need the AI engine: install it on the Anim tab, or pick stock footage.")
        if visuals == "footage" and not load_settings(Config()).pexels_api_key:
            raise HTTPException(400, "Stock footage needs a Pexels key (Settings), or pick AI pictures.")
        voice = body.voice.strip()
        if voice and not re.fullmatch(r"[a-z]{2}-[A-Z]{2}-[A-Za-z]+Neural|sarvam:[a-z_]{2,40}", voice):
            raise HTTPException(400, "Unknown voice")
        if voice.startswith("sarvam:") and not os.environ.get("SARVAM_API_KEY"):
            raise HTTPException(400, "Sarvam voices need your Sarvam AI key (Settings > Long videos).")
        language = body.language if body.language in LANGUAGES else "english"
        seconds = max(15, min(180, int(body.seconds)))  # YouTube Shorts run up to 3 minutes
        given = {"source": "script" if body.source == "script" else "ai", "topic": body.topic.strip()[:300],
                 "kind": body.kind if body.kind in KINDS else "story", "script": body.script.strip()[:20000],
                 "title": body.title.strip()[:100], "seconds": seconds, "language": language,
                 "split": body.split if body.split in ("one", "length") else "auto",
                 "screen_text": "voice" if body.screen_text == "voice" else "english", "visuals": visuals,
                 "style": body.style if body.style in ART_STYLES else "auto",
                 "quality": body.quality if body.quality in QUALITIES else "auto", "upscale": bool(body.upscale),
                 "voice": voice, "speed": max(0, min(40, int(body.speed))), "captions": bool(body.captions),
                 "watermark": body.watermark.strip()[:40],
                 "memes": body.memes if body.memes in ("off", "some", "lots") else load_settings(Config()).memes}
        if given["source"] == "script":
            parts = split_parts(given["script"], language, seconds, given["split"])
            if not parts:
                raise HTTPException(400, "Paste your story first.")
            if len(parts) > 12:
                raise HTTPException(400, f"That story makes {len(parts)} Shorts; keep it to 12 or fewer (or split it).")
            given["parts"] = len(parts)
        else:
            given["parts"] = max(1, min(MAX_PARTS, int(body.parts)))
        title = given["title"] or given["topic"][:80] or None
        return jobs.submit(title, given["parts"], "story", given["kind"], "storyshorts", story_input=given,
                           captions=given["captions"])

    @app.get("/api/story/estimate")
    def story_estimate(language: str = "english", seconds: int = 30, text: str = "", split: str = "auto"):
        """How the user's story would be cut: parts and their lengths (the Story tab shows it while typing)."""
        from .storyshorts import WPS, split_parts

        parts = split_parts(text[:20000], language, max(15, min(180, seconds)), split if split in ("one", "length") else "auto")
        return {"parts": [round(sum(len(x.split()) for x in p) / WPS.get(language, 2.6) + 1) for p in parts]}

    @app.post("/api/script-video")
    def script_video(body: ScriptVideoRequest):
        from .scriptvideo import parse_script

        title, script = body.title.strip(), body.script.strip()
        if not title or not script:
            raise HTTPException(400, "The title and the script are needed.")
        if not parse_script(script)[0]:
            raise HTTPException(400, "The script has no lines to read.")
        given = {"title": title, "description": body.description.strip(), "hook": body.hook.strip(), "script": script,
                 "screen_text": "script" if body.screen_text == "script" else "english"}
        return jobs.submit(title, 1, "script", None, "script", script_input=given, voice=body.voice or None,
                           captions=body.captions, memes=body.memes if body.memes in ("off", "some", "lots") else None,
                           hook_template=body.hook_template if body.hook_template in ("auto", "kinetic", "rapid", "stakes", "cinematic") else None,
                           voice_rate=body.voice_rate if re.fullmatch(r"[+-]\d{1,2}%", body.voice_rate or "") else None)

    # ---------- Shoot: your script filmed by you (reelgen/shoot.py) ----------

    def _shoot(pid: str) -> dict:
        from . import shoot

        try:
            return shoot.load(cfg, pid)
        except (FileNotFoundError, ValueError):
            raise HTTPException(404, "Shoot not found")

    @app.get("/api/shoot")
    def shoot_list():
        from . import shoot

        return shoot.projects(cfg)

    @app.post("/api/shoot")
    def shoot_new(body: ShootBody):
        from . import shoot

        try:
            proj = shoot.new_project(cfg, body.model_dump())
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        shoot.plan_in_background(load_settings(Config()), proj["id"])
        return shoot.load(cfg, proj["id"])

    @app.get("/api/shoot/{pid}")
    def shoot_get(pid: str):
        from . import shoot

        return shoot.recheck_old(cfg, _shoot(pid))  # takes checked an older way get checked again

    @app.post("/api/shoot/{pid}/plan")
    def shoot_plan(pid: str):
        from . import shoot

        if _shoot(pid)["plan"]["status"] == "running":
            raise HTTPException(409, "Claude is planning it already")
        shoot.update(cfg, pid, lambda p: p["plan"].update(status="running", error=""))
        shoot.plan_in_background(load_settings(Config()), pid)
        return shoot.load(cfg, pid)

    @app.post("/api/shoot/{pid}/lines/{k}/camera")
    def shoot_camera(pid: str, k: int, on: bool = True):
        """You decide a line yourself: on camera or B-roll."""
        from . import shoot

        proj = _shoot(pid)
        if not 0 <= k < len(proj["lines"]):
            raise HTTPException(404, "No such line")
        return shoot.update(cfg, pid, lambda p: p["lines"][k].update(camera=bool(on)))

    @app.post("/api/shoot/{pid}/voice")
    def shoot_voice(pid: str, body: ShootVoiceBody):
        """Your voice in this shoot: cleaned, and missing words rebuilt in it (voice engine)."""
        from . import shoot

        proj = _shoot(pid)
        given = body.model_dump(exclude_none=True)
        voice = shoot.voice_options(proj)
        voice.update({k: v for k, v in given.items() if k != "choices"})
        voice["choices"] = {**voice["choices"], **given.get("choices", {})}
        return shoot.update(cfg, pid, lambda p: p.update(voice=voice))

    @app.get("/api/voice-engine")
    def voice_engine_status():
        from . import voice_engine
        return voice_engine.status()

    @app.post("/api/voice-engine")
    def voice_engine_install():
        from . import voice_engine
        if not voice_engine.install():
            raise HTTPException(409, "Already installing")
        return {"ok": True}

    @app.delete("/api/shoot/{pid}")
    def shoot_delete(pid: str):
        from . import shoot

        _shoot(pid)
        shoot.delete(cfg, pid)
        return {"ok": True}

    @app.post("/api/shoot/{pid}/shots/{n}/take")
    async def shoot_take(pid: str, n: int, request: Request, name: str = "take.mov"):
        """The best take of a shot, as the raw request body (streamed to disk: phone videos are big)."""
        from . import shoot

        _shoot(pid)
        try:
            target = shoot.take_target(cfg, pid, n, name)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        size = 0
        with open(target, "wb") as f:
            async for chunk in request.stream():
                f.write(chunk)
                size += len(chunk)
        if size < 10_000:
            target.unlink(missing_ok=True)
            raise HTTPException(400, "The file is empty or didn't finish uploading")
        shoot.process_in_background(load_settings(Config()), pid, n, target)
        return {"ok": True, "size": size}

    @app.delete("/api/shoot/{pid}/shots/{n}/take")
    def shoot_take_delete(pid: str, n: int):
        from . import shoot

        _shoot(pid)
        shoot.remove_take(cfg, pid, n)
        return shoot.load(cfg, pid)

    @app.get("/api/shoot/{pid}/shots/{n}/take.mp4")
    def shoot_take_file(pid: str, n: int):
        from . import shoot

        _shoot(pid)
        path = shoot.take_paths(cfg, pid, n)["proxy"]
        if not path.is_file():
            raise HTTPException(404, "Not ready yet")
        return FileResponse(path, media_type="video/mp4")

    @app.post("/api/shoot/{pid}/make")
    def shoot_make(pid: str, body: ShootMakeBody):
        from . import shoot

        proj = _shoot(pid)
        missing = shoot.missing_takes(proj)
        if missing:
            raise HTTPException(400, f"Upload a take of shot{'s' if len(missing) > 1 else ''} {', '.join(map(str, missing))} first.")
        if proj["plan"]["status"] == "running":
            raise HTTPException(409, "Claude is still planning which lines show you: a minute more")
        job = jobs.submit(proj["title"], 1, "shoot", None, "shoot", shoot_input={"id": pid}, captions=body.captions)
        shoot.update(cfg, pid, lambda p: p.update(video={"status": "queued", "job": job["id"]}))
        return job

    @app.get("/api/jobs")
    def list_jobs():
        now = time.time()  # lets the page run its timers on this computer's clock
        return [{**j, "now": now} for j in jobs.jobs]

    @app.get("/api/jobs/{job_id}/videos/{n}/script")
    def job_script(job_id: str, n: int):
        """The script a running (or finished) video is using right now, as readable sections. Only reads
        files the pipeline already wrote; the job keeps going."""
        job = next((j for j in jobs.jobs if j["id"] == job_id), None)
        if job is None:
            raise HTTPException(404, "job not found")
        for folder in _video_folders(cfg, job, n):
            data = _latest_script(folder)
            if data is not None:
                return script_view(data)
        raise HTTPException(404, "No script yet: Claude is still writing it.")

    def busy_folders() -> set[str]:
        return {f for j in jobs.jobs if j["status"] in ("queued", "running") for f in j.get("folders", []) + j.get("resume", [])}

    @app.delete("/api/jobs/{job_id}")
    def remove_job(job_id: str, discard: bool = False):
        """Take a job off the list. A queued or running job is stopped at once: the Claude call or
        render it is on is killed (reelgen/stopper.py). `discard` also deletes the files of videos
        it left unfinished (they can't be resumed after that)."""
        with jobs.lock:
            job = next((j for j in jobs.jobs if j["id"] == job_id), None)
            if job is None:
                raise HTTPException(404, "No such job")
            running = job["status"] in ("queued", "running")
            if running:
                job.update(cancel=True, pause=True)
            jobs.jobs.remove(job)
        if running:
            job["log"].append({"t": time.time(), "msg": "Stopped and removed"})
            if job.get("started"):  # its threads take a few seconds to end; delete only after that
                threading.Thread(target=_discard_when_done, args=(job, discard), daemon=True).start()
                return {"ok": True}
        if discard:
            _discard(job)
        return {"ok": True}

    def _discard_when_done(job: dict, discard: bool) -> None:
        for _ in range(120):
            if job.get("finished"):
                break
            time.sleep(1)
        if discard:
            _discard(job)

    def _discard(job: dict) -> None:
        from .animated import CHECKPOINT as ANIM_CHECKPOINT
        from .pipeline import CHECKPOINT
        from .storyshorts import CHECKPOINT as STORY_CHECKPOINT
        from .toon import CHECKPOINT as TOON_CHECKPOINT
        busy = busy_folders()
        for f in set(job.get("folders", []) + job.get("resume", [])) - busy:
            path = (cfg.output_dir / f).resolve()
            if path.parent == cfg.output_dir.resolve() and any((path / c).exists() for c in (CHECKPOINT, ANIM_CHECKPOINT, TOON_CHECKPOINT, STORY_CHECKPOINT)):
                shutil.rmtree(path, ignore_errors=True)

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
        from .animated import CHECKPOINT as ANIM_CHECKPOINT
        from .storyshorts import CHECKPOINT as STORY_CHECKPOINT
        from .toon import CHECKPOINT as TOON_CHECKPOINT
        path = (cfg.output_dir / folder_id).resolve()
        if path.parent != cfg.output_dir.resolve() or not any((path / c).exists() for c in (CHECKPOINT, TOON_CHECKPOINT, ANIM_CHECKPOINT, STORY_CHECKPOINT)):
            raise HTTPException(404, "Not an unfinished video")
        if folder_id in busy_folders():
            raise HTTPException(409, "It's being made right now")
        shutil.rmtree(path, ignore_errors=True)
        return {"ok": True}

    @app.get("/api/unfinished")
    def list_unfinished():
        """Videos that stopped part-way (failed, or the app was closed) and can be resumed."""
        from .pipeline import unfinished

        from .animated import anim_unfinished
        from .storyshorts import story_unfinished
        from .toon import toon_unfinished

        busy = busy_folders()
        return [u for u in unfinished(cfg) + toon_unfinished(cfg) + anim_unfinished(cfg) + story_unfinished(cfg) if u["id"] not in busy]

    @app.post("/api/resume")
    def resume(body: dict):
        from .pipeline import unfinished
        from .toon import CHECKPOINT as TOON_CHECKPOINT, unfinished_toons

        from .animated import CHECKPOINT as ANIM_CHECKPOINT, QUALITIES, forget_music, music_failed, unfinished_anims

        from .storyshorts import CHECKPOINT as STORY_CHECKPOINT, unfinished_stories

        stories = [f for f in body.get("folders", []) if f in unfinished_stories(cfg) and f not in busy_folders()]
        if stories:  # Story Shorts resume through their own pipeline, one series at a time
            saved = json.loads((cfg.output_dir / stories[0] / STORY_CHECKPOINT).read_text(encoding="utf-8"))
            given = saved.get("request") or {}
            return jobs.submit((saved.get("series") or {}).get("title") or given.get("topic") or None,
                               len((saved.get("series") or {}).get("parts") or []) or given.get("parts", 1), "resume",
                               given.get("kind", "story"), "storyshorts", story_input=given, story_resume=stories[:1],
                               captions=given.get("captions"))
        anims = [f for f in body.get("folders", []) if f in unfinished_anims(cfg) and f not in busy_folders()]
        if anims:  # Animated videos resume through their own pipeline too
            if body.get("music") == "redo":  # "Resume with AI music": the failed music step runs again
                for f in anims:
                    if music_failed(json.loads((cfg.output_dir / f / ANIM_CHECKPOINT).read_text(encoding="utf-8"))):
                        forget_music(cfg.output_dir / f)
            saved = json.loads((cfg.output_dir / anims[0] / ANIM_CHECKPOINT).read_text(encoding="utf-8"))
            given = saved.get("request") or {}
            if body.get("quality") in QUALITIES:  # "Resume with fast clips": the clips still to make use it
                given = {**given, "quality": body["quality"]}
            if body.get("motion") in ("key", "stills"):  # "Resume, key shots only": fewer clips from here on
                given = {**given, "motion": body["motion"]}
            return jobs.submit((saved.get("script") or {}).get("title") or given.get("topic") or None, len(anims), "resume",
                               "facts", "anim", anim_input=given, anim_resume=anims, captions=given.get("captions"))
        toons = [f for f in body.get("folders", []) if f in unfinished_toons(cfg) and f not in busy_folders()]
        if toons:  # Toon videos resume through their own pipeline, never the Shorts/long one
            saved = json.loads((cfg.output_dir / toons[0] / TOON_CHECKPOINT).read_text(encoding="utf-8"))
            given = saved.get("request") or {}
            return jobs.submit((saved.get("script") or {}).get("title") or given.get("topic") or None, len(toons), "resume",
                               "facts", "toon", toon_input=given, toon_resume=toons, captions=given.get("captions"))
        available = {u["id"] for u in unfinished(cfg)} - busy_folders()
        folders = [f for f in body.get("folders", []) if f in available]
        if not folders:
            raise HTTPException(400, "Nothing saved to resume for these videos; generate them again.")
        # The card keeps the video's own title, style and length (it showed "Trending topic · Facts" with
        # the Shorts stages for a resumed Script Video or News medium video).
        first = next(u for u in unfinished(cfg) if u["id"] == folders[0])
        title = first.get("title") or (first.get("topic") if first.get("topic") != "Trending topic" else None)
        return jobs.submit(title, len(folders), "resume", first.get("style"), first.get("length", "short"),
                           resume=folders)

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
        if job.get("anim_input"):  # an Animated job resumes its own saved videos (anim-checkpoint.json)
            from .animated import unfinished_anims
            saved = [f for f in dict.fromkeys(job.get("folders", [])) if f in unfinished_anims(cfg) and f not in busy_folders()]
            if not saved:
                raise HTTPException(400, "Nothing saved to resume for these videos; generate them again.")
            return jobs.submit(job["topic"], len(saved), "resume", "facts", "anim", anim_input=job["anim_input"],
                               anim_resume=saved, captions=job.get("captions"))
        if job.get("story_input"):  # a Story Shorts job resumes its own saved series (story-checkpoint.json)
            from .storyshorts import unfinished_stories
            saved = [f for f in dict.fromkeys(job.get("folders", [])) if f in unfinished_stories(cfg) and f not in busy_folders()]
            if not saved:
                raise HTTPException(400, "Nothing saved to resume for this story; make it again.")
            return jobs.submit(job["topic"], job["count"], "resume", job.get("style"), "storyshorts",
                               story_input=job["story_input"], story_resume=saved[:1], captions=job.get("captions"))
        if job.get("toon_input"):  # a Toon job resumes its own saved videos (toon-checkpoint.json)
            from .toon import unfinished_toons
            saved = [f for f in dict.fromkeys(job.get("folders", [])) if f in unfinished_toons(cfg) and f not in busy_folders()]
            if not saved:
                raise HTTPException(400, "Nothing saved to resume for these videos; generate them again.")
            return jobs.submit(job["topic"], len(saved), "resume", "facts", "toon", toon_input=job["toon_input"],
                               toon_resume=saved, captions=job.get("captions"))
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

    @app.put("/api/library/{kind}/{name}/ban")
    def ban_library_file(kind: str, name: str, on: bool = True):
        """Never use this file again (or allow it back)."""
        from . import media

        try:
            media.set_banned(cfg, kind, name, on)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        return {"ok": True, "banned": media.banned(cfg, kind, name)}

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

    from . import updater

    cfg = load_settings(cfg)
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    wait = float(os.environ.pop("REEL_WAIT_PORT", "0") or 0)  # set by the updater: the old app may still be closing
    if not updater.port_bindable(cfg.port, wait):
        owner = updater.port_owner(cfg.port)
        print(f"\n  Port {cfg.port} is already in use" + (f" by {owner}" if owner else "") + ", so Reel Studio can't start.\n"
              "  Another Reel Studio may still be open: close its window"
              + (f", or end PID {owner.split('PID ')[-1].rstrip(')')} in Task Manager (Details tab)" if "PID" in owner else "")
              + ", then start again.\n")
        sys.exit(1)
    print_banner(cfg)
    tunnel.start(cfg)
    uvicorn.run(create_app(cfg), host="0.0.0.0", port=cfg.port, log_level="warning")
