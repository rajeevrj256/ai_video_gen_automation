"""Stick Stories: stick-figure comedy episodes (16:9, 3-8 min) and Shorts (9:16) for the channel's
own style, with a recurring cast. One Claude call writes the episode (fiction, no web search, no
fact-check): scenes in sets, every line with its speaker, pose, face, camera and sounds. Each
character gets their own voice (one take per character, cut per line, so mouths move on the words);
the Remotion composition `StickStory` (remotion/src/story/) draws it all in SVG.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal, get_args

from pydantic import BaseModel, Field

from . import media
from .config import Config
from .llm import ask
from .categories import CATEGORIES
from .longform import LSource, verify_sources, with_sources
from .script_writer import AI_CLICHES, SoundCue
from .sfx import write_sfx
from .verify import probe
from .video import FFMPEG, REMOTION_DIR, _remotion_cli, _render_remotion, media_seconds
from .voice import Word as _Word, synthesize_scenes

log = logging.getLogger(__name__)
Progress = Callable[[str], None]

Look = Literal["boy", "girl", "man", "woman", "kid", "old-man", "old-woman"]
Pose = Literal["stand", "walk", "run", "sit", "point", "arms-up", "facepalm", "shrug", "hands-on-hips", "think",
               "cry", "lie", "wave", "hold"]
Face = Literal["neutral", "happy", "laugh", "shock", "angry", "sad", "smirk", "cry", "nervous", "confused", "sleepy",
               "love", "dead"]
Emote = Literal["none", "!", "?", "!?", "sweat", "anger", "hearts", "zzz", "sparkle", "lines"]
Prop = Literal["none", "phone", "book", "paper", "cup", "bag", "laptop", "ball", "plate", "remote", "thing"]
Setting = Literal["living-room", "classroom", "kitchen", "bedroom", "street", "office", "bathroom", "park", "shop",
                  "exam-hall", "blank"]
Camera = Literal["wide", "close", "punch", "shake"]
Action = Literal["none", "jump", "shake", "fall", "spin", "walk-in-left", "walk-in-right", "walk-out-left",
                 "walk-out-right"]
# The sets' furniture and the spots, shared with the editor (remotion/src/story/sets.json): a new kind of
# furniture goes there (and gets a drawing in furniture.tsx); the writer's schema and prompt follow it.
SETS = json.loads((REMOTION_DIR / "src" / "story" / "sets.json").read_text(encoding="utf-8"))
Spot = Literal[tuple(SETS["spots"])]
FurnitureKind = Literal[tuple(SETS["furniture"])]
# How a line is said: the voice's pace (added to the chosen speed), pitch and loudness for edge-tts,
# which takes no emotion styles. Each character's lines are recorded in one take per emotion.
EMOTIONS = {
    "neutral": (0, 0, 0), "happy": (6, 18, 5), "excited": (12, 30, 15), "laughing": (8, 35, 10),
    "angry": (10, -12, 35), "shouting": (14, 10, 50), "sad": (-22, -25, -15), "crying": (-18, -10, -5),
    "scared": (16, 25, -5), "nervous": (10, 12, -10), "whisper": (-12, -8, -45), "shocked": (4, 45, 20),
    "sarcastic": (-14, -18, 0), "confused": (-6, 12, 0), "proud": (-4, -6, 15),
}
Emotion = Literal[tuple(EMOTIONS)]
StickMood = Literal["playful", "quirky", "curious", "uplifting", "emotional", "mystery", "suspense", "energetic", "calm"]
Effect = Literal["none", "erupt", "smoke", "fire", "sparkle", "shake"]
THING_HELP = ("'volcano' (a science-project volcano, drawn by hand) or a lucide icon name in kebab-case for anything "
              "else: trophy, cake, pizza, tv, gift, rocket, dog, cat, guitar, gamepad-2, lamp, plant, alarm-clock, "
              "microscope, flask-conical, bomb, crown, car, bike, briefcase...")


class SThing(BaseModel):
    name: str = Field(description="What it is: " + THING_HELP)
    spot: Spot = Field(description="Where it stands: a spot no one stands on, next to who uses it.")
    on_table: bool = Field(default=True, description="On a small table (true) or on the floor (false).")
    big: bool = False
    effect: Effect = Field(default="none", description="What it does during this line: erupt (a volcano's lava), smoke, fire, sparkle, shake.")

class SPiece(BaseModel):
    kind: FurnitureKind
    spot: Spot = Field(description="Its centre. Someone sitting on it stands on its spot or, when it seats several, "
                       "on the spots next to it that it covers.")
    seats: int = Field(default=1, ge=1, le=3, description="How many spots wide (a sofa or bench 2-3, a counter 2-3).")


NARRATORS = {"english": ["en-US-AndrewMultilingualNeural", "en-US-BrianMultilingualNeural", "en-US-ChristopherNeural"],
             "hindi": ["hi-IN-MadhurNeural", "hi-IN-SwaraNeural"]}

DEFAULT_CAST = "Ben - boy\nLily - girl\nMom - woman\nDad - man\nMr. Carter - man"
SPOTS: dict[str, int] = SETS["spots"]
SHORT_GAP = 230  # 9:16: the cast stands this far apart, centred (heads are 168 px wide)
VOICES = {
    "english": {"boy": "en-US-AndrewMultilingualNeural", "kid": "en-US-AnaNeural", "girl": "en-US-AvaMultilingualNeural",
                "man": "en-US-GuyNeural", "woman": "en-US-JennyNeural",
                "old-man": "en-US-ChristopherNeural", "old-woman": "en-US-AriaNeural"},
    "hindi": {"boy": "hi-IN-MadhurNeural", "kid": "hi-IN-SwaraNeural", "girl": "hi-IN-SwaraNeural",
              "man": "hi-IN-MadhurNeural", "woman": "hi-IN-SwaraNeural",
              "old-man": "hi-IN-MadhurNeural", "old-woman": "hi-IN-SwaraNeural"},
}
# Voices to choose from for each look (English), first = the default. Two characters with the same look
# get different voices automatically; the tab can also set each character's voice.
VOICE_POOLS = {
    "boy": ["en-US-AndrewMultilingualNeural", "en-US-BrianMultilingualNeural", "en-US-EricNeural"],
    "girl": ["en-US-AvaMultilingualNeural", "en-US-EmmaMultilingualNeural", "en-US-AnaNeural"],
    "kid": ["en-US-AnaNeural", "en-US-EmmaMultilingualNeural"],
    "man": ["en-US-GuyNeural", "en-US-ChristopherNeural", "en-US-RogerNeural", "en-US-SteffanNeural",
            "en-US-BrianMultilingualNeural", "en-US-EricNeural"],
    "woman": ["en-US-JennyNeural", "en-US-AriaNeural", "en-US-MichelleNeural", "en-US-EmmaMultilingualNeural"],
    "old-man": ["en-US-ChristopherNeural", "en-US-RogerNeural", "en-US-GuyNeural"],
    "old-woman": ["en-US-AriaNeural", "en-US-MichelleNeural", "en-US-JennyNeural"],
}
VOICE_NAMES = {  # for the tab's voice picker
    "en-US-AndrewMultilingualNeural": "Andrew (young man, warm)", "en-US-BrianMultilingualNeural": "Brian (young man, casual)",
    "en-US-EricNeural": "Eric (man, light)", "en-US-GuyNeural": "Guy (man, deep)", "en-US-ChristopherNeural": "Christopher (man, mature)",
    "en-US-RogerNeural": "Roger (man, older)", "en-US-SteffanNeural": "Steffan (man, calm)",
    "en-US-AvaMultilingualNeural": "Ava (young woman, bright)", "en-US-EmmaMultilingualNeural": "Emma (young woman, cheerful)",
    "en-US-AnaNeural": "Ana (child)", "en-US-JennyNeural": "Jenny (woman, friendly)", "en-US-AriaNeural": "Aria (woman, confident)",
    "en-US-MichelleNeural": "Michelle (woman, soft)",
}
WORDS_PER_SECOND = 2.2  # dialogue with comic pauses


@dataclass
class StickRequest:
    idea: str = ""
    format: str = "long"  # long (16:9 episode) | short (9:16)
    minutes: float = 5.0
    language: str = "english"
    speed: float = 1.5  # how fast everyone talks: 1.5 = 50% faster than normal (snappy comedy timing)
    seconds: int = 0  # a Short's length: 15, 30 or 45 s (0 = 25-50 s)
    style: str = "comedy"  # comedy | fiction (a story with a twist) | facts (true, researched, fact-checked)
    cast: str = DEFAULT_CAST


# ---------- the episode Claude writes ----------

class SCast(BaseModel):
    id: str = Field(description="Short lowercase id, e.g. 'raju'.")
    name: str
    look: Look


class SActor(BaseModel):
    id: str = Field(description="A cast id.")
    spot: Spot = Field(description="Where they stand. Keep each character on the same spot within a scene unless they move.")
    pose: Pose
    face: Face
    facing: Literal["left", "right"] = Field(description="Who they look at: usually toward the person they talk to.")
    emote: Emote = "none"
    prop: Prop = "none"
    prop_text: str = Field(default="", description="1-4 characters on a paper or phone screen (e.g. 'F', '$3'), or empty.")
    prop_thing: str = Field(default="", description="With prop 'thing': what they hold, " + THING_HELP)
    action: Action = Field(default="none", description="Movement during this line: enter or leave the scene, jump, shake, fall, spin.")


class SLine(BaseModel):
    speaker: str = Field(description="The cast id saying this line, 'narrator' for a voice-over (facts and stories), "
                         "or 'none' for a silent beat (a reaction, a look, a pause).")
    line: str = Field(default="", description="What they say, spoken naturally, max 22 words. Empty for a silent beat.")
    emotion: Emotion = Field(default="neutral", description="How it's said (the voice changes pace, pitch and loudness); "
                             "match the speaker's face.")
    pause_before: float = Field(default=0.2, ge=0, le=1.5, description="Seconds of silence before it: 0.6-1.2 before a punchline or a reaction.")
    camera: Camera = Field(default="wide", description="'wide' most of the time, 'close' on a reaction, 'punch' on a punchline, 'shake' on a shock.")
    focus: str = Field(default="", description="Cast id the camera frames on 'close' (default: the speaker).")
    caption: str = Field(default="", description="A meme caption at the top ('POV: ...', 'Meanwhile...', '5 minutes later'), usually empty.")
    actors: list[SActor] = Field(description="Everyone on screen during this line, with their pose, face and position now.")
    things: list[SThing] = Field(default_factory=list, description="Objects standing in the scene during this line (not "
                                 "held); repeat them on every line of the scene while they're there.")
    sounds: list[SoundCue] = Field(default_factory=list, description="0-2 sound effects on a word of the line (or word '*' for a silent beat).")


class SScene(BaseModel):
    setting: Setting
    sign: str = Field(default="", description="A word on the set (a door sign, the board, a shop name), or empty.")
    furniture: list[SPiece] = Field(default_factory=list, description="The furniture this scene needs, placed so the "
                                    "staging works (a sofa under the people sitting, a table under the project). Empty = "
                                    "the setting's usual furniture.")
    washing: bool = Field(default=False, description="Kitchen only: true only when someone in this scene is washing "
                          "dishes at the sink (draws running water and soap foam in front of them). Otherwise false.")
    intensity: float = Field(default=0.5, ge=0, le=1, description="How full the music is in this scene: 0.2 quiet, "
                             "0.5 normal, 0.9 chaos or the climax.")
    lines: list[SLine]


class Episode(BaseModel):
    title: str = Field(description="The episode's title, a relatable situation (used as the YouTube title).")
    logline: str = Field(description="One sentence: the premise and the twist.")
    youtube_description: str = Field(description="2-3 natural sentences about the episode, then one line inviting viewers to subscribe. No hashtags.")
    tags: list[str] = Field(description="8-15 search tags.")
    hashtags: list[str] = Field(description="3 hashtags without '#'.")
    music: str = Field(default="compose", description="'compose' (a new track made for this video in your mood: the "
                       "usual choice), one of the user's own tracks from the music list only when it truly fits, or 'none'.")
    mood: StickMood = Field(default="playful", description="The composed track's mood; not the same as the recent videos'.")
    cast: list[SCast] = Field(description="The characters in this episode (from the given cast; add a minor one only if needed).")
    category: str = Field(default="", description="The library shelf: one of " + ", ".join(CATEGORIES) + ".")
    sources: list[LSource] = Field(default_factory=list, description="Facts only: 2-6 pages you opened with web search "
                                   "that confirm every figure, date and name. Empty for comedy and stories.")
    scenes: list[SScene]


def _system(short: bool, minutes: float, language: str, style: str = "comedy", seconds: int = 0) -> str:
    lang = ("natural, casual American English, the way kids, teens and parents really talk (no Indian or British "
            "words, no rupees: dollars, US schools, US homes)" if language == "english"
            else "everyday Hindi in Devanagari script, as families really talk")
    payoff = {"comedy": "punchline", "fiction": "twist", "facts": "answer"}.get(style, "punchline")
    hook = {"comedy": "with a 'POV:' caption", "fiction": "with someone already in trouble",
            "facts": "with a surprising question or a wrong belief someone holds"}.get(style, "")
    if short:
        span = (f"{seconds} seconds (at most {seconds + 3}): ONE situation, {max(3, seconds // 4)}-{max(4, seconds // 3)} "
                "short lines" if seconds else "25-50 seconds: ONE situation, 5-12 lines")
        form = f"""a YouTube Short (9:16), {span}. The first line ({hook}) \
