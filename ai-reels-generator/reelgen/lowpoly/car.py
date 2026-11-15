"""Real car sound for the low-poly films (the user: "car sound not good, must be real car sound. i added car sound,
acceleration sound, analyse acc to speed how car generated speed, brakes, slide sound while emergency brake, drift
sounds").

The engine is the user's own recording (car/engine-run.ogg, 27.6 s: a full-throttle run through five gears from idle to
about 210 km/h, then a lift-off; its revs read off the tachometer in its video every second, RPM below). A car's engine
in a shot follows that car's speed in the shot (Big.tsx `profile` keys, mirrored in `speed_keys`): a six-speed
gearbox turns the speed into revs (up a gear at `UP`, down at `DOWN`), and every 40 ms of the output takes 90 ms of the
recording from the moment it was at those revs, on the throttle while the car holds or gains speed and from the
lift-off while it slows, pitched the last bit to match (granular playback). So a race climbs through the gears, a
braking car's revs fall away, a jump's wheels spin up in the air, and no two shots repeat a loop. The recording has no
tyres in it: the squeal of an emergency stop, a drift and a spin is made here (`squeal`).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np

from ..sfx import RATE, _lowpass

RECORDING = Path(__file__).with_name("car") / "engine-run.ogg"
# the tachometer (thousands of rpm) through the recording, second by second, with the four shifts and the lift-off
RPM = [(0.0, 1.0), (1.0, 2.0), (2.0, 3.2), (3.0, 6.0), (4.0, 6.8), (4.55, 7.1), (4.6, 4.0), (5.0, 4.2), (6.0, 6.0),
       (7.0, 7.6), (8.0, 7.8), (8.45, 8.0), (8.5, 6.3), (9.0, 6.4), (10.0, 6.6), (11.0, 7.0), (12.0, 7.6), (13.0, 8.0),
       (14.0, 8.5), (15.15, 8.7), (15.2, 6.6), (16.0, 6.5), (20.0, 6.8), (22.0, 7.5), (24.0, 8.0), (25.35, 8.4),
       (25.4, 7.8), (26.5, 7.6), (26.9, 4.6), (27.6, 4.3)]
ON = [(0.15, 2.1), (2.2, 4.45), (5.05, 8.35), (8.65, 15.05), (15.35, 25.25)]  # on the throttle, clear of the shifts
OFF = (26.95, 27.5)  # off the throttle, the revs falling
TOP = [55, 92, 128, 163, 200, 240]  # km/h at UP thousand rpm in each gear
UP, DOWN, IDLE = 7.4, 3.3, 1.05
GRAIN, HOP = 0.09, 0.04  # seconds
JUMP_TIME = 1.25  # = Big.tsx jump's time in the air (timeline.JUMP_TIME)


@lru_cache(maxsize=1)
def _source() -> np.ndarray | None:
    if not RECORDING.exists():
        return None
    from ..sticky.mixdown import decode

    x = decode(RECORDING).mean(axis=1)
    return x / (np.abs(x).max() or 1)


def _rpm_at(pos: np.ndarray) -> np.ndarray:
    t, r = zip(*RPM)
    return np.interp(pos, t, r)


@lru_cache(maxsize=1)
def _bank() -> tuple[np.ndarray, np.ndarray]:
    """Every 10 ms of the recording on the throttle, and its revs."""
    pos = np.concatenate([np.arange(a + GRAIN, b - GRAIN, 0.01) for a, b in ON])
    return pos, _rpm_at(pos)


def speed_keys(motion: str, at: float, dur: float) -> list[tuple[float, float]]:
    """A vehicle's speed (m/s) over action seconds, as Big.tsx `profile` moves it."""
    return {
        "race": [(0, 15), (0.75, 16), (2.35, 33), (max(2.6, dur), 36)],
        "drift": [(0, 23), (at, 23), (at + 0.6, 17)],
        "spin": [(0, 21), (at, 21), (at + 1.1, 8), (at + 2.2, 14)],
        "reverse": [(0, 9)],
        "jump": [(0, 24)],
        "stop": [(0, 22), (at, 22), (at + 1.0, 0)],
        "drive": [(0, 13)],
    }.get(motion, [(0, 13)])


