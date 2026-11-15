"""The Journey's story: one subject, one real place, its stages in their true order, two lines of text.

Claude writes it (`write`), the fact-check model checks every stage against real sources (`check`: the order, how it
looks, how long it really takes), and `repair` keeps the timing and the sounds inside what the rest of the pipeline
can make. Never the same subject twice (`<output>/journey_history.json`)."""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from ..config import Config
from ..llm import ask

log = logging.getLogger(__name__)

# sound.py's recordings: beds play under a whole stage, spots on a moment of it
BED_NAMES = ("birds-morning", "birds-forest", "birds-park", "stream", "rain", "storm", "crickets", "traffic", "engine",
             "leaves", "wind", "bee")
SPOT_NAMES = ("thunder", "squish", "crunch")
SoundName = Literal["birds-morning", "birds-forest", "birds-park", "stream", "rain", "storm", "crickets", "traffic",
                    "engine", "leaves", "wind", "bee", "thunder", "squish", "crunch"]
LightName = Literal["dawn", "morning", "midday", "golden", "overcast", "storm", "rain", "dusk", "night"]
CATEGORY = Literal["Nature & Animals", "Science & Space", "Weather", "Life & People"]


class JSound(BaseModel):
    name: SoundName
    at: float = Field(0.0, description="spots only: when it happens, as a fraction 0-1 of the stage (a landing at 0.7)")
    volume: float = Field(1.0, description="0.3-1.5; 1 = as recorded (beds a little under, spots clear)")


class JStage(BaseModel):
    what: str = Field(description="What the viewer sees in this stage, concrete and true to life, one sentence")
    elapsed: str = Field(description="Real time since the start when this stage is reached: 'day 0', 'day 9', 'week 7'")
    fact: str = Field(description="The real-world basis for this stage (biology, physics, weather), one sentence a "
                                  "fact-checker can confirm")
    picture: str = Field(description="The photograph of this stage's END state for the image model, 40-75 words: the "
                                     "subject in this state first (species, colours, shapes, size in frame), then the "
                                     "place and camera words copied exactly from `place` and `camera`, then the light. "
                                     "Only what is visible: no 'the same', no history, no time words")
    change: Literal["small", "medium", "large"] = Field(description="How much the picture differs from the stage before "
                                                                    "(small = a little wrinkling, large = a plant where "
                                                                    "there were seeds)")
    size: float = Field(0.3, description="How tall the subject stands in this stage, as a fraction of the picture's "
                                         "height (a fallen fruit 0.15-0.3, a seedling 0.3-0.5, a grown plant 0.6-0.9)")
    keeps: bool = Field(False, description="True when the original subject is still there in this stage, with "
                                           "something growing out of it (a palm shoot from the coconut); false when it "
                                           "has changed itself or is gone (the tomato rotted into the soil)")
    cut: bool = Field(False, description="True only for a new camera set-up (stage 1's wide event shot -> the close "
                                         "ground camera); every other stage continues the same shot")
    motion: str = Field(description="What moves during this stage's clip, for the video model, 15-40 words: a time-lapse "
                                    "of the change, or real-time motion (the truck drives off, the bee lands)")
    timelapse: bool = Field(True, description="True for sped-up time (growth, decay, clouds racing); false for real-time "
                                              "motion (a fall, a vehicle, an animal)")
    light: LightName
    seconds: float = Field(description="How long this stage runs on screen, 3.5-6.5")
    sounds: list[JSound] = Field(default_factory=list, description="1-3: the place's sounds at this moment")


