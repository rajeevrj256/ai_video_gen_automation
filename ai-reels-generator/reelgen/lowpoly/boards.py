"""✍ Read the storyboard first: the Low-poly tab's per-build option (never a setting). The user: "i write, they generate
storyboards, i will read and approve, then it goes to build; if rejected regenerate some other storyboard with same
prompt, but i have option to accept a rejected script as well again; at first generate 2-3 different storyboards with
the same prompt; this only works if i open the enhancer at the time of building a video, not at settings".

A set (<output>/lowpoly-boards/<id>/set.json) is one prompt, the request it was made with, the Claude picks, and its
drafts (draft-<n>.json). A round (`write_round`, the job `lowpoly_boards`): one call proposes N clearly different takes
on the prompt (story.pitches, told every draft written for it before and why the user turned one down), then each
take is written as a whole storyboard, all at once in their own threads (story.write with its take; a film over
LONG_FROM minutes as its act-by-act outline, story.plan_outline, since writing every act of three 13-minute films
to read one would cost three films). The tab shows each draft shot by shot (`view`). Approving one (`prepare_build`)
makes an unfinished low-poly video from it that the job carries on like a resume: its story is never written again
(a long film's acts are written from the approved outline and take). Rejecting the last open draft writes a new round
(the server starts it); a rejected draft can still be approved. Approved is final (approve another draft for a second
video)."""
from __future__ import annotations

import json
import logging
import re
import shutil
import threading
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from ..config import Config
from . import story as S
from .timeline import LEAD, SILENT, STAMP, TAIL

log = logging.getLogger(__name__)
DIR = "lowpoly-boards"
COUNTS = (2, 3)  # storyboards to choose from in a round
WPS = 2.7  # words a second, for the estimate the tab shows (the narrator reads ~2.65, dialogue a little faster)
_lock = threading.Lock()


def _root(cfg: Config) -> Path:
    return Path(cfg.output_dir) / DIR


def _folder(cfg: Config, sid: str) -> Path:
    if not re.fullmatch(r"[0-9A-Za-z-]{6,60}", sid or ""):
        raise KeyError(sid)
    return _root(cfg) / sid


def load(cfg: Config, sid: str) -> dict:
    path = _folder(cfg, sid) / "set.json"
    if not path.exists():
        raise KeyError(sid)
    return json.loads(path.read_text(encoding="utf-8"))


def _save(cfg: Config, s: dict) -> None:
    path = _folder(cfg, s["id"]) / "set.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def _update(cfg: Config, sid: str, change) -> dict:
    with _lock:
        s = load(cfg, sid)
        change(s)
        _save(cfg, s)
        return s


def is_long(req: dict) -> bool:
    return req.get("format") == "film" and float(req.get("minutes", 3.5)) > S.LONG_FROM


