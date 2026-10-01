"""Long videos: 8-10 minute, 16:9, fully animated (no stock footage), for YouTube.

trend -> Claude writes a chaptered script where every beat has a narration line and an
animated visual -> fact-check and fix (before anything is recorded) -> Indian English
voice, one take per chapter -> Remotion "Long" composition -> checks -> Claude review of
frames from every chapter -> report with YouTube chapter timestamps and post text.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import uuid
import zlib
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal

from PIL import Image
from pydantic import BaseModel, Field

from .fsutil import move
from .config import Config
from .llm import ask, meter_add_earlier, meter_records, start_meter, summarize_usage, usage_line
from .post_copy import clean_tags, save_post_text
from . import media
from .models3d import Part, find_model
from .script_writer import AI_CLICHES, SoundCue
from . import music, sound_design, variety
from .sfx import write_cue_sounds, write_sfx
from .trends import collect_trends, load_history, save_history, trends_as_json, Trend
from .verify import FactCheck, VerifyResult, Review, probe
from .video import FFMPEG, _remotion_cli, _render_remotion, media_seconds
from .visuals import pexels_video
from .voice import SceneAudio, synthesize_scenes

log = logging.getLogger(__name__)
Progress = Callable[[str], None]

WIDTH, HEIGHT = 1920, 1080
CARD_SECONDS = 2.4  # chapter title card
CHAPTER_GAP = 0.5  # breath at the end of each chapter
WORDS_PER_SECOND = 2.5  # measured presenter pace at +10%, pauses included
MIN_MINUTES, MAX_MINUTES = 6.5, 11.0
FACT_FIXES = 2
LLM_TIMEOUT = 2400  # a 1,300-word script with research at high effort can take well over 15 minutes
LONG_ATTEMPTS = 2  # a long render takes a long time; one full retry at most
VISUAL_TYPES = ("title", "stat", "timeline", "compare", "steps", "icons", "quote", "keyword", "chart", "footage",
                "model3d", "scene")
TEXT_TYPES = ("title", "keyword")  # visuals that are mostly words
HOOK_SECONDS = (25.0, 30.0)


# ---------- the script ----------

class LItem(BaseModel):
    label: str = Field(description="timeline: the date or year. compare/chart: the side or the time point. steps: the step's short name.")
    text: str = Field(description="timeline: what happened (max 6 words). steps: one short detail. Empty otherwise.")
    value: float = Field(description="compare/chart: the real number used for the bar or point. 0 otherwise.")
    display: str = Field(description="compare/chart: how the number is written, e.g. '₹2.4 lakh crore', '46,000'. Empty otherwise.")


class SceneActor(BaseModel):
    icon: str = Field(description="A Lucide icon name in kebab-case that is the actor, e.g. 'user', 'ship', 'factory', 'microscope', 'truck', 'banknote'.")
    action: Literal["enter-left", "enter-right", "drop-in", "rise", "walk-across", "approach", "flee", "shake",
                    "pulse", "spin", "fall", "grow", "shrink", "orbit", "multiply"] = Field(
        description="What it does. enter-left/right: slides in. drop-in: falls in and bounces. rise: comes up from below. walk-across: crosses the frame. approach: comes close to the camera. flee: rushes away. shake: trembles (fear, alarm). pulse: beats like a heart. spin: turns. fall: topples and drops. grow: swells huge. shrink: dwindles. orbit: circles the first actor. multiply: becomes a crowd of copies.")
    label: str = Field(default="", description="At most 2 words under it, or empty (usually empty: the narration says it).")


class LVisual(BaseModel):
    type: Literal["title", "stat", "timeline", "compare", "steps", "icons", "quote", "keyword", "chart",
                  "footage", "model3d", "scene"] = Field(
        description="title: a big headline. stat: one striking number. timeline: 2-5 dated moments. compare: "
                    "exactly 2 things side by side. steps: 2-4 steps of how something works. icons: 1-3 icons "
                    "that picture the line. quote: a real, verified quote. keyword: one word or short phrase. "
                    "chart: 3-6 real data points over time. footage: a real video clip of a place or scene, "
                    "full screen. model3d: an object from the story as an animated 3D model. scene: a small "
                    "animated scene of 1-4 icon 'actors' that act the line out (enter, chase, fall, grow...).")
    headline: str = Field(description="title/keyword: the text (keyword max 3 words). stat: the number exactly as shown, e.g. '₹1.2 lakh'. quote: the quote. icons/timeline/compare/steps/chart: a short heading (max 7 words).")
    sub: str = Field(description="A short supporting line (max 10 words): what the stat is, who said the quote, the chart's unit. Can be empty.")
    items: list[LItem] = Field(description="timeline: 2-5, compare: exactly 2, steps: 2-4, chart: 3-6. Empty for the other types.")
    icons: list[str] = Field(description="icons: 1-3 Lucide icon names in kebab-case that picture the line, e.g. 'cloud-rain', 'train-front', 'indian-rupee', 'landmark', 'satellite'. Empty for other types.")
    query: str = Field(default="", description="footage only: an English stock-video search, 2-4 words, the place or subject first, e.g. 'stockholm old town', 'monsoon rain street'. Empty otherwise.")
    model: str = Field(default="", description="model3d only: the object, concretely, e.g. 'red oil barrel', 'vintage propeller plane', 'gold coin'. Empty otherwise.")
    search: str = Field(default="", description="model3d only: 1-3 English words to find a ready-made model, the main noun LAST, e.g. 'oil barrel', 'propeller plane', 'coin'. Empty otherwise.")
    parts: list[Part] = Field(default_factory=list, description="model3d only: how to build the object from 4-24 simple shapes if no ready-made model is found, in metres, +Y up, front facing +Z. Make it recognisable: proportions and colours matter more than detail. Empty otherwise.")
    scene: Literal["sky", "space", "studio"] = Field(default="studio", description="model3d only: where it's shown. sky: flying through clouds. space: drifting among stars. studio: turning on a dark stage.")
    actors: list[SceneActor] = Field(default_factory=list, description="scene only: 1-4 icon actors, in the order they act. Empty otherwise.")
    camera: Literal["push", "pull", "pan-left", "pan-right", "rise", "dutch", "orbit", "still"] = Field(
        default="push", description="How the camera moves during this beat. Vary it; never the same move three beats in a row. 'still' only for a calm pause.")
    impact: bool = Field(default=False, description="True only for the few biggest moments (a reveal, the twist, a shocking number): a punch-in, a short freeze with a flash, a screen shake and a bass hit. At most one per chapter.")


class LBeat(BaseModel):
    narration: str = Field(description="What the narrator says over this visual: 1-2 sentences, 12-30 words.")
    visual: LVisual
    sounds: list[SoundCue] = Field(default_factory=list, description="Sound effects on words of this line: up to 4 layered in the cold open's first beats, otherwise usually none.")


class HookShot(BaseModel):
    beat: Literal["curiosity", "unexpected", "tension", "problem", "gap"] = Field(
        description="Which part of the trailer this shot is: curiosity (0-4 s: a strong visual and an instant question), unexpected (4-9 s: the surprising situation), tension (9-15 s: build the stakes), problem (15-22 s: show part of the problem), gap (22-27 s: the curiosity gap, the question left hanging).")
    line: str = Field(description="What the narrator says, trailer style: a short, punchy line of 3-12 words, or empty for a shot carried by sound and picture alone. Never reveals the answer.")
    text: str = Field(default="", description="On-screen text slammed in for this shot: 1-3 words (a date, a number, a place, 'WAIT...'), or empty. Most shots have none.")
    visual: LVisual = Field(description="What we see. Prefer motion: scene, model3d, footage, icons, stat. The camera move should be dramatic (push, dutch, orbit, pan).")


class LChapter(BaseModel):
    title: str = Field(description="Chapter title for the title card and YouTube chapters, 2-5 words. YouTube shows chapters as 'key moments' in search, so make it a clear, searchable phrase about what the chapter covers ('How Oxford Mass-Produced It', not 'A New Hope'). Chapter 1 (the cold open) is 'Intro'.")
    beats: list[LBeat] = Field(description="6-14 beats. Each beat's visual shows what its narration says.")
    intensity: int = Field(default=3, ge=1, le=5, description="How intense the music is under this chapter, 1 (quiet, reflective) to 5 (peak). Build toward the twist and the ending; drop low after a peak so the next build is felt.")
    drop: bool = Field(default=False, description="True for the one or two chapters that open on the twist or the big turn: the music cuts to silence for a moment, then hits.")
    ambience: Literal["none", "room", "city", "rain", "wind", "crowd", "night", "lab", "sea", "fire"] = Field(
        default="none", description="A quiet background sound bed for where this chapter takes place, or 'none'.")


class LongScript(BaseModel):
    topic: str = Field(description="The trending topic you chose, exactly as written in the candidate list (fiction: the theme you used).")
    why_chosen: str = Field(description="One sentence: why this will hold viewers for 8 minutes, and the one story you will tell.")
    facts_checked: str = Field(description="The key facts the script relies on and where they come from.")
    category: Literal["Sports", "Money", "Science & Space", "Tech", "History", "Nature & Animals", "Weather",
                      "Entertainment", "India", "Life & People", "Stories", "Comedy"] = Field(
        description="The library shelf this video belongs on. Fiction is 'Stories', jokes are 'Comedy'; otherwise the subject area.")
    subject: str = Field(description="The one subject the whole video explores in depth.")
    hook_question: str = Field(description="The one big question the cold open plants; the video answers it only in the last chapter.")
    answer: str = Field(description="The answer or twist the last chapter delivers, in one sentence.")
    youtube_title: str = Field(description="YouTube title, max 70 characters: curiosity plus the main search keyword, no clickbait the video doesn't deliver.")
    hook: list[HookShot] = Field(default_factory=list, description="The 25-30 second energetic cinematic hook before the video starts: 6-9 shots in trailer order (curiosity, unexpected, tension, problem, gap). A teaser, not the story starting: it makes the viewer think 'wait, what happened?' and never gives away the answer.")
    mood: Literal["mystery", "suspense", "emotional", "uplifting", "curious", "dark", "energetic", "calm"] = Field(
        default="curious", description="The music's mood for the main video, chosen from the story.")
    hook_music: Literal["spy-pulse", "ticking-clock", "dark-pulse", "glitch-drive"] = Field(
        default="spy-pulse", description="The hook's own trailer track: spy-pulse (ticking spy/action energy), ticking-clock (a race against time), dark-pulse (dread, mystery), glitch-drive (tech, chaos).")
    chapters: list[LChapter] = Field(description="6-8 chapters in order. The first is the cold open ('Intro').")
    music: str = Field(default="", description="Background track name from the music list, or 'none'.")


def _system(style: str, language: str) -> str:
    kind = ("a true story told like a documentary, every fact checked" if style != "story"
            else "an original fiction story, clearly presented as a story")
    return f"""You write 8 to 10 minute YouTube videos that people watch to the end: {kind}. \
