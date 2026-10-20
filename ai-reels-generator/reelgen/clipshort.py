"""A YouTube Short made from part of a finished long, medium or Script video, ending on the full video.

The user: "make shorts on actual long scripted video by choosing script part ... take reference of long video so i
can upload on youtube and at end of short tell to know more visit this video", then "explaining the part of script
on shorts and linking with main video by the end".

On the video page (`✂️ Short from this video`) the user picks a run of the script's lines (`lines`) and how it is told:
- `explain` (default): Claude retells that part as a Short that stands on its own (`write_plan`: one call, no web,
  only the facts, numbers and names those lines state, `_new_numbers` checks it in code), each new line showing one of
  the chosen lines' own visuals (`visual_from`), so the Short looks like the video it points to;
- `exact`: the chosen lines word for word with their visuals (a Script Video's words stay the user's), with a hook
  line before them unless it's turned off.
Both start on a hook line over a keyword slide and end on an outro line ("the full story is in the video linked
below") over an end card (`endCard`: the long video's thumbnail with a play button, its title and length, an arrow
down to YouTube's related-video link; remotion/src/long/EndCard.tsx).

It is edited like a re-make (`build_long(remake=True)`): the same voice and pace, the video's own look, background
photo, footage, memes and AI music copied in under the Short's numbering (`_copy_files`), nothing drawn, searched or
generated; then rendered with the Long composition at 9:16 (`vertical`). The Short lands in the library as its own
video (`<stamp>-<slug>-short`, report `source: "clip"`, `from_video`), the original is never touched. Its description
links the full video when the user gave the link; the report's `related_video_tip` says how to set YouTube's own
related-video link on the Short.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Callable, Literal

from pydantic import BaseModel, Field

from .config import Config

log = logging.getLogger(__name__)
Progress = Callable[[str], None]

NOT_FOR = ("shoot", "stick", "anim", "toon", "storyshorts", "clip")  # not long-pipeline videos (a Shoot is your voice)
LENGTHS = (30, 45, 60, 90)  # seconds the user can ask an explained Short to run
MAX_SECONDS = 180  # YouTube's longest Short
TAIL = 0.6  # seconds the end card stays after the outro's last word


def why_not(folder: Path) -> str:
    """'' when a Short can be made from this video, else the reason."""
    try:
        report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "This video has no report."
    if report.get("format") != "long" or report.get("source") in NOT_FOR:
        return "Shorts can be made from long, medium and Script videos."
    if not (folder / "props.json").exists() or not (folder / "script.json").exists():
        return "This video's edit wasn't saved with it."
    return ""


def _load(folder: Path):
    from .longform import LongScript

    report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
    script = LongScript.model_validate_json((folder / "script.json").read_text(encoding="utf-8"))
    old = json.loads((folder / "props.json").read_text(encoding="utf-8"))
    flat = [(ci, bi, b) for ci, c in enumerate(script.chapters) for bi, b in enumerate(c.beats)]
    if len(flat) != len(old.get("beats") or []):
        raise ValueError("This video's saved edit doesn't match its script, so a Short can't be cut from it")
    return report, script, old, flat


def lines(folder: Path) -> dict:
    """The script's lines for the picker: each with its chapter, words and where it plays in the video."""
    reason = why_not(folder)
    if reason:
        return {"why_not": reason, "lines": []}
    report, script, old, flat = _load(folder)
    beats = old["beats"]
    words = sum(len(b.narration.split()) for _, _, b in flat)
    seconds = sum(float(b["duration"]) for b in beats) or 1.0
    return {"why_not": "", "title": report.get("title", ""), "source": report.get("source", ""),
            "wps": round(words / seconds, 3), "lengths": list(LENGTHS),
            "lines": [{"n": k, "chapter": ci, "chapter_title": script.chapters[ci].title, "text": b.narration,
                       "start": round(float(beats[k]["start"]), 2), "seconds": round(float(beats[k]["duration"]), 2)}
                      for k, (ci, _, b) in enumerate(flat)]}


class ClipLine(BaseModel):
    text: str = Field(description="One line the narrator says, 8-24 words.")
    visual_from: int = Field(description="The number of the chosen line whose visual this line shows: the one that "
                                         "pictures it best. Use each at most twice.")


