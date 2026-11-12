"""The Journey's motion: one clip per stage, each going from where the last one ended to the stage's picture.

A clip starts on the last frame of the clip before it (so the joins are seamless, like the reference's chained
clips) and ends on its stage's picture (first-and-last-frame video): the change between the two is the time-lapse.
The opening clip, and the first after the opening cut, start on their own picture and only move forward.

Engines, all free: Hugging Face's Wan 2.2 first-and-last-frame Space while the account's daily ZeroGPU minutes last
(the best), then this computer's AI engine (LTX-Video 2B, with an end-frame condition), and if a clip still can't
be made, a slow dissolve between the two pictures (`morph`, ffmpeg only) so the video is never left with a hole.
Each clip is then timed to its stage (slowed with motion interpolation, never with repeated frames) and the stages
are joined into story.mp4 (16:9, 1920x1080, 30 fps) and a blurred tall copy for behind it (story-bg.mp4)."""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

from .. import anim_engine, hfcloud
from ..video import FFMPEG, media_seconds
from . import frames
from .story import Journey

log = logging.getLogger(__name__)
FPS = 30
OUT_W, OUT_H = 1920, 1080
LOCAL_LONGEST = 4.0  # seconds a clip may be on this computer's engine (LTX's time grows with the frames)


def clip_path(work: Path, k: int) -> Path:
    return work / "clips" / f"c{k:02d}.mp4"


def last_frame(work: Path, k: int) -> Path:
    return clip_path(work, k).with_suffix(".last.jpg")


def _ok(p: Path) -> bool:
    return p.exists() and Path(str(p) + ".ok").exists()


# The rain itself is made by the video model, falling in the picture (the editor draws none): it is told so.
WEATHER_MOTION = {
    "storm": "Heavy rain pours down in sheets and splashes on the ground, dark clouds roll, the wind gusts. ",
    "rain": "Steady rain falls and splashes on the ground. ",
}


def plan(j: Journey, work: Path, seed: int) -> list[dict]:
    clips = []
    for k, s in enumerate(j.stages):
        fresh = k == 0 or s.cut
        how = ("Time-lapse: " if s.timelapse else "Real-time: ") + s.motion.strip()
        clips.append({
            "id": f"c{k:02d}", "stage": k, "out": str(clip_path(work, k)), "seed": seed + 300 + k,
            "image": str(frames.path(work, k) if fresh else last_frame(work, k - 1)),
            "end": None if fresh else str(frames.path(work, k)),
            "seconds": round(s.seconds, 2), "timelapse": s.timelapse,
            "prompt": (f"{how} {s.what.strip()} {WEATHER_MOTION.get(s.light, '')}The camera stays still, the same "
                       f"place: {j.place.strip()} Photorealistic, natural colours, smooth natural motion, no text."),
        })
    return clips


def _local(clips: list[dict], work: Path, progress) -> None:
    """This computer's engine: T5 reads the prompts, LTX makes the clips (one worker run for all, in order)."""
    from ..animated import CLIP_SIZES

    vram = float(anim_engine.probe().get("vram_gb") or 0)
    W, H, _ = CLIP_SIZES["fast" if vram < 6 else "standard"]
    shots = []
    for c in clips:
        frames_n = min(int(LOCAL_LONGEST * 24), int(round(c["seconds"] * 24)))
        frames_n = max(25, (frames_n - 1) // 8 * 8 + 1)
        shots.append({"id": c["id"], "image": c["image"], "end": c["end"], "out": c["out"],
                      "emb": str(Path(c["out"]).with_suffix(".pt")), "frames": frames_n, "seed": c["seed"],
                      "prompt": c["prompt"]})
    progress(f"Animating {len(shots)} stage(s) on this computer ({W}x{H}; slow on a small graphics card)")
    anim_engine.run_stage("embed", {"shots": shots}, work, progress, "Reading the motion prompts")
    anim_engine.run_stage("clips", {"shots": shots, "width": W, "height": H, "fps": 24}, work, progress,
                          "Animating the stages")


def morph(a: Path, b: Path, seconds: float, out: Path) -> None:
    """The last resort for one clip: picture a slowly dissolving into picture b under a slow push-in."""
    out.parent.mkdir(parents=True, exist_ok=True)
    t = max(1.0, seconds)
    vf = (f"[0:v]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,crop={OUT_W}:{OUT_H},setsar=1[a];"
          f"[1:v]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,crop={OUT_W}:{OUT_H},setsar=1[b];"
          f"[a][b]xfade=transition=fade:duration={t - 0.2:.2f}:offset=0.1,"
          f"zoompan=z='1+0.04*on/{int(t * FPS)}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={OUT_W}x{OUT_H}:fps={FPS}")
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-loop", "1", "-framerate", str(FPS), "-t", f"{t:.2f}", "-i", str(a),
                    "-loop", "1", "-framerate", str(FPS), "-t", f"{t:.2f}", "-i", str(b), "-filter_complex", vf,
                    "-t", f"{t:.2f}", "-c:v", "libx264", "-crf", "17", "-pix_fmt", "yuv420p", str(out)],
                   check=True, capture_output=True)
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-sseof", "-0.1", "-i", str(out), "-frames:v", "1", "-q:v", "2",
                    str(out.with_suffix(".last.jpg"))], check=False, capture_output=True)
    Path(str(out) + ".ok").write_text("morph", encoding="utf-8")