def new_set(cfg: Config, request: dict, count: int, ai: dict | None = None) -> dict:
    """A set for one prompt (`request` = the LowPolyRequest the video will be built with)."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    s = {"id": f"{stamp}-{uuid.uuid4().hex[:4]}", "created": time.time(), "request": request, "ai": ai or None,
         "count": count if count in COUNTS else COUNTS[-1], "rounds": 0, "drafts": []}
    _folder(cfg, s["id"]).mkdir(parents=True, exist_ok=True)
    with _lock:
        _save(cfg, s)
    return s


def estimate(story: S.Story) -> float:
    """About how long it runs, before any voice is recorded (timeline.build's own shot lengths, words at WPS)."""
    total = 0.0
    for s in story.shots:
        words = len(s.line.split())
        total += ((STAMP if s.stamp.strip() else LEAD) + words / WPS + TAIL if words else SILENT) + s.pause
    return round(total, 1)


def _others(s: dict) -> str:
    """Every storyboard written for this prompt so far, for the next round's takes to differ from."""
    out = []
    for d in s["drafts"]:
        if not d.get("title"):
            continue
        why = d.get("note", "").strip()
        tag = (f" [the user turned it down{': ' + why if why else ''}]" if d["state"] == "rejected"
               else " [the user chose it]" if d["state"] == "approved" else "")
        out.append(f"- {d['title']}: {d.get('problem') or d.get('take', '')}{tag}")
    return "\n".join(out)


def write_round(cfg: Config, sid: str, count: int, progress) -> int:
    """The job: `count` new takes on the set's prompt, each written as a storyboard in its own thread. Returns how many
    were written; raises when none could be."""
    from ..llm import set_limit_reporter, start_meter, usage_line
    from ..pipeline import Paused, set_pause_check

    s = load(cfg, sid)
    req = s["request"]
    fiction = req.get("kind") == "fiction"
    short = req.get("format") != "film"
    seconds = max(20, min(60, int(req.get("seconds", 35))))
    minutes = max(2.5, min(15.0, float(req.get("minutes", 3.5))))
    long = is_long(req)
    topic = (req.get("topic") or "").strip()
    should_pause = getattr(progress, "should_pause", None)
    set_pause_check(should_pause)
    set_limit_reporter(progress)
    start_meter(lambda r: progress(usage_line(r)))
    count = max(1, min(COUNTS[-1], int(count)))
    progress(f"Claude is thinking up {count} different takes on your prompt"
             + (" (to read as act-by-act outlines: a film this long is written act by act once you approve one)" if long else ""))
    takes = S.pitches(cfg, topic, kind="fiction" if fiction else "life", short=short, seconds=seconds, minutes=minutes,
                      n=count, others=_others(s))
    if not takes:
        raise RuntimeError("Claude proposed no takes on the prompt")

    numbers: list[int] = []

    def add(s2: dict) -> None:
        s2["rounds"] = int(s2.get("rounds", 0)) + 1
        for t in takes:
            n = max([d["n"] for d in s2["drafts"]] + [0]) + 1
            numbers.append(n)
            s2["drafts"].append({"n": n, "round": s2["rounds"], "state": "writing", "title": t.title.strip(), "take": t.take.strip(),
                                 "differs": t.differs.strip(), "problem": "", "long": long, "started": time.time()})
    _update(cfg, sid, add)
    progress(f"{len(takes)} takes: " + "; ".join(f"'{t.title.strip()}'" for t in takes) + ". Writing each one as a storyboard")
    folder = _folder(cfg, sid)

    def one(i: int, n: int, take: S.Pitch) -> None:
        vp = (lambda m, k=i + 1: progress(f"[V{k}] {m}")) if len(takes) > 1 else progress
        set_pause_check(should_pause)
        set_limit_reporter(vp)
        start_meter(lambda r: vp(usage_line(r)))
        vp(f"Claude is writing the storyboard {n}: '{take.title.strip()}'")
        text = f"{take.title.strip()}: {take.take.strip()}"
        try:
            if long:
                ask_for, made, _ = S._asking(cfg, topic, fiction, text)
                outline = S.plan_outline(cfg, ask_for, made, minutes=minutes, fiction=fiction, progress=vp)
                data = {"outline": outline.model_dump(), "acts": [], "take": text}
                info = {"title": outline.title.strip(), "problem": outline.problem.strip(), "acts": len(outline.acts),
                        "seconds": round(sum(a.minutes for a in outline.acts) * 60), "cast": [c.name for c in outline.cast]}
            else:
                story = S.write(cfg, topic, short=short, seconds=seconds, minutes=minutes, progress=vp,
                                kind="fiction" if fiction else "life", take=text)
                data = story.model_dump()
                info = {"title": story.title.strip(), "problem": story.problem.strip(), "shots": len(story.shots),
                        "seconds": estimate(story), "cast": [c.name for c in story.cast]}
            (folder / f"draft-{n}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            _update(cfg, sid, lambda s2: _set(s2, n, state="ready", ready=time.time(), **info))
            vp(f"Done: storyboard {n} is ready to read: '{info['title']}'")
        except Paused:
            _update(cfg, sid, lambda s2: _set(s2, n, state="failed", error="stopped before it was finished"))
            vp(f"Storyboard {n} failed: stopped before it was finished")
        except Exception as exc:  # noqa: BLE001 - one draft failing never loses the others
            log.exception("Storyboard %d failed", n)
            _update(cfg, sid, lambda s2: _set(s2, n, state="failed", error=str(exc)[:300]))
            vp(f"Storyboard {n} failed: {exc}")

    threads = [threading.Thread(target=one, args=(i, n, t), daemon=True) for i, (n, t) in enumerate(zip(numbers, takes))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    done = [d for d in load(cfg, sid)["drafts"] if d["n"] in numbers and d["state"] == "ready"]
    if not done:
        errors = [d.get("error", "") for d in load(cfg, sid)["drafts"] if d["n"] in numbers]
        raise RuntimeError(f"No storyboard could be written: {next((e for e in errors if e), 'unknown error')}")
    progress(f"{len(done)} storyboard{'s' if len(done) > 1 else ''} ready to read in the Low-poly tab")
    return len(done)


def _set(s: dict, n: int, **fields) -> None:
    for d in s["drafts"]:
        if d["n"] == n:
            d.update(fields)
            return
    raise KeyError(n)


def _draft(s: dict, n: int) -> dict:
    for d in s["drafts"]:
        if d["n"] == n:
            return d
    raise KeyError(n)


def listing(cfg: Config, busy: set[str], limit: int = 12) -> list[dict]:
    """The sets the tab shows, newest first. A draft still 'writing' while no job writes its set is one the app
    stopped in the middle of (closed, restarted): it is shown as failed."""
    out = []
    for path in sorted(_root(cfg).glob("*/set.json"), reverse=True)[:limit]:
        try:
            s = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        writing = s["id"] in busy
        for d in s["drafts"]:
            if d["state"] == "writing" and not writing:
                d["state"], d["error"] = "failed", "the app stopped while it was being written"
        req = s["request"]
        out.append({"id": s["id"], "created": s["created"], "count": s.get("count", 3), "writing": writing,
                    "kind": req.get("kind", "life"), "format": req.get("format", "short"), "seconds": req.get("seconds"),
                    "minutes": req.get("minutes"), "vertical": req.get("vertical", False), "topic": (req.get("topic") or "")[:400],
                    "long": is_long(req), "drafts": s["drafts"]})
    return out


def _place(name: str) -> str:
    return {"busstop": "bus stop", "living": "living room"}.get(name, name.replace("-", " "))


def _actor(a: S.LPActor) -> str:
    bits = [a.action.replace("-", " ")]
    if a.expression not in ("neutral", ""):
        bits.append(f"({a.expression})")
    if a.to:
        bits.append(f"→ {a.to}")
    if a.hold not in ("none", ""):
        bits.append(f"holding a {a.hold}")
    if a.look_at:
        bits.append(f"· looks at {a.look_at}")
    return f"{'him' if a.who == 'hero' else a.who}: {' '.join(bits)}"


def view(cfg: Config, sid: str, n: int) -> dict:
    """One draft, readable: what it is, who is in it, and every shot (place, light, camera, who does what, the line),
    or a long film's acts."""
    s = load(cfg, sid)
    d = _draft(s, n)
    path = _folder(cfg, sid) / f"draft-{n}.json"
    if d["state"] in ("writing", "failed") or not path.exists():
        return {**d, "shots": [], "acts": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if "outline" in data:
        o = S.Outline.model_validate(data["outline"])
        return {**d, "youtube_title": o.youtube_title, "description": o.description, "mood": o.mood,
                "cast": [{"name": c.name, "who": c.who, "voice": c.voice} for c in o.cast],
                "acts": [{"name": a.name, "minutes": a.minutes, "summary": a.summary, "places": [_place(p) for p in a.places],
                          "ends_with": a.ends_with, "mood": a.mood, "energy": a.energy} for a in o.acts], "shots": []}
    story = S.Story.model_validate(data)
    S.lock_cast(cfg, story, keep=False)  # people met before show with their saved names and voices
    shots = []
    for i, x in enumerate(story.shots, 1):
        shots.append({"n": i, "stamp": x.stamp, "place": _place(x.set), "light": x.light, "camera": x.camera.replace("-", " "),
                      "people": [_actor(a) for a in x.actors], "line": x.line, "speaker": x.speaker, "red": x.red,
                      "pause": x.pause, "slowmo": x.slowmo, "things": [t.kind + (f" '{t.label}'" if t.label else "") for t in x.things],
                      "big": [f"{b.kind} {b.motion}" for b in x.big], "fx": [f.kind for f in x.fx]})
    return {**d, "youtube_title": story.youtube_title, "description": story.description, "mood": story.mood,
            "cast": [{"name": c.name, "who": c.who, "voice": c.voice} for c in story.cast], "shots": shots, "acts": []}


def reject(cfg: Config, sid: str, n: int, note: str = "") -> bool:
    """Turn a draft down (with what was wrong, for the next round). True when no draft is left to read or being
    written and none was approved, so the server writes a new round with the same prompt (after an approval, more
    are written only when asked: 'Write more')."""
    def change(s: dict) -> None:
        d = _draft(s, n)
        if d["state"] == "approved":
            raise ValueError("That storyboard is already approved and building")
        d.update(state="rejected", note=note.strip()[:400], decided=time.time())
    s = _update(cfg, sid, change)
    return not any(d["state"] in ("ready", "writing", "approved") for d in s["drafts"])


def prepare_build(cfg: Config, sid: str, n: int) -> tuple[str, dict]:
    """Approve a draft (an open one or one turned down before): an unfinished low-poly video made from it, carried on
    by `run_lowpoly` like a resumed one. Returns its folder's name and the request it is built with."""
    from .run import CHECKPOINT, LowPolyRequest

    s = load(cfg, sid)
    d = _draft(s, n)
    if d["state"] == "approved":
        raise ValueError("That storyboard is already approved and building")
    if d["state"] not in ("ready", "rejected"):
        raise ValueError("That storyboard isn't written yet")
    data = json.loads((_folder(cfg, sid) / f"draft-{n}.json").read_text(encoding="utf-8"))
    req = asdict(LowPolyRequest(**{k: v for k, v in s["request"].items() if k in LowPolyRequest.__dataclass_fields__}))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    work = Path(cfg.output_dir) / f"{stamp}-{uuid.uuid4().hex[:4]}-lowpoly-working"
    work.mkdir(parents=True)
    board = {"set": sid, "draft": n, "title": d.get("title", ""), "take": d.get("take", ""), "drafts": len(s["drafts"])}
    state = {"stage": "", "stamp": stamp, "request": req, "board": board}
    try:
        if "outline" in data:  # a long film: its acts are written from this outline and take when the job starts
            (work / "story-parts.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        else:
            story = S.Story.model_validate(data)
            S.lock_cast(cfg, story)  # now its new people join the recurring cast
            S.save(story, work / "story.json")
            S.remember(cfg, story)
            state["stage"] = "written"
        (work / CHECKPOINT).write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        raise
    _update(cfg, sid, lambda s2: _set(s2, n, state="approved", work=work.name, decided=time.time()))
    return work.name, req


def built(cfg: Config, sid: str, n: int, job_id: str) -> None:
    _update(cfg, sid, lambda s2: _set(s2, n, job=job_id))


def remove(cfg: Config, sid: str) -> None:
    shutil.rmtree(_folder(cfg, sid), ignore_errors=True)
