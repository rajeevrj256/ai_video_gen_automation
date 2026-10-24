"""Sarvam AI's Bulbul v3 voices: Indian voices made for Hindi, English and Hinglish (code-mixed) narration.

Voices are named `sarvam:<speaker>` wherever an edge-tts voice name goes: a bulbul:v4-flash voice ID
(`sarvam:shubh_enhi_ads`, `<name>_<language>_<style>`; `enhi` = English-Hindi code-mixed, the user tried Shubh on
v4 Flash in Sarvam's playground) or a bulbul:v3 speaker (`sarvam:shubh`). The key is
SARVAM_API_KEY (.env, or Settings > Long videos, which writes it there); it never goes back to the page.
API (docs.sarvam.ai, text-to-speech/convert): POST https://api.sarvam.ai/text-to-speech, header
`api-subscription-key`, body text (≤2500 characters for bulbul:v3) + language_code + speaker + model + pace
(0.5-2.0) + speech_sample_rate + output_audio_codec; the answer is {"audios": [base64]} with no word timings.
So a chapter is spoken in takes of whole lines (one take flows like a presenter, as with edge-tts), each line is
cut at the real pause nearest to where its words should end (`_pause_near`), and the words of each line are then
spread over that line's own audio by syllables. ₹3 per 1,000 characters (Sept 2026): ~₹25-30 a 10-minute video.
"""
from __future__ import annotations

import base64
import logging
import os
import re
import time
from pathlib import Path

import numpy as np
import requests

log = logging.getLogger(__name__)

URL = "https://api.sarvam.ai/text-to-speech"
# Your own cloned voice (Sarvam Content Studio / POST /voices/create gives an ID `svc-<uuid>`; Settings > Long videos
# 'Your Sarvam voice'): spoken through POST /voices/clone, multipart, at most 1000 characters a request, the answer
# {"audio_b64" (or the older "audio"), "request_id", "audio_duration"}. The user's own playground setup: en-IN,
# pace 1.2, 32000 Hz, quality control and text normalisation on.
CLONE_URL = "https://api.sarvam.ai/voices/clone"
CLONE_LIMIT = 950  # characters a request (the API refuses over 1000)
CLONE_RATE = 32000
LIMIT = 2000  # characters per take (the API takes 2500; Devanagari can come out a little longer than the Roman text)
RATE = 24000
GAP = 0.3  # seconds of silence between two takes
# The REST answer came out ~4 dB louder than the same voice from Sarvam's playground (user's two files, same text:
# -13.4 vs -17.4 LUFS, peak -0.3 dBFS), which sounded harsher; every take is levelled to the playground's loudness.
TARGET_LUFS, PEAK_CEILING = -17.0, -1.5

# bulbul:v4-flash voices for Hinglish and Hindi narration (docs' Voices page; 222 in all, gender not stated).
V4_VOICES = {
    "shubh_enhi_ads": "Shubh, Hinglish, lively (male)", "shubh_enhi_companion": "Shubh, Hinglish, conversational (male)",
    "shubh_hi_stories_mixed": "Shubh, Hindi storytelling (male)", "sunny_enhi_customer": "Sunny, Hinglish (male)",
    "anand_hi_news": "Anand, Hindi news (male)", "simran_enhi_companion": "Simran, Hinglish, conversational (female)",
    "ishita_enhi_companion": "Ishita, Hinglish, conversational (female)", "shalini_enhi_companion": "Shalini, Hinglish (female)",
    "simran_hi_narration": "Simran, Hindi narration (female)", "shreya_hi_news": "Shreya, Hindi news (female)",
}
# bulbul:v3's speakers (docs, 37).
SPEAKERS = {
    "shubh": "male", "aditya": "male", "rahul": "male", "rohan": "male", "amit": "male", "dev": "male",
    "ratan": "male", "varun": "male", "manan": "male", "sumit": "male", "kabir": "male", "aayan": "male",
    "ashutosh": "male", "advait": "male", "anand": "male", "tarun": "male", "sunny": "male", "mani": "male",
    "gokul": "male", "vijay": "male", "mohit": "male", "rehan": "male", "soham": "male",
    "ritu": "female", "priya": "female", "neha": "female", "pooja": "female", "simran": "female",
    "kavya": "female", "ishita": "female", "shreya": "female", "roopa": "female", "tanya": "female",
    "shruti": "female", "suhani": "female", "kavitha": "female", "rupali": "female",
}


def is_sarvam(voice: str) -> bool:
    return voice.startswith("sarvam:")


def is_clone(speaker: str) -> bool:
    """`svc-<uuid>`: a voice cloned in Sarvam (yours), not one of their speakers."""
    return speaker.startswith("svc-")


