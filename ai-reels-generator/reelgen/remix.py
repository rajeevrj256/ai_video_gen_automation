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


def remove_sound(cfg: Config, folder: Path, name: str, progress: Progress = log.info) -> dict:
    """The video without the sound called `name` (as the Effects & media used panel names it)."""
    from .audio import master
    from .verify import probe

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
    original = folder / "reel-original.mp4"
    if not original.exists():
        shutil.copy(folder / "reel.mp4", original)  # the video as it was, the first time anything is taken out
    out = folder / "reel-remix.mp4"
    from .soundtrack import mix

    progress("Mixing the sound again without it")
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
    report["removed_sounds"] = sorted(set(report.get("removed_sounds", [])) | {name})
    report["sound_changed"] = datetime.now(timezone.utc).isoformat()
    report.setdefault("checks", {})["probe"] = info
    (folder / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    progress(f"Done: '{name}' is out of the video (the old version is kept as reel-original.mp4)")
    return report
