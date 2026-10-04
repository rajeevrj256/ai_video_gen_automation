"""Toon Explainers: flat, colourful animated explainers (16:9) with cartoon people, a mascot that carries
the story, objects, numbered countdown cards, date cards, word slams and an action on every sentence.

The model is a style of video (the fast "what would happen / top-N scenarios" explainer), not any one
video: Claude picks the structure (countdown, scenario, explainer, timeline, myths, versus), designs a
new mascot and cast, and every video gets its own palette, card and slam style, so no two look alike and
nothing is copied from another channel. True claims are researched and fact-checked like every pipeline
here; anything speculative is said as a possibility.

Separate from every other pipeline: its own tab (Toon), job (`toon_input`), composition (`Toon`,
remotion/src/toon/), checkpoint file (`toon-checkpoint.json`, so the Shorts/long resume never picks
it up) and memory (`toon_history.json`).
"""

from __future__ import annotations

import json
import logging
import random
import re
import shutil
import subprocess
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal

from pydantic import BaseModel, Field

from . import media, repeats
from .categories import CATEGORIES
from .config import Config
from .llm import ask
from .longform import LSource, verify_sources, with_sources
from .script_writer import AI_CLICHES
from .sfx import write_sfx
from .verify import probe
from .video import FFMPEG, _remotion_cli, _render_remotion, media_seconds
from .voice import synthesize_scenes

log = logging.getLogger(__name__)
Progress = Callable[[str], None]

CHECKPOINT = "toon-checkpoint.json"
HISTORY = "toon_history.json"
WORDS_PER_SECOND = 2.75  # fast, punchy narration (the reference ran at ~2.9)
_lock = threading.Lock()

FORMS = {
    "countdown": "a top-N countdown (5-10 entries, counted down, the strongest last); each entry is a mini story: a calm "
                 "setup, the turn ('except...'), a real dated example, why it happens, where it leads",
    "scenario": "a step-by-step 'what would happen if' simulation in stages over time (minute 1, day 1, year 1...); "
                "every stage stands on a real fact and the speculative parts are clearly possibilities",
    "explainer": "how something really works, layer by layer, each layer answering the question the last one raised",
    "timeline": "the true story in order: dated turning points, each with what changed and why it mattered",
    "myths": "beliefs people hold versus what the evidence shows, one per segment, the biggest surprise last",
    "versus": "two things compared round by round on what matters, ending with an honest verdict",
}
Form = Literal["countdown", "scenario", "explainer", "timeline", "myths", "versus"]
Shape = Literal["bubble", "blob", "bot", "cube", "coin", "drop", "ghost"]
Accessory = Literal["none", "headset", "antenna", "cap", "glasses", "crown", "bowtie"]
Mood = Literal["neutral", "happy", "wink", "smug", "angry", "sad", "scared", "shocked", "sleepy", "evil", "cool"]
Backdrop = Literal["grid", "flat", "dots", "sky", "city", "space", "lab", "stage", "desk"]
Action = Literal["none", "pop", "crack", "clone", "flood", "unlock", "lock", "toggle-off", "toggle-on", "gauge-up",
                 "gauge-down", "strings", "strings-burn", "burst", "fly-out", "crosshair", "sparks", "cage", "connect",
                 "orbit", "rain", "arrow-up", "arrow-down", "versus", "bars", "shake"]
Pose = Literal["stand", "point", "shrug", "hands-up", "hands-head", "think", "wave", "run", "sit", "present"]
Hair = Literal["short", "side", "curly", "bun", "long", "bald", "spiky", "cap"]
MusicMood = Literal["mystery", "suspense", "curious", "dark", "energetic", "uplifting", "playful", "quirky", "emotional"]

ACTION_HELP = """\
- pop: the objects spring in on the word. crack: cracks spread across the wall and lightning jumps to the mascot.
- clone: grey copies of the mascot appear around it. flood: copies pour in and fill the whole screen.
- unlock / lock: a padlock opens or snaps shut over the first object. cage: bars drop over the mascot.
- toggle-off / toggle-on: a big switch flips (label = the first object's label). gauge-up / gauge-down: a dial's needle
  swings (label = first object's label).
- strings: a hand holds the objects on puppet strings. strings-burn: the strings catch fire and the objects fall.
- burst: the mascot smashes through a brick wall. fly-out: a dark crate opens and things fly out of it.
- crosshair: a red target locks onto the first object. sparks: electricity crackles over the objects.
- connect: dashed lines link the objects with messages travelling along them. orbit: the objects circle the mascot.
- rain: the first object rains down from the sky. arrow-up / arrow-down: a trend line climbs or crashes.
- versus: the first two objects face off with a VS badge. bars: a bar chart of `values`, labelled by the objects.
- shake: the whole picture shakes. none: nothing extra (the people/mascot carry the shot)."""

