"""Words you skipped or said wrong in a filmed take, put back in your own voice (the Shoot tab).

The word check (`shoot.matches`) knows which script words weren't heard. `gaps` finds where each run of them belongs in
the take: right after the heard word matched to the script word before it. If other words were heard there, you said
something else (a wrong word) and they are replaced; if not, the run is put into the pause (a skipped word).
`splice` puts the new audio in, levelled to the words around it, with short crossfades. The new audio is made by the
voice engine (`voice_engine.speak`: your voice cloned from your own takes). The edit then shows B-roll on a fixed line
that was on camera, since your lips no longer match it, and moves its caption words to the new times (`shift_words`).
"""

from __future__ import annotations

import logging
import subprocess
import wave
from pathlib import Path

import numpy as np

from .video import FFMPEG
from .voice import Word

log = logging.getLogger(__name__)

FADE = 0.012  # seconds of crossfade at each joint
BREATH = 0.08  # pause kept on each side of a put-back word
FILLER_ONLY_OK = True  # a run of only small words ('hain', 'ko') is left alone: speech-to-text drops and joins them
NEAR = 0.6  # seconds: a word heard this close to a line's start or end, where its missing words go, is said instead
MISHEARD = 0.6  # sound overlap at which a 'wrong' word counts as the right one misheard (`misheard`)


def misheard(script_words: list[str], said: list[Word]) -> bool:
    """What was heard in place of the script's words sounds like them (the same consonants, the first sound aside):
    you said them and speech-to-text misheard ('already' came back as 'पल्रदी'), so they stay as said. Only a clearly
    different word is 'said wrong'."""
    from .shoot import skeleton

    a = "".join(skeleton(w) for w in script_words)
    b = "".join(skeleton(w.text) for w in said)
    if not a or not b:
        return False
    lcs = [0] * (len(b) + 1)
    for x in a:
        prev = 0
        for j, y in enumerate(b):
            prev, lcs[j + 1] = lcs[j + 1], prev + 1 if x == y else max(lcs[j + 1], lcs[j])
    return 2 * lcs[-1] / (len(a) + len(b)) >= MISHEARD


def gaps(lines: list[str], heard: list[Word]) -> list[dict]:
    """Every run of script words not heard, per line, with where it goes:
    {line, words (as written), text, kind 'skipped'|'wrong', said (the wrong words heard there), at [a, b]}.
    `at` is the stretch of the take it replaces (a == b: put in at that moment)."""
    from .shoot import FILLER, matches

    tokens, match = matches(lines, heard)
    out = []
    for k, line in enumerate(lines):
        words = line.split()
        mine = [t for t, tok in enumerate(tokens) if tok[0] == k]
        if not any(t in match for t in mine):
            continue  # nothing of the line was heard: not a word to fix, the line is missing (shown on the card)
        run: list[int] = []
        for i, t in enumerate(mine + [None]):
            if t is not None and t not in match:
                run.append(t)
                continue
            if run:
                idx = list(dict.fromkeys(tokens[x][1] for x in run))  # word positions (hyphen parts share one)
                said_words = [words[j] for j in idx]
                if not (FILLER_ONLY_OK and all(w.lower().strip(".,!?;:…") in FILLER for w in said_words)):
                    before = next((match[x] for x in reversed(mine[:mine.index(run[0])]) if x in match), None)
                    after = next((match[x] for x in mine[mine.index(run[-1]) + 1:] if x in match), None)
                    # the heard words in between are what you said instead; never past another line's words
                    lo = before if before is not None else max((match[x] for x in range(run[0]) if x in match), default=-1)
                    hi = after if after is not None else min((match[x] for x in range(run[-1] + 1, len(tokens)) if x in match),
                                                             default=len(heard))
                    wrong = heard[lo + 1:hi]
                    if before is None and after is not None:  # the line starts with them: only words right before
                        wrong = [w for w in wrong if heard[after].start - w.end <= NEAR]
                    elif after is None and before is not None:  # it ends with them: only words right after
                        wrong = [w for w in wrong if w.start - heard[before].end <= NEAR]
                    if wrong and misheard(said_words, wrong):
                        run = []
                        continue
                    if wrong:
                        a, b = wrong[0].start, wrong[-1].end
                    elif before is not None:
                        a = b = heard[before].end
                    else:
                        a = b = max(0.0, heard[after].start - BREATH)
                    out.append({"line": k, "words": said_words, "text": " ".join(said_words), "at": [round(a, 3), round(b, 3)],
                                "kind": "wrong" if wrong else "skipped", "said": " ".join(w.text for w in wrong),
                                "first_word": idx[0]})
                run = []
    return out