The video is animated motion graphics, so every beat pairs one narration line with one animated \
visual that shows exactly what that line says. A few beats can be a real video clip or a 3D model.

Language and voice: write in {language}. For Indian English that means natural, educated Indian English \
as a sharp Indian presenter speaks it: clear and warm, not American slang, not Hinglish. Use lakh and \
crore with rupees for Indian money, metric units, and Indian comparisons (a Mumbai local train, a \
cricket ground, the monsoon) where they genuinely make a number easier to picture. Read by \
text-to-speech: no abbreviations, symbols or emojis in narration; write numbers as they are spoken.

Retention structure (the most important rules):
- Build the big question around the most surprising fact in the story (the paradox or twist), \
not the obvious "how did they do it": e.g. "Sweden flipped every car to the other side of the \
road, and crashes dropped. Why?" beats "How did Sweden switch sides?".
- Chapter 1, the cold open (45-75 seconds): the first sentence (12 words or fewer) plants that \
question. Then raise the stakes. It must NOT explain the method, the answer or the twist, not \
even in passing; the viewer learns them where the story reaches them. No greeting, no "in this \
video", no "by the end you'll know".
- Never repeat the answer: reveal it once, late, then use it for the payoff.
- 5 to 7 more chapters of 60-100 seconds. Each opens with a mini-hook (a new question or surprise) \
and ends on an open loop that pulls into the next ("But that created a bigger problem.").
- Around the middle, a twist that changes how the story looks.
- The big question is answered only in the last chapter, which ties back to the first line and ends \
with one short, natural line asking viewers to subscribe for the next story.
- One subject, in depth: the whole video stays on the subject you name. Every chapter goes a level \
deeper (how, why, the telling detail, what it caused, what nobody expects). Never a list of \
separate examples.
- Scenes are linked by "but" and "so", never "and also". Vary sentence length. No filler \
("think about that", "their answer was brutal").
- Vary how chapters open: a question, a scene, a number, a quote, a contradiction. Never the \
same pattern twice in a row.
- No chapter is a list (logo, song, signs, buses...): every beat must raise the risk, answer a \
worry or push the story forward, or it goes.
- The call to action names a concrete next story, not a generic "subscribe for more".
- Never use these phrases: {", ".join(AI_CLICHES)}.

The hook (25-30 seconds, before chapter 1): an energetic cinematic trailer for this video, NOT the \
story starting. It has its own look and its own driving music. 6-9 fast shots in this order: curiosity \
(0-4 s, a strong visual and an instant question), unexpected (4-9 s, the surprising situation), tension \
(9-15 s, build the stakes), problem (15-22 s, show part of the problem), gap (22-27 s, the question left \
hanging); then it cuts to the video. Keep the energy high: quick shots, punchy lines, a word slammed in \
on the big moments. Lines are short and punchy (3-12 words; some shots have no line \
at all and let picture and sound carry them). It must make the viewer think "wait... what happened?" \
and must never give away the answer or the punchline. The cold open (chapter 1) then starts the story.

Show, don't write (very important): the story is told by motion, camera and sound; text only \
supports it. The weak version is "big text, then another big text". The strong version: an actor \
enters, the camera pushes in, something falls, a number counts up, a sound hits, then two short words.
- 'keyword' and 'title' beats (mostly words) are at most 1 in 7 beats and never two in a row. Keyword \
text is at most 3 words, a headline at most 6.
- Use 'scene' often: 1-4 icon actors that act the line out (a ship enters and a storm icon shakes \
above it; coins multiply; a factory grows; a person flees). Pick concrete icons and actions that \
match the words.
- Pick a camera move for every visual and vary them (push, pull, pans, rise, dutch, orbit); save \
'impact' for the one biggest moment of a chapter.

Music and sound: set the music mood from the story, and give every chapter an intensity (1-5) that \
follows the tension: build toward the twist and the ending, fall back after a peak, and mark the \
chapter that opens on the twist with a drop. Pick an ambience only where a place matters.

Visuals:
- Every visual must match its line. Numbers on screen must be real, sourced and identical to what \
the narration says; no made-up, rounded-up or "illustrative" data. A chart needs real figures; \
otherwise use a stat or a keyword. A quote must be a real, verified quote with its speaker; if you \
can't verify one, don't use a quote.
- Vary the types; never the same type twice in a row. Prefer scene, icons, timelines, steps, \
compares, charts, stats, footage and 3D that make the idea visual.
- 'footage' (at most one per chapter, only in a true story): when the viewer needs to SEE a real \
place or scene the line talks about (a city, a landscape, a busy street, rain on a road). Only what \
stock video can show truthfully: a city or country by name, nature, everyday scenes. Never a named \
person, a specific event, a specific building's interior, an old photo or anything from the past \
("stockholm 1967"): stock video is filmed recently. The headline is a short place label ("Stockholm") \
and the sub what we're seeing; both may be empty.
- 'model3d' (at most once per chapter, only where it helps): the one object a line is about, brought \
to life in 3D, e.g. the plane while the line talks about a flight, a satellite in space, a barrel of \
oil for an oil-price line, a coin for money. You decide the object from the story. Describe it, give \
search words, and always give its parts (4-24 simple shapes) so it can be built if no ready-made \
model exists. Pick the scene: 'sky' only for things that fly (the model flies left to right with its \
front first), 'space' for space objects, 'studio' (a turntable) for everything else. Never in a \
serious or tragic moment (a crash, a war, a death, a disaster): a toy-like 3D model there is \
disrespectful. Headline: a short label, or empty.

