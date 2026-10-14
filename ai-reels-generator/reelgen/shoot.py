"""Shoot: videos of you on camera, filmed in your phone's own camera app, with the app as teleprompter and editor.

1. You paste your script (and a hook). It is cut into lines in code (scriptvideo.parse_script / parse_hook, so no word
   ever changes) and the lines into shots of one or two lines (`make_shots`), one take each.
2. Claude plans it (`plan`: one call, no web search: the Script Video storyboard plus `on_camera` for every line):
   which lines show you and which show B-roll (stock footage, motion graphics, AI stills in the hook) while your
   voice goes on, the chapters, the music and the sounds.
3. The Shoot tab's teleprompter shows each shot and highlights the words as you say them (the browser's speech
   recognition on this computer's mic, matched loosely to the script: web/index.html). You film the shot with the
   phone's camera app, as many times as you like.
4. You upload the best take of each shot (from the phone over Wi-Fi, or from this computer). `process_take` makes a
   1080p H.264 copy (HDR tone-mapped, upright, cropped to the video's shape), cleans the sound, transcribes it
   (faster-whisper, offline) and finds where each line starts and ends; the tab shows how well it matches the script.
5. Make the video (`run_shoot`): the Script Video path through the long pipeline (`longform._long_loop` with `manual`):
   your takes are the voice (`voices_for`), on-camera lines show your take ('camera' visuals, a punch-in on every other
   cut), the others their B-roll; captions from your words; the cinematic hook, music, sound design and mastering as in
   every long video. 16:9 for YouTube or 9:16 for Shorts.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Callable

from pydantic import Field, create_model

from .config import Config
from .scriptvideo import BoardBeat, BoardShot, ScriptInput, Storyboard, parse_hook, parse_script
from .video import FFMPEG, media_seconds
from .voice import SceneAudio, Word

log = logging.getLogger(__name__)
Progress = Callable[[str], None]

FOLDER = "shoots"  # <output>/shoots/<id>/project.json, takes/
FORMATS = {"long": (1920, 1080), "short": (1080, 1920)}
LANGUAGES = ("english", "hinglish", "hindi")
SHOT_LINES, SHOT_WORDS = 2, 50  # a shot is one or two lines, at most this many words
HOOK_SHOT_WORDS = 30
LEAD, TAIL = 0.18, 0.35  # seconds kept before a take's first word and after its last
PUNCH = 1.12  # every other cut between takes punches in, so jump cuts feel deliberate
FILLER = {"a", "an", "the", "and", "of", "to", "in", "on", "at", "is", "it", "so", "but", "that", "this", "was",
          "hai", "hain", "hu", "hun", "hoon", "tha", "thi", "ki", "ka", "ke", "ko", "se", "aur", "bhi", "ye", "wo", "na",
          "ne"}  # small words speech-to-text drops or joins to the word before ('rahe hain' -> 'रहें'): not flagged

_lock = threading.Lock()  # project.json writes
_work = threading.Lock()  # one take processed at a time (transcoding and transcription use every core)


# ---------- projects ----------

def root(cfg: Config) -> Path:
    return cfg.output_dir / FOLDER


def folder(cfg: Config, pid: str) -> Path:
    path = root(cfg) / Path(pid).name
    if not (path / "project.json").exists():
        raise FileNotFoundError(pid)
    return path


def load(cfg: Config, pid: str) -> dict:
    return json.loads((folder(cfg, pid) / "project.json").read_text(encoding="utf-8"))


def _save(cfg: Config, proj: dict) -> None:
    path = root(cfg) / proj["id"] / "project.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(proj, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def update(cfg: Config, pid: str, fn: Callable[[dict], None]) -> dict:
    """Change a project under the lock (planning, take processing and the page all write it)."""
    with _lock:
        proj = load(cfg, pid)
        fn(proj)
        _save(cfg, proj)
        return proj


def projects(cfg: Config) -> list[dict]:
    out = []
    for path in sorted(root(cfg).glob("*/project.json"), reverse=True) if root(cfg).exists() else []:
        try:
            p = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out.append({"id": p["id"], "title": p["title"], "created": p["created"], "format": p["format"],
                    "shots": len(p["shots"]), "ready": sum(1 for s in p["shots"] if (s.get("take") or {}).get("status") == "ready"),
                    "plan": p["plan"]["status"], "video": p.get("video")})
    return out


def make_shots(hook: list[str], lines: list[str], marked: list[tuple[int, str]]) -> tuple[list[dict], list[dict]]:
    """Every line (hook lines first) and the shots they are filmed in: hook lines up to HOOK_SHOT_WORDS together,
    script lines one or two at a time (SHOT_WORDS at most), a new shot at every chapter the user marked."""
    rows = [{"k": i, "part": "hook", "i": i, "text": t, "camera": None} for i, t in enumerate(hook)]
    rows += [{"k": len(hook) + i, "part": "script", "i": i, "text": t, "camera": None} for i, t in enumerate(lines)]
    starts = {i for i, _ in marked}
    shots: list[dict] = []
    cur: list[dict] = []

    def close() -> None:
        if cur:
            shots.append({"n": len(shots) + 1, "lines": [r["k"] for r in cur], "hook": cur[0]["part"] == "hook",
                          "take": None})
            cur.clear()

    for r in rows:
        words = sum(len(x["text"].split()) for x in cur) + len(r["text"].split())
        limit = HOOK_SHOT_WORDS if r["part"] == "hook" else SHOT_WORDS
        new_part = cur and cur[0]["part"] != r["part"]
        if cur and (new_part or words > limit or (r["part"] == "script" and (len(cur) >= SHOT_LINES or r["i"] in starts))):
            close()
        cur.append(r)
    close()
    return rows, shots


def new_project(cfg: Config, given: dict) -> dict:
    title, script = given["title"].strip(), given["script"].strip()
    if not title or not script:
        raise ValueError("The title and the script are needed.")
    lines, marked = parse_script(script)
    if not lines:
        raise ValueError("The script has no lines to read.")
    hook = parse_hook(given.get("hook", ""))
    rows, shots = make_shots(hook, lines, marked)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    proj = {"id": f"{stamp}-{uuid.uuid4().hex[:4]}", "created": stamp, "title": title,
            "description": given.get("description", "").strip(), "hook": given.get("hook", "").strip(), "script": script,
            "language": given.get("language") if given.get("language") in LANGUAGES else "english",
            "format": given.get("format") if given.get("format") in FORMATS else "long",
            "screen_text": "script" if given.get("screen_text") == "script" else "english",
            "lines": rows, "marked": marked, "shots": shots, "plan": {"status": "idle", "error": ""}, "video": None}
    (root(cfg) / proj["id"] / "takes").mkdir(parents=True, exist_ok=True)
    _save(cfg, proj)
    return proj


def delete(cfg: Config, pid: str) -> None:
    shutil.rmtree(folder(cfg, pid), ignore_errors=True)


# ---------- the plan: which lines show you (one Claude call) ----------

CAMERA_HELP = ("True: the viewer sees you saying this line (opinions, questions to the viewer, turns in the story, the "
               "opening line, the call to action, emotional moments). False: B-roll, the visual below shows the evidence "
               "(a number, a date, a place, a process, a comparison, a quote) while your voice goes on.")
ShootBeat = create_model("ShootBeat", __base__=BoardBeat, on_camera=(bool, Field(default=True, description=CAMERA_HELP)))
ShootShot = create_model("ShootShot", __base__=BoardShot, on_camera=(bool, Field(default=False, description=CAMERA_HELP + " In the hook only for 2-3 key lines, the big question among them; silent and flash shots never.")))
ShootBoard = create_model("ShootBoard", __base__=Storyboard,
                          hook=(list[ShootShot], Storyboard.model_fields["hook"]),
                          beats=(list[ShootBeat], Storyboard.model_fields["beats"]))

SHOOT_RULES = """

