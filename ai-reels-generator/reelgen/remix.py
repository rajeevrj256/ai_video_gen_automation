"""Take a sound out of a finished video (the video page's Effects & media used panel: 🗑 Remove from this video).

Every cue that plays it is dropped from the video's props.json (a transition sound the editor plays by name points at
a silent file instead), and the video gets its new sound:
- long videos, Script and Shoot videos, animated, Toon and Stick videos: the soundtrack is mixed again from the props
  (soundtrack.mix, seconds) and put under the same picture (-c:v copy), then mastered like every video;
A Short keeps only its finished video (its voice, music and effect files are not kept), so its sounds can't be
changed: `why_not` says so and the page shows no button. The first time, the video as it was is kept next to it as
reel-original.mp4. No Claude calls.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .config import Config
from .video import FFMPEG

log = logging.getLogger(__name__)
Progress = Callable[[str], None]

MIXED = ("Long", "Anim", "Toon", "StickStory")  # compositions soundtrack.mix knows


def composition(report: dict, props: dict) -> str:
    editor = str(report.get("editor", ""))
    if m := re.search(r"remotion \((\w+)", editor):
        return m.group(1)
    if "beats" in props:
        return "Long"
    if editor.startswith("remotion") or "scenes" in props:
        return "Reel"
    raise ValueError("This video wasn't made with the editor, so its sounds can't be changed")


def _needed(props: dict) -> list[str]:
    """Every sound file the mix reads (voice, music, effects)."""
    out = [c["src"] for c in props.get("cues") or []]
    hook = props.get("hook") or {}
    out += [x.get("audio") for x in (hook.get("shots") or []) + (props.get("beats") or []) + (props.get("shots") or [])]
    out += [hook.get("music"), hook.get("drone"), props.get("music"), props.get("hookMusic"), props.get("hookDrone")]
    out += [m.get("src") for m in (props.get("musicParts") or []) + (props.get("ambience") or [])]
    return [x for x in out if x]


def why_not(folder: Path) -> str:
    """Why this video's sounds can't be changed, or '' when they can."""
    if not (folder / "props.json").exists() or not (folder / "report.json").exists():
        return "This video was made before its sounds were saved."
    props = json.loads((folder / "props.json").read_text(encoding="utf-8"))
    try:
        comp = composition(json.loads((folder / "report.json").read_text(encoding="utf-8")), props)
    except ValueError as exc:
        return str(exc)
    if comp not in MIXED:
        return "A Short keeps only its finished video, not its sound files, so a sound can't be taken out of it."
    missing = [f for f in _needed(props) if not (folder / f).exists()]
    if missing:
        return f"Some of this video's sound files are gone ({missing[0]}), so its sound can't be mixed again."
    return ""


def _silence(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(b"\0\0" * 4410)


def _remix(folder: Path, props: dict, report: dict, comp: str, progress: Progress, line: str) -> None:
    """The soundtrack mixed again from `props` and put under the same picture (mastered, checked); props and report
    saved. The first time, the video as it was is kept as reel-original.mp4."""
    from .audio import master
    from .soundtrack import mix
    from .verify import probe

    original = folder / "reel-original.mp4"
    if not original.exists():
        shutil.copy(folder / "reel.mp4", original)  # the video as it was, the first time its sound is changed
    out = folder / "reel-remix.mp4"
    progress(line)
    sound = folder / "soundtrack-remix.wav"
    mix(props, comp, folder, sound, FFMPEG)
    proc = subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(folder / "reel.mp4"), "-i", str(sound),
                           "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "320k", "-shortest",
                           "-movflags", "+faststart", str(out)], capture_output=True, text=True)
    sound.unlink(missing_ok=True)
    if proc.returncode != 0:
        out.unlink(missing_ok=True)
        raise RuntimeError(f"Putting the new sound under the video failed: {proc.stderr[-300:]}; the video is unchanged")
    master(out)
    info = probe(out)
    if not info.get("has_audio") or abs(float(info.get("duration") or 0) - float(report.get("duration_seconds") or info.get("duration") or 0)) > 1.5:
        out.unlink(missing_ok=True)
        raise RuntimeError("The new version didn't come out right; the video is unchanged")
    out.replace(folder / "reel.mp4")
    (folder / "props.json").write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
    report["sound_changed"] = datetime.now(timezone.utc).isoformat()
    report.setdefault("checks", {})["probe"] = info
    (folder / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def remove_sound(cfg: Config, folder: Path, name: str, progress: Progress = log.info) -> dict:
    """The video without the sound called `name` (as the Effects & media used panel names it)."""
    reason = why_not(folder)
    if reason:
        raise ValueError(reason)
    props = json.loads((folder / "props.json").read_text(encoding="utf-8"))
    report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
    comp = composition(report, props)
    cues = props.get("cues") or []
    kept = [c for c in cues if (c.get("name") or Path(c["src"]).stem) != name]
    sfx = props.get("sfx") or {}
    silenced = [k for k in sfx if k == name]
    if len(kept) == len(cues) and not silenced:
        raise ValueError(f"'{name}' isn't in this video")
    props["cues"] = kept
    if silenced:
        _silence(folder / "sfx" / "silence.wav")
        for k in silenced:
            sfx[k] = "sfx/silence.wav"
    progress(f"Taking '{name}' out ({len(cues) - len(kept)} time(s)" + (", and on every scene cut" if silenced else "") + ")")
    _remix(folder, props, report, comp, progress, "Mixing the sound again without it")
    report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
    report["removed_sounds"] = sorted(set(report.get("removed_sounds", [])) | {name})
    (folder / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    progress(f"Done: '{name}' is out of the video (the old version is kept as reel-original.mp4)")
    return report


def _music_slots(props: dict, src: str) -> list[tuple[dict, str]]:
    """Where a music file plays in a video's props: (holder, key) pairs."""
    hook = props.get("hook") or {}
    slots = [(h, k) for h, k in ((hook, "music"), (props, "music"), (props, "hookMusic")) if h.get(k) == src]
    slots += [(m, "src") for m in props.get("musicParts") or [] if m.get("src") == src]
    return slots


