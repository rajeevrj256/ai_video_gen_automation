"""The low-poly films' soundtrack, mixed in numpy from the timeline and levelled by loudness the way ears hear it (LUFS,
K-weighted as in ITU BS.1770), with the voices in charge: the narration and the dialogue on their frames; the score
(AI music when the engine is installed, else composed in the story's moods) well under them, stepping back while
anyone speaks and not swelling between lines that follow closely, high-passed and with a dip where voices sit; the
world's sounds (synthesised, reelgen/lowpoly/sounds.py) each at its own place under the voice: a crash or an impact
close behind it, footsteps and typing further, and the beds that run for a whole shot (wind, rain, fire, a siren far
off) far under it and lower still while someone speaks.

The first version levelled the music by its RMS only ~7 dB under the voice between lines, let it swell up in every
gap, and capped every effect at one level, so a wind bed ran nearly as loud as the dialogue for whole shots (the
user's film 'reel_5_2': "background music is too loud ... hawa sound too noisy"). The finished video is mastered to
-14 LUFS by the render (reelgen/audio.py)."""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
from scipy.signal import lfilter

from . import sounds
from ..sticky.mixdown import RATE, _place, _tracks, decode

GENRE = "piano-minimal"  # the original's sound: soft felt piano
FICTION_GENRE = "cinematic-orchestral"  # a fiction film's score
MIX_VERSION = 2

# how far under the voice (LU) the music sits between lines and while someone speaks
MUSIC_GAP = {"life": 10.0, "fiction": 11.0}
MUSIC_UNDER = {"life": 18.0, "fiction": 20.0}
MUSIC_EQ = "highpass=f=70,lowshelf=f=180:g=-5,equalizer=f=2500:t=o:w=1.2:g=-4"  # room for the voices
EFFECT_EQ = "highpass=f=45"  # no sub rumble under the effects
BRIDGE = 1.2  # seconds: the music stays down across a pause shorter than this between lines
ATTACK, RELEASE = 0.15, 0.6  # it goes down just before a line and comes back slowly after

# each sound's loudness under the voice (LU); a bed that runs for a whole shot sits far under it
UNDER_VOICE = {
    "impact": 7, "crash": 6, "glass": 9, "crack": 9, "thud": 10, "rumble": 13, "swoosh": 10, "flyby": 9, "skid": 10, "creak": 12,
    "door": 10, "knock": 10, "alarm": 9, "notify": 10, "buzz": 11, "ding": 11, "chime": 11, "bell": 11, "pop": 12, "send": 12,
    "tap": 13, "page": 14, "scribble": 14, "coins": 11, "cheer": 12, "swell": 14, "static": 16,
    "footsteps": 17, "typing": 18, "tick": 19, "heartbeat": 15,
    "wind": 27, "rain": 24, "fire": 24, "siren": 27, "sparks": 22, "crowd": 22,
    "engine": 13, "jet": 14, "propeller": 15,  # a vehicle under way: the shot's own bed, the loudest one
    "rev": 8,  # the foot on the accelerator in a cut-in: over the engine bed
}
BEDS = {"wind", "rain", "fire", "siren", "sparks", "crowd", "tick", "engine", "jet", "propeller"}  # lower still under speech
BED_UNDER_SPEECH = 0.5  # -6 dB more while someone speaks
EFFECT_UNDER_SPEECH = 0.75


# ---------------------------------------------------------------- loudness (BS.1770, K-weighted, gated)

def _kfilter(fs: int = RATE):
    """The two K-weighting stages (a high shelf for the head, a high-pass) for this rate, derived as libebur128 does,
    so at 48 kHz they are the standard's own coefficients."""
    import math

    f0, G, Q = 1681.974450955533, 3.999843853973347, 0.7071752369554196
    K = math.tan(math.pi * f0 / fs)
    vh = 10 ** (G / 20)
    vb = vh ** 0.4996667741545416
    a0 = 1 + K / Q + K * K
    b1 = [(vh + vb * K / Q + K * K) / a0, 2 * (K * K - vh) / a0, (vh - vb * K / Q + K * K) / a0]
    a1 = [1.0, 2 * (K * K - 1) / a0, (1 - K / Q + K * K) / a0]
    f0, Q = 38.13547087602444, 0.5003270373238773
    K = math.tan(math.pi * f0 / fs)
    d = 1 + K / Q + K * K
    b2 = [1.0, -2.0, 1.0]
    a2 = [1.0, 2 * (K * K - 1) / d, (1 - K / Q + K * K) / d]
    return (np.array(b1), np.array(a1)), (np.array(b2), np.array(a2))