You on camera: the presenter filmed every line of this script on their own camera; their recorded voice is the \
narration. For every line decide `on_camera`: show them, or cut to B-roll (the line's visual) while their voice goes \
on. Like a documentary presenter's video: about half the lines on camera; on camera for the opening line, direct \
address, opinions, questions to the viewer, turns in the story, emotional moments and the call to action; B-roll for \
facts, numbers, dates, places, processes, comparisons and quotes, so the evidence is on screen when it is said. Never \
more than 3 lines in a row on camera, never more than 4 in a row without them. Still give every line a visual: it is \
the B-roll, and the fallback if a take is missing. In the hook, most shots are B-roll (pictures, flash shots), with the \
presenter on camera for 2-3 key lines."""

TALL_RULES = """
The video is a tall 9:16 phone video: timelines (2-5 dates) and steps (2-4) stack top to bottom, compare shows two tall \
bars, a chart has 3-6 points; keep words short (a keyword at most 3 words, a headline at most 6, item labels at most \
3 words)."""


def _given(proj: dict) -> ScriptInput:
    return ScriptInput(title=proj["title"], description=proj["description"], hook=proj["hook"], script=proj["script"],
                       screen_text=proj["screen_text"])


def _parts(proj: dict) -> tuple[list[str], list[str], list[tuple[int, str]]]:
    hook = [r["text"] for r in proj["lines"] if r["part"] == "hook"]
    lines = [r["text"] for r in proj["lines"] if r["part"] == "script"]
    return hook, lines, [tuple(m) for m in proj["marked"]]


def plan(cfg: Config, pid: str) -> dict:
    """Claude's storyboard with on-camera lines; saved in the project, which shows it on every line."""
    from .scriptvideo import storyboard

    update(cfg, pid, lambda p: p["plan"].update(status="running", error=""))
    proj = load(cfg, pid)
    hook, lines, marked = _parts(proj)
    try:
        board = storyboard(cfg, _given(proj), hook, lines, marked, schema=ShootBoard,
                           extra=SHOOT_RULES + (TALL_RULES if proj["format"] == "short" else ""))
    except Exception as exc:  # noqa: BLE001 - shown on the page; the user can plan again
        log.exception("Shoot plan failed")
        reason = str(exc)[:400]
        update(cfg, pid, lambda p: p["plan"].update(status="failed", error=reason))
        raise
    cam = {b.line: b.on_camera for b in board.beats}
    hook_cam = {s.line: s.on_camera for s in board.hook if s.line}

    def apply(p: dict) -> None:
        for r in p["lines"]:
            r["camera"] = (hook_cam.get(r["i"] + 1, False) if r["part"] == "hook" else cam.get(r["i"] + 1, True))
        p["plan"] = {"status": "done", "error": "", "board": board.model_dump(), "at": datetime.now(timezone.utc).isoformat()}

    return update(cfg, pid, apply)


def plan_in_background(cfg: Config, pid: str) -> None:
    def go() -> None:
        try:
            plan(cfg, pid)
        except Exception:  # noqa: BLE001 - recorded in the project
            pass

    threading.Thread(target=go, daemon=True).start()


# ---------- matching what you said to the script ----------

_DEVA = {  # Devanagari to Roman letters, only as far as the matching needs (vowels are dropped anyway)
    **dict(zip("कखगघङचछजझञटठडढणतथदधनपफबभमयरलवशषसह",
               ["k", "kh", "g", "gh", "n", "C", "Ch", "j", "jh", "n", "t", "th", "d", "dh", "n", "t", "th", "d", "dh",
                "n", "p", "f", "b", "bh", "m", "y", "r", "l", "v", "sh", "sh", "s", "h"])),
    **dict(zip("अआइईउऊएऐओऔऋ", ["a", "aa", "i", "ii", "u", "uu", "e", "ai", "o", "au", "ri"])),
    **dict(zip("ािीुूेैोौृ", ["aa", "i", "ii", "u", "uu", "e", "ai", "o", "au", "ri"])),
    "ं": "n", "ँ": "n", "ः": "h", "्": "", "़": "", "ॉ": "o", "ॅ": "e",
    **dict(zip("०१२३४५६७८९", "0123456789")),
}


# Roman spellings that don't sound like their letters, so a word typed in Roman letters gives the letters Devanagari
# gives for the same sound (Hindi speech-to-text writes English words as they sound: 'कमान्ट्स', 'साईंटिस'). C = 'ch'.
_SPELL = [(r"^kn", "n"), (r"^wr", "r"), (r"^ps", "s"), (r"gh(?=t|$)", ""), (r"ph", "f"), (r"ck", "k"),
          (r"ti(?=on)|si(?=on)", "sh"), (r"t(?=ure)", "C"), (r"dg(?=e)", "j"), (r"ch", "C"), (r"sc(?=[eiy])", "s"),
          (r"c(?=[eiy])", "s"), (r"c", "k"), (r"x", "ks"), (r"q", "k"), (r"z", "j"), (r"(?<=[aeiou])w(?![aeiou])", ""),
          (r"w", "v")]
# Sounds a Hindi speaker (and speech-to-text) swaps inside a word: voiced and voiceless pairs, m/n, ch/j.
_CLASS = str.maketrans({"g": "k", "d": "t", "b": "p", "f": "p", "C": "j", "m": "n"})


def skeleton(word: str) -> str:
    """A word reduced to how it sounds, in any spelling or script: Roman letters, English spellings read as sounds,
    its first sound, then only the consonants, with sounds that are easily swapped merged ('jaante', 'jante', 'जानते'
    -> 'jnt'; 'commands', 'कमान्ट्स' -> 'knts'; 'AI', 'याई' -> 'a'). Keep in step with `skel` in web/index.html."""
    deva = any("\u0900" <= c <= "\u097f" for c in word)
    w = "".join(_DEVA.get(c, c) for c in word.lower())
    w = re.sub(r"['’]s\b", "", w)
    w = re.sub(r"[^a-z0-9C]", "", w)
    for a, b in [] if deva else _SPELL:  # Devanagari is written as it sounds already
        w = re.sub(a, b, w)
    if not w or w.isdigit():
        return w
    first = "a" if w[0] in "aeiouy" else "c" if w[0] == "C" else w[0]  # the first sound keeps its voicing
    rest = re.sub(r"[aeiouhy]", "", w[1:]).translate(_CLASS)
    return re.sub(r"(.)\1+", r"\1", first + rest)


@lru_cache(maxsize=65536)
def alike(a: str, b: str) -> float:
    """How surely two skeletons are the same word: 1 the same, 0.6-0.9 close (a consonant heard differently, one
    added or dropped), 0 not the same. Short ones must be equal, except a nasal ending ('rahe', 'रहें')."""
    if a == b:
        return 1.0 if a else 0.0
    if not a or not b or a[0] != b[0] or a.isdigit() or b.isdigit():
        return 0.0
    if min(len(a), len(b)) == 1:
        return 0.7 if a + "n" == b or b + "n" == a else 0.0
    lcs = [0] * (len(b) + 1)
    for x in a:
        prev = 0
        for j, y in enumerate(b):
            prev, lcs[j + 1] = lcs[j + 1], prev + 1 if x == y else max(lcs[j + 1], lcs[j])
    ratio = 2 * lcs[-1] / (len(a) + len(b))
    near = ratio >= 0.6 or (ratio >= 0.5 and min(len(a), len(b)) >= 3 and a[:2] == b[:2])  # 'commands', 'कमाण्च'
    return round(ratio, 3) if near else 0.0


RUN = 0.5  # a word heard right after the one before it counts this much more: a restarted line keeps its full attempt


def pairs(script: list[str], heard: list[str]) -> dict[int, int]:
    """Script word -> heard word, in order, the most and surest matches (each word's `alike`, plus `RUN` for every
    word that follows its neighbour): what you skipped stays unmatched, ad-libs and false starts are passed over, and
    of a line said twice the last full attempt is kept."""
    n, m = len(script), len(heard)
    none = float("-inf")
    best = [[0.0] * (m + 1) for _ in range(n + 1)]
    run = [[none] * (m + 1) for _ in range(n + 1)]  # best alignment in which script[i-1] is heard as heard[j-1]
    for i in range(1, n + 1):
        a, bi, ri, bp, rp = script[i - 1], best[i], run[i], best[i - 1], run[i - 1]
        for j in range(1, m + 1):
            if s := alike(a, heard[j - 1]):
                ri[j] = s + max(bp[j - 1], rp[j - 1] + RUN)
            bi[j] = max(ri[j], bp[j], bi[j - 1])
    out: dict[int, int] = {}
    i, j, linked = n, m, False
    while i > 0 and j > 0:
        if linked or best[i][j] == run[i][j]:
            out[i - 1] = j - 1
            linked = run[i - 1][j - 1] + RUN > best[i - 1][j - 1]
            i, j = i - 1, j - 1
        elif best[i][j] == best[i - 1][j]:
            i -= 1
        else:
            j -= 1
    return out


def _script_tokens(lines: list[str]) -> list[tuple[int, int, str]]:
    """(line, word index in the line, skeleton) for every word that has one; 'blue-green' is heard as two words."""
    return [(k, j, s) for k, text in enumerate(lines) for j, w in enumerate(text.split())
            for part in re.split(r"[-–—/]", w) if (s := skeleton(part))]


def _cluster(idx: list[int], gap: int = 6) -> list[int]:
    """The longest run of heard-word indices without a gap over `gap`: a line said twice keeps its better attempt."""
    if not idx:
        return []
    idx = sorted(idx)
    runs, cur = [], [idx[0]]
    for i in idx[1:]:
        if i - cur[-1] > gap:
            runs.append(cur)
            cur = []
        cur.append(i)
    runs.append(cur)
    return max(runs, key=len)


def matches(lines: list[str], heard: list[Word]) -> tuple[list[tuple[int, int, str]], dict[int, int]]:
    """The script's tokens (`_script_tokens`) and, for each one heard, the heard word it is: in order, and only the
    best cluster of each line (`_cluster`), so a false start's words don't count."""
    tokens = _script_tokens(lines)
    match = pairs([t[2] for t in tokens], [skeleton(w.text) for w in heard])  # script token -> heard word
    out: dict[int, int] = {}
    for k in range(len(lines)):
        mine = [t for t, tok in enumerate(tokens) if tok[0] == k]
        kept = set(_cluster([match[t] for t in mine if t in match]))
        out.update({t: match[t] for t in mine if match.get(t) in kept})
    return tokens, out


def align(lines: list[str], heard: list[Word], length: float) -> list[dict]:
    """Where each line of a take starts and ends (cut in the pause between lines), which heard words are its own, and
    which script words weren't heard."""
    tokens, match = matches(lines, heard)
    out = []
    for k, text in enumerate(lines):
        mine = [t for t, tok in enumerate(tokens) if tok[0] == k]
        hits = sorted(match[t] for t in mine if t in match)
        missing = list(dict.fromkeys(text.split()[tokens[t][1]] for t in mine if t not in match))
        out.append({"first": hits[0] if hits else None, "last": hits[-1] if hits else None,
                    "matched": round(1 - len(missing) / max(1, len(mine)), 2),
                    "missing": [m for m in missing if skeleton(m) and m.lower().strip(".,!?;:") not in FILLER][:12]})
    # Cut points: halfway through the pause between one line's last word and the next one's first.
    known = [(k, r) for k, r in enumerate(out) if r["first"] is not None]
    if not known:
        return [{"start": 0.0, "end": length, "speech": [0.0, length], **r} for r in out]
    for k, r in enumerate(out):
        if r["first"] is None:  # nothing heard of this line: between its neighbours, by word count
            before = max((x for x, _ in known if x < k), default=None)
            after = min((x for x, _ in known if x > k), default=None)
            a = heard[out[before]["last"]].end if before is not None else 0.0
            b = heard[out[after]["first"]].start if after is not None else length
            r["speech"] = [round(a, 3), round(b, 3)]
        else:
            r["speech"] = [heard[r["first"]].start, heard[r["last"]].end]
    for k, r in enumerate(out):
        a, b = r["speech"]
        r["start"] = round(max(0.0, a - LEAD) if k == 0 else (out[k - 1]["speech"][1] + a) / 2, 3)
        r["end"] = round(min(length, b + TAIL) if k == len(out) - 1 else (b + out[k + 1]["speech"][0]) / 2, 3)
        r["end"] = max(r["end"], r["start"] + 0.3)
    return out


def caption_words(text: str, heard: list[Word], r: dict, offset: float) -> list[Word]:
    """The line's own words (as written, for captions and sound cues) on the times you said them: matched words take
    their heard times, the others are spread between them. Times relative to `offset` (the line's cut)."""
    words = text.split()
    sk = [skeleton(w) for w in words]
    pool = heard[r["first"]:r["last"] + 1] if r.get("first") is not None else []
    times: list[tuple[float, float] | None] = [None] * len(words)
    if pool:
        for i, j in pairs(sk, [skeleton(w.text) for w in pool]).items():
            times[i] = (pool[j].start, pool[j].end)
    a, b = r["speech"]
    anchors = [(-1, a)] + [(i, t[0]) for i, t in enumerate(times) if t] + [(len(words), b)]
    for (i0, t0), (i1, t1) in zip(anchors, anchors[1:]):
        gap = [i for i in range(i0 + 1, i1)]
        if not gap:
            continue
        start = times[i0][1] if i0 >= 0 and times[i0] else t0
        step = max(0.05, (t1 - start) / (len(gap) + 0.0001))
        for n, i in enumerate(gap):
            times[i] = (start + n * step, start + (n + 1) * step - 0.02)
    return [Word(w, round(max(0.0, t[0] - offset), 3), round(max(0.0, t[1] - offset), 3)) for w, t in zip(words, times)]


# ---------- a take ----------

def _info(path: Path) -> dict:
    err = subprocess.run([FFMPEG, "-hide_banner", "-i", str(path)], capture_output=True, text=True, encoding="utf-8",
                         errors="replace").stderr
    video = next((ln for ln in err.splitlines() if "Video:" in ln), "")
    out: dict = {"duration": 0.0, "width": 0, "height": 0, "rotation": 0, "hdr": False, "audio": "Audio:" in err}
    if m := re.search(r"Duration: (\d+):(\d+):([\d.]+)", err):
        out["duration"] = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
    if m := re.search(r", (\d{2,5})x(\d{2,5})", video):
        out["width"], out["height"] = int(m[1]), int(m[2])
    if m := re.search(r"rotation of (-?[\d.]+) degrees", err) or re.search(r"rotate\s*:\s*(-?\d+)", err):
        out["rotation"] = int(round(float(m[1]))) % 360
    if out["rotation"] in (90, 270):
        out["width"], out["height"] = out["height"], out["width"]
    out["hdr"] = bool(re.search(r"arib-std-b67|smpte2084", video))
    return out


TONEMAP = ("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=tonemap=hable:desat=0,"
           "zscale=t=bt709:m=bt709:r=tv,format=yuv420p")


def _proxy(src: Path, dst: Path, size: tuple[int, int], hdr: bool) -> bool:
    """A copy the editor plays fast: the video's own size (cropped, never stretched), 30 fps, H.264 with a key frame
    every half second, the sound kept for listening on the page. HDR (the iPhone's default) is tone-mapped to normal
    video; returns whether that worked."""
    w, h = size
    fit = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,fps=30"
    base = [FFMPEG, "-y", "-loglevel", "error", "-i", str(src), "-map", "0:v:0", "-map", "0:a:0?"]
    tail = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-g", "15", "-pix_fmt", "yuv420p", "-c:a", "aac",
            "-b:a", "160k", "-ac", "2", "-movflags", "+faststart", str(dst)]
    if hdr:
        if subprocess.run(base + ["-vf", f"{TONEMAP},{fit}"] + tail, capture_output=True).returncode == 0:
            return True
        log.warning("HDR tone-mapping failed for %s; converting without it", src.name)
    subprocess.run(base + ["-vf", fit] + tail, capture_output=True, check=True)
    return not hdr