def my_voice() -> tuple[str, str]:
    """(voice name as the app uses it, its label) for the cloned voice in Settings, or ('', '')."""
    from .config import Config, load_settings

    cfg = load_settings(Config())
    vid = (cfg.my_voice_id or "").strip()
    return (f"sarvam:{vid}", (cfg.my_voice_name or "My voice").strip()) if vid else ("", "")


def key() -> str:
    return os.environ.get("SARVAM_API_KEY", "").strip()


# Delivery levels: Sarvam's `temperature` ("controls expressiveness", 0.01-1.0, default 0.6, v3 and v4-flash) and a
# pace factor. Only the hook uses a level above normal (Settings `hook_delivery`), so the chapters keep one steady voice.
DELIVERY = {"normal": (None, 1.0), "lively": (0.75, 1.05), "very": (0.9, 1.05)}


def delivery(kind: str = "") -> tuple[float | None, float]:
    """(temperature, pace factor) for a take: `kind` is "hook" for the hook's take, or a level name for the voice test."""
    if kind in DELIVERY:
        return DELIVERY[kind]
    if kind == "hook":
        from .config import Config, load_settings

        return DELIVERY.get(load_settings(Config()).hook_delivery, DELIVERY["normal"])
    return DELIVERY["normal"]


def pace() -> float:
    """Settings > Long videos 'Sarvam pace' (its own: the general voice speed is +10% for Shorts)."""
    from .config import Config, load_settings

    return min(2.0, max(0.5, float(load_settings(Config()).sarvam_pace or 1.0)))


def pace_for(speaker: str) -> float:
    """Your cloned voice has its own pace (Settings 'Your voice's pace', 1.2 as in your playground setup)."""
    if not is_clone(speaker):
        return pace()
    from .config import Config, load_settings

    return min(2.0, max(0.5, float(load_settings(Config()).my_voice_pace or 1.2)))


def speaker_of(voice: str) -> str:
    name = voice.split(":", 1)[1].strip().lower() if ":" in voice else voice.lower()
    if re.fullmatch(r"svc-[0-9a-f-]{8,64}", name):
        return name
    if name not in SPEAKERS and not re.fullmatch(r"[a-z]+_[a-z]{2,4}_[a-z_]+", name):
        raise ValueError(f"Unknown Sarvam voice '{name}'")
    return name


def model_for(speaker: str) -> str:
    return "bulbul:v4-flash" if "_" in speaker else "bulbul:v3"


def language_for(speaker: str) -> str:
    return "en-IN" if "_en_" in speaker else "hi-IN"  # hi and enhi voices read Hindi and Hinglish


def say(text: str, speaker: str, pace: float = 1.0, codec: str = "wav", temperature: float | None = None) -> bytes:
    """One take. Rate limits and server hiccups are tried again; a wrong key or used-up credits are said plainly."""
    if not key():
        raise RuntimeError("Add your Sarvam API key in Settings > Long videos to use the Sarvam voices")
    if is_clone(speaker):
        return _clone_say(text, speaker, pace, codec)
    body = {"text": text, "language_code": language_for(speaker), "speaker": speaker, "model": model_for(speaker),
            "pace": round(min(2.0, max(0.5, pace)), 2), "speech_sample_rate": RATE, "output_audio_codec": codec}
    if temperature is not None:
        body["temperature"] = round(min(1.0, max(0.01, temperature)), 2)
    swapped = False
    for attempt in range(4):
        try:
            resp = requests.post(URL, json=body, headers={"api-subscription-key": key()}, timeout=180)
        except requests.RequestException as exc:
            if attempt == 3:
                raise RuntimeError(f"Couldn't reach Sarvam: {exc}") from None
            time.sleep(4 * (attempt + 1))
            continue
        if resp.status_code == 200:
            audios = (resp.json() or {}).get("audios") or []
            if not audios:
                raise RuntimeError("Sarvam answered without audio")
            return base64.b64decode(audios[0])
        try:
            err = resp.json().get("error") or {}
        except ValueError:
            err = {}
        code, msg = err.get("code", ""), str(err.get("message") or resp.text)[:200]
        if code == "insufficient_quota_error":
            raise RuntimeError("Your Sarvam credits have run out (sarvam.ai dashboard)")
        if resp.status_code in (401, 403) or "api_key" in code or code == "authentication_error":
            raise RuntimeError("Sarvam refused the API key: check it in Settings > Long videos")
        if resp.status_code in (400, 422) and "language" in msg.lower() and not swapped:
            # the REST docs name it language_code, the playground's SDK code target_language_code: try the other once
            body["target_language_code"] = body.pop("language_code")
            swapped = True
            continue
        if resp.status_code in (429, 500, 502, 503, 504) and attempt < 3:
            time.sleep(6 * (attempt + 1))
            continue
        raise RuntimeError(f"Sarvam voice failed ({resp.status_code} {code}): {msg}")
    raise RuntimeError("Sarvam voice failed")


