"""The low-poly films' soundtrack, mixed in numpy from the timeline: the narration on its frames, quiet piano under
it (AI music when the engine is installed, else composed in the story's mood), stepping back while he speaks, and
the world's sounds (synthesised, reelgen/sticky/sounds.py). The finished video is mastered to -14 LUFS by the
render (reelgen/audio.py)."""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

from ..sticky import sounds
from ..sticky.mixdown import RATE, _capped, _place, _tracks, decode

MUSIC_RMS = 0.055  # between lines (the voice is levelled to -16 LUFS, ~0.14 RMS): about 8 dB under it
DUCK = 0.45  # the music under a spoken line (about 15 dB under the voice)
EFFECT_GAIN = 0.85
GENRE = "piano-minimal"  # the original's sound: soft felt piano


def _speech_gate(voice: np.ndarray) -> np.ndarray:
    """1 where the narrator is silent, 0 under a line, with 0.25 s ramps (10 ms blocks)."""
    block = RATE // 100
    n = len(voice) // block
    on = (np.abs(voice[: n * block]).reshape(n, block, 2).max(axis=(1, 2)) > 0.01).astype(np.float32)
    hold = np.convolve(on, np.ones(40), mode="same") > 0  # bridge the gaps between words
    ramp = np.convolve(hold.astype(np.float32), np.ones(25) / 25, mode="same")
    g = np.repeat(1 - np.clip(ramp, 0, 1), block)
    return np.concatenate([g, np.ones(len(voice) - len(g), np.float32)]).astype(np.float32)


def mix(cfg, props: dict, clips: list[dict], cues: list[dict], sections: list[dict], work: Path, out: Path, seed: int,
        progress, brief: str) -> dict:
    total = float(props["duration"]) + 0.5
    n = int(total * RATE)
    music = np.zeros((n, 2), np.float32)
    voice = np.zeros_like(music)
    fx = np.zeros_like(music)
    for c in clips:
        _place(voice, decode(Path(c["path"])), float(c["at"]), 1.0)
    tracks, genre = _tracks(cfg, sections, work, seed, progress, GENRE, brief)
    for i, s in enumerate(sections):
        x = decode(tracks[i], "highpass=f=60")
        loud = x[np.abs(x).max(axis=1) > 0.01] if len(x) else x
        if len(loud):
            x = x * min(4.0, MUSIC_RMS / max(1e-6, float(np.sqrt((loud ** 2).mean()))))
        length = s["end"] - s["start"] + (1.5 if i < len(sections) - 1 else 0.4)
        x = np.tile(x, (int(length * RATE) // max(1, len(x)) + 1, 1))[: int(length * RATE)]
        env = np.ones(len(x), np.float32)
        fin, fout = int((1.2 if i else 0.6) * RATE), int(1.6 * RATE)
        env[: min(fin, len(x))] *= np.linspace(0, 1, min(fin, len(x)))
        env[-min(fout, len(x)):] *= np.linspace(1, 0, min(fout, len(x)))
        _place(music, x * env[:, None], s["start"], 1.0)
    files = sounds.write_all(work / "sfx", {c["sound"] for c in cues})
    loaded = {k: _capped(decode(p)) for k, p in files.items()}
    for c in cues:
        _place(fx, loaded[c["sound"]], float(c["at"]), EFFECT_GAIN * float(c.get("volume", 1)), c.get("length"))
    gate = _speech_gate(voice)
    buf = music * (DUCK + (1 - DUCK) * gate)[:, None] + fx * (0.7 + 0.3 * gate)[:, None] + voice
    peak = float(np.abs(buf).max() or 1)
    if peak > 0.95:
        buf = buf / peak * 0.95
    pcm = (np.clip(buf, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    ai = [i for i, p in tracks.items() if p.name.endswith("-ai.wav")]
    return {"music": (f"AI music ({genre}) for {len(ai)} of {len(sections)} parts" if ai else
                      f"composed ({', '.join(s['mood'] for s in sections)})"), "sound_cues": len(cues), "genre": genre}
