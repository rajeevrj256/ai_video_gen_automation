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
import random
import re
import threading
import ssl
import wave
from dataclasses import dataclass
from pathlib import Path

import edge_tts
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
                      kokoro_voice: str = "") -> list[SceneAudio]:
    """Render one audio file per scene so each scene's duration follows its voiceover.

    Delivery is brisk, like a Shorts creator (videos are capped at 30 seconds).
    Speed (and pitch, where supported) drifts slightly from scene to scene, like a
    person speaking, instead of the flat identical delivery that gives TTS away.
    The hook is a touch faster and more energetic.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    if engine in ("auto", "edge"):
        try:
            return _edge_scenes(narrations, voice, out_dir)
        except Exception as exc:
            if engine == "edge":
                raise
            log.warning("Microsoft voice unavailable (%s); using the offline Kokoro voice", exc)
    return _kokoro_scenes(narrations, kokoro_voice or KOKORO_FOR_EDGE.get(voice) or _kokoro_default(voice), out_dir)


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


def _edge_scenes(narrations: list[str], voice: str, out_dir: Path) -> list[SceneAudio]:
    results = []
    for i, text in enumerate(narrations):
        path = out_dir / f"scene_{i:02d}.mp3"
        rate = f"{random.randint(20, 24) if i == 0 else random.randint(12, 20):+d}%"
        pitch = f"{random.randint(-3, 3):+d}Hz"
        words = asyncio.run(_edge_synthesize(text, voice, rate, pitch, path))
        results.append(SceneAudio(path, words))
    return results


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


def _kokoro_scenes(narrations: list[str], voice: str, out_dir: Path) -> list[SceneAudio]:
    with _kokoro_lock:
        return _kokoro_scenes_locked(narrations, voice, out_dir)


def _kokoro_scenes_locked(narrations: list[str], voice: str, out_dir: Path) -> list[SceneAudio]:
    kokoro = _load_kokoro()
    lang = KOKORO_LANG.get(voice[:1], "en-us")
    results = []
    for i, text in enumerate(narrations):
        speed = random.uniform(1.20, 1.24) if i == 0 else random.uniform(1.12, 1.20)
        samples, rate = kokoro.create(text, voice=voice, speed=speed, lang=lang,
                                      sentence_pause=SENTENCE_PAUSE, clause_pause=CLAUSE_PAUSE)
        path = out_dir / f"scene_{i:02d}.wav"
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(rate)
            wav.writeframes((np.clip(samples, -1, 1) * 32767).astype(np.int16).tobytes())
        results.append(SceneAudio(path, _estimate_words(text, samples, rate)))
    return results


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