def _read(path: Path) -> tuple[np.ndarray, int]:
    try:
        w = wave.open(str(path))
    except wave.Error:  # 32-bit float (the voice model's) or another format: as 16-bit through ffmpeg
        pcm = path.with_name(path.stem + ".s16.wav")
        subprocess.run([FFMPEG, "-v", "error", "-y", "-i", str(path), "-c:a", "pcm_s16le", str(pcm)], check=True)
        w = wave.open(str(pcm))
    with w:
        sr, ch, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(w.getnframes())
    x = np.frombuffer(raw, {2: np.int16, 4: np.int32}[width]).astype(np.float32) / (2 ** (8 * width - 1))
    return (x.reshape(-1, ch).mean(1) if ch > 1 else x), sr


def _write(path: Path, x: np.ndarray, sr: int) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())


def _as_wav(src: Path, sr: int, dst: Path) -> Path:
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", str(src), "-ac", "1", "-ar", str(sr), str(dst)], check=True)
    return dst


def _rms(x: np.ndarray) -> float:
    """Loudness of the audible part (the quietest 40% of 20 ms frames left out)."""
    f = 960
    n = len(x) // f
    if n == 0:
        return float(np.sqrt((x ** 2).mean() + 1e-12))
    e = (x[:n * f].reshape(n, f) ** 2).mean(1)
    loud = e[e >= np.percentile(e, 40)]
    return float(np.sqrt(loud.mean() + 1e-12))


def _trim(x: np.ndarray, sr: int, floor_db: float = -40) -> np.ndarray:
    """The clip without silence at its ends (TTS adds some), keeping 20 ms."""
    f = int(sr * 0.01)
    n = len(x) // f
    if n == 0:
        return x
    e = 10 * np.log10((x[:n * f].reshape(n, f) ** 2).mean(1) + 1e-12)
    loud = np.where(e > e.max() + floor_db)[0]
    if not len(loud):
        return x
    a, b = max(0, (loud[0] - 2) * f), min(len(x), (loud[-1] + 3) * f)
    return x[a:b]


SNAP = 0.1  # speech-to-text word times are about this far off: cuts move to the quietest moment this near


def _snap(x: np.ndarray, sr: int, t: float, lo: float | None = None, hi: float | None = None) -> float:
    """The quietest 10 ms within SNAP of `t` (between `lo` and `hi`): the gap between two words, so a cut never
    takes half a syllable."""
    f = int(sr * 0.01)
    a = max(0.0, t - SNAP, lo if lo is not None else 0.0)
    b = min(len(x) / sr, t + SNAP, hi if hi is not None else len(x) / sr)
    i0, i1 = int(a * sr) // f, int(b * sr) // f
    if i1 - i0 < 2:
        return t
    frames = x[i0 * f:i1 * f].reshape(-1, f)
    return round((i0 + int(np.argmin((frames ** 2).mean(1)))) * f / sr + 0.005, 3)