class Journey(BaseModel):
    title: str = Field(description="Short title, 2-5 words")
    subject: str = Field(description="The one thing whose journey this is, with its species: 'a ripe tomato "
                                     "(Solanum lycopersicum)'")
    theme: str = Field(description="The life lesson the journey is a picture of, one sentence")
    place: str = Field(description="The one real place, 25-45 words, concrete: ground, plants, background, region and "
                                   "climate. Copied word for word into every picture")
    camera: str = Field(description="The fixed camera, 10-20 words: height, angle, lens, framing ('low ground-level "
                                    "camera, 35mm lens, shallow depth of field, subject lower centre'). Copied into "
                                    "every picture")
    top_text: str = Field(description="The line above the picture, 3-7 words: the setback ('The fall was just the "
                                      "beginning')")
    bottom_text: str = Field(description="The line under the picture, 3-7 words: the turn ('Rock bottom is fertile "
                                         "ground')")
    stages: list[JStage]
    youtube_title: str = Field(description="YouTube Shorts title, under 70 characters, ending with #shorts")
    description: str = Field(description="2-4 sentences: what really happens in the video and the lesson, plain words")
    tags: list[str] = Field(description="8-14 search tags")
    hashtags: list[str] = Field(description="3-5 hashtags with #")
    category: CATEGORY = "Nature & Animals"
    thumbnail_text: str = Field("", description="2-4 words for a thumbnail")


RULES = """You write a photoreal time-lapse Short with no narration and no music: one thing's journey through time in one
real place, as if a camera had been left on the ground and recorded it for weeks. It is a picture of a life lesson: a
setback that turns out to be a beginning. The model for it (learn from it, never copy it): a ripe tomato falls off a
truck onto a dirt verge, wrinkles and rots in the sun, splits, the rain washes its seeds into the soil, they sprout,
grow into a plant, it flowers, a bee visits, green fruit, then the plant hangs full of red tomatoes. Text above the
picture: 'The fall was just the beginning'; below: 'Rock bottom is fertile ground'.

REAL AND ACCURATE (the most important rule):
- Only a process that truly happens in nature, in its true order, with true appearances: colours, shapes, parts,
  sizes, the species named. If seeds sprout, the seedlings have the real seed leaves of that species first; flowers
  have the real colour and form; fruit ripens the real way. Nothing magical, nothing faster than the `elapsed` says.
- `elapsed` gives the real time since the start for each stage, and `fact` the real basis a fact-checker can confirm.
  Put realistic times, not rounded myths. The place must suit the subject (climate, season, soil).
- No people's faces; a vehicle or a hand only far or partly in frame, at the start if the story needs it. No animals
  doing human things. Weather only as it really comes (rain from storm clouds, a wet ground after).

THE SHOT:
- One `place` and one `camera` for the whole video, copied word for word into every `picture`. The camera never moves
  between stages: only light, weather and the subject change, so the stages join into one continuous time-lapse.
- Stage 1 may be the event that starts it (the fall) in real time, from a wider angle; the next stage then has
  `cut` true and starts the low fixed camera. No other cuts.
- {stages} stages, each 3.5-6.5 seconds, {seconds} seconds in all. Each stage's `picture` shows the state at the END
  of the stage; its `motion` says what changes during it. `change` says how far the picture moves from the stage
  before: keep most steps small or medium so the time-lapse flows; a large step only where the real process jumps.
- The light changes with time as it really would (a storm darkens it, the morning after is bright and wet, nights
  are blue and dark); vary it, but keep most stages in daylight so the subject is clear.
- Pictures are real photographs: natural colours, real textures, shallow depth of field, no text, no frames, no
  watermark, no split screens. The subject in the lower middle, never cut by the edge. Name only what is visible.

THE TWO LINES: `top_text` names the setback, `bottom_text` the turn, 3-7 words each, plain and strong, not a cliché
from a poster ('never give up', 'believe in yourself', 'everything happens for a reason' are banned), and they fit the
pictures exactly. They are the only words on screen.

SOUNDS: per stage 1-3 from the list, true to that moment: birds by day, crickets only at night, rain/storm with rain,
thunder on a flash of a storm, engine only while the vehicle is in the shot, bee only when a bee is in the picture,
squish when soft fruit lands or bursts, crunch for something dry breaking, wind or leaves when plants sway, traffic only
by a road. Names: {names}.
"""


def _recent(cfg: Config) -> list[dict]:
    try:
        return json.loads((cfg.output_dir / "journey_history.json").read_text(encoding="utf-8"))[-60:]
    except (OSError, ValueError):
        return []


def remember(cfg: Config, j: Journey) -> None:
    items = _recent(cfg) + [{"title": j.title, "subject": j.subject, "top": j.top_text, "bottom": j.bottom_text}]
    try:
        (cfg.output_dir / "journey_history.json").write_text(json.dumps(items[-200:], ensure_ascii=False, indent=1),
                                                            encoding="utf-8")
    except OSError:
        pass


