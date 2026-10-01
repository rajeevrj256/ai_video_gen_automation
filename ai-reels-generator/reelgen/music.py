"""Original music, composed per video in code, so every video sounds different and nothing
is copied or needs a licence.

- `compose(mood, sections, seconds, seed)`: the main track. The mood picks tempo, scale,
  chord progressions and instruments; each section (a chapter) has an intensity from 0 to 1
  that adds or removes layers (pad -> bass -> ticks -> arps -> drums), and a section can
  start with a drop (a moment of silence, then a hit). The seed changes key, tempo,
  progression and patterns, so two videos in the same mood still differ.
- `trailer(style, seconds, cuts, seed)`: the hook's own energetic track: a short build, then a
  driving groove (four-on-the-floor kick, backbeat clap, the ticking "ti-ti-ti-ti" spy rhythm, a
  minor bass ostinato, stabs, a lead in the second half), a snare roll and a riser into the final
  cut, silence and a big hit. Original: it only shares the energy of spy/action intros.
- `ambience(kind, seconds, seed)`: a quiet background bed (city, rain, room, wind, crowd,
  night, lab, sea, fire) under a chapter.

All output is mono 44.1 kHz WAV, peak-normalised; the editor sets the levels.
"""

from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfilt

RATE = 44100

MOODS = ("mystery", "suspense", "emotional", "uplifting", "curious", "dark", "energetic", "calm")
TRAILERS = ("spy-pulse", "ticking-clock", "dark-pulse", "glitch-drive")
AMBIENCES = ("none", "room", "city", "rain", "wind", "crowd", "night", "lab", "sea", "fire")

SCALES = {
    "minor": [0, 2, 3, 5, 7, 8, 10],
    "phrygian": [0, 1, 3, 5, 7, 8, 10],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "harmonic": [0, 2, 3, 5, 7, 8, 11],
    "major": [0, 2, 4, 5, 7, 9, 11],
    "lydian": [0, 2, 4, 6, 7, 9, 11],
}


@dataclass
class Mood:
    bpm: tuple[int, int]
    scales: tuple[str, ...]
    progressions: tuple[tuple[int, ...], ...]  # scale degrees, one chord per bar
    lead: str  # pluck | piano | bell
    bass: str  # pulse | walk | drone | drive
    drums: str  # none | soft | pop | drive | trap
    root: tuple[int, int]  # MIDI range for the key


MOOD_SPECS = {
    "mystery": Mood((78, 92), ("minor", "dorian", "harmonic"), ((0, 5, 3, 4), (0, 6, 5, 6), (0, 3, 6, 4)), "bell", "pulse", "soft", (43, 50)),
    "suspense": Mood((96, 118), ("minor", "harmonic", "phrygian"), ((0, 0, 5, 4), (0, 6, 5, 4), (0, 1, 0, 6)), "pluck", "drive", "drive", (40, 47)),
    "emotional": Mood((64, 78), ("major", "minor"), ((0, 4, 5, 3), (5, 3, 0, 4), (0, 5, 3, 4)), "piano", "walk", "none", (45, 52)),
    "uplifting": Mood((100, 116), ("major", "lydian"), ((0, 4, 5, 3), (3, 4, 0, 5), (0, 3, 4, 4)), "pluck", "walk", "pop", (45, 52)),
    "curious": Mood((104, 122), ("major", "dorian"), ((0, 3, 4, 3), (0, 5, 3, 4), (1, 4, 0, 5)), "pluck", "walk", "soft", (45, 52)),
    "dark": Mood((66, 80), ("phrygian", "minor"), ((0, 1, 0, 6), (0, 5, 1, 0), (0, 6, 1, 0)), "bell", "drone", "soft", (36, 43)),
    "energetic": Mood((128, 146), ("minor", "dorian"), ((0, 5, 3, 6), (0, 3, 6, 5), (0, 6, 3, 4)), "pluck", "drive", "trap", (40, 47)),
    "calm": Mood((80, 94), ("major", "lydian", "dorian"), ((0, 3, 0, 4), (0, 5, 3, 4), (3, 0, 4, 0)), "piano", "walk", "none", (45, 52)),
}