class ClipPlan(BaseModel):
    hook: str = Field(description="The Short's first line, at most 12 words: the most surprising concrete thing in this "
                                  "part. Never a greeting, 'Did you know', 'In this video', 'Imagine' or a setup.")
    hook_keyword: str = Field(description="1-3 words of the hook, shown huge while it's said.")
    lines: list[ClipLine] = Field(default_factory=list, description="The Short's body (explain mode only; empty otherwise).")
    outro: str = Field(description="The last line, at most 16 words: leaves the bigger question open and says the full "
                                   "story is in the video linked below.")
    youtube_title: str = Field(description="The Short's YouTube title, at most 70 characters, the subject's search "
                                           "words first, no clickbait the Short doesn't deliver.")
    description: str = Field(description="1-2 sentences for the Short's description (no links: they are added).")
    hashtags: list[str] = Field(description="3 hashtags without '#', the first 'shorts'.")


_NUM = re.compile(r"\d+(?:[.,]\d+)*")


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in _NUM.findall(text)}


def _new_numbers(plan: ClipPlan, source: str) -> list[str]:
    """Numbers the Short says that the chosen lines don't: none is allowed (never a figure of our own)."""
    said = " ".join([plan.hook, plan.hook_keyword, plan.outro] + [x.text for x in plan.lines])
    return sorted(_numbers(said) - _numbers(source))


def write_plan(cfg: Config, script, chosen: list, mode: str, seconds: int, wps: float, title: str,
               progress: Progress = log.info) -> ClipPlan:
    """Claude's hook, outro, title and (explain) the retold lines, from the chosen lines only."""
    from .llm import ask

    numbered = "\n".join(f"{k} {b.narration}" for k, (_, _, b) in enumerate(chosen))
    source = " ".join(b.narration for _, _, b in chosen)
    budget = max(25, int(seconds * wps))
    if mode == "explain":
        body = (f"Retell the chosen lines below as a Short that a viewer who never saw the video understands on its "
                f"own: about {budget} words in all, hook and outro included ({seconds} seconds at this narrator's "
                f"pace). Explain, don't summarise: one idea per line, linked by 'but', 'so', 'that's why', a concrete "
                f"example where the lines give one. Use only the facts, numbers and names the chosen lines state; the "
                f"rest of the script is context for what a word means, never a source of new figures. Give every line "
                f"the chosen line whose visual fits it (visual_from).")
    else:
        body = "The chosen lines are spoken as they are; write only the hook, outro, title, description and hashtags."
    system = f"""You turn one part of a finished YouTube video into a YouTube Short that ends by sending viewers to \
the full video.
{body}
Write in the narrator's language and style exactly as the lines are written (Hinglish in Roman letters stays \
Hinglish in Roman letters, Indian English stays Indian English). The hook comes first and must work in the first \
second; the outro is the last line, invites the viewer to the full video below (YouTube shows it as a link under the \
Short) and promises nothing the full video doesn't have. No new facts anywhere, no number the chosen lines don't say."""
    story = "\n".join(f"{c.title}: " + " ".join(b.narration for b in c.beats) for c in script.chapters)
    prompt = (f"The full video: {title}\n\nThe chosen lines (numbered):\n{numbered}\n\n"
              f"The full script, for context only:\n{story}")
    progress("Claude is writing the Short" + (" (explaining the part)" if mode == "explain" else " (hook and outro)"))
    plan = ask(cfg.ai_backend, cfg.claude_model, system, prompt, ClipPlan, allow_web=False, effort="medium", timeout=600)
    extra = _new_numbers(plan, source)
    if extra:  # once more with the reason, then whatever is still wrong is dropped
        progress(f"The Short said {', '.join(extra)}, which the chosen lines don't: writing it again")
        plan = ask(cfg.ai_backend, cfg.claude_model, system,
                   prompt + f"\n\nYour last try used the numbers {', '.join(extra)}, which the chosen lines don't state. "
                            "Use none of them.", ClipPlan, allow_web=False, effort="medium", timeout=600)
    return plan


def _copy_files(folder: Path, work: Path, picks: list[int], chapter: int) -> None:
    """The video's own files the Short shows, under the Short's numbering: beat k of the Short shows line picks[k]'s
    footage clip or meme (None = a hook or outro slide), the chosen part's chapter becomes chapter 0 (its background
    photo and AI music). Copies, never links: the edit writes prepared files with these names."""
    def copy(src: Path, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)

    for k, g in enumerate(picks):
        if g is None:
            continue
        for sub in ("footage", "memes"):
            for f in (folder / sub).glob(f"beat{g:03d}.*") if (folder / sub).is_dir() else []:
                copy(f, work / sub / f"beat{k:03d}{f.suffix}")
    for f in (folder / "plates").glob(f"{chapter}.*") if (folder / "plates").is_dir() else []:
        copy(f, work / "plates" / f"0{f.suffix}")
    for f in (folder / "music").glob(f"ai-ch{chapter:02d}.*") if (folder / "music").is_dir() else []:
        copy(f, work / "music" / f.name.replace(f"ai-ch{chapter:02d}", "ai-ch00", 1))
    if (folder / "models").is_dir():
        shutil.copytree(folder / "models", work / "models", dirs_exist_ok=True)


