"""Natural Hinglish from the Hindi voices.

A Script Video written in Roman Hinglish ("Aur ye hume next question tak lekar aata hai") was read by
hi-IN-MadhurNeural, which guessed every word from its Roman letters: the Hindi words came out right, the English
ones wrong ("nesht kweshtan", "sakshes", "Intiya", "mobhail deta", "afortibal"). The Hindi voices say English words
properly when they stand in English letters among Devanagari, so the text the voice speaks is written that way:
Hindi words in Devanagari, English words as they are. Only the script changes, never a word (checked: the same
number of words per line), and captions and sound cues keep the user's own text (`voice.synthesize_scenes` maps
the spoken words back by position). One small Claude call per batch of new lines; lines done before come from
<output>/hinglish_cache.json.
"""
from __future__ import annotations

import json
import logging
import re
import threading

from pydantic import BaseModel

log = logging.getLogger(__name__)

DEVANAGARI = re.compile(r"[ऀ-ॿ]")
LATIN = re.compile(r"[A-Za-z]")
_lock = threading.Lock()


def is_hindi_voice(voice: str) -> bool:
    """Hindi voices, and Sarvam's (its docs: transliterated input "significantly reduces output quality. Always use
    native script for Indic words")."""
    return voice.startswith("hi-IN") or voice.startswith("sarvam:")


# Very common Hindi words typed in Roman letters that aren't English words too: how Hinglish text is told apart
# from English for the multilingual voices (English scripts must never cost a conversion call).
HINDI_WORDS = {"hai", "hain", "aur", "ke", "ki", "ka", "ko", "mein", "ye", "yeh", "wo", "woh", "nahi", "nahin", "bhi",
               "kya", "kyun", "kyon", "tha", "thi", "hum", "aap", "tum", "jo", "toh", "kaise", "kab", "kahan", "lekin",
               "sirf", "bahut", "kaafi", "abhi", "hota", "hoti", "karte", "karta", "karna", "raha", "rahi", "rahe",
               "liye", "wala", "wali", "unka", "unki", "iska", "iski", "hamare", "humein", "hume", "apne", "agar"}


def enabled() -> bool:
    """Settings: mixed script on (default), or every voice reads the Roman text as written."""
    from .config import Config, load_settings

    return bool(load_settings(Config()).hinglish_mix)


def looks_hinglish(texts: list[str]) -> bool:
    ws = [w.lower() for t in texts for w in words(t)]
    hits = sum(w in HINDI_WORDS for w in ws)
    return hits >= 3 and hits >= 0.06 * len(ws)


def needs_mixing(voice: str, texts: list[str], least: int = 20) -> bool:
    """Hinglish typed in Roman letters for a Hindi voice (or a multilingual one, when it is clearly Hinglish)."""
    joined = " ".join(texts)
    latin, deva = len(LATIN.findall(joined)), len(DEVANAGARI.findall(joined))
    if latin <= least or latin <= 2 * deva:
        return False
    return is_hindi_voice(voice) or ("Multilingual" in voice and looks_hinglish(texts))


def words(text: str) -> list[str]:
    """The words as a voice reads them: whitespace-split, punctuation at the edges dropped."""
    out = []
    for tok in text.split():
        tok = re.sub(r"^[^\w]+|[^\w]+$", "", tok)
        if tok:
            out.append(tok)
    return out


class MixedLines(BaseModel):
    lines: list[str]


SYSTEM = """You prepare Hinglish narration for a Hindi text-to-speech voice. The voice says Hindi words right only \
in Devanagari and English words right only in English letters, so each line you get, typed in Roman letters, is \
written again in mixed script:
- every Hindi or Urdu word in Devanagari: aur -> और, ye -> ये, hai -> है, hume -> हमें, lekar -> लेकर, aata -> आता, \
shayad -> शायद, kaafi -> काफ़ी, log -> लोग, kai -> कई, mein -> में, bhi -> भी, ke -> के, ki -> की, ka -> का, na -> ना
- every English word exactly as written, in English letters: next question, success, mobile data, affordable, \
recharge plans, households, broadband, officially, announce
- names of people, brands, apps, places and units stay in English letters (Starlink, India, Jio, Elon Musk, GB)
- numbers, symbols and punctuation stay as they are
Keep every word, in the same order: one output word for each input word. Never translate, add, drop, merge or \
split a word, and never correct the grammar. Return the lines in the same order and the same number."""