def _chunks(text: str, limit: int) -> list[str]:
    """Text in pieces of at most `limit` characters, cut at sentence ends (else at a comma, else a space)."""
    out: list[str] = []
    for sent in re.split(r"(?<=[.!?…।])\s+", text.strip()):
        while len(sent) > limit:
            cut = max(sent.rfind(", ", 0, limit), sent.rfind(" ", 0, limit))
            cut = cut if cut > limit // 3 else limit
            out.append(sent[:cut + 1].strip())
            sent = sent[cut + 1:].strip()
        if out and len(out[-1]) + 1 + len(sent) <= limit:
            out[-1] = f"{out[-1]} {sent}"
        elif sent:
            out.append(sent)
    return out


def _clone_say(text: str, speaker: str, pace: float, codec: str = "wav") -> bytes:
    """Your cloned voice. Over CLONE_LIMIT characters the text is spoken in pieces cut at sentence ends and joined
    with GAP seconds between them (a WAV; another codec only for one piece)."""
    pieces = _chunks(text, CLONE_LIMIT)
    if len(pieces) > 1:
        import io
        import wave

        frames, params = [], None
        for piece in pieces:
            with wave.open(io.BytesIO(_clone_once(piece, speaker, pace, "wav"))) as w:
                params = params or w.getparams()
                if frames:
                    frames.append(b"\0" * int(GAP * params.framerate) * params.sampwidth * params.nchannels)
                frames.append(w.readframes(w.getnframes()))
        buf = io.BytesIO()
        with wave.open(buf, "wb") as out:
            out.setparams(params)
            out.writeframes(b"".join(frames))
        return buf.getvalue()
    return _clone_once(text, speaker, pace, codec)


def _clone_once(text: str, speaker: str, pace: float, codec: str) -> bytes:
    """One request to POST /voices/clone (multipart). Hindi in Devanagari goes as hi-IN, the rest as en-IN (cloning
    is cross-lingual and reads code-mixed text); numbers and dates are spoken by Sarvam's own normalisation."""
    form = {"text": text, "language_code": "hi-IN" if re.search("[\u0900-\u097F]", text) else "en-IN",
            "voice_id": speaker, "pace": str(round(min(2.0, max(0.5, pace)), 2)), "speech_sample_rate": str(CLONE_RATE),
            "output_audio_codec": codec, "enable_qc": "true", "enable_text_normalization": "true"}
    for attempt in range(4):
        try:
            resp = requests.post(CLONE_URL, files={k: (None, v) for k, v in form.items()},  # multipart/form-data
                                 headers={"api-subscription-key": key()}, timeout=240)
        except requests.RequestException as exc:
            if attempt == 3:
                raise RuntimeError(f"Couldn't reach Sarvam: {exc}") from None
            time.sleep(4 * (attempt + 1))
            continue
        if resp.status_code == 200:
            data = resp.json() or {}
            audio = data.get("audio_b64") or data.get("audio")
            if not audio:
                raise RuntimeError("Sarvam answered without audio")
            return base64.b64decode(audio)
        try:
            err = resp.json().get("error") or {}
        except ValueError:
            err = {}
        code, msg = err.get("code", ""), str(err.get("message") or resp.text)[:200]
        if resp.status_code == 402 or code == "insufficient_quota_error":
            raise RuntimeError("Your Sarvam credits have run out (sarvam.ai dashboard)")
        if resp.status_code in (401, 403):
            raise RuntimeError("Sarvam refused the API key: check it in Settings > Long videos")
        if resp.status_code in (429, 500, 502, 503, 504) and attempt < 3:
            time.sleep(6 * (attempt + 1))
            continue
        if resp.status_code in (400, 404, 422) and "voice" in msg.lower():
            raise RuntimeError(f"Sarvam doesn't know the voice ID {speaker}: check it in Settings > Long videos ({msg})")
        raise RuntimeError(f"Your Sarvam voice failed ({resp.status_code} {code}): {msg}")
    raise RuntimeError("Your Sarvam voice failed")