# ---------- small DSP helpers ----------

def _t(seconds: float) -> np.ndarray:
    return np.arange(max(1, int(RATE * seconds))) / RATE


def _mtof(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def _filt(x: np.ndarray, kind: str, freq) -> np.ndarray:
    sos = butter(2, freq, btype=kind, fs=RATE, output="sos")
    return sosfilt(sos, x)


def _env(n: int, attack: float, release: float, hold: float | None = None) -> np.ndarray:
    t = np.arange(n) / RATE
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    end = n / RATE if hold is None else hold
    r = np.clip((end - t) / max(release, 1e-4), 0, 1) if release else 1.0
    return a * r


def _add(buf: np.ndarray, x: np.ndarray, at: float, gain: float = 1.0) -> None:
    i = int(at * RATE)
    if i >= len(buf) or i + len(x) <= 0:
        return
    if i < 0:
        x, i = x[-i:], 0
    j = min(len(buf), i + len(x))
    buf[i:j] += x[: j - i] * gain


def _reverb(x: np.ndarray, mix: float = 0.25) -> np.ndarray:
    """A few decaying echoes: enough space for pads and plucks without a real reverb."""
    out = x.copy()
    for delay, g in ((0.043, 0.5), (0.071, 0.4), (0.113, 0.32), (0.197, 0.22), (0.29, 0.14)):
        d = int(delay * RATE)
        out[d:] += x[:-d] * g * mix * 2
    return out


def _write(path: Path, x: np.ndarray, peak: float = 0.6) -> Path:
    x = x / (np.abs(x).max() or 1.0) * peak
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
    return path


# ---------- instruments ----------

_cache: dict = {}


def _cached(key, make):
    if key not in _cache:
        if len(_cache) > 4000:
            _cache.clear()
        _cache[key] = make()
    return _cache[key]


def kick(punch: float = 1.0) -> np.ndarray:
    def make():
        t = _t(0.45)
        f = 45 + 110 * np.exp(-t * 28)
        body = np.sin(2 * np.pi * np.cumsum(f) / RATE) * np.exp(-t * 7)
        click = np.random.default_rng(1).standard_normal(len(t)) * np.exp(-t * 300) * 0.3
        return np.tanh((body + click) * 1.6 * punch)
    return _cached(("kick", punch), make)


def snare() -> np.ndarray:
    def make():
        t = _t(0.3)
        noise = _filt(np.random.default_rng(2).standard_normal(len(t)), "band", [1500, 6000]) * np.exp(-t * 16)
        tone = np.sin(2 * np.pi * 190 * t) * np.exp(-t * 30) * 0.6
        return noise * 1.4 + tone
    return _cached("snare", make)


def hat(open_: bool = False) -> np.ndarray:
    def make():
        t = _t(0.35 if open_ else 0.06)
        n = _filt(np.random.default_rng(3).standard_normal(len(t)), "high", 7000)
        return n * np.exp(-t * (11 if open_ else 70))
    return _cached(("hat", open_), make)


def tick(pitch: float = 3200) -> np.ndarray:
    """The short 'ti' of a ticking pulse: a clicky blip."""
    def make():
        t = _t(0.035)
        return (np.sin(2 * np.pi * pitch * t) + 0.5 * np.sin(2 * np.pi * pitch * 1.51 * t)) * np.exp(-t * 140)
    return _cached(("tick", pitch), make)


def bass(freq: float, dur: float, bright: float = 700) -> np.ndarray:
    def make():
        t = _t(dur)
        saw = sum(np.sin(2 * np.pi * freq * k * t) / k for k in range(1, 9))
        return _filt(saw + np.sin(2 * np.pi * freq / 2 * t) * 0.8, "low", bright) * _env(len(t), 0.006, min(0.08, dur / 2))
    return _cached(("bass", round(freq, 2), round(dur, 3), bright), make)


def pad(freqs: list[float], dur: float, dark: bool = False) -> np.ndarray:
    def make():
        t = _t(dur + 0.8)
        x = np.zeros_like(t)
        for f in freqs:
            for det in (0.996, 1.0, 1.004):
                x += sum(np.sin(2 * np.pi * f * det * k * t) / (k * k) for k in range(1, 5))
        x = _filt(x, "low", 900 if dark else 1600)
        return x * _env(len(t), 0.5, 0.8, dur + 0.8)
    return _cached(("pad", tuple(round(f, 2) for f in freqs), round(dur, 2), dark), make)


def pluck(freq: float) -> np.ndarray:
    def make():
        t = _t(0.9)
        return sum(np.sin(2 * np.pi * freq * k * t) * np.exp(-t * (5 + 4 * k)) / k for k in range(1, 6))
    return _cached(("pluck", round(freq, 2)), make)


def piano(freq: float) -> np.ndarray:
    def make():
        t = _t(2.2)
        amps = (1, 0.45, 0.25, 0.15, 0.08, 0.05)
        x = sum(a * np.sin(2 * np.pi * freq * k * 1.0008 ** k * t) * np.exp(-t * (1.6 + 0.9 * k)) for k, a in enumerate(amps, 1))
        return x * _env(len(t), 0.004, 0.3)
    return _cached(("piano", round(freq, 2)), make)


def bell(freq: float) -> np.ndarray:
    def make():
        t = _t(2.5)
        return sum(a * np.sin(2 * np.pi * freq * r * t) * np.exp(-t * d) for r, a, d in
                   ((1, 1, 1.4), (2.76, 0.5, 2.6), (5.4, 0.25, 4.5), (8.9, 0.1, 7)))
    return _cached(("bell", round(freq, 2)), make)


def stab(freqs: list[float], length: float = 0.28) -> np.ndarray:
    """A short brassy chord hit."""
    def make():
        t = _t(length + 0.2)
        x = sum(sum(np.sin(2 * np.pi * f * k * t) / k for k in range(1, 10)) for f in freqs)
        x = _filt(x, "low", 2400) * np.exp(-t * (1 / max(length, 0.05)) * 2.2)
        return x * _env(len(t), 0.004, 0.05)
    return _cached(("stab", tuple(round(f, 2) for f in freqs), length), make)


def riser(seconds: float) -> np.ndarray:
    t = _t(seconds)
    x = t / seconds
    noise = _filt(np.random.default_rng(5).standard_normal(len(t)), "high", 900) * x ** 2.5
    tone = np.sin(2 * np.pi * np.cumsum(120 + 900 * x ** 2) / RATE) * x ** 2 * 0.5
    return noise * 0.7 + tone


def boom(size: float = 1.0) -> np.ndarray:
    def make():
        t = _t(2.2)
        f = 30 + 70 * np.exp(-t * 5)
        body = np.tanh(2.4 * np.sin(2 * np.pi * np.cumsum(f) / RATE)) * np.exp(-t * 1.8)
        crack = _filt(np.random.default_rng(9).standard_normal(len(t)), "low", 3000) * np.exp(-t * 18) * 0.5
        return (body + crack) * size
    return _cached(("boom", size), make)


def swell_reverse(seconds: float = 1.2) -> np.ndarray:
    t = _t(seconds)
    x = _filt(np.random.default_rng(11).standard_normal(len(t)), "band", [300, 4000]) * np.exp(-t * 3)
    return x[::-1]


# ---------- the main track ----------

@dataclass
class Section:
    start: float
    end: float
    intensity: float  # 0..1
    drop: bool = False  # silence just before the start, then a hit


def _chord(scale: list[int], degree: int, root: int, octave: int = 0) -> list[float]:
    notes = []
    for k in (0, 2, 4):
        d = degree + k
        notes.append(_mtof(root + 12 * octave + scale[d % 7] + 12 * (d // 7)))
    return notes


def compose(mood: str, sections: list[Section], seconds: float, seed: int, out: Path) -> Path:
    spec = MOOD_SPECS.get(mood, MOOD_SPECS["calm"])
    rng = np.random.default_rng(seed)
    bpm = int(rng.integers(spec.bpm[0], spec.bpm[1] + 1))
    beat = 60 / bpm
    bar = beat * 4
    step = beat / 4
    scale = SCALES[spec.scales[int(rng.integers(len(spec.scales)))]]
    prog = spec.progressions[int(rng.integers(len(spec.progressions)))]
    root = int(rng.integers(spec.root[0], spec.root[1] + 1))
    lead_voice = {"pluck": pluck, "piano": piano, "bell": bell}[spec.lead]
    arp_shape = [(0, 1, 2, 1), (0, 2, 1, 2), (0, 1, 2, 3), (2, 1, 0, 1)][int(rng.integers(4))]
    hat_pattern = [(1, 0, 1, 0), (1, 1, 1, 1), (1, 0, 1, 1), (0, 1, 0, 1)][int(rng.integers(4))]
    bass_rhythm = {"pulse": (0, 8), "walk": (0, 4, 8, 12), "drone": (0,), "drive": tuple(range(0, 16, 2))}[spec.bass]

    n = int(RATE * (seconds + 3))
    pads, low, lead, drums, fx = (np.zeros(n) for _ in range(5))

    def level(t: float) -> float:
        for s in sections:
            if s.start <= t < s.end:
                return s.intensity
        return sections[-1].intensity if sections else 0.4

    drops = [s.start for s in sections if s.drop and s.start > 2]
    bars = int(seconds / bar) + 1
    for b in range(bars):
        t0 = b * bar
        lv = level(t0 + 0.01)
        nxt = level(t0 + bar + 0.01)
        degree = prog[b % len(prog)]
        chord = _chord(scale, degree, root, 1)
        # Pad: always there, fuller with intensity.
        _add(pads, pad(chord, bar, dark=spec.bass == "drone"), t0, 0.25 + 0.3 * lv)
        # Bass from low intensity up.
        if lv >= 0.25:
            f = _mtof(root + scale[degree % 7] - 12)
            for s in bass_rhythm:
                d = step * (4 if spec.bass != "drone" else 16)
                _add(low, bass(f, d * 0.9, 500 + 900 * lv), t0 + s * step, 0.55 + 0.3 * lv)
        # Arps / melody.
        if lv >= 0.45:
            per = 2 if lv < 0.75 else 1  # 8ths, or 16ths when it's intense
            notes = _chord(scale, degree, root, 2) + [_mtof(root + 36 + scale[(degree + 7) % 7])]
            for i in range(0, 16, per):
                if rng.random() < (0.35 if spec.lead == "bell" else 0.85):
                    _add(lead, lead_voice(notes[arp_shape[(i // per) % 4]]), t0 + i * step, 0.3)
        # Percussion.
        if spec.drums != "none" or lv >= 0.85:
            if lv >= 0.35:
                for i in range(16):
                    if hat_pattern[i % 4] and (lv > 0.6 or i % 2 == 0):
                        _add(drums, tick(2800) if spec.drums in ("soft", "none") else hat(), t0 + i * step, 0.18 + 0.2 * lv)
            if lv >= 0.6:
                kicks = {"drive": (0, 4, 8, 12), "trap": (0, 6, 10), "pop": (0, 8), "soft": (0, 10), "none": (0,)}[spec.drums]
                for k in kicks:
                    _add(drums, kick(), t0 + k * step, 0.7)
                for sn in ((4, 12) if spec.drums in ("drive", "pop", "trap") else (12,)):
                    _add(drums, snare(), t0 + sn * step, 0.45)
            # A fill into a louder section.
            if nxt > lv + 0.2:
                for i in range(12, 16):
                    _add(drums, snare(), t0 + i * step, 0.2 + 0.08 * (i - 11))
    # Drops: a riser into it, silence just before, then a hit.
    for d in drops:
        _add(fx, riser(min(4.0, bar * 2)), d - min(4.0, bar * 2) - 0.35, 0.35)
        _add(fx, boom(), d, 0.9)
    mix = _reverb(pads + lead * 0.8, 0.3) + low + drums * 0.9 + fx
    for d in drops:  # the silence before the drop
        i, j = int((d - 0.35) * RATE), int(d * RATE)
        mix[max(0, i):max(0, j)] *= np.linspace(1, 0, max(0, j) - max(0, i)) ** 3 if j > i else 1
    mix = mix[: int(RATE * seconds)]
    fade = min(len(mix), int(RATE * 2))
    mix[-fade:] *= np.linspace(1, 0, fade)
    return _write(out, np.tanh(mix / (np.abs(mix).max() or 1) * 1.4))


# ---------- the hook's trailer track ----------

def clap() -> np.ndarray:
    def make():
        t = _t(0.25)
        n = _filt(np.random.default_rng(13).standard_normal(len(t)), "band", [900, 3500])
        env = sum(np.exp(-np.clip(t - d, 0, None) * 60) * (t >= d) for d in (0, 0.012, 0.024)) + np.exp(-t * 14) * 0.5
        return n * env
    return _cached("clap", make)


def tom(freq: float = 110) -> np.ndarray:
    def make():
        t = _t(0.6)
        f = freq * (1 + 0.6 * np.exp(-t * 18))
        return np.sin(2 * np.pi * np.cumsum(f) / RATE) * np.exp(-t * 6)
    return _cached(("tom", freq), make)


TRAILER_SPECS = {
    # bpm range, hats (tick = the 'ti-ti-ti' spy rhythm), bass pattern (scale degrees per 8th), stab voice, lead voice
    "spy-pulse": ((132, 142), "tick", (0, 0, 3, 0, 5, 0, 3, 7), "stab", "pluck"),
    "glitch-drive": ((138, 150), "glitch", (0, 0, 0, 3, 0, 0, 5, 3), "stab", "bell"),
    "ticking-clock": ((122, 130), "clock", (0, 7, 0, 5, 0, 3, 0, 5), "piano", "piano"),
    "dark-pulse": ((112, 124), "tom", (0, 0, 1, 0, 0, 0, 6, 5), "stab", "bell"),
}


def trailer(style: str, seconds: float, cuts: list[float], seed: int, out: Path) -> Path:
    """An energetic, original trailer track for the hook, built like an action/spy intro:
    a short build, then a driving groove (four-on-the-floor kick, backbeat clap, ticking hats,
    a minor bass ostinato, stabs), a lead that joins for the second half, a snare roll and a
    riser into the final cut, a moment of silence and a big hit. `cuts` are the shot changes."""
    bpm_range, hats, riff, stab_voice, lead_voice = TRAILER_SPECS.get(style, TRAILER_SPECS["spy-pulse"])
    rng = np.random.default_rng(seed)
    bpm = int(rng.integers(bpm_range[0], bpm_range[1] + 1))
    s16 = 60 / bpm / 4
    root = int(rng.integers(38, 44))
    minor = SCALES["harmonic" if rng.random() < 0.5 else "minor"]
    prog = [(0, 5, 3, 4), (0, 6, 5, 4), (0, 3, 5, 4)][int(rng.integers(3))]
    final = seconds
    groove_in = min(3.2, final * 0.12)  # the build before the beat drops in
    roll_from = final - min(3.5, final * 0.15)
    n = int(RATE * (final + 2.5))
    drums, bass_buf, music_buf, fx = (np.zeros(n) for _ in range(4))
    note = lambda deg, octave=0: _mtof(root + 12 * octave + minor[deg % 7] + 12 * (deg // 7))
    lead_fn = {"pluck": pluck, "bell": bell, "piano": piano}[lead_voice]
    arp = [(0, 2, 4, 2), (0, 4, 2, 4), (4, 2, 0, 2)][int(rng.integers(3))]

    # The build: a riser and a ticking pulse into the drop of the beat.
    _add(fx, riser(groove_in), 0, 0.5)
    t, i = 0.0, 0
    while t < final - 0.32:
        p = t / final
        step, beat = i % 16, (i // 4) % 4
        bar = i // 16
        chord_deg = prog[bar % len(prog)]
        grooving = t >= groove_in and t < roll_from
        # hats / the ticking rhythm (all the way, louder as it goes)
        if hats == "tick" and (step % 2 == 0 or rng.random() < 0.55):
            _add(drums, tick(3000 if step % 4 else 3700), t, 0.28 + 0.25 * p)
        elif hats == "glitch":
            _add(drums, hat(), t, 0.22 + 0.2 * p)
            if rng.random() < 0.12:
                for r in range(3):
                    _add(drums, tick(4200 + 600 * r), t + r * s16 / 3, 0.25)
        elif hats == "clock" and step % 4 == 0:
            _add(drums, tick(2400 if beat % 2 else 1800), t, 0.5)
        elif hats == "tom" and step in (0, 3, 6, 10, 12, 14):
            _add(drums, tom(98 if step < 8 else 82), t, 0.55)
        if hats != "tick" and step % 2 == 1 and t >= groove_in:
            _add(drums, hat(), t, 0.16 + 0.15 * p)
        if grooving:
            if step % 4 == 0:
                _add(drums, kick(), t, 0.85)
            if step in (4, 12):
                _add(drums, clap(), t, 0.55)
                _add(drums, snare(), t, 0.25)
            if step == 14 and bar % 2:
                _add(drums, hat(True), t, 0.22)
            # driving bass: every 8th, the riff over the chord root
            if step % 2 == 0:
                deg = chord_deg + riff[(step // 2) % 8]
                _add(bass_buf, bass(note(deg, -1), s16 * 1.8, 500 + 1500 * p), t, 0.7)
            # stabs on the downbeat and the 'and' of 2, every bar after the first
            if step in (0, 6) and bar % 2 == 0:
                chord = [note(chord_deg + k, 1) for k in (0, 2, 4)]
                _add(music_buf, stab(chord, 0.22) if stab_voice == "stab" else sum(piano(f) for f in chord), t, 0.4)
            # the lead joins for the second half
            if p > 0.45 and step % 2 == 0:
                _add(music_buf, lead_fn(note(chord_deg + arp[(step // 2) % 4], 2)), t, 0.22)
        if step == 0 and t >= groove_in:  # a pad under it all, for harmony
            _add(music_buf, pad([note(chord_deg + k, 0) for k in (0, 2, 4)], s16 * 16, dark=True), t, 0.22)
        if t >= roll_from:  # snare roll speeding up into the cut
            roll = 1 if (t - roll_from) / (final - roll_from) > 0.5 else 2
            if i % roll == 0:
                _add(drums, snare(), t, 0.25 + 0.45 * (t - roll_from) / (final - roll_from))
        t += s16
        i += 1
    # Hits on the shot changes, a riser into the final cut, silence, then the big hit.
    for c in cuts[:-1]:
        _add(fx, boom(0.45), c, 0.3)
    _add(fx, riser(min(4.0, final * 0.2)), final - min(4.0, final * 0.2) - 0.3, 0.55)
    x = drums * 0.9 + bass_buf * 0.75 + _reverb(music_buf, 0.3) * 0.8 + fx
    i0, i1 = int((final - 0.3) * RATE), int(final * RATE)
    x[i0:i1] *= np.linspace(1, 0.02, i1 - i0) ** 2
    x[i1:] = 0
    _add(x, boom(1.0), final, 1.1)
    _add(x, stab([note(0, 0), note(2, 0), note(4, 0)], 0.6), final, 0.6)
    x = x[: int(RATE * (final + 1.8))]
    x[-int(RATE * 0.8):] *= np.linspace(1, 0, int(RATE * 0.8))
    return _write(out, np.tanh(x / (np.abs(x).max() or 1) * 1.6), peak=0.75)


# ---------- ambience beds ----------

def _brown(n: int, rng) -> np.ndarray:
    b = np.cumsum(rng.standard_normal(n))
    b -= _filt(b, "low", 2)  # remove the drift
    return b / (np.abs(b).max() or 1)


def ambience(kind: str, seconds: float, seed: int, out: Path) -> Path | None:
    if kind not in AMBIENCES or kind == "none":
        return None
    rng = np.random.default_rng(seed)
    n = int(RATE * seconds)
    t = np.arange(n) / RATE
    if kind == "room":
        x = _filt(rng.standard_normal(n), "low", 350) * 0.6 + 0.08 * np.sin(2 * np.pi * 100 * t)
    elif kind == "city":
        x = _filt(_brown(n, rng), "low", 700)
        for _ in range(int(seconds / 6)):  # passing cars
            at, d = rng.uniform(0, seconds), rng.uniform(2, 4)
            car = _filt(rng.standard_normal(int(RATE * d)), "band", [200, 1500]) * np.sin(np.linspace(0, np.pi, int(RATE * d))) ** 2
            _add(x, car, at, 0.5)
    elif kind == "rain":
        x = _filt(rng.standard_normal(n), "band", [900, 7000]) * (0.8 + 0.2 * np.sin(2 * np.pi * 0.13 * t))
        drops = np.zeros(n)
        drops[rng.integers(0, n, int(seconds * 25))] = rng.uniform(0.5, 1.5, int(seconds * 25))
        x += _filt(drops, "high", 2000) * 2
    elif kind == "wind":
        x = _filt(_brown(n, rng), "band", [150, 1200]) * (0.5 + 0.5 * np.sin(2 * np.pi * t / rng.uniform(5, 9)) ** 2)
    elif kind == "crowd":
        x = _filt(rng.standard_normal(n), "band", [300, 1800]) * (0.6 + 0.4 * np.abs(np.sin(2 * np.pi * 3.3 * t + np.sin(2 * np.pi * 0.7 * t) * 3)))
    elif kind == "night":
        x = _filt(rng.standard_normal(n), "low", 300) * 0.3
        for _ in range(int(seconds * 1.2)):  # crickets
            at = rng.uniform(0, seconds)
            ch = np.sin(2 * np.pi * 4600 * _t(0.12)) * (np.sin(2 * np.pi * 30 * _t(0.12)) > 0)
            _add(x, ch, at, 0.12)
    elif kind == "lab":
        x = sum(np.sin(2 * np.pi * 120 * k * t) / k for k in (1, 2, 3)) * 0.15 + _filt(rng.standard_normal(n), "low", 500) * 0.3
        for _ in range(int(seconds / 5)):
            _add(x, np.sin(2 * np.pi * 1760 * _t(0.12)) * _env(int(RATE * 0.12), 0.005, 0.03), rng.uniform(0, seconds), 0.12)
    elif kind == "sea":
        x = _filt(_brown(n, rng), "low", 900) * (0.3 + 0.7 * np.sin(np.pi * t / rng.uniform(6, 9)) ** 4)
    else:  # fire
        x = _filt(_brown(n, rng), "low", 400) * 0.6
        pops = np.zeros(n)
        pops[rng.integers(0, n, int(seconds * 12))] = rng.uniform(0.3, 1, int(seconds * 12))
        x += _filt(pops, "band", [1000, 5000]) * 3
    fade = min(n, RATE)
    x[:fade] *= np.linspace(0, 1, fade)
    x[-fade:] *= np.linspace(1, 0, fade)
    return _write(out, x, peak=0.5)
