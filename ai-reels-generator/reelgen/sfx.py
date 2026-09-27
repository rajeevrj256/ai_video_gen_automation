"""Short sound effects for the edit, synthesised on the fly so there are no audio
files to ship or license.

- whoosh: a soft swell of filtered air (flash transition and the hook title).
- impact: a short low boom (zoom transition).
- swish: a fast, bright air swipe (slide transition).
- glitch: a digital stutter of clicks and noise bursts (glitch transition).
- shimmer: a soft rising chime (fade transition).
- pop: a quick, rounded blip for when a graphic lands.

Neither has leading silence: sound starts on the first sample, so each hit lands
exactly on the frame it's placed at.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

RATE = 44100


def _write(path: Path, samples: np.ndarray, peak: float = 0.5) -> Path:
    samples = samples / (np.abs(samples).max() or 1.0) * peak  # peak at -6 dBFS: no clipping
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes((samples * 32767).astype(np.int16).tobytes())
    return path


def _whoosh(duration: float = 0.42, peak_at: float = 0.25) -> np.ndarray:
    n = int(RATE * duration)
    x = np.arange(n) / n
    noise = np.random.default_rng(7).standard_normal(n)
    # A low-pass filter that opens up and closes again: air rushing past.
    cutoff = 250 + 3200 * np.sin(np.pi * x) ** 2
    alpha = 1 - np.exp(-2 * np.pi * cutoff / RATE)
    out = np.empty(n)
    y = 0.0
    for i in range(n):
        y += alpha[i] * (noise[i] - y)
        out[i] = y
    # Starts audible (no dead air before the swell), peaks at `peak_at`, then trails off.
    envelope = np.where(x < peak_at, 0.15 + 0.85 * (x / peak_at) ** 1.5, np.exp(-(x - peak_at) * 7))
    return out * envelope


def _pop(duration: float = 0.12) -> np.ndarray:
    t = np.arange(int(RATE * duration)) / RATE
    freq = 600 + 800 * np.exp(-t * 60)  # quick downward pitch bend
    tone = np.sin(2 * np.pi * np.cumsum(freq) / RATE)
    envelope = np.minimum(t / 0.002, 1) * np.exp(-t * 38)
    return tone * envelope


def _impact(duration: float = 0.55) -> np.ndarray:
    t = np.arange(int(RATE * duration)) / RATE
    freq = 45 + 110 * np.exp(-t * 18)  # a thump that drops in pitch
    body = np.sin(2 * np.pi * np.cumsum(freq) / RATE) * np.exp(-t * 7)
    click = np.random.default_rng(3).standard_normal(len(t)) * np.exp(-t * 90) * 0.35  # the attack
    return (body + click) * np.minimum(t / 0.001, 1)


def _swish(duration: float = 0.22) -> np.ndarray:
    # A whoosh squeezed shorter and brighter: a camera whip rather than air.
    n = int(RATE * duration)
    x = np.arange(n) / n
    noise = np.random.default_rng(11).standard_normal(n)
    cutoff = 1200 + 6500 * np.sin(np.pi * x) ** 2
    alpha = 1 - np.exp(-2 * np.pi * cutoff / RATE)
    out = np.empty(n)
    y = 0.0
    for i in range(n):
        y += alpha[i] * (noise[i] - y)
        out[i] = y
    return out * np.sin(np.pi * x) ** 0.7


def _glitch(duration: float = 0.3) -> np.ndarray:
    rng = np.random.default_rng(5)
    n = int(RATE * duration)
    out = np.zeros(n)
    pos = 0
    while pos < n:  # alternating bursts of crushed noise, square tone and silence
        length = int(RATE * rng.uniform(0.012, 0.04))
        kind = rng.integers(0, 3)
        seg = np.arange(min(length, n - pos))
        if kind == 0:
            out[pos:pos + len(seg)] = np.round(rng.standard_normal(len(seg)) * 3) / 3
        elif kind == 1:
            out[pos:pos + len(seg)] = np.sign(np.sin(2 * np.pi * rng.uniform(300, 1400) * seg / RATE)) * 0.6
        pos += length
    return out * np.linspace(1, 0.4, n)


def _shimmer(duration: float = 0.7) -> np.ndarray:
    t = np.arange(int(RATE * duration)) / RATE
    tone = np.zeros_like(t)
    for k, f in enumerate((880, 1320, 1760, 2640)):  # a soft chord that blooms in, one note at a time
        onset = k * 0.05
        env = np.clip((t - onset) / 0.04, 0, 1) * np.exp(-np.clip(t - onset, 0, None) * 5)
        tone += np.sin(2 * np.pi * f * t) * env / (k + 1)
    return tone


def _sad(notes: tuple[float, ...] = (392.0, 370.0, 349.2, 329.6)) -> np.ndarray:
    """"Wah wah wah waaah": four falling brassy notes, the last one long and wobbling."""
    out = []
    for i, f0 in enumerate(notes):
        dur = 0.34 if i < len(notes) - 1 else 1.1
        t = np.arange(int(RATE * dur)) / RATE
        wobble = 1 + (0.012 * np.sin(2 * np.pi * 6 * t) if i == len(notes) - 1 else 0)
        phase = 2 * np.pi * np.cumsum(f0 * wobble) / RATE
        tone = sum(np.sin(k * phase) / k for k in range(1, 6))  # brassy: a few harmonics
        env = np.minimum(1, t / 0.03) * np.minimum(1, (dur - t) / 0.08)
        out.append(tone * env)
    return np.concatenate(out)


def write_sfx(out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    return {
        "whoosh": _write(out_dir / "whoosh.wav", _whoosh()),
        "impact": _write(out_dir / "impact.wav", _impact(), peak=0.6),
        "swish": _write(out_dir / "swish.wav", _swish(), peak=0.45),
        "glitch": _write(out_dir / "glitch.wav", _glitch(), peak=0.35),
        "shimmer": _write(out_dir / "shimmer.wav", _shimmer(), peak=0.3),
        "pop": _write(out_dir / "pop.wav", _pop(), peak=0.45),
        "sad": _write(out_dir / "sad.wav", _sad(), peak=0.4),
    }