ALL_DEVANAGARI = """You prepare Hinglish lines for a Hindi voice model that reads only Devanagari: English words in \
English letters come out mangled ('Scientists already human' became 'निसायन्तुस्ट आदरी विमन'). Write each line, \
typed in Roman letters, again entirely in Devanagari, the way an Indian speaker says it:
- Hindi or Urdu words in their usual spelling: aur -> और, hai -> है, mein -> में, kaam -> काम, sawaal -> सवाल
- English words spelled as they sound in Indian English: scientists -> साइंटिस्ट्स, already -> ऑलरेडी, computer -> \
कंप्यूटर, commands -> कमांड्स, future -> फ़्यूचर, AI -> एआई, thoughts -> थॉट्स, read -> रीड
- names, brands and units the same way (Neuralink -> न्यूरालिंक, GB -> जीबी); numbers as digits
- punctuation as it is
Keep every word, in the same order: one output word for each input word. Never translate, add, drop, merge or split \
a word. Return the lines in the same order and the same number."""


def to_devanagari(texts: list[str], ask_fn=None) -> list[str]:
    """Each line entirely in Devanagari, English words as they sound (for the voice engine's Hindi model, which can't
    read English letters); a line that can't be converted safely stays as it is. Cached with the mixed-script lines."""
    with _lock:
        cache = _load_cache()
        key = lambda t: "deva:" + t  # noqa: E731
        todo = [t for t in dict.fromkeys(texts) if t.strip() and key(t) not in cache]
        if todo:
            try:
                got = _convert(todo, ask_fn, ALL_DEVANAGARI)
            except Exception as exc:  # noqa: BLE001
                log.warning("Devanagari conversion failed (%s); the line is read as written", exc)
                got = []
            for original, new in zip(todo, got):
                new = new.strip()
                if new and len(words(new)) == len(words(original)):
                    cache[key(original)] = new
            _save_cache(cache)
    return [cache.get("deva:" + t, t) for t in texts]


def _cache_path():
    from .config import Config, load_settings

    return load_settings(Config()).output_dir / "hinglish_cache.json"


def _load_cache() -> dict:
    try:
        return json.loads(_cache_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_cache(cache: dict) -> None:
    try:
        path = _cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        log.warning("Couldn't save the Hinglish cache: %s", exc)


def to_speech(texts: list[str], ask_fn=None) -> list[str]:
    """Each line in mixed script for a Hindi voice; a line that can't be converted safely stays as it is."""
    with _lock:
        cache = _load_cache()
        todo = [t for t in dict.fromkeys(texts) if t.strip() and t not in cache]
        if todo:
            try:
                mixed = _convert(todo, ask_fn)
            except Exception as exc:  # noqa: BLE001 - the voice still speaks the line as written
                log.warning("Hinglish conversion failed (%s); the voice reads the Roman text", exc)
                mixed = []
            for original, new in zip(todo, mixed):
                new = new.strip()
                if new and len(words(new)) == len(words(original)):
                    cache[original] = new
                else:
                    log.info("Hinglish line kept as written (word count changed): %r -> %r", original, new)
            _save_cache(cache)
    return [cache.get(t, t) for t in texts]


def _convert(lines: list[str], ask_fn=None, system: str = "") -> list[str]:
    from .config import Config, load_settings
    from .llm import ask

    cfg = load_settings(Config())
    call = ask_fn or (lambda system, prompt: ask(cfg.ai_backend, cfg.fact_model or cfg.claude_model, system, prompt,
                                                 MixedLines, effort="low", timeout=600))
    out: list[str] = []
    for i in range(0, len(lines), 60):  # long chapters in a few calls
        part = lines[i:i + 60]
        prompt = "Lines:\n" + "\n".join(f"{n + 1}. {t}" for n, t in enumerate(part))
        res = call(system or SYSTEM, prompt)
        got = [re.sub(r"^\s*\d+\.\s*", "", x) for x in res.lines]
        out += got if len(got) == len(part) else [""] * len(part)
    return out
