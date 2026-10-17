"""Short sound effects for the edit, synthesised on the fly so there are no audio
files to ship or license.

- whoosh: a soft swell of filtered air (flash transition and the hook title).
- impact: a short low thud (zoom transition).
- swish: a fast, bright air swipe (slide transition).
- glitch: a digital stutter of clicks and noise bursts (glitch transition).
- shimmer: a soft rising chime (fade transition).
- pop: a quick, rounded blip for when a graphic lands.
- the cinematic hook's own set (HOOK_SOUNDS, write_hook_sounds): sub boom, whip, shutter, paper tear,
  typewriter labels and a dark drone; used in hooks only.

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
# boom, hit and rise were deleted at the user's request (they sounded bad on every video), and later every riser
# (the built-in one and the hook's): the user banned them.
def _boing(duration: float = 0.7) -> np.ndarray:
    """A cartoon spring: a low note whose pitch wobbles fast, then settles (a silly moment, a meme's punchline)."""
    t = np.arange(int(RATE * duration)) / RATE
    freq = 170 * (1 + 0.45 * np.sin(2 * np.pi * 11 * t) * np.exp(-t * 4.5)) * (1 + 0.6 * np.exp(-t * 9))
    phase = 2 * np.pi * np.cumsum(freq) / RATE
    tone = np.sin(phase) + 0.35 * np.sin(2 * phase)
    return tone * np.minimum(t / 0.004, 1) * np.exp(-t * 4)


def _scratch(duration: float = 0.42) -> np.ndarray:
    """A record scratch: the music stops ('wait, what?'). Noise pulled through a band that sweeps up, then down."""
    n = int(RATE * duration)
    t = np.arange(n) / RATE
    x = t / duration
    noise = np.random.default_rng(11).standard_normal(n)
    centre = np.where(x < 0.45, 500 + 2600 * (x / 0.45), 3100 - 2700 * ((x - 0.45) / 0.55))
    hi = noise
    for _ in range(4):  # one pole rolls off too gently: white noise stayed a hiss at ~8 kHz
        hi = _lowpass(hi, centre * 1.2)
    band = hi - _lowpass(hi, centre * 0.5)
    grain = 1 + 0.6 * np.sign(np.sin(2 * np.pi * (40 + 60 * x) * t))  # the groove's rasp
    return band * grain * np.minimum(t / 0.005, 1) * np.minimum(1, (duration - t) / 0.06)


CUE_SOUNDS = {
    "sword": (_sword, 0.5, 0.05, "blade slash with a metallic ring: a sharp reveal, a cut, a decisive moment"),
    "heartbeat": (_heartbeat, 0.55, 0.0, "a heartbeat: suspense, fear, a life-or-death moment"),
    "tick": (_tick, 0.3, 0.0, "a clock ticking: deadlines, time running out, countdowns"),
    "cash": (_cash, 0.35, 0.0, "coins and a till bell: money, prices, profit"),
    "drone": (_drone, 0.22, 0.0, "low uneasy pad under a line: mystery, something is off"),
    "ding": (_ding, 0.3, 0.0, "clean ding: a fact or idea landing, a lightbulb moment"),
    "typing": (_typing, 0.25, 0.0, "keyboard clicks: searching, messaging, hacking, writing"),
    "click": (_click, 0.3, 0.0, "a crisp click: text or a counter landing"),
    "rumble": (_rumble, 0.5, 0.0, "a low rumble: shaking, a threat, fear"),
    "flyby": (_flyby, 0.4, 0.5, "something rushing past the camera: a plane, a car, a crowd"),
    "boing": (_boing, 0.35, 0.0, "a cartoon spring: a silly moment, a joke's punchline"),
    "scratch": (_scratch, 0.32, 0.0, "a record scratch: 'wait, what?', an awkward or surprising turn"),
}


# ---- The cinematic hook's own sounds (long videos, Script Videos, the Anim cold open, the first word of a Short) ----
# Modelled on a documentary-trailer cold open the user wanted (a dark drone from the first frame, a sub boom on each
# big cut, typed labels ticking, whips, then silence). The boom is used in hooks only (and under a Short's first
# word): the old boom/hit/rise cues sounded bad on every video and stay out of CUE_SOUNDS and the sound design. The
# hook's riser was removed too: the user banned it.

def _sub_boom(duration: float = 2.6) -> np.ndarray:
    """A deep trailer boom: a sine dropping from ~95 to ~34 Hz with a long decay, its first harmonic for small
    speakers, a soft noise thump on the attack and a dark tail. Felt more than heard: it never covers the voice."""
    t = np.arange(int(RATE * duration)) / RATE
    freq = 34 + 61 * np.exp(-t * 9)
    phase = 2 * np.pi * np.cumsum(freq) / RATE
    body = np.sin(phase) * np.exp(-t * 1.6)
    body += 0.35 * np.sin(2 * phase) * np.exp(-t * 3.2)  # the octave: phones and laptops can't play 40 Hz
    body = np.tanh(body * 1.6) / np.tanh(1.6)  # a little warmth
    thump = _lowpass(np.random.default_rng(31).standard_normal(len(t)), 900) * np.exp(-t * 28) * 0.9
    tail = _lowpass(np.random.default_rng(32).standard_normal(len(t)), 160) * np.exp(-t * 1.9) * 0.25
    return (body + thump + tail) * np.minimum(t / 0.0015, 1)


def _hook_whip(duration: float = 0.38) -> np.ndarray:
    """A heavy camera whip: a bright swipe with a low rush under it."""
    n = int(RATE * duration)
    x = np.arange(n) / n
    noise = np.random.default_rng(34).standard_normal(n)
    sweep = 600 + 8000 * np.sin(np.pi * x) ** 3  # opens fast and shuts: the swipe
    bright = _lowpass(noise, sweep) - _lowpass(noise, sweep * 0.25)
    low = _lowpass(noise, 180) * 1.1 * np.exp(-((x - 0.45) / 0.25) ** 2)
    return (bright * 1.6 + low) * np.sin(np.pi * np.minimum(1, x * 1.15)) ** 0.8


def _hook_type(chars: int, every: float) -> np.ndarray:
    """An old typewriter typing a label: one strike per letter `every` seconds (spaces are softer), a little
    mechanical rattle on each, and the carriage bell's ding left out (too cute)."""
    t = np.arange(int(RATE * (chars * every + 0.15))) / RATE
    rng = np.random.default_rng(35 + chars)
    out = np.zeros_like(t)
    for k in range(chars):
        at = k * every + rng.uniform(-0.006, 0.006)
        u = np.clip(t - max(0.0, at), 0, None)
        on = t >= max(0.0, at)
        strike = (np.sin(2 * np.pi * rng.uniform(1700, 2300) * u) * np.exp(-u * 340)
                  + rng.standard_normal(len(t)) * np.exp(-u * 600) * 0.8
                  + np.sin(2 * np.pi * 180 * u) * np.exp(-u * 90) * 0.6)  # the body of the machine
        out += strike * on * rng.uniform(0.7, 1.0)
    return out


def _hook_shutter(duration: float = 0.22) -> np.ndarray:
    """A film camera's shutter: two quick mechanical clicks."""
    t = np.arange(int(RATE * duration)) / RATE
    out = np.zeros_like(t)
    for at, f0 in ((0.0, 3100), (0.075, 2400)):
        u = np.clip(t - at, 0, None)
        out += ((np.sin(2 * np.pi * f0 * u) + np.random.default_rng(int(f0)).standard_normal(len(t)) * 0.7)
                * np.exp(-u * 220) * (t >= at))
    return out


def _hook_tear(duration: float = 0.42) -> np.ndarray:
    """Paper torn across the frame: crackling bursts of mid-high noise."""
    rng = np.random.default_rng(36)
    t = np.arange(int(RATE * duration)) / RATE
    noise = rng.standard_normal(len(t))
    band = noise - _lowpass(noise, 900)
    band = _lowpass(band, 5200)
    crackle = (rng.random(len(t)) < 0.012).astype(float)
    crackle = np.convolve(crackle, np.exp(-np.arange(200) / 25), mode="same")
    env = np.sin(np.pi * np.minimum(1, t / duration * 1.05)) ** 0.6
    return band * (0.45 + crackle) * env


def _hook_drone(duration: float) -> np.ndarray:
    """The dark bed under the whole hook: a low minor cluster beating slowly, a sub pulse every two seconds and a
    cold wind on top. Fades in over a second; its end is cut by the editor where the hook drops to silence."""
    t = np.arange(int(RATE * max(1.0, duration))) / RATE
    pad = np.zeros_like(t)
    for f0, a in ((55.0, 1.0), (65.4, 0.55), (82.4, 0.5), (110.0 * 1.006, 0.3), (77.8, 0.25)):  # A, C, E, a sour Eb
        pad += a * np.sin(2 * np.pi * f0 * t + 0.6 * np.sin(2 * np.pi * 0.07 * t * (1 + f0 / 200)))
    pad *= 0.75 + 0.25 * np.sin(2 * np.pi * 0.11 * t)
    pulse = np.zeros_like(t)
    for k in range(int(t[-1] // 2.0) + 1):
        u = np.clip(t - k * 2.0, 0, None)
        pulse += np.sin(2 * np.pi * 41 * u) * np.exp(-u * 4.5) * (t >= k * 2.0)
    wind = _lowpass(np.random.default_rng(37).standard_normal(len(t)), 500 + 300 * np.sin(2 * np.pi * 0.05 * t) ** 2)
    # Dark strings an octave and two up, so phones and laptops (no sub) still hear the bed.
    strings = np.zeros_like(t)
    for f0, a in ((220.0, 1.0), (261.6, 0.7), (311.1, 0.45)):
        ph = 2 * np.pi * f0 * t + 0.002 * f0 * np.sin(2 * np.pi * 5.1 * t)  # a slow vibrato
        strings += a * sum(np.sin(k * ph) / k for k in range(1, 5))
    strings = _lowpass(strings, 1200) * (0.5 + 0.5 * np.sin(2 * np.pi * 0.06 * t - 1.2) ** 2)
    out = pad * 0.6 + pulse * 0.5 + wind * 0.5 + strings * 0.16
    return out * np.minimum(t / 1.0, 1)


# name -> (make, peak); written by write_hook_sounds. Peaks are below the cue sounds' because they run long or sit low.
HOOK_SOUNDS = {
    "hook-boom": (_sub_boom, 0.8),
    "hook-whip": (_hook_whip, 0.45),
    "hook-shutter": (_hook_shutter, 0.35),
    "hook-tear": (_hook_tear, 0.35),
}
TYPE_EVERY = 0.045  # seconds per typed letter: keep in step with TypedLabel (remotion/src/cine/TypedLabel.tsx)


def write_hook_sounds(out_dir: Path, drone_seconds: float = 0.0, labels: tuple[str, ...] = ()) -> dict[str, Path]:
    """The hook's sounds in `out_dir`: hook-boom, hook-whip, hook-shutter, hook-tear, a drone of
    `drone_seconds` (hook-drone) and one typing take per label length (hook-type-<letters>)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out = {n: _write(out_dir / f"{n}.wav", make(), peak=peak) for n, (make, peak) in HOOK_SOUNDS.items()}
    if drone_seconds > 0:
        out["hook-drone"] = _write(out_dir / "hook-drone.wav", _hook_drone(drone_seconds), peak=0.3)
    for n in sorted({len(x) for x in labels if x}):
        out[f"hook-type-{n}"] = _write(out_dir / f"hook-type-{n}.wav", _hook_type(n, TYPE_EVERY), peak=0.3)
    return out


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