def _words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", s.lower()) if len(w) > 3}


def too_close(j: Journey, past: list[dict]) -> str:
    mine = _words(j.subject)
    for p in past:
        theirs = _words(p.get("subject", ""))
        if mine and theirs and len(mine & theirs) / max(1, min(len(mine), len(theirs))) >= 0.5:
            return p.get("subject", "")
        if j.top_text.strip(". ").lower() == str(p.get("top", "")).strip(". ").lower():
            return p.get("top", "")
    return ""


def stage_count(seconds: float) -> int:
    """About one stage every 5 seconds (the reference: 60 s, ten or eleven stages)."""
    return max(5, min(16, round(seconds / 5)))


def write(cfg: Config, idea: str, seconds: float, progress=log.info, top: str = "", bottom: str = "") -> Journey:
    n = stage_count(seconds)
    system = RULES.format(stages=n, seconds=f"{seconds:g}", names=", ".join(BED_NAMES + SPOT_NAMES))
    past = _recent(cfg)
    made = "\n".join(f"- {p['subject']} ({p.get('top', '')})" for p in past[-30:]) or "- none yet"
    ask_for = (f"Make the journey of: {idea.strip()}." if idea.strip() else
               "Choose the subject yourself: a real natural process with a fall and a rebirth that a phone viewer "
               "will watch to the end (a seed, a fruit, an egg, an insect, a forest after a fire, a coral, a river...), "
               "different from the ones already made.")
    if top.strip() or bottom.strip():
        ask_for += (f"\nUse these lines exactly as written: top '{top.strip()}', bottom '{bottom.strip()}'."
                    if top.strip() and bottom.strip() else
                    f"\nUse this line exactly: {'top' if top.strip() else 'bottom'} '{(top or bottom).strip()}'.")
    prompt = f"{ask_for}\n\nJourneys already made (never the same subject or lines again):\n{made}"
    progress(f"Claude is writing the journey ({seconds:g} s, {n} stages{', ' + idea.strip()[:60] if idea.strip() else ''})")
    j = ask(cfg.ai_backend, cfg.claude_model, system, prompt, Journey, allow_web=False, effort=cfg.claude_effort, timeout=1800)
    near = too_close(j, past) if not idea.strip() else ""
    if near:
        progress(f"That subject is too close to '{near}'; writing another one")
        j = ask(cfg.ai_backend, cfg.claude_model, system, prompt + f"\n\nYour first idea was too close to '{near}'. "
                "Choose a different subject.", Journey, allow_web=False, effort=cfg.claude_effort, timeout=1800)
    if top.strip():
        j.top_text = top.strip()
    if bottom.strip():
        j.bottom_text = bottom.strip()
    return j


# ---------- the fact-check: every stage against real sources ----------

class StageCheck(BaseModel):
    stage: int = Field(description="The stage number as listed (1-based)")
    verdict: Literal["confirmed", "wrong"]
    note: str = Field("", description="What a source says, a few words, and the page")
    what: str = Field("", description="wrong only: the corrected `what`")
    elapsed: str = Field("", description="wrong only: the corrected `elapsed`")
    fact: str = Field("", description="wrong only: the corrected `fact`")
    picture: str = Field("", description="wrong only: the corrected `picture`, same rules (subject state first, then the "
                                         "place and camera words unchanged, then the light)")


class JourneyCheck(BaseModel):
    stages: list[StageCheck]
    order_ok: bool = Field(description="True when the stages are in the order the real process goes")
    order_note: str = ""


CHECK_SYSTEM = """You fact-check a wordless nature time-lapse before it is drawn and animated. Each stage says what is
seen, the real time since the start, and the real-world basis. Search the web and open reliable pages (botany,
entomology, university extension services, encyclopaedias). A stage is confirmed only when sources say it really
happens that way: the right appearance (colours, shapes, the plant's or animal's real parts at that age), the right
order, a realistic time. A stage that is roughly right but shows something wrong (wrong flower colour, true leaves
before seed leaves, fruit ripening the wrong colour, a time far off) is 'wrong': give the corrected fields, keeping
the same moment of the journey. Don't flag artistic choices (light, camera, weather) unless they are impossible."""


