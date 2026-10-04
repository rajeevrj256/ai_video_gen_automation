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
from .script_writer import AI_CLICHES, SoundCue
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
Shape = Literal["bubble", "blob", "bot", "cube", "coin", "drop", "ghost", "sun", "flame", "planet", "virus", "chip",
                "battery", "shield", "heart", "cloud", "star"]
GENERIC = ("bubble", "blob", "cube", "ghost", "star", "drop")  # bodies that say nothing about the subject
Accessory = Literal["none", "headset", "antenna", "cap", "glasses", "crown", "bowtie"]
Mood = Literal["neutral", "happy", "wink", "smug", "angry", "sad", "scared", "shocked", "sleepy", "evil", "cool",
               "confused", "laughing", "crying", "proud", "determined", "worried"]
Backdrop = Literal["grid", "flat", "dots", "sky", "city", "space", "lab", "stage", "desk"]
Action = Literal["none", "pop", "crack", "clone", "flood", "unlock", "lock", "toggle-off", "toggle-on", "gauge-up",
                 "gauge-down", "strings", "strings-burn", "burst", "fly-out", "crosshair", "sparks", "cage", "connect",
                 "orbit", "rain", "arrow-up", "arrow-down", "versus", "bars", "shake"]
Pose = Literal["stand", "point", "shrug", "hands-up", "hands-head", "think", "wave", "run", "sit", "present",
               "arms-crossed", "celebrate", "typing", "sneak", "cower", "facepalm", "hold-up"]
Outfit = Literal["shirt", "suit", "lab-coat", "hoodie", "uniform", "robe", "dress", "overalls", "period-coat", "jacket", "t-shirt"]
Headwear = Literal["none", "hard-hat", "cap", "top-hat", "tricorn", "headscarf", "crown", "helmet", "beanie", "hood",
                   "bowler", "turban", "chef-hat", "graduation-cap"]
Kind = Literal["fact", "explanation", "question", "surprise", "warning", "comparison", "statistic", "conclusion",
               "emotional", "humor", "call-to-action", "reveal"]
Tone = Literal["calm", "firm", "dramatic", "excited", "urgent", "curious", "soft", "playful", "confident", "direct"]
# How each tone is spoken (edge-tts has no styles): rate % added to the chosen speed, pitch Hz, volume %.
TONES = {"calm": (0, 0, 0), "firm": (-6, -10, 6), "dramatic": (-10, -18, 0), "excited": (8, 22, 10),
         "urgent": (10, -4, 14), "curious": (0, 18, 0), "soft": (-12, -6, -14), "playful": (5, 26, 6),
         "confident": (-4, -12, 10), "direct": (4, 0, 10)}
EmphasisFx = Literal["text", "zoom", "shake", "flash", "glow", "rain", "react", "pause"]
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
    shape: Shape = Field(description="Its body, from what it stands for: bot/chip/bubble (AI, computers, chat), sun/planet "
                         "(space, the sun, Earth), flame (fire, heat, energy), battery (power, electricity), virus "
                         "(disease, malware), shield (security, defence), heart (health, love), coin (money), cloud "
                         "(weather, the cloud), drop (water), star, cube, blob, ghost (only when nothing fits better).")
    color: str = Field(description="Its main colour as #RRGGBB, bright and readable on the palette (not grey).")
    accessory: Accessory


class TPerson(BaseModel):
    id: str = Field(description="Short id used in the shots, e.g. 'eng', 'ceo'.")
    role: str = Field(description="Who they are in the story (an engineer, a minister, a farmer...). Never a real, named person.")
    personality: str = Field(default="", description="2-4 words that set how they move and react (nervous intern, smug executive...).")
    age: Literal["child", "young", "adult", "elder"] = "adult"
    build: Literal["slim", "average", "broad"] = "average"
    outfit: Outfit = Field(default="shirt", description="Fits the role and the period: a hacker in a hoodie, an official in a "
                           "suit, a scientist in a lab coat, a 19th-century clerk in a period coat, a worker in overalls.")
    headwear: Headwear = "none"
    held: str = Field(default="", description="A lucide icon name they hold (phone, briefcase, clipboard, wrench...), or empty.")
    held_svg: str = Field(default="", description="Only if no icon fits what they hold: a small flat SVG drawing of it (see Custom drawings).")
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
    svg: str = Field(default="", description="A custom flat drawing of this object when no icon really shows it (see Custom "
                     "drawings); the icon is then only its fallback.")
    icon: str = Field(description="A lucide icon name in kebab-case for the object (shield, server, brain-circuit, coins, "
                      "virus, factory...), or 'crate' (a mystery box), 'padlock' or 'server' (drawn by hand). For a named "
                      "organisation or product use badge=true and its name as the label.")
    label: str = Field(default="", description="0-3 words under the object, or the badge text.")
    badge: bool = Field(default=False, description="A name badge (organisation, product, place) instead of an icon.")