Accuracy: only state facts you are confident about or have looked up with web search. Never invent \
details, dialogue or figures in a true story. Timeless wording: never "today", "this week" or "five \
days ago"; use dates. No politics or politicians, tragedies, violence, or rumours about real people. \
Fiction uses invented characters only and never presents itself as real events."""


def write_long_script(cfg: Config, candidates: list[Trend], minutes: float, feedback: str = "",
                      previous: LongScript | None = None) -> LongScript:
    words = int(minutes * 60 * WORDS_PER_SECOND)
    task = ("Pick the candidate with the richest story behind it and write the video." if cfg.video_style != "story"
            else "Write an original fiction story; the topics are only inspiration.")
    prompt = (f"Candidate topics trending now (region {cfg.geo}):\n{trends_as_json(candidates)}\n\n{task}\n"
              f"- Length: about {words} words of narration in total ({minutes:g} minutes), no less than "
              f"{int(words * 0.9)} and no more than {int(words * 1.1)}.\n"
              f"- 6 to 8 chapters, 6 to 14 beats each." + variety.recent_block(cfg) + "\n\n"
              + media.prompt_block(cfg, long=True)
              + media.models_block(cfg))
    if len(candidates) == 1 and candidates[0].source == "manual":
        prompt += f"\n- The user asked for this topic: {candidates[0].title}. Use it."
    if feedback:
        prompt += f"\n\nThe previous draft was rejected. Fix every point:\n{feedback}"
        if previous is not None:
            prompt += (f"\n\nThe rejected draft:\n{previous.model_dump_json()}\n"
                       "Keep what works; rewrite what was flagged. Don't reuse a flagged claim in softer words.")
    script = ask(cfg.ai_backend, cfg.claude_model, _system(cfg.video_style, cfg.long_language), prompt,
                 LongScript, allow_web=True, effort=cfg.claude_effort, timeout=LLM_TIMEOUT)
    log.info("Long video topic: %s (%s)", script.topic, script.why_chosen)
    return script


class BeatFix(BaseModel):
    chapter: int = Field(description="Chapter number, 1-based, as in the numbered script (3.4 = chapter 3). 0 for a hook line (H2 = chapter 0, beat 2).")
    beat: int = Field(description="Beat number within the chapter, 1-based (3.4 = beat 4); for a hook line its number (H2 = 2).")
    narration: str = Field(description="The corrected line, same length and flow as before.")
    visual: LVisual = Field(description="The corrected visual; unchanged if only the words were wrong.")
    text: str | None = Field(default=None, description="Hook lines only: the corrected on-screen word slam (1-3 words), or '' to remove it. Leave null to keep it.")


class ScriptFixes(BaseModel):
    fixes: list[BeatFix] = Field(description="One entry per line that must change. Only the flagged lines.")


FIX_SYSTEM = """You correct flagged lines in a finished documentary script. Change only what the fact-check \
flagged, keep each line's length, tone and place in the story, and keep every number on screen identical to \
its narration. If a claim can't be stated accurately, replace it with a nearby fact you are sure of, or make \
the line less specific. Use web search when you need to confirm the corrected fact."""

STRICT_FIX = ("These lines were already corrected before and are still flagged. Don't try another version of "
              "the same claim: drop the disputed detail or say only what every source agrees on (less specific "
              "is fine: 'one of the country's bestselling office products' instead of 'top five'). Visuals must "
              "match: no number or ranking on screen that the sources don't all confirm.")

Line = tuple  # (chapter, beat); chapter 0 = the hook


def _numbered(script: LongScript, mark: set | None = None) -> str:
    """The script with line numbers (H1.. for the hook, 3.4 for chapter 3 beat 4); `mark` puts >> on lines."""
    out = []
    for hi, h in enumerate(script.hook, 1):
        m = ">> " if mark and (0, hi) in mark else ""
        out.append(f"{m}H{hi} {h.line}  {_visual_text(h.visual)}" + (f" [text: {h.text}]" if h.text else ""))
    for ci, c in enumerate(script.chapters, 1):
        out.append(f"\nChapter {ci}: {c.title}")
        for bi, b in enumerate(c.beats, 1):
            m = ">> " if mark and (ci, bi) in mark else ""
            out.append(f"{m}{ci}.{bi} {b.narration}  {_visual_text(b.visual)}")
    return "\n".join(out)


def fix_long_script(script: LongScript, cfg: Config, issues: list[str], instructions: str,
                    strict: bool = False) -> tuple[LongScript, set]:
    """Rewrite only the flagged lines. Regenerating the whole script to fix one figure
    brought new small errors each time; a targeted fix leaves everything else untouched.
    Returns the fixed script and which lines changed (so only those are checked again)."""
    prompt = (f"The script, numbered (H = hook line, chapter.beat):\n{_numbered(script)}\n\nProblems flagged:\n"
              + "\n".join(issues) + (f"\n\nSuggested fixes: {instructions}" if instructions else "")
              + "\n\nFor a rule about the script's form (a visual type, text length, two slides in a row, a phrase to "
                "avoid, a hook line), change only the lines involved."
              + (f"\n\n{STRICT_FIX}" if strict else "") + "\n\nReturn the corrected lines only.")
    result = ask(cfg.ai_backend, cfg.claude_model, FIX_SYSTEM, prompt, ScriptFixes, allow_web=True,
                 effort=cfg.claude_effort, timeout=LLM_TIMEOUT)
    fixed = script.model_copy(deep=True)
    changed = set()
    for f in result.fixes:
        if f.chapter == 0 and 1 <= f.beat <= len(fixed.hook):
            h = fixed.hook[f.beat - 1]
            fixed.hook[f.beat - 1] = HookShot(beat=h.beat, line=f.narration, visual=f.visual,
                                              text=h.text if f.text is None else f.text)
            changed.add((0, f.beat))
        elif 1 <= f.chapter <= len(fixed.chapters) and 1 <= f.beat <= len(fixed.chapters[f.chapter - 1].beats):
            old = fixed.chapters[f.chapter - 1].beats[f.beat - 1]
            fixed.chapters[f.chapter - 1].beats[f.beat - 1] = LBeat(narration=f.narration, visual=f.visual,
                                                                    sounds=old.sounds)
            changed.add((f.chapter, f.beat))
    log.info("Fixed %d line(s): %s", len(changed), ", ".join(f"{c}.{b}" if c else f"H{b}" for c, b in sorted(changed)))
    return fixed, changed


def narration_words(script: LongScript) -> int:
    return sum(len(b.narration.split()) for c in script.chapters for b in c.beats)


LENGTH_FIX = ("For the length: shorten (or lengthen) the longest (or shortest) lines by a few words each, "
              "keeping every fact and the story; change as few lines as needed.")
GLOBAL_ISSUES = ("Narration is", "chapters; use", "The hook has")  # need a real rewrite; the rest is line-level


def repair_long_script(script: LongScript) -> LongScript:
    """Fix line-level rule breaks in code, without a Claude call: a 4-word keyword becomes a title
    (titles allow 6 words), surplus items/actors are trimmed, a hook word slam over 3 words is
    dropped. A whole rewrite for one word cost ~500k tokens."""
    s = script.model_copy(deep=True)
    limits = {"timeline": 5, "compare": 2, "steps": 4, "chart": 6}

    def fix(v: LVisual) -> None:
        if v.type == "keyword" and len(v.headline.split()) > 3:
            v.type = "title"
        if v.type == "title" and len(v.headline.split()) > 6:
            v.headline = " ".join(v.headline.split()[:6])
        if v.type in limits and len(v.items) > limits[v.type]:
            v.items = v.items[:limits[v.type]]
        if v.type == "scene" and len(v.actors) > 4:
            v.actors = v.actors[:4]
        if v.type == "scene" and not v.actors and v.icons:
            v.type = "icons"

    for h in s.hook:
        fix(h.visual)
        if len(h.text.split()) > 3:
            h.text = ""
    for c in s.chapters:
        for b in c.beats:
            fix(b.visual)
    return s


def check_long_script(script: LongScript, minutes: float) -> VerifyResult:
    result = VerifyResult()
    words = narration_words(script)
    target = minutes * 60 * WORDS_PER_SECOND
    result.checks["word_count"] = words
    if not target * 0.85 <= words <= target * 1.15:
        result.fail(f"Narration is {words} words; write about {int(target)} for {minutes:g} minutes.")
    if not 5 <= len(script.chapters) <= 9:
        result.fail(f"{len(script.chapters)} chapters; use 6 to 8.")
    lowered = " ".join(b.narration for c in script.chapters for b in c.beats).lower()
    found = [p for p in AI_CLICHES if re.search(rf"\b{re.escape(p)}\b", lowered)]
    if found:
        result.fail(f"Uses AI-sounding phrases: {', '.join(found)}.")
    first = script.chapters[0].beats[0].narration if script.chapters and script.chapters[0].beats else ""
    hook = re.split(r"(?<=[.?!])\s", first.strip(), maxsplit=1)[0]
    result.checks["hook"] = hook
    if len(hook.split()) > 14:
        result.fail(f"The opening sentence is {len(hook.split())} words ('{hook}'); make the hook 12 words or fewer.")
    # The hook: a 25-30 s trailer of 6-9 shots with short lines.
    if not 6 <= len(script.hook) <= 9:
        result.fail(f"The hook has {len(script.hook)} shots; write 6-9 (curiosity, unexpected, tension, problem, gap).")
    hook_words = sum(len(h.line.split()) for h in script.hook)
    result.checks["hook_words"] = hook_words
    if hook_words > 62:
        result.fail(f"The hook's lines have {hook_words} words; keep them under 62 so the hook stays within 30 seconds.")
    for hi, h in enumerate(script.hook, 1):
        if len(h.line.split()) > 13:
            result.fail(f"Hook shot {hi}: the line is {len(h.line.split())} words; trailer lines are 3-12 words.")
        if len(h.text.split()) > 3:
            result.fail(f"Hook shot {hi}: on-screen text '{h.text}' is more than 3 words.")
    # Show, don't write: few text-only beats, never two in a row.
    all_beats = [b for c in script.chapters for b in c.beats]
    texty = [b.visual.type in TEXT_TYPES for b in all_beats]
    result.checks["text_beats"] = f"{sum(texty)}/{len(texty)}"
    if texty and sum(texty) > len(texty) / 7 + 1:
        result.fail(f"{sum(texty)} of {len(texty)} beats are keyword/title slides; at most 1 in 7. Show the idea with "
                    "scene, icons, stat, chart, timeline, compare, steps, footage or 3D instead.")
    if any(a and b for a, b in zip(texty, texty[1:])):
        result.fail("Two keyword/title slides in a row; put a moving visual between them.")
    for ci, chapter in enumerate(script.chapters, 1):
        for bi, beat in enumerate(chapter.beats, 1):
            v = beat.visual
            if v.type == "keyword" and len(v.headline.split()) > 3:
                result.fail(f"Chapter {ci} beat {bi}: keyword '{v.headline}' is more than 3 words.")
            if v.type == "scene" and not 1 <= len(v.actors) <= 4:
                result.fail(f"Chapter {ci} beat {bi}: a scene needs 1-4 actors, it has {len(v.actors)}.")
            need = {"timeline": (2, 5), "compare": (2, 2), "steps": (2, 4), "chart": (3, 6)}.get(v.type)
            if need and not need[0] <= len(v.items) <= need[1]:
                result.fail(f"Chapter {ci} beat {bi}: a {v.type} needs {need[0]}-{need[1]} items, it has {len(v.items)}.")
    return result


FACT_SYSTEM = """You fact-check scripts for long YouTube documentaries before they are produced. Check every \
factual claim in the narration and in the on-screen visuals (numbers, dates, quotes and who said them). \
Use web search to confirm anything you are not certain of. Flag wrong or outdated facts, numbers that don't \
match sources, quotes you can't verify word for word, invented details or dialogue presented as fact, \
exaggerations, myths stated as fact, and lines that contradict each other. Don't comment on style. Be \
strict: a viewer who knows the subject should find nothing to correct in the comments."""


