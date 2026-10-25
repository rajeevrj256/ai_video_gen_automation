"""Render a Sticky film: the picture in one-minute parts with Remotion (each part kept, so a crash costs a minute),
joined with the soundtrack from mixdown.py and mastered to -14 LUFS (reelgen/audio.py). The shared render helpers are
used as they are; nothing in the other pipelines changes."""
from __future__ import annotations

import hashlib
import json
import logging
import math
import subprocess
import time
from pathlib import Path

from .. import stopper
from ..video import FFMPEG, REMOTION_DIR, _concurrency, _first_error, _gpu_error, _gpu_failed, _gpu_wanted, _remotion_cli, _remotion_cmd

log = logging.getLogger(__name__)
PART_SECONDS = 60
PART_TIMEOUT = 3600
TRIES = 3


def render(props: dict, soundtrack: Path, work: Path, out: Path, progress, crf: int = 18) -> None:
    cli = _remotion_cli()
    if not cli:
        raise RuntimeError("Remotion isn't installed (run start.sh / start.bat once).")
    props_path = work / "props.json"
    props_path.write_text(json.dumps({**props, "silent": True}, ensure_ascii=False), encoding="utf-8")
    fps = int(props["fps"])
    total = max(1, math.ceil(float(props["duration"]) * fps))
    parts = work / "render-parts"
    parts.mkdir(exist_ok=True)
    stamp = hashlib.sha1(json.dumps(props, sort_keys=True).encode()).hexdigest()[:16]
    mark = parts / "timeline.txt"
    if not mark.exists() or mark.read_text() != stamp:  # a changed film: its old parts are useless
        for old in parts.glob("*"):
            old.unlink()
        mark.write_text(stamp)
    step = PART_SECONDS * fps
    ranges = [(a, min(a + step, total) - 1) for a in range(0, total, step)]
    files, started = [], time.time()
    gpu = _gpu_wanted()
    for i, (a, b) in enumerate(ranges):
        part, ok = parts / f"part{i:03d}.mp4", parts / f"part{i:03d}.ok"
        files.append(part)
        if part.exists() and ok.exists():
            continue
        for tries in range(1, TRIES + 1):
            cmd = _remotion_cmd(cli, "Sticky", part, props_path, crf, gpu, [f"--frames={a}-{b}", "--muted"],
                                max(1, _concurrency() // 2) if tries == TRIES else None)
            t0 = time.time()
            proc = stopper.run(cmd, cwd=REMOTION_DIR, capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=PART_TIMEOUT, stdin=subprocess.DEVNULL)
            if proc.returncode == 0 and part.exists():
                ok.write_text("ok")
                break
            if gpu and _gpu_error(proc):
                _gpu_failed(proc)
                gpu = False
                continue
            if tries == TRIES:
                raise RuntimeError(f"Rendering part {i + 1} of {len(ranges)} failed: {_first_error(proc)}")
            progress(f"Editing: part {i + 1} of {len(ranges)} failed ({_first_error(proc)[:120]}); trying it again")
        rate = (b - a + 1) / max(0.1, time.time() - t0)
        left = (total - b - 1) / max(0.01, (b + 1) / max(0.1, time.time() - started)) / 60
        progress(f"Editing: {(b + 1) / fps / 60:.1f} of {total / fps / 60:.1f} min done · {rate:.1f} frames/s"
                 + (f" · about {max(1, round(left))} min left" if b + 1 < total else ""))
    listing = parts / "parts.txt"
    listing.write_text("".join(f"file '{f.name}'\n" for f in files), encoding="utf-8")
    join = [FFMPEG, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing), "-i", str(soundtrack),
            "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "256k", "-shortest", "-movflags", "+faststart"]
    proc = subprocess.run(join + ["-c:v", "copy", str(out)], capture_output=True, text=True)
    if proc.returncode != 0 or not out.exists():  # parts from two encoders: join them by encoding once
        proc = subprocess.run(join + ["-c:v", "libx264", "-crf", str(crf), "-pix_fmt", "yuv420p", str(out)], capture_output=True, text=True)
    if proc.returncode != 0 or not out.exists():
        raise RuntimeError(f"Joining the film failed: {proc.stderr[-600:]}")
    from ..audio import master
    try:
        done = master(out)
        if done:
            progress(f"Sound mastered: {done['before']:.1f} -> {done['after']:.1f} LUFS")
    except Exception as exc:  # noqa: BLE001 - the film itself is finished
        if isinstance(exc, stopper.Paused):
            raise
        log.warning("Mastering skipped: %s", exc)
