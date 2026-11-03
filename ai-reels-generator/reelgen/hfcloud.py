"""Hugging Face cloud engine for animated videos (the Anim tab's 'Cloud' engine).

The user tested it by hand and liked it: Qwen-Image 2.1 draws the pictures (a character picture as reference keeps
the same character in every new place) and LTX-2.5 animates each picture into a clip (1472x832, up to 5 s, 24 fps).
Both run on Hugging Face's ZeroGPU Spaces with the user's token, so the time comes out of the account's daily GPU
quota (40 min a day with PRO). Spaces are called through `gradio_client`; the user can point the app at their own
private duplicates (REEL_HF_IMAGE_SPACE / REEL_HF_VIDEO_SPACE).

Every finished picture and clip is written next to a `.ok` file, exactly like the local worker, so a video that runs
out of daily minutes stops with `CloudOut` and Resume (tomorrow, or after buying minutes) continues from the next item.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)
Progress = Callable[[str], None]

IMAGE_SPACE = "Qwen/Qwen-Image-2.1"
VIDEO_SPACE = "Lightricks/LTX-2.5"
CLIP_W, CLIP_H = 1472, 832  # the size the user's good test clip came out at (16:9, multiples of 64)
PIC_W, PIC_H = 1344, 768
LONGEST = 5.0  # the Space's limit for one clip
TRIES = 3


class CloudOut(RuntimeError):
    """The account's GPU minutes for today are used up (or the token is missing/refused): Resume later."""


def token() -> str:
    return (os.environ.get("HF_TOKEN") or "").strip()


def ready() -> bool:
    return bool(token())


def spaces() -> tuple[str, str]:
    return ((os.environ.get("REEL_HF_IMAGE_SPACE") or IMAGE_SPACE).strip(),
            (os.environ.get("REEL_HF_VIDEO_SPACE") or VIDEO_SPACE).strip())


def _client(space: str):
    try:
        from gradio_client import Client
    except ImportError as exc:  # pragma: no cover - installed from requirements.txt
        raise RuntimeError("gradio_client isn't installed: run start.bat / start.sh once to install it") from exc
    if not token():
        raise CloudOut("No Hugging Face token: paste it in the Anim tab (Hugging Face box)")
    return Client(space, token=token(), verbose=False)


def _quota_error(text: str) -> bool:
    t = text.lower()
    return any(w in t for w in ("quota", "runs limit", "exceeded your", "gpu limit", "credits", "401", "unauthorized"))


def _call(make, label: str, stop: Callable[[], None]) -> object:
    """Run one Space job, checking Pause/Stop every 2 s; retried on passing errors, CloudOut on quota/token."""
    last = ""
    for attempt in range(TRIES):
        job = make()
        try:
            while not job.done():
                try:
                    stop()
                except BaseException:
                    job.cancel()
                    raise
                time.sleep(2)
            return job.result()
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
            if _quota_error(last):
                raise CloudOut(f"Hugging Face says: {last[:200]}. Your daily GPU minutes are probably used up: "
                               "press Resume tomorrow (finished pictures and clips are kept), or add credits.") from exc
            log.warning("%s failed (try %d): %s", label, attempt + 1, last[:300])
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"{label} failed 3 times: {last[:300]}")


def _done(p: Path) -> bool:
    return p.exists() and Path(str(p) + ".ok").exists()


def _ok(p: Path) -> None:
    Path(str(p) + ".ok").write_text("ok", encoding="utf-8")


def _to_jpg(src: str, out: Path, w: int, h: int) -> None:
    from .video import FFMPEG
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", src, "-vf",
                    f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}", "-q:v", "2", str(out)],
                   check=True, capture_output=True)


