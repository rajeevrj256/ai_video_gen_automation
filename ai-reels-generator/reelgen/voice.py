"""Text-to-speech voiceover with word-level timings (for the animated captions).

Two engines:
- "edge": Microsoft Edge's neural voices through the free `edge-tts` package (online,
  no API key, exact word timings). List voices with: `edge-tts --list-voices`.
- "kokoro": the open-source Kokoro model running on this computer (offline). The
  model (~350 MB) downloads once on first use. Word timings are estimated.

"auto" (the default) uses edge and falls back to kokoro when Microsoft's service
refuses the connection — it does that for some networks and cloud servers.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
import threading
import ssl
import wave
from dataclasses import dataclass
from pathlib import Path

import edge_tts
import imageio_ffmpeg
import numpy as np
import requests
from edge_tts import communicate as _edge_communicate

from .config import PROJECT_ROOT

log = logging.getLogger(__name__)
logging.getLogger("phonemizer").setLevel(logging.ERROR)  # noisy, harmless word-count warnings

TICKS_PER_SECOND = 10_000_000  # edge-tts reports offsets in 100 ns units

# edge-tts only trusts certifi's CA list. Behind a proxy that inspects TLS (office
# networks, some cloud machines) the proxy's CA comes via SSL_CERT_FILE, so honour it.
if os.environ.get("SSL_CERT_FILE") and hasattr(_edge_communicate, "_SSL_CTX"):
    _edge_communicate._SSL_CTX = ssl.create_default_context(cafile=os.environ["SSL_CERT_FILE"])

KOKORO_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
KOKORO_FILES = ("kokoro-v1.0.onnx", "voices-v1.0.bin")
MODEL_DIR = PROJECT_ROOT / "assets" / "models"
SENTENCE_PAUSE, CLAUSE_PAUSE = 0.25, 0.1  # seconds of silence Kokoro puts at . and ,

# Closest Kokoro voice (and espeak language) for each voice offered in the app.
KOKORO_FOR_EDGE = {
    "en-US-AndrewMultilingualNeural": "am_michael",
    "en-US-BrianMultilingualNeural": "am_puck",
    "en-US-AvaMultilingualNeural": "af_heart",
    "en-US-EmmaMultilingualNeural": "af_heart",
    "en-US-AndrewNeural": "am_michael",
    "en-US-AvaNeural": "af_heart",
    "en-US-BrianNeural": "am_puck",
    "en-GB-RyanNeural": "bm_george",
    "en-IN-PrabhatNeural": "am_michael",
    "en-IN-NeerjaNeural": "af_heart",
    "hi-IN-MadhurNeural": "hm_omega",
    "hi-IN-SwaraNeural": "hf_alpha",
}
KOKORO_LANG = {"a": "en-us", "b": "en-gb", "h": "hi", "e": "es", "f": "fr-fr", "i": "it", "p": "pt-br"}


@dataclass
class Word:
    text: str
    start: float  # seconds, relative to the start of its scene audio
    end: float


@dataclass
class SceneAudio:
    path: Path
    words: list[Word]


def synthesize_scenes(narrations: list[str], voice: str, out_dir: Path, engine: str = "auto",
                      kokoro_voice: str = "", rate: str = "+10%") -> list[SceneAudio]:
    """One audio file per scene, so each scene's duration follows its voiceover.

    The whole narration is spoken in one take and then cut between scenes. Speaking
    each scene on its own restarts the intonation every few seconds (every scene ends
    on the same falling "full stop" tone), which is what makes TTS sound like someone
    reading lines off a card. One take flows like a presenter explaining. `rate` is a
    steady pace for the whole take, e.g. "+10%".
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    pct = int(re.sub(r"[^\d-]", "", rate) or 0)
    if engine in ("auto", "edge"):
        try:
            return _edge_scenes(narrations, voice, out_dir, f"{pct:+d}%")
        except Exception as exc:
            if engine == "edge":
                raise
            log.warning("Microsoft voice unavailable (%s); using the offline Kokoro voice", exc)
    return _kokoro_scenes(narrations, kokoro_voice or KOKORO_FOR_EDGE.get(voice) or _kokoro_default(voice),
                          out_dir, 1 + pct / 100)


# ---------- one take, cut into scenes ----------

def _letters(text: str) -> int:
    return len(re.sub(r"[\W_]", "", text))


def _scene_of_words(narrations: list[str], words: list[Word]) -> list[int]:
    """Which scene each spoken word belongs to, matched by position in the text (the
    engine's words don't always split on the same spaces, so count letters)."""
    ends, total = [], 0
    for text in narrations:
        total += _letters(text)
        ends.append(total)
    out, pos = [], 0
    for w in words:
        n = _letters(w.text)
        mid = pos + n / 2
        out.append(next((i for i, e in enumerate(ends) if mid <= e), len(ends) - 1))
        pos += n
    return out


def _cut_scenes(samples: np.ndarray, rate: int, words: list[Word], scene_of: list[int],
                count: int, cuts: list[float], out_dir: Path) -> list[SceneAudio]:
    """Write scene_XX.wav files, cut at `cuts` (seconds, count-1 of them), with each
    scene's words shifted to its own start."""
    bounds = [0.0, *cuts, len(samples) / rate]
    results = []
    for i in range(count):
        a, b = bounds[i], bounds[i + 1]
        path = out_dir / f"scene_{i:02d}.wav"
        _write_wav(path, samples[int(a * rate):int(b * rate)], rate)
        results.append(SceneAudio(path, [Word(w.text, max(0.0, w.start - a), max(0.0, w.end - a))
                                         for w, s in zip(words, scene_of) if s == i]))
    return results