hooks in under 2 seconds; the {payoff} lands in the last 5 seconds, and the ending can loop back to the start. \
At most 3 characters, standing close together (spots left, center, right)."""
    else:
        words = int(minutes * 60 * WORDS_PER_SECOND)
        form = f"""a {minutes:g}-minute YouTube episode (16:9), about {words} words of dialogue in 4-8 scenes. One \
story: a setup that pulls the viewer in ({hook}), a problem that grows with two or three complications, a turn, \
and a {payoff} that pays off the start."""
    if style == "facts":
        brief = f"""You make stick-figure explainers of TRUE facts for the channel Stickcident: one real, surprising, \
checkable fact (science, the human body, animals, history, money, how everyday things work) that the small \
recurring cast acts out. You write {form}

The cast lives it: a character believes the myth or asks the question, another shows what really happens, and a \
'narrator' voice-over can explain the key fact in plain words while the cast reacts and demonstrates with real \
objects. Keep it light and character-driven, with a joke where it fits, but every claim is true. Accuracy rules: \
search the web and open the pages; every figure, date, name and cause in a line, a sign or a caption must be on \
a page you opened, and those pages go in 'sources'. If the sources disagree or you can't confirm it, leave it \
out. No rumours, no medical or money advice, nothing about living people's private lives."""
    elif style == "fiction":
        brief = f"""You write stick-figure short stories for the channel Stickcident: mystery, suspense, \