PALETTES = [
    {"tones": ["#7B2FF7", "#1F8EF1", "#FF8FAB", "#F9C74F", "#5E2B97"], "ink": "#0B1430", "glow": "#38BDF8", "accent": "#FF9F1C", "hot": "#E5484D", "paper": "#FFFFFF"},
    {"tones": ["#FF6B6B", "#4ECDC4", "#FFE66D", "#1A535C", "#FF9F68"], "ink": "#14213D", "glow": "#4ECDC4", "accent": "#FFB703", "hot": "#D62828", "paper": "#FFFFFF"},
    {"tones": ["#3A86FF", "#8338EC", "#FF006E", "#FB5607", "#FFBE0B"], "ink": "#0D1B2A", "glow": "#4CC9F0", "accent": "#FFBE0B", "hot": "#FF006E", "paper": "#FFFFFF"},
    {"tones": ["#2EC4B6", "#E71D36", "#FF9F1C", "#011627", "#7209B7"], "ink": "#011627", "glow": "#2EC4B6", "accent": "#FF9F1C", "hot": "#E71D36", "paper": "#FDFFFC"},
    {"tones": ["#06D6A0", "#118AB2", "#EF476F", "#FFD166", "#073B4C"], "ink": "#073B4C", "glow": "#06D6A0", "accent": "#FFD166", "hot": "#EF476F", "paper": "#FFFFFF"},
    {"tones": ["#9B5DE5", "#F15BB5", "#FEE440", "#00BBF9", "#00F5D4"], "ink": "#1B1035", "glow": "#00F5D4", "accent": "#FEE440", "hot": "#F15BB5", "paper": "#FFFFFF"},
    {"tones": ["#264653", "#2A9D8F", "#E9C46A", "#F4A261", "#E76F51"], "ink": "#10242C", "glow": "#2A9D8F", "accent": "#E9C46A", "hot": "#E76F51", "paper": "#FFFDF5"},
    {"tones": ["#5390D9", "#7400B8", "#56CFE1", "#F72585", "#4EA8DE"], "ink": "#10002B", "glow": "#72EFDD", "accent": "#F9C74F", "hot": "#F72585", "paper": "#FFFFFF"},
]
SKINS = ["#F6D3B3", "#EBB98F", "#D69A6C", "#B97A50", "#8D5A3B", "#6B3F28"]
# The automatic sound for each action (only the built-in set: never boom, hit or rise).
ACTION_SOUND = {"pop": "pop", "crack": "glitch", "clone": "pop", "flood": "whoosh", "unlock": "impact", "lock": "impact",
                "toggle-off": "impact", "toggle-on": "impact", "gauge-up": "swish", "gauge-down": "swish",
                "strings": "swish", "strings-burn": "whoosh", "burst": "impact", "fly-out": "whoosh", "crosshair": "glitch",
                "sparks": "glitch", "cage": "impact", "connect": "swish", "orbit": "shimmer", "rain": "shimmer",
                "arrow-up": "swish", "arrow-down": "sad", "versus": "impact", "bars": "pop", "shake": "impact"}
VOICES = {"en-US-AndrewMultilingualNeural": "Andrew (US, warm)", "en-US-BrianMultilingualNeural": "Brian (US, bright)",
          "en-US-GuyNeural": "Guy (US, newsy)", "en-US-ChristopherNeural": "Christopher (US, deep)",
          "en-US-AvaMultilingualNeural": "Ava (US, female)", "en-GB-RyanNeural": "Ryan (UK)"}


@dataclass
class ToonRequest:
    topic: str = ""
    minutes: float = 3.0
    form: str = "auto"  # auto (Claude picks, avoiding recent ones) or one of FORMS
    voice: str = "en-US-AndrewMultilingualNeural"
    speed: int = 12  # % faster than normal
    captions: bool = True
    watermark: str = ""


# ---------- what Claude writes ----------

class TMascot(BaseModel):
    name: str = Field(description="A short name for the mascot.")
    represents: str = Field(description="What the mascot stands for in this video (the AI, a virus, a coin, the viewer's money...).")
    shape: Shape = Field(description="Body: bubble (chat bubble), blob, bot (rounded robot head), cube, coin, drop (water drop), ghost.")
    color: str = Field(description="Its main colour as #RRGGBB, bright and readable on the palette (not grey).")
    accessory: Accessory


