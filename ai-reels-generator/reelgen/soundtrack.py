"""The soundtrack of a long video (Long, StickStory) mixed straight from its props with ffmpeg and numpy.

Remotion's own sound pass loads every sound file from a small file server in the render process, and on
the user's laptop that server refused connections whenever many sounds started close together
(ECONNREFUSED on rumble-lv.wav, then heartbeat-lv.wav, minute 11 of an 11-minute Script Video, three
tries in a row, after a single pass had already timed out at one hour). This mixes the same sounds with the
same rules as the editor (remotion/src/Sound.tsx, long/Long.tsx, story/Story.tsx) in seconds, with no
browser and no server:

- every sound starts on the frame its <Sequence> starts (round(seconds * fps)) and plays until its file
  ends, its Sequence ends or the video ends;
- music loops and follows `Music`'s level: `duck` under speech, `full` in the pauses (0.35 s ramps),
  15 frames fade-in and 45 frames fade-out over its own Sequence, stepping aside (1.2 s ramps) in `mute`;
- an effect plays at its volume, halved when it lands within 0.15 s of speech (SPEECH_DUCK);
- volume is set per video frame, as Remotion does.

Keep this in step with those files: a change to how the editor plays a sound must change this too.
"""

from __future__ import annotations

import logging
import subprocess
import wave
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

RATE = 48000
DUCK_RAMP = 0.35
MUTE_RAMP = 1.2
SPEECH_DUCK = 0.5


def _interp(x, xs, ys):
    """Remotion's interpolate() with extrapolation clamped."""
    return np.interp(x, xs, ys)