def _visual_text(v: LVisual) -> str:
    items = "; ".join(f"{i.label} {i.text} {i.display}".strip() for i in v.items)
    return f"[{v.type}: {v.headline}" + (f" | {v.sub}" if v.sub else "") + (f" | {items}" if items else "") + "]"


def fact_check_long(script: LongScript, cfg: Config, only: set | None = None) -> VerifyResult:
    """Check every claim, or with `only`, just the lines marked >> (the ones just corrected):
    the rest was already checked, so it is there as context and not searched again."""
    if only:
        ask_for = ("Fact-check ONLY the lines marked >> (they were just corrected); the other lines were already "
                   "checked and are context. Refer to lines by their numbers (e.g. 3.4, H2).")
    else:
        ask_for = "Fact-check this script, the hook lines (H1...) included. Refer to lines by their numbers (e.g. 3.4, H2)."
    prompt = (f"Topic: {script.topic}\nThe writer's sources: {script.facts_checked}\n{_numbered(script, only)}\n\n{ask_for}")
    check = ask(cfg.ai_backend, cfg.claude_model, FACT_SYSTEM, prompt, FactCheck, allow_web=True, effort=cfg.claude_effort,
                timeout=LLM_TIMEOUT)
    result = VerifyResult()
    result.checks["fact_check"] = check.model_dump()
    for issue in check.blocking_issues:
        result.fail("Fact-check: " + issue)
    return result


# ---------- voice, timeline, props ----------

def _group_words(words: list[dict], max_words: int = 9, pause: float = 0.22) -> list[list[dict]]:
    """Subtitle lines for one beat: up to max_words, breaking where the voice pauses (the
    word timings carry no punctuation, but sentence and comma breaks are audible gaps)."""
    groups, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        gap = words[i + 1]["start"] - w["end"] if i + 1 < len(words) else 0
        left = len(words) - i - 1
        if (len(cur) >= max_words and left > 2) or (gap > pause and len(cur) >= 3):
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    return groups


HOOK_TAIL = 0.8  # the cut into the video: a beat of glitch and black, carried by the trailer's final hit


def _seed(script: LongScript) -> int:
    """Stable per video, so a re-make gets the same music and look."""
    return zlib.crc32((script.topic + script.youtube_title).encode("utf-8")) & 0x7FFFFFFF


def _hook_timing(lengths: list[float | None]) -> list[float]:
    """Shot lengths for the hook: each line plus a breath, silent shots a short hold, and the
    whole hook stretched or tightened into 25-30 s (the cut into the video included)."""
    base = [(ln + 0.45) if ln else 2.0 for ln in lengths]
    floor = [(ln + 0.15) if ln else 1.4 for ln in lengths]
    lo, hi = HOOK_SECONDS[0] - HOOK_TAIL, HOOK_SECONDS[1] - HOOK_TAIL
    total = sum(base)
    if total < lo:  # hold the shots longer
        base = [b * lo / total for b in base]
    elif total > hi:  # tighten the holds, never cutting into a line
        spare = sum(b - f for b, f in zip(base, floor))
        cut = min(spare, total - hi)
        base = [b - (b - f) * (cut / spare if spare else 0) for b, f in zip(base, floor)]
    return [round(b, 3) for b in base]


def _prep_visual(v: dict, cfg: Config, work: Path, index: int, clip_ids: set[int], duration: float) -> dict:
    v = _media_visual(v, cfg, work, index, clip_ids)
    v["icons"] = [i.strip().lower().replace(" ", "-") for i in v.get("icons") or []]
    times = sound_design.actor_times(len(v.get("actors") or []), duration)
    for a, at in zip(v.get("actors") or [], times):
        a["icon"] = a["icon"].strip().lower().replace(" ", "-")
        a["at"] = at
    if v.get("impact"):
        v["impactAt"] = sound_design.impact_time(duration)
    return v