class TPerson(BaseModel):
    id: str = Field(description="Short id used in the shots, e.g. 'eng', 'ceo'.")
    role: str = Field(description="Who they are in the story (an engineer, a minister, a farmer...). Never a real, named person.")
    skin: int = Field(ge=0, le=5, description="Skin tone 0 (light) to 5 (dark); vary across the cast.")
    hair: Hair
    hair_color: str = Field(description="#RRGGBB")
    beard: Literal["none", "stubble", "full", "mustache"]
    glasses: bool
    shirt: str = Field(description="#RRGGBB")
    tie: str = Field(default="", description="#RRGGBB or empty")
    coat: str = Field(default="", description="#RRGGBB for a jacket/lab coat, or empty")
    pants: str = Field(description="#RRGGBB")


class TOnScreen(BaseModel):
    icon: str = Field(description="A lucide icon name in kebab-case for the object (shield, server, brain-circuit, coins, "
                      "virus, factory...), or 'crate' (a mystery box), 'padlock' or 'server' (drawn by hand). For a named "
                      "organisation or product use badge=true and its name as the label.")
    label: str = Field(default="", description="0-3 words under the object, or the badge text.")
    badge: bool = Field(default=False, description="A name badge (organisation, product, place) instead of an icon.")


class TActor(BaseModel):
    id: str = Field(description="A cast id.")
    pose: Pose
    mood: Mood
    pos: Literal["far-left", "left", "center", "right", "far-right"]
    talking: bool = Field(default=False, description="True if this person is the one saying/announcing the line (their mouth moves).")


class TShot(BaseModel):
    line: str = Field(description="One spoken sentence, 4-26 words. The whole video is these lines in order.")
    backdrop: Backdrop = Field(description="grid: a glowing digital room (inside computers, networks, AI). flat: plain colour "
                               "for ideas and objects. dots: playful colour. sky / city: the outside world, the public. space: "
                               "global scale. lab: scientists, research. stage: a podium with microphones (statements, press, "
                               "officials). desk: someone at work at a desk with a screen.")
    mascot: Mood | Literal["hidden"] = Field(description="The mascot's face in this shot, or 'hidden'.")
    mascot_tint: Literal["normal", "red", "grey", "gold", "green"] = Field(default="normal", description="red = danger/angry, grey = a copy or powerless, gold = winning, green = healthy.")
    mascot_pos: Literal["left", "center", "right"] = "center"
    mascot_size: Literal["s", "m", "l"] = "m"
    people: list[TActor] = Field(default_factory=list, description="0-3 cast members acting the line out.")
    crowd: bool = Field(default=False, description="Ordinary people running across a city/sky scene (panic, the public).")
    objects: list[TOnScreen] = Field(default_factory=list, description="0-4 objects that show what the line says.")
    action: Action = Field(description="What happens in this shot (see the list).")
    action_word: str = Field(description="The word of the line on which the action happens (copied from the line).")
    slam: str = Field(default="", description="1-3 words in huge letters, only for the punchline of a beat; mostly empty.")
    date: str = Field(default="", description="Shown as a date card when the line introduces a real dated event, e.g. 'July 2024'.")
    values: list[float] = Field(default_factory=list, description="bars only: the real figures from the line, in order.")
    camera: Literal["push", "pull", "pan", "still"] = "push"
    enter: Literal["cut", "whip", "zoom", "flash"] = "cut"


class TSegment(BaseModel):
    number: int = Field(default=0, description="countdown: the entry's number (counting down); otherwise 0.")
    heading: str = Field(default="", description="The entry/stage title shown on its card (2-6 words), or empty.")
    intensity: float = Field(default=0.5, ge=0, le=1, description="How intense this part is (the music follows it).")
    shots: list[TShot]


class ToonScript(BaseModel):
    subject: str = Field(description="The one specific subject of the video.")
    form: Form
    title: str = Field(description="The video's title: curiosity and the main search phrase, max 70 characters, honest.")
    hook: str = Field(description="One sentence: why someone keeps watching.")
    youtube_description: str = Field(description="2-4 natural sentences about the video, then one line inviting viewers to subscribe. No hashtags.")
    tags: list[str] = Field(description="10-20 search tags.")
    hashtags: list[str] = Field(description="3 hashtags without '#'.")
    category: str = Field(default="", description="One of " + ", ".join(CATEGORIES) + ".")
    mood: MusicMood = Field(description="The composed music's mood.")
    mascot: TMascot
    cast: list[TPerson] = Field(default_factory=list, description="0-5 cartoon people used in the shots (generic roles, never real named people).")
    sources: list[LSource] = Field(default_factory=list, description="3-10 pages you opened that confirm every real fact.")
    segments: list[TSegment]