def splice(take: Path, fixes: list[tuple[float, float, Path]], out: Path) -> list[tuple[float, float]]:
    """`take` with each (a, b, clip): the stretch a..b replaced by the clip (a == b: put in at a), the clip trimmed,
    levelled to the speech around it and joined with short crossfades. Returns (where, change in length) for each
    fix in the new file's time, so later times can be shifted (`shift_words`)."""
    x, sr = _read(take)
    pieces, pos, changes, shift = [], 0, [], 0.0
    fade = int(FADE * sr)
    for a, b, clip in sorted(fixes):
        if a == b:
            a = b = _snap(x, sr, a)
        else:
            a, b = _snap(x, sr, a, hi=(a + b) / 2), _snap(x, sr, b, lo=(a + b) / 2)
        y, _ = _read(_as_wav(clip, sr, clip.with_suffix(".sr.wav")))
        y = _trim(y, sr)
        around = x[max(0, int((a - 1.5) * sr)):min(len(x), int((b + 1.5) * sr))]
        y = y * min(4.0, _rms(around) / max(_rms(y), 1e-6))  # as loud as your words around it
        gap = np.zeros(int(BREATH * sr), np.float32) if a == b else np.zeros(0, np.float32)
        y = np.concatenate([gap, y, gap])
        ia, ib = int(a * sr), int(b * sr)
        head = x[pos:ia].copy()
        if len(head) > fade and len(y) > fade:  # crossfade the joint
            ramp = np.linspace(0, 1, fade, dtype=np.float32)
            y[:fade] = y[:fade] * ramp + head[-fade:] * (1 - ramp)
            head = head[:-fade]
        pieces += [head, y]
        changes.append((round(a + shift, 3), round(len(y) / sr - (b - a), 3)))
        shift += len(y) / sr - (b - a)
        pos = ib
    tail = x[pos:].copy()
    if pieces and len(tail) > fade and len(pieces[-1]) > fade:
        ramp = np.linspace(0, 1, fade, dtype=np.float32)
        tail[:fade] = tail[:fade] * ramp + pieces[-1][-fade:] * (1 - ramp)
        pieces[-1] = pieces[-1][:-fade]
    _write(out, np.concatenate(pieces + [tail]), sr)
    return changes


def shift_words(words: list[Word], changes: list[tuple[float, float]]) -> list[Word]:
    """Word times after `splice`: everything after a fix moves by its change in length."""
    out = []
    for w in words:
        d = sum(c for at, c in changes if w.start >= at - 1e-3)
        out.append(Word(w.text, round(max(0.0, w.start + d), 3), round(max(0.0, w.end + d), 3)))
    return out


# ---------- your voice: the missing words spoken again ----------

SEEDS = (11, 23, 37)  # tries: the voice model now and then says other words, so each try is checked
REF_SECONDS = 12.0  # how much of your clean speech the voice model copies (it uses the first 10 s)


def reference(takes: list[tuple[Path, list[Word]]], out: Path) -> Path:
    """A stretch of your speech for the voice model to copy: from the take with the most words heard, its first word
    to the end of the last word inside REF_SECONDS."""
    audio, heard = max(takes, key=lambda t: len(t[1]))
    a = max(0.0, heard[0].start - 0.1)
    b = max((w.end for w in heard if w.end <= a + REF_SECONDS), default=heard[-1].end)
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", str(audio), "-ss", f"{a:.3f}", "-to", f"{b + 0.15:.3f}",
                    "-ac", "1", "-ar", "24000", str(out)], check=True)
    return out


def speakable(texts: list[str], language: str) -> tuple[list[str], str]:
    """The lines as the voice model reads them, and its language: Hindi and Hinglish entirely in Devanagari (English
    letters come out mangled: 'Scientists already human' as 'निसायन्तुस्ट आदरी विमन'; in Devanagari the checker heard
    100% of the line)."""
    if language == "english":
        return texts, "en"
    from .hinglish import to_devanagari

    return to_devanagari(texts), "hi"


def _span(line: str, gap: dict) -> list[int]:
    """The script tokens (`shoot._script_tokens` of the one line) of a gap's words."""
    from .shoot import _script_tokens

    want = set(range(gap["first_word"], gap["first_word"] + len(gap["words"])))
    return [t for t, tok in enumerate(_script_tokens([line])) if tok[1] in want]


def _cut_from(said: Path, line: str, gap: dict, heard: list[Word], out: Path) -> bool:
    """The gap's words cut out of a line spoken in your voice; False if they aren't all in it. Speech-to-text's word
    times are a little off and run into each other, so each cut moves to the quietest moment near it, as far as the
    middle of the word next to it (cutting only inward once took 'kom-' off 'computer')."""
    from .shoot import matches

    _, match = matches([line], heard)
    span = _span(line, gap)
    if not span or any(t not in match for t in span):
        return False
    x, sr = _read(said)
    i, j = match[span[0]], match[span[-1]]
    a, b = heard[i].start, heard[j].end
    lo = (heard[i - 1].start + heard[i - 1].end) / 2 if i > 0 else 0.0
    hi = (heard[j + 1].start + heard[j + 1].end) / 2 if j + 1 < len(heard) else len(x) / sr
    a = _snap(x, sr, a, lo=lo, hi=(a + b) / 2)
    b = _snap(x, sr, b, lo=(a + b) / 2, hi=hi)
    if b - a < 0.08:
        return False
    _write(out, x[int(a * sr):int(b * sr)], sr)
    return True


