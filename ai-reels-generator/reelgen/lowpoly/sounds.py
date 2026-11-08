"""The low-poly films' sounds: the Sticky films' synthesised ones (reelgen/sticky/sounds.py, read only) plus what action
and fiction need, made here the same way (no files to license): a heavy impact, a metal crash, breaking glass, the
ground cracking, straining metal, a tyre skid, a siren, wind, fire, sparks, a fly-by and a frightened crowd. No boom
and no riser (the user's standing rule): the weight comes from the impact and the crash. Animals: a roar, heavy footfalls, wing beats."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .. import sfx
from ..sfx import RATE, _lowpass, _write
from ..sticky import sounds as sticky
from . import car


def _real(x, made):
    """The recording when it is there, else the synthesised sound."""
    return x if x is not None else made()


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


def _engine() -> np.ndarray:
    """A sports car's engine under way (looped): a V8's firing note and its half-order burble, climbing through the
    revs and dropping at each gear change, with a little intake noise on the pulses. No sub boom: it sits 140-450 Hz."""
    t = _t(6.0)
    ph = (t % 2.0) / 2.0  # three gears in six seconds
    rpm = 2700 + 3700 * ph ** 0.85
    f = rpm / 60 * 4  # four firings a turn
    phase = 2 * np.pi * np.cumsum(f) / RATE
    x = sum(a * np.sin(k * phase + k * 0.7) for k, a in ((0.5, 0.55), (1, 1.0), (1.5, 0.35), (2, 0.5), (3, 0.28), (4, 0.15)))
    pulse = 0.6 + 0.4 * np.maximum(0, np.sin(phase))
    air = _lowpass(_noise(47, len(t)), 2200) * pulse * 0.35
    shift = 1 - 0.55 * np.exp(-((t % 2.0) / 0.06)) * (t > 0.1)  # the lift at each change
    return _loopable(_lowpass(x * 0.5 + air, 3200) * shift)


def _rev() -> np.ndarray:
    """The foot slammed on the accelerator: the V8's note leaps from idle to the top of its revs in a third of a second
    and holds there as it pulls away, with the intake's rush; a crackle as it settles. 140-500 Hz, no sub boom."""
    t = _t(1.4)
    rpm = 1100 + 5600 * (1 - np.exp(-np.maximum(0, t - 0.03) / 0.12)) - 900 * np.clip((t - 0.7) / 0.7, 0, 1)
    f = rpm / 60 * 4
    phase = 2 * np.pi * np.cumsum(f) / RATE
    x = sum(a * np.sin(k * phase + k * 0.7) for k, a in ((0.5, 0.6), (1, 1.0), (1.5, 0.4), (2, 0.55), (3, 0.3), (4, 0.16)))
    pulse = 0.6 + 0.4 * np.maximum(0, np.sin(phase))
    air = _lowpass(_noise(50, len(t)), 2600) * pulse * (0.25 + 0.35 * np.clip((t - 0.03) / 0.15, 0, 1))
    rng = np.random.default_rng(51)
    pops = np.zeros_like(t)
    for at in rng.uniform(0.95, 1.3, 5):
        i = int(at * RATE)
        pops[i:i + 160] += rng.uniform(0.3, 0.6) * np.exp(-np.arange(min(160, len(t) - i)) / 30)
    env = np.minimum(t / 0.02, 1) * np.minimum((1.4 - t) / 0.25, 1)
    return _lowpass(x * 0.5 + air, 3400) * env + _lowpass(pops * _noise(52, len(t)), 3000)


def _jet() -> np.ndarray:
    """A jet going over (looped): a broad roar and a high turbine whine."""
    t = _t(6.0)
    roar = _lowpass(_noise(48, len(t)), 1400)
    roar -= _lowpass(roar, 120)  # no rumble under it
    whine = np.sin(2 * np.pi * np.cumsum(2150 + 40 * np.sin(2 * np.pi * 0.2 * t)) / RATE) * 0.12
    return _loopable(roar * (0.85 + 0.15 * np.sin(2 * np.pi * 0.17 * t)) + whine)


def _propeller() -> np.ndarray:
    """A small propeller plane (looped): the engine's drone and the blades beating the air."""
    t = _t(6.0)
    f = 92 + 3 * np.sin(2 * np.pi * 0.13 * t)
    phase = 2 * np.pi * np.cumsum(f) / RATE
    drone = sum(a * np.sin(k * phase) for k, a in ((1, 0.6), (2, 1.0), (3, 0.5), (4, 0.3), (6, 0.15)))
    blades = 0.55 + 0.45 * np.maximum(0, np.sin(phase * 0.5)) ** 3
    air = _lowpass(_noise(49, len(t)), 1800) * blades * 0.5
    return _loopable(_lowpass(drone * 0.4 + air, 2600))