class TActor(BaseModel):
    id: str = Field(description="A cast id.")
    pose: Pose
    mood: Mood
    mood_after: Mood | Literal[""] = Field(default="", description="Their face changes to this on the emphasised phrase (a reaction), or empty.")
    pos: Literal["far-left", "left", "center", "right", "far-right"]
    talking: bool = Field(default=False, description="True if this person is the one saying/announcing the line (their mouth moves).")


class TShot(BaseModel):
    # Think first, like a director: what must the viewer see, feel and understand at this exact moment?
    line: str = Field(description="One spoken sentence, 4-26 words. The whole video is these lines in order.")
    meaning: str = Field(description="What the viewer must understand from this line, in a few words.")
    kind: Kind
    importance: Literal["low", "medium", "high", "critical"] = Field(description="low: connective/background (subtle motion). "
                        "medium: a supporting point (a character move + a supporting visual). high: a key fact (a new "
                        "visual, camera move, emphasis). critical: the hook, a reveal, a turn (everything hits at once). "
                        "Most lines are low or medium; critical is rare.")
    tone: Tone = Field(description="How the narrator says it: calm (explaining), firm (an important fact), dramatic (a "
                       "reveal), excited (a surprise), urgent (a warning), curious (a question), soft (an emotional moment), "
                       "playful (humour), confident (a conclusion), direct (a call to action).")
    emphasis: str = Field(default="", description="The few words of the line that carry it (copied exactly, e.g. 'millions "
                          "of dollars in losses'), or empty for low lines. Never every word.")
    emphasis_fx: list[EmphasisFx] = Field(default_factory=list, description="What happens on the emphasised words: text (big "
                                          "animated words), zoom (camera punches in), shake, flash, glow, rain (the first object "
                                          "rains down, e.g. money), react (faces change to mood_after / mascot_after), pause (a "
                                          "beat of silence after the line). 0 for low, 1-2 for medium/high, 3-4 for critical.")
    visual_idea: str = Field(description="The visual concept for this line in one sentence: who/what we see and what happens, "
                             "a metaphor for anything abstract.")
    backdrop: Backdrop = Field(description="grid: a glowing digital room (inside computers, networks, AI). flat: plain colour "
                               "for ideas and objects. dots: playful colour. sky / city: the outside world, the public. space: "
                               "global scale. lab: scientists, research. stage: a podium with microphones (statements, press, "
                               "officials). desk: someone at work at a desk with a screen.")
    mascot: Mood | Literal["hidden"] = Field(description="The mascot's face in this shot, or 'hidden'.")
    mascot_tint: Literal["normal", "red", "grey", "gold", "green"] = Field(default="normal", description="red = danger/angry, grey = a copy or powerless, gold = winning, green = healthy.")
    mascot_pos: Literal["left", "center", "right"] = "center"
    mascot_size: Literal["s", "m", "l"] = "m"
    mascot_after: Mood | Literal[""] = Field(default="", description="The mascot's face on the emphasised words, or empty.")
    backdrop_after: Backdrop | Literal[""] = Field(default="", description="The setting switches to this on the emphasised "
                                                  "words ('Then everything changed'), or empty.")
    scene_art: str = Field(default="", description="A custom flat drawing for this scene when the built-in settings and "
                           "objects can't show it (a pyramid, a 1850s telegraph office, a dam, a volcano...): see Custom drawings.")
    scene_art_pos: Literal["left", "center", "right", "back"] = Field(default="back", description="back = a large element behind everything.")
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
    sounds: list[SoundCue] = Field(default_factory=list, description="0-2 sound effects from the sound list on exact words "
                                   "(the user's own files when they fit); most lines get none, the action already has one.")


class TSegment(BaseModel):
    number: int = Field(default=0, description="countdown: the entry's number (counting down); otherwise 0.")
    heading: str = Field(default="", description="The entry/stage title shown on its card (2-6 words), or empty.")
    intensity: float = Field(default=0.5, ge=0, le=1, description="How intense this part is (the music follows it).")
    shots: list[TShot]