def revs(motion: str, at: float, dur: float, slow: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """The engine's revs (thousands) and whether the throttle is open, every HOP seconds of the shot."""
    keys = speed_keys(motion, at, dur * slow)
    kt, kv = zip(*keys)
    t = np.arange(0, dur + HOP, HOP) * slow  # action time
    v = np.interp(t, kt, kv) * 3.6
    gain = np.gradient(v, t) if len(t) > 1 else np.zeros_like(t)
    g = next((i for i, top in enumerate(TOP) if v[0] < top * 0.8), len(TOP) - 1)
    out = np.zeros_like(v)
    for i, kmh in enumerate(v):
        r = kmh / TOP[g] * UP
        if r > UP and g < len(TOP) - 1:
            g += 1
        elif r < DOWN and g > 0:
            g -= 1
        out[i] = max(IDLE + 0.15 * (kmh > 2), kmh / TOP[g] * UP)
    if motion == "jump":  # off the ground the wheels spin free: the revs flare, then bite again on landing
        air = (t > at) & (t < at + JUMP_TIME)
        out[air] *= 1.18
    if motion in ("drift", "spin"):  # the tail out, the wheels spinning: a flare of revs through the slide
        slide = (t > at) & (t < at + 1.2)
        out[slide] *= 1.12
    # braking hard (more than ~4 km/h a second off): off the throttle; through a drift or a spin his foot stays down
    throttle = (gain > -4) | (motion in ("drift", "spin"))
    return out, throttle


def engine(motion: str, at: float, dur: float, slow: float = 1.0, seed: int = 1) -> np.ndarray | None:
    """The car's engine through a shot of `dur` seconds (None without the recording)."""
    src = _source()
    if src is None:
        return None
    rpm, on = revs(motion, at, dur, slow)
    pos_bank, rpm_bank = _bank()
    rng = np.random.default_rng(seed)
    n = int(GRAIN * RATE)
    win = np.hanning(n)
    out = np.zeros(int((dur + GRAIN) * RATE))
    norm = np.zeros_like(out)
    prev = None
    for i, (r, open_) in enumerate(zip(rpm, on)):
        if open_:
            want = (prev + HOP) if prev is not None else None
            cost = np.abs(rpm_bank - r) * 4 + (np.abs(pos_bank - want) * 0.6 if want is not None else 0)
            near = np.argsort(cost)[:4]
            pos = float(pos_bank[near[int(rng.integers(len(near)))]])
        else:  # easing off: the recording's lift-off, the revs falling
            pos = OFF[0] + GRAIN + (i * HOP) % (OFF[1] - OFF[0] - 2 * GRAIN)
        prev = pos
        ratio = float(np.clip(r / float(_rpm_at(np.array([pos]))[0]), 0.55, 1.7))
        span = int(n * ratio)
        a = int(pos * RATE) - span // 2
        if a < 0 or a + span >= len(src):
            continue
        raw = src[a:a + span]
        # every grain at one loudness first (the recording idles ~6 dB louder than it pulls at speed), then the
        # throttle's own level
        grain = np.interp(np.linspace(0, span - 1, n), np.arange(span), raw) / (np.sqrt(np.mean(raw ** 2)) + 1e-4) * 0.25 * win
        k = int(i * HOP * RATE)
        m = min(n, len(out) - k)
        if m <= 0:
            break
        level = (1.0 if open_ else 0.55) * (0.75 + 0.25 * min(1.0, r / 7.0))  # louder as it revs
        if r < 1.6:
            level *= 0.55  # idling
        out[k:k + m] += grain[:m] * level
        norm[k:k + m] += win[:m]
    out = out / np.maximum(norm, 0.5)
    out = out[: int(dur * RATE)]
    fade = min(len(out) // 4, int(0.06 * RATE))
    if fade:
        out[:fade] *= np.linspace(0, 1, fade)
        out[-fade:] *= np.linspace(1, 0, fade)
    return out / (np.abs(out).max() or 1) * 0.9


def rev() -> np.ndarray | None:
    """The foot slammed on the accelerator (the pedal cut-in): the recording's first gear pulling hard, 1.3 s."""
    src = _source()
    if src is None:
        return None
    x = src[int(2.3 * RATE): int(3.6 * RATE)].copy()
    x[: int(0.03 * RATE)] *= np.linspace(0, 1, int(0.03 * RATE))
    x[-int(0.35 * RATE):] *= np.linspace(1, 0, int(0.35 * RATE))
    return x / (np.abs(x).max() or 1)


def squeal(length: float, kind: str = "brake", seed: int = 1) -> np.ndarray:
    """Tyres screeching: a tonal squeal (rubber stick-slip) with its overtones wavering, rough noise of the scrub under
    it, and a chatter. An emergency stop starts high and sinks as the car slows; a drift wails and warbles longer; a
    spin swoops."""
    length = max(0.3, length)
    t = np.arange(int(length * RATE)) / RATE
    rng = np.random.default_rng(seed)
    drift = _lowpass(rng.standard_normal(len(t)), 3) * 25  # slow random wander
    base = {"brake": 1250.0, "drift": 1050.0, "spin": 980.0}.get(kind, 1150.0)
    if kind == "brake":
        f0 = base * (1 - 0.28 * t / length)
    elif kind == "spin":
        f0 = base * (1 + 0.22 * np.sin(np.pi * t / length))
    else:
        f0 = base * (1 + 0.06 * np.sin(2 * np.pi * 1.7 * t))
    f0 = f0 * (1 + 0.04 * drift / (np.abs(drift).max() or 1))
    ph = 2 * np.pi * np.cumsum(f0) / RATE
    tone = np.sin(ph) + 0.45 * np.sin(2 * ph + 0.7) + 0.2 * np.sin(3 * ph + 1.3)
    scrub = rng.standard_normal(len(t))
    scrub = _lowpass(scrub, 3800) - _lowpass(scrub, 650)
    chatter = 1 + 0.35 * _lowpass(rng.standard_normal(len(t)), 18) / 0.2
    env = np.minimum(t / 0.035, 1) * np.minimum((length - t) / min(0.3, length / 3), 1)
    if kind == "brake":
        env *= 1 - 0.35 * t / length  # the squeal fades as the car stops
    x = (tone * 0.5 + scrub * 0.55) * np.clip(chatter, 0.4, 1.6) * env
    return x / (np.abs(x).max() or 1) * 0.9