def draw(job: dict, work: Path, progress: Progress, stop: Callable[[], None]) -> None:
    """The local `keyframes` job (animated.keyframe_job) drawn by Qwen-Image: character sheets first (text only),
    then every shot with its main character's sheet as reference (and the shot before it for `same_place`)."""
    from gradio_client import handle_file

    space = spaces()[0]
    items = list(job.get("characters", [])) + list(job.get("shots", []))
    todo = [it for it in items if not _done(Path(it["out"]))]
    if not todo:
        return
    client = _client(space)
    t0 = time.time()
    for n, it in enumerate(todo, 1):
        out = Path(it["out"])
        refs, prompt = [], it["prompt"]
        if it.get("ref") and Path(it["ref"]).exists():
            refs.append(it["ref"])
            prompt = f"Use this character exactly as drawn (same head, eyes, clothes, colours). {prompt}"
        if it.get("init") and Path(it["init"]).exists():
            refs.append(it["init"])
            prompt += (" Keep the same place, light and colours as in the last picture, seen from a new angle."
                       if len(refs) > 1 else " Same place as in this picture, a new moment and angle.")
        if refs:
            prompt += " Completely new picture: a new pose, natural lighting on the character, a soft shadow."
        gallery = [{"image": handle_file(r), "caption": None} for r in refs]
        seed = int(it.get("seed", 7)) % 2147483647
        progress(f"☁️ Drawing picture {n} of {len(todo)} ({it['id']}) on Hugging Face")

        def make():
            # The Space needs its two steps in one session: prepare (stores the prompt and pictures), then generate.
            client.predict(gallery, prompt, False, True, "quality", seed, False, api_name="/prepare_request")
            return client.submit(prompt, False, True, "./generation_logs_paper_case", seed, PIC_H, PIC_W, "",
                                 api_name="/generate_request")

        path = _call(make, f"Picture {it['id']}", stop)
        _to_jpg(str(path), out, PIC_W, PIC_H)
        _ok(out)
    progress(f"☁️ {len(todo)} pictures drawn in {(time.time() - t0) / 60:.1f} min")


def animate(job: dict, work: Path, progress: Progress, stop: Callable[[], None]) -> None:
    """The local `clips` job (animated.clip_jobs) animated by LTX-2.5: one clip per picture, its sound removed
    (the edit has its own), plus the `.last.jpg` the editor holds when the line outlasts the clip."""
    from gradio_client import handle_file
    from .video import FFMPEG

    space = spaces()[1]
    todo = [s for s in job.get("shots", []) if not _done(Path(s["out"]))]
    if not todo:
        return
    client = _client(space)
    t0 = time.time()
    for n, s in enumerate(todo, 1):
        out = Path(s["out"])
        out.parent.mkdir(parents=True, exist_ok=True)
        seconds = max(1.0, min(LONGEST, round((int(s.get("frames", 49)) - 1) / 24 * 2) / 2))
        prompt = (f"{s['prompt']} Consistent character, stable face, glowing eyes stay the same, no morphing, "
                  "smooth cinematic 3D animation.")
        progress(f"☁️ Animating shot {n} of {len(todo)} ({s['id']}, {seconds:g} s) on Hugging Face")
        seed = int(s.get("seed", 42)) % 2147483647

        def make():
            return client.submit(prompt, handle_file(s["image"]), CLIP_H, CLIP_W, seconds, seed, "conv", False, False,
                                 True, api_name="/run")

        result = _call(make, f"Clip {s['id']}", stop)
        video = result[0] if isinstance(result, (list, tuple)) else result
        if isinstance(video, dict):
            video = video.get("video") or video.get("path")
        tmp = out.with_suffix(".tmp.mp4")
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(video), "-an", "-c:v", "copy", str(tmp)],
                       check=True, capture_output=True)
        shutil.move(str(tmp), out)
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-sseof", "-0.1", "-i", str(out), "-frames:v", "1",
                        "-q:v", "2", str(out.with_suffix(".last.jpg"))], check=False, capture_output=True)
        _ok(out)
    progress(f"☁️ {len(todo)} clips animated in {(time.time() - t0) / 60:.1f} min")