# Animals and creatures (the user's dinosaur script: a T-Rex roaring, a herd, pterosaurs, an egg hatching).
def _roar() -> np.ndarray:
    """A huge animal's roar: a rough growl that swells up in pitch and falls away, its throat (a rattling low voice)
    under a breathy roar of noise shaped by an open mouth."""
    t = _t(2.2)
    shape = np.sin(np.pi * np.clip(t / 2.0, 0, 1)) ** 0.6
    f = 62 + 46 * shape + 6 * np.sin(2 * np.pi * 5.5 * t)
    saw = 2 * ((np.cumsum(f) / RATE) % 1) - 1
    rasp = 1 + 0.7 * _lowpass(_noise(61, len(t)), 40) / 0.25  # the rattle of the throat
    voice = _lowpass(saw * np.clip(rasp, 0.2, 2.2), 1400)
    breath = _noise(62, len(t))
    breath = _lowpass(breath, 2600) - _lowpass(breath, 380)
    env = np.minimum(t / 0.18, 1) * np.clip((2.2 - t) / 0.9, 0, 1) ** 1.3
    return (voice * 0.8 + breath * 0.55 * (0.4 + shape)) * env


def _stomp() -> np.ndarray:
    """One heavy footfall: a deep thud through the ground and the crunch of what it lands on."""
    t = _t(0.7)
    low = np.sin(2 * np.pi * np.cumsum(38 + 40 * np.exp(-t * 18)) / RATE) * np.exp(-t * 7.5)
    hit = _lowpass(_noise(63, len(t)), 320) * np.exp(-t * 26)
    crunch = (_noise(64, len(t)) - _lowpass(_noise(64, len(t)), 900)) * np.exp(-t * 30) * 0.25
    return low + hit * 1.2 + crunch


def _flap() -> np.ndarray:
    """A big wing beat: a soft whump of air."""
    t = _t(0.45)
    air = _noise(65, len(t))
    air = _lowpass(air, 700) - _lowpass(air, 90)
    return air * np.sin(np.pi * t / 0.45) ** 2


def _wings() -> np.ndarray:
    """Wings beating steadily (a bed under a flying creature): a beat every 0.7 s."""
    beat = _flap()
    out = np.zeros(int(RATE * 2.8))
    for k in range(4):
        a = int(RATE * 0.7 * k)
        out[a:a + len(beat)] += beat[: len(out) - a]
    return out

MAKERS = {
    **sticky.MAKERS,
    "engine": (_engine, 0.5), "jet": (_jet, 0.45), "propeller": (_propeller, 0.45), "rev": (lambda: _real(car.rev(), _rev), 0.6),
    "impact": (sfx._impact, 0.75), "crash": (_crash, 0.7), "glass": (_glass, 0.5), "crack": (_crack, 0.6), "creak": (_creak, 0.45),
    "skid": (_skid, 0.45), "siren": (_siren, 0.3), "wind": (_wind, 0.35), "fire": (_fire, 0.35), "sparks": (_sparks, 0.35),
    "flyby": (sfx._flyby, 0.6), "crowd": (_crowd, 0.35), "roar": (_roar, 0.8), "stomp": (_stomp, 0.8), "flap": (_flap, 0.5),
    "wings": (_wings, 0.45), "rumble": (lambda: sfx._rumble(1.6), 0.55),
}


# a sound made again since a video was mixed gets a new file name, so a re-mix of an older video picks it up
VERSION = {"wind": 2, "siren": 2, "fire": 2, "rev": 2}


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


# ---------------------------------------------------------------- footsteps, one by one, where the feet land

# The first footsteps were one 2-second loop of identical 90 Hz thuds every 0.42 s under every walk, on every floor,
# while his walk puts a foot down every 0.57 s (the user: "walk sound not look real"). Now each step is made on its
# own at the moment a foot lands in the animation (timeline.step_times), as a heel strike and the toe rolling off,
# with the floor's own sound, a little different every time, and a short room echo indoors.