class ToonScript(BaseModel):
    subject: str = Field(description="The one specific subject of the video.")
    cold_open: list[TShot] = Field(default_factory=list, description="The hook, 30-40 seconds (85-110 spoken words) in 6-10 "
                                   "fast shots before the title card: the most gripping moments of the video, escalating, "
                                   "big actions, 2-3 slams, ending on a cliffhanger line. Only things the video really "
                                   "shows; true or clearly a possibility.")
    form: Form
    title: str = Field(description="The video's title: curiosity and the main search phrase, max 70 characters, honest.")
    hook: str = Field(description="One sentence: why someone keeps watching.")
    youtube_description: str = Field(description="2-4 natural sentences about the video, then one line inviting viewers to subscribe. No hashtags.")
    tags: list[str] = Field(description="10-20 search tags.")
    hashtags: list[str] = Field(description="3 hashtags without '#'.")
    category: str = Field(default="", description="One of " + ", ".join(CATEGORIES) + ".")
    mood: MusicMood = Field(description="The composed music's mood (when music is 'compose').")
    music: str = Field(default="compose", description="The main music: one of the user's own tracks from the music list when "
                       "it truly fits the whole video, else 'compose' (a new track in your mood).")
    hook_track: str = Field(default="", description="One of the user's own tracks for the cold open when it fits, else empty "
                            "(an energetic trailer track is composed).")
    mascot: TMascot
    cast: list[TPerson] = Field(default_factory=list, description="0-5 cartoon people used in the shots (generic roles, never real named people).")
    sources: list[LSource] = Field(default_factory=list, description="3-10 pages you opened that confirm every real fact.")
    segments: list[TSegment]


def _system(minutes: float, form: str, recent: str, sounds: str = "") -> str:
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
- Open with `cold_open`, an energetic 30-40 second hook (85-110 words, 6-10 shots), like a trailer: a startling first \
line in 12 words or fewer, then the stakes rising shot by shot (the most surprising facts and moments from the video, \
a "but" turn, a question the viewer needs answered), 2-3 slams, a different action in every shot, and a final \
cliffhanger line that leads straight into the title card. The segments start after the title. No greeting, no \
"in this video". These words count toward the total length.
- Never use these phrases: {", ".join(AI_CLICHES)}.
- Accuracy first: every real name, number, date and event must be true and confirmed with web search; put the pages in \
`sources`. Anything speculative is said as a possibility ("could", "imagine", "experts warn"), never as fact. No real \
people as characters, no politics or rumours about real people.
- Write your own words: never copy another channel's script, titles, characters or jokes.

You are the animation director, not an asset picker. For every line, think in this order before choosing anything:
narration → meaning → emotion → visual concept → characters → animation → camera → text → sound → timing, and ask:
"what must the audience see, feel and understand at this exact moment?" Fill `meaning`, `kind`, `importance`, `tone`,
`emphasis` and `visual_idea` first, then the visuals that serve them.

