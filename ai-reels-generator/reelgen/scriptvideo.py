"""Script Video: a long video made from the user's own finished script.

The user gives the title, description, hook and full script, already fact-checked and approved.
Nothing they wrote is rewritten or checked again. The text is cut into lines here, in code, so
every spoken word stays exactly as written; one Claude call (no web search) then storyboards it:
a visual and sounds for every line, the chapters and their music, and the hook as a trailer of
shots built from the user's hook lines. The result is an ordinary LongScript, handed to the
existing long-video loop as already scripted (longform._long_loop with `manual`): voice, sound
design, music, 3D/footage, the Remotion edit and the technical checks are the long pipeline's own.
"""

import json
import logging
import re
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pydantic import BaseModel, Field

from . import media, variety
from .config import Config
from .llm import ask
from .longform import (LLM_TIMEOUT, WORDS_PER_SECOND, HookShot, LBeat, LChapter, LongScript, LVisual, Progress,
                       _long_loop, _system, repair_long_script)
from .script_writer import SoundCue
from .trends import Trend

log = logging.getLogger(__name__)

Category = LongScript.model_fields["category"].annotation
Mood = LongScript.model_fields["mood"].annotation
HookMusic = LongScript.model_fields["hook_music"].annotation
Ambience = LChapter.model_fields["ambience"].annotation
TrailerBeat = HookShot.model_fields["beat"].annotation
MAX_SILENT = 3  # picture-and-sound-only shots Claude may add to the hook


@dataclass
class ScriptInput:
    title: str
    description: str
    hook: str
    script: str


# ---------- cutting the text into lines (code, so the words never change) ----------

_SENTENCE = re.compile(r"(?<=[.!?…])[\"'”’)\]]*\s+")
_HEADING = re.compile(r"^\s*(#+\s*|(chapter|part)\s+\w+\s*[:.\-–—]?\s*)", re.I)


def _words(text: str) -> int:
    return len(text.split())


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE.split(" ".join(text.split())) if s.strip()]


def _split_long(sentence: str, limit: int) -> list[str]:
    """A sentence over `limit` words is cut at commas, semicolons or dashes, nearest the middle."""
    if _words(sentence) <= limit:
        return [sentence]
    cuts = [m.end() for m in re.finditer(r"[,;:]\s+|\s+[–—-]\s+", sentence)]
    if not cuts:
        return [sentence]
    mid = len(sentence) / 2
    at = min(cuts, key=lambda c: abs(c - mid))
    return _split_long(sentence[:at].strip(), limit) + _split_long(sentence[at:].strip(), limit)


def _beats(paragraph: str) -> list[str]:
    """Lines of 12-30 words where the sentences allow it: short sentences are joined, a long one
    is cut at a comma. A sentence is never cut mid-clause."""
    out, acc = [], []
    for s in (p for sentence in _sentences(paragraph) for p in _split_long(sentence, 34)):
        if acc and (_words(" ".join(acc)) >= 12 or _words(" ".join(acc + [s])) > 30):
            out.append(" ".join(acc))
            acc = []
        acc.append(s)
    if acc:
        out.append(" ".join(acc))
    return out


def _is_heading(line: str) -> bool:
    line = line.strip()
    if _HEADING.match(line):
        return True
    return 0 < _words(line) <= 8 and not re.search(r"[.!?,;\"”…]$", line)


def parse_script(text: str) -> tuple[list[str], list[tuple[int, str]]]:
    """The script's lines, and the chapters the user marked (first line index, title), if any.
    A heading is a short line without end punctuation ('Chapter 2: The Crash', '## The Money')."""
    lines: list[str] = []
    chapters: list[tuple[int, str]] = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip()):
        rows = [r for r in block.split("\n") if r.strip()]
        while rows and _is_heading(rows[0]):
            title = _HEADING.sub("", rows[0]).strip(" #:-–—") or rows[0].strip(" #")
            chapters.append((len(lines), title))
            rows = rows[1:]
        if rows:
            lines += _beats(" ".join(rows))
    # A heading with no lines after it (or two in a row) marks nothing.
    chapters = [c for i, c in enumerate(chapters) if c[0] < len(lines) and (i + 1 == len(chapters) or chapters[i + 1][0] > c[0])]
    if chapters and chapters[0][0] != 0:
        chapters.insert(0, (0, "Intro"))
    return lines, chapters


