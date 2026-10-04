"""Assemble the final 9:16 video: backgrounds + voiceover + captions + graphics + music.

The edit is rendered by Remotion (the `remotion/` folder): animated graphics,
word-by-word captions, the hook title, punch-in cuts with flashes, and synced
sound effects. If Node.js or the Remotion packages aren't installed (or the
render fails), a simpler moviepy edit without graphics is made instead.
"""

from __future__ import annotations

import json
import logging
import os
import random
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from moviepy import (
    AudioFileClip,
    ColorClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    VideoClip,
    VideoFileClip,
    afx,
    vfx,
)

from .captions import build_captions, group_words, render_title
from .config import MAX_SECONDS, PROJECT_ROOT, Config
from . import media
from .sfx import write_sfx
from .voice import SceneAudio

log = logging.getLogger(__name__)

REMOTION_DIR = PROJECT_ROOT / "remotion"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

# Breathing room after each scene's narration; varied so the pacing isn't robotic.
SCENE_PADDING = (0.12, 0.35)
MIN_PADDING = 0.05
TITLE_SECONDS = 2.8


# ---------- timeline (shared by both editors) ----------

@dataclass
class Timeline:
    starts: list[float]
    durations: list[float]

    @property
    def total(self) -> float:
        return self.starts[-1] + self.durations[-1] if self.starts else 0.0


def media_seconds(path: Path) -> float:
    """Length of an audio or video file, read from ffmpeg's header info."""
    info = subprocess.run([FFMPEG, "-hide_banner", "-i", str(path)], capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", info)
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else 0.0


def voice_seconds(scenes: list[SceneAudio]) -> float:
    return sum(media_seconds(s.path) for s in scenes)


def plan_timeline(scenes: list[SceneAudio]) -> Timeline:
    """Each scene lasts its voiceover plus a little air, keeping the video under MAX_SECONDS
    by shrinking the air first (a frame of margin keeps rounding from tipping it over)."""
    voices = [media_seconds(s.path) for s in scenes]
    pads = [random.uniform(*SCENE_PADDING) for _ in scenes]
    room = MAX_SECONDS - 0.1 - sum(voices)
    if sum(pads) > room:
        shrink = max(room, MIN_PADDING * len(pads)) / sum(pads)
        pads = [max(MIN_PADDING, p * shrink) for p in pads]
    starts, t = [], 0.0
    for voice, pad in zip(voices, pads):
        starts.append(round(t, 3))
        t += voice + pad
    return Timeline(starts, [round(v + p, 3) for v, p in zip(voices, pads)])


def render_video(title: str, scenes: list[SceneAudio], backgrounds: list[list[Path]], cfg: Config,
                 out_path: Path, graphics: list | None = None, transitions: list[str] | None = None,
                 sounds: list[list] | None = None, music: str = "", music_file: Path | None = None) -> dict:
    """Render to `out_path`. Every input file must live inside out_path's folder,
    which is the public dir Remotion serves them from."""
    timeline = plan_timeline(scenes)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    editor = "remotion"
    cli = _remotion_cli()
    try:
        if cli is None:
            raise RuntimeError("Node.js or the Remotion packages are not installed (run start.bat / start.sh)")
        props = build_props(title, scenes, backgrounds, graphics or [None] * len(scenes), timeline, cfg,
                            out_path.parent, transitions, sounds, music, music_file)
        _render_remotion(cli, props, out_path)
    except Exception as exc:
        log.warning("Remotion edit unavailable, using the simpler moviepy edit: %s", exc)
        editor = f"moviepy ({exc})"[:300]
        _render_moviepy(title, scenes, backgrounds, timeline, cfg, out_path)

    thumb_path = out_path.with_name("thumbnail.jpg")
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", f"{min(1.0, timeline.total / 2):.2f}",
                    "-i", str(out_path), "-frames:v", "1", "-q:v", "3", str(thumb_path)], check=False)
    log.info("Rendered %s (%.1fs) with %s", out_path, timeline.total, editor)
    return {"video": str(out_path), "thumbnail": str(thumb_path), "duration_seconds": round(timeline.total, 1),
            "editor": editor}


# ---------- Remotion ----------

