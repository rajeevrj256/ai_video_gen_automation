"""The Sticky films' soundtrack, mixed from the timeline with ffmpeg and numpy (the composition draws no sound):
a music bed per act (each act its own mood, crossfaded; it drops away on 'quiet' shots), every sound cue on its frame,
and, when asked, the inner voice's whispered lines (three of the seven reference films whisper them)."""
from __future__ import annotations

import asyncio
import logging
import random
import subprocess
from pathlib import Path

import numpy as np

from .. import aimusic, music
from ..video import FFMPEG
from . import sounds

log = logging.getLogger(__name__)
RATE = 44100
MUSIC_GAIN = 0.34
EFFECT_RMS = 0.09
MUSIC_RMS = 0.18  # every act's track brought to this level first (composed moods came out up to ~6 dB apart)
QUIET_GAIN = 0.1
INTENSITY = {"open": 0.3, "loop": 0.45, "low": 0.2, "turn": 0.3, "day1": 0.35, "climb": 0.75, "test": 0.6, "resolve": 0.55,
             "thesis": 0.25, "title": 0.35}
GENRES = ("lofi", "piano-minimal", "ambient-electronic", "acoustic-folk")
WHISPER_VOICE = "en-US-ChristopherNeural"


def decode(path: Path) -> np.ndarray:
    """Any sound file as float32 stereo at RATE."""
    raw = subprocess.run([FFMPEG, "-v", "error", "-i", str(path), "-ac", "2", "-ar", str(RATE), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2).copy()


def _place(buf: np.ndarray, x: np.ndarray, at: float, gain: float, length: float | None = None) -> None:
    i = int(at * RATE)
    if i >= len(buf) or len(x) == 0:
        return
    if length:  # loop the sound across the span it was given
        n = int(length * RATE)
        x = np.tile(x, (n // len(x) + 1, 1))[:n]
        fade = min(len(x), int(0.25 * RATE))
        x[-fade:] *= np.linspace(1, 0, fade)[:, None]
    j = min(len(buf), i + len(x))
    buf[i:j] += x[: j - i] * gain


def _capped(x: np.ndarray) -> np.ndarray:
    """An effect no louder than EFFECT_RMS where it sounds: the phone buzz, dense from start to end, sat ~5 dB over
    every other sound at the same peak."""
    loud = x[np.abs(x).max(axis=1) > 0.01]
    rms = float(np.sqrt((loud ** 2).mean())) if len(loud) else 0.0
    return x * (EFFECT_RMS / rms) if rms > EFFECT_RMS else x


def _tracks(cfg, sections: list[dict], work: Path, seed: int, progress) -> dict[int, Path]:
    """One track per act: from the AI music model when it's installed (a calm genre the last films didn't use),
    else composed (music.compose) in the act's mood."""
    out = work / "music"
    out.mkdir(parents=True, exist_ok=True)
    made: dict[int, Path] = {}
    if aimusic.available(cfg):
        recent = set(aimusic.recent_genres(cfg))
        genre = random.Random(seed).choice([g for g in GENRES if g not in recent] or list(GENRES))
        wanted = [aimusic.track(f"act{i:02d}", out / f"act{i:02d}-ai.wav", s["end"] - s["start"] + 2, genre, s["mood"],
                                INTENSITY.get(s["act"], 0.4), "soft score for a wordless animated short film about an everyday struggle",
                                seed + i) for i, s in enumerate(sections)]
        for tid, path in aimusic.make(cfg, wanted, work, progress, "Music (AI)").items():
            made[int(tid[3:])] = path
        if made:
            aimusic.remember(cfg, genre)
    for i, s in enumerate(sections):
        if i in made:
            continue
        seconds = s["end"] - s["start"] + 2
        mood = s["mood"] if s["mood"] in music.MOOD_SPECS else "calm"
        made[i] = music.compose(mood, [music.Section(0, seconds, INTENSITY.get(s["act"], 0.4))], seconds, seed * 31 + i,
                                out / f"act{i:02d}.wav")
    return made


def _whispers(lines: list[tuple[float, str]], work: Path, progress) -> list[tuple[float, Path]]:
    """The inner voice's lines, whispered: a low male voice slowed a touch, filtered thin and breathy with a short
    echo. A failure (no network for the voice) only leaves them silent, like four of the seven reference films."""
    if not lines:
        return []
    from .. import voice  # noqa: F401 - its SSL fix for edge-tts behind a proxy
    import edge_tts

    out_dir = work / "whispers"
    out_dir.mkdir(parents=True, exist_ok=True)
    done = []
    for k, (at, text) in enumerate(lines):
        raw, final = out_dir / f"w{k:02d}.mp3", out_dir / f"w{k:02d}.wav"
        if not final.exists():
            try:
                asyncio.run(edge_tts.Communicate(text, WHISPER_VOICE, rate="-12%", pitch="-14Hz", volume="-10%").save(str(raw)))
                subprocess.run([FFMPEG, "-v", "error", "-y", "-i", str(raw), "-af",
                                "highpass=f=220,lowpass=f=3400,aecho=0.6:0.4:70:0.25,volume=1.4", str(final)], check=True)
            except Exception as exc:  # noqa: BLE001 - whispers are a garnish
                progress(f"The inner voice stays silent ({str(exc)[:120]})")
                return done
        done.append((at, final))
    return done


def mix(cfg, props: dict, cues: list[dict], sections: list[dict], work: Path, out: Path, seed: int,
        whispers: bool, progress) -> dict:
    """Write the soundtrack (WAV) and return what went into it for the report."""
    total = float(props["duration"]) + 0.5
    buf = np.zeros((int(total * RATE), 2), np.float32)
    tracks = _tracks(cfg, sections, work, seed, progress)
    for i, s in enumerate(sections):
        x = decode(tracks[i])
        loud = x[np.abs(x).max(axis=1) > 0.01] if len(x) else x
        if len(loud):
            x = x * min(4.0, MUSIC_RMS / max(1e-6, float(np.sqrt((loud ** 2).mean()))))
        length = s["end"] - s["start"] + (1.5 if i < len(sections) - 1 else 0.5)
        x = np.tile(x, (int(length * RATE) // max(1, len(x)) + 1, 1))[: int(length * RATE)]
        n = len(x)
        env = np.ones(n, np.float32)
        fin, fout = int(0.8 * RATE), int(1.5 * RATE)
        env[:fin] *= np.linspace(0, 1, min(fin, n))[: min(fin, n)] if i else 1
        env[-min(fout, n):] *= np.linspace(1, 0, min(fout, n))
        for a, b in s["quiet"]:  # the breath before the turn: the music steps back, smoothly
            qa, qb = int((a - s["start"]) * RATE), int((b - s["start"]) * RATE)
            ramp = int(0.4 * RATE)
            g = np.ones(n, np.float32)
            g[max(0, qa):max(0, qb)] = QUIET_GAIN
            g[max(0, qa - ramp):max(0, qa)] = np.linspace(1, QUIET_GAIN, max(0, qa) - max(0, qa - ramp))
            g[max(0, qb):min(n, qb + ramp)] = np.linspace(QUIET_GAIN, 1, min(n, qb + ramp) - max(0, qb))
            env *= g
        _place(buf, x * env[:, None], s["start"], MUSIC_GAIN * (0.75 + 0.5 * INTENSITY.get(s["act"], 0.4)))  # low quieter, climb fuller
    files = sounds.write_all(work / "sfx", {c["sound"] for c in cues})
    loaded = {k: _capped(decode(p)) for k, p in files.items()}
    for c in cues:
        _place(buf, loaded[c["sound"]], c["at"], 0.9 * float(c.get("volume", 1)), c.get("length"))
    said = []
    if whispers:
        lines = [(sh["start"] + 0.15, sh["whisper"]["text"]) for sh in props["shots"] if sh.get("whisper")]
        said = _whispers(lines, work, progress)
        for at, path in said:
            _place(buf, decode(path), at, 0.75)
    peak = float(np.abs(buf).max() or 1)
    buf = buf / peak * 0.89 if peak > 0.89 else buf
    pcm = (np.clip(buf, -1, 1) * 32767).astype(np.int16)
    import wave
    with wave.open(str(out), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    ai = [i for i, p in tracks.items() if p.name.endswith("-ai.wav")]
    return {"music": f"AI music for {len(ai)} of {len(sections)} acts, composed for the rest" if ai else
            f"composed, one track per act ({', '.join(s['mood'] for s in sections)})",
            "sound_cues": len(cues), "whispers": len(said)}