class Mixer:
    def __init__(self, ffmpeg: str, public: Path, fps: int, frames: int):
        self.ffmpeg, self.public, self.fps, self.frames = ffmpeg, public, fps, frames
        self.spf = RATE / fps  # samples per frame (1600 at 30 fps)
        self.out = np.zeros((int(round(frames * self.spf)), 2), dtype=np.float32)
        self._cache: dict[str, np.ndarray] = {}

    def _load(self, src: str) -> np.ndarray:
        if src not in self._cache:
            path = self.public / src
            raw = subprocess.run([self.ffmpeg, "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "2",
                                  "-ar", str(RATE), "-"], capture_output=True, check=True).stdout
            data = np.frombuffer(raw, dtype=np.float32).reshape(-1, 2)
            if len(data) > RATE * 60:  # a track over a minute is used once: not kept in memory
                return data
            self._cache[src] = data
        return self._cache[src]

    def add(self, src: str, start_frame: int, *, length_frames: int | None = None, volume=1.0,
            loop: bool = False, trim_frames: int = 0) -> None:
        """One <Audio> inside a <Sequence from=start_frame durationInFrames=length_frames>. `volume` is a
        number or a function of the frame since the sound started (numpy array in, array out)."""
        if not src or start_frame >= self.frames:
            return
        data = self._load(src)[int(round(trim_frames * self.spf)):]
        if not len(data):
            return
        seq_frames = self.frames - start_frame if length_frames is None else min(length_frames, self.frames - start_frame)
        if seq_frames <= 0:
            return
        n = int(round(seq_frames * self.spf))
        if not loop:
            n = min(n, len(data))
        a = int(round(start_frame * self.spf))
        n = min(n, len(self.out) - a)
        # Mixed in 10-second blocks, reading the file in place (a loop wraps around it): no full-length
        # copies of an 11-minute track on a laptop that is short of memory.
        block = RATE * 10
        for i in range(0, n, block):
            idx = np.arange(i, min(n, i + block))
            piece = data[idx % len(data)] if loop else data[i:i + len(idx)]
            if callable(volume):
                frames = (idx / self.spf).astype(int)
                gain = np.asarray(volume(frames.astype(np.float64)), dtype=np.float32)
                piece = piece * gain[:, None]
            else:
                piece = piece * np.float32(volume)
            self.out[a + i:a + i + len(idx)] += piece

    def write(self, path: Path) -> None:
        with wave.open(str(path), "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(RATE)
            for i in range(0, len(self.out), RATE * 10):
                w.writeframes((np.clip(self.out[i:i + RATE * 10], -1.0, 1.0) * 32767).astype("<i2").tobytes())


def _music_level(fps: int, seq_frames: int, speech, full: float, duck: float, mute=()):
    """`Music`'s level(frame) from Sound.tsx, for an array of frames."""
    spans = sorted((float(a), float(b)) for a, b in speech)

    def level(frame: np.ndarray) -> np.ndarray:
        t = frame / fps
        if spans:
            dist = np.full(t.shape, np.inf)
            for a, b in spans:
                d = np.where(t < a, a - t, np.where(t > b, t - b, 0.0))
                dist = np.minimum(dist, d)
            k = _interp(dist, [0.05, DUCK_RAMP], [0, 1])
        else:
            k = np.ones_like(t)
        fade = _interp(frame, [0, 15, seq_frames - 45, seq_frames], [0, 1, 1, 0])
        away = np.ones_like(t)
        for a, b in mute:
            away = np.minimum(away, _interp(t, [a - MUTE_RAMP, a, b, b + MUTE_RAMP], [1, 0, 0, 1]))
        return (duck + (full - duck) * k) * fade * away

    return level


def _in_speech(at: float, speech) -> bool:
    return any(a - 0.15 <= at <= b + 0.15 for a, b in speech)


def _cues(m: Mixer, cues, speech) -> None:
    for c in cues or []:
        vol = float(c.get("volume", 1)) * (SPEECH_DUCK if _in_speech(float(c["at"]), speech) else 1)
        m.add(c["src"], round(float(c["at"]) * m.fps), volume=vol, trim_frames=round(float(c.get("trim") or 0) * m.fps))


def _long(m: Mixer, p: dict) -> None:
    f = lambda s: round(float(s) * m.fps)  # noqa: E731
    speech = p.get("speech") or []
    hook = p.get("hook") or {}
    for s in hook.get("shots") or []:
        if s.get("audio"):
            m.add(s["audio"], f(s["start"]))
    for b in p.get("beats") or []:
        if b.get("audio"):
            m.add(b["audio"], f(b["start"]))
    if hook.get("music"):
        n = f(hook["duration"] + 1.8)
        m.add(hook["music"], 0, length_frames=n, volume=_music_level(
            m.fps, min(n, m.frames), [s for s in speech if s[0] < hook["duration"]], 0.62, 0.3))
    music_from = float(p.get("musicFrom") or 0)
    parts = p.get("musicParts") or []
    if p.get("music"):
        start = f(music_from)
        m.add(p["music"], start, loop=True, volume=_music_level(
            m.fps, m.frames - start, [(a - music_from, b - music_from) for a, b in speech], 0.18, 0.065,
            [(x["from"] - music_from, x["to"] - music_from) for x in parts]))
    for x in parts:
        start, n = f(x["from"]), max(1, f(x["to"] - x["from"]))
        m.add(x["src"], start, length_frames=n, loop=True, volume=_music_level(
            m.fps, min(n, m.frames - start), [(a - x["from"], b - x["from"]) for a, b in speech], 0.16, 0.06))
    for a in p.get("ambience") or []:
        n = max(1, f(a["to"] - a["from"]))
        m.add(a["src"], f(a["from"]), length_frames=n, loop=True,
              volume=lambda fr, n=n: _interp(fr, [0, 30, n - 30, n], [0, 0.1, 0.1, 0]))
    _cues(m, p.get("cues"), speech)
    sfx = p.get("sfx") or {}
    if sfx.get("whoosh"):
        for c in p.get("chapters") or []:
            if c.get("card", 0) > 0 and not c.get("style"):
                m.add(sfx["whoosh"], max(0, f(c["start"]) - 3), length_frames=f(1.2), volume=0.3)


def _story(m: Mixer, p: dict) -> None:
    f = lambda s: round(float(s) * m.fps)  # noqa: E731
    speech = p.get("speech") or []
    for s in p.get("shots") or []:
        if s.get("audio"):
            m.add(s["audio"], f(float(s["start"]) + float(s.get("lead") or 0)))
    if p.get("music"):
        m.add(p["music"], 0, loop=True, volume=_music_level(m.fps, m.frames, speech, 0.16, 0.06))
    _cues(m, p.get("cues"), speech)


def _toon(m: Mixer, p: dict) -> None:
    """remotion/src/toon/Toon.tsx: each shot's voice at its start + lead, the music under it all, the cues."""
    f = lambda s: round(float(s) * m.fps)  # noqa: E731
    speech = p.get("speech") or []
    for s in p.get("shots") or []:
        if s.get("audio"):
            m.add(s["audio"], f(float(s["start"]) + float(s.get("lead") or 0)))
    if p.get("music"):
        m.add(p["music"], 0, loop=True, volume=_music_level(m.fps, m.frames, speech, 0.17, 0.06))
    _cues(m, p.get("cues"), speech)


def mix(props: dict, composition: str, public: Path, out: Path, ffmpeg: str) -> None:
    """Write the soundtrack of `props` to `out` (48 kHz stereo WAV, exactly the video's length)."""
    fps = int(props.get("fps") or 30)
    frames = max(1, int(np.ceil(float(props["duration"]) * fps)))
    m = Mixer(ffmpeg, public, fps, frames)
    if composition == "Long":
        _long(m, props)
    elif composition == "StickStory":
        _story(m, props)
    elif composition == "Toon":
        _toon(m, props)
    else:
        raise ValueError(f"No soundtrack mixer for {composition}")
    m.write(out)
    log.info("Mixed the soundtrack (%.1f min)", frames / fps / 60)