def _remotion_cli() -> Path | None:
    cli = REMOTION_DIR / "node_modules" / ".bin" / ("remotion.cmd" if os.name == "nt" else "remotion")
    return cli if cli.exists() and shutil.which("node") else None


def _graphic(g) -> dict:
    """Script graphic -> props, dropping ones that can't be drawn rather than failing the render."""
    none = {"type": "none", "headline": "", "label": "", "points": []}
    if g is None or g.type == "none":
        return none
    data = g.model_dump()
    if g.type == "chart" and len(g.points) < 2:
        return none
    if g.type == "compare":
        if len(g.points) < 2:
            return none
        data["points"] = data["points"][:2]
    if g.type in ("stat", "keyword") and not g.headline.strip():
        return none
    return data


TRANSITIONS = ("flash", "zoom", "slide", "glitch", "fade")


def plan_transitions(requested: list[str] | None, count: int) -> list[str]:
    """The transition into each scene ("none" for the first). Keeps Claude's choices, but
    never the same one twice in a row, and at least two kinds when there are 3+ cuts, so
    scene changes never all look and sound alike."""
    wanted = [t if t in TRANSITIONS else "flash" for t in (requested or [])]
    wanted += ["flash"] * (count - len(wanted))
    out = ["none"]
    for i in range(1, count):
        t = wanted[i]
        if t == out[-1]:  # swap a repeat for the next kind in the list
            t = TRANSITIONS[(TRANSITIONS.index(t) + 1) % len(TRANSITIONS)]
        out.append(t)
    if count >= 4 and len(set(out[1:])) < 2:
        out = ["none"] + [TRANSITIONS[i % 2] for i in range(count - 1)]
    return out


def build_props(title: str, scenes: list[SceneAudio], backgrounds: list[list[Path]], graphics: list,
                timeline: Timeline, cfg: Config, public_dir: Path, transitions: list[str] | None = None,
                sounds: list[list] | None = None, music_name: str = "", music_file: Path | None = None) -> dict:
    """Everything the Reel composition needs (see remotion/src/types.ts). Times in seconds."""
    def rel(path: Path) -> str:  # paths in props are relative to the public dir
        return Path(path).resolve().relative_to(public_dir.resolve()).as_posix()

    kinds = plan_transitions(transitions, len(scenes))
    scene_props, cuts, captions, cues, spoken = [], [], [], [], []
    used: dict[str, str] = {}
    for i, (scene, clips, start, duration) in enumerate(zip(scenes, backgrounds, timeline.starts, timeline.durations)):
        scene_props.append({"start": start, "duration": duration, "audio": rel(scene.path),
                            "graphic": _graphic(graphics[i] if i < len(graphics) else None),
                            "transition": kinds[i]})

        per_clip = duration / len(clips)
        for j, clip in enumerate(clips):
            video = clip.suffix == ".mp4"
            length = media_seconds(clip) if video else None
            # Skip the stock intro, and leave enough clip to fill the cut.
            offset = random.uniform(0, max(0.0, length - per_clip) * 0.6) if length else 0.0
            placeholder = clip.stem.startswith("gradient_")
            cuts.append({
                "src": "" if placeholder else rel(clip),
                "start": round(start + j * per_clip, 3),
                "duration": round(per_clip, 3),
                "offset": round(offset, 3),
                "length": round(length, 3) if length else None,
                "punchIn": (len(cuts) % 2) == 1,  # every other cut, across the whole video
                "image": not video,
            })

        spoken += [(start + w.start, start + w.end) for w in scene.words]
        room = media.TOTAL_CUES - len(cues)
        cues += media.resolve_cues((sounds[i] if sounds and i < len(sounds) else []), scene.words, start, cfg,
                                   public_dir / "sfx", rel, min(room, media.HOOK_CUES if i == 0 else media.SCENE_CUES),
                                   used)
        groups = group_words(scene.words)
        for g_idx, group in enumerate(groups):
            end = groups[g_idx + 1][0].start if g_idx + 1 < len(groups) else duration
            words = [{"text": w.text, "start": round(start + w.start, 3), "end": round(start + min(w.end, duration), 3)}
                     for w in group]
            if end > group[0].start:
                captions.append({"start": words[0]["start"], "end": round(start + end, 3), "words": words})

    if music_file is not None and Path(music_file).exists():  # a re-make keeps the video's own track
        music = Path(shutil.copy(music_file, public_dir / f"music-kept{Path(music_file).suffix.lower()}"))
    else:  # a new track for this video (an upload Claude picked, else composed in a fitting mood)
        music = media.pick_music(cfg, music_name, public_dir, timeline.total,
                                 {"facts": "curious", "story": "mystery", "comedy": "playful"}.get(cfg.video_style, ""))
    sfx = write_sfx(public_dir / "sfx")
    sfx.update(media.uploaded_for(cfg, list(sfx), public_dir / "sfx"))  # the user's whoosh/pop/... where one matches
    props = {
        "title": title,
        "fps": cfg.fps,
        "duration": round(timeline.total, 3),
        "scenes": scene_props,
        "cuts": cuts,
        "captions": captions if cfg.captions else [],  # subtitles off: no caption layer at all
        "music": rel(music) if music else None,
        "sfx": {name: rel(path) for name, path in sfx.items()},
        "cues": cues,
        "speech": media.speech_spans(spoken),
    }
    # Every effect quieter than the narrator, measured, whatever file it came from.
    props["sfxLevels"] = media.level_sounds(props, public_dir, [sp["audio"] for sp in scene_props])
    return props


