"""Polished sound for every video, whatever pipeline made it (no per-video settings):

- the narration is levelled to one loudness (`level_voice`, called by `voice.synthesize_scenes` for every voice:
  edge, Kokoro and Sarvam), so a quiet take and a loud one end up the same;
- the music is levelled against that voice (`media.level_music`): while the narrator speaks it sits SPEECH_GAP_DB
  under the voice and rises in the pauses by the composition's own swell, whatever its source (composed, AI-made or
  an upload that came in at its own loudness);
- every finished video is mastered to the loudness YouTube and Instagram play at (`master`: two-pass EBU R128
  loudnorm to -14 LUFS, true peak under -1.5 dBTP, picture copied untouched), called by `video._render_remotion`.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

VOICE_LUFS = -16.0  # the narration's integrated loudness before mixing
VOICE_PEAK = -1.5  # dBFS: a boost never pushes the voice's peaks past this
MASTER_LUFS, MASTER_TP, MASTER_LRA = -14.0, -1.5, 11.0


def _ffmpeg() -> str:
    from .video import FFMPEG

    return FFMPEG


def measure(paths: list[Path]) -> tuple[float | None, float | None]:
    """Integrated loudness (LUFS) and sample peak (dBFS) of the files played back to back."""
    paths = [p for p in paths if p and Path(p).exists()]
    if not paths:
        return None, None
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        for p in paths:
            f.write("file '" + str(Path(p).resolve()).replace("'", "'\\''") + "'\n")
        listing = f.name
    try:
        err = subprocess.run([_ffmpeg(), "-hide_banner", "-nostats", "-f", "concat", "-safe", "0", "-i", listing,
                              "-af", "ebur128=peak=sample", "-f", "null", "-"], capture_output=True, text=True,
                             timeout=600).stderr
    except (subprocess.SubprocessError, OSError) as exc:
        log.warning("Couldn't measure the voice: %s", exc)
        return None, None
    finally:
        Path(listing).unlink(missing_ok=True)
    lufs = re.findall(r"I:\s*(-?[\d.]+) LUFS", err)
    peak = re.findall(r"Peak:\s*(-?[\d.]+|-inf) dBFS", err)
    loud = float(lufs[-1]) if lufs else None
    return (loud if loud is not None and loud > -70 else None), (float(peak[-1]) if peak and peak[-1] != "-inf" else None)


def gain_file(path: Path, gain_db: float, limit: bool = False) -> bool:
    """Apply a gain to a WAV file in place (16-bit PCM, same rate and channels); `limit` adds a soft peak limiter."""
    tmp = path.with_name(path.stem + ".gain" + path.suffix)
    af = f"volume={gain_db:.2f}dB" + (",alimiter=limit=0.95:level=false" if limit else "")
    proc = subprocess.run([_ffmpeg(), "-y", "-loglevel", "error", "-i", str(path), "-af", af, "-c:a", "pcm_s16le", str(tmp)],
                          capture_output=True, text=True)
    if proc.returncode != 0 or not tmp.exists():
        log.warning("Couldn't level %s: %s", path.name, proc.stderr[-200:])
        tmp.unlink(missing_ok=True)
        return False
    tmp.replace(path)
    return True


def level_voice(paths: list[Path]) -> float:
    """One gain for the whole narration (its lines keep their levels against each other) to VOICE_LUFS, peaks under
    VOICE_PEAK. Returns the gain in dB (0 when nothing was changed)."""
    paths = [Path(p) for p in paths if p and Path(p).suffix.lower() == ".wav" and Path(p).exists()]
    loud, peak = measure(paths)
    if loud is None:
        return 0.0
    gain = VOICE_LUFS - loud
    if peak is not None:
        gain = min(gain, VOICE_PEAK - peak)
    if abs(gain) < 0.5:
        return 0.0
    done = sum(gain_file(p, gain) for p in paths)
    log.info("Voice levelled by %+.1f dB (%.1f LUFS -> %.1f) in %d file(s)", gain, loud, loud + gain, done)
    return round(gain, 2) if done else 0.0


def master(video: Path) -> dict | None:
    """The finished video's sound at -14 LUFS (true peak under -1.5 dBTP) in two passes, the picture copied as it is.
    Returns {before, after} LUFS, or None when it was left alone (no sound, or ffmpeg failed: the video stays)."""
    target = f"I={MASTER_LUFS}:TP={MASTER_TP}:LRA={MASTER_LRA}"
    try:
        err = subprocess.run([_ffmpeg(), "-hide_banner", "-nostats", "-i", str(video), "-vn", "-af",
                              f"loudnorm={target}:print_format=json", "-f", "null", "-"], capture_output=True, text=True,
                             timeout=1800).stderr
        stats = json.loads(err[err.rindex("{"):err.rindex("}") + 1])
        before = float(stats["input_i"])
    except (subprocess.SubprocessError, OSError, ValueError, KeyError):
        return None
    if before < -70:  # silent
        return None
    if abs(before - MASTER_LUFS) < 0.5 and float(stats.get("input_tp", 0)) <= MASTER_TP:
        return {"before": before, "after": before}
    tmp = video.with_name(video.stem + ".master" + video.suffix)
    measured = (f":measured_I={stats['input_i']}:measured_TP={stats['input_tp']}:measured_LRA={stats['input_lra']}"
                f":measured_thresh={stats['input_thresh']}:offset={stats['target_offset']}:linear=true")
    proc = subprocess.run([_ffmpeg(), "-y", "-loglevel", "error", "-i", str(video), "-map", "0:v?", "-map", "0:a",
                           "-c:v", "copy", "-af", f"loudnorm={target}{measured}", "-ar", "48000", "-c:a", "aac",
                           "-b:a", "320k", "-movflags", "+faststart", str(tmp)], capture_output=True, text=True,
                          timeout=3600)
    if proc.returncode != 0 or not tmp.exists() or tmp.stat().st_size < 1000:
        log.warning("Mastering %s failed; the video keeps its mix: %s", video.name, proc.stderr[-300:])
        tmp.unlink(missing_ok=True)
        return None
    tmp.replace(video)
    log.info("Mastered %s: %.1f -> %.1f LUFS", video.name, before, MASTER_LUFS)
    return {"before": before, "after": MASTER_LUFS}