heartwarming, revenge-served-sweetly or "you won't believe how this ended" stories about everyday people, told \
with a small recurring cast. You write {form}

Story first: a character we care about wants something, something stands in the way, the stakes rise, and an \
ending the viewer didn't see coming but that was set up from the first scene (a detail planted early pays off). \
Emotion matters more than jokes: fear, hope, guilt, relief, a lump in the throat; a little humour only where \
real people would joke. A 'narrator' line can set the time or place ('Three years later...'). It is fiction: no \
real people, brands or events."""
    else:
        brief = f"""You write stick-figure comedy for the channel Stickcident: relatable everyday moments (school, \
exams, parents, siblings, friends, phones, food, chores) told with a small recurring cast. You write {form}

Comedy first: this is a comedy channel, so every scene is built from jokes, every scene ends on a laugh and \
there's a laugh at least every 3-4 lines. Use what makes these Shorts go viral: a painfully relatable setup, \
misunderstandings, a confident character being wrong, deadpan replies, sarcasm, absurd escalation, a reveal \
that recontextualises everything, visual gags (a prop, a sign, a phone screen), reaction shots, running gags \
and a callback for the final punchline. Cut every line that isn't a setup or a punchline. Sounds help the joke: \
a pop on a reveal, the sad trombone ('sad') on a fail, a click or ding on a phone, a whoosh on a fast exit."""
    return f"""{brief}

The dialogue is in {lang}. The cast talks fast (about 1.5x normal speed), so write snappy lines; let silence and reactions do work (silent beats with \
speaker 'none', a 0.6-1.2 s pause before a punchline, the camera punching in or closing on a reaction). Show \
emotion with poses, faces and emotes: a facepalm, a shocked face with '!', sweat when nervous, a jump for joy, \
someone falling over when stunned. Every spoken line has an emotion (the voice follows it) that matches the \
speaker's face: angry and shouting lines with '!', sad ones slower with '...', laughing, excited, scared, sarcastic, \
whispering. Vary it: a scene where everyone is neutral is flat.

Clean and family-friendly, something anyone can relate to. No politics, religion, real people, brands, insults \
about groups, or anything mean-spirited. Never use these phrases: {", ".join(AI_CLICHES)}.

The lines appear as small subtitles under the scene, so keep each one short (a few words to one sentence). \
Pick the setting each scene needs (living room, classroom, exam hall, office, street, park, shop, bedroom, \
bathroom, kitchen) and vary it between episodes: don't open in the same place as the recent episodes listed. \
Washing dishes at the sink is one situation among many, only when the story is about it (set 'washing').

Staging: every line lists everyone on screen with their spot, pose, face and facing (toward who they talk \
to). Whoever is sitting in the story (on the couch, watching TV, at a desk, waiting) has pose 'sit' on every line \
until they stand up, on a spot covered by a seat (or a stool is drawn under them). {_furniture_help()}

Show the real object, never a paper with its name: a science project is a 'volcano' thing (effect 'erupt' when it \
goes off), a birthday has a cake, a prize a trophy. Use things for objects in the scene and prop 'thing' with \
prop_thing for something held. Paper is only for a test, a note or a report card. Keep spots steady within a scene. Use walk-in/walk-out actions for entrances and exits, and change the \
setting for a new scene."""


