"""Never make the same video twice, in any pipeline (Shorts, medium/long, Script Video, Stick).

What counts as "made": every video in the library (its report: title, subject, topic, premise) plus
every subject claimed by a video still being made (`<output>/subjects.json`, written as soon as a
script exists, so two videos running at once never pick the same one, and one that fails later
still counts for a while).

How it is used:
- `prompt_block` goes into every writer's prompt: the subjects already made, "never again".
- A broad topic you type ("the origin story of an everyday technology") is first narrowed to one
  subject by a small call (`choose_subject`) that sees the same list and is checked in code, before
  the expensive research-and-write call (a long script alone was 1.2M tokens; a repeated long video
  cost 5 hours of rendering).
- `too_close` checks the finished script's subject and title against the list (same subject, or most
  of the same words); the pipeline then writes once more with the reason, and stops the video if it
  still repeats, before voice, footage or the render.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from .config import Config

log = logging.getLogger(__name__)

_lock = threading.Lock()
_mine = threading.local()  # the subject this video's thread narrowed to and claimed
CLAIMS = "subjects.json"
# Every format counts against every other: a Short on a subject means no medium or long video on it either
# (a medium video on the barcode repeated a barcode Short). Stick videos keep their own list.
EVERY = ("short", "long")
STOP = set("a an the and or but of to in on at for with by from is are was were be been his her their your my our "
           "it its this that these those when what who how why he she they you i we me him them not no just so then "
           "than into out up about over after before again behind story origin history secret real truth really "
           "actually nobody everyone everybody video".split())


def _words(text: str) -> set[str]:
    return {w[:-1] if w.endswith("s") and len(w) > 4 else w
            for w in re.findall(r"[a-z0-9']+", (text or "").lower()) if w not in STOP and len(w) > 2}


def made(cfg: Config) -> list[dict]:
    """Every video made or being made: {title, subject, topic, premise, when, kind}, oldest first."""
    out: dict[str, dict] = {}
    root = cfg.output_dir
    for path in sorted(root.glob("*/report.json")) if root.exists() else []:
        try:
            r = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        subject = r.get("subject") or ""
        if not subject and (path.parent / "script.json").exists():  # older Shorts kept it only in the script
            try:
                subject = json.loads((path.parent / "script.json").read_text(encoding="utf-8")).get("subject") or ""
            except (OSError, json.JSONDecodeError):
                pass
        entry = {"title": r.get("youtube_title") or r.get("title") or r.get("topic") or "",
                 "subject": subject, "topic": r.get("topic") or "",
                 "premise": r.get("why_chosen") or "", "when": str(r.get("created_at", ""))[:8],
                 "kind": _kind(r)}
        out[path.parent.name] = entry
    try:
        claims = json.loads((root / CLAIMS).read_text(encoding="utf-8")) if (root / CLAIMS).exists() else []
    except (OSError, json.JSONDecodeError):
        claims = []
    for c in claims:
        out.setdefault("claim:" + c.get("subject", "") + c.get("title", ""), c)
    return sorted(out.values(), key=lambda e: e.get("when", ""))


def _kind(report: dict) -> str:
    if report.get("source") == "stick":
        return "stick"
    return "long" if report.get("format") == "long" else "short"


def claim(cfg: Config, entry: dict) -> None:
    """Remember a subject as soon as its script exists (kept 400 deep)."""
    entry = {**entry, "when": entry.get("when") or datetime.now().strftime("%Y%m%d")}
    with _lock:
        path = cfg.output_dir / CLAIMS
        try:
            claims = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        except (OSError, json.JSONDecodeError):
            claims = []
        claims.append(entry)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(claims[-400:], ensure_ascii=False, indent=0), encoding="utf-8")


def _core(subject: str) -> set[str]:
    """What a video is about, without the angle: the subject's first phrase. 'The barcode: why a 1949 idea
    waited 25 years' and 'The barcode and its first supermarket scan' are both {'barcode'}."""
    head = re.split(r":|,|;|\(| - | — | – |\band\b|\bwhy\b|\bhow\b|\bthat\b|\bwhich\b|\bwho\b|\bwhen\b",
                    (subject or "").lower(), maxsplit=1)[0]
    return _words(head.replace("'s ", " "))


def too_close(subject: str, title: str, past: list[dict]) -> dict | None:
    """The earlier video this one repeats: the same subject, or most of the same words in the subject
    and title (so a new title on the same subject is caught; 'QR code' vs 'Why nobody pays for the QR
    code' share 'qr' and 'code')."""
    mine_subject, mine = _words(subject), _words(subject + " " + title)
    for p in reversed(past):
        theirs_subject = _words(p.get("subject", ""))
        theirs = _words(" ".join([p.get("subject", ""), p.get("title", "")]))
        if mine_subject and theirs_subject and (mine_subject <= theirs or theirs_subject <= mine):
            return p  # one subject is wholly inside the other video's subject and title
        core, their_core = _core(subject), _core(p.get("subject", ""))
        if (core and core <= theirs) or (their_core and their_core <= mine):
            return p  # the same thing, told from another angle (the barcode, twice)
        if mine and theirs and len(mine & theirs) / len(mine | theirs) >= 0.4:
            return p
    return None