Directing rules:
- Visual hierarchy by importance. low: one subtle visual, camera still or a slow pan, no text. medium: a character
move or reaction plus one supporting visual. high: a new visual, a camera move, the emphasised words on screen.
critical (the hook's key lines, reveals, turns): strong action + character reaction + big typography + camera punch
+ sound, all on the same word. Most lines are low or medium, so the high ones land.
- Emphasis: pick only the words that carry the line ("millions of dollars in losses", not the whole sentence) and what
happens on them (`emphasis_fx`): big words, a zoom, a reaction (`mood_after` / `mascot_after`), money raining, a
flash. "Then everything changed": on "changed" the faces change, the setting changes (`backdrop_after`), the camera
pushes in and a sound hits. Never emphasise every line.
- Every sentence gets the picture of its own meaning, never generic motion behind the voice. Abstract ideas become a
visual metaphor (inflation → a shrinking coin; a bottleneck → a funnel jammed with packets).
- Characters are cast per scene from what the line is about: an AI engineer, a government official, a hacker in a
hoodie at a glowing screen, a 19th-century telegraph operator in a period coat. Give each its age, build, outfit,
headwear, what it holds and its personality; the same person keeps their look, but bring in new people whenever the
story needs someone else. Poses and faces act the line out (cowering, celebrating, typing, arms crossed...).
- The mascot is the subject (an AI, a virus, money...): designed from what the video is about (a solar storm → a sun,
malware → a virus, savings → a coin), new each video; hidden in every shot if nothing can be a character. Its face
and tint follow the story; clone or flood it when the subject spreads.
- Something happens in every shot (`action` on its `action_word`), never the same action, pose, camera move or cut
twice in a row, and never more than 3 shots on the same setting. One consistent style, constant variation.
- Objects: an icon when one shows it exactly, a badge for a named company or place, and a custom drawing when neither
does. A date card when a real dated event comes in. Slams only for punchlines.
- Tone of voice follows the sentence: an important fact is firmer and slower, a reveal dramatic, a warning urgent, a
question curious, an emotional moment soft, a conclusion confident.
- countdown: each segment is one entry with its `number` and `heading`; its first line is that entry's setup.

Custom drawings (`svg`, `scene_art`, `held_svg`): when nothing built in shows the thing, draw it yourself as flat,
bold cartoon vector art in the style of the video: an SVG fragment (no <svg> wrapper) for a 200x200 box using only
path, circle, ellipse, rect, polygon, polyline, line and g, solid fills, dark outlines (stroke #15151c, width 4-6),
2-5 colours, simple shapes, no text, no images, no scripts, under 1500 characters. Use them where they matter (about
1 shot in 4), not for things an icon already shows.

Actions:
{ACTION_HELP}

{sounds}"""


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
    if topic:  # the user's own topic is the video: never swapped for another subject
        prompt = (f"Topic, chosen by the user: {topic}\nThe video is about exactly this topic (its subject and title follow "
                  "it). Don't replace it with a different subject.")
    else:
        prompt = ("Topic: pick a subject people are curious or worried about right now (science, technology, space, "
                  "health, money, nature, history) that suits this format.") + repeats.prompt_block(cfg, repeats.EVERY)
    if avoid:
        prompt += f"\n\n{avoid}"
    prompt += ("\n- Research budget: at most 8 web searches and 6 opened pages, then write.")
    sounds = media.prompt_block(cfg) + "\nIn this video, `music` and `hook_track` name the user's own tracks only when they fit; otherwise 'compose' / empty."
    return ask(cfg.ai_backend, cfg.claude_model, _system(req.minutes, req.form, recent, sounds), prompt, ToonScript,
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
    refs = {f"H{hi + 1}": sh for hi, sh in enumerate(sc.cold_open)}
    refs.update({f"S{si + 1}.{hi + 1}": sh for si, seg in enumerate(sc.segments) for hi, sh in enumerate(seg.shots)})
    return refs


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
    sc.cold_open = [sh for sh in sc.cold_open if sh.line.strip()]
    for seg in sc.segments:
        seg.shots = [sh for sh in seg.shots if sh.line.strip()]
    sc.segments = [seg for seg in sc.segments if seg.shots]
    return sc, issues, findings


# ---------- from the script to the editor's props ----------

def _look(p: TPerson) -> dict:
    return {"skin": SKINS[p.skin % len(SKINS)], "hair": p.hair, "hairColor": p.hair_color, "beard": p.beard,
            "glasses": p.glasses, "shirt": p.shirt, "tie": p.tie or None, "pants": p.pants, "coat": p.coat or None,
            "age": p.age, "build": p.build, "outfit": p.outfit, "headwear": p.headwear,
            "held": p.held.strip().lower()[:40] or None, "heldSvg": clean_svg(p.held_svg, f"h{p.id}") or None}


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


TITLE_SECONDS = 2.4  # the title card after the cold open
# Importance sets the visual intensity: how fast the action plays (seconds), the camera, the default emphasis.
INTENSITY = {"low": (1.3, "still"), "medium": (0.9, "push"), "high": (0.6, "push"), "critical": (0.4, "push")}
POSE_SWAP = {"stand": "think", "point": "present", "shrug": "arms-crossed", "think": "point", "hands-head": "cower",
             "present": "point", "sit": "typing", "arms-crossed": "shrug", "wave": "celebrate", "typing": "think",
             "celebrate": "hands-up", "hands-up": "celebrate", "cower": "hands-head", "facepalm": "shrug",
             "hold-up": "present", "run": "run", "sneak": "sneak"}


def _norm(w: str) -> str:
    return re.sub(r"[^a-z0-9]", "", w.lower())


def _find_phrase(words, phrase: str) -> tuple[float, float] | None:
    """Where in the line's audio the emphasised phrase is spoken (start of its first word, end of its last).
    Matched on the letters, since edge-tts times some word groups as one ('90 percent', 'In 1859')."""
    want = "".join(_norm(w) for w in phrase.split())
    if not want or not words:
        return None
    text, owner = "", []
    for k, w in enumerate(words):
        n = _norm(w.text)
        text += n
        owner += [k] * len(n)
    at = text.find(want)
    if at < 0:  # not said as written: its first word, if it is there
        first = _norm(phrase.split()[0])
        at, want = text.find(first), first
        if not first or at < 0:
            return None
    return words[owner[at]].start, words[owner[at + len(want) - 1]].end


def _direct(shots: list[dict]) -> None:
    """The director's last pass in code: intensity follows importance, and no camera move, cut, setting or pose
    repeats too often (the writer is told the same; this makes sure)."""
    cams = {"low": ["still", "pan"], "medium": ["push", "pan", "pull"], "high": ["push", "pull"], "critical": ["push"]}
    last_pose: dict[str, str] = {}
    for i, s in enumerate(shots):
        if s.get("card") and s["card"]["kind"] in ("number", "title"):
            continue
        imp = s.get("importance", "medium")
        if imp == "low":
            s["slam"], s["emphasisFx"] = None, [fx for fx in s.get("emphasisFx", []) if fx in ("react",)]
        if imp == "critical" and s.get("emphasis"):
            s["emphasisFx"] = list(dict.fromkeys([*s.get("emphasisFx", []), "text", "zoom", "react"]))[:4]
        prev = [x for x in shots[max(0, i - 2):i] if not x.get("card") or x["card"]["kind"] == "date"]
        if s["camera"] not in cams[imp] or (len(prev) == 2 and all(x["camera"] == s["camera"] for x in prev)):
            options = [c for c in cams[imp] if not prev or c != prev[-1]["camera"]] or cams[imp]
            s["camera"] = options[i % len(options)]
        if len(prev) == 2 and all(x["enter"] == s["enter"] for x in prev) and s["enter"] != "cut":
            s["enter"] = "cut"
        if len(prev) >= 2 and all(x["backdrop"] == s["backdrop"] for x in prev):
            s["tone"] = (s["tone"] + 1 + i) % 5  # a fourth shot in the same setting at least changes its colour
        for pp in s.get("people") or []:
            key = pp["look"]["shirt"] + pp["look"]["hair"]
            if last_pose.get(key) == pp["pose"] and pp["pose"] not in ("run", "sit", "typing"):
                pp["pose"] = POSE_SWAP.get(pp["pose"], "think")
            last_pose[key] = pp["pose"]


def build(sc: ToonScript, req: ToonRequest, cfg: Config, work: Path, progress: Progress, seed: int) -> tuple[dict, dict]:
    from . import music as composer, variety

    style = _style(cfg, seed)
    # What is spoken, in order: the cold open, then each countdown number ("Number seven.") and every line.
    plan: list[tuple[str, int, TShot | None, str]] = [("hook", -1, sh, sh.line) for sh in sc.cold_open]
    for si, seg in enumerate(sc.segments):
        if sc.form == "countdown" and seg.number:
            plan.append(("number", si, None, f"Number {_spoken_number(seg.number)}."))
        plan += [("line", si, sh, sh.line) for sh in seg.shots]
    # Each run of lines in the same tone is one take (calm explaining, a firm fact, a dramatic reveal, an urgent
    # warning...): the delivery follows the sentence, and within a run the voice still flows.
    progress("Recording the voiceover")
    voice = req.voice if req.voice in VOICES else "en-US-AndrewMultilingualNeural"
    tone_of = lambda item: item[2].tone if item[2] is not None else "firm"  # noqa: E731
    audio: list = [None] * len(plan)
    i = 0
    while i < len(plan):
        j = i
        while j + 1 < len(plan) and tone_of(plan[j + 1]) == tone_of(plan[i]):
            j += 1
        pace, pitch, loud = TONES.get(tone_of(plan[i]), (0, 0, 0))
        takes = synthesize_scenes([text for *_, text in plan[i:j + 1]], voice, work / "audio" / f"take{i:03d}",
                                  cfg.tts_engine, cfg.kokoro_voice, f"{max(-30, min(50, req.speed + pace)):+d}%",
                                  f"{pitch:+d}Hz", f"{loud:+d}%")
        audio[i:j + 1] = takes
        i = j + 1
    sfx = write_sfx(work / "sfx")
    sfx.update(media.uploaded_for(cfg, list(sfx), work / "sfx"))
    rel = lambda p: Path(p).relative_to(work).as_posix()  # noqa: E731
    cast = {p.id: p for p in sc.cast}
    looks = {p.id: _look(p) for p in sc.cast}
    shots, cues, spoken, used = [], [], [], {}
    tones = len(PALETTES[style["palette"]]["tones"])
    cue = lambda name, at, vol: cues.append({"src": rel(sfx[name]), "at": round(max(0.0, at), 3), "volume": vol, "name": name}) if name in sfx else None  # noqa: E731
    m = sc.mascot
    t, music_from = 0.0, 0.0
    hook_cuts: list[float] = []

    def title_card() -> None:
        nonlocal t, music_from
        shots.append({"start": round(t, 3), "duration": TITLE_SECONDS, "lead": 0, "audio": None, "text": "", "words": [],
                      "segment": -1, "backdrop": "flat", "tone": 0, "items": [], "action": "none", "at": 0.2,
                      "camera": "push", "enter": "flash", "mascot": {"mood": "happy", "tint": "normal", "pos": "center", "size": "m"},
                      "card": {"kind": "title", "text": sc.title}})
        cue("whoosh", t - 0.15, 0.7)
        cue("impact", t + 0.2, 0.8)
        cue("shimmer", t + 0.45, 0.5)
        t += TITLE_SECONDS
        music_from = max(0.0, t - 0.4)

    for n, ((kind, si, sh, text), sa) in enumerate(zip(plan, audio)):
        if kind != "hook" and not any((x.get("card") or {}).get("kind") == "title" for x in shots):
            title_card()  # once, after the cold open (first, if there is none)
        seg = sc.segments[si] if si >= 0 else None
        imp = sh.importance if sh is not None else "high"
        # A beat of silence before a reveal or a critical line, and after one that asks for a pause.
        lead = 0.35 if kind == "number" else 0.45 if sh is not None and (imp == "critical" or sh.kind == "reveal") else 0.12
        talk = media_seconds(sa.path)
        tail = 0.55 if kind == "number" else 0.6 if sh is not None and "pause" in sh.emphasis_fx else 0.22
        duration = round(lead + talk + tail, 3)
        words = [{"text": w.text, "start": round(w.start, 3), "end": round(w.end, 3)} for w in sa.words]
        tone = (si if si >= 0 else 2) % tones
        if kind == "number":
            shot = {"backdrop": "flat", "tone": tone, "items": [], "action": "none", "at": 0.3, "camera": "still",
                    "enter": "whip", "card": {"kind": "number", "text": str(seg.number), "sub": seg.heading or None}}
            cue("whoosh", t - 0.05, 0.6)
            cue("impact", t + 0.25, 0.7)
        else:
            key = _norm(sh.action_word)
            hit = next((w for w in sa.words if key and _norm(w.text) == key), None)
            at = round(lead + (hit.start if hit else talk * 0.35), 3)
            span = _find_phrase(sa.words, sh.emphasis) if sh.emphasis.strip() else None
            emph = {"text": sh.emphasis.strip()[:48], "at": round(lead + span[0], 3), "end": round(lead + span[1], 3)} if span else None
            people = [{"look": looks[a.id], "pose": a.pose, "mood": a.mood, "moodAfter": a.mood_after or None, "pos": a.pos,
                       "talking": a.talking, "seated": sh.backdrop == "desk", "flip": a.pos in ("right", "far-right"),
                       "personality": cast[a.id].personality}
                      for a in sh.people[:3] if a.id in cast]
            if sh.backdrop == "stage" and people:  # the speaker stands at the podium, anyone else to the side
                speaker = next((x for x in people if x["talking"]), people[0])
                others = iter(["far-left", "far-right"])
                for x in people:
                    x["pos"] = "center" if x is speaker else (x["pos"] if x["pos"] in ("far-left", "far-right") else next(others, "far-right"))
            items = []
            for k, o in enumerate(sh.objects[:4]):
                art = clean_svg(o.svg, f"o{n}-{k}")
                items.append({"icon": o.icon.strip().lower()[:40] or "sparkles", "label": o.label[:28] or None,
                              "badge": o.badge, "svg": art or None})
            speed, _ = INTENSITY.get(imp, INTENSITY["medium"])
            shot = {"backdrop": sh.backdrop, "tone": tone, "action": sh.action, "at": at, "camera": sh.camera,
                    "enter": "whip" if kind == "hook" and sh.enter == "cut" else sh.enter, "items": items,
                    "mascot": None if sh.mascot == "hidden" else {"mood": sh.mascot, "tint": sh.mascot_tint,
                                                                   "pos": sh.mascot_pos, "size": sh.mascot_size,
                                                                   "moodAfter": sh.mascot_after or None},
                    "people": people, "crowd": sh.crowd, "slam": sh.slam[:24].upper() or None,
                    "card": {"kind": "date", "text": sh.date[:20]} if sh.date else None,
                    "values": [float(v) for v in sh.values[:5]], "importance": imp, "kind": sh.kind,
                    "emphasis": emph, "emphasisFx": list(dict.fromkeys(sh.emphasis_fx))[:4] if emph else [],
                    "backdropAfter": sh.backdrop_after or None, "speed": speed,
                    "sceneArt": clean_svg(sh.scene_art, f"s{n}") or None, "sceneArtPos": sh.scene_art_pos}
            # Sounds: the action on its word, the emphasis hit, a whoosh on whip cuts, a swish on other cuts, the
            # writer's own cues (the user's files when they fit).
            loud = {"low": 0.55, "medium": 0.7, "high": 0.8, "critical": 0.9}.get(imp, 0.7)
            cue(ACTION_SOUND.get(sh.action, ""), t + at, loud)
            if emph and imp in ("high", "critical"):
                cue("impact" if imp == "critical" else "pop", t + emph["at"], loud)
                if imp == "critical":
                    cue("shimmer", t + emph["at"] + 0.15, 0.5)
            if shot["enter"] == "whip":
                cue("whoosh", t - 0.05, 0.6)
            elif shots:
                cue("swish", t - 0.03, 0.3)
            if shot["slam"]:
                cue("pop", t + max(0.0, at - 0.1), 0.6)
            cues += media.resolve_cues(sh.sounds, sa.words, t + lead, cfg, work / "sfx", rel, 2, used)
            if kind == "hook":
                hook_cuts.append(t)
        shots.append({"start": round(t, 3), "duration": duration, "lead": lead, "audio": rel(sa.path), "text": text,
                      "words": words, "segment": si, **shot})
        spoken += [(t + lead + w.start, t + lead + w.end) for w in sa.words]
        t += duration
    if not any((x.get("card") or {}).get("kind") == "title" for x in shots):
        title_card()
    _direct(shots)
    t = round(t + 0.8, 3)
    (work / "music").mkdir(parents=True, exist_ok=True)
    mine = {mm.name for mm in media.music(cfg) if mm.path is not None}
    # The hook: one of the user's own tracks when Claude picked one that fits (and no recent video used), else a
    # trailer track in a style the last videos didn't use.
    hook_music, choice_hook = None, ""
    if hook_cuts:
        if sc.hook_track in mine and media.fresh_track(cfg, sc.hook_track):
            hook_music = media.pick_music(cfg, sc.hook_track, work / "music", music_from + 0.4)
            choice_hook = sc.hook_track
            media.note_music(cfg, sc.hook_track)
        else:
            used_t = [h.get("trailer") for h in _history(cfg)[-3:]]
            trailer = random.Random(seed).choice([x for x in variety.TRAILERS if x not in used_t] or list(variety.TRAILERS))
            style["trailer"], choice_hook = trailer, f"trailer ({trailer})"
            hook_music = composer.trailer(trailer, music_from + 0.4, [c for c in hook_cuts[1:]] + [music_from], seed,
                                          work / "music" / "hook.wav")
    # The rest: the user's own track when it fits, else a track composed in a mood the last videos didn't use.
    if sc.music in mine and media.fresh_track(cfg, sc.music):
        track, mood = media.pick_music(cfg, sc.music, work / "music", t - music_from), sc.music
        media.note_music(cfg, sc.music)
    else:
        recent_moods = [x[5:] for x in media.recent_music(cfg) if x.startswith("mood:")][-3:]
        mood = sc.mood if sc.mood not in recent_moods else media.fresh_mood(cfg, tuple(MusicMood.__args__), seed)
        seg_starts = [next(x["start"] for x in shots if x["segment"] == si) for si in range(len(sc.segments))]
        bounds = list(zip(seg_starts, [*seg_starts[1:], t]))
        sections = [composer.Section(max(0.0, a - music_from), b - music_from, sc.segments[si].intensity)
                    for si, (a, b) in enumerate(bounds)]
        track = composer.compose(mood, sections, t - music_from, seed, work / "music" / "score.wav")
        media.note_music(cfg, f"mood:{mood}")
    props = {
        "fps": cfg.fps, "duration": t, "title": sc.title, "palette": PALETTES[style["palette"]],
        "mascot": {"shape": m.shape, "color": m.color if re.fullmatch(r"#[0-9a-fA-F]{6}", m.color) else "#2F9BFF",
                   "accessory": m.accessory, "name": m.name},
        "style": {"slam": style["slam"], "card": style["card"], "seed": style["seed"]},
        "shots": shots, "captions": req.captions, "watermark": req.watermark.strip()[:40] or None,
        "music": rel(track) if track else None, "musicFrom": round(music_from, 3), "musicMood": mood,
        "musicChoice": mood if mood in mine else f"composed ({mood})", "hookChoice": choice_hook,
        "hookMusic": rel(hook_music) if hook_music else None, "hookEnd": round(music_from + 0.4, 3),
        "speech": media.speech_spans(spoken), "cues": cues,
    }
    props["sfxLevels"] = media.level_sounds(props, work, [x["audio"] for x in shots if x.get("audio")])
    return props, style


# ---------- custom drawings Claude makes (sanitised) ----------

SVG_TAGS = {"g", "path", "circle", "ellipse", "rect", "polygon", "polyline", "line", "defs", "linearGradient",
            "radialGradient", "stop"}
SVG_ATTRS = {"d", "cx", "cy", "r", "rx", "ry", "x", "y", "width", "height", "x1", "y1", "x2", "y2", "points", "fill",
             "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin", "opacity", "fill-opacity", "stroke-opacity",
             "transform", "id", "offset", "stop-color", "stop-opacity", "gradientUnits", "fx", "fy", "fill-rule",
             "stroke-dasharray"}
_SAFE_VALUE = re.compile(r"^[#\w\s.,()%:+-]*$")


def clean_svg(fragment: str, uid: str) -> str:
    """A drawing Claude wrote, reduced to plain vector shapes: only whitelisted elements and attributes,
    no scripts, links, images, events or styles; ids made unique per drawing; empty if it isn't valid."""
    import xml.etree.ElementTree as ET

    text = re.sub(r"</?svg[^>]*>", "", (fragment or "").strip(), flags=re.I)
    text = re.sub(r"\sxmlns(:\w+)?=\"[^\"]*\"", "", text)
    if not text or len(text) > 6000:
        return ""
    try:
        root = ET.fromstring(f"<g>{text}</g>")
    except ET.ParseError:
        return ""
    count = 0

    def walk(el) -> bool:
        nonlocal count
        count += 1
        tag = el.tag.split("}")[-1]
        if tag not in SVG_TAGS or count > 160:
            return False
        for k in list(el.attrib):
            v = el.attrib[k]
            key = k.split("}")[-1]
            if key not in SVG_ATTRS or not _SAFE_VALUE.match(v) or "javascript" in v.lower():
                del el.attrib[k]
            elif key == "id":
                el.attrib[k] = f"{uid}-{v}"
            elif "url(#" in v:
                el.attrib[k] = re.sub(r"url\(#([\w-]+)\)", lambda m_: f"url(#{uid}-{m_.group(1)})", v)
        el.text = el.tail = None
        for child in list(el):
            if not walk(child):
                el.remove(child)
        return True

    walk(root)
    if count < 2 or not len(root):
        return ""
    out = "".join(ET.tostring(child, encoding="unicode") for child in root)
    return re.sub(r"\sxmlns(:\w+)?=\"[^\"]*\"", "", out)[:8000]


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
        progress("Claude is researching and writing the script and storyboard")
        sc = write_script(cfg, req)
        if req.topic.strip():  # your topic is kept; a video already made on it is only pointed out
            twin = repeats.too_close(sc.subject, sc.title, [x for x in repeats.made(cfg) if x.get("kind", "short") in repeats.EVERY])
            if twin:
                progress(f"Note: a video like this exists already (\"{twin.get('title')}\"); keeping your topic")
            repeats.claim(cfg, {"title": sc.title, "subject": sc.subject, "topic": req.topic.strip(), "kind": "long"})
        else:  # Claude's own pick: never the same video twice
            sc = repeats.guard(cfg, sc, repeats.EVERY, lambda why: write_script(cfg, req, why), progress, kind="long")
        (work / "draft.json").write_text(sc.model_dump_json(indent=1), encoding="utf-8")
        sc, issues, findings = check_facts(cfg, sc, progress)
        save(stage="scripted", script=sc.model_dump(), issues=issues, findings=findings)
    _fresh_mascot(cfg, sc, seed)
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
                    "mascot_color": sc.mascot.color,
                    "palette": style["palette"], "slam": style["slam"], "card": style["card"], "trailer": style.get("trailer"),
                    "mood": props.get("musicMood")})
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