def parse_hook(text: str) -> list[str]:
    """The hook's lines: one per sentence, a sentence over 12 words cut at a comma or dash."""
    return [p for s in _sentences(text) for p in _split_long(s, 12)]


# ---------- the storyboard (one Claude call, no web search) ----------

class BoardShot(BaseModel):
    line: int = Field(description="The hook line spoken over this shot (H3 = 3), or 0 for a silent shot carried by picture and sound alone.")
    beat: TrailerBeat = Field(description="Which part of the trailer this shot is: curiosity, unexpected, tension, problem or gap, in that order across the shots.")
    text: str = Field(default="", description="On-screen text slammed in: 1-3 words taken from the line (or, for a silent shot, from the hook), or empty. Most shots have none.")
    visual: LVisual = Field(description="What we see: exactly what the line says, dramatic camera. Prefer motion: scene, model3d, footage, icons, stat.")
    sounds: list[SoundCue] = Field(default_factory=list, description="0-2 sound effects: on a word of the line, or word '*' to land on the slammed text.")


class BoardChapter(BaseModel):
    first_line: int = Field(description="The number of the chapter's first line.")
    title: str = Field(description="Chapter title for the title card and YouTube chapters, 2-5 words, a clear searchable phrase. The first chapter is 'Intro'. When the user marked the chapters, their title exactly.")
    music: str = LChapter.model_fields["music"]
    intensity: int = LChapter.model_fields["intensity"]
    drop: bool = LChapter.model_fields["drop"]
    ambience: Ambience = LChapter.model_fields["ambience"]


class BoardBeat(BaseModel):
    line: int = Field(description="The line number.")
    visual: LVisual = Field(description="What we see while this line is spoken: exactly what it says.")
    sounds: list[SoundCue] = Field(default_factory=list, description="Sound effects on words of this line: up to 4 in the first lines, otherwise usually none.")


class Storyboard(BaseModel):
    category: Category = LongScript.model_fields["category"]
    subject: str = Field(description="The one subject the video is about, in a few words.")
    hook_question: str = Field(description="The big question the script plants, in one sentence (for the record; never shown).")
    mood: Mood = LongScript.model_fields["mood"]
    hook_music: HookMusic = LongScript.model_fields["hook_music"]
    hook_track: str = LongScript.model_fields["hook_track"]
    music: str = LongScript.model_fields["music"]
    hook: list[BoardShot] = Field(description="The hook's shots in order: every hook line exactly once, in order, plus at most 3 silent shots.")
    chapters: list[BoardChapter] = Field(description="The chapters in order, by their first line.")
    beats: list[BoardBeat] = Field(description="One entry per script line, in order, every line.")


def _board_system(cfg: Config) -> str:
    """The long writer's own rules for visuals, sound and music (the same pipeline, the same look),
    with the writing, research and accuracy parts left out: the words are final."""
    full = _system(cfg.video_style, cfg.long_language)
    rules = full[full.index("Show, don't write"):full.index("Accuracy:")].strip()
    return f"""You storyboard a finished YouTube video script for an animated motion-graphics video. The \
script, its hook, title and description are written, fact-checked and approved by the user. Never change, \
add, remove or reorder a spoken word: you only decide what the viewer sees and hears.

For every numbered line, pick the animated visual that shows exactly what that line says, and its sound \
effects. Numbers, dates, names and quotes on screen come only from the script's own lines, written as the \
line says them; never add a figure, date or quote the line doesn't state, never round one. A 'quote' visual \
only for words the script itself quotes; a 'chart' or 'compare' only with figures the script gives.

The hook is a cinematic trailer before the video, built from the user's hook lines H1, H2... Give every \
hook line exactly one shot, in order. Where a picture or a sound lands harder without words, add a silent \
shot (line 0) between or after them, at most 3. Spread the trailer beats across the shots in order: \
curiosity (a strong visual and an instant question), unexpected (the surprising situation), tension \
(build the stakes), problem (part of the problem), gap (the question left hanging). Slam 1-3 words on \
screen on the biggest moments only (most shots have none), taken from the hook. Use dramatic camera moves \
(push, dutch, orbit, pan), quick visual changes and the hook's own trailer music. The visuals must match \
the hook's words exactly, and never show the answer the script keeps for the end.

Chapters: when the user marked chapters, keep them exactly (same first lines and titles) and set their \
music. Otherwise group the lines into chapters at the story's natural turns: a cold open titled 'Intro', \
then chapters of roughly 6-14 lines, each with a clear 2-5 word searchable title.

{rules}"""