_K = _kfilter()


def _blocks(x: np.ndarray) -> np.ndarray:
    """Mean square of the K-weighted signal (both channels summed) in 400 ms blocks every 100 ms."""
    if x.ndim == 1:
        x = x[:, None]
    y = x.astype(np.float64)
    for b, a in _K:
        y = lfilter(b, a, y, axis=0)
    p = (y ** 2).sum(axis=1)
    hop, size = RATE // 10, int(RATE * 0.4)
    if len(p) < size:
        return np.array([p.mean()]) if len(p) else np.array([0.0])
    c = np.concatenate([[0.0], np.cumsum(p)])
    starts = np.arange(0, len(p) - size + 1, hop)
    return (c[starts + size] - c[starts]) / size


def lufs(x: np.ndarray, keep: np.ndarray | None = None) -> float:
    """Integrated loudness (LUFS, absolute and relative gates). `keep`: per-block booleans choosing which blocks count."""
    z = _blocks(x)
    if keep is not None:
        z = z[keep[: len(z)]] if len(keep) >= len(z) else z[: len(keep)][keep]
    z = z[z > 10 ** ((-70 + 0.691) / 10)]
    if not len(z):
        return -120.0
    rel = -0.691 + 10 * np.log10(z.mean()) - 10
    z = z[-0.691 + 10 * np.log10(z) > rel]
    return float(-0.691 + 10 * np.log10(z.mean())) if len(z) else -120.0


def _filt_effect(x: np.ndarray) -> np.ndarray:
    """EFFECT_EQ in numpy (a 45 Hz high-pass), for sounds made here rather than read from a file."""
    from scipy.signal import butter, sosfilt

    return sosfilt(butter(2, 45, "highpass", fs=RATE, output="sos"), x, axis=0).astype(np.float32)


def _db(v: float) -> float:
    return float(10 ** (v / 20))


# ---------------------------------------------------------------- when someone speaks

def speech_envelope(voice: np.ndarray) -> np.ndarray:
    """0..1 per sample: 1 while anyone speaks (pauses under BRIDGE between lines bridged), reached ATTACK before a
    line starts and let go over RELEASE after it ends."""
    block = RATE // 100
    n = len(voice) // block
    if not n:
        return np.zeros(len(voice), np.float32)
    on = np.abs(voice[: n * block]).reshape(n, block, -1).max(axis=(1, 2)) > 0.01
    idx = np.flatnonzero(on)
    if len(idx):
        gaps = np.flatnonzero(np.diff(idx) > 1)
        for g in gaps:  # fill short pauses between words and lines
            a, b = idx[g], idx[g + 1]
            if (b - a) * block / RATE < BRIDGE:
                on[a:b] = True
    env = on.astype(np.float32)
    # reach full duck ATTACK before speech (look ahead) and release over RELEASE after it
    att, rel = int(ATTACK * 100), int(RELEASE * 100)
    ahead = np.zeros_like(env)
    for k in range(1, att + 1):
        ahead[:-k] = np.maximum(ahead[:-k], env[k:] * (1 - k / (att + 1)))
    after = np.zeros_like(env)
    for k in range(1, rel + 1):
        after[k:] = np.maximum(after[k:], env[:-k] * (1 - k / (rel + 1)))
    env = np.maximum(env, np.maximum(ahead, after))
    out = np.repeat(env, block)
    return np.concatenate([out, np.full(len(voice) - len(out), out[-1] if len(out) else 0, np.float32)]).astype(np.float32)


# ---------------------------------------------------------------- the mix