def _render_remotion(cli: Path, props: dict, out_path: Path, composition: str = "Reel", crf: int = 18,
                     timeout: int = 1800, progress=None) -> None:
    """Render with Remotion. A long composition (over PART_FROM seconds) is rendered in one-minute parts
    that survive a crash, a timeout or closing the app (`_render_in_parts`); a Short in one go."""
    public_dir = out_path.parent
    props_path = public_dir / "props.json"
    props_path.write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
    if composition in ("Long", "StickStory") and float(props.get("duration") or 0) > PART_FROM:
        return _render_in_parts(cli, props, props_path, out_path, composition, crf, progress or log.info)
    gpu = _gpu_wanted()
    cmd = _remotion_cmd(cli, composition, out_path, props_path, crf, gpu)
    log.info("Rendering with Remotion: %s", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=REMOTION_DIR, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, stdin=subprocess.DEVNULL)
    if (proc.returncode != 0 or not out_path.exists()) and gpu:
        # GPU encoding (NVENC) fails outright on machines without a usable NVIDIA GPU
        # rather than falling back, so retry once with normal CPU encoding.
        _gpu_failed(proc)
        cmd = _remotion_cmd(cli, composition, out_path, props_path, crf, False)
        proc = subprocess.run(cmd, cwd=REMOTION_DIR, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout, stdin=subprocess.DEVNULL)
    if proc.returncode != 0 or not out_path.exists():
        tail = (proc.stderr.strip() or proc.stdout.strip())[-1500:]
        raise RuntimeError(f"Remotion render failed ({proc.returncode}): {tail}")


PART_FROM = 150  # seconds: longer compositions render in parts
PART_SECONDS = 60
PART_TIMEOUT = 3600  # one part (a minute of video) taking an hour means something is stuck
_gpu_broken = {"why": ""}  # set once GPU encoding failed on this machine: later renders go straight to CPU


def _env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    return "" if value.startswith("#") else value  # a comment read as a value


def _gpu_wanted() -> bool:
    return bool(_env("REEL_HWACCEL")) and _env("REEL_HWACCEL") != "disable" and not _gpu_broken["why"]


def _gpu_failed(proc) -> None:
    tail = (proc.stderr.strip() or proc.stdout.strip())[-400:]
    _gpu_broken["why"] = tail or "GPU encoding failed"
    log.warning("GPU encoding failed, using CPU encoding from now on: %s", tail)