def build_long(script: LongScript, cfg: Config, work: Path, progress: Progress,
               voices: list[list[SceneAudio]] | None = None, look: dict | None = None) -> dict:
    """Record the voice (one take per chapter) and lay out the hook and every beat on the timeline,
    with this video's look, music, ambience and sound design.
    `voices`: recordings to use instead (the user's own voiceover), one list per chapter.
    `look`: the look to keep (a re-make); a new video gets a fresh one."""
    seed = _seed(script)
    new_look = look is None
    look = look or variety.pick_look(cfg, seed)
    beats, chapters, lines, cues, spoken = [], [], [], [], []
    used: dict[str, str] = {}
    clip_ids: set[int] = set()  # never the same stock clip twice

    # The hook: a trailer before the video, with its own lines, look and music.
    hook = {"duration": 0.0, "shots": [], "music": None, "style": ""}
    if script.hook:
        progress("Recording the hook")
        said = [h.line.strip() for h in script.hook]
        takes = iter(synthesize_scenes([x for x in said if x], cfg.long_voice, work / "audio" / "hook",
                                       cfg.tts_engine, cfg.kokoro_voice, cfg.voice_rate) if any(said) else [])
        audios = [next(takes) if x else None for x in said]
        lengths = _hook_timing([media_seconds(a.path) if a else None for a in audios])
        t = 0.0
        for i, (h, sa, d) in enumerate(zip(script.hook, audios, lengths)):
            shot = {"start": round(t, 3), "duration": d, "beat": h.beat, "text": h.text.strip(),
                    "audio": sa.path.relative_to(work).as_posix() if sa else None,
                    "visual": _prep_visual(h.visual.model_dump(), cfg, work, 900 + i, clip_ids, d)}
            if sa:
                lines += _group_words([{"text": w.text, "start": round(t + w.start, 3), "end": round(t + w.end, 3)}
                                       for w in sa.words])
                spoken += [(t + w.start, t + w.end) for w in sa.words]
            hook["shots"].append(shot)
            t += d
        hook["duration"] = round(t + HOOK_TAIL, 3)
        hook["style"] = variety.fresh_trailer(cfg, script.hook_music, seed)
        cuts = [s["start"] for s in hook["shots"][1:]] + [hook["duration"] - 0.05]
        hook["music"] = music.trailer(hook["style"], hook["duration"] - 0.05, cuts, seed,
                                      work / "music" / "hook.wav").relative_to(work).as_posix()

    t = hook["duration"]
    for ci, chapter in enumerate(script.chapters):
        card = CARD_SECONDS if ci > 0 else 0.0
        chapters.append({"index": ci, "title": chapter.title, "start": round(t, 3), "card": card,
                         "intensity": chapter.intensity, "drop": chapter.drop, "ambience": chapter.ambience})
        t += card
        if voices is not None:
            audio = voices[ci]
        else:
            progress(f"Recording voiceover: chapter {ci + 1} of {len(script.chapters)}")
            audio = synthesize_scenes([b.narration for b in chapter.beats], cfg.long_voice, work / "audio" / f"ch{ci:02d}",
                                      cfg.tts_engine, cfg.kokoro_voice, cfg.voice_rate)
        for beat, sa in zip(chapter.beats, audio):
            duration = media_seconds(sa.path)
            v = _prep_visual(beat.visual.model_dump(), cfg, work, len(beats), clip_ids, duration)
            beats.append({"start": round(t, 3), "duration": round(duration, 3), "chapter": ci,
                          "audio": sa.path.relative_to(work).as_posix(), "visual": v})
            lines += _group_words([{"text": w.text, "start": round(t + w.start, 3), "end": round(t + w.end, 3)}
                                   for w in sa.words])
            spoken += [(t + w.start, t + w.end) for w in sa.words]
            cues += media.resolve_cues(beat.sounds, sa.words, t, cfg, work / "sfx",
                                       lambda p: p.relative_to(work).as_posix(),
                                       media.HOOK_CUES if ci == 0 else 1, used)
            t += duration
        chapters[-1]["end"] = round(t + CHAPTER_GAP, 3)
        t += CHAPTER_GAP
    captions = []
    for g in lines:
        captions.append({"start": g[0]["start"], "end": round(g[-1]["end"] + 0.25, 3), "words": g})
    for a, b in zip(captions, captions[1:]):  # never two subtitle lines at once
        a["end"] = min(a["end"], b["start"])

    # Music: the user's own track if Claude picked one, else composed for this story's mood,
    # following each chapter's intensity. It starts where the hook ends.
    progress("Composing the music")
    main_start = hook["duration"]
    track = None
    if script.music and script.music != "none" and any(m.name == script.music and m.path for m in media.music(cfg)):
        track = media.pick_music(cfg, script.music, work / "music", t - main_start)
    if track is None and script.music != "none":
        sections = [music.Section(c["start"] - main_start, c["end"] - main_start, (c["intensity"] - 1) / 4,
                                  bool(c["drop"])) for c in chapters]
        track = music.compose(script.mood, sections, t - main_start, seed, work / "music" / "main.wav")
    ambience = []
    for c in chapters:
        if c["ambience"] != "none":
            bed = music.ambience(c["ambience"], c["end"] - c["start"], seed + c["index"],
                                 work / "music" / f"ambience{c['index']:02d}.wav")
            if bed:
                ambience.append({"src": bed.relative_to(work).as_posix(), "from": c["start"], "to": c["end"]})

    sfx = write_sfx(work / "sfx")
    props = {
        "title": script.youtube_title,
        "fps": cfg.fps,
        "duration": round(t, 3),
        "look": look,
        "hook": hook,
        "chapters": chapters,
        "beats": beats,
        "captions": captions if cfg.captions else [],  # off: the visuals use the space instead
        "all_captions": captions,  # kept either way, so subtitles can be switched later without re-recording
        "music": track.relative_to(work).as_posix() if track else None,
        "musicFrom": main_start,
        "ambience": ambience,
        "sfx": {k: p.relative_to(work).as_posix() for k, p in sfx.items()},
        "cues": cues,
        "speech": media.speech_spans(spoken),
        "currency": currency_of(script),
    }
    # Sound for every visual action, on top of Claude's word cues.
    auto = sound_design.design(props, look["transition"])
    extra = write_cue_sounds(work / "sfx", {n for n, _, _ in auto} - set(sfx))
    files = {**{k: p.relative_to(work).as_posix() for k, p in sfx.items()},
             **{k: p.relative_to(work).as_posix() for k, p in extra.items()}}
    props["cues"] = cues + [{"src": files[n], "at": at, "volume": vol, "name": n} for n, at, vol in auto if n in files]
    if new_look:
        variety.remember(cfg, look, script.mood, hook["style"])
    return props


def _media_visual(v: dict, cfg: Config, work: Path, index: int, used: set[int]) -> dict:
    """Fetch a footage beat's clip or copy a model3d beat's model into the render folder.
    Without one (no Pexels key, no matching clip, no real model) the beat becomes an animated scene."""
    if v["type"] == "footage":
        clip = None
        if cfg.pexels_api_key and v.get("query"):
            (work / "footage").mkdir(parents=True, exist_ok=True)
            try:
                clip = pexels_video(v["query"], cfg.pexels_api_key, work / "footage" / f"beat{index:03d}.mp4",
                                    used, min_height=1080, landscape=True)
            except Exception as exc:
                log.warning("Pexels failed for %r: %s", v["query"], exc)
        if clip:
            v.update(src=clip.relative_to(work).as_posix(), length=round(media_seconds(clip), 3))
            return v
    elif v["type"] == "model3d":
        path = find_model(cfg, v.get("model", ""), v.get("search", ""), work / "models")
        if path is not None:
            v["src"] = path.relative_to(work).as_posix()
            v["parts"] = []
            return v
        # Nothing real to show: an object built from primitive shapes read as a grey pile of
        # cylinders (review of the Budget video), so it becomes an icon actor acting the line out.
        v["type"] = "scene"
        name = (v.get("model") or v.get("search") or "box").strip().lower().replace(" ", "-")
        v["actors"] = [{"icon": name, "action": "rise" if v.get("scene") != "space" else "orbit",
                        "label": v.get("headline", "")[:24]}]
        v["headline"] = ""
        v["parts"] = []
        return v
    else:
        return v
    if v["type"] == "footage":  # no clip (no Pexels key or no match): a small animated place scene, never a bare name
        v["type"] = "scene"
        v["actors"] = [{"icon": "building-2", "action": "rise", "label": ""},
                       {"icon": "map-pin", "action": "drop-in", "label": v.get("headline", "")[:20]}]
        v["headline"] = ""
        return v
    v["type"] = "title" if v.get("headline") else "keyword"
    v["headline"] = v.get("headline") or (v.get("model") or "").split(" ")[0].title()
    return v