def _numbered(hook: list[str], lines: list[str], marked: list[tuple[int, str]]) -> str:
    starts = dict(marked)
    out = ["Hook lines:"] + [f"H{i} {h}" for i, h in enumerate(hook, 1)] + ["", "Script lines:"]
    for i, line in enumerate(lines):
        if i in starts:
            out.append(f"## Chapter: {starts[i]}")
        out.append(f"{i + 1} {line}")
    return "\n".join(out)


def storyboard(cfg: Config, given: ScriptInput, hook: list[str], lines: list[str],
               marked: list[tuple[int, str]]) -> Storyboard:
    prompt = (f"Title: {given.title}\nDescription (context only): {given.description}\n\n"
              + _numbered(hook, lines, marked)
              + ("\n\nThe user marked the chapters (## lines): keep them." if marked else
                 "\n\nNo chapters are marked: group the lines into chapters.")
              + variety.recent_block(cfg) + "\n\n" + media.prompt_block(cfg, long=True) + media.models_block(cfg)
              + f"\n\nReturn {len(hook)} hook line shot(s) (plus up to {MAX_SILENT} silent ones) and exactly "
                f"{len(lines)} beats, one per script line.")
    return ask(cfg.ai_backend, cfg.claude_model, _board_system(cfg), prompt, Storyboard, allow_web=False,
               effort=cfg.claude_effort, timeout=LLM_TIMEOUT)


def _fallback_visual(line: str) -> LVisual:
    """For a line the storyboard skipped: a few icons, no words of its own."""
    return LVisual(type="icons", headline="", sub="", items=[], icons=["sparkles"], camera="push")