def _free_ram_gb() -> float | None:
    """Memory free right now (Windows, Linux, macOS), or None if unknown."""
    try:
        if os.name == "nt":
            import ctypes

            class Status(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            st = Status()
            st.dwLength = ctypes.sizeof(Status)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
            return st.ullAvailPhys / 2**30
        with open("/proc/meminfo", encoding="utf-8") as fh:
            info = dict(line.split(":", 1) for line in fh)
        return int(info["MemAvailable"].split()[0]) / 2**20
    except Exception:
        return None


def _concurrency() -> int:
    """Frames drawn at once: REEL_CONCURRENCY, else every core, but never more browser tabs than free
    memory holds (about 0.9 GB each). Too many tabs on a laptop with little free memory made Windows
    swap to disk, and the render crawled at ~1 frame a second."""
    if _env("REEL_CONCURRENCY"):
        return max(1, int(float(_env("REEL_CONCURRENCY"))))
    cores = max(1, os.cpu_count() or 1)
    free = _free_ram_gb()
    return cores if free is None else max(2, min(cores, int(free / 0.9)))


def _remotion_cmd(cli: Path, composition: str, out: Path, props_path: Path, crf: int, gpu: bool,
                  extra: list[str] | None = None) -> list[str]:
    cmd = [str(cli), "render", "src/index.ts", composition, str(out),
           f"--props={props_path}", f"--public-dir={props_path.parent}",
           # bt709 tags the file as standard TV-range colour, so phones don't show it washed out.
           "--codec=h264", "--color-space=bt709", "--overwrite",
           # Frames go to the encoder as JPEG; the default quality (80) softens text edges.
           "--jpeg-quality=95", f"--concurrency={_concurrency()}"]
    # Remotion downloads its own headless Chrome on first render. Where that
    # download is blocked, REEL_CHROME can point at an installed Chrome/Chromium.
    # REEL_CHROME=chrome-for-testing uses Remotion's full test browser instead of the headless
    # shell: on a Windows laptop with a GTX 1650 only that one (with REEL_GL empty) drew on the GPU.
    chrome = _env("REEL_CHROME")
    if chrome.lower() == "chrome-for-testing":
        cmd += ["--chrome-mode=chrome-for-testing"]
    elif chrome:
        cmd += [f"--browser-executable={chrome}", "--chrome-mode=chrome-for-testing"]
    if _env("REEL_GL"):  # browser GPU backend, e.g. "egl" on Linux
        cmd.append(f"--gl={_env('REEL_GL')}")
    if gpu:
        # Remotion turns GPU encoding (NVENC) off whenever --crf is given ("crf is not supported with
        # hardware acceleration"), so the GPU sat idle while the CPU encoded. NVENC takes a bitrate:
        # REEL_GPU_BITRATE, default 8M for 16:9 videos (flat animation) and 12M for Shorts (footage).
        bitrate = _env("REEL_GPU_BITRATE") or ("12M" if composition == "Reel" else "8M")
        cmd += [f"--hardware-acceleration={_env('REEL_HWACCEL')}", f"--video-bitrate={bitrate}"]
    else:
        cmd.append(f"--crf={crf}")
    return cmd + (extra or [])


def _render_in_parts(cli: Path, props: dict, props_path: Path, out_path: Path, composition: str, crf: int,
                     progress) -> None:
    """Render a long video one minute at a time into render-parts/, then join the parts and the
    soundtrack (rendered once, audio only) without re-encoding. A finished part is kept: a crash, a
    timeout or a closed app costs one minute of work, and Resume continues with the next part (parts
    of a changed timeline are thrown away). Every part reports progress and the time left; GPU
    encoding is tried on the first part and, if it fails, the rest goes to the CPU (no full re-render)."""
    import hashlib
    import math

    fps = int(props.get("fps") or 30)
    total = max(1, math.ceil(float(props["duration"]) * fps))
    parts = out_path.parent / "render-parts"
    parts.mkdir(exist_ok=True)
    stamp = hashlib.sha1((json.dumps(props, sort_keys=True) + composition).encode()).hexdigest()[:16]
    mark = parts / "timeline.sha"
    if not mark.exists() or mark.read_text().strip() != stamp:
        for old in parts.glob("*"):
            old.unlink()
        mark.write_text(stamp)
    step = PART_SECONDS * fps
    ranges = [(a, min(a + step, total) - 1) for a in range(0, total, step)]
    files, drawn, started = [], 0, time.time()
    for i, (a, b) in enumerate(ranges):
        part, ok = parts / f"part{i:03d}.mp4", parts / f"part{i:03d}.ok"
        files.append(part)
        if part.exists() and ok.exists():
            continue
        gpu = _gpu_wanted()
        for attempt in (gpu, False) if gpu else (False,):
            cmd = _remotion_cmd(cli, composition, part, props_path, crf, attempt, [f"--frames={a}-{b}", "--muted"])
            log.info("Rendering part %d/%d: %s", i + 1, len(ranges), " ".join(cmd))
            t0 = time.time()
            try:
                proc = subprocess.run(cmd, cwd=REMOTION_DIR, capture_output=True, text=True, encoding="utf-8",
                                      errors="replace", timeout=PART_TIMEOUT, stdin=subprocess.DEVNULL)
            except subprocess.TimeoutExpired:
                raise RuntimeError(f"Part {i + 1} of {len(ranges)} (one minute of video) took over an hour, so the "
                                   "render stopped; the finished parts are kept and Resume continues from here.")
            if proc.returncode == 0 and part.exists():
                ok.write_text("gpu" if attempt else "cpu")
                break
            if attempt:  # GPU encoding failed: this part and the rest on the CPU
                _gpu_failed(proc)
                progress("GPU encoding didn't work on this computer; encoding on the CPU instead")
                continue
            tail = (proc.stderr.strip() or proc.stdout.strip())[-1500:]
            raise RuntimeError(f"Remotion render failed on part {i + 1} ({proc.returncode}): {tail}")
        drawn += b - a + 1
        rate = (b - a + 1) / max(0.1, time.time() - t0)
        left = (total - b - 1) / max(0.01, drawn / max(0.1, time.time() - started)) / 60
        progress(f"Editing: {(b + 1) / fps / 60:.1f} of {total / fps / 60:.1f} min done · {rate:.1f} frames/s · "
                 + (f"about {max(1, round(left))} min left" if b + 1 < total else "adding the sound and joining the parts"))
    # The soundtrack once (voice, music, effects), then everything joined without re-encoding the picture.
    audio = parts / "audio.wav"
    if not audio.exists():
        cmd = [str(cli), "render", "src/index.ts", composition, str(audio), f"--props={props_path}",
               f"--public-dir={props_path.parent}", "--codec=wav", "--overwrite"]
        proc = subprocess.run(cmd, cwd=REMOTION_DIR, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=PART_TIMEOUT, stdin=subprocess.DEVNULL)
        if proc.returncode != 0 or not audio.exists():
            raise RuntimeError(f"Rendering the soundtrack failed: {(proc.stderr or proc.stdout)[-800:]}")
    listing = parts / "parts.txt"
    listing.write_text("".join(f"file '{f.name}'\n" for f in files), encoding="utf-8")
    join = [FFMPEG, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing), "-i", str(audio),
            "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "320k", "-shortest", "-movflags", "+faststart"]
    proc = subprocess.run(join + ["-c:v", "copy", str(out_path)], capture_output=True, text=True)
    if proc.returncode != 0 or not out_path.exists():  # parts from two encoders: join them by re-encoding once
        proc = subprocess.run(join + ["-c:v", "libx264", "-crf", str(crf), "-pix_fmt", "yuv420p", str(out_path)],
                              capture_output=True, text=True)
    if proc.returncode != 0 or not out_path.exists():
        raise RuntimeError(f"Joining the parts failed: {proc.stderr[-800:]}")
    shutil.rmtree(parts, ignore_errors=True)


# ---------- moviepy (fallback) ----------

def _fill_frame(clip, width: int, height: int):
    """Scale to cover the frame, then center-crop to exactly width x height."""
    scale = max(width / clip.w, height / clip.h)
    clip = clip.resized(scale)
    return clip.cropped(x_center=clip.w / 2, y_center=clip.h / 2, width=width, height=height)


def _background(path: Path, duration: float, cfg: Config, punch_in: bool):
    if path.suffix == ".mp4":
        clip = VideoFileClip(str(path), audio=False)
        clip = _fill_frame(clip, cfg.width, cfg.height)
        if punch_in:  # editor-style tighter crop on alternate cuts
            clip = _fill_frame(clip.resized(1.12), cfg.width, cfg.height)
        if clip.duration < duration:
            clip = clip.with_effects([vfx.Loop(duration=duration)])
            return clip.subclipped(0, duration)
        start = random.uniform(0, max(0.0, clip.duration - duration) * 0.6)  # skip the stock intro
        return clip.subclipped(start, start + duration)
    # Still image: slow Ken Burns zoom so the frame never feels static.
    clip = ImageClip(str(path)).with_duration(duration)
    clip = clip.resized(lambda t: 1 + 0.03 * t)
    return clip.with_position("center")


def _scene_backgrounds(paths: list[Path], start: float, duration: float, cfg: Config, cut_index: int):
    """Split one scene across its clips (quick cuts), returning clips placed on the timeline."""
    clips = []
    per_clip = duration / len(paths)
    for i, path in enumerate(paths):
        clips.append(_background(path, per_clip, cfg, punch_in=(cut_index + i) % 2 == 1).with_start(start + i * per_clip))
    return clips


def _progress_bar(total: float, cfg: Config, height: int = 14):
    def frame(t):
        img = np.zeros((height, cfg.width, 3), dtype=np.uint8)
        img[:, : int(cfg.width * min(t / total, 1.0))] = (255, 214, 10)
        return img

    return VideoClip(frame_function=frame, duration=total).with_position((0, cfg.height - height))


def _music(total: float, cfg: Config):
    tracks = sorted(cfg.music_dir.glob("*.mp3")) if cfg.music_dir.exists() else []
    if not tracks:
        return None
    track = AudioFileClip(str(random.choice(tracks)))
    effects = [afx.MultiplyVolume(0.12), afx.AudioFadeOut(1.5)]
    if track.duration < total:
        effects.insert(0, afx.AudioLoop(duration=total))
    return track.with_effects(effects).subclipped(0, total)


def _render_moviepy(title: str, scenes: list[SceneAudio], backgrounds: list[list[Path]], timeline: Timeline,
                    cfg: Config, out_path: Path) -> None:
    bg_layers, caption_layers, audio_layers = [], [], []
    caption_width = cfg.width - 140
    caption_y = int(cfg.height * 0.60)
    cuts = 0

    for scene, bg_paths, t, duration in zip(scenes, backgrounds, timeline.starts, timeline.durations):
        bg_layers.extend(_scene_backgrounds(bg_paths, t, duration, cfg, cuts))
        cuts += len(bg_paths)
        audio_layers.append(AudioFileClip(str(scene.path)).with_start(t))
        for cap in build_captions(scene.words, t, t + duration, caption_width, font_path=cfg.font_path):
            caption_layers.append(
                ImageClip(cap.image)
                .with_start(cap.start)
                .with_duration(cap.end - cap.start)
                .with_position(("center", caption_y - cap.image.shape[0] // 2))
            )

    total = timeline.total
    # Darken footage slightly so white captions stay readable on any background.
    dim = ColorClip((cfg.width, cfg.height), color=(0, 0, 0)).with_opacity(0.28).with_duration(total)
    title_img = render_title(title, cfg.width - 120, font_path=cfg.font_path)
    title_clip = (ImageClip(title_img).with_duration(min(TITLE_SECONDS, total))
                  .with_position(("center", int(cfg.height * 0.14))))

    video = CompositeVideoClip(
        bg_layers + [dim] + caption_layers + [title_clip, _progress_bar(total, cfg)],
        size=(cfg.width, cfg.height),
    ).with_duration(total)

    music = _music(total, cfg)
    if music is not None:
        audio_layers.append(music)
    video = video.with_audio(CompositeAudioClip(audio_layers).with_duration(total))

    video.write_videofile(
        str(out_path),
        fps=cfg.fps,
        codec="libx264",
        audio_codec="aac",
        preset="veryfast",
        threads=4,
        temp_audiofile=str(out_path.with_name("_temp_audio.m4a")),  # keep temp files out of the cwd
        ffmpeg_params=["-pix_fmt", "yuv420p", "-movflags", "+faststart", "-crf", "18"],
        logger=None,
    )
    video.close()