# Three ways to hear a few seconds of audio, and a majority decides: speech-to-text is unstable on a short clip and
# falls back to sampling when unsure, so one hearing can't be trusted (a spliced line with the rebuilt word in place
# came back as gibberish once, and with the word all three ways the next time; the line with the word cut out was
# heard without it 3 times of 3 one run, and 'with' it once in another).
DECODES = ({}, {"vad_filter": False}, {"beam_size": 1})


def hearings(path: Path, line: str, language: str) -> list[set[int]]:
    """The script tokens of `line` heard in `path`, once per way in `DECODES`."""
    from .shoot import _hear, matches

    return [set(matches([line], _hear(language, path, **opts) or [])[1]) for opts in DECODES]


def heard_by(hs: list[set[int]], tokens: list[int]) -> int:
    """How many of the hearings heard every one of `tokens`."""
    return sum(1 for h in hs if tokens and all(t in h for t in tokens))


def repair(items: list[dict], ref: Path, language: str, work: Path, progress) -> list[dict]:
    """Each item {wav (one line of your take), text (the line), gaps (times relative to the wav), out}: the gaps
    spoken in your voice and spliced in. The voice engine speaks whole lines (a word on its own came out as 3.6 s of
    other words); each try's words are cut out, spliced in and the line is heard again: kept only when the words are
    there now, else the next try (`SEEDS`). Returns per item {ok, fixed: [words], failed: [words], changes} (out is
    written only when something was fixed)."""
    from . import voice_engine
    from .shoot import _hear

    work.mkdir(parents=True, exist_ok=True)
    spoken, lang = speakable([it["text"] for it in items], language)
    best: list[dict] = [{"ok": False, "fixed": [], "failed": [g["text"] for g in it["gaps"]], "changes": []} for it in items]
    pending = list(range(len(items)))
    for seed in SEEDS:
        if not pending:
            break
        job = [{"text": spoken[i], "out": str(work / f"line{i:03d}-try{seed}.wav"), "seed": seed} for i in pending]
        voice_engine.run("speak", {"ref": str(ref), "lang": lang, "items": job}, work, progress, "Your voice")
        still = []
        for i in pending:
            it = items[i]
            said = work / f"line{i:03d}-try{seed}.wav"
            got: dict[int, Path] = {}
            for opts in DECODES:  # the words' times in what your voice said, heard whichever way finds them
                heard = _hear(language, said, **opts) or []
                for g, gap in enumerate(it["gaps"]):
                    clip = work / f"line{i:03d}-try{seed}-gap{g}.wav"
                    if g not in got and _cut_from(said, it["text"], gap, heard, clip):
                        got[g] = clip
                if len(got) == len(it["gaps"]):
                    break
            if got:
                trial = work / f"line{i:03d}-try{seed}-spliced.wav"
                changes = splice(Path(it["wav"]), [(it["gaps"][g]["at"][0], it["gaps"][g]["at"][1], c) for g, c in got.items()], trial)
                hs = hearings(trial, it["text"], language)  # are the words there now? (most hearings must say so)
                fixed = [it["gaps"][g]["text"] for g in got if heard_by(hs, _span(it["text"], it["gaps"][g])) > len(hs) // 2]
                if len(fixed) > len(best[i]["fixed"]):
                    trial.replace(it["out"])
                    best[i] = {"ok": True, "fixed": fixed, "changes": changes,
                               "failed": [g["text"] for g in it["gaps"] if g["text"] not in fixed]}
            progress(f"Your voice: line {i + 1}, try {SEEDS.index(seed) + 1}: "
                     + (f"rebuilt {', '.join(best[i]['fixed'])}" if best[i]["fixed"] else "not clear enough yet"))
            if best[i]["failed"]:
                still.append(i)
        pending = still
    return best