def _furniture_help() -> str:
    kinds = "; ".join(f"{k} ({v['about']})" for k, v in SETS["furniture"].items())
    usual = "; ".join(f"{s}: " + (", ".join(f"{p['kind']} at {p['spot']}" for p in ps) or "nothing")
                      for s, ps in SETS["defaults"].items())
    return (f"Each scene's furniture is yours to arrange (list it in 'furniture'; empty = the usual). Kinds: {kinds}. "
            f"Usual furniture: {usual}. A piece seating 3 at center covers left, center and right.")


def _scene_x(scene: SScene, short: bool) -> dict[str, float]:
    """Each spot's x for this scene. Episodes use the fixed spots; a Short packs the spots people and
    objects use next to each other, SHORT_GAP apart around the centre, so the close 9:16 frame holds
    them and a spot stays put through the scene. Spots nobody uses (a sofa's middle, a plant) fall
    between or beyond them."""
    if not short:
        return {k: float(v) for k, v in SPOTS.items()}
    names = list(SPOTS)
    used = sorted({names.index(a.spot) for ln in scene.lines for a in [*ln.actors, *ln.things]})
    x = {i: 960 + (k - (len(used) - 1) / 2) * SHORT_GAP for k, i in enumerate(used)}
    for i in range(len(names)):
        if i in x:
            continue
        lo = max((j for j in used if j < i), default=None)
        hi = min((j for j in used if j > i), default=None)
        if lo is not None and hi is not None:
            x[i] = x[lo] + (x[hi] - x[lo]) * (i - lo) / (hi - lo)
        elif lo is not None:
            x[i] = x[lo] + (i - lo) * SHORT_GAP
        elif hi is not None:
            x[i] = x[hi] - (hi - i) * SHORT_GAP
        else:
            x[i] = 960 + (i - 2) * SHORT_GAP
    return {n: x[i] for i, n in enumerate(names)}


def _default_pieces(setting: str) -> list[SPiece]:
    return [SPiece(**p) for p in SETS["defaults"].get(setting, [])]


def _piece_width(kind: str, seats: int, spacing: float) -> int:
    """The same widths as widthOf in furniture.tsx."""
    one = {"sofa": 300, "bench": 300, "bed": 380, "counter": 360, "shop-counter": 300, "work-desk": 300,
           "table": 260, "desk": 260}.get(kind, 0)
    if not one:
        return {"armchair": 230, "chair": 160, "stool": 160, "washbasin": 240, "tv": 260, "plant": 140}.get(kind, 200)
    return round(max(one, (max(1, seats) - 1) * spacing + one))


# Clothes colours in the channel's greys: the first character (the lead) in a white shirt, the others
# in turn; dresses start grey. Each character keeps theirs for the whole video.
SHIRTS = ("#FFFFFF", "#E4E4E4", "#B4B4B4", "#FFFFFF", "#9C9C9C")
DRESSES = ("#9C9C9C", "#E4E4E4", "#B4B4B4", "#FFFFFF")


def _outfits(cast: list) -> dict[str, str]:
    """Each character's colour: shirts and dresses each go through their own list in cast order."""
    out, seen = {}, {"dress": 0, "shirt": 0}
    for c in cast:
        kind = "dress" if c.look in ("girl", "woman", "old-woman") else "shirt"
        colours = DRESSES if kind == "dress" else SHIRTS
        out[c.id] = colours[seen[kind] % len(colours)]
        seen[kind] += 1
    return out


def _rate(speed: float, extra: int = 0) -> str:
    """1.5 -> '+50%' (the voices' speaking rate), plus an emotion's change of pace in points."""
    return f"{round((min(2.0, max(0.8, speed)) - 1) * 100) + extra:+d}%"