def _system(minutes: float, form: str, recent: str) -> str:
    words = int(minutes * 60 * WORDS_PER_SECOND)
    form_rule = (f"Use the form: {form}: {FORMS[form]}." if form in FORMS else
                 "Choose the form that fits the material best:\n" + "\n".join(f"- {k}: {v}" for k, v in FORMS.items()))
    return f"""You write and storyboard fast, flat-animated explainer videos for YouTube (16:9): cartoon people, one \
mascot that carries the story, simple objects, and something happening on every single sentence.

Length: about {words} spoken words ({minutes:g} minutes), every line one shot.
{form_rule}{recent}

The narration:
- American English, a confident, slightly dramatic narrator talking to the viewer. Short punchy sentences mixed with \
longer ones; each line pushes forward (but, so, except, which means). Escalate: every segment raises the stakes.
- Open on the stakes in the first two lines; no greeting, no "in this video".
- Never use these phrases: {", ".join(AI_CLICHES)}.
- Accuracy first: every real name, number, date and event must be true and confirmed with web search; put the pages in \
`sources`. Anything speculative is said as a possibility ("could", "imagine", "experts warn"), never as fact. No real \
people as characters, no politics or rumours about real people.
- Write your own words: never copy another channel's script, titles, characters or jokes.

The pictures (one shot per line):
- Something happens in every shot: pick the `action` that shows the line literally (a line about breaking out → \
burst or crack; about control → strings; about turning off the grid → toggle-off; about spreading → clone or flood). \
Fire it on the word that says it (`action_word`). Never the same action two shots in a row.
- The mascot is the subject (an AI, a virus, money...) and appears in most shots; its face and tint follow the story \
(happy → smug → red and angry). Clone and flood it when the subject spreads.
- Cartoon people act out lines about humans: engineers at a desk, an official at the stage podium (talking=true), \
scientists in the lab, a running crowd in the city. Keep each cast member's look the same all video.
- Objects are simple icons; a named company or place is a badge. 0-4 per shot, never clutter.
- A slam (1-3 huge words) only on a beat's punchline, about 1 shot in 6. A date card when a real dated event comes in.
- Backdrops change with the meaning; never more than 3 shots in a row on the same one. Use whip/zoom/flash cuts \
between segments and on big turns; plain cuts elsewhere.
- countdown: each segment is one entry with its `number` and `heading`; its first line is that entry's setup.

Actions:
{ACTION_HELP}"""