def take_paths(cfg: Config, pid: str, n: int) -> dict[str, Path]:
    d = folder(cfg, pid) / "takes"
    return {"proxy": d / f"shot{n:02d}.mp4", "audio": d / f"shot{n:02d}.wav"}


TAKE_TYPES = (".mov", ".mp4", ".m4v", ".webm", ".mkv", ".3gp")


def take_target(cfg: Config, pid: str, n: int, filename: str) -> Path:
    """Where an uploaded take of shot `n` is written (shotNN-original.<ext>); the shot's old files go."""
    proj = load(cfg, pid)
    if not any(s["n"] == n for s in proj["shots"]):
        raise ValueError(f"There is no shot {n}")
    ext = Path(filename or "take.mov").suffix.lower() or ".mov"
    if ext not in TAKE_TYPES:
        raise ValueError(f"Can't use a {ext} file as a video take (a phone's .mov or .mp4 works)")
    d = folder(cfg, pid) / "takes"
    d.mkdir(exist_ok=True)
    for old in d.glob(f"shot{n:02d}*"):
        old.unlink(missing_ok=True)
    return d / f"shot{n:02d}-original{ext}"


CHECKER = 2  # how a take's words are checked; takes checked an older way are checked again (`recheck_old`)


def _hear(language: str, audio: Path, **options) -> list[Word] | None:
    """What was said in a take. Hindi and Hinglish go to the 'small' model in Hindi mode (REEL_WHISPER_HINDI_MODEL):
    in English mode speech-to-text translates Hindi ('Lekin sawaal hai' came back as 'But the question is', so a
    Hinglish take showed 28% of its words heard), and the 'base' model translates even in Hindi mode. 'small' writes
    what you said in Devanagari, English words as they sound ('कमान्ट्स'), which `skeleton` reads."""
    from .myvoice import transcribe

    model = "" if language == "english" else os.environ.get("REEL_WHISPER_HINDI_MODEL", "small")
    lang = "english" if language == "english" else "hindi"
    heard = transcribe(audio, lang, model, **options)
    if heard and _looped(heard):  # stuck in a loop ('हूँँँँँँँँ...' at a hard joint): once more, without carrying text over
        log.info("Speech-to-text looped on %s; trying again", Path(audio).name)
        again = transcribe(audio, lang, model, condition_on_previous_text=False, temperature=(0.2, 0.4, 0.6, 0.8))
        if again and (not _looped(again) or len(again) > len(heard)):
            heard = again
    return [w for w in heard if not _looped([w])] if heard else heard