def _write_wav(path: Path, samples: np.ndarray, rate: int) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes((np.clip(samples, -1, 1) * 32767).astype(np.int16).tobytes())


# ---------- edge (online) ----------

async def _edge_synthesize(text: str, voice: str, rate: str, pitch: str, out_path: Path) -> list[Word]:
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, boundary="WordBoundary")
    words: list[Word] = []
    with open(out_path, "wb") as fh:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                fh.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / TICKS_PER_SECOND
                words.append(Word(chunk["text"], start, start + chunk["duration"] / TICKS_PER_SECOND))
    return words


def _edge_scenes(narrations: list[str], voice: str, out_dir: Path, rate: str) -> list[SceneAudio]:
    full = out_dir / "narration.mp3"
    words = asyncio.run(_edge_synthesize(" ".join(t.strip() for t in narrations), voice, rate, "+0Hz", full))
    scene_of = _scene_of_words(narrations, words)
    if sorted(set(scene_of)) != list(range(len(narrations))):
        raise RuntimeError("could not match the spoken words to the scenes")
    # Cut halfway through the pause between one scene's last word and the next one's first.
    cuts = []
    for i in range(1, len(narrations)):
        last = max(w.end for w, s in zip(words, scene_of) if s == i - 1)
        first = min(w.start for w, s in zip(words, scene_of) if s == i)
        cuts.append((last + first) / 2)
    samples, sr = _decode(full)
    return _cut_scenes(samples, sr, words, scene_of, len(narrations), cuts, out_dir)


def _decode(path: Path, rate: int = 24000) -> tuple[np.ndarray, int]:
    """Any audio file -> mono float samples, via ffmpeg."""
    raw = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-i", str(path), "-f", "s16le",
                          "-ac", "1", "-ar", str(rate), "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32767, rate


# ---------- kokoro (offline) ----------

_kokoro = None
_kokoro_lock = threading.Lock()  # parallel videos share one model; synthesis takes seconds


def _kokoro_default(edge_voice: str) -> str:
    if edge_voice.startswith("hi-"):
        return "hm_omega"
    if edge_voice.startswith("en-GB"):
        return "bm_george"
    return "af_heart"


def _load_kokoro():
    global _kokoro
    if _kokoro is None:
        from kokoro_onnx import Kokoro

        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        for name in KOKORO_FILES:
            path = MODEL_DIR / name
            if path.exists():
                continue
            log.info("Downloading the offline voice model %s (one time only)", name)
            part = path.with_name(name + ".part")
            with requests.get(KOKORO_URL + name, stream=True, timeout=60) as resp:
                resp.raise_for_status()
                with open(part, "wb") as fh:
                    for block in resp.iter_content(1 << 20):
                        fh.write(block)
            part.rename(path)
        _kokoro = Kokoro(str(MODEL_DIR / KOKORO_FILES[0]), str(MODEL_DIR / KOKORO_FILES[1]))
    return _kokoro


def _kokoro_scenes(narrations: list[str], voice: str, out_dir: Path, speed: float) -> list[SceneAudio]:
    with _kokoro_lock:
        kokoro = _load_kokoro()
        text = " ".join(t.strip() for t in narrations)
        samples, rate = kokoro.create(text, voice=voice, speed=speed, lang=KOKORO_LANG.get(voice[:1], "en-us"),
                                      sentence_pause=SENTENCE_PAUSE, clause_pause=CLAUSE_PAUSE)
    words = _estimate_words(text, samples, rate)
    counts = [len(t.split()) for t in narrations]
    scene_of = [i for i, n in enumerate(counts) for _ in range(n)]
    # Word times are estimates, so cut in the quietest spot of the pause near each boundary.
    cuts, k = [], 0
    for n in counts[:-1]:
        k += n
        cuts.append(_quietest(samples, rate, words[k - 1].end, words[k].start))
    return _cut_scenes(samples, rate, words, scene_of, len(narrations), cuts, out_dir)


def _quietest(samples: np.ndarray, rate: int, a: float, b: float, reach: float = 0.35) -> float:
    """The centre of the quietest 40 ms between a-reach and b+reach seconds."""
    win = int(0.04 * rate)
    lo, hi = max(0, int((a - reach) * rate)), min(len(samples) - win, int((b + reach) * rate))
    if hi <= lo:
        return (a + b) / 2
    energy = np.convolve(np.abs(samples[lo:hi + win]), np.ones(win), "valid")
    return (lo + int(np.argmin(energy)) + win / 2) / rate


def _syllables(word: str) -> float:
    groups = len(re.findall(r"[aeiouy]+", word.lower()))
    return (groups or max(1.0, len(word) / 3)) + 0.4  # non-Latin scripts: go by length


def _estimate_words(text: str, samples: np.ndarray, rate: int) -> list[Word]:
    """Kokoro gives no word timings, so spread the words over the speech by syllable
    count, leaving room for the pauses it inserts after punctuation."""
    words = text.split()
    if not words:
        return []
    loud = np.nonzero(np.abs(samples) > np.abs(samples).max() * 0.02)[0]
    start, end = (float(loud[0] / rate), float(loud[-1] / rate)) if len(loud) else (0.0, len(samples) / rate)

    def pause_after(w: str) -> float:
        return SENTENCE_PAUSE if w[-1] in ".!?" else CLAUSE_PAUSE if w[-1] in ",;:" else 0.0

    pauses = sum(pause_after(w) for w in words[:-1])
    weights = [_syllables(w) for w in words]
    per_unit = max(end - start - pauses, 0.1 * len(words)) / sum(weights)
    out, t = [], start
    for w, weight in zip(words, weights):
        out.append(Word(w, t, t + weight * per_unit))
        t += weight * per_unit + pause_after(w)
    return out