def parse_cast(text: str) -> list[dict]:
    """'Name - look' or 'Name - look - voice' per line (a voice id from VOICE_NAMES; empty = automatic)."""
    out = []
    for row in (text or DEFAULT_CAST).splitlines():
        if not row.strip():
            continue
        parts = [p.strip() for p in row.split(" - ")]
        if len(parts) == 1 and "-" in row:  # 'Ben-boy' written without spaces
            parts = [p.strip() for p in row.split("-", 1)]
        name, look = parts[0], (parts[1].lower() if len(parts) > 1 else "boy")
        voice = parts[2] if len(parts) > 2 and parts[2] in VOICE_NAMES else ""
        out.append({"id": re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or f"c{len(out)}",
                    "name": name, "look": look if look in get_args(Look) else "boy", "voice": voice})
    return out


def assign_voices(cast: list[dict], language: str = "english") -> dict[str, str]:
    """Each character's voice: the one chosen in the tab, else the first voice for their look that no one
    else uses yet (Dad and Mr. Carter are both 'man' but sound different)."""
    if language != "english":
        return {c["id"]: VOICES.get(language, VOICES["english"]).get(c["look"], VOICES["english"]["man"]) for c in cast}
    taken = {c["voice"] for c in cast if c.get("voice")}
    out = {}
    for c in cast:
        if c.get("voice"):
            out[c["id"]] = c["voice"]
            continue
        pool = VOICE_POOLS.get(c["look"], VOICE_POOLS["man"])
        pick = next((v for v in pool if v not in taken), None) \
            or next((v for p in VOICE_POOLS.values() for v in p if v not in taken), pool[0])
        out[c["id"]] = pick
        taken.add(pick)
    return out


def _recent_line(r) -> str:
    if isinstance(r, str):  # older history entries were plain titles
        return r
    return (f"{r.get('title')}" + (f": {r['logline']}" if r.get("logline") else "")
            + f" (places: {', '.join(r.get('places', []))}; music: {r.get('music', '?')})")


# ---------- never the same story twice ----------

_history_lock = threading.Lock()
STOP = set("a an the and or but of to in on at for with by from is are was be his her their your my our it its "
           "this that when what who how why he she they you i we me him them not no just so then than into out up "
           "about over after before again".split())


def _words(text: str) -> set[str]:
    return {w.rstrip("s") for w in re.findall(r"[a-z']+", text.lower()) if w not in STOP and len(w) > 2}


def made_before(cfg: Config) -> list[dict]:
    """Every stick video already made or being made: the library's reports (title and premise), plus
    the history file, which is written as soon as a story is written (so a video still rendering, or
    one that failed later, counts too). Newest last."""
    seen: dict[str, dict] = {}
    for path in sorted(cfg.output_dir.glob("*/report.json")):
        try:
            rep = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if rep.get("source") == "stick":
            seen[rep.get("title", "").lower()] = {"title": rep.get("title", ""), "logline": rep.get("why_chosen", ""),
                                                   "style": rep.get("style", "")}
    try:
        history = json.loads(_history(cfg).read_text(encoding="utf-8")) if _history(cfg).exists() else []
    except (OSError, json.JSONDecodeError):
        history = []
    for r in history:
        r = r if isinstance(r, dict) else {"title": r}
        key = r.get("title", "").lower()
        seen[key] = {**seen.get(key, {}), **{k: v for k, v in r.items() if v}}
    return list(seen.values())


def too_close(ep: Episode, past: list[dict]) -> dict | None:
    """The earlier video this story repeats, if any: the same title, or most of the same words in the
    title and premise (word overlap, so a new title on the same story is caught)."""
    mine = _words(ep.title + " " + ep.logline)
    for r in past:
        if r.get("title", "").strip().lower() == ep.title.strip().lower():
            return r
        theirs = _words(r.get("title", "") + " " + r.get("logline", ""))
        if mine and theirs and len(mine & theirs) / len(mine | theirs) >= 0.4:
            return r
    return None


def remember(cfg: Config, entry: dict) -> None:
    with _history_lock:
        try:
            history = json.loads(_history(cfg).read_text(encoding="utf-8")) if _history(cfg).exists() else []
        except (OSError, json.JSONDecodeError):
            history = []
        history = [h for h in history if (h.get("title") if isinstance(h, dict) else h) != entry["title"]] + [entry]
        _history(cfg).write_text(json.dumps(history[-200:], ensure_ascii=False, indent=0), encoding="utf-8")


def write_episode(cfg: Config, req: StickRequest, recent: list, avoid: str = "") -> Episode:
    short = req.format == "short"
    cast = parse_cast(req.cast)
    prompt = ("The cast (use these ids and looks):\n" + "\n".join(f"- {c['id']}: {c['name']} ({c['look']})" for c in cast)
              + (f"\n\nThe idea: {req.idea}" if req.idea.strip() else "\n\nPick a fresh, relatable situation yourself.")
              + ("\n\nAlready made (never repeat one of these stories, not even with a new title or another "
                 "character; also avoid their opening place and music mood):\n"
                 + "\n".join(f"- {_recent_line(r)}" for r in recent[-40:]) if recent else "")
              + (f"\n\nYour first draft repeated an earlier video ({avoid}). Write a completely different situation."
                 if avoid else "")
              + "\n\n" + media.prompt_block(cfg))
    return ask(cfg.ai_backend, cfg.claude_model, _system(short, req.minutes, req.language, req.style, req.seconds), prompt, Episode,
               allow_web=req.style == "facts", effort=cfg.claude_effort, timeout=1800)


# ---------- facts: checked before anything is recorded ----------

class LineCheck(BaseModel):
    ref: str = Field(description="The line's reference, e.g. 'S1L3'.")
    verdict: Literal["confirmed", "wrong", "unsupported"]
    note: str = Field(default="", description="What the sources say, briefly.")
    fix: str = Field(default="", description="For wrong/unsupported: the same line rewritten so it is true (same speaker, "
                     "same length, same tone), or empty to cut the claim.")