def _looped(heard: list[Word]) -> bool:
    """A transcript stuck in a loop: a letter repeated six times, or a 'word' longer than any real one."""
    return any(re.search(r"(.)\1{5,}", w.text) or len(w.text) > 30 for w in heard)


def _best_hearing(language: str, audio: Path, lines: list[str], length: float) -> list[Word] | None:
    """What was said in a take, heard once, and the other ways too when that matched less than GOOD_HEARING of the
    script: the best match is kept. One hearing of a take with a rough edit in it came back 23% when it was ~95%."""
    from .wordfix import DECODES

    heard = _hear(language, audio)
    if not heard or _judge(lines, heard, length)[2] >= GOOD_HEARING:
        return heard
    best, score = heard, _judge(lines, heard, length)[2]
    for opt in DECODES[1:]:
        other = _hear(language, audio, **opt)
        if other and (m := _judge(lines, other, length)[2]) > score:
            best, score = other, m
    return best


def _judge(lines: list[str], heard: list[Word], length: float) -> tuple[list[dict], str, float]:
    """The take's lines (cut points, words not heard), its verdict and the share of words heard."""
    rows = align(lines, heard, length)
    worst = min(r["matched"] for r in rows)
    missed = sum(len(r["missing"]) for r in rows)
    verdict = "good" if worst >= 0.8 and missed <= 1 else "check words"
    return rows, verdict, round(sum(r["matched"] for r in rows) / len(rows), 2)