def make(j: Journey, work: Path, seed: int, engine: str, progress, stop) -> dict:
    """Make every clip that isn't made. Returns {clip id: engine} for the report."""
    clips = plan(j, work, seed)
    made_by: dict = json.loads((work / "clips" / "engines.json").read_text()) if (work / "clips" / "engines.json").exists() else {}

    def note(ids, how):
        for i in ids:
            made_by.setdefault(i, how)
        (work / "clips").mkdir(exist_ok=True)
        (work / "clips" / "engines.json").write_text(json.dumps(made_by, indent=1), encoding="utf-8")

    todo = [c for c in clips if not _ok(Path(c["out"]))]
    if todo and engine in ("cloud", "auto") and hfcloud.ready():
        try:
            hfcloud.between({"clips": todo}, work, progress, stop)
        except hfcloud.CloudOut as exc:
            if engine == "cloud" or not anim_engine.installed():
                note([c["id"] for c in todo if _ok(Path(c["out"]))], "cloud")
                raise
            progress(f"Hugging Face is out of free minutes ({str(exc)[:80]}); animating the rest on this computer")
        except Exception as exc:  # noqa: BLE001 - the Space is down or changed: this computer takes over
            if exc.__class__.__name__ in ("Paused", "Stopped"):
                raise
            log.warning("Cloud clips failed: %s", exc)
            progress(f"Hugging Face couldn't animate ({str(exc)[:100]}); using this computer")
        note([c["id"] for c in todo if _ok(Path(c["out"]))], "cloud")
    todo = [c for c in clips if not _ok(Path(c["out"]))]
    if todo and anim_engine.installed() and engine != "cloud":
        try:
            _local(todo, work, progress)
        except Exception as exc:  # noqa: BLE001
            if exc.__class__.__name__ in ("Paused", "Stopped"):
                raise
            log.warning("Local clips failed: %s", exc)
            progress(f"This computer couldn't animate every stage ({str(exc)[:100]}); dissolving the rest")
        note([c["id"] for c in todo if _ok(Path(c["out"]))], "local")
    for c in clips:  # whatever is still missing: a dissolve, so the video has no hole
        if not _ok(Path(c["out"])):
            a = Path(c["image"]) if Path(c["image"]).exists() else frames.path(work, max(0, c["stage"] - 1))
            morph(a, Path(c["end"] or frames.path(work, c["stage"])), c["seconds"], Path(c["out"]))
            note([c["id"]], "dissolve")
    return made_by