def prompt_block(cfg: Config, kinds: tuple[str, ...] = ("short", "long"), limit: int = 80) -> str:
    """For a writer's prompt: what was already made (newest first)."""
    past = [p for p in made(cfg) if p.get("kind", "short") in kinds][-limit:]
    if not past:
        return ""
    lines = "\n".join(f"- {p.get('subject') or p.get('topic')}: \"{p.get('title')}\"" for p in reversed(past))
    return ("\n\nAlready made on this channel. Never make one of these again, not under another title, angle or "
            "framing; pick a different subject:\n" + lines)


class Subject(BaseModel):
    subject: str = Field(description="One specific subject (a thing, event, person-free story or place) the video will be about, e.g. 'the barcode'.")
    angle: str = Field(description="One sentence: the story you would tell about it.")


class Subjects(BaseModel):
    options: list[Subject] = Field(description="8 different subjects that fit the topic, none already made, from different areas.")


def choose_subject(cfg: Config, topic: str, kinds: tuple[str, ...], tries: int = 3) -> Subject | None:
    """Narrow a broad topic to one subject not made before (a small call, no web search). Claude lists
    8 options, the code drops every one that repeats a video already made and picks one of the rest at
    random: asked for one, Claude gave the same famous example (the barcode) every time the same topic
    was typed, in Shorts, medium and long videos alike."""
    import random

    from .llm import ask

    past = [p for p in made(cfg) if p.get("kind", "short") in kinds]
    note, tried = "", []
    for _ in range(tries):
        picks = ask(cfg.ai_backend, cfg.claude_model,
                    "You plan videos for a channel. Turn the user's topic into 8 specific subjects for a video, each "
                    "from a different area. If the topic already names one subject, give only that one. Never list a "
                    "subject the channel already made. Skip the first examples everyone thinks of; mix well-known "
                    "and less-told ones.",
                    f"Topic: {topic}{prompt_block(cfg, kinds)}{note}", Subjects, allow_web=False, effort="low",
                    timeout=300)
        fresh = []
        for pick in picks.options:
            twin = too_close(pick.subject, pick.angle, past)
            if twin:
                tried.append(f"'{pick.subject}' (already made as \"{twin.get('title')}\")")
                log.info("Subject %s repeats %s", pick.subject, twin.get("title"))
            elif not any(too_close(pick.subject, pick.angle, [{"subject": f.subject, "title": f.angle}]) for f in fresh):
                fresh.append(pick)
        if fresh:
            return random.choice(fresh)
        note = "\n\nThese were already made, so pick others that fit the topic: " + "; ".join(tried[-16:])
    return None


def narrow(cfg: Config, topic: str, kinds: tuple[str, ...], progress=log.info) -> str:
    """A topic you typed, as 'Subject: X. Angle' for the writer: one subject this channel hasn't made.
    Raises when every try repeats an earlier video (nothing else has been spent yet)."""
    progress("Choosing a subject that hasn't been made before")
    pick = choose_subject(cfg, topic, kinds)
    if pick is None:
        raise RuntimeError(f"Every subject Claude found for \"{topic}\" was already made. Give a more specific or "
                           "different topic.")
    progress(f"Subject: {pick.subject}")
    # Claimed now, not after the script: a Short and a long video started on the same topic at the same
    # time must not both pick it.
    _mine.subject = pick.subject  # this video's own claim: guard must not call its script a repeat of it
    claim(cfg, {"title": pick.angle, "subject": pick.subject, "topic": topic, "kind": "short", "narrowed": True})
    return f"Subject: {pick.subject}. {pick.angle}"


def guard(cfg: Config, script, kinds: tuple[str, ...], rewrite, progress=log.info, kind: str = "short"):
    """Check a freshly written script against everything made; write it once more with the reason if
    it repeats one, and stop the video if it still does (before voice, footage and the render).
    `rewrite(reason)` returns a new script. The accepted subject is claimed at once."""
    own = getattr(_mine, "subject", None)
    _mine.subject = None
    past = [p for p in made(cfg) if p.get("kind", "short") in kinds
            and not (own and p.get("narrowed") and p.get("subject") == own)]
    title = getattr(script, "youtube_title", "") or getattr(script, "title", "")
    twin = too_close(script.subject, title, past)
    if twin:
        progress(f"This repeats \"{twin.get('title')}\" (made {twin.get('when', 'before')}); writing a different one")
        script = rewrite(f"This script repeats a video the channel already made: \"{twin.get('title')}\" (subject: "
                         f"{twin.get('subject') or twin.get('topic')}). Choose a different subject and write it again.")
        title = getattr(script, "youtube_title", "") or getattr(script, "title", "")
        twin = too_close(script.subject, title, past)
        if twin:
            raise RuntimeError(f"Stopped before recording: the script repeats \"{twin.get('title')}\" again. Pick another "
                               "topic.")
    claim(cfg, {"title": title, "subject": script.subject, "topic": getattr(script, "topic", ""),
                "premise": getattr(script, "why_chosen", ""), "kind": kind})
    return script