# Real footsteps (ESC-50 recordings, measured beside ours) come in two kinds, and neither has a pitched thump (the first
# synth's 90-110 Hz sine with a pitch drop is a drum machine's kick: an AudioSet classifier (AST) heard it as 'Drum
# machine' / 'Music'). On a hard floor a step is one dull 'tock' (most of its energy 150-400 Hz, gone in ~15 ms) with
# a small second tap ~9 ms after it and the toe touching ~0.1 s later; on loose or rough ground it is a burst of
# small crunches that builds for ~50 ms into the main impact (a low thud under it) and dies away over ~60 ms.

# per floor: kind 'hard' or 'ground'; the tock's band (Hz) and decay (s); the click on top (band, level); a hollow
# ring (band, decay, level) for wooden floors; crunch grains (count, band, level); a low thud's level; splash; room echo
SURFACES = {
    "wood": dict(kind="hard", tock=((150, 520), 0.014), click=((1200, 4500), 0.25), hollow=((180, 420), 0.03, 0.45),
                 grains=(0, (0, 0), 0), thud=0.25, splash=0, room=0.3),
    "tile": dict(kind="hard", tock=((220, 700), 0.01), click=((2000, 7000), 0.5), hollow=None, grains=(2, (3000, 7500), 0.2),
                 thud=0.15, splash=0, room=0.4),
    "carpet": dict(kind="hard", tock=((120, 380), 0.018), click=((800, 2500), 0.08), hollow=None, grains=(0, (0, 0), 0),
                   thud=0.3, splash=0, room=0.08),
    "rubber": dict(kind="hard", tock=((140, 450), 0.016), click=((1000, 3500), 0.15), hollow=((160, 380), 0.02, 0.2),
                   grains=(0, (0, 0), 0), thud=0.3, splash=0, room=0.25),
    "studio": dict(kind="hard", tock=((150, 480), 0.015), click=((1000, 3500), 0.15), hollow=((170, 400), 0.02, 0.2),
                   grains=(0, (0, 0), 0), thud=0.25, splash=0, room=0.22),
    "concrete": dict(kind="hard", tock=((180, 600), 0.011), click=((1500, 6500), 0.35), hollow=None, grains=(14, (2000, 7500), 0.25),
                     thud=0.2, splash=0, room=0.05),
    "wet": dict(kind="ground", tock=((180, 550), 0.012), click=((1500, 5000), 0.2), hollow=None, grains=(18, (2000, 7000), 0.3),
                thud=0.35, splash=0.6, room=0.08),
    "path": dict(kind="ground", tock=((150, 450), 0.014), click=((1000, 4500), 0.15), hollow=None, grains=(45, (1200, 7000), 0.45),
                 thud=0.6, splash=0, room=0.0),
    "gravel": dict(kind="ground", tock=((140, 420), 0.014), click=((900, 4000), 0.12), hollow=None, grains=(90, (900, 7500), 0.6),
                   thud=0.55, splash=0, room=0.0),
}
# per way of moving: how hard the foot lands, when the toe touches (s), how much it scuffs, timing looseness (s)
PACES = {"walk": (1.0, 0.11, 1.0, 0.018), "carry": (1.25, 0.13, 0.8, 0.02), "jog": (1.25, 0.07, 1.15, 0.012),
         "run": (1.5, 0.05, 1.3, 0.01), "flee": (1.5, 0.05, 1.4, 0.014), "dash": (1.6, 0.03, 1.5, 0.004)}


def _sos(kind: str, f):
    from scipy.signal import butter

    return butter(2, f, kind, fs=RATE, output="sos")


def _filt(x: np.ndarray, kind: str, f) -> np.ndarray:
    from scipy.signal import sosfilt

    hi = RATE / 2 - 100
    f = [min(v, hi) for v in f] if isinstance(f, (list, tuple)) else min(f, hi)
    return sosfilt(_sos(kind, f), x)


def _burst(rng, n: int, decay: float, kind: str, f, rise: float = 0.0008) -> np.ndarray:
    """A short noise burst (a tock, a click, a crunch): a quick rise, an exponential tail, filtered; scaled to peak 1."""
    t = np.arange(n) / RATE
    x = _filt(rng.standard_normal(n) * np.exp(-t / decay) * np.minimum(t / rise, 1), kind, f)
    return x / (np.abs(x).max() or 1)