def _end_thumb(folder: Path, work: Path, report: dict, at: float) -> str | None:
    """The full video's picture for the end card: its YouTube thumbnail when one was made, else a frame of it."""
    from .video import FFMPEG

    dest = work / "endcard.jpg"
    for name in ("thumbnail-youtube.jpg",):
        if (folder / name).exists():
            shutil.copy2(folder / name, dest)
            return dest.name
    if (folder / "reel.mp4").exists():
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", f"{max(0.0, at):.2f}", "-i", str(folder / "reel.mp4"),
                        "-frames:v", "1", "-q:v", "3", str(dest)], check=False)
    return dest.name if dest.exists() else None


def _clock(seconds: float) -> str:
    s = int(round(seconds))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def make(cfg: Config, folder: Path, first: int, last: int, mode: Literal["explain", "exact"] = "explain",
         seconds: int = 45, hook: bool = True, link: str = "", progress: Progress = log.info) -> dict:
    """The Short (see the module's notes): its report, the new video in the library."""
    from .longform import LBeat, LVisual
    from .longform import build_long
    from .pipeline import _render_slot, done_line, slugify
    from .rerender import _remake_look, _settings
    from .verify import probe
    from .video import _remotion_cli, _render_remotion

    reason = why_not(folder)
    if reason:
        raise ValueError(reason)
    report, script, old, flat = _load(folder)
    first, last = max(0, int(first)), min(len(flat) - 1, int(last))
    if first > last:
        raise ValueError("Pick the first and the last line of the part")
    chosen = flat[first:last + 1]
    span = sum(float(old["beats"][k]["duration"]) for k in range(first, last + 1))
    if mode == "exact" and span > MAX_SECONDS - 10:
        raise ValueError(f"Those lines run {span:.0f} s; a Short can be at most {MAX_SECONDS} s. Pick fewer lines.")
    seconds = seconds if seconds in LENGTHS else 45
    cfg, pace, _, _ = _settings(cfg, report, None, None, None)
    cfg, look = _remake_look(cfg, old)
    look = dict(look or {})
    chapter = chosen[0][0]
    words = sum(len(b.narration.split()) for _, _, b in flat)
    wps = words / max(1.0, sum(float(b["duration"]) for b in old["beats"]))
    title = report.get("title") or script.youtube_title
    plan = write_plan(cfg, script, chosen, mode, seconds, wps, title, progress)
    source = " ".join(b.narration for _, _, b in chosen)
    bad = set(_new_numbers(plan, source))
    issues: list[str] = []

    def clean(text: str) -> bool:
        return not (_numbers(text) & bad)

    beats, picks = [], []  # the Short's lines, and which chosen line's files each one shows (global index)
    if (hook or mode == "explain") and plan.hook.strip() and clean(plan.hook):
        kw = plan.hook_keyword.strip() if clean(plan.hook_keyword) else ""
        beats.append(LBeat(narration=plan.hook.strip(), visual=LVisual(
            type="keyword", headline=" ".join((kw or plan.hook).split()[:3]), sub="", items=[], icons=[], camera="push",
            impact=True)))
        picks.append(None)
    body = [x for x in plan.lines if x.text.strip()] if mode == "explain" else []
    if mode == "explain" and (not body or any(not clean(x.text) for x in body)):
        issues.append("Claude's retelling used a figure the chosen lines don't state; the lines are used as they are.")
        body = []
    if body:
        for x in body:
            k = min(max(0, x.visual_from), len(chosen) - 1)
            beats.append(LBeat(narration=x.text.strip(), visual=chosen[k][2].visual.model_copy(deep=True)))
            picks.append(first + k)
    else:
        for k, (_, _, b) in enumerate(chosen):
            beats.append(b.model_copy(deep=True))
            picks.append(first + k)
    outro = plan.outro.strip() if clean(plan.outro) else ""
    if outro:
        beats.append(LBeat(narration=outro, visual=LVisual(type="title", headline=title[:60], sub="", items=[],
                                                           icons=[], camera="still")))
        picks.append(None)
    ch = script.chapters[chapter]
    short = script.model_copy(update={"hook": [], "hook_backdrop": "", "chapters": [
        ch.model_copy(update={"beats": beats, "card_text": "", "drop": False, "title": ch.title})]})
    urls = dict(look.get("plateUrls") or {})
    look["plateUrls"] = {"0": urls[str(chapter)]} if str(chapter) in urls else {}

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = slugify(plan.youtube_title or title).strip("-") or "short"
    work = cfg.output_dir / f"{stamp}-{slug}-short-working"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    try:
        _copy_files(folder, work, picks, chapter)
        progress(f"Recording {len(beats)} lines ({cfg.long_voice}, {pace})")
        props = build_long(short, cfg, work, progress, look=look, remake=True)
        if outro:
            end = props["beats"][-1]
            first_beat = old["beats"][first]
            props["endCard"] = {"from": end["start"], "title": title, "length": _clock(report.get("duration_seconds") or 0),
                                "thumb": _end_thumb(folder, work, report, float(first_beat["start"]) + 1.0)}
        props.update(vertical=True, duration=round(props["duration"] + TAIL, 3))
        if props["duration"] > MAX_SECONDS:
            issues.append(f"The Short runs {props['duration']:.0f} s, over YouTube's {MAX_SECONDS} s for a Short.")
        cli = _remotion_cli()
        if cli is None:
            raise RuntimeError("Node.js or the Remotion packages are not installed (run start.bat / start.sh)")
        progress(f"Editing the Short ({props['duration']:.0f} s, 9:16)")
        with _render_slot(cfg):
            _render_remotion(cli, props, work / "reel.mp4", composition="Long", crf=18, progress=progress)
        progress("Verifying the Short")
        info = probe(work / "reel.mp4")
        if (info.get("width"), info.get("height")) != (1080, 1920):
            issues.append(f"Resolution is {info.get('width')}x{info.get('height')}, expected 1080x1920.")
        if not info.get("has_audio"):
            issues.append("No audio track.")
        final = cfg.output_dir / f"{stamp}-{slug}-short"
        work.rename(final)
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        raise
    from .video import FFMPEG

    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", "1", "-i", str(final / "reel.mp4"), "-frames:v", "1",
                    "-q:v", "3", str(final / "thumbnail.jpg")], check=False)
    (final / "props.json").write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
    (final / "script.json").write_text(short.model_dump_json(indent=2), encoding="utf-8")
    tags = [h.strip().lstrip("#") for h in plan.hashtags if h.strip()][:3] or ["shorts"]
    link = link.strip()
    desc = plan.description.strip() + (f"\n\nWatch the full video: {link}" if link else
                                       f"\n\nWatch the full video: {title}")
    new = {
        "id": final.name, "format": "short", "length": "short", "source": "clip", "from_video": folder.name,
        "from_title": title, "clip": {"first": first, "last": last, "mode": mode if body or mode == "exact" else "exact",
                                      "seconds": seconds if mode == "explain" else None},
        "topic": report.get("topic", ""), "subject": report.get("subject", ""), "category": report.get("category", ""),
        "style": report.get("style", ""), "title": plan.youtube_title or title,
        "narration": " ".join(b.narration for b in beats), "created_at": stamp, "verified": not issues, "score": None,
        "issues": issues, "checks": {"probe": info}, "attempts": 1, "video": str(final / "reel.mp4"),
        "thumbnail": str(final / "thumbnail.jpg"), "duration_seconds": round(props["duration"], 1),
        "captions": cfg.captions, "voice": cfg.long_voice, "voice_rate": pace, "language": report.get("language", ""),
        "youtube_title": (plan.youtube_title or title)[:100], "caption": desc, "hashtags": tags,
        "youtube_description": desc, "youtube_hashtags": tags, "youtube_tags": report.get("youtube_tags", []),
        "full_video_link": link,
        "related_video_tip": f"In YouTube Studio open this Short > Details > Related video and pick '{title}': "
                             "YouTube then shows a link to it under the Short, where the end card points.",
        "music": props.get("musicChoice", ""), "editor": "remotion (Long, 9:16)", "sources": report.get("sources", []),
        "credits": report.get("credits", []),
    }
    (final / "report.json").write_text(json.dumps(new, indent=2, ensure_ascii=False), encoding="utf-8")
    progress(done_line(new))
    return new
