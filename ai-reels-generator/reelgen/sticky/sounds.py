"""The Sticky films' sounds, synthesised (no files to license): the world's own sounds on every action and the
feeling's stingers (ANALYSIS.md: phone dings and notification tones, typing, knocks, steps, the alarm, a heartbeat at
the realisation, a chime or bell when something good lands, a rumble under the inner voice, static on a slip).
The existing effects in reelgen/sfx.py are reused as they are (read only); the rest are made here. No boom and no
riser: the user's standing rule."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .. import sfx
from ..sfx import RATE, _lowpass, _write


def _t(seconds: float) -> np.ndarray:
    return np.arange(int(RATE * seconds)) / RATE


def _notify() -> np.ndarray:
    """Two soft marimba notes up: a message, a like, a notification."""
    t = _t(0.55)
    out = np.zeros_like(t)
    for at, f in ((0.0, 1046.5), (0.11, 1568.0)):
        u = np.clip(t - at, 0, None)
        out += (np.sin(2 * np.pi * f * u) + 0.3 * np.sin(2 * np.pi * f * 4 * u)) * np.exp(-u * 14) * (t >= at)
    return out


def _buzz() -> np.ndarray:
    """A phone vibrating on a table: two short rattles."""
    t = _t(1.0)
    gate = ((t % 0.5) < 0.32).astype(float)
    tone = np.sign(np.sin(2 * np.pi * 172 * t)) * 0.6 + np.sin(2 * np.pi * 344 * t) * 0.3
    return _lowpass(tone * gate, 900)


def _tap() -> np.ndarray:
    """A fingertip on glass, or paper on a wall."""
    t = _t(0.08)
    return np.random.default_rng(3).standard_normal(len(t)) * np.exp(-t * 120) * 0.6 + np.sin(2 * np.pi * 1800 * t) * np.exp(-t * 200)


def _send() -> np.ndarray:
    """The message-sent swoosh: a short upward air."""
    t = _t(0.28)
    x = t / 0.28
    noise = np.random.default_rng(5).standard_normal(len(t))
    return _lowpass(noise, 800 + 3000 * x) * np.sin(np.pi * x) ** 2


def _knock() -> np.ndarray:
    """Three knocks on a wooden door."""
    t = _t(0.9)
    out = np.zeros_like(t)
    for at in (0.0, 0.18, 0.36):
        u = np.clip(t - at, 0, None)
        out += (np.sin(2 * np.pi * 180 * u) + 0.5 * np.sin(2 * np.pi * 410 * u)) * np.exp(-u * 40) * (t >= at)
        out += _lowpass(np.random.default_rng(int(at * 100)).standard_normal(len(t)), 1500) * np.exp(-u * 90) * (t >= at) * 0.4
    return out


def _door() -> np.ndarray:
    """A door: a short creak and a soft close."""
    t = _t(1.1)
    creak = np.sin(2 * np.pi * np.cumsum(300 + 120 * np.sin(2 * np.pi * 3 * t)) / RATE) * (t < 0.6) * np.sin(np.pi * np.clip(t / 0.6, 0, 1))
    u = np.clip(t - 0.75, 0, None)
    close = np.sin(2 * np.pi * 90 * u) * np.exp(-u * 18) * (t >= 0.75)
    return _lowpass(creak, 1400) * 0.35 + close


def _alarm() -> np.ndarray:
    """An alarm clock: beep-beep, beep-beep."""
    t = _t(1.6)
    gate = (((t % 0.4) < 0.09) | (((t - 0.14) % 0.4) < 0.09) & (t > 0.14)).astype(float)
    return np.sign(np.sin(2 * np.pi * 2900 * t)) * 0.4 * gate


def _bell() -> np.ndarray:
    """A soft bell: something good lands, a new day."""
    t = _t(2.4)
    return sum(np.sin(2 * np.pi * f * t) * a * np.exp(-t * d) for f, a, d in ((523.3, 1, 1.4), (1046.5, 0.5, 2), (1567.0, 0.25, 3), (2637, 0.12, 4)))


def _chime() -> np.ndarray:
    """A light rising chime: hope, a realisation, the voice dissolving."""
    t = _t(1.6)
    out = np.zeros_like(t)
    for k, f in enumerate((1318.5, 1568.0, 1975.5, 2637.0)):
        u = np.clip(t - k * 0.09, 0, None)
        out += np.sin(2 * np.pi * f * u) * np.exp(-u * 3.5) * (t >= k * 0.09)
    return out


def _static() -> np.ndarray:
    """A burst of static: a glitch in him, a relapse."""
    t = _t(0.6)
    noise = np.random.default_rng(9).standard_normal(len(t))
    gate = (np.random.default_rng(10).random(len(t) // 400 + 1) > 0.35).repeat(400)[: len(t)]
    return (noise - _lowpass(noise, 1200)) * gate * np.sin(np.pi * t / 0.6)


def _scribble() -> np.ndarray:
    """A marker ticking a box on the calendar."""
    t = _t(0.35)
    noise = np.random.default_rng(12).standard_normal(len(t))
    band = _lowpass(noise, 4500) - _lowpass(noise, 1500)
    return band * (0.6 + 0.4 * np.sin(2 * np.pi * 18 * t)) * np.sin(np.pi * t / 0.35)


def _page() -> np.ndarray:
    """Paper: a drawing held up, a page turned."""
    t = _t(0.45)
    noise = np.random.default_rng(13).standard_normal(len(t))
    return (_lowpass(noise, 3500) - _lowpass(noise, 600)) * np.sin(np.pi * t / 0.45) ** 1.5


def _rain() -> np.ndarray:
    """Rain on a window: a bed for a whole shot (looped)."""
    t = _t(4.0)
    noise = np.random.default_rng(14).standard_normal(len(t))
    drops = np.zeros_like(t)
    rng = np.random.default_rng(15)
    for at in rng.uniform(0, 4, 90):
        u = np.clip(t - at, 0, None)
        drops += np.sin(2 * np.pi * rng.uniform(2500, 5000) * u) * np.exp(-u * 300) * (t >= at) * 0.3
    return _lowpass(noise, 2500) * 0.35 + drops


def _cheer() -> np.ndarray:
    """A small room clapping and cheering softly."""
    t = _t(2.5)
    rng = np.random.default_rng(16)
    out = np.zeros_like(t)
    for at in rng.uniform(0, 2.3, 140):
        u = np.clip(t - at, 0, None)
        out += rng.standard_normal(len(t)) * np.exp(-u * 160) * (t >= at) * rng.uniform(0.3, 1)
    return _lowpass(out, 3000) * np.minimum(t / 0.3, 1) * np.minimum((2.5 - t) / 0.8, 1)


def _thud() -> np.ndarray:
    """Something soft hitting the floor (a phone face-down, a bag dropped)."""
    t = _t(0.35)
    return np.sin(2 * np.pi * np.cumsum(140 * np.exp(-t * 8) + 60) / RATE) * np.exp(-t * 14)


MAKERS = {
    "ding": (sfx._ding, 0.45), "notify": (_notify, 0.4), "buzz": (_buzz, 0.4), "typing": (lambda: sfx._typing(2.0), 0.3),
    "tap": (_tap, 0.35), "send": (_send, 0.35), "knock": (_knock, 0.55), "door": (_door, 0.45),
    "footsteps": (lambda: sfx._footsteps(2.0, 0.42), 0.35), "alarm": (_alarm, 0.4), "heartbeat": (lambda: sfx._heartbeat(1.1), 0.6),
    "rumble": (lambda: sfx._rumble(2.2), 0.45), "static": (_static, 0.3), "chime": (_chime, 0.35), "bell": (_bell, 0.4),
    "pop": (sfx._pop, 0.35), "swoosh": (sfx._whoosh, 0.3), "scribble": (_scribble, 0.35), "tick": (lambda: sfx._tick(2.0), 0.35),
    "page": (_page, 0.35), "coins": (sfx._cash, 0.4), "rain": (_rain, 0.3), "cheer": (_cheer, 0.4), "thud": (_thud, 0.5),
}
LOOPED = {"footsteps", "typing", "rain", "tick", "heartbeat"}  # played for the whole span they're given


def write_all(out_dir: Path, names: set[str]) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    made = {}
    for name in sorted(names):
        make, peak = MAKERS[name]
        path = out_dir / f"{name}.wav"
        if not path.exists():
            _write(path, make(), peak)
        made[name] = path
    return made