class EpisodeCheck(BaseModel):
    lines: list[LineCheck] = Field(description="Only lines that state a fact (figures, dates, names, causes); skip pure reactions.")


def _refs(ep: Episode) -> dict[str, SLine]:
    return {f"S{si + 1}L{li + 1}": ln for si, sc in enumerate(ep.scenes) for li, ln in enumerate(sc.lines)}


def fact_check_episode(cfg: Config, ep: Episode, only: set[str] | None = None) -> EpisodeCheck:
    """Every factual line checked against the web on the fact-check model (`only`: just these refs)."""
    rows = [f"{r}{' >>' if only and r in only else ''} [{ln.speaker}] {ln.line}"
            + (f" (caption: {ln.caption})" if ln.caption else "")
            + "".join(f" (on screen: {a.prop_text})" for a in ln.actors if a.prop_text)
            for r, ln in _refs(ep).items() if ln.line.strip() or ln.caption]
    signs = [f"Scene {i + 1} sign: {sc.sign}" for i, sc in enumerate(ep.scenes) if sc.sign]
    system = ("You fact-check a short educational stick-figure video. Search the web and open reliable pages. A line "
              "is confirmed only if a source you opened says the same; a figure must match (rounding is fine if the "
              "line says 'about'). Jokes, reactions and obvious fiction about the characters aren't claims.")
    prompt = (f"Title: {ep.title}\nThe writer's sources: " + "; ".join(f"{x.title} {x.url}" for x in ep.sources)
              + ("\n\nCheck only the lines marked >> (the rest was checked before)." if only else "")
              + "\n\n" + "\n".join(rows + signs))
    return ask(cfg.ai_backend, cfg.fact_model, system, prompt, EpisodeCheck, allow_web=True,
               effort=cfg.fact_effort, timeout=1200)


def check_facts(cfg: Config, ep: Episode, progress: Progress) -> tuple[Episode, list[str], list[dict]]:
    """Check, fix what's wrong (a fixed line is checked once more), cut what still can't be confirmed.
    Returns the episode, the issues left for the report, and every finding."""
    findings: list[dict] = []
    refs = _refs(ep)
    progress("Fact-checking every claim")
    check = fact_check_episode(cfg, ep)
    changed = set()
    for c in check.lines:
        findings.append(c.model_dump())
        ln = refs.get(c.ref)
        if ln is None or c.verdict == "confirmed":
            continue
        ln.line = c.fix.strip()  # a true line, or nothing: an unconfirmed claim is never spoken
        changed.add(c.ref)
    issues = []
    rewritten = {r for r in changed if refs[r].line}
    if rewritten:
        progress(f"Re-checking the {len(rewritten)} corrected line(s)")
        for c in fact_check_episode(cfg, ep, only=rewritten).lines:
            if c.ref not in rewritten:
                continue
            findings.append({**c.model_dump(), "round": 2})
            if c.verdict != "confirmed":
                issues.append(f"{c.ref}: still not confirmed ({c.note}); the line was cut.")
                refs[c.ref].line = ""
    for sc in ep.scenes:  # a cut line becomes a silent beat (the reaction stays)
        for ln in sc.lines:
            if not ln.line.strip() and ln.speaker not in ("none", ""):
                ln.speaker = "none"
    return ep, issues, findings


# ---------- from the episode to the editor's props ----------