def replace_music(cfg: Config, folder: Path, src: str, progress: Progress = log.info) -> dict:
    """A music track YouTube claimed (Content ID), taken out of a finished video: in its place a new track composed
    for the same length (the hook's: a trailer on the hook's own cuts) at the same loudness, the sound mixed again
    under the same picture. An upload from your library is also marked claimed and never used again. No Claude."""
    from . import cinehook, media, music
    from .audio import gain_file
    from .video import media_seconds

    reason = why_not(folder)
    if reason:
        raise ValueError(reason)
    props = json.loads((folder / "props.json").read_text(encoding="utf-8"))
    report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
    comp = composition(report, props)
    slots = _music_slots(props, src)
    if not slots or not (folder / src).exists():
        raise ValueError("That track isn't in this video")
    hook = props.get("hook") or {}
    library = hook.get("own") if any(h is hook for h, _ in slots) else next(
        (m.get("name") for m, _ in slots if m is not props and m is not hook and not str(m.get("name", "")).startswith(("AI music", "Composed"))), "")
    seconds = max(1.0, media_seconds(folder / src))
    seed = int.from_bytes(src.encode("utf-8")[-4:].rjust(4, b"0"), "big") + 7
    out = folder / "music" / f"replaced-{len(list((folder / 'music').glob('replaced-*.wav')))}.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    if any(h is hook for h, _ in slots) and hook.get("shots"):
        progress(f"Composing a new hook track ({seconds:.0f} s, on the hook's cuts)")
        cuts = [float(sh["start"]) for sh in hook["shots"][1:]] + [max(0.1, seconds - 0.05)]
        music.trailer(hook.get("style") or "spy-pulse", seconds, cuts, seed, out, instant=cinehook.energetic(hook.get("template")))
    else:
        mood = ""
        if (folder / "script.json").exists():
            script = json.loads((folder / "script.json").read_text(encoding="utf-8"))
            mood = (script.get("script", script) or {}).get("mood", "")
        progress(f"Composing a new track ({seconds:.0f} s, mood {mood or 'calm'})")
        music.compose(mood or "calm", [music.Section(0.0, seconds, 0.5, False)], seconds, seed, out)
    old, new = media._loudness(folder / src), media._loudness(out)
    if old and new:  # where the claimed track sat in the mix
        import math

        gain_file(out, max(-24.0, min(15.0, 20 * math.log10(old / new))), limit=True)
    rel = out.relative_to(folder).as_posix()
    for holder, key in slots:
        holder[key] = rel
        if holder is hook:
            hook.pop("own", None)
            hook.pop("ai", None)
        elif holder is not props:
            holder["name"] = "Composed (replaced a claimed track)"
    _remix(folder, props, report, comp, progress, "Mixing the sound again with the new track")
    report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
    original = media._files(cfg, "music", everything=True)
    file = next((i.path.name for i in original if i.path and i.name == library), "") if library else ""
    if file:
        media.mark_claimed(cfg, "music", file)
    report.setdefault("replaced_music", []).append({"old": src, "new": rel, "library": file})
    (folder / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    progress(f"Done: the claimed track is out ({rel} in its place)" + (f"; '{file}' is never used again" if file else "")
             + ". The video as it was is kept as reel-original.mp4.")
    return report
