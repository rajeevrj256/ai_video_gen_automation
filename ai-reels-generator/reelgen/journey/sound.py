"""The Journey's sound: only what the place would sound like, from real recordings (journey/sounds/, CC0 but one
CC BY engine; see CREDITS.txt). The reference video has no voice and no music: an engine, birds, rain and a storm,
crickets, a bee, each fading into the next with the time-lapse, loud and quiet like real life.

Beds (birds, rain, crickets...) run under their stages and cross-fade at the joins; the same bed in stages that follow
each other plays on without restarting. Spots (thunder, a soft fruit landing) fall on their moment. The mix is made
here in numpy (mono sources spread a little in stereo) and mastered with the picture (audio.master, -14 LUFS)."""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

from ..video import FFMPEG
from .story import BED_NAMES, Journey

RATE = 44100
BANK = Path(__file__).with_name("sounds")
FADE = 0.8  # a bed fades in and out over this, overlapping its neighbours
GAIN_DB = {  # each bed's level against the others (the files are levelled alike); storms and engines are loud
    "birds-morning": -1, "birds-forest": -1, "birds-park": 0, "stream": -3, "rain": 0, "storm": 2, "crickets": -3,
    "traffic": -4, "engine": 1, "leaves": -7, "wind": -5, "bee": -4, "thunder": 2, "squish": 0, "crunch": -2,
}
CREDITS = {"engine": "Engine sound: 'Engine-loop heavy vehicle/tank' by Nayckron (opengameart.org), CC BY 3.0"}


def _decode(path: Path) -> np.ndarray:
    raw = subprocess.run([FFMPEG, "-loglevel", "error", "-i", str(path), "-ac", "2", "-ar", str(RATE), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2).copy()


def _wind() -> np.ndarray:
    """No CC0 wind recording sounded like wind to the classifier: the low-poly films' airy synthesised wind."""
    from ..lowpoly.sounds import _wind as wind
    from ..sfx import RATE as SFX_RATE

    x = np.asarray(wind(), np.float32)
    if SFX_RATE != RATE:
        x = np.interp(np.arange(int(len(x) * RATE / SFX_RATE)) * SFX_RATE / RATE, np.arange(len(x)), x).astype(np.float32)
    x = x / (np.sqrt((x ** 2).mean()) + 1e-9) * 0.045  # about the bank's level
    return np.stack([x, np.roll(x, 2205)], 1)


_cache: dict[str, np.ndarray] = {}


def load(name: str, variant: int = 0) -> np.ndarray:
    key = f"{name}#{variant}"
    if key not in _cache:
        if name == "wind":
            _cache[key] = _wind()
        else:
            files = sorted(BANK.glob(f"{name}.ogg")) or sorted(BANK.glob(f"{name}-*.ogg"))
            if not files:
                raise FileNotFoundError(f"No recording called {name}")
            _cache[key] = _decode(files[variant % len(files)])
    return _cache[key]


def _bed(src: np.ndarray, n: int, offset: int) -> np.ndarray:
    """`n` samples of a recording from `offset`, looped with a short cross-fade where it wraps."""
    if len(src) >= offset + n:
        return src[offset:offset + n].copy()
    k = max(1, min(int(0.3 * RATE), len(src) // 4))
    out = src[offset:].copy()
    ramp = np.linspace(0, 1, k, dtype=np.float32)[:, None]
    while len(out) < n:
        out[-k:] = out[-k:] * (1 - ramp) + src[:k] * ramp
        out = np.concatenate([out, src[k:]])
    return out[:n]


def _smooth(x: np.ndarray, k: int) -> np.ndarray:
    """A moving average over `k` samples (running sums: a direct convolution of a minute of audio took minutes)."""
    if k < 2 or len(x) < 2:
        return x
    p = np.pad(x.astype(np.float64), (k // 2, k - k // 2), mode="edge")
    c = np.concatenate([[0.0], np.cumsum(p)])
    return ((c[k:k + len(x)] - c[:len(x)]) / k).astype(np.float32)


def _env(n: int, fade_in: int, fade_out: int) -> np.ndarray:
    e = np.ones(n, np.float32)
    if fade_in:
        e[:fade_in] = np.linspace(0, 1, fade_in) ** 1.5
    if fade_out:
        e[-fade_out:] = np.linspace(1, 0, fade_out) ** 1.5
    return e


def mix(j: Journey, out: Path, seed: int) -> dict:
    """Write the soundtrack WAV. Returns what played where (for the report and Effects & media used)."""
    total = sum(s.seconds for s in j.stages)
    n = int(total * RATE) + RATE
    track = np.zeros((n, 2), np.float32)
    rng = np.random.default_rng(seed)
    starts, t = [], 0.0
    for s in j.stages:
        starts.append(t)
        t += s.seconds
    used, runs = [], []
    # beds: runs of stages that share a bed play as one stretch
    for name in BED_NAMES:
        k = 0
        while k < len(j.stages):
            hit = [x for x in j.stages[k].sounds if x.name == name]
            if not hit:
                k += 1
                continue
            a, vols = k, []
            while k < len(j.stages) and any(x.name == name for x in j.stages[k].sounds):
                vols.append(max(x.volume for x in j.stages[k].sounds if x.name == name))
                k += 1
            runs.append((name, a, k, vols))
    for name, a, b, vols in runs:
        t0, t1 = max(0.0, starts[a] - (FADE / 2 if a else 0)), min(total, starts[b - 1] + j.stages[b - 1].seconds + FADE / 2)
        i0, i1 = int(t0 * RATE), int(t1 * RATE)
        src = load(name)
        piece = _bed(src, i1 - i0, int(rng.integers(0, max(1, len(src) - (i1 - i0)))) if len(src) > i1 - i0 else 0)
        # the stage's own volume, eased from stage to stage
        vol = np.ones(i1 - i0, np.float32)
        for m, v in enumerate(vols):
            sa = max(i0, int(starts[a + m] * RATE)) - i0
            vol[sa:] = v
        vol = _smooth(vol, int(0.5 * RATE))
        fi = int(FADE * RATE) if a else int(0.15 * RATE)
        fo = int(FADE * RATE) if b < len(j.stages) else int(1.2 * RATE)
        g = 10 ** (GAIN_DB.get(name, 0) / 20)
        track[i0:i1] += piece * (vol * _env(i1 - i0, fi, fo) * g)[:, None]
        used.append({"sound": name, "from": round(t0, 2), "to": round(t1, 2)})
    # spots
    for k, s in enumerate(j.stages):
        for x in s.sounds:
            if x.name in BED_NAMES:
                continue
            src = load(x.name, int(rng.integers(0, 3)))
            at = starts[k] + x.at * s.seconds
            i0 = int(at * RATE)
            m = min(len(src), n - i0)
            if m <= 0:
                continue
            track[i0:i0 + m] += src[:m] * (x.volume * 10 ** (GAIN_DB.get(x.name, 0) / 20))
            used.append({"sound": x.name, "at": round(at, 2)})
    track = track[:int(total * RATE)]
    peak = float(np.abs(track).max() or 1)
    if peak > 0.98:
        track *= 0.98 / peak
    pcm = (np.clip(track, -1, 1) * 32767).astype("<i2")
    out.parent.mkdir(parents=True, exist_ok=True)
    import wave
    with wave.open(str(out), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    names = {u["sound"] for u in used}
    return {"sounds": used, "credits": [CREDITS[k] for k in CREDITS if k in names]}