def currency_of(script: LongScript) -> str:
    """The money the story is about, so the editor's money icons show ₹/€/£ instead of $."""
    text = " ".join([h.line for h in script.hook] + [b.narration + " " + b.visual.headline
                                                      for c in script.chapters for b in c.beats]).lower()
    counts = {"rupee": text.count("₹") + len(re.findall(r"\brupees?\b|\blakh\b|\bcrore\b", text)),
              "euro": text.count("€") + len(re.findall(r"\beuros?\b", text)),
              "pound": text.count("£") + len(re.findall(r"\bpounds? sterling\b|\bsterling\b", text)),
              "dollar": text.count("$") + len(re.findall(r"\bdollars?\b", text))}
    best = max(counts, key=counts.get)
    return best if counts[best] >= 2 and best != "dollar" else ""


def youtube_chapters(props: dict) -> str:
    def stamp(s: float) -> str:
        s = int(s)
        return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"
    # YouTube needs the first chapter at 0:00; the hook plays inside the intro.
    return "\n".join(f"{stamp(0 if i == 0 else c['start'])} {c['title']}" for i, c in enumerate(props["chapters"]))


# ---------- checks and review ----------

def check_long_video(video: Path) -> VerifyResult:
    result = VerifyResult()
    if not video.exists() or video.stat().st_size < 500_000:
        result.fail("Video file missing or empty.")
        return result
    info = probe(video)
    result.checks["probe"] = info
    if (info.get("width"), info.get("height")) != (WIDTH, HEIGHT):
        result.fail(f"Resolution is {info.get('width')}x{info.get('height')}, expected {WIDTH}x{HEIGHT}.")
    minutes = info.get("duration", 0) / 60
    if not MIN_MINUTES <= minutes <= MAX_MINUTES:
        result.fail(f"Video is {minutes:.1f} minutes; it should be 8 to 10.")
    if not info.get("has_audio"):
        result.fail("No audio track.")
    result.checks["size_mb"] = round(video.stat().st_size / 1e6, 1)
    return result