def process_take(cfg: Config, pid: str, n: int, original: Path) -> dict:
    """Prepare an uploaded take: the editor's copy, the cleaned sound, what you said and where each line is."""
    from .myvoice import _clean

    proj = load(cfg, pid)
    shot = next(s for s in proj["shots"] if s["n"] == n)
    lines = [proj["lines"][k]["text"] for k in shot["lines"]]
    paths = take_paths(cfg, pid, n)
    take = {"status": "processing", "file": original.name, "uploaded": datetime.now(timezone.utc).isoformat()}
    update(cfg, pid, lambda p: next(s for s in p["shots"] if s["n"] == n).update(take=take))
    try:
        with _work:
            info = _info(original)
            if not info["duration"] or not info["width"]:
                raise ValueError("This file has no video in it")
            if not info["audio"]:
                raise ValueError("This take has no sound: the voice comes from it")
            size = FORMATS[proj["format"]]
            converted = _proxy(original, paths["proxy"], size, info["hdr"])
            _clean(original, paths["audio"], trim=False)
            heard = _best_hearing(proj["language"], paths["audio"], lines, media_seconds(paths["audio"]))
        length = media_seconds(paths["audio"])
        notes = []
        portrait = info["height"] > info["width"]
        if portrait != (proj["format"] == "short"):
            notes.append("Filmed " + ("upright" if portrait else "sideways") + " for a " + ("9:16 Short" if proj["format"] == "short" else "16:9 video")
                         + ": the picture is cropped to fit. Turn the phone " + ("upright" if proj["format"] == "short" else "sideways") + " for the next takes.")
        if info["hdr"]:
            notes.append("HDR video was converted to normal colours." if converted else
                         "HDR video couldn't be converted and may look washed out: turn off Settings > Camera > Record Video > HDR Video.")
        if heard is None:
            rows = [{"start": 0.0, "end": length, "speech": [0.0, length], "first": None, "last": None, "matched": None,
                     "missing": []}] if len(lines) == 1 else None
            if rows is None:  # no transcript: split by word count
                total = sum(len(t.split()) for t in lines)
                rows, t = [], 0.0
                for text in lines:
                    d = length * len(text.split()) / max(1, total)
                    rows.append({"start": round(t, 3), "end": round(t + d, 3), "speech": [t, t + d], "first": None,
                                 "last": None, "matched": None, "missing": []})
                    t += d
            verdict = "no transcript"
            notes.append("faster-whisper isn't installed, so the words weren't checked and lines are cut by length.")
        else:
            rows, verdict, matched = _judge(lines, heard, length)
        take.update(status="ready", duration=round(length, 2), width=info["width"], height=info["height"],
                    hdr=info["hdr"], verdict=verdict, notes=notes, lines=rows, checker=CHECKER,
                    heard=[[w.text, w.start, w.end] for w in heard] if heard else None,
                    matched=None if heard is None else matched)
    except Exception as exc:  # noqa: BLE001 - shown on the shot's card
        log.exception("Take %s of %s failed", n, pid)
        take.update(status="failed", error=str(exc)[:300])
    update(cfg, pid, lambda p: next(s for s in p["shots"] if s["n"] == n).update(take=take))
    return take


_active: set[tuple[str, int]] = set()  # takes being prepared or checked by this run of the app


def process_in_background(cfg: Config, pid: str, n: int, original: Path) -> None:
    def go() -> None:
        try:
            process_take(cfg, pid, n, original)
        finally:
            _active.discard((pid, n))

    _active.add((pid, n))  # before the card says 'processing', so opening the project never starts it twice
    update(cfg, pid, lambda p: next(s for s in p["shots"] if s["n"] == n).update(
        take={"status": "processing", "file": original.name}))
    threading.Thread(target=go, daemon=True).start()


def recheck(cfg: Config, pid: str, n: int) -> None:
    """Check a ready take's words again the current way (`CHECKER`), without preparing the video again: a new
    transcript for Hindi and Hinglish, the saved one matched again for English. A failed check keeps the old one."""
    proj = load(cfg, pid)
    shot = next(s for s in proj["shots"] if s["n"] == n)
    lines = [proj["lines"][k]["text"] for k in shot["lines"]]
    old = shot.get("take") or {}
    audio = take_paths(cfg, pid, n)["audio"]
    try:
        with _work:
            if proj["language"] == "english" and old.get("heard"):
                heard = [Word(t, a, b) for t, a, b in old["heard"]]
            else:
                heard = _best_hearing(proj["language"], audio, lines, media_seconds(audio))
        length = media_seconds(audio)
        if not heard:
            raise ValueError("nothing was heard")
        rows, verdict, matched = _judge(lines, heard, length)
        new = {"verdict": verdict, "lines": rows, "matched": matched, "checker": CHECKER,
               "heard": [[w.text, w.start, w.end] for w in heard]}
        log.info("Shot %s of %s checked again: %d%% of the words heard (was %d%%)", n, pid, round(matched * 100),
                 round((old.get("matched") or 0) * 100))
    except Exception as exc:  # noqa: BLE001 - the take keeps its earlier check
        log.warning("Checking shot %s of %s again failed: %s", n, pid, exc)
        new = {}

    def put(p: dict) -> None:
        take = next(s for s in p["shots"] if s["n"] == n).get("take")
        if take and take.get("file") == old.get("file"):  # not replaced meanwhile
            take.update(new)
            take.pop("rechecking", None)

    update(cfg, pid, put)


