"""Your own voiceover for a finished video.

The app shows the script with each line's time slot and pace, plays the video, and records
you (one take for the whole video, or line by line). `finish` then:

1. cleans the recording (rumble filter, level, silence trimmed at the edges),
2. transcribes it with faster-whisper (offline; optional) to get word timings,
3. in one-take mode, cuts it into the script's lines where your words match them,
4. compares every line with the script: words said, words missed, and speed against the
   original slot,
5. optionally fits your speed to the original timing (at most 20% either way, so it still
   sounds like you),
6. renders a separate video, reel-myvoice.mp4, with the same footage, graphics, music and
   sound effects. The original video is never touched.

No Claude calls, so no tokens.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import time
from dataclasses import replace
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable

from .config import MAX_SECONDS, Config
from .fsutil import move
from .video import FFMPEG, media_seconds
from .voice import SceneAudio, Word

log = logging.getLogger(__name__)
Progress = Callable[[str], None]

TAKES = "myvoice"  # folder inside the video's folder
OUTPUT = "reel-myvoice.mp4"
MAX_STRETCH = 1.2  # fitting never speeds up or slows down a line by more than this
AUDIO_TYPES = {".webm", ".ogg", ".wav", ".mp3", ".m4a", ".mp4", ".aac", ".opus"}


# ---------- the script with its timing ----------

def _load(folder: Path) -> tuple[dict, dict, bool]:
    report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
    script = json.loads((folder / "script.json").read_text(encoding="utf-8"))
    return report, script, report.get("format") == "long"


def segments(folder: Path) -> dict:
    """Every line to speak, with where it sits in the video and how fast it's spoken."""
    report, script, long = _load(folder)
    if long:
        lines = [(f"{c['title']} · {bi}", b["narration"]) for c in script["chapters"]
                 for bi, b in enumerate(c["beats"], 1)]
    else:
        lines = [(f"Scene {i}", s["narration"]) for i, s in enumerate(script["scenes"], 1)]
    props_path = folder / "props.json"
    slots = None
    if props_path.exists():
        props = json.loads(props_path.read_text(encoding="utf-8"))
        items = props.get("beats" if long else "scenes", [])
        if len(items) == len(lines):
            slots = [(i["start"], i["duration"]) for i in items]
    total = float(report.get("duration_seconds") or 0) or 30.0
    if slots is None:  # older videos: spread the time by word count
        counts = [max(1, len(t.split())) for _, t in lines]
        t, slots = 0.0, []
        for n in counts:
            d = total * n / sum(counts)
            slots.append((round(t, 3), round(d, 3)))
            t += d
    out = []
    for i, ((label, text), (start, duration)) in enumerate(zip(lines, slots)):
        words = len(text.split())
        rate = words / max(duration, 0.1)
        out.append({"index": i, "label": label, "text": text, "start": round(start, 2),
                    "end": round(start + duration, 2), "seconds": round(duration, 2), "words": words,
                    "rate": round(rate, 2),
                    "pace": "fast" if rate > 3.4 else "normal" if rate > 2.5 else "calm"})
    return {"format": "long" if long else "short", "duration": total, "exact": props_path.exists(),
            "segments": out, "takes": takes(folder),
            "result": report.get("my_voice"), "has_video": (folder / OUTPUT).exists()}


def takes(folder: Path) -> dict:
    d = folder / TAKES
    found = {"all": None, "parts": {}}
    for f in sorted(d.glob("*")) if d.exists() else []:
        if f.name.startswith("take-all."):
            found["all"] = f.name
        elif m := re.match(r"part-(\d+)\.", f.name):
            found["parts"][int(m[1])] = f.name
    return found


def save_take(folder: Path, part: str, filename: str, data: bytes) -> str:
    ext = Path(filename).suffix.lower() or ".webm"
    if ext not in AUDIO_TYPES:
        raise ValueError(f"Can't use a {ext} file as a voice recording")
    if not data:
        raise ValueError("The recording is empty")
    d = folder / TAKES
    d.mkdir(exist_ok=True)
    stem = "take-all" if part == "all" else f"part-{int(part):03d}"
    for old in d.glob(stem + ".*"):
        old.unlink()
    (d / (stem + ext)).write_bytes(data)
    return stem + ext


# ---------- audio ----------

