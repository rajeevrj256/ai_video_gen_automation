"""The low-poly films' sounds: the Sticky films' synthesised ones (reelgen/sticky/sounds.py, read only) plus what action
and fiction need, made here the same way (no files to license): a heavy impact, a metal crash, breaking glass, the
ground cracking, straining metal, a tyre skid, a siren, wind, fire, sparks, a fly-by and a frightened crowd. No boom
and no riser (the user's standing rule): the weight comes from the impact, the crash and a short rumble."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .. import sfx
from ..sfx import RATE, _lowpass, _write
from ..sticky import sounds as sticky


def _t(seconds: float) -> np.ndarray:
    return np.arange(int(RATE * seconds)) / RATE


def _noise(seed: int, n: int) -> np.ndarray:
    return np.random.default_rng(seed).standard_normal(n)


def _crash() -> np.ndarray:
    """Metal hitting metal or concrete: a hard noise burst, ringing panels at clashing pitches, a rattle as it settles."""
    t = _t(1.6)
    burst = _lowpass(_noise(31, len(t)), 3500) * np.exp(-t * 9)
    ring = sum(np.sin(2 * np.pi * f * t + k) * np.exp(-t * d) for k, (f, d) in enumerate(((317, 5), (452, 6), (689, 8), (1131, 10), (1873, 13))))
    body = np.sin(2 * np.pi * np.cumsum(70 + 90 * np.exp(-t * 12)) / RATE) * np.exp(-t * 6)
    rng = np.random.default_rng(32)
    rattle = np.zeros_like(t)
    for at in rng.uniform(0.15, 1.2, 40):
        u = np.clip(t - at, 0, None)
        rattle += np.sin(2 * np.pi * rng.uniform(900, 2600) * u) * np.exp(-u * 70) * (t >= at) * rng.uniform(0.1, 0.4)
    return burst * 0.9 + ring * 0.18 + body * 0.8 + rattle * 0.5


def _glass() -> np.ndarray:
    """A window breaking: a bright crack, then shards tinkling down."""
    t = _t(1.8)
    crack = _noise(33, len(t)) * np.exp(-t * 30)
    rng = np.random.default_rng(34)
    tinkle = np.zeros_like(t)
    for at in np.concatenate([rng.uniform(0.02, 0.4, 50), rng.uniform(0.4, 1.5, 40)]):
        u = np.clip(t - at, 0, None)
        f = rng.uniform(3000, 7500)
        tinkle += (np.sin(2 * np.pi * f * u) + 0.5 * np.sin(2 * np.pi * f * 1.47 * u)) * np.exp(-u * rng.uniform(40, 90)) * (t >= at) * rng.uniform(0.15, 0.6)
    return crack * 0.8 + tinkle * 0.6


def _crack() -> np.ndarray:
    """The ground or a cable giving way: a sharp snap and a short crackle of splitting stone."""
    t = _t(0.7)
    snap = _noise(35, len(t)) * np.exp(-t * 60)
    rng = np.random.default_rng(36)
    crackle = np.zeros_like(t)
    for at in np.sort(rng.uniform(0.0, 0.45, 26)):
        u = np.clip(t - at, 0, None)
        crackle += _noise(int(at * 1000) + 37, len(t)) * np.exp(-u * 220) * (t >= at) * rng.uniform(0.2, 0.7)
    low = np.sin(2 * np.pi * np.cumsum(90 + 60 * np.exp(-t * 20)) / RATE) * np.exp(-t * 10)
    return snap + _lowpass(crackle, 2500) * 0.8 + low * 0.5


def _creak() -> np.ndarray:
    """Steel straining under weight: a slow, low, rough groan that bends in pitch."""
    t = _t(1.4)
    f = 70 + 25 * np.sin(2 * np.pi * 0.6 * t) + 12 * np.sin(2 * np.pi * 3.1 * t)
    saw = 2 * ((np.cumsum(f) / RATE) % 1) - 1
    rough = 1 + 0.5 * np.sign(np.sin(2 * np.pi * 23 * t))  # the stick-slip of metal
    return _lowpass(saw * rough, 900) * np.sin(np.pi * t / 1.4) ** 0.7


def _skid() -> np.ndarray:
    """Tyres screeching: a band of noise and a whining tone, sliding down as it slows."""
    t = _t(1.0)
    whine = np.sin(2 * np.pi * np.cumsum(1500 - 500 * t) / RATE) + 0.5 * np.sin(2 * np.pi * np.cumsum(2300 - 700 * t) / RATE)
    hiss = _noise(38, len(t)) - _lowpass(_noise(38, len(t)), 1500)
    env = np.minimum(t / 0.05, 1) * np.minimum((1.0 - t) / 0.15, 1)
    return (whine * 0.4 + hiss * 0.7) * env * (0.8 + 0.2 * np.sin(2 * np.pi * 31 * t))


def _siren() -> np.ndarray:
    """An emergency siren far off: a rising and falling wail, softened by distance (looped)."""
    t = _t(4.0)
    f = 700 + 450 * (0.5 - 0.5 * np.cos(2 * np.pi * t / 2.0))
    tone = np.sin(2 * np.pi * np.cumsum(f) / RATE) + 0.3 * np.sin(2 * np.pi * np.cumsum(2 * f) / RATE)
    return _lowpass(_lowpass(tone, 1400), 1400) * 0.8  # far off: duller


def _loopable(x: np.ndarray, fade: float = 0.4) -> np.ndarray:
    """A bed that loops without a seam: its last `fade` seconds cross-faded into its start."""
    k = int(RATE * fade)
    y = x[:-k].copy()
    ramp = np.linspace(0, 1, k)
    y[:k] = y[:k] * ramp + x[-k:] * (1 - ramp)
    return y


def _wind() -> np.ndarray:
    """Wind: soft air moving past, gusting slowly (looped). The first version was low-passed noise, a low roar that
    covered the dialogue ('hawa sound too noisy'); now the band is airy (350 Hz-1.8 kHz), with no rumble under it."""
    t = _t(8.0)
    gust = 0.5 + 0.3 * np.sin(2 * np.pi * 0.11 * t) + 0.2 * np.sin(2 * np.pi * 0.29 * t + 1.3)
    n = _noise(39, len(t))
    air = n - _lowpass(n, 350)  # nothing under 350 Hz
    return _loopable(_lowpass(air, 700 + 1100 * gust) * (0.3 + 0.7 * gust))


def _fire() -> np.ndarray:
    """A fire burning: a low roar with pops and crackles (looped)."""
    t = _t(4.0)
    roar = _lowpass(_noise(40, len(t)), 350) * (0.8 + 0.2 * np.sin(2 * np.pi * 0.7 * t))
    rng = np.random.default_rng(41)
    pops = np.zeros_like(t)
    for at in rng.uniform(0, 4, 120):
        u = np.clip(t - at, 0, None)
        pops += _noise(int(at * 997) + 42, len(t)) * np.exp(-u * rng.uniform(300, 900)) * (t >= at) * rng.uniform(0.1, 0.6)
    return _loopable(roar * 0.6 + pops * 0.5)


def _sparks() -> np.ndarray:
    """Metal scraping and sparking: a hiss with fizzing crackle (looped)."""
    t = _t(2.0)
    hiss = _noise(43, len(t)) - _lowpass(_noise(43, len(t)), 3000)
    fizz = _noise(44, len(t)) * (np.random.default_rng(45).random(len(t)) < 0.004) * 4
    return hiss * 0.5 * (0.7 + 0.3 * np.sin(2 * np.pi * 17 * t)) + _lowpass(fizz, 6000)


def _crowd() -> np.ndarray:
    """Frightened people nearby: a murmur of many voices, with a few rising cries (vowel-like formants on noise)."""
    t = _t(3.0)
    rng = np.random.default_rng(46)
    out = np.zeros_like(t)
    for k in range(14):
        f0 = rng.uniform(140, 320)
        voice = 2 * ((np.cumsum(f0 * (1 + 0.08 * np.sin(2 * np.pi * rng.uniform(0.5, 2) * t + k))) / RATE) % 1) - 1
        env = np.clip(np.sin(2 * np.pi * rng.uniform(0.3, 0.9) * t + rng.uniform(0, 6)), 0, None) ** 2
        out += _lowpass(voice, rng.uniform(700, 1400)) * env * rng.uniform(0.3, 1)
    return out * np.minimum(t / 0.3, 1) * np.minimum((3.0 - t) / 0.5, 1)


MAKERS = {
    **sticky.MAKERS,
    "impact": (sfx._impact, 0.75), "crash": (_crash, 0.7), "glass": (_glass, 0.5), "crack": (_crack, 0.6), "creak": (_creak, 0.45),
    "skid": (_skid, 0.45), "siren": (_siren, 0.3), "wind": (_wind, 0.35), "fire": (_fire, 0.35), "sparks": (_sparks, 0.35),
    "flyby": (sfx._flyby, 0.6), "crowd": (_crowd, 0.35), "rumble": (lambda: sfx._rumble(1.6), 0.55),
}


# a sound made again since a video was mixed gets a new file name, so a re-mix of an older video picks it up
VERSION = {"wind": 2, "siren": 2, "fire": 2}


def write_all(out_dir: Path, names: set[str]) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    made = {}
    for name in sorted(n for n in names if n in MAKERS):
        make, peak = MAKERS[name]
        v = VERSION.get(name, 1)
        path = out_dir / (f"{name}-v{v}.wav" if v > 1 else f"{name}.wav")
        if not path.exists():
            _write(path, make(), peak)
        made[name] = path
    return made