def recheck_old(cfg: Config, proj: dict) -> dict:
    """When a project is opened: takes checked an older way are checked again, and takes left half-prepared when the
    app closed are prepared again, in the background (each once per run of the app). Returns the project as shown."""
    pid = proj["id"]
    stale = [s["n"] for s in proj["shots"] if (t := s.get("take") or {}).get("status") == "ready"
             and t.get("heard") is not None and t.get("checker", 1) < CHECKER and (pid, s["n"]) not in _active]
    stuck = [s for s in proj["shots"] if (s.get("take") or {}).get("status") == "processing" and (pid, s["n"]) not in _active]
    for s in stuck:
        original = folder(cfg, pid) / "takes" / str(s["take"].get("file") or "")
        if s["take"].get("file") and original.exists():
            process_in_background(cfg, pid, s["n"], original)
    if not stale:
        return load(cfg, pid) if stuck else proj
    _active.update((pid, n) for n in stale)  # never removed: a check that fails isn't retried in a loop

    def mark(p: dict) -> None:
        for s in p["shots"]:
            if s["n"] in stale and s.get("take"):
                s["take"]["rechecking"] = True

    proj = update(cfg, pid, mark)

    def go() -> None:
        for n in stale:
            recheck(cfg, pid, n)

    threading.Thread(target=go, daemon=True).start()
    return proj


def remove_take(cfg: Config, pid: str, n: int) -> None:
    d = folder(cfg, pid) / "takes"
    for f in d.glob(f"shot{n:02d}*"):
        f.unlink(missing_ok=True)
    update(cfg, pid, lambda p: next(s for s in p["shots"] if s["n"] == n).update(take=None))


def missing_takes(proj: dict) -> list[int]:
    return [s["n"] for s in proj["shots"] if (s.get("take") or {}).get("status") != "ready"]


# ---------- the edit: your takes as the voice and the picture ----------

def _cut(src: Path, dst: Path, start: float, end: float) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(src), "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
                    "-ac", "1", "-ar", "24000", str(dst)], check=True)


def voices_for(shoot: dict, script, work: Path, progress: Progress) -> tuple[list[list[SceneAudio]], list, dict]:
    """The video's voice from your takes, line by line, and the picture of each on-camera line.
    Returns (voices per chapter, voices per hook shot (None for silent shots), visual overrides by (chapter, beat) and
    ('hook', shot index)). Called by longform._long_loop when it builds the timeline of a Shoot video."""
    from .audio import level_voice

    proj = json.loads(Path(shoot["project"]).read_text(encoding="utf-8"))
    takes_dir = Path(shoot["project"]).parent / "takes"
    (work / "takes").mkdir(parents=True, exist_ok=True)
    opts = voice_options(proj)
    engine = (opts["clean"] or opts["fix"]) and _engine_ready(progress)
    clean = _clean_takes(proj, takes_dir, work, progress) if engine and opts["clean"] else {}
    heard_again = _hear_takes(proj, clean, takes_dir, progress) if engine and opts["fix"] else {}
    by_line: dict[int, tuple[dict, dict, int]] = {}  # line k -> (shot, its take, row in the take)
    for s in proj["shots"]:
        take = s.get("take") or {}
        if take.get("status") != "ready":
            continue
        if s["n"] in heard_again:  # the best of three hearings of the cleaned take: its cuts and words
            take = {**take, "lines": heard_again[s["n"]]["rows"], "heard": heard_again[s["n"]]["heard"]}
        for j, k in enumerate(s["lines"]):
            by_line[k] = (s, take, j)
    progress(f"Cutting your {len(proj['shots'])} takes into {len(proj['lines'])} lines")
    audios: dict[int, SceneAudio] = {}
    camera: dict[int, dict] = {}
    zoom_for: dict[int, float] = {}
    for k, row in enumerate(proj["lines"]):
        if k not in by_line:
            raise RuntimeError(f"Shot with line {k + 1} has no take: upload it on the Shoot tab")
        s, take, j = by_line[k]
        r = take["lines"][j]
        src = clean.get(s["n"]) or takes_dir / f"shot{s['n']:02d}.wav"
        dst = work / "audio" / "takes" / f"line{k:03d}.wav"
        _cut(src, dst, r["start"], r["end"])
        heard = [Word(t, a, b) for t, a, b in (take.get("heard") or [])]
        words = caption_words(row["text"], heard, r, r["start"]) if heard else _even(row["text"], r["end"] - r["start"])
        audios[k] = SceneAudio(dst, words)
        if row.get("camera"):
            proxy = work / "takes" / f"shot{s['n']:02d}.mp4"
            if not proxy.exists():
                try:
                    os.link(takes_dir / proxy.name, proxy)
                except OSError:
                    shutil.copy(takes_dir / proxy.name, proxy)
            if s["n"] not in zoom_for:
                zoom_for[s["n"]] = PUNCH if len(zoom_for) % 2 else 1.0
            camera[k] = {"type": "camera", "src": f"takes/{proxy.name}", "from": r["start"],
                         "until": round(r["end"] - r["start"], 3), "zoom": zoom_for[s["n"]], "headline": "", "sub": "",
                         "items": [], "icons": [], "camera": "still"}
    fixed = _fix_words(proj, audios, clean, heard_again, takes_dir, work, progress) if heard_again else {}
    for k in fixed:
        if camera.pop(k, None):  # your lips no longer match the line: its B-roll instead
            progress(f"Line {k + 1} shows B-roll now (a word in it was rebuilt in your voice)")
    (work / "your-voice.json").write_text(json.dumps({
        "cleaned": sorted(clean), "fixed": [{"line": k + 1, **{x: r[x] for x in ("fixed", "failed")}} for k, r in fixed.items()],
    }, ensure_ascii=False), encoding="utf-8")
    gain = level_voice([a.path for a in audios.values()])
    if gain:
        progress(f"Your voice levelled by {gain:+.1f} dB")
    hook_rows = [k for k, r in enumerate(proj["lines"]) if r["part"] == "hook"]
    script_rows = [k for k, r in enumerate(proj["lines"]) if r["part"] == "script"]
    voices, overrides, n = [], {}, 0
    for ci, chapter in enumerate(script.chapters):
        row = []
        for bi, _ in enumerate(chapter.beats):
            k = script_rows[n]
            row.append(audios[k])
            if k in camera:
                overrides[(ci, bi)] = camera[k]
            n += 1
        voices.append(row)
    hook_voices, h = [], 0
    for i, shot in enumerate(script.hook):
        if shot.line.strip():
            k = hook_rows[h]
            hook_voices.append(audios[k])
            if k in camera:
                overrides[("hook", i)] = camera[k]
            h += 1
        else:
            hook_voices.append(None)
    return voices, hook_voices, overrides


