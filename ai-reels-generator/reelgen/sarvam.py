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
# pace 1.2, 48000 Hz, quality control and text normalisation on.
CLONE_URL = "https://api.sarvam.ai/voices/clone"
CLONE_LIMIT = 950  # characters a request (the API refuses over 1000)
CLONE_RATE = 48000  # the user asked for 48 kHz (Sarvam allows up to 48000)
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


def keys() -> list[str]:
    """Every Sarvam key you saved (SARVAM_API_KEY, several separated by commas: one per free account)."""
    return [k for k in re.split(r"[\s,;]+", os.environ.get("SARVAM_API_KEY", "")) if k]


def key() -> str:
    """The first key (any key at all = the Sarvam voices are available)."""
    return next(iter(keys()), "")


# Several keys: when one account's credits run out (or its key is refused) the next key takes over, and the spent one
# is skipped for RETRY_HOURS (a recharge brings it back after that, or at once when the keys are saved again).
# Only a fingerprint of each key is written down (<output>/sarvam-keys.json), never the key.
RETRY_HOURS = 12


def _keys_file() -> Path:
    from .config import Config

    return Config().output_dir / "sarvam-keys.json"


def _fingerprint(k: str) -> str:
    import hashlib

    return hashlib.sha1(k.encode()).hexdigest()[:12]