def fit(src: Path, seconds: float, out: Path, hd: bool = True) -> None:
    """The clip at exactly `seconds` and 30 fps: slowed with motion-compensated interpolation (a time-lapse moving a
    little slower looks natural; repeated frames judder), sped up by dropping frames. `hd`: scaled to 1920x1080 here
    (lanczos); else kept at its own size for the AI upscaler (interpolating small frames is also much faster)."""
    dur = media_seconds(src) or seconds
    factor = seconds / dur
    size = (f",scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase:flags=lanczos,crop={OUT_W}:{OUT_H},setsar=1,"
            "unsharp=5:5:0.35") if hd else ",scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1"
    if factor > 1.04:
        vf = f"setpts={factor:.4f}*PTS,minterpolate=fps={FPS}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1{size}"
    else:
        vf = f"setpts={factor:.4f}*PTS,fps={FPS}{size}"
    out.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(src), "-vf", vf, "-t", f"{seconds:.3f}",
                           "-an", "-c:v", "libx264", "-crf", "15", "-preset", "medium", "-pix_fmt", "yuv420p", str(out)],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Timing clip {src.name} failed: {proc.stderr[-300:]}")


def _fresh(out: Path, src: Path, seconds: float) -> bool:
    """A timed clip made from this very clip at this length (a clip made again, or a new length, times it again)."""
    tag = Path(str(out) + ".ok")
    return out.exists() and tag.exists() and tag.read_text(encoding="utf-8").strip() == f"{src.stat().st_mtime:.0f}|{seconds:.3f}"


def join(j: Journey, work: Path, made_by: dict, progress) -> tuple[Path, Path, list[float]]:
    """story.mp4 (the stages in order, 1920x1080, 30 fps) and story-bg.mp4 (blurred, 9:16, for behind it).
    Clips from this computer's engine are small: timed at their own size, then sharpened to full HD by the AI
    upscaler (Real-ESRGAN, the engine's `upscale` stage); the rest are scaled here. Returns the stage starts."""
    timed, starts, t, up = [], [], 0.0, []
    for k, s in enumerate(j.stages):
        src = clip_path(work, k)
        out = work / "timed" / f"t{k:02d}.mp4"
        timed.append(out)
        starts.append(round(t, 3))
        t += s.seconds
        if _fresh(out, src, s.seconds):
            continue
        out.unlink(missing_ok=True)
        if made_by.get(f"c{k:02d}") == "local" and anim_engine.installed():
            raw = out.with_suffix(".raw.mp4")
            fit(src, s.seconds, raw, hd=False)
            up.append((k, src, raw, out))
        else:
            fit(src, s.seconds, out)
            Path(str(out) + ".ok").write_text(f"{src.stat().st_mtime:.0f}|{s.seconds:.3f}", encoding="utf-8")
    if up:
        items = [{"id": f"t{k:02d}", "src": str(raw), "out": str(out), "kind": "video", "w": OUT_W, "h": OUT_H}
                 for k, _, raw, out in up]
        try:
            anim_engine.run_stage("upscale", {"items": items, "model": "general",
                                              "sr_dir": str(anim_engine.MODELS / "upscale")}, work, progress,
                                  "Sharpening the clips to full HD")
        except Exception as exc:  # noqa: BLE001 - scaled the plain way instead
            if exc.__class__.__name__ in ("Paused", "Stopped"):
                raise
            log.warning("Upscaling failed: %s", exc)
        for k, src, raw, out in up:
            if not out.exists():
                fit(src, j.stages[k].seconds, out)
            Path(str(out) + ".ok").write_text(f"{src.stat().st_mtime:.0f}|{j.stages[k].seconds:.3f}", encoding="utf-8")
    listing = work / "timed" / "list.txt"
    listing.write_text("".join(f"file '{p.name}'\n" for p in timed), encoding="utf-8")
    story = work / "story.mp4"
    progress(f"Joining {len(timed)} stages into one shot ({t:.1f} s)")
    proc = subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
                           "-vf", f"fps={FPS},scale={OUT_W}:{OUT_H},setsar=1", "-c:v", "libx264", "-crf", "16",
                           "-preset", "medium", "-pix_fmt", "yuv420p", "-an", str(story)], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Joining the stages failed: {proc.stderr[-300:]}")
    bg = work / "story-bg.mp4"  # blurred once here; the editor only scales it up
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(story), "-vf",
                    "scale=540:960:force_original_aspect_ratio=increase,crop=540:960,gblur=sigma=18,"
                    "eq=brightness=-0.04:saturation=1.08", "-c:v", "libx264", "-crf", "24", "-pix_fmt", "yuv420p",
                    "-an", str(bg)], check=True, capture_output=True)
    return story, bg, starts