# ---------- your voice: cleaned, and missing words rebuilt (voice_engine.py, wordfix.py) ----------

STUDIO = ("highpass=f=85,equalizer=f=200:t=q:w=1.0:g=-3,equalizer=f=4000:t=q:w=0.9:g=4,highshelf=f=8000:g=3,"
          "acompressor=threshold=-22dB:ratio=2.5:attack=10:release=150:makeup=3")  # less boom, clearer, steadier
VOICE_WAIT = 600  # seconds to wait for the graphics card before the video goes on with the takes as recorded
FIX_MIN_MATCH = 0.5  # a line with fewer of its words heard is a bad transcript or a different line: never 'fixed'
FIX_MAX_WORDS, FIX_MAX_SECONDS = 8, 3.0  # longer gaps are a missing sentence: that needs a new take, not a patch
PLAUSIBLE = 0.25  # a hearing matching this much less of the script than the best one is broken and doesn't vote
GOOD_HEARING = 0.9  # a take's first hearing matching less than this is heard the other ways too, and the best kept


def voice_options(proj: dict) -> dict:
    """The shoot's voice settings (both on unless switched off on the Shoot tab)."""
    return {"clean": True, "fix": True, **(proj.get("voice") or {})}


def _engine_ready(progress: Progress) -> bool:
    from . import voice_engine

    if voice_engine.installed():
        return True
    progress("Your voice: the voice engine isn't installed (Shoot tab), so the takes are used as recorded")
    return False


def _clean_takes(proj: dict, takes_dir: Path, work: Path, progress: Progress) -> dict[int, Path]:
    """Each take's sound with noise, hum and room taken out (ClearerVoice, timing kept to the sample, so your lips stay
    in sync) and a studio tone (`STUDIO`); kept next to the take (shotNN-voice.wav) for the next edit."""
    from . import stopper, voice_engine

    out, jobs = {}, []
    for s in proj["shots"]:
        take = s.get("take") or {}
        if take.get("status") != "ready":
            continue
        n = s["n"]
        voiced = takes_dir / f"shot{n:02d}-voice.wav"
        if voiced.exists():
            out[n] = voiced
            continue
        hq = takes_dir / f"shot{n:02d}-48k.wav"
        if not hq.exists():
            subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(takes_dir / take["file"]), "-vn", "-ac", "1",
                            "-ar", "48000", str(hq)], check=True)
        jobs.append({"n": n, "src": str(hq), "out": str(takes_dir / f"shot{n:02d}-clean.wav")})
    if jobs:
        progress(f"Your voice: cleaning {len(jobs)} take(s) (noise, hum and room taken out; timing kept)")
        try:
            voice_engine.run("clean", {"items": jobs}, work, progress, "Your voice", wait=VOICE_WAIT)
        except stopper.Paused:
            raise
        except Exception as exc:  # noqa: BLE001 - the video goes on with the takes as recorded
            progress(f"Your voice: cleaning skipped ({exc}); the takes are used as recorded")
            return out
        for j in jobs:
            voiced = takes_dir / f"shot{j['n']:02d}-voice.wav"
            if Path(j["out"]).exists():
                subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", j["out"], "-af", STUDIO, "-ar", "48000",
                                str(voiced)], check=True)
                out[j["n"]] = voiced
    return out


def _hear_takes(proj: dict, clean: dict[int, Path], takes_dir: Path, progress: Progress) -> dict[int, dict]:
    """Each take heard again, three ways (`wordfix.DECODES`), from its cleaned sound: the transcript that matches the
    script best gives the line cuts, and all three vote on which words are missing (`_fix_words`). Deciding from
    line-sized pieces went wrong: a line cut placed late made 'kya future mein', said clearly, look missing."""
    from .wordfix import DECODES

    progress("Your voice: listening to each take again to find words that are really missing")
    out = {}
    for s in proj["shots"]:
        take = s.get("take") or {}
        if take.get("status") != "ready" or not take.get("heard"):
            continue
        audio = clean.get(s["n"]) or takes_dir / f"shot{s['n']:02d}.wav"
        lines = [proj["lines"][k]["text"] for k in s["lines"]]
        length = media_seconds(audio)
        tries = []
        for opt in DECODES:
            heard = _hear(proj["language"], audio, **opt) or []
            if heard:
                rows, _, matched = _judge(lines, heard, length)
                tries.append((matched, heard, rows, matches(lines, heard)[1]))
        if not tries:
            continue
        matched, heard, rows, _ = max(tries, key=lambda t: t[0])
        # a hearing that got much less of the script than the best is broken (with silence-skipping off one heard only
        # the take's last line): it gets no vote
        out[s["n"]] = {"heard": [[w.text, w.start, w.end] for w in heard], "rows": rows, "matched": matched,
                       "votes": [set(t[3]) for t in tries if t[0] >= matched - PLAUSIBLE]}
    return out