def build(ep: Episode, req: StickRequest, cfg: Config, work: Path, progress: Progress) -> dict:
    short = req.format == "short"
    looks = {c.id: c.look for c in ep.cast}
    voices = VOICES.get(req.language, VOICES["english"])  # fallback for a character nobody assigned
    lines = [(si, li, ln) for si, sc in enumerate(ep.scenes) for li, ln in enumerate(sc.lines)]

    # One take per character (their lines in order), cut per line: each voice stays consistent.
    progress("Recording the voices")
    audio: dict[tuple[int, int], object] = {}
    given = {c["id"]: c for c in parse_cast(req.cast)}
    cast = [{"id": c.id, "look": c.look, "voice": given.get(c.id, {}).get("voice", "")} for c in ep.cast]
    voice_of = assign_voices(cast, req.language)
    # The narrator: a voice none of the cast has.
    voice_of["narrator"] = next((v for v in NARRATORS.get(req.language, NARRATORS["english"]) if v not in voice_of.values()),
                                NARRATORS.get(req.language, NARRATORS["english"])[0])
    speakers = set(looks) | {"narrator"}
    # One take per character and emotion, cut per line: a character keeps one voice, and an angry line
    # is louder and lower while a sad one is slower and quieter.
    for cid, emo in sorted({(ln.speaker, ln.emotion) for _, _, ln in lines if ln.speaker in speakers and ln.line.strip()}):
        mine = [(si, li, ln) for si, li, ln in lines if ln.speaker == cid and ln.emotion == emo and ln.line.strip()]
        pace, pitch, loud = EMOTIONS.get(emo, (0, 0, 0))
        takes = synthesize_scenes([ln.line for _, _, ln in mine], voice_of.get(cid, voices["man"]),
                                  work / "audio" / cid / emo, cfg.tts_engine, cfg.kokoro_voice,
                                  _rate(req.speed, pace), f"{pitch:+d}Hz", f"{loud:+d}%")
        for (si, li, _), sa in zip(mine, takes):
            audio[(si, li)] = sa

    sfx = write_sfx(work / "sfx")
    sfx.update(media.uploaded_for(cfg, list(sfx), work / "sfx"))
    rel = lambda p: Path(p).relative_to(work).as_posix()  # noqa: E731
    shots, cues, spoken, used = [], [], [], {}
    place = [_scene_x(sc, short) for sc in ep.scenes]
    spacing = SHORT_GAP if short else SETS["spacing"]
    furniture = [[{"kind": p.kind, "x": round(place[si][p.spot]), "width": _piece_width(p.kind, p.seats, spacing)}
                  for p in (sc.furniture or _default_pieces(sc.setting))] for si, sc in enumerate(ep.scenes)]
    t = 0.0
    for si, li, ln in lines:
        scene = ep.scenes[si]
        sa = audio.get((si, li))
        lead = round(ln.pause_before, 2)
        talk = media_seconds(sa.path) if sa else 0.0
        duration = round(lead + (talk + 0.3 if sa else max(1.1, 0.9)), 3)
        words = [{"text": w.text, "start": round(w.start, 3), "end": round(w.end, 3)} for w in (sa.words if sa else [])]
        xs = place[si]
        things = [{"name": th.name.strip().lower()[:40] or "box", "x": round(xs[th.spot]), "table": th.on_table,
                   "big": th.big, "effect": th.effect} for th in ln.things]
        actors = [{"id": a.id, "x": round(xs[a.spot]), "pose": a.pose, "face": a.face,
                   "facing": 1 if a.facing == "right" else -1, "emote": a.emote, "prop": a.prop,
                   "propText": a.prop_text[:6],
                   "propThing": a.prop_thing.strip().lower()[:40], "action": a.action} for a in ln.actors if a.id in looks]
        shots.append({"start": round(t, 3), "duration": duration, "scene": si, "setting": scene.setting,
                      "sign": scene.sign or None,
                      "washing": scene.setting == "kitchen" and scene.washing, "furniture": furniture[si], "things": things, "caption": ln.caption or None, "camera": ln.camera,
                      "focus": ln.focus or None, "actors": actors,
                      "speaker": ln.speaker if sa else None, "emotion": ln.emotion, "text": ln.line if sa else None, "words": words,
                      "audio": rel(sa.path) if sa else None, "lead": lead})
        if sa:
            spoken += [(t + lead + w.start, t + lead + w.end) for w in sa.words]
            cues += media.resolve_cues([c for c in ln.sounds if c.word.strip() != "*"], sa.words, t + lead, cfg,
                                       work / "sfx", rel, 2, used)
        for c in [c for c in ln.sounds if c.word.strip() == "*"][:1]:
            cues += media.resolve_cues([c.model_copy(update={"word": "beat"})], [_Word("beat", lead, lead + 0.3)], t, cfg,
                                       work / "sfx", rel, 1, used)
        if li == 0 and si > 0 and "whoosh" in sfx:  # a new place: a whoosh on the cut
            cues.append({"src": rel(sfx["whoosh"]), "at": round(max(0.0, t - 0.1), 3), "volume": 0.4, "name": "whoosh"})
        t += duration
    t += 0.6
    # A track of its own for every video: composed in the mood Claude picked, from a fresh seed (key,
    # tempo, chords), following each scene's intensity; one of the user's tracks only when Claude picked it.
    choice = (ep.music or "compose").strip()
    mine = {m.name for m in media.music(cfg) if m.path is not None}
    if choice in mine:
        track = media.pick_music(cfg, choice, work / "music", t)
    elif choice == "none":
        track = None
    else:
        from . import music as composer

        starts = [next(s["start"] for s in shots if s["scene"] == si) for si in range(len(ep.scenes)) if any(s["scene"] == si for s in shots)]
        sections = [composer.Section(a, b, ep.scenes[si].intensity) for si, (a, b) in enumerate(zip(starts, [*starts[1:], t]))]
        (work / "music").mkdir(parents=True, exist_ok=True)
        track = composer.compose(ep.mood, sections, t, int(uuid.uuid4().int % 2**31), work / "music" / "score.wav")
        choice = f"composed ({ep.mood})"
    props = {
        "fps": cfg.fps, "duration": round(t, 3), "title": ep.title, "vertical": short,
        "cast": [{"id": c.id, "name": c.name, "look": c.look, "outfit": _outfits(ep.cast)[c.id]} for c in ep.cast],
        "shots": shots, "music": rel(track) if track else None, "musicChoice": choice, "cues": cues,
        "speech": media.speech_spans(spoken), "sfx": {k: rel(p) for k, p in sfx.items()},
    }
    props["sfxLevels"] = media.level_sounds(props, work, [s["audio"] for s in shots if s.get("audio")])
    return props


# ---------- the run ----------

def _history(cfg: Config) -> Path:
    return cfg.output_dir / "stick_history.json"