def contact_sheet_long(video: Path, out: Path, props: dict) -> Path:
    """Two frames from every chapter (a third and two thirds in), 4 per row."""
    hook = props.get("hook") or {}
    times = [hook["duration"] * 0.3, hook["duration"] * 0.75] if hook.get("shots") else []  # the hook first
    for i, c in enumerate(props["chapters"]):
        end = props["chapters"][i + 1]["start"] if i + 1 < len(props["chapters"]) else props["duration"]
        body = c["start"] + c["card"]
        times += [body + (end - body) * 0.33, body + (end - body) * 0.7]
    tiles = []
    for k, t in enumerate(times):
        tile = out.with_name(f"_frame{k}.jpg")
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
                        "-vf", "scale=480:270", str(tile)], check=False)
        if tile.exists():
            tiles.append(Image.open(tile).convert("RGB"))
            tile.unlink()
    rows = (len(tiles) + 3) // 4
    sheet = Image.new("RGB", (480 * 4, 270 * max(rows, 1)), "black")
    for k, tile in enumerate(tiles):
        sheet.paste(tile, ((k % 4) * 480, (k // 4) * 270))
    sheet.save(out, quality=85)
    return out


LONG_REVIEW_SYSTEM = """You are a strict YouTube editor reviewing an 8-10 minute fully animated video before \
it is posted. You judge whether viewers would stay to the end: a cold open that plants one big question, \
chapters that each open with a mini-hook and end on an open loop, one subject explored in depth rather than \
a list, a twist near the middle and a payoff that answers the opening question. It opens with a 25-30 \
second cinematic hook (a trailer: curiosity, the unexpected, tension, part of the problem, a curiosity gap) \
that must not give the answer away. The story should be told by motion, camera and sound, with text only \
supporting it: a video that is mostly big words on backgrounds is a slideshow and fails. You also check \
that each animated visual matches its line and that nothing is inaccurate, exaggerated or unverifiable. \
Be honest and specific; don't pass mediocre work."""


def review_long(video: Path, script: LongScript, props: dict, cfg: Config) -> tuple[Review, VerifyResult]:
    sheet = contact_sheet_long(video, video.with_name("review_frames.jpg"), props)
    lines = []
    for ci, c in enumerate(script.chapters, 1):
        lines.append(f"\nChapter {ci}: {c.title}")
        lines += [f"{ci}.{bi} {b.narration}  {_visual_text(b.visual)}" for bi, b in enumerate(c.beats, 1)]
    hook_lines = " / ".join(f"[{h.beat}] {h.line or '(no line)'} {_visual_text(h.visual)}" for h in script.hook)
    prompt = (f"The image shows two frames from the hook, then two frames from every chapter, left to right, top to "
              f"bottom.\n\nHook: {hook_lines}\n"
              f"Title: {script.youtube_title}\nThe big question: {script.hook_question}\n"
              f"Style: {'fiction story' if cfg.video_style == 'story' else 'true story, fact-checked'}\n"
              + "\n".join(lines) + "\n\nScore it and list what to fix. For 'visuals_match', judge the animated "
              "visuals against their lines. For 'story', judge retention across the whole video.")
    review = ask(cfg.ai_backend, cfg.claude_model, LONG_REVIEW_SYSTEM, prompt, Review, images=[sheet],
                 effort=cfg.claude_effort, timeout=LLM_TIMEOUT)
    result = VerifyResult()
    scores = [review.human_feel, review.hook, review.visuals_match, review.accuracy, review.story]
    result.score = round(sum(scores) / len(scores), 1)
    result.checks["review"] = review.model_dump()
    if review.blocking_issues:
        for issue in review.blocking_issues:
            result.fail("Reviewer: " + issue)
    elif min(scores) < 6 or result.score < 7 or review.hook < 7:
        result.fail("Reviewer: " + "; ".join(review.issues or ["scores too low"]))
    return review, result


# ---------- post text ----------

POST_SYSTEM = """You are a YouTube SEO specialist for a documentary channel. Your job is the text that makes \
YouTube recommend a finished long video and makes searchers click it, without misleading anyone.

Research first (web search): what people actually search for this subject (YouTube and Google autocomplete \
style phrases, "how/why/what" questions, the names and terms they use), which titles of the videos ranking \
for it now look like, and which hashtags are really used for it. Build everything around one main keyword \
(the phrase with the most search intent that the video truly answers) and 3-5 related phrases.

Rules YouTube's ranking rewards:
- Title: the main keyword in the first 40 characters, then the curiosity or promise that earns the click. \
50-70 characters. Specific beats vague (names, numbers, places). No clickbait the video doesn't pay off, no \
ALL CAPS, at most one emoji (usually none).
- Description: the first 150 characters decide the search snippet and the "more" click, so they hold the \
main keyword and the hook. Then 150-300 words in natural sentences that use the related phrases the way a \
person would, never a keyword list (stuffing gets a video demoted). Then one line inviting viewers to \
subscribe and to comment an answer to a question from the video, which drives engagement.
- Hashtags: 3 that people really follow for this subject (they show above the title), main one first.
- Tags: 15-25, main keyword first, then close variants, then broader topic phrases, then long-tail \
questions. Under 500 characters in total.

Keep every fact identical to the script. Never promise what the video doesn't deliver."""


class LongPost(BaseModel):
    main_keyword: str = Field(description="The one search phrase the video is optimised for, e.g. 'history of penicillin'.")
    youtube_title: str = Field(description="50-70 characters, the main keyword in the first 40, then the curiosity or promise. No hashtags, no '#shorts', no ALL CAPS.")
    youtube_description: str = Field(description="First 150 characters: the main keyword plus the hook (this is the search snippet). Then 150-300 words of natural sentences that use the related search phrases, covering what the video explores without giving the answer away. End with one line inviting viewers to subscribe and to comment an answer to a question from the video. No hashtags, no chapter list, no keyword lists.")
    youtube_hashtags: list[str] = Field(description="Exactly 3 hashtags without '#', really used for this subject, main one first (they show above the title). Never 'shorts'.")
    youtube_tags: list[str] = Field(description="15-25 tags without '#', main keyword first, then close variants, broader topic phrases and long-tail questions people search. Under 500 characters in total.")
    hashtag_notes: str = Field(description="One or two sentences: what you searched and why you chose the main keyword, or 'not verified' if you couldn't check.")


def write_long_post(script: LongScript, props: dict, cfg: Config) -> dict:
    """YouTube text only: a long 16:9 video goes on YouTube, not Instagram Reels or Shorts."""
    summary = " ".join(b.narration for c in script.chapters for b in c.beats)[:6000]
    prompt = (f"Topic: {script.topic}\nDraft title: {script.youtube_title}\nThe big question: {script.hook_question}\n"
              f"Chapters: {', '.join(c.title for c in script.chapters)}\n"
              f"Narration (start): {summary}\n\nResearch the search terms, then write the YouTube post text for this long "
              f"{'fiction story' if cfg.video_style == 'story' else 'documentary'} video.")
    post = ask(cfg.ai_backend, cfg.claude_model, POST_SYSTEM, prompt, LongPost, allow_web=True, effort=cfg.claude_effort)
    return {
        "caption": "",
        "hashtags": [],
        "youtube_title": post.youtube_title,
        "youtube_description": post.youtube_description.strip() + "\n\nChapters:\n" + youtube_chapters(props),
        "youtube_hashtags": [t for t in clean_tags(post.youtube_hashtags) if t.lower() != "shorts"],
        "youtube_tags": _fit_tags(post.youtube_tags),
        "hashtag_notes": f"Main keyword: {post.main_keyword}. {post.hashtag_notes}",
    }


def _fit_tags(tags: list[str], limit: int = 500) -> list[str]:
    """YouTube rejects more than 500 characters of tags (commas count; a tag with spaces counts its quotes)."""
    out, used = [], 0
    for t in (t.strip().lstrip("#") for t in tags):
        cost = len(t) + (2 if " " in t else 0) + (1 if out else 0)
        if t and t.lower() not in {o.lower() for o in out} and used + cost <= limit:
            out.append(t)
            used += cost
    return out


# ---------- the run ----------

def run_long(cfg: Config, topic: str | None = None, progress: Progress = log.info) -> dict:
    """Make one long video. Returns its report (the same shape the app reads for Shorts)."""
    from .pipeline import _claimed, _history_lock, _render_slot, _topic_lock, slugify

    minutes = cfg.long_minutes
    history_path = cfg.output_dir / "history.json"
    progress("Finding trending topics")
    if topic:
        candidates = [Trend(title=topic, source="manual")]
    else:
        with _topic_lock:
            with _history_lock:
                used = load_history(history_path)
            candidates = collect_trends(cfg.geo, used + sorted(_claimed))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    work = cfg.output_dir / f"{stamp}-{uuid.uuid4().hex[:4]}-long-working"
    work.mkdir(parents=True, exist_ok=True)
    progress(f"Saving progress in {work.name}")  # lets a failed job resume from here
    return _long_loop(cfg, work, candidates, topic, stamp, progress)


def resume_long(cfg: Config, work: Path, state: dict, progress: Progress) -> dict:
    from dataclasses import replace

    cfg = replace(cfg, video_style=state.get("style", cfg.video_style))
    progress(f"Resuming {work.name}")
    progress(f"Saving progress in {work.name}")
    return _long_loop(cfg, work, [Trend(**c) for c in state.get("candidates", [])], state.get("topic"),
                      state["stamp"], progress, resume=state)


def _enc_long_best(best: dict | None) -> dict | None:
    return None if best is None else {"script": best["script"].model_dump(), "verdict": asdict(best["verdict"]),
                                      "props": best["props"], "attempt": best["attempt"], "file": str(best["file"])}


def _dec_long_best(d: dict | None) -> dict | None:
    return None if not d else {"script": LongScript.model_validate(d["script"]), "verdict": VerifyResult(**d["verdict"]),
                               "props": d["props"], "attempt": d["attempt"], "file": Path(d["file"])}


def _long_loop(cfg: Config, work: Path, candidates: list, topic: str | None, stamp: str, progress: Progress,
               resume: dict | None = None) -> dict:
    """The attempt loop for one long video. Saves checkpoint.json after the script, the
    voice and every render, so a stopped video can carry on instead of starting again."""
    from .pipeline import CHECKPOINT, STAGE_DONE, _history_lock, _render_slot, pause_point, slugify

    resume = resume or {}
    # The length it was written for: a resume under other settings must not call it too long or short.
    minutes = resume.get("minutes") or cfg.long_minutes
    history_path = cfg.output_dir / "history.json"
    feedback = resume.get("feedback", "")
    script = LongScript.model_validate(resume["script"]) if resume.get("script") else None
    open_facts: list[str] = resume.get("open_facts", [])
    best = _dec_long_best(resume.get("best"))
    start = resume.get("attempt", 1)
    meter_add_earlier(resume.get("usage"))
    state = {"length": "long", "minutes": minutes, "topic": topic, "stamp": stamp, "style": cfg.video_style,
             "candidates": [asdict(c) for c in candidates], "best": resume.get("best")}

    def save(**changes) -> None:
        state.update(changes, usage=meter_records())
        (work / CHECKPOINT).write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        pause_point()

    try:
        revise: dict | None = None  # set after a failed review: fix those lines next round
        for attempt in range(start, LONG_ATTEMPTS + 1):
            tag = f"[attempt {attempt}/{LONG_ATTEMPTS}]"
            stage = resume.get("stage") if attempt == start else None
            changed: set | None = None  # None = check everything; a set = only the lines just corrected
            checked_all = False  # has the whole script been fact-checked once?
            if stage == "revise":  # resumed after a failed review
                revise = {"issues": resume.get("review_issues") or [feedback], "fix": resume.get("review_fix", "")}
                stage = None
            if revise:
                # A failed review revises the flagged lines instead of writing a new script: a rewrite
                # costs ~1.5M tokens and brings new errors; the facts already checked stay checked.
                progress(f"{tag} Revising the lines the reviewer flagged (keeping the rest of the script)")
                script, changed = fix_long_script(script, cfg, revise["issues"], revise["fix"])
                checked_all, revise = True, None
            elif stage:
                progress(f"{tag} Resuming: {STAGE_DONE.get(stage, stage)} already done")
            else:
                progress(f"{tag} Claude is picking the topic and writing the script (long video, a few minutes)")
                script = write_long_script(cfg, candidates, minutes, feedback, script if feedback else None)
            for fix in range(0 if stage else FACT_FIXES + 2):
                script = repair_long_script(script)  # free fixes first
                basic = check_long_script(script, minutes)
                checking = basic.passed and cfg.video_style != "story"
                if checking:
                    progress(f"{tag} Claude is fact-checking the " + ("script" if not checked_all or changed is None
                                                                       else f"{len(changed)} corrected line(s)"))
                facts = fact_check_long(script, cfg, changed if checked_all else None) if checking else VerifyResult()
                checked_all = checked_all or checking
                if basic.passed and facts.passed:
                    break
                problems = basic.issues + facts.issues
                if fix == FACT_FIXES + 1 or (not basic.passed and fix == FACT_FIXES):  # 2 rewrites for structure
                    progress(f"{tag} Still has problems after the strict fix: {'; '.join(problems)}")
                    break
                fixes = facts.checks.get("fact_check", {}).get("fix_instructions", "")
                whole = [p for p in basic.issues if p.startswith(GLOBAL_ISSUES)]
                if changed is not None and all(p.startswith("Narration is") for p in whole):
                    # Corrected lines pushed the length off: trim or extend lines, never write it again.
                    whole = []
                    fixes = (fixes + " " if fixes else "") + LENGTH_FIX
                if whole:  # length, chapters or hook size is off: that needs a real rewrite (and a full check)
                    progress(f"{tag} Rewriting the script: {'; '.join(problems)}")
                    script = write_long_script(cfg, candidates, minutes, "\n".join(problems + ([fixes] if fixes else [])), script)
                    changed, checked_all = None, False
                else:  # line-level: correct just those lines, never the whole script
                    strict = basic.passed and fix >= FACT_FIXES
                    progress(f"{tag} {'Removing what the sources do not all confirm' if strict else 'Fixing the script'}: "
                             f"{'; '.join(problems)}")
                    script, now = fix_long_script(script, cfg, basic.issues + facts.issues, fixes, strict=strict)
                    changed = (changed or set()) | now if not basic.passed else now
                    if not now:  # nothing was changed: another check would find the same
                        break
            if not stage:  # claims still disputed after the strict fix: the video must be checked by hand
                open_facts = [] if facts.passed else list(facts.issues)
            # Only a script whose structure is still wrong starts over; facts are fixed in place.
            if not stage and not basic.passed and attempt < LONG_ATTEMPTS:
                feedback = "\n".join(problems)
                save(attempt=attempt + 1, stage=None, feedback=feedback, script=script.model_dump())
                continue
            if not stage:
                save(attempt=attempt, stage="scripted", script=script.model_dump(), feedback=feedback,
                     open_facts=open_facts)

            if stage in ("voiced", "rendered") and not all(
                    (work / b["audio"]).exists() for b in resume["props"]["beats"] if b.get("audio")):
                progress(f"{tag} The saved voiceover files are gone; recording it again")
                stage = "scripted"
            if stage in ("voiced", "rendered"):
                props = resume["props"]
            else:
                for old in ("audio", "sfx"):
                    shutil.rmtree(work / old, ignore_errors=True)
                props = build_long(script, cfg, work, progress)
                save(stage="voiced", props=props)
            progress(f"{tag} Editing the video ({props['duration'] / 60:.1f} min of animation; this takes a while)")
            cli = _remotion_cli()
            if cli is None:
                raise RuntimeError("Node.js or the Remotion packages are not installed (run start.bat / start.sh)")
            out = work / "reel.mp4"
            if stage == "rendered" and out.exists():
                pass  # the edit finished before it stopped
            else:
                with _render_slot(cfg):
                    _render_remotion(cli, props, out, composition="Long", crf=18, timeout=4 * 3600)
                save(stage="rendered")
            subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", "3", "-i", str(out), "-frames:v", "1",
                            "-q:v", "3", str(work / "thumbnail.jpg")], check=False)

            progress(f"{tag} Verifying video quality")
            verdict = check_long_video(out)
            if verdict.passed:
                progress(f"{tag} Claude is reviewing the finished video")
                _, review = review_long(out, script, props, cfg)
                verdict.checks.update(review.checks)
                verdict.score = review.score
                if not review.passed:
                    verdict.passed = False
                    verdict.issues += review.issues
            # Keep each rendered attempt; the best one (passed, then highest score) becomes reel.mp4.
            kept = work / f"attempt{attempt}.mp4"
            move(out, kept)
            shutil.copy(work / "thumbnail.jpg", work / f"attempt{attempt}.jpg")
            this = {"script": script, "verdict": verdict, "props": props, "attempt": attempt, "file": kept}
            if best is None or (verdict.passed, verdict.score or 0) > (best["verdict"].passed, best["verdict"].score or 0):
                best = this
            save(best=_enc_long_best(best))
            if verdict.passed:
                progress(f"{tag} Passed verification (score {verdict.score})")
                break
            progress(f"{tag} Failed verification: {'; '.join(verdict.issues)}")
            review_fix = verdict.checks.get("review", {}).get("fix_instructions", "")
            feedback = "\n".join(verdict.issues + ([review_fix] if review_fix else []))
            revise = {"issues": list(verdict.issues), "fix": review_fix}
            save(attempt=attempt + 1, stage="revise", feedback=feedback, script=script.model_dump(),
                 review_issues=list(verdict.issues), review_fix=review_fix)

        if best is None:
            raise RuntimeError(f"No usable long script after {LONG_ATTEMPTS} attempts: {feedback}")
        script, verdict, props = best["script"], best["verdict"], best["props"]
        move(best["file"], work / "reel.mp4")
        (work / f"attempt{best['attempt']}.jpg").replace(work / "thumbnail.jpg")
        for scratch in [*work.glob("attempt*.mp4"), *work.glob("attempt*.jpg")]:
            scratch.unlink(missing_ok=True)
        (work / "props.json").write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
        final_dir = cfg.output_dir / f"{stamp}-{slugify(script.topic)}-long"
        move(work, final_dir)
        (final_dir / CHECKPOINT).unlink(missing_ok=True)
        (final_dir / "script.json").write_text(script.model_dump_json(indent=2), encoding="utf-8")
        report = {
            "id": final_dir.name,
            "format": "long",
            "topic": script.topic,
            "topic_source": candidates[0].source if topic else next(
                (c.source for c in candidates if c.title.lower() == script.topic.lower()), "unknown"),
            "style": cfg.video_style,
            "category": script.category,
            "voice": cfg.long_voice,
            "captions": cfg.captions,
            "why_chosen": script.why_chosen,
            "title": script.youtube_title,
            "subject": script.subject,
            "hook_question": script.hook_question,
            "narration": " ".join(b.narration for c in script.chapters for b in c.beats),
            "facts_checked": script.facts_checked,
            "chapters": [{"title": c["title"], "start": c["start"]} for c in props["chapters"]],
            "created_at": stamp,
            "verified": verdict.passed and not open_facts,
            "score": verdict.score,
            "issues": verdict.issues + [f"Unconfirmed after fact-checking, check before posting: {x}" for x in open_facts],
            "checks": verdict.checks,
            "attempts": best["attempt"],
            "video": str(final_dir / "reel.mp4"),
            "thumbnail": str(final_dir / "thumbnail.jpg"),
            "duration_seconds": round(props["duration"], 1),
            "editor": "remotion (Long)",
        }
        progress("Claude is writing the title, description, chapters and tags")
        try:
            report.update(write_long_post(script, props, cfg))
        except Exception as exc:
            log.warning("Post text step failed: %s", exc)
            report.update({"caption": "", "hashtags": [], "youtube_title": script.youtube_title,
                           "youtube_description": "Chapters:\n" + youtube_chapters(props), "youtube_hashtags": [],
                           "youtube_tags": [], "post_text_error": str(exc)[:300]})
        save_post_text(report, final_dir)
        report["usage"] = summarize_usage(meter_records())
        (final_dir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        with _history_lock:
            save_history(history_path, script.topic)
        progress("Done" if report["verified"] else "Done, but it did not pass every check — review before posting")
        return report
    except Exception:
        # Keep the folder when it has a checkpoint: the video can be resumed from there.
        if work.exists() and not (work / CHECKPOINT).exists():
            shutil.rmtree(work, ignore_errors=True)
        raise


def run_long_batch(cfg: Config, count: int, topic: str | None, progress: Progress) -> list[dict]:
    """Several long videos, one after another (each takes the shared video slot). Jokes
    don't suit 8 minutes, so 'comedy' becomes a true story; 'mix' alternates true and fiction."""
    from dataclasses import replace

    from .llm import set_limit_reporter
    from .pipeline import Paused, _video_slot, done_line, set_pause_check

    reports = []
    should_pause = getattr(progress, "should_pause", None)
    for i in range(count):
        style = {"comedy": "facts", "mix": ("facts", "story")[i % 2]}.get(cfg.video_style, cfg.video_style)
        vp = (lambda m, n=i + 1: progress(f"[V{n}] {m}")) if count > 1 else progress
        with _video_slot(cfg):
            if should_pause and should_pause():
                progress((f"[V{i + 1}] " if count > 1 else "") + "§skip {}")
                continue
            set_pause_check(should_pause)
            set_limit_reporter(vp)
            start_meter(lambda r, vp=vp: vp(usage_line(r)))
            vp(f"=== Video {i + 1}/{count} ===")
            try:
                reports.append(run_long(replace(cfg, video_style=style), topic, vp))
                vp(done_line(reports[-1]))
            except Paused:
                vp("Paused: progress saved. Press Resume to carry on from here.")
            except Exception as exc:
                log.exception("Long video %d failed", i + 1)
                vp(f"Video {i + 1} failed: {exc}")
    return reports