def level_file(src: Path, dst: Path) -> float:
    """Copy src to dst (wav or mp3 by its extension) at TARGET_LUFS, peaks kept under PEAK_CEILING. Returns the gain."""
    import subprocess

    import imageio_ffmpeg

    ff = imageio_ffmpeg.get_ffmpeg_exe()
    probe = subprocess.run([ff, "-hide_banner", "-nostats", "-i", str(src), "-af", "ebur128=peak=sample", "-f", "null", "-"],
                           capture_output=True, text=True).stderr
    lufs = re.findall(r"I:\s*(-?[\d.]+) LUFS", probe)
    peak = re.findall(r"Peak:\s*(-?[\d.]+|-inf) dBFS", probe)
    gain = 0.0
    if lufs and float(lufs[-1]) > -70:
        gain = TARGET_LUFS - float(lufs[-1])
        if peak and peak[-1] != "-inf":
            gain = min(gain, PEAK_CEILING - float(peak[-1]))
    tmp = dst.with_name(dst.stem + ".lv" + dst.suffix)
    codec = ["-c:a", "libmp3lame", "-b:a", "128k"] if dst.suffix == ".mp3" else ["-c:a", "pcm_s16le"]
    proc = subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(src), "-af", f"volume={gain:.2f}dB", *codec, str(tmp)],
                          capture_output=True, text=True)
    if proc.returncode != 0 or not tmp.exists():
        raise RuntimeError(f"Couldn't level the Sarvam voice: {proc.stderr[-200:]}")
    tmp.replace(dst)
    return gain


def _takes(narrations: list[str], limit: int = LIMIT) -> list[list[int]]:
    """Whole lines grouped into takes of at most `limit` characters."""
    groups: list[list[int]] = []
    for i, text in enumerate(narrations):
        size = len(text) + 1
        if groups and sum(len(narrations[j]) + 1 for j in groups[-1]) + size <= limit:
            groups[-1].append(i)
        else:
            groups.append([i])
    return groups


def _pause_near(samples: np.ndarray, rate: int, t: float, reach: float = 1.2) -> float:
    """The middle of the real pause (≥120 ms of near-silence) closest to t; else the quietest spot near it.
    Word times here are estimates, and a sentence end always has a pause: cutting there never splits a word."""
    win = max(1, int(0.03 * rate))
    lo, hi = max(0, int((t - reach) * rate)), min(len(samples) - win, int((t + reach) * rate))
    if hi <= lo:
        return t
    env = np.convolve(np.abs(samples[lo:hi + win]), np.ones(win) / win, "valid")[::win // 3 or 1]
    step = (win // 3 or 1) / rate
    quiet = env < max(float(env.max()) * 0.05, 1e-4)
    edges = np.diff(np.concatenate([[0], quiet.astype(np.int8), [0]]))
    starts, ends = np.nonzero(edges == 1)[0], np.nonzero(edges == -1)[0]
    # A real pause first (>=120 ms); else a shorter gap between words (>=50 ms: two lines read together still
    # leave one); only then the quietest spot, which can fall inside a word.
    for least in (0.12, 0.05):
        runs = [(a, b) for a, b in zip(starts, ends) if (b - a) * step >= least]
        if runs:
            mids = [lo / rate + (a + b) / 2 * step for a, b in runs]
            return min(mids, key=lambda m: abs(m - t))
    if reach < 2.4:  # nothing near the estimate: look further before cutting into sound
        return _pause_near(samples, rate, t, reach * 2)
    return lo / rate + int(np.argmin(env)) * step


def scenes(narrations: list[str], speaker: str, out_dir: Path, pace: float = 1.0, temperature: float | None = None):
    """One audio file per line, spoken in takes of whole lines, like voice.synthesize_scenes."""
    from .voice import SceneAudio, _decode, _estimate_words, _write_wav

    out_dir.mkdir(parents=True, exist_ok=True)
    pieces, cuts, t0 = [], [], 0.0
    for n, group in enumerate(_takes(narrations, CLONE_LIMIT if is_clone(speaker) else LIMIT)):
        text = " ".join(narrations[j].strip() for j in group)
        take = out_dir / f"take_{n:02d}.wav"
        take.write_bytes(say(text, speaker, pace, temperature=temperature))
        level_file(take, take)
        samples, _ = _decode(take, RATE)
        if pieces:  # between two takes: the middle of the silence put there
            pieces.append(np.zeros(int(GAP * RATE), dtype=np.float32))
            cuts.append(t0 + GAP / 2)
            t0 += GAP
        words = _estimate_words(text, samples, RATE)
        k = 0
        for j in group[:-1]:
            k += len(narrations[j].split())
            if 0 < k < len(words):
                cuts.append(t0 + _pause_near(samples, RATE, (words[k - 1].end + words[k].start) / 2))
            else:
                cuts.append(t0 + len(samples) / RATE * (j - group[0] + 1) / len(group))
        pieces.append(samples.astype(np.float32))
        t0 += len(samples) / RATE
    full = np.concatenate(pieces) if pieces else np.zeros(1, dtype=np.float32)
    bounds = [0.0, *sorted(cuts), len(full) / RATE]
    out = []
    for i, text in enumerate(narrations):
        seg = full[int(bounds[i] * RATE):int(bounds[i + 1] * RATE)]
        path = out_dir / f"scene_{i:02d}.wav"
        _write_wav(path, seg, RATE)
        out.append(SceneAudio(path, _estimate_words(text, seg, RATE) if len(seg) else []))
    return out