def mix(cfg, props: dict, clips: list[dict], cues: list[dict], sections: list[dict], work: Path, out: Path, seed: int,
        progress, brief: str, fiction: bool = False) -> dict:
    kind = "fiction" if fiction else "life"
    total = float(props["duration"]) + 0.5
    n = int(total * RATE)
    music = np.zeros((n, 2), np.float32)
    voice = np.zeros_like(music)
    fx = np.zeros_like(music)
    beds = np.zeros_like(music)
    for c in clips:
        _place(voice, decode(Path(c["path"])), float(c["at"]), 1.0)
    talk = speech_envelope(voice)
    lv = lufs(voice)
    if lv < -60:
        lv = -16.0  # a silent film: place everything as if the voice were at the narration's usual level

    # the score: each part placed with its fades, then the whole of it brought under the voice
    tracks, genre = _tracks(cfg, sections, work, seed, progress, FICTION_GENRE if fiction else GENRE, brief)
    for i, s in enumerate(sections):
        x = decode(tracks[i], MUSIC_EQ)
        part = lufs(x)
        if part > -60:
            x = x * _db(-23 - part)  # every part at one loudness first (composed moods differ by several dB)
        length = s["end"] - s["start"] + (1.5 if i < len(sections) - 1 else 0.4)
        x = np.tile(x, (int(length * RATE) // max(1, len(x)) + 1, 1))[: int(length * RATE)]
        env = np.ones(len(x), np.float32)
        fin, fout = int((1.2 if i else 0.6) * RATE), int(1.6 * RATE)
        env[: min(fin, len(x))] *= np.linspace(0, 1, min(fin, len(x)))
        env[-min(fout, len(x)):] *= np.linspace(1, 0, min(fout, len(x)))
        _place(music, x * env[:, None], s["start"], 1.0)
    lm = lufs(music)
    gain = _db(lv - MUSIC_GAP[kind] - lm) if lm > -60 else 0.0
    under = _db(-(MUSIC_UNDER[kind] - MUSIC_GAP[kind]))
    music *= (gain * (1 - (1 - under) * talk))[:, None]

    # the world's sounds, each at its own loudness under the voice
    files = sounds.write_all(work / "sfx", {c["sound"] for c in cues if c.get("steps") is None})
    step_gain = None  # every walk's steps at one level: set by the first walk
    loaded: dict[str, np.ndarray] = {}
    for name, path in files.items():
        x = decode(path, EFFECT_EQ)
        lx = lufs(x)
        target = lv - UNDER_VOICE.get(name, 10)
        loaded[name] = x * min(8.0, _db(target - lx)) if lx > -60 else x
    for c in cues:
        if c.get("steps") is not None:  # footsteps: each landing where a foot does, recorded steps on this floor
            x = sounds.recorded_steps(c["steps"], c.get("surface", "concrete"), c.get("pace", "walk"), int(c.get("seed", 1)), bool(c.get("slow")))
            if x is None:
                x = sounds.footsteps(c["steps"], c.get("surface", "concrete"), c.get("pace", "walk"), int(c.get("seed", 1)), bool(c.get("slow")))
            x = _filt_effect(np.stack([x, x], axis=1).astype(np.float32))
            if step_gain is None:
                lx = lufs(x)
                step_gain = min(8.0, _db(lv - UNDER_VOICE["footsteps"] - lx)) if lx > -60 else 1.0
            _place(fx, x * step_gain, float(c["at"]), float(c.get("volume", 1)))
            continue
        x = loaded.get(c["sound"])
        if x is not None:
            _place(beds if c["sound"] in BEDS else fx, x, float(c["at"]), float(c.get("volume", 1)), c.get("length"))
    beds *= (1 - (1 - BED_UNDER_SPEECH) * talk)[:, None]
    fx *= (1 - (1 - EFFECT_UNDER_SPEECH) * talk)[:, None]

    buf = music + fx + beds + voice
    peak = float(np.abs(buf).max() or 1)
    if peak > 0.95:
        buf = buf / peak * 0.95
    pcm = (np.clip(buf, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    mid = talk[RATE // 5:: RATE // 10]  # each 400 ms block judged by its middle
    speaking, quiet = mid > 0.99, mid < 0.01
    levels = {"voice": round(lv, 1), "music_between_lines": round(lufs(music, quiet), 1),
              "music_under_speech": round(lufs(music, speaking), 1), "beds": round(lufs(beds), 1), "effects": round(lufs(fx), 1)}
    ai = [i for i, p in tracks.items() if p.name.endswith("-ai.wav")]
    return {"music": (f"AI music ({genre}) for {len(ai)} of {len(sections)} parts" if ai else
                      f"composed ({', '.join(s['mood'] for s in sections)})"), "sound_cues": len(cues), "genre": genre,
            "levels": levels, "mix_version": MIX_VERSION}
