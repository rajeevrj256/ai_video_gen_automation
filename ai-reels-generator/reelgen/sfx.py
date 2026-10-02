"""Short sound effects for the edit, synthesised on the fly so there are no audio
files to ship or license.

- whoosh: a soft swell of filtered air (flash transition and the hook title).
- impact: a short low thud (zoom transition).
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


# ---- Sounds for sentence-level sound design (chosen per line by the script writer) ----

def _lowpass(x: np.ndarray, cutoff) -> np.ndarray:
    alpha = 1 - np.exp(-2 * np.pi * np.broadcast_to(cutoff, x.shape) / RATE)
    out = np.empty_like(x)
    y = 0.0
    for i in range(len(x)):
        y += alpha[i] * (x[i] - y)
        out[i] = y
    return out


def _sword(duration: float = 0.9) -> np.ndarray:
    """A blade drawn fast: a bright air slash, then a metallic ring that dies away."""
    t = np.arange(int(RATE * duration)) / RATE
    noise = np.random.default_rng(11).standard_normal(len(t))
    slash = (noise - _lowpass(noise, 2500)) * np.exp(-((t - 0.07) / 0.05) ** 2)
    ring = sum(np.sin(2 * np.pi * f * t) * a for f, a in ((1320, 1), (2710, 0.6), (4180, 0.35), (5930, 0.2)))
    ring *= np.clip((t - 0.06) / 0.01, 0, 1) * np.exp(-np.clip(t - 0.06, 0, None) * 5)
    return slash * 1.4 + ring * 0.5


def _riser(duration: float = 1.8) -> np.ndarray:
    """Tension building into a line: filtered noise and a tone both climbing, ending loud."""
    t = np.arange(int(RATE * duration)) / RATE
    x = t / duration
    noise = _lowpass(np.random.default_rng(5).standard_normal(len(t)), 300 + 6000 * x ** 2)
    tone = np.sin(2 * np.pi * np.cumsum(110 + 440 * x ** 2) / RATE)
    return (noise + tone * 0.5) * x ** 2.2



def _heartbeat(duration: float = 1.1) -> np.ndarray:
    """Lub-dub, once."""
    t = np.arange(int(RATE * duration)) / RATE
    def thump(at, gain):
        u = np.clip(t - at, 0, None)
        return np.sin(2 * np.pi * np.cumsum(50 + 40 * np.exp(-u * 30)) / RATE) * np.exp(-u * 16) * (t >= at) * gain
    return thump(0.0, 1.0) + thump(0.26, 0.75)


def _tick(duration: float = 2.0) -> np.ndarray:
    """A clock ticking four times: time running out."""
    t = np.arange(int(RATE * duration)) / RATE
    out = np.zeros_like(t)
    for k in range(4):
        u = np.clip(t - k * 0.5, 0, None)
        out += np.sin(2 * np.pi * (3200 if k % 2 else 2600) * u) * np.exp(-u * 260) * (t >= k * 0.5)
    return out



def _cash(duration: float = 0.9) -> np.ndarray:
    """Coins and a till bell: money."""
    t = np.arange(int(RATE * duration)) / RATE
    bell = sum(np.sin(2 * np.pi * f * t) * a for f, a in ((2093, 1), (2637, 0.7), (3136, 0.5))) * np.exp(-t * 6)
    coins = np.zeros_like(t)
    for k, at in enumerate((0.0, 0.05, 0.11, 0.16)):
        u = np.clip(t - at, 0, None)
        coins += np.sin(2 * np.pi * (5200 + 400 * k) * u) * np.exp(-u * 80) * (t >= at)
    return bell * 0.6 + coins * 0.5


def _drone(duration: float = 3.0) -> np.ndarray:
    """A low, uneasy pad for mystery lines; fades in and out."""
    t = np.arange(int(RATE * duration)) / RATE
    pad = sum(np.sin(2 * np.pi * f * t + np.sin(2 * np.pi * 0.3 * t) * k) for k, f in enumerate((55, 82.4, 116.5)))
    env = np.minimum(t / 0.8, 1) * np.minimum((duration - t) / 0.8, 1)
    return pad * env


def _ding(duration: float = 0.6) -> np.ndarray:
    """A clean notification ding: a fact landing."""
    t = np.arange(int(RATE * duration)) / RATE
    return (np.sin(2 * np.pi * 1568 * t) + 0.4 * np.sin(2 * np.pi * 3136 * t)) * np.exp(-t * 7) * np.minimum(t / 0.003, 1)


def _typing(duration: float = 1.2) -> np.ndarray:
    """Keyboard clicks: someone writing, searching, messaging."""
    t = np.arange(int(RATE * duration)) / RATE
    out = np.zeros_like(t)
    rng = np.random.default_rng(4)
    at = 0.0
    while at < duration - 0.05:
        u = np.clip(t - at, 0, None)
        out += rng.standard_normal(len(t)) * np.exp(-u * 400) * (t >= at) * rng.uniform(0.5, 1)
        at += rng.uniform(0.07, 0.16)
    return out


def _click(duration: float = 0.05) -> np.ndarray:
    """A crisp UI click: text landing, a counter ticking."""
    t = np.arange(int(RATE * duration)) / RATE
    return (np.sin(2 * np.pi * 2600 * t) + 0.6 * np.sin(2 * np.pi * 5200 * t)) * np.exp(-t * 160)



def _rumble(duration: float = 1.2) -> np.ndarray:
    """A low trembling rumble: something shaking, fear, a building threat."""
    t = np.arange(int(RATE * duration)) / RATE
    noise = _lowpass(np.random.default_rng(22).standard_normal(len(t)), 120)
    return noise * (0.6 + 0.4 * np.sin(2 * np.pi * 9 * t)) * np.sin(np.pi * t / duration)


def _flyby(duration: float = 1.6) -> np.ndarray:
    """Something passing the camera: a swelling then fading rush with a falling pitch."""
    t = np.arange(int(RATE * duration)) / RATE
    x = t / duration
    noise = np.random.default_rng(23).standard_normal(len(t))
    tone = np.sin(2 * np.pi * np.cumsum(220 - 90 * x) / RATE) * 0.4
    return (_lowpass(noise, 600 + 1800 * np.sin(np.pi * x)) + tone) * np.sin(np.pi * x) ** 2


# name -> (make, peak, seconds the sound should lead its word by, what it's for)
# boom, hit and rise were deleted at the user's request (they sounded bad on every video).
CUE_SOUNDS = {
    "sword": (_sword, 0.5, 0.05, "blade slash with a metallic ring: a sharp reveal, a cut, a decisive moment"),
    "riser": (_riser, 0.35, 1.7, "tension rising INTO the word it's placed on: builds up to a reveal"),
    "heartbeat": (_heartbeat, 0.55, 0.0, "a heartbeat: suspense, fear, a life-or-death moment"),
    "tick": (_tick, 0.3, 0.0, "a clock ticking: deadlines, time running out, countdowns"),
    "cash": (_cash, 0.35, 0.0, "coins and a till bell: money, prices, profit"),
    "drone": (_drone, 0.22, 0.0, "low uneasy pad under a line: mystery, something is off"),
    "ding": (_ding, 0.3, 0.0, "clean ding: a fact or idea landing, a lightbulb moment"),
    "typing": (_typing, 0.25, 0.0, "keyboard clicks: searching, messaging, hacking, writing"),
    "click": (_click, 0.3, 0.0, "a crisp click: text or a counter landing"),
    "rumble": (_rumble, 0.5, 0.0, "a low rumble: shaking, a threat, fear"),
    "flyby": (_flyby, 0.4, 0.5, "something rushing past the camera: a plane, a car, a crowd"),
}


def write_cue_sounds(out_dir: Path, names: set[str]) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    return {n: _write(out_dir / f"{n}.wav", CUE_SOUNDS[n][0](), peak=CUE_SOUNDS[n][1]) for n in names if n in CUE_SOUNDS}


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