def _clean(src: Path, dst: Path, trim: bool) -> Path:
    """Mono 24 kHz WAV, rumble cut, level evened out; `trim` removes silence at both ends."""
    filters = "highpass=f=80,loudnorm=I=-16:TP=-1.5:LRA=11"
    if trim:
        edge = "silenceremove=start_periods=1:start_threshold=-42dB:start_silence=0.12"
        filters += f",{edge},areverse,{edge},areverse"
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(src), "-af", filters, "-ac", "1", "-ar", "24000",
                    str(dst)], check=True)
    return dst


def _cut(src: Path, dst: Path, start: float, end: float) -> Path:
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(src), "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
                    "-ac", "1", "-ar", "24000", str(dst)], check=True)
    return dst


def _tempo(src: Path, dst: Path, factor: float) -> Path:
    """factor > 1 speeds up; pitch stays the same."""
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(src), "-af", f"atempo={factor:.4f}", str(dst)],
                   check=True)
    return dst


def _silences(path: Path) -> list[tuple[float, float]]:
    info = subprocess.run([FFMPEG, "-hide_banner", "-i", str(path), "-af", "silencedetect=n=-38dB:d=0.25", "-f",
                           "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", info)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", info)]
    return list(zip(starts, ends))


_whisper = None


def transcribe(path: Path, language: str = "") -> list[Word] | None:
    """Word timings of what you actually said, or None when faster-whisper isn't installed."""
    global _whisper
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        log.info("faster-whisper not installed: timing only, no word check")
        return None
    import os
    if _whisper is None:
        _whisper = WhisperModel(os.environ.get("REEL_WHISPER_MODEL", "base"), device="cpu", compute_type="int8")
    lang = {"hindi": "hi", "english": "en"}.get(language.split()[-1].lower(), None) if language else None
    parts, _ = _whisper.transcribe(str(path), word_timestamps=True, language=lang, vad_filter=True)
    return [Word(w.word.strip(), round(w.start, 3), round(w.end, 3)) for seg in parts for w in (seg.words or [])
            if w.word.strip()]


def _norm(text: str) -> str:
    text = re.sub(r"['’]s\b", "", text.lower())  # "samurai's" is heard as "samurai"
    return re.sub(r"[^\w]", "", text)


# Small words speech-to-text often drops or mishears; missing only these doesn't flag a line.
FILLER = {"a", "an", "the", "and", "of", "to", "in", "on", "at", "is", "it", "so", "but", "that", "this", "was"}


def _tokens(text: str) -> list[str]:
    return [t for t in (_norm(w) for w in text.split()) if t]


# ---------- one take -> lines ----------

def _split_one_take(audio: Path, heard: list[Word] | None, lines: list[str]) -> list[tuple[float, float]]:
    """Where each line starts and ends in a single take."""
    length = media_seconds(audio)
    counts = [max(1, len(_tokens(t))) for t in lines]
    if heard:
        script = [(k, tok) for k, t in enumerate(lines) for tok in _tokens(t)]
        said = [_norm(w.text) for w in heard]
        first_hit: dict[int, int] = {}
        for block in SequenceMatcher(None, [s for _, s in script], said, autojunk=False).get_matching_blocks():
            for j in range(block.size):
                k = script[block.a + j][0]
                first_hit.setdefault(k, block.b + j)
                first_hit[k] = min(first_hit[k], block.b + j)
        starts = [0.0]
        for k in range(1, len(lines)):
            if k in first_hit:
                i = first_hit[k]
                prev_end = heard[i - 1].end if i > 0 else 0.0
                starts.append(max(starts[-1], (prev_end + heard[i].start) / 2))
            else:
                starts.append(None)  # filled in below
        # Lines with no matched word: spread between their neighbours by word count.
        for k in range(1, len(lines)):
            if starts[k] is None:
                nxt = next((j for j in range(k + 1, len(lines)) if starts[j] is not None), None)
                end = starts[nxt] if nxt is not None else length
                span = counts[k - 1:(nxt or len(lines))]
                starts[k] = starts[k - 1] + (end - starts[k - 1]) * counts[k - 1] / max(1, sum(span))
    else:
        # No transcript: cut by word count, moved to the nearest pause.
        pauses = [(a + b) / 2 for a, b in _silences(audio)]
        starts, t = [0.0], 0.0
        for n in counts[:-1]:
            t += length * n / sum(counts)
            near = min(pauses, key=lambda p: abs(p - t), default=t)
            starts.append(near if abs(near - t) < 1.5 and near > starts[-1] else t)
    ends = starts[1:] + [length]
    return [(round(a, 3), round(b, 3)) for a, b in zip(starts, ends)]


# ---------- check ----------

def _check(expected: str, heard: list[Word] | None, seconds: float, slot: float) -> dict:
    ratio = seconds / max(slot, 0.1)  # >1: you took longer than the video's line
    speed = ("slower" if ratio > 1.15 else "faster" if ratio < 0.85 else "matched")
    out = {"your_seconds": round(seconds, 2), "video_seconds": round(slot, 2), "speed": speed,
           "speed_ratio": round(ratio, 2)}
    if heard is not None:
        want, got = _tokens(expected), [_norm(w.text) for w in heard]
        sm = SequenceMatcher(None, want, got, autojunk=False)
        matched = sum(b.size for b in sm.get_matching_blocks())
        missing, extra = [], []
        for op, a1, a2, b1, b2 in sm.get_opcodes():
            if op in ("delete", "replace"):
                missing += want[a1:a2]
            if op in ("insert", "replace"):
                extra += got[b1:b2]
        out.update(words_matched=round(matched / max(1, len(want)), 2), missing=missing[:12], extra=extra[:12],
                   heard=" ".join(w.text for w in heard))
    ok_words = heard is None or not [w for w in out["missing"] if w not in FILLER]
    out["verdict"] = ("good" if ok_words and speed == "matched" else
                      "check words" if not ok_words else f"a little {speed}")
    return out


def _words_for(heard: list[Word] | None, text: str, offset: float, seconds: float) -> list[Word]:
    """Caption words for a line: what you said, or the script spread over your line when there's no transcript."""
    if heard:
        return [Word(w.text, max(0.0, round(w.start - offset, 3)), max(0.0, round(w.end - offset, 3))) for w in heard]
    toks = text.split()
    step = seconds / max(1, len(toks))
    return [Word(t, round(i * step, 3), round((i + 1) * step - 0.02, 3)) for i, t in enumerate(toks)]


# ---------- finish ----------

def finish(cfg: Config, folder: Path, mode: str, fit: str, progress: Progress = log.info) -> dict:
    """mode: 'all' (one take) or 'parts' (line by line). fit: 'mine' (the video follows your
    timing) or 'slides' (your lines are sped up or slowed down toward the video's timing)."""
    report, script, long = _load(folder)
    info = segments(folder)
    segs = info["segments"]
    have = takes(folder)
    work = folder / "_myvoice"
    shutil.rmtree(work, ignore_errors=True)
    (work / "lines").mkdir(parents=True)
    language = cfg.long_language if long else cfg.language
    try:
        progress("Cleaning up your recording")
        pieces: list[tuple[Path, list[Word] | None]] = []
        if mode == "all":
            if not have["all"]:
                raise ValueError("Record the whole video first (one take)")
            clean = _clean(folder / TAKES / have["all"], work / "take.wav", trim=True)
            progress("Listening to what you said (speech to text)")
            heard = transcribe(clean, language)
            for k, (a, b) in enumerate(_split_one_take(clean, heard, [s["text"] for s in segs])):
                line = _cut(clean, work / "lines" / f"raw{k:03d}.wav", a, b)
                words = None if heard is None else [w for w in heard if a - 0.05 <= w.start < b]
                pieces.append((line, None if words is None else
                               [Word(w.text, round(w.start - a, 3), round(w.end - a, 3)) for w in words]))
        else:
            missing = [s["label"] for s in segs if s["index"] not in have["parts"]]
            if missing:
                raise ValueError("Not recorded yet: " + ", ".join(missing[:6]) + ("..." if len(missing) > 6 else ""))
            progress("Listening to what you said (speech to text)")
            for s in segs:
                line = _clean(folder / TAKES / have["parts"][s["index"]], work / "lines" / f"raw{s['index']:03d}.wav",
                              trim=True)
                pieces.append((line, transcribe(line, language)))

        progress("Checking your lines against the script")
        checks, audios = [], []
        for s, (path, heard) in zip(segs, pieces):
            length = media_seconds(path)
            spoken = (heard[-1].end - heard[0].start) if heard else length
            checks.append({"index": s["index"], "label": s["label"], "text": s["text"],
                           **_check(s["text"], heard, spoken, s["seconds"])})
            factor = 1.0
            if fit == "slides":
                factor = min(MAX_STRETCH, max(1 / MAX_STRETCH, length / max(s["seconds"] - 0.15, 0.3)))
            audios.append([path, heard, length, factor])

        if not long:  # a Short must stay under 30 seconds: speed everything up evenly if needed
            total = sum(length / factor for _, _, length, factor in audios) + 0.12 * len(audios)
            room = MAX_SECONDS - 1
            if total > room:
                extra = total / room
                if extra > 1.35:
                    raise ValueError(f"Your voiceover is {total:.0f}s; a Short can be {MAX_SECONDS}s. Speak a little "
                                     "faster or re-record the longest lines.")
                progress(f"Your voiceover is {total:.1f}s: speeding it up {round((extra - 1) * 100)}% to fit 30s")
                for a in audios:
                    a[3] *= extra

        scenes = []
        for k, (path, heard, length, factor) in enumerate(audios):
            if abs(factor - 1) > 0.01:
                path = _tempo(path, work / "lines" / f"line{k:03d}.wav", factor)
                length /= factor
                if heard:
                    heard = [Word(w.text, round(w.start / factor, 3), round(w.end / factor, 3)) for w in heard]
            scenes.append(SceneAudio(path, _words_for(heard, segs[k]["text"], 0.0, length)))
            checks[k]["fitted_by"] = round(factor, 2)

        progress("Editing the video with your voice (takes a few minutes)")
        if long:
            _render_long(cfg, folder, work, report, script, scenes, progress)
        else:
            _render_short(cfg, folder, work, report, script, scenes)
        move(work / "reel.mp4", folder / (OUTPUT + ".new"))
        (folder / OUTPUT).unlink(missing_ok=True)
        move(folder / (OUTPUT + ".new"), folder / OUTPUT)

        good = sum(c["verdict"] == "good" for c in checks)
        result = {"mode": mode, "fit": fit, "video": OUTPUT, "made": time.time(), "lines": checks, "good_lines": good,
                  "transcribed": pieces[0][1] is not None if pieces else False,
                  "duration_seconds": round(media_seconds(folder / OUTPUT), 1),
                  "summary": f"{good} of {len(checks)} lines match the script and the video's pace"}
        report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
        report["my_voice"] = result
        (folder / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        progress("Done: " + result["summary"])
        return report
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _render_short(cfg: Config, folder: Path, work: Path, report: dict, script: dict,
                  scenes: list[SceneAudio]) -> None:
    from .rerender import _same_footage
    from .script_writer import ReelScript
    from .video import render_video
    from .visuals import fetch_backgrounds

    for field in ("subject", "hook_question", "answer"):
        script.setdefault(field, "")
    script.setdefault("category", "Life & People")
    s = ReelScript.model_validate(script)
    cfg = replace(cfg, captions=report.get("captions", True))
    # The render reads every file from its own folder, so the lines move in next to it.
    local = []
    for k, sc in enumerate(scenes):
        dst = work / "audio" / f"scene_{k:02d}.wav"
        dst.parent.mkdir(exist_ok=True)
        shutil.copy(sc.path, dst)
        local.append(SceneAudio(dst, sc.words))
    backgrounds = _same_footage(folder, work, len(s.scenes)) or fetch_backgrounds(
        [x.visual_queries for x in s.scenes], cfg.pexels_api_key, cfg.width, cfg.height, work / "backgrounds")
    from .pipeline import _render_slot
    with _render_slot(cfg):  # one edit at a time
        render_video(s.title, local, backgrounds, cfg, work / "reel.mp4", graphics=[x.graphic for x in s.scenes],
                     transitions=[x.transition for x in s.scenes], sounds=[x.sounds for x in s.scenes],
                     music=s.music)


def _render_long(cfg: Config, folder: Path, work: Path, report: dict, script: dict, scenes: list[SceneAudio],
                 progress: Progress) -> None:
    from .longform import LongScript, build_long
    from .video import _remotion_cli, _render_remotion

    ls = LongScript.model_validate(script)
    cfg = replace(cfg, captions=report.get("captions", True))
    voices, k = [], 0
    for ci, chapter in enumerate(ls.chapters):
        chunk = []
        for _ in chapter.beats:
            dst = work / "audio" / f"ch{ci:02d}" / f"beat_{k:03d}.wav"
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(scenes[k].path, dst)
            chunk.append(SceneAudio(dst, scenes[k].words))
            k += 1
        voices.append(chunk)
    old = folder / "props.json"
    look = json.loads(old.read_text(encoding="utf-8")).get("look") if old.exists() else None
    props = build_long(ls, cfg, work, progress, voices=voices, look=look)
    cli = _remotion_cli()
    if cli is None:
        raise RuntimeError("Node.js or the Remotion packages are not installed (run start.bat / start.sh)")
    from .pipeline import _render_slot
    with _render_slot(cfg):  # one edit at a time
        _render_remotion(cli, props, work / "reel.mp4", composition="Long", crf=18, timeout=4 * 3600)