def _step(rng, s: dict, weight: float, roll: float, scuff: float, pitch: float, slow: bool) -> np.ndarray:
    """One footstep, made the way real ones sound: a dull tock with a little click and a second tap on a hard floor, or
    a burst of crunches building into the impact on loose ground; then the toe. Noise only, nothing pitched."""
    stretch = 1.8 if slow else 1.0  # slow motion: everything longer and lower
    pitch = pitch * (0.6 if slow else 1.0)
    pre = 0.06 * stretch  # room before the impact for a crunch that builds into it
    m = int(RATE * (0.4 * stretch + pre))
    out = np.zeros(m)

    def add(at: float, x: np.ndarray, gain: float) -> None:
        i = int((pre + at * stretch) * RATE)
        if 0 <= i < m:
            out[i:i + len(x)] += x[: m - i] * gain

    (t1, t2), td = s["tock"]
    band = (t1 * pitch, t2 * pitch)
    add(0, _burst(rng, int(RATE * 0.08 * stretch), td * stretch, "bandpass", band, 0.0015), 1.0)  # the impact
    add(rng.uniform(0.007, 0.011), _burst(rng, int(RATE * 0.05 * stretch), td * 0.7 * stretch, "bandpass", band), rng.uniform(0.2, 0.4))
    (c1, c2), cl = s["click"]
    add(0, _burst(rng, int(RATE * 0.02), 0.0015 * stretch, "bandpass", (c1 * pitch, c2 * pitch)), cl * scuff)
    if s["hollow"]:
        (h1, h2), hd, hl = s["hollow"]
        add(0.001, _burst(rng, int(RATE * 0.1 * stretch), hd * stretch, "bandpass", (h1 * pitch, h2 * pitch), 0.002), hl)
    if s["thud"]:
        add(0.002, _burst(rng, int(RATE * 0.15 * stretch), 0.03 * stretch, "lowpass", 150 * pitch, 0.008), s["thud"])
    count, (g1, g2), gl = s["grains"]
    for _ in range(int(count * scuff)):  # crunches building into the impact and dying away after it
        before = rng.random() < 0.45
        at = -abs(rng.normal(0, 0.022)) if before else abs(rng.normal(0, 0.03))
        level = gl * rng.uniform(0.2, 1.0) * (np.exp(at / 0.03) if before else np.exp(-at / 0.04))
        add(at, _burst(rng, int(RATE * 0.006), rng.uniform(0.0006, 0.002), "bandpass", (g1 * pitch, g2 * pitch)), level)
    toe = roll * rng.uniform(0.85, 1.2)  # the toe touching down
    add(toe, _burst(rng, int(RATE * 0.05 * stretch), td * 0.8 * stretch, "bandpass", (band[0] * 1.3, band[1] * 1.4)), rng.uniform(0.18, 0.32))
    if s["splash"]:
        add(0.002, _burst(rng, int(RATE * 0.15 * stretch), 0.04 * stretch, "bandpass", (2000 * pitch, 7000 * pitch), 0.004), s["splash"] * 0.6)
        for _ in range(5):
            add(rng.uniform(0.02, 0.14), _burst(rng, int(RATE * 0.02), 0.004, "bandpass", (2500, 6500)), rng.uniform(0.1, 0.25))
    out *= weight
    if s["room"]:  # a room: early reflections, darker than the step
        dark = _filt(out, "lowpass", 2500)
        for delay, gain in ((0.013, 0.3), (0.023, 0.22), (0.037, 0.15), (0.058, 0.09), (0.083, 0.05)):
            d = int(delay * RATE)
            out[d:] += dark[:-d] * gain * s["room"] * 2.2
    return out


def footsteps(times: list[float], surface: str = "concrete", pace: str = "walk", seed: int = 1, slow: bool = False) -> np.ndarray:
    """A track of single footsteps at `times` (seconds from its start), each made on its own: the floor's sound, the
    way of moving, the left foot a little heavier than the right, every step a little different. Mono, at RATE."""
    s = SURFACES.get(surface, SURFACES["concrete"])
    weight, roll, scrape, loose = PACES.get(pace, PACES["walk"])
    rng = np.random.default_rng(seed)
    if not times:
        return np.zeros(1)
    out = np.zeros(int((max(times) + 0.7 * (1.8 if slow else 1)) * RATE))
    for k, at in enumerate(times):
        step = _step(rng, s, weight * (1.08 if k % 2 == 0 else 0.93) * 10 ** (rng.uniform(-2.5, 2.5) / 20), roll * rng.uniform(0.85, 1.15),
                     scrape * rng.uniform(0.7, 1.3), rng.uniform(0.93, 1.07), slow)
        i = max(0, int((at - 0.06 * (1.8 if slow else 1) + rng.normal(0, loose)) * RATE))  # the impact lands on `at`
        j = min(len(out), i + len(step))
        out[i:j] += step[: j - i]
    return out