def _fix_words(proj: dict, audios: dict, clean: dict, heard_again: dict, takes_dir: Path, work: Path,
               progress: Progress) -> dict[int, dict]:
    """Words you skipped or said wrong, rebuilt in your voice in each line's audio (`wordfix.repair`); `audios` is
    updated in place. A word is missing only when most of the take's three hearings miss it. Returns the repaired
    lines {line k: result}."""
    from . import stopper, wordfix

    wanted: dict[int, list[dict]] = {}
    refs = []
    for s in proj["shots"]:
        view = heard_again.get(s["n"])
        if not view:
            continue
        heard = [Word(t, a, b) for t, a, b in view["heard"]]
        refs.append((clean.get(s["n"]) or takes_dir / f"shot{s['n']:02d}.wav", heard))
        lines = [proj["lines"][k]["text"] for k in s["lines"]]
        tokens = _script_tokens(lines)
        for g in wordfix.gaps(lines, heard):
            span = [t for t, tok in enumerate(tokens) if tok[0] == g["line"]
                    and g["first_word"] <= tok[1] < g["first_word"] + len(g["words"])]
            if wordfix.heard_by(view["votes"], span) > len(view["votes"]) // 2:
                continue  # most hearings heard it: said, just misheard once
            row = view["rows"][g["line"]]
            if ((row.get("matched") or 0) < FIX_MIN_MATCH or len(g["words"]) > FIX_MAX_WORDS
                    or g["at"][1] - g["at"][0] > FIX_MAX_SECONDS):
                progress(f"Your voice: '{g['text']}' can't be patched in (too much of the line is missing): film it again")
                continue
            wanted.setdefault(s["lines"][g["line"]], []).append(
                dict(g, at=[round(max(0.0, g["at"][0] - row["start"]), 3), round(max(0.0, g["at"][1] - row["start"]), 3)]))
    if not wanted:
        progress("Your voice: every word of the script is in your takes")
        return {}
    keys = sorted(wanted)
    items = [{"wav": str(audios[k].path), "text": proj["lines"][k]["text"], "gaps": wanted[k],
              "out": str(work / "audio" / "takes" / f"line{k:03d}-fixed.wav")} for k in keys]
    words = ", ".join(f"'{g['text']}'" for k in keys for g in wanted[k])
    progress(f"Your voice: rebuilding {words} in your own voice")
    try:
        ref = wordfix.reference(refs, work / "audio" / "takes" / "your-voice-ref.wav")
        results = wordfix.repair(items, ref, proj["language"], work / "voice-fix", progress)
    except stopper.Paused:
        raise
    except Exception as exc:  # noqa: BLE001 - the video goes on with the takes as recorded
        log.exception("Rebuilding words failed")
        progress(f"Your voice: couldn't rebuild the words ({exc}); the takes are used as recorded")
        return {}
    done = {}
    for k, it, r in zip(keys, items, results):
        if r["ok"]:
            audios[k] = SceneAudio(Path(it["out"]), wordfix.shift_words(audios[k].words, r["changes"]))
            done[k] = r
        if r["failed"]:
            progress(f"Your voice: couldn't rebuild {', '.join(repr(w) for w in r['failed'])} in line {k + 1}; it stays as recorded")
    if done:
        progress(f"Your voice: rebuilt {sum(len(r['fixed']) for r in done.values())} word(s) in {len(done)} line(s)")
    return done


def _even(text: str, seconds: float) -> list[Word]:
    toks = text.split()
    step = seconds / max(1, len(toks))
    return [Word(t, round(i * step, 3), round((i + 1) * step - 0.02, 3)) for i, t in enumerate(toks)]


def run_shoot(cfg: Config, pid: str, progress: Progress = log.info) -> dict:
    """The finished video from a Shoot project: planned if it wasn't, then the long pipeline from 'scripted' on."""
    from dataclasses import replace

    from .longform import WORDS_PER_SECOND, _long_loop
    from .pipeline import CHECKPOINT
    from .scriptvideo import assemble, spoken_text
    from .trends import Trend

    proj = load(cfg, pid)
    if missing_takes(proj):
        raise RuntimeError(f"Shot(s) {', '.join(map(str, missing_takes(proj)))} have no ready take yet")
    if proj["plan"]["status"] != "done":
        progress("Claude is planning the video: which lines show you and which show B-roll")
        proj = plan(cfg, pid)
    hook, lines, marked = _parts(proj)
    board = ShootBoard.model_validate(proj["plan"]["board"])
    script = assemble(_given(proj), board, hook, lines, marked)
    assert spoken_text(script) == " ".join(lines)  # not one spoken word changed
    seconds = sum((s["take"].get("duration") or 0) for s in proj["shots"])
    minutes = max(0.5, seconds / 60) if seconds else sum(len(x.split()) for x in lines) / WORDS_PER_SECOND / 60
    on = sum(1 for r in proj["lines"] if r.get("camera"))
    progress(f"Your shoot: {len(proj['shots'])} takes, {len(proj['lines'])} lines ({on} on camera), "
             f"about {minutes:.1f} min")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    work = cfg.output_dir / f"{stamp}-{uuid.uuid4().hex[:4]}-shoot-working"
    work.mkdir(parents=True, exist_ok=True)
    progress(f"Saving progress in {work.name}")
    manual = {"title": proj["title"], "description": proj["description"], "hook": proj["hook"], "script": proj["script"],
              "screen_text": proj["screen_text"], "vertical": proj["format"] == "short",
              "shoot": {"id": pid, "project": str(folder(cfg, pid) / "project.json")}}
    state = {"length": "long", "minutes": minutes, "topic": proj["title"], "stamp": stamp, "style": cfg.video_style,
             "candidates": [{"title": proj["title"], "source": "your shoot"}], "attempt": 1, "stage": "scripted",
             "script": script.model_dump(), "manual": manual}
    (work / CHECKPOINT).write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    update(cfg, pid, lambda p: p.update(video={"status": "making", "folder": work.name}))
    try:
        report = _long_loop(replace(cfg, long_minutes=minutes), work, [Trend(title=proj["title"], source="your shoot")],
                            proj["title"], stamp, progress, resume=state)
    except Exception:
        update(cfg, pid, lambda p: p.update(video={"status": "stopped", "folder": work.name}))
        raise
    update(cfg, pid, lambda p: p.update(video={"status": "done", "id": report["id"]}))
    return report


def run_shoot_job(cfg: Config, pid: str, progress: Progress) -> list[dict]:
    """The app's job: one Shoot video in the shared video slot, with token metering and pause."""
    from .llm import set_limit_reporter, start_meter, usage_line
    from .pipeline import Paused, _video_slot, done_line, set_pause_check

    should_pause = getattr(progress, "should_pause", None)
    with _video_slot(cfg):
        set_pause_check(should_pause)
        set_limit_reporter(progress)
        start_meter(lambda r: progress(usage_line(r)))
        progress("=== Video 1/1 ===")
        try:
            report = run_shoot(cfg, pid, progress)
            progress(done_line(report))
            return [report]
        except Paused:
            progress("Paused: progress saved. Press Resume to carry on from here.")
        except Exception as exc:
            log.exception("Shoot video failed")
            progress(f"Video 1 failed: {exc}")
    return []