def run_stick(cfg: Config, req: StickRequest, progress: Progress = log.info) -> dict:
    from .fsutil import move
    from .llm import meter_records, summarize_usage
    from .pipeline import _render_slot, slugify

    short = req.format == "short"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    work = cfg.output_dir / f"{stamp}-{uuid.uuid4().hex[:4]}-stick-working"
    work.mkdir(parents=True, exist_ok=True)
    progress(f"Saving progress in {work.name}")
    try:
        recent = made_before(cfg)
        progress(("Claude is researching and writing" if req.style == "facts" else "Claude is writing")
                 + (" the Short" if short else " the episode"))
        ep = write_episode(cfg, req, recent)
        # A story too close to one already made is written again once (not when you gave the idea).
        twin = None if req.idea.strip() else too_close(ep, recent)
        if twin:
            progress(f"That story was already made (\"{twin.get('title')}\"); Claude is writing a different one")
            ep = write_episode(cfg, req, recent, avoid=f"\"{twin.get('title')}\": {twin.get('logline', '')}")
        # Remembered now, before voices and render: a video made at the same time sees it.
        remember(cfg, {"title": ep.title, "logline": ep.logline, "style": req.style,
                       "places": list(dict.fromkeys(sc.setting for sc in ep.scenes)), "music": ep.mood})
        fact_issues, findings, sources, dropped = [], [], [], []
        if req.style == "facts":
            ep, fact_issues, findings = check_facts(cfg, ep, progress)
            sources, dropped = verify_sources(ep.sources)
        (work / "episode.json").write_text(ep.model_dump_json(indent=2), encoding="utf-8")
        props = build(ep, req, cfg, work, progress)
        progress(f"Editing the video ({props['duration'] / 60:.1f} min)")
        cli = _remotion_cli()
        if cli is None:
            raise RuntimeError("Node.js or the Remotion packages are not installed (run start.bat / start.sh)")
        out = work / "reel.mp4"
        with _render_slot(cfg):
            _render_remotion(cli, props, out, composition="StickStory", crf=18, timeout=4 * 3600)
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", "2", "-i", str(out), "-frames:v", "1", "-q:v", "3",
                        str(work / "thumbnail.jpg")], check=False)
        progress("Verifying video quality")
        info = probe(out)
        want = (1080, 1920) if short else (1920, 1080)
        issues = list(fact_issues)
        if req.style == "facts" and not sources:
            issues.append("No source link could be opened; check the facts before posting.")
        if (info.get("width"), info.get("height")) != want:
            issues.append(f"Resolution is {info.get('width')}x{info.get('height')}, expected {want[0]}x{want[1]}.")
        if not info.get("has_audio"):
            issues.append("No audio track.")
        final = cfg.output_dir / f"{stamp}-{slugify(ep.title)}-stick"
        move(work, final)
        report = {
            "id": final.name, "format": "short" if short else "long", "length": "short" if short else "stick",
            "source": "stick", "topic": ep.title, "topic_source": "stick story",
            "style": {"facts": "facts", "fiction": "story"}.get(req.style, "comedy"),
            "category": ep.category if ep.category in CATEGORIES and req.style != "comedy"
            else {"fiction": "Stories", "facts": "Science & Space"}.get(req.style, "Comedy"),
            "title": ep.title, "why_chosen": ep.logline, "narration": " ".join(l.line for s in ep.scenes for l in s.lines if l.line),
            "created_at": stamp, "verified": not issues, "score": None, "issues": issues, "checks": {"probe": info},
            "attempts": 1, "video": str(final / "reel.mp4"), "thumbnail": str(final / "thumbnail.jpg"),
            "duration_seconds": round(props["duration"], 1), "editor": "remotion (StickStory)", "captions": False,
            "voice": req.language, "youtube_title": ep.title[:100],
            "youtube_description": with_sources(ep.youtube_description.strip(), sources, []), "youtube_hashtags": ep.hashtags[:3],
            "youtube_tags": ep.tags, "caption": ep.youtube_description.strip(), "hashtags": ep.hashtags,
        }
        if req.style == "facts":
            report.update({"fact_check": findings, "sources": sources, "sources_unreachable": dropped})
        (final / "props.json").write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
        report["usage"] = summarize_usage(meter_records())
        (final / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        remember(cfg, {"title": ep.title, "logline": ep.logline, "style": req.style,
                       "places": list(dict.fromkeys(sc.setting for sc in ep.scenes)), "music": props.get("musicChoice", "")})
        progress("Done" if not issues else "Done, but it did not pass every check — review before posting")
        return report
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        raise


def run_stick_job(cfg: Config, req: StickRequest, count: int, progress: Progress) -> list[dict]:
    """The app's job: `count` episodes or Shorts, one after another, in the shared video slot."""
    from .llm import set_limit_reporter, start_meter, usage_line
    from .pipeline import Paused, _video_slot, done_line, set_pause_check

    reports = []
    should_pause = getattr(progress, "should_pause", None)
    for i in range(count):
        vp = (lambda m, n=i + 1: progress(f"[V{n}] {m}")) if count > 1 else progress
        with _video_slot(cfg):
            if should_pause and should_pause():
                vp("§skip {}")
                continue
            set_pause_check(should_pause)
            set_limit_reporter(vp)
            start_meter(lambda r, vp=vp: vp(usage_line(r)))
            vp(f"=== Video {i + 1}/{count} ===")
            try:
                reports.append(run_stick(cfg, req, vp))
                vp(done_line(reports[-1]))
            except Paused:
                vp("Paused.")
            except Exception as exc:
                log.exception("Stick video %d failed", i + 1)
                vp(f"Video {i + 1} failed: {exc}")
    return reports


def voice_preview(cfg: Config, voice: str, speed: float, name: str = "") -> Path:
    """A short sample of a voice at a speed, for the tab's ▶ button (cached)."""
    if voice not in VOICE_NAMES:
        raise ValueError("Unknown voice")
    folder = cfg.output_dir / "voice_previews"
    out = folder / f"{voice}-{_rate(speed)}.wav"
    if not out.exists():
        line = f"Hi, I'm {name or VOICE_NAMES[voice].split(' ')[0]}. Wait... did someone eat my sandwich?"
        sa = synthesize_scenes([line], voice, folder / "tmp", cfg.tts_engine, cfg.kokoro_voice, _rate(speed))[0]
        folder.mkdir(parents=True, exist_ok=True)
        shutil.move(str(sa.path), out)
    return out