def _history(cfg: Config) -> list[dict]:
    try:
        return json.loads((cfg.output_dir / HISTORY).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _remember(cfg: Config, entry: dict) -> None:
    with _lock:
        past = _history(cfg)
        past.append(entry)
        (cfg.output_dir / HISTORY).write_text(json.dumps(past[-60:], indent=1), encoding="utf-8")


def write_script(cfg: Config, req: ToonRequest, avoid: str = "") -> ToonScript:
    past = _history(cfg)[-6:]
    recent = ""
    if req.form not in FORMS and past:
        recent = ("\nThe last videos used these forms and mascots; pick something different: "
                  + "; ".join(f"{p.get('form')} ({p.get('mascot')})" for p in past))
    topic = req.topic.strip()
    prompt = (f"Topic: {topic}" if topic else "Topic: pick a subject people are curious or worried about right now "
              "(science, technology, space, health, money, nature, history) that suits this format.")
    prompt += repeats.prompt_block(cfg, repeats.EVERY)
    if avoid:
        prompt += f"\n\n{avoid}"
    prompt += ("\n- Research budget: at most 8 web searches and 6 opened pages, then write.")
    return ask(cfg.ai_backend, cfg.claude_model, _system(req.minutes, req.form, recent), prompt, ToonScript,
               allow_web=True, effort=cfg.claude_effort, timeout=2400)


# ---------- fact-check (the same rules as every other pipeline) ----------

class LineCheck(BaseModel):
    ref: str = Field(description="The line's reference, e.g. 'S2.3'.")
    verdict: Literal["confirmed", "wrong", "unsupported"]
    note: str = Field(default="", description="What the sources say, briefly.")
    fix: str = Field(default="", description="For wrong/unsupported: the line rewritten so it is true (or clearly framed "
                     "as a possibility), same length and tone; empty to cut it.")


class ScriptCheck(BaseModel):
    lines: list[LineCheck] = Field(description="Only lines that state a real fact (names, numbers, dates, events, causes).")


def _refs(sc: ToonScript) -> dict[str, TShot]:
    return {f"S{si + 1}.{hi + 1}": sh for si, seg in enumerate(sc.segments) for hi, sh in enumerate(seg.shots)}


def _check(cfg: Config, sc: ToonScript, only: set[str] | None = None) -> ScriptCheck:
    rows = [f"{r}{' >>' if only and r in only else ''} {sh.line}"
            + (f" (on screen: {sh.slam})" if sh.slam else "") + (f" (date card: {sh.date})" if sh.date else "")
            + (f" (chart values: {sh.values})" if sh.values else "")
            for r, sh in _refs(sc).items() if sh.line.strip()]
    system = ("You fact-check an animated explainer. Search the web and open reliable pages. A line is confirmed only if a "
              "source you opened says the same; figures and dates must match. Lines clearly framed as a possibility or a "
              "hypothetical ('could', 'imagine', 'if') are fine as long as they don't state a false fact.")
    prompt = (f"Title: {sc.title}\nThe writer's sources: " + "; ".join(f"{s.title} {s.url}" for s in sc.sources)
              + ("\n\nCheck only the lines marked >> (the rest was checked before)." if only else "") + "\n\n" + "\n".join(rows))
    return ask(cfg.ai_backend, cfg.fact_model, system, prompt, ScriptCheck, allow_web=True, effort=cfg.fact_effort, timeout=1200)


def check_facts(cfg: Config, sc: ToonScript, progress: Progress) -> tuple[ToonScript, list[str], list[dict]]:
    """Check every factual line, apply the checker's true rewrite (checked once more), cut what still can't
    be confirmed (its shot goes). Returns the script, the issues left and every finding."""
    findings: list[dict] = []
    refs = _refs(sc)
    progress("Fact-checking every claim")
    changed: set[str] = set()
    for c in _check(cfg, sc).lines:
        findings.append(c.model_dump())
        sh = refs.get(c.ref)
        if sh is None or c.verdict == "confirmed":
            continue
        sh.line, sh.date = c.fix.strip(), ""  # a rewritten line loses its date card unless re-confirmed with it
        if sh.values:
            sh.values, sh.action = [], "pop"
        changed.add(c.ref)
    issues = []
    rewritten = {r for r in changed if refs[r].line}
    if rewritten:
        progress(f"Re-checking the {len(rewritten)} corrected line(s)")
        for c in _check(cfg, sc, only=rewritten).lines:
            if c.ref in rewritten:
                findings.append({**c.model_dump(), "round": 2})
                if c.verdict != "confirmed":
                    issues.append(f"{c.ref}: still not confirmed ({c.note}); the shot was cut.")
                    refs[c.ref].line = ""
    for seg in sc.segments:
        seg.shots = [sh for sh in seg.shots if sh.line.strip()]
    sc.segments = [seg for seg in sc.segments if seg.shots]
    return sc, issues, findings


# ---------- from the script to the editor's props ----------

def _look(p: TPerson) -> dict:
    return {"skin": SKINS[p.skin % len(SKINS)], "hair": p.hair, "hairColor": p.hair_color, "beard": p.beard,
            "glasses": p.glasses, "shirt": p.shirt, "tie": p.tie or None, "pants": p.pants, "coat": p.coat or None}


def _style(cfg: Config, seed: int) -> dict:
    """This video's own palette and card/slam style: never the palette of the last 3 videos."""
    rng = random.Random(seed)
    used = [h.get("palette") for h in _history(cfg)[-3:]]
    pal = rng.choice([i for i in range(len(PALETTES)) if i not in used] or list(range(len(PALETTES))))
    last = (_history(cfg) or [{}])[-1]
    slam = rng.choice([s for s in ("pill", "stroke", "stamp") if s != last.get("slam")])
    card = rng.choice([c for c in ("badge", "ticket", "circle") if c != last.get("card")])
    return {"palette": pal, "slam": slam, "card": card, "seed": seed % 1000}


def _spoken_number(n: int) -> str:
    words = "zero one two three four five six seven eight nine ten eleven twelve".split()
    return words[n] if 0 <= n < len(words) else str(n)


def build(sc: ToonScript, req: ToonRequest, cfg: Config, work: Path, progress: Progress, seed: int) -> tuple[dict, dict]:
    style = _style(cfg, seed)
    # The spoken script: a countdown entry opens with its number ("Number seven."), then every line.
    plan: list[tuple[int, TShot | None, str]] = []
    for si, seg in enumerate(sc.segments):
        if sc.form == "countdown" and seg.number:
            plan.append((si, None, f"Number {_spoken_number(seg.number)}."))
        for sh in seg.shots:
            plan.append((si, sh, sh.line))
    progress("Recording the voiceover")
    rate = f"+{max(0, min(40, req.speed))}%"
    voice = req.voice if req.voice in VOICES else "en-US-AndrewMultilingualNeural"
    audio = synthesize_scenes([text for _, _, text in plan], voice, work / "audio", cfg.tts_engine, cfg.kokoro_voice, rate)
    sfx = write_sfx(work / "sfx")
    sfx.update(media.uploaded_for(cfg, list(sfx), work / "sfx"))
    rel = lambda p: Path(p).relative_to(work).as_posix()  # noqa: E731
    cast = {p.id: p for p in sc.cast}
    shots, cues, spoken = [], [], []
    tones = len(PALETTES[style["palette"]]["tones"])
    t = 0.0
    for (si, sh, text), sa in zip(plan, audio):
        seg = sc.segments[si]
        lead = 0.35 if sh is None else 0.12
        talk = media_seconds(sa.path)
        duration = round(lead + talk + (0.55 if sh is None else 0.22), 3)
        words = [{"text": w.text, "start": round(w.start, 3), "end": round(w.end, 3)} for w in sa.words]
        if sh is None:  # the countdown card
            shot = {"backdrop": "flat", "tone": si % tones, "items": [], "action": "none", "at": 0.3, "camera": "still",
                    "enter": "whip", "card": {"kind": "number", "text": str(seg.number), "sub": seg.heading or None}}
            cues += [{"src": rel(sfx["whoosh"]), "at": round(t, 3), "volume": 0.5, "name": "whoosh"},
                     {"src": rel(sfx["impact"]), "at": round(t + 0.25, 3), "volume": 0.45, "name": "impact"}]
        else:
            key = re.sub(r"[^a-z0-9]", "", sh.action_word.lower())
            hit = next((w for w in sa.words if key and re.sub(r"[^a-z0-9]", "", w.text.lower()) == key), None)
            at = round(lead + (hit.start if hit else talk * 0.35), 3)
            people = [{"look": _look(cast[a.id]), "pose": a.pose, "mood": a.mood, "pos": a.pos, "talking": a.talking,
                       "seated": sh.backdrop == "desk", "flip": a.pos in ("right", "far-right")}
                      for a in sh.people[:3] if a.id in cast]
            if sh.backdrop == "stage" and people:  # the speaker stands at the podium, anyone else to the side
                speaker = next((x for x in people if x["talking"]), people[0])
                others = iter(["far-left", "far-right"])
                for x in people:
                    x["pos"] = "center" if x is speaker else (x["pos"] if x["pos"] in ("far-left", "far-right") else next(others, "far-right"))
            shot = {"backdrop": sh.backdrop, "tone": si % tones, "action": sh.action, "at": at, "camera": sh.camera,
                    "enter": sh.enter,
                    "items": [{"icon": o.icon.strip().lower()[:40] or "sparkles", "label": o.label[:28] or None, "badge": o.badge}
                              for o in sh.objects[:4]],
                    "mascot": None if sh.mascot == "hidden" else {"mood": sh.mascot, "tint": sh.mascot_tint,
                                                                   "pos": sh.mascot_pos, "size": sh.mascot_size},
                    "people": people, "crowd": sh.crowd, "slam": sh.slam[:24].upper() or None,
                    "card": {"kind": "date", "text": sh.date[:20]} if sh.date else None,
                    "values": [float(v) for v in sh.values[:5]]}
            sound = ACTION_SOUND.get(sh.action)
            if sound in sfx:
                cues.append({"src": rel(sfx[sound]), "at": round(t + at, 3), "volume": 0.45, "name": sound})
            if shot["enter"] == "whip":
                cues.append({"src": rel(sfx["whoosh"]), "at": round(max(0.0, t - 0.05), 3), "volume": 0.4, "name": "whoosh"})
            if shot["slam"]:
                cues.append({"src": rel(sfx["pop"]), "at": round(t + max(0.0, at - 0.1), 3), "volume": 0.4, "name": "pop"})
        shots.append({"start": round(t, 3), "duration": duration, "lead": lead, "audio": rel(sa.path), "text": text,
                      "words": words, "segment": si, **shot})
        spoken += [(t + lead + w.start, t + lead + w.end) for w in sa.words]
        t += duration
    t = round(t + 0.8, 3)
    # A track composed for this video in Claude's mood, rising with each segment's intensity.
    from . import music as composer

    (work / "music").mkdir(parents=True, exist_ok=True)
    starts = [next(s["start"] for s in shots if s["segment"] == si) for si in range(len(sc.segments))]
    sections = [composer.Section(a, b, sc.segments[si].intensity) for si, (a, b) in enumerate(zip(starts, [*starts[1:], t]))]
    track = composer.compose(sc.mood, sections, t, seed, work / "music" / "score.wav")
    media.note_music(cfg, f"mood:{sc.mood}")
    m = sc.mascot
    props = {
        "fps": cfg.fps, "duration": t, "title": sc.title, "palette": PALETTES[style["palette"]],
        "mascot": {"shape": m.shape, "color": m.color if re.fullmatch(r"#[0-9a-fA-F]{6}", m.color) else "#2F9BFF",
                   "accessory": m.accessory, "name": m.name},
        "style": {"slam": style["slam"], "card": style["card"], "seed": style["seed"]},
        "shots": shots, "captions": req.captions, "watermark": req.watermark.strip()[:40] or None,
        "music": rel(track), "speech": media.speech_spans(spoken), "cues": cues,
    }
    props["sfxLevels"] = media.level_sounds(props, work, [s["audio"] for s in shots if s.get("audio")])
    return props, style


# ---------- the run ----------

def run_toon(cfg: Config, req: ToonRequest, progress: Progress = log.info, resume: str | None = None) -> dict:
    from .fsutil import move
    from .llm import meter_records, summarize_usage
    from .pipeline import _render_slot, pause_point, slugify

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    work = cfg.output_dir / resume if resume else cfg.output_dir / f"{stamp}-{uuid.uuid4().hex[:4]}-toon-working"
    work.mkdir(parents=True, exist_ok=True)
    progress(f"Saving progress in {work.name}")
    state = json.loads((work / CHECKPOINT).read_text(encoding="utf-8")) if (work / CHECKPOINT).exists() else {}
    stamp = state.get("stamp", stamp)
    seed = state.get("seed") or int(uuid.uuid4().int % 2**31)

    def save(**changes) -> None:
        state.update(changes, stamp=stamp, seed=seed, request=asdict(req))
        (work / CHECKPOINT).write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        pause_point()

    if state.get("script"):
        sc = ToonScript.model_validate(state["script"])
        issues, findings = state.get("issues", []), state.get("findings", [])
        progress("Resuming: script and fact-check already done")
    else:
        topic = req.topic.strip()
        if topic and len(topic.split()) > 2:  # a broad topic: narrow it to one subject not made before
            req = ToonRequest(**{**asdict(req), "topic": repeats.narrow(cfg, topic, repeats.EVERY, progress)})
        progress("Claude is researching and writing the script and storyboard")
        sc = write_script(cfg, req)
        sc = repeats.guard(cfg, sc, repeats.EVERY, lambda why: write_script(cfg, req, why), progress, kind="long")
        (work / "draft.json").write_text(sc.model_dump_json(indent=1), encoding="utf-8")
        sc, issues, findings = check_facts(cfg, sc, progress)
        save(stage="scripted", script=sc.model_dump(), issues=issues, findings=findings)
    sources, dropped = verify_sources(sc.sources)
    if state.get("props") and all((work / s["audio"]).exists() for s in state["props"]["shots"] if s.get("audio")):
        props, style = state["props"], state["style"]
        progress("Resuming: voice and music already done")
    else:
        props, style = build(sc, req, cfg, work, progress, seed)
        save(stage="voiced", props=props, style=style)
    progress(f"Editing the video ({props['duration'] / 60:.1f} min of animation)")
    cli = _remotion_cli()
    if cli is None:
        raise RuntimeError("Node.js or the Remotion packages are not installed (run start.bat / start.sh)")
    out = work / "reel.mp4"
    if not (state.get("stage") == "rendered" and out.exists()):
        with _render_slot(cfg):
            _render_remotion(cli, props, out, composition="Toon", crf=18, progress=progress)
        save(stage="rendered")
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", "3", "-i", str(out), "-frames:v", "1", "-q:v", "3",
                    str(work / "thumbnail.jpg")], check=False)
    progress("Verifying video quality")
    info = probe(out)
    issues = list(issues)
    if not sources:
        issues.append("No source link could be opened; check the facts before posting.")
    if (info.get("width"), info.get("height")) != (1920, 1080):
        issues.append(f"Resolution is {info.get('width')}x{info.get('height')}, expected 1920x1080.")
    if not info.get("has_audio"):
        issues.append("No audio track.")
    _remember(cfg, {"title": sc.title, "subject": sc.subject, "form": sc.form, "mascot": f"{sc.mascot.shape} {sc.mascot.represents}",
                    "palette": style["palette"], "slam": style["slam"], "card": style["card"]})
    final = cfg.output_dir / f"{stamp}-{slugify(sc.title)}-toon"
    (work / CHECKPOINT).unlink(missing_ok=True)
    move(work, final)
    narration = " ".join(sh.line for seg in sc.segments for sh in seg.shots)
    report = {
        "id": final.name, "format": "long", "length": "long" if props["duration"] >= 420 else "medium",
        "source": "toon", "topic": sc.subject, "subject": sc.subject, "topic_source": "toon explainer",
        "style": "facts", "form": sc.form, "category": sc.category if sc.category in CATEGORIES else "",
        "title": sc.title, "why_chosen": sc.hook, "narration": narration, "created_at": stamp,
        "verified": not issues, "score": None, "issues": issues, "checks": {"probe": info}, "attempts": 1,
        "video": str(final / "reel.mp4"), "thumbnail": str(final / "thumbnail.jpg"),
        "duration_seconds": round(props["duration"], 1), "editor": "remotion (Toon)", "captions": req.captions,
        "voice": req.voice, "youtube_title": sc.title[:100],
        "youtube_description": with_sources(sc.youtube_description.strip(), sources, []),
        "youtube_hashtags": sc.hashtags[:3], "youtube_tags": sc.tags, "caption": sc.youtube_description.strip(),
        "hashtags": sc.hashtags, "fact_check": findings, "sources": sources, "sources_unreachable": dropped,
        "mascot": sc.mascot.model_dump(),
    }
    (final / "script.json").write_text(sc.model_dump_json(indent=2), encoding="utf-8")
    (final / "props.json").write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
    report["usage"] = summarize_usage(meter_records())
    (final / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    progress("Done" if not issues else "Done, but it did not pass every check — review before posting")
    return report


def run_toon_job(cfg: Config, req: ToonRequest, count: int, progress: Progress, resume: list[str] | None = None) -> list[dict]:
    """The app's job: `count` videos one after another in the shared video slot (or resume saved ones)."""
    from .llm import set_limit_reporter, start_meter, usage_line
    from .pipeline import Paused, _video_slot, done_line, set_pause_check

    reports = []
    should_pause = getattr(progress, "should_pause", None)
    todo = [(r,) for r in (resume or [])] or [(None,)] * count
    for i, (folder,) in enumerate(todo):
        vp = (lambda m, n=i + 1: progress(f"[V{n}] {m}")) if len(todo) > 1 else progress
        with _video_slot(cfg):
            if should_pause and should_pause():
                vp("§skip {}")
                continue
            set_pause_check(should_pause)
            set_limit_reporter(vp)
            start_meter(lambda r, vp=vp: vp(usage_line(r)))
            vp(f"=== Video {i + 1}/{len(todo)} ===")
            try:
                reports.append(run_toon(cfg, req, vp, folder))
                vp(done_line(reports[-1]))
            except Paused:
                vp("Paused: progress saved. Press Resume to carry on from here.")
            except Exception as exc:
                log.exception("Toon video %d failed", i + 1)
                vp(f"Video {i + 1} failed: {exc}")
    return reports


def unfinished_toons(cfg: Config) -> list[str]:
    return sorted(p.parent.name for p in cfg.output_dir.glob(f"*-toon-working/{CHECKPOINT}"))


def toon_unfinished(cfg: Config) -> list[dict]:
    """Unfinished Toon videos for the app's "Unfinished videos" list (same shape as pipeline.unfinished)."""
    done = {"scripted": "script and fact-check", "voiced": "script, fact-check and voiceover", "rendered": "everything but the checks"}
    out = []
    for folder in unfinished_toons(cfg):
        path = cfg.output_dir / folder / CHECKPOINT
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        script = state.get("script") or {}
        out.append({"id": folder, "topic": script.get("subject") or (state.get("request") or {}).get("topic") or "Toon",
                    "title": script.get("title", ""), "style": "facts", "length": "toon", "attempt": 1,
                    "done": done.get(state.get("stage") or "", "nothing yet"), "updated": path.stat().st_mtime})
    return out