def _rows(j: Journey, only: set[int] | None = None) -> str:
    return "\n".join(f"{k}{' >>' if only and k in only else ''}. [{s.elapsed}] {s.what} | basis: {s.fact} | picture: {s.picture}"
                     for k, s in enumerate(j.stages, 1))


def _check(cfg: Config, j: Journey, only: set[int] | None = None) -> JourneyCheck:
    prompt = (f"Subject: {j.subject}\nPlace: {j.place}\n"
              + ("Check only the stages marked >> (the rest was confirmed before).\n" if only else "")
              + "\n" + _rows(j, only))
    return ask(cfg.ai_backend, cfg.fact_model, CHECK_SYSTEM, prompt, JourneyCheck, allow_web=True,
               effort=cfg.fact_effort, timeout=1500)


def check(cfg: Config, j: Journey, progress=log.info) -> tuple[Journey, list[str], list[dict]]:
    """Every stage checked; a wrong one gets the checker's correction and one more check; one still not confirmed is
    taken out (its time goes to its neighbours), unless it is the first or last. Returns the journey, the issues left
    and every finding."""
    progress(f"Fact-checking every stage of the journey ({len(j.stages)})")
    found = _check(cfg, j)
    findings = [c.model_dump() for c in found.stages]
    issues = [] if found.order_ok else [f"The order may not be right: {found.order_note}"]
    fixed: set[int] = set()
    for c in found.stages:
        if c.verdict != "wrong" or not 1 <= c.stage <= len(j.stages):
            continue
        s = j.stages[c.stage - 1]
        s.what = c.what.strip() or s.what
        s.elapsed = c.elapsed.strip() or s.elapsed
        s.fact = c.fact.strip() or s.fact
        s.picture = c.picture.strip() or s.picture
        fixed.add(c.stage)
    if fixed:
        progress(f"Corrected {len(fixed)} stage(s) from the sources; checking them again")
        again = _check(cfg, j, only=fixed)
        findings += [{**c.model_dump(), "round": 2} for c in again.stages if c.stage in fixed]
        drop = {c.stage for c in again.stages if c.stage in fixed and c.verdict != "confirmed"}
        drop -= {1, len(j.stages)}
        for k in sorted(drop, reverse=True):
            gone = j.stages.pop(k - 1)
            issues.append(f"Stage {k} ('{gone.what}') could not be confirmed and was left out.")
            if j.stages:  # its time goes to the stage that now covers it
                j.stages[min(k - 1, len(j.stages) - 1)].seconds += gone.seconds
    return j, issues, findings


# ---------- keep it inside what the pipeline makes ----------

def repair(j: Journey, seconds: float) -> list[str]:
    notes = []
    if not j.stages:
        raise ValueError("The journey has no stages")
    for k, s in enumerate(j.stages):
        s.seconds = max(3.0, min(7.0, float(s.seconds or 5)))
        if k == 0:
            s.cut = False
        s.sounds = s.sounds[:4]
        for x in s.sounds:
            x.at = max(0.0, min(1.0, x.at))
            x.volume = max(0.2, min(1.6, x.volume))
    cuts = [k for k, s in enumerate(j.stages) if s.cut]
    for k in cuts[1:]:  # one cut at most: from the opening event to the fixed camera
        j.stages[k].cut = False
        notes.append(f"Stage {k + 1} continues the shot (only one cut)")
    total = sum(s.seconds for s in j.stages)
    if seconds and abs(total - seconds) > 1.0:
        f = seconds / total
        for s in j.stages:
            s.seconds = round(max(3.0, min(7.5, s.seconds * f)), 2)
    j.top_text, j.bottom_text = j.top_text.strip(), j.bottom_text.strip()
    return notes


def save(j: Journey, path: Path) -> None:
    path.write_text(j.model_dump_json(indent=1), encoding="utf-8")


def load(path: Path) -> Journey:
    return Journey.model_validate_json(path.read_text(encoding="utf-8"))