# ---------------------------------------------------------------- recorded footsteps (CC0)

# Synthesised steps never passed for real ones: after four rebuilds the AudioSet classifier still heard 'Knock' or
# 'Slap', never 'Walk, footsteps'. So steps are recorded ones (footsteps/, all CC0, see footsteps/CREDITS.txt), one
# picked per step (never the same twice running), a touch higher or lower and louder or softer each time, coloured for
# the floor (tiles brighter, carpet and rubber duller, mud on wet stone) and given the room's echo indoors.
BANK = Path(__file__).with_name("footsteps")
# floor -> (the recorded sets it uses, a filter on them, room echo, an extra layer and its level)
FLOORS = {  # chosen by an AudioSet classifier's 'Walk, footsteps' score on a walk of each (see CLAUDE.md)
    "wood": (("floor",), "", 0.04, None, 0),
    "studio": (("floor",), "lowpass=f=5000", 0.04, None, 0),
    "carpet": (("floor",), "lowpass=f=1800", 0.04, None, 0),
    "rubber": (("floor",), "lowpass=f=2600", 0.04, None, 0),
    "tile": (("stone", "floor"), "highshelf=f=2500:g=3", 0.25, None, 0),
    "concrete": (("stone",), "", 0.04, None, 0),
    "wet": (("stone",), "", 0.08, "mud", 0.6),
    "path": (("gravel", "sand"), "", 0.0, None, 0),
    "gravel": (("gravel",), "", 0.0, None, 0),
}
_bank: dict[str, list[np.ndarray]] = {}


def _recorded(kind: str, af: str = "") -> list[np.ndarray]:
    key = f"{kind}|{af}"
    if key not in _bank:
        from ..sticky.mixdown import decode

        _bank[key] = [decode(p, af).mean(axis=1) if af else decode(p).mean(axis=1) for p in sorted(BANK.glob(f"{kind}-*.ogg"))]
    return _bank[key]


def _respeed(x: np.ndarray, factor: float) -> np.ndarray:
    """Played `factor` times as fast (higher and shorter above 1, lower and longer below)."""
    n = max(2, int(len(x) / factor))
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x)


def recorded_steps(times: list[float], surface: str = "concrete", pace: str = "walk", seed: int = 1, slow: bool = False) -> np.ndarray | None:
    """A track of recorded footsteps landing at `times` (seconds from its start); None when the recordings are missing."""
    sets, af, room, layer, layer_gain = FLOORS.get(surface, FLOORS["concrete"])
    pool = [x for s_ in sets for x in _recorded(s_, af)]
    extra = _recorded(layer) if layer else []
    if not pool or not times:
        return None
    weight, _roll, _scuff, loose = PACES.get(pace, PACES["walk"])
    rng = np.random.default_rng(seed)
    out = np.zeros(int((max(times) + 1.2 * (2.5 if slow else 1)) * RATE))
    last = -1
    for k, at in enumerate(times):
        pick = int(rng.integers(len(pool)))
        if pick == last and len(pool) > 1:
            pick = (pick + 1) % len(pool)
        last = pick
        speed = rng.uniform(0.96, 1.04) * (1.03 if pace in ("run", "flee", "dash") else 1.0) * (0.6 if slow else 1.0)
        step = _respeed(pool[pick], speed)
        if extra:
            e = _respeed(extra[int(rng.integers(len(extra)))], speed)
            n = min(len(step), len(e))
            step = step.copy()
            step[:n] += e[:n] * layer_gain
        gain = min(1.6, weight) * (1.06 if k % 2 == 0 else 0.94) * 10 ** (rng.uniform(-2, 2) / 20)
        i = max(0, int((at - 0.006 + rng.normal(0, loose)) * RATE))  # each recording starts 6 ms before its impact
        j = min(len(out), i + len(step))
        out[i:j] += step[: j - i] * gain
    if room:  # a room: early reflections, darker than the steps
        dark = _filt(out, "lowpass", 2500)
        for delay, g in ((0.013, 0.3), (0.023, 0.22), (0.037, 0.15), (0.058, 0.09), (0.083, 0.05)):
            d = int(delay * RATE)
            out[d:] += dark[:-d] * g * room * 2.2
    return out