def _hook_shots(board: Storyboard, hook: list[str]) -> list[HookShot]:
    """Every hook line once, in order, with Claude's shot for it; silent shots kept where they are."""
    shots, nxt, silent = [], 1, 0
    order: list[TrailerBeat] = ["curiosity", "unexpected", "tension", "problem", "gap"]

    def missing(n: int) -> HookShot:
        return HookShot(beat=order[min(4, (n - 1) * 5 // max(1, len(hook)))], line=hook[n - 1],
                        visual=_fallback_visual(hook[n - 1]))

    for s in board.hook:
        if s.line == 0 and silent < MAX_SILENT and shots:
            shots.append(HookShot(beat=s.beat, line="", text=s.text, visual=s.visual, sounds=s.sounds))
            silent += 1
        elif nxt <= s.line <= len(hook):
            while nxt < s.line:
                shots.append(missing(nxt))
                nxt += 1
            shots.append(HookShot(beat=s.beat, line=hook[s.line - 1], text=s.text, visual=s.visual, sounds=s.sounds))
            nxt += 1
    while nxt <= len(hook):
        shots.append(missing(nxt))
        nxt += 1
    return shots


def assemble(given: ScriptInput, board: Storyboard, hook: list[str], lines: list[str],
             marked: list[tuple[int, str]]) -> LongScript:
    """The storyboard plus the user's own words, as an ordinary long-video script."""
    visuals = {b.line: b for b in board.beats if 1 <= b.line <= len(lines)}
    skipped = [i for i in range(1, len(lines) + 1) if i not in visuals]
    if skipped:
        log.warning("Storyboard skipped line(s) %s: they get a simple icon visual", skipped)
    settings = sorted({c.first_line: c for c in board.chapters if 1 <= c.first_line <= len(lines)}.values(),
                      key=lambda c: c.first_line)
    if marked:  # the user's chapters, with the music Claude set for each
        starts = [(i, title, settings[k] if k < len(settings) else None) for k, (i, title) in enumerate(marked)]
    else:
        starts = [(c.first_line - 1, c.title, c) for c in settings] or [(0, "Intro", None)]
        starts[0] = (0, starts[0][1], starts[0][2])
    chapters = []
    for k, (first, title, c) in enumerate(starts):
        last = starts[k + 1][0] if k + 1 < len(starts) else len(lines)
        if last <= first:
            continue
        beats = [LBeat(narration=lines[i], visual=visuals[i + 1].visual if i + 1 in visuals else _fallback_visual(lines[i]),
                       sounds=visuals[i + 1].sounds if i + 1 in visuals else []) for i in range(first, last)]
        extra = {"music": c.music, "intensity": c.intensity, "drop": c.drop, "ambience": c.ambience} if c else {}
        chapters.append(LChapter(title=title, beats=beats, **extra))
    script = LongScript(topic=given.title, why_chosen="Your own script.", facts_checked="Checked and approved by you.",
                        category=board.category, subject=board.subject, hook_question=board.hook_question, answer="",
                        youtube_title=given.title, hook=_hook_shots(board, hook) if hook else [], mood=board.mood,
                        hook_music=board.hook_music, hook_track=board.hook_track, chapters=chapters, music=board.music)
    return repair_long_script(script)  # the long pipeline's own free visual fixes; never the words


def spoken_text(script: LongScript) -> str:
    return " ".join(b.narration for c in script.chapters for b in c.beats)


# ---------- the run ----------

def run_script_video(cfg: Config, given: ScriptInput, progress: Progress = log.info) -> dict:
    """One video from the user's script: storyboard it, then the long pipeline from 'scripted' on."""
    from .pipeline import CHECKPOINT

    lines, marked = parse_script(given.script)
    if not lines:
        raise ValueError("The script is empty.")
    hook = parse_hook(given.hook)
    minutes = sum(_words(x) for x in lines) / WORDS_PER_SECOND / 60
    progress(f"Your script: {len(lines)} lines, about {minutes:.1f} min of narration"
             + (f", {len(marked)} chapters marked" if marked else "") + f"; hook: {len(hook)} line(s)")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    work = cfg.output_dir / f"{stamp}-{uuid.uuid4().hex[:4]}-script-working"
    work.mkdir(parents=True, exist_ok=True)
    progress(f"Saving progress in {work.name}")
    progress("Claude is storyboarding your script and hook (visuals, sounds, music)")
    board = storyboard(cfg, given, hook, lines, marked)
    script = assemble(given, board, hook, lines, marked)
    assert spoken_text(script) == " ".join(lines)  # not one spoken word changed
    manual = {"title": given.title, "description": given.description, "hook": given.hook, "script": given.script}
    state = {"length": "long", "minutes": minutes, "topic": given.title, "stamp": stamp, "style": cfg.video_style,
             "candidates": [{"title": given.title, "source": "your script"}], "attempt": 1, "stage": "scripted",
             "script": script.model_dump(), "manual": manual}  # usage: the loop's own saves record it
    (work / CHECKPOINT).write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    return _long_loop(replace(cfg, long_minutes=minutes), work, [Trend(title=given.title, source="your script")],
                      given.title, stamp, progress, resume=state)


def run_script_job(cfg: Config, given: ScriptInput, progress: Progress) -> list[dict]:
    """The app's job: one Script Video in the shared video slot, with token metering and pause."""
    from .llm import set_limit_reporter, start_meter, usage_line
    from .pipeline import Paused, _video_slot, done_line, set_pause_check

    should_pause = getattr(progress, "should_pause", None)
    with _video_slot(cfg):
        set_pause_check(should_pause)
        set_limit_reporter(progress)
        start_meter(lambda r: progress(usage_line(r)))
        progress("=== Video 1/1 ===")
        try:
            report = run_script_video(cfg, given, progress)
            progress(done_line(report))
            return [report]
        except Paused:
            progress("Paused: progress saved. Press Resume to carry on from here.")
        except Exception as exc:
            log.exception("Script video failed")
            progress(f"Video 1 failed: {exc}")
    return []