def _spent() -> dict:
    import json

    try:
        return json.loads(_keys_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _retire(k: str, why: str) -> None:
    import json

    state = _spent()
    state[_fingerprint(k)] = {"at": time.time(), "why": why}
    try:
        _keys_file().parent.mkdir(parents=True, exist_ok=True)
        _keys_file().write_text(json.dumps(state, indent=1), encoding="utf-8")
    except OSError:
        pass
    log.warning("Sarvam key %d of %d: %s; trying the next key", keys().index(k) + 1 if k in keys() else 0, len(keys()), why)


def forget_spent() -> None:
    """Keys saved again in Settings: every key gets another try."""
    _keys_file().unlink(missing_ok=True)


def key_status() -> dict:
    state, now = _spent(), time.time()
    spent = [k for k in keys() if now - state.get(_fingerprint(k), {}).get("at", 0) < RETRY_HOURS * 3600]
    return {"count": len(keys()), "spent": len(spent)}


def _post(url: str, voice_bound: bool = False, **kw):
    """POST with the first key that still has credits. A key whose credits ran out (402 / insufficient_quota) or that
    Sarvam refuses (401/403) is set aside and the next one tried. `voice_bound`: your cloned voice belongs to one
    account, so another account's key that doesn't know the voice is skipped (not set aside)."""
    state, now = _spent(), time.time()
    fresh = [k for k in keys() if now - state.get(_fingerprint(k), {}).get("at", 0) >= RETRY_HOURS * 3600]
    if not keys():
        raise RuntimeError("Add your Sarvam API key in Settings > Long videos to use the Sarvam voices")
    resp, last = None, ""
    for k in fresh:
        resp = requests.post(url, headers={"api-subscription-key": k}, **kw)
        try:
            err = (resp.json() or {}).get("error") or {} if resp.status_code != 200 else {}
        except ValueError:
            err = {}
        code, msg = str(err.get("code", "")), str(err.get("message", ""))
        if resp.status_code == 402 or code == "insufficient_quota_error":
            _retire(k, "credits ran out")
            last = "credits"
            continue
        if resp.status_code in (401, 403) or code == "authentication_error":
            _retire(k, "key refused")
            last = last or "refused"
            continue
        if voice_bound and resp.status_code in (400, 404, 422) and "voice" in msg.lower():
            if k != fresh[-1]:
                last = last or "voice"
                continue  # this account doesn't have your cloned voice: try the next key
            if len(fresh) < len(keys()):  # the keys left don't have it, and the others are out of credits
                raise RuntimeError("Your cloned voice belongs to a Sarvam account that is out of credits right now (your "
                                   "other keys don't have this voice). Recharge that account, then start it again: the "
                                   "takes already recorded are kept on this computer and not paid for twice")
        return resp
    many = len(keys()) > 1
    if last == "refused":
        raise RuntimeError("Sarvam refused " + ("every key" if many else "the API key") + ": check them in Settings > Long videos")
    raise RuntimeError(("All your Sarvam keys have" if many else "Your Sarvam credits have") + " run out of credits "
                       "(sarvam.ai dashboard). Recharge or add another key in Settings > Long videos, then start it "
                       "again: the takes already recorded are kept on this computer and not paid for twice")


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


# Every take Sarvam made is kept on this computer, keyed by what was asked (voice, text, pace, delivery, rate...): a
# re-make that ran out of credits after 8 of 10 chapters recorded all 8 again on the next try and paid twice. Now
# any retry, re-make or resume with the same words reuses the paid takes. Takes not used for CACHE_DAYS are dropped.
CACHE_DIR = "sarvam-cache"
CACHE_DAYS = 60


def _cache_path(*parts) -> Path:
    import hashlib

    from .config import Config

    key_ = hashlib.sha1(repr(parts).encode("utf-8")).hexdigest()
    return Config().output_dir / CACHE_DIR / key_[:2] / f"{key_}.bin"


def _prune_cache() -> None:
    """Drop takes not used for CACHE_DAYS (at most once a day, cheap)."""
    from .config import Config

    root = Config().output_dir / CACHE_DIR
    stamp = root / ".pruned"
    try:
        if stamp.exists() and time.time() - stamp.stat().st_mtime < 86400:
            return
        root.mkdir(parents=True, exist_ok=True)
        stamp.touch()
        for f in root.glob("*/*.bin"):
            if time.time() - f.stat().st_mtime > CACHE_DAYS * 86400:
                f.unlink(missing_ok=True)
    except OSError:
        pass


def say(text: str, speaker: str, pace: float = 1.0, codec: str = "wav", temperature: float | None = None) -> bytes:
    """One take, from this computer's cache when the same take was already paid for; else from Sarvam."""
    path = _cache_path(speaker, text, round(pace, 3), codec, temperature, RATE, CLONE_RATE, model_for(speaker))
    if path.exists() and path.stat().st_size > 1000:
        path.touch()  # used: kept another CACHE_DAYS
        return path.read_bytes()
    audio = _say(text, speaker, pace, codec, temperature)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(audio)
        tmp.replace(path)
        _prune_cache()
    except OSError as exc:  # a full disk never stops a video
        log.warning("Couldn't keep the Sarvam take: %s", exc)
    return audio


def _say(text: str, speaker: str, pace: float = 1.0, codec: str = "wav", temperature: float | None = None) -> bytes:
    """One take from Sarvam. Rate limits and server hiccups are tried again; a wrong key or used-up credits are said plainly."""
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
            resp = _post(URL, json=body, timeout=180)
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
            raise RuntimeError("Your Sarvam credits have run out (sarvam.ai dashboard). After recharging, start it again: "
                               "the takes already recorded are kept on this computer and not paid for twice")
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
            resp = _post(CLONE_URL, voice_bound=True, files={k: (None, v) for k, v in form.items()},  # multipart
                         timeout=240)
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
            raise RuntimeError("Your Sarvam credits have run out (sarvam.ai dashboard). After recharging, start it again: "
                               "the takes already recorded are kept on this computer and not paid for twice")
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
    rate = CLONE_RATE if is_clone(speaker) else RATE  # your voice kept at the 48 kHz it was asked for
    pieces, cuts, t0 = [], [], 0.0
    for n, group in enumerate(_takes(narrations, CLONE_LIMIT if is_clone(speaker) else LIMIT)):
        text = " ".join(narrations[j].strip() for j in group)
        take = out_dir / f"take_{n:02d}.wav"
        take.write_bytes(say(text, speaker, pace, temperature=temperature))
        level_file(take, take)
        samples, _ = _decode(take, rate)
        if pieces:  # between two takes: the middle of the silence put there
            pieces.append(np.zeros(int(GAP * rate), dtype=np.float32))
            cuts.append(t0 + GAP / 2)
            t0 += GAP
        words = _estimate_words(text, samples, rate)
        k = 0
        for j in group[:-1]:
            k += len(narrations[j].split())
            if 0 < k < len(words):
                cuts.append(t0 + _pause_near(samples, rate, (words[k - 1].end + words[k].start) / 2))
            else:
                cuts.append(t0 + len(samples) / rate * (j - group[0] + 1) / len(group))
        pieces.append(samples.astype(np.float32))
        t0 += len(samples) / rate
    full = np.concatenate(pieces) if pieces else np.zeros(1, dtype=np.float32)
    bounds = [0.0, *sorted(cuts), len(full) / rate]
    out = []
    for i, text in enumerate(narrations):
        seg = full[int(bounds[i] * rate):int(bounds[i + 1] * rate)]
        path = out_dir / f"scene_{i:02d}.wav"
        _write_wav(path, seg, rate)
        out.append(SceneAudio(path, _estimate_words(text, seg, rate) if len(seg) else []))
    return out
