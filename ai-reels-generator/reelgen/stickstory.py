"""Stick Stories: stick-figure comedy episodes (16:9, 3-8 min) and Shorts (9:16) for the channel's
own style, with a recurring cast. One Claude call writes the episode (fiction, no web search, no
fact-check): scenes in sets, every line with its speaker, pose, face, camera and sounds. Each
character gets their own voice (one take per character, cut per line, so mouths move on the words);
the Remotion composition `StickStory` (remotion/src/story/) draws it all in SVG.
"""

from __future__ import annotations

import json
import logging
import math
import re
import shutil
import subprocess
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal, get_args

from pydantic import BaseModel, Field

from . import aimusic, media, music
from .config import Config
from .llm import ask
from .categories import CATEGORIES
from .longform import LSource, verify_sources, with_sources
from .script_writer import AI_CLICHES, SoundCue
from .sfx import write_cue_sounds, write_sfx
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
                  "exam-hall", "blank", "mine", "tunnel", "garage", "warehouse"]
Camera = Literal["wide", "close", "punch", "push"]  # no "shake": the user wants no vibration; push = a very slow push-in
Action = Literal["none", "jump", "fall", "spin", "step", "walk-across", "turn", "look-up", "walk-in-left", "walk-in-right", "walk-out-left",
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
THING_HELP = ("drawn by hand: 'volcano' (a science-project volcano), 'dog', 'cat', 'bird', 'car', 'bus', 'bike', 'truck' "
              "(vehicles stand on the ground); or a lucide icon name in kebab-case for anything else: trophy, cake, pizza, "
              "tv, gift, rocket, guitar, gamepad-2, lamp, plant, alarm-clock, microscope, flask-conical, crown, briefcase...")


class SThing(BaseModel):
    name: str = Field(description="What it is: " + THING_HELP)
    spot: Spot = Field(description="Where it stands: a spot no one stands on, next to who uses it.")
    on_table: bool = Field(default=True, description="On a small table (true) or on the floor (false).")
    big: bool = False
    effect: Effect = Field(default="none", description="What it does during this line: erupt (a volcano's lava), smoke, fire, sparkle, shake.")
    svg: str = Field(default="", description="Only when nothing built in shows it: your own drawing of it (see Drawings).")
    photo: str = Field(default="", description="A real picture as proof (see Proof pictures): Wikimedia Commons search "
                       "words, e.g. 'Google logo 2010', 'YouTube logo 2005', 'San Diego Zoo elephants'.")

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
# Types written from researched facts (web search, every claim checked, sources in the description).
TRUE_STYLES = ("facts", "documentary")
# The documentary type follows the user's "Stickman Explainer Engine" prompt: a narration beat of about 9-10 words
# for every ~4-second shot, so the number of shots follows the length (15 s = 4, 30 s = 8, 60 s = 15).
BEAT_SECONDS = 4
DOC_LEAD, DOC_TAIL = 0.15, 0.2  # a documentary beat's pause before and after its line (seconds)


def beats_for(seconds: float) -> int:
    return max(3, math.ceil(seconds / BEAT_SECONDS))


# What may be drawn (the engine's visual safety rule): the narration can carry real names and facts, the picture never
# needs them. For every type; the documentary type leans on it most.
VISUAL_SAFETY = ("What is drawn (signs, captions, objects, props) never names a real person and never draws a real brand, "
                 "logo, military insignia or a flag in a conflict (a real logo or photo only as a proof picture, below); a place tied to a tragedy stays generic ('a city', 'a "
                 "coastal road'). Never show violence, injury, death, blood, a weapon being used or anyone being harmed: "
                 "show the moment before, the aftermath far away, or an object standing in for it (an empty chair, a "
                 "closed door, a stopped clock, smoke on the horizon). Disaster only as a distant silhouette or "
                 "aftermath. Keep it restrained: understatement carries more weight than spectacle.")

# Places and objects the app has no drawing for are drawn by Claude at runtime (like Toon's custom drawings), as SVG
# that toon.clean_svg reduces to plain shapes before it reaches the editor.
DRAWINGS = ("Drawings: the settings, furniture and drawn objects above are the app's own and look best; use them "
            "whenever they fit. When the story needs a place none of them shows (a courtroom, a ship's deck, a rocket "
            "factory, a 1990s office, a castle hall), set the scene's setting to 'blank' and draw its background in "
            "'backdrop_svg': an SVG fragment (no <svg> wrapper) for a 1920x900 box whose floor line is y=900, people "
            "stand in front of it, so keep the lower 300 px plain (wall or ground) and put the detail higher up. For an "
            "object nothing shows, draw it in the thing's 'svg': a 200x200 box, standing on its bottom edge. Style: "
            "hand-inked and flat, thick dark outlines (stroke #1E1B18, width 4-6), solid fills in muted earthy colours "
            "(tan #C8B893, sage #A9AE8A, dusty grey #B9B5AA, cream #E6DCC2, brick #9C4A3C, navy #34435E, olive "
            "#6E6F45, brown #7E5E3E), simple geometric shapes, sparse detail; only path, circle, ellipse, rect, "
            "polygon, polyline, line and g; no text, logos, images or gradients; a background under 5000 characters, "
            "an object under 1500. Never draw a real person, brand or logo.")

# Real pictures as proof (evidence.py): Wikimedia Commons files with a free licence, credited in the description.
PROOF = ("Proof pictures: when a real image proves or names what the line says better than a drawing (a company buying "
         "another: both companies' logos of that time; the real building or place; a document, a newspaper front page, "
         "the product as it looked), add a thing with `photo` = Wikimedia Commons search words, the era included ('YouTube "
         "logo 2005', 'Google logo 2010', 'Googleplex building'). It appears as a pinned photo card in the scene, and its "
         "credit goes in the description. Use it where it adds proof (a few per video), not for every line; logos, places, "
         "objects and documents, never violence; a real person only when the narration names them.")

DOC_SHOTS = ("Every beat is one shot with ONE clear, plain action, never several: a character's step forward ('step'), "
             "walking across the frame ('walk-across'), a head turn ('turn'), looking up ('look-up'), sitting down, "
             "picking up or putting down an object, or the scene itself moving (dust, smoke or rain drifting, the light "
             "turning to dusk). Vary the shots across the video and never repeat one twice in a row: a very wide "
             "establishing shot (people 'far', often 'from_behind' facing the place), a wide shot, a close-up ('close' "
             "on a face), a profile (facing across the frame), someone seen from behind, a very slow push-in ('push'). "
             "Give every scene its weather, light and ambience (wind, rain, room tone, city, night...) from its place "
             "and time. The main character is designed for the story's era and work (clothes by garment and colour) "
             "and keeps that look; others are generic people ('a man in a dark suit'), never a real person's likeness. "
             "No captions; a sign only with a generic word.")


@dataclass
class StickRequest:
    idea: str = ""
    format: str = "long"  # long (16:9 episode) | short (9:16)
    minutes: float = 5.0
    language: str = "english"
    speed: float = 1.5  # how fast everyone talks: 1.5 = 50% faster than normal (snappy comedy timing)
    seconds: int = 0  # a Short's length: 15, 30 or 45 s (0 = 25-50 s)
    style: str = "comedy"  # comedy | fiction (a story with a twist) | facts (true, researched, fact-checked) | documentary (narrated true story)
    cast: str = DEFAULT_CAST
    subtitles: str = "auto"  # auto (on, off for documentaries) | on | off
    opening: str = "auto"  # how the first line hooks: a key of OPENINGS, or auto (the writer picks one the last videos didn't use)


# The Stick tab's opening (hook) choice: the kinds of first line hooks.RULES describes, one asked for by name.
OPENINGS = {
    "shock": "a shocking number or fact, said in the first words",
    "claim": "a bold claim the video then proves",
    "action": "a cold open: the most dramatic moment already happening, explained after",
    "contradiction": "a contradiction or paradox the viewer needs resolved",
    "question": "a stakes question the viewer can't leave without the answer to",
    "countdown": "a countdown or a deadline: time running out",
    "you": "'you' in the situation: the viewer put inside the moment",
    "ending": "the ending first, then how it got there",
}


# ---------- the episode Claude writes ----------

# ---------- how each character looks (the ink look: remotion/src/story/ink.tsx) ----------
# Muted, desaturated cloth colours (the hand-inked explainer style the user chose), by name for Claude.
INK_COLOURS = {
    "navy": "#34435E", "brick": "#9C4A3C", "olive": "#6E6F45", "mustard": "#B8914A", "teal": "#3E6B6A",
    "plum": "#6B4A5E", "rust": "#A0613A", "slate": "#5B6670", "sand": "#C9B48E", "forest": "#3F5A45",
    "charcoal": "#3A3A3D", "cream": "#E6DCC6", "denim": "#4C5D74", "maroon": "#6E3434", "khaki": "#A29470",
    "grey": "#8C8C88", "tan": "#A08458", "brown": "#5A4232", "black": "#1E1B18", "white": "#EDE6D6",
}
HAIR_COLOURS = {"black": "#1E1B18", "dark-brown": "#3B2E24", "brown": "#5A3E2B", "auburn": "#7A3E2A",
                "blonde": "#B89A5E", "grey": "#8E8A84", "white": "#D8D2C4"}
Colour = Literal[tuple(INK_COLOURS)]


class SDesign(BaseModel):
    hair: Literal["messy", "spiky", "side-part", "curly", "short", "long", "ponytail", "bun", "braids", "bald"]
    hair_colour: Literal[tuple(HAIR_COLOURS)] = "black"
    top: Literal["hoodie", "tshirt", "shirt", "jacket", "suit", "sweater", "coat", "dress", "coveralls", "kurta"] = Field(
        description="What they wear on top (coveralls and a dress cover the legs too).")
    top_colour: Colour
    bottom: Literal["trousers", "jeans", "shorts", "skirt", "none"] = Field(description="'none' under a dress.")
    bottom_colour: Colour = "charcoal"
    shoes: Literal["shoes", "boots", "sneakers", "sandals"] = "shoes"
    shoes_colour: Colour = "brown"
    headwear: Literal["none", "cap", "hard-hat", "beanie", "fedora", "cowboy", "helmet", "chef-hat", "headscarf", "beret",
                      "bow", "headband"] = "none"
    headwear_colour: Colour = "mustard"
    extras: list[Literal["glasses", "sunglasses", "beard", "stubble", "mustache", "earrings", "tie", "scarf", "satchel",
                         "backpack", "apron", "lanyard", "stethoscope", "watch", "headlamp"]] = Field(
        default_factory=list, description="0-3 things that make them recognisable at a glance (a miner: satchel, headlamp).")
    extra_colour: Colour = Field(default="tan", description="The tie, scarf, bag or apron's colour.")


DESIGN_RULES = ("Design every character's look for this story ('design'): what this person would really wear here "
                "(job, age, era, weather, place): a miner in navy coveralls with a hard hat, a headlamp, a satchel and "
                "boots; a teacher in a sweater with glasses; a chef in a chef hat and an apron. Muted colours only, every "
                "character's top a different colour so they're told apart at a glance, and one or two details that make "
                "each recognisable. A character listed with a fixed look keeps it exactly (copy it); a description the "
                "user gave is followed.")


class SCast(BaseModel):
    id: str = Field(description="Short lowercase id, e.g. 'raju'.")
    name: str
    look: Look
    design: SDesign | None = Field(default=None, description="How they look (always give it).")


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
    action: Action = Field(default="none", description="Movement during this line: enter or leave the scene, jump, fall, spin, "
                           "'step' (one step forward: into the picture when seen from behind), 'walk-across' (across the "
                           "frame the way they face), 'turn' (turns to face the other way halfway), 'look-up'.")
    from_behind: bool = Field(default=False, description="Seen from behind (no face): someone facing a place or walking into it.")
    far: bool = Field(default=False, description="Small and far away, for a very wide establishing shot (the 'mine' setting puts "
                      "them at the mine's mouth).")


class SLine(BaseModel):
    speaker: str = Field(description="The cast id saying this line, 'narrator' for a voice-over (facts and stories), "
                         "or 'none' for a silent beat (a reaction, a look, a pause).")
    line: str = Field(default="", description="What they say, spoken naturally, max 22 words. Empty for a silent beat.")
    emotion: Emotion = Field(default="neutral", description="How it's said (the voice changes pace, pitch and loudness); "
                             "match the speaker's face.")
    pause_before: float = Field(default=0.2, ge=0, le=1.5, description="Seconds of silence before it: 0.6-1.2 before a punchline or a reaction.")
    camera: Camera = Field(default="wide", description="'wide' most of the time, 'close' on a reaction, 'punch' on a "
                           "punchline or a shock, 'push' for a very slow push-in on a quiet, weighty moment.")
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
    backdrop_svg: str = Field(default="", description="Only when no setting shows the place: setting 'blank' and your own "
                              "drawing of its background (see Drawings).")
    weather: Literal["none", "rain", "snow", "dust", "smoke"] = Field(default="none", description="What drifts through "
                                                                       "the scene (outdoors, or smoke anywhere).")
    light: Literal["day", "dawn", "dusk", "night"] = "day"
    ambience: Literal[tuple(music.AMBIENCES)] = Field(default="none", description="A quiet background sound for the "
                                                       "place: wind outdoors, rain, room tone, city, night, crowd...")
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
    music_prompt: str = Field(default="", description=aimusic.PROMPT_FIELD)
    cast: list[SCast] = Field(description="The characters in this episode (from the given cast; add a minor one only if needed).")
    category: str = Field(default="", description="The library shelf: one of " + ", ".join(CATEGORIES) + ".")
    sources: list[LSource] = Field(default_factory=list, description="Facts only: 2-6 pages you opened with web search "
                                   "that confirm every figure, date and name. Empty for comedy and stories.")
    scenes: list[SScene]


def _system(short: bool, minutes: float, language: str, style: str = "comedy", seconds: int = 0) -> str:
    lang = ("natural, casual American English, the way kids, teens and parents really talk (no Indian or British "
            "words, no rupees: dollars, US schools, US homes)" if language == "english"
            else "everyday Hindi in Devanagari script, as families really talk")
    payoff = {"comedy": "punchline", "fiction": "twist", "facts": "answer", "documentary": "closing line"}.get(style, "punchline")
    hook = {"comedy": "with a 'POV:' caption", "fiction": "with someone already in trouble",
            "facts": "with a surprising question or a wrong belief someone holds",
            "documentary": "with the most striking true detail, in plain words"}.get(style, "")
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
    if style == "documentary":
        secs = (seconds or 45) if short else minutes * 60
        n = beats_for(secs)
        rest = secs - (n - 1) * BEAT_SECONDS
        form = (f"a YouTube Short (9:16) of {secs:g} seconds: exactly {n} beats" if short
                else f"a {minutes:g}-minute YouTube documentary (16:9): about {n} beats in 4-8 scenes") + (
            f", each beat one line of about 9-10 spoken words (one ~4-second shot)"
            + (f"; the last beat shorter, about {max(3, round(rest * 2.4))} words" if short and rest < BEAT_SECONDS else "")
            + (". At most 3 characters on screen." if short else "."))
        brief = f"""You make narrated, hand-inked stick-figure documentaries for the channel Stickcident: one real, \
researchable story from history, documentary, true crime or remarkable true events (no invented events, no \
conspiracy premises), chosen for strong visual beats that can be shown without depicting violence. You write {form}

Research first: search the web and open the pages. Every name, date, figure and cause the narrator says must be on a \
page you opened, and those pages go in 'sources'; where something is genuinely disputed, say so rather than \
flattening it. Stories with real victims stay factual and restrained: no gore, no dramatised suffering.

The narration carries the story: every line's speaker is 'narrator' (the cast never speaks; they act it out \
silently), one beat per line, written plainly and conversationally in short sentences. The first beat hooks the \
viewer ({hook}); the middle beats carry the story forward one idea at a time; the last beat lands the closing line. \
No sponsor copy, no subscribe prompts, no sign-offs. The tone is restrained and slightly melancholy (music mood calm, \
emotional or mystery).

{DOC_SHOTS}"""
    elif style == "facts":
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
    if style == "documentary":  # a calm narrator, quiet acting, real people named only in the narration
        return f"""{brief}

The narration is in {"clear, natural American English" if language == "english" else "clear, natural Hindi in Devanagari script"}, \
read at a calm pace (emotion 'neutral', 'sad' or 'whisper' where it fits). The cast acts quietly: faces and poses \
show the feeling (concerned, surprised, weary, resolved), no comic emotes, jumps or falls for laughs.

No politics, religion, rumours or insults. Real people can be named in the narration when the sources do; the \
drawings stay generic. {VISUAL_SAFETY} Never use these phrases: {", ".join(AI_CLICHES)}.

Pick the setting each shot needs (living room, classroom, exam hall, office, street, park, shop, bedroom, \
bathroom, kitchen, 'mine': a desert mountainside with a mine entrance, 'tunnel': underground, a mine tunnel or shelter with timber supports and lamps, 'garage': a suburban garage with shelves of boxes (where a business starts), 'warehouse': tall racks of boxes and a moving conveyor (a business at scale); 'blank' only when no place fits) and its furniture. {_furniture_help()} \
Keep spots steady within a scene; use walk-in/walk-out for entrances and exits and change the setting for a new \
place. Show the real object, never a paper with its name; things stand on a table or the floor, held ones as prop \
'thing' with prop_thing. {DESIGN_RULES}

{DRAWINGS}

{PROOF}"""
    return f"""{brief}

The dialogue is in {lang}. The cast talks fast (about 1.5x normal speed), so write snappy lines; let silence and reactions do work (silent beats with \
speaker 'none', a 0.6-1.2 s pause before a punchline, the camera punching in or closing on a reaction). Show \
emotion with poses, faces and emotes: a facepalm, a shocked face with '!', sweat when nervous, a jump for joy, \
someone falling over when stunned. Every spoken line has an emotion (the voice follows it) that matches the \
speaker's face: angry and shouting lines with '!', sad ones slower with '...', laughing, excited, scared, sarcastic, \
whispering. Vary it: a scene where everyone is neutral is flat.

Clean and family-friendly, something anyone can relate to. No politics, religion, real people, brands, insults \
about groups, or anything mean-spirited. {VISUAL_SAFETY} Never use these phrases: {", ".join(AI_CLICHES)}.

The lines appear as small subtitles under the scene, so keep each one short (a few words to one sentence). \
Pick the setting each scene needs (living room, classroom, exam hall, office, street, park, shop, bedroom, \
bathroom, kitchen, or 'mine': a desert mountainside with a mine entrance, for a very wide opening with far-away figures) and vary it between episodes: don't open in the same place as the recent episodes listed. \
Washing dishes at the sink is one situation among many, only when the story is about it (set 'washing').

Staging: every line lists everyone on screen with their spot, pose, face and facing (toward who they talk \
to). Whoever is sitting in the story (on the couch, watching TV, at a desk, waiting) has pose 'sit' on every line \
until they stand up, on a spot covered by a seat (or a stool is drawn under them). {_furniture_help()}

Show the real object, never a paper with its name: a science project is a 'volcano' thing (effect 'erupt' when it \
goes off), a birthday has a cake, a prize a trophy. Use things for objects in the scene and prop 'thing' with \
prop_thing for something held. Paper is only for a test, a note or a report card. {DESIGN_RULES} Keep spots steady within a scene. Use walk-in/walk-out actions for entrances and exits, and change the \
setting for a new scene.

{DRAWINGS}

{PROOF}"""


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


# Each character's design is kept by name (<output>/stick_cast.json), so a recurring character looks the
# same in every episode; a new description typed in the tab gives them a new look.
def _cast_file(cfg: Config) -> Path:
    return cfg.output_dir / "stick_cast.json"


def _saved_cast(cfg: Config) -> dict:
    try:
        return json.loads(_cast_file(cfg).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def kept_designs(cfg: Config, cast: list[dict]) -> dict[str, SDesign]:
    """The saved design of every cast member whose description hasn't changed since it was made."""
    saved, out = _saved_cast(cfg), {}
    for c in cast:
        row = saved.get(_key(c["name"]))
        if row and row.get("look") == c["look"] and row.get("about", "") == c.get("about", ""):
            try:
                out[c["id"]] = SDesign(**row["design"])
            except Exception:  # a design from an older schema: made again
                pass
    return out


def lock_designs(cfg: Config, ep: "Episode", cast: list[dict]) -> None:
    """Fixed looks win over what Claude wrote; new ones are saved for the next episodes."""
    kept = kept_designs(cfg, cast)
    about = {c["id"]: c.get("about", "") for c in cast}
    with _history_lock:
        saved = _saved_cast(cfg)
        for c in ep.cast:
            if c.id in kept:
                c.design = kept[c.id]
                continue
            row = saved.get(_key(c.name))
            if c.id not in about and row and row.get("look") == c.look:  # a minor character met before
                try:
                    c.design = SDesign(**row["design"])
                    continue
                except Exception:
                    pass
            if c.design is not None:
                saved[_key(c.name)] = {"name": c.name, "look": c.look, "about": about.get(c.id, ""),
                                       "design": c.design.model_dump()}
        _cast_file(cfg).write_text(json.dumps(saved, ensure_ascii=False, indent=1), encoding="utf-8")


def ink_design(d: "SDesign | None", look: str, i: int) -> dict | None:
    """The editor's design (types.ts Design): colours as hex. None = the editor's default for the look."""
    if d is None:
        return None
    c = INK_COLOURS
    return {"hair": d.hair, "hairColour": HAIR_COLOURS.get(d.hair_colour, "#1E1B18"), "top": d.top,
            "topColour": c[d.top_colour], "bottom": "none" if d.top == "dress" else d.bottom,
            "bottomColour": c[d.bottom_colour], "shoes": d.shoes, "shoesColour": c[d.shoes_colour],
            "headwear": d.headwear, "headwearColour": c[d.headwear_colour], "extras": list(dict.fromkeys(d.extras)),
            "extraColour": c[d.extra_colour]}


def parse_cast(text: str) -> list[dict]:
    """'Name - look', then optionally a voice id (from VOICE_NAMES; empty = automatic) and how they look in
    words ('Ben - boy - navy hoodie, messy hair'), one character per line."""
    out = []
    for row in (text or DEFAULT_CAST).splitlines():
        if not row.strip():
            continue
        parts = [p.strip() for p in row.split(" - ")]
        if len(parts) == 1 and "-" in row:  # 'Ben-boy' written without spaces
            parts = [p.strip() for p in row.split("-", 1)]
        name, look = parts[0], (parts[1].lower() if len(parts) > 1 else "boy")
        voice = next((x for x in parts[2:] if x in VOICE_NAMES), "")
        about = ", ".join(x for x in parts[2:] if x and x not in VOICE_NAMES)  # how they look, in the user's words
        out.append({"id": re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or f"c{len(out)}",
                    "name": name, "look": look if look in get_args(Look) else "boy", "voice": voice, "about": about})
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
    kept = kept_designs(cfg, cast)
    if req.style == "documentary":  # a true story has its own people, dressed for its time and place
        roster = ("The cast: design the people this true story needs, 1-3 (the main character first), ids like 'miner' "
                  "or 'officer', names as roles ('The miner'), each with a design for the era and the work; generic "
                  "people, never a real person's likeness. The channel's recurring cast doesn't appear.")
    else:
        roster = "The cast (use these ids and looks):\n" + "\n".join(
            f"- {c['id']}: {c['name']} ({c['look']})"
            + (f", fixed look: {kept[c['id']].model_dump_json()}" if c["id"] in kept
               else f", looks like: {c['about']}" if c.get("about") else "") for c in cast)
    prompt = (roster
              + (f"\n\nThe idea: {req.idea}" if req.idea.strip() else "\n\nPick a fresh, relatable situation yourself.")
              + ("\n\nAlready made (never repeat one of these stories, not even with a new title or another "
                 "character; also avoid their opening place and music mood):\n"
                 + "\n".join(f"- {_recent_line(r)}" for r in recent[-40:]) if recent else "")
              + (f"\n\nYour first draft repeated an earlier video ({avoid}). Write a completely different situation."
                 if avoid else "")
              + "\n\n" + media.prompt_block(cfg))
    from .hooks import block as hook_block

    prompt += hook_block(cfg)
    if req.style in TRUE_STYLES:  # every search result stays in the context and is re-read on every later turn
        prompt += ("\n\nResearch budget: at most 5 web searches and 4 opened pages in all. Find 2-4 solid sources "
                   "early, take every figure, date and name from them, and stop searching (a 3-minute video's writing "
                   "once cost 1.2M tokens with open-ended research).")
    if req.opening in OPENINGS:  # chosen on the Stick tab: this kind of opening, whatever the last videos used
        prompt += f"\n\nOpen with this kind of hook: {OPENINGS[req.opening]}. Only facts the video states."
    return ask(cfg.ai_backend, cfg.claude_model, _system(short, req.minutes, req.language, req.style, req.seconds), prompt, Episode,
               allow_web=req.style in TRUE_STYLES, effort=cfg.claude_effort, timeout=1800)


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


def fact_check_episode(cfg: Config, ep: Episode, only: set[str] | None = None, notes: list[dict] | None = None) -> EpisodeCheck:
    """Every factual line checked against the web on the fact-check model (`only`: just these refs)."""
    rows = [f"{r}{' >>' if only and r in only else ''} [{ln.speaker}] {ln.line}"
            + (f" (caption: {ln.caption})" if ln.caption else "")
            + "".join(f" (on screen: {a.prop_text})" for a in ln.actors if a.prop_text)
            for r, ln in _refs(ep).items() if ln.line.strip() or ln.caption]
    signs = [f"Scene {i + 1} sign: {sc.sign}" for i, sc in enumerate(ep.scenes) if sc.sign]
    system = ("You fact-check a short educational stick-figure video. Search the web and open reliable pages. A line "
              "is confirmed only if a source you opened says the same; a figure must match (rounding is fine if the "
              "line says 'about'). Jokes, reactions and obvious fiction about the characters aren't claims. Budget: "
              "open the writer's sources first and confirm what they cover; search only for claims they don't, at most "
              "6 searches and 6 pages in all (open-ended research made one 3-minute video's check cost 1.2M tokens).")
    prompt = (f"Title: {ep.title}\nThe writer's sources: " + "; ".join(f"{x.title} {x.url}" for x in ep.sources)
              + ("\n\nCheck only the lines marked >> (the rest was checked before)." if only else "")
              + ("\n\nWhat the first check found (your evidence: the corrected lines were rewritten from it):\n"
                 + "\n".join(f"{n['ref']}: {n['verdict']}: {n.get('note', '')}" for n in notes) if notes else "")
              + "\n\n" + "\n".join(rows + signs))
    if notes:
        system += (" This is a re-check without web search: the first check's findings below are your sources. Confirm a "
                   "rewritten line when they support it; mark it unsupported only when they don't.")
    # A re-check of lines rewritten from the first check's findings needs no new search: those findings are the
    # evidence (the user's 3-minute Facts video re-checked 7 lines with web search: the check cost 903k tokens).
    return ask(cfg.ai_backend, cfg.fact_model, system, prompt, EpisodeCheck, allow_web=not notes,
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
        notes = [f for f in findings if f.get("ref") in rewritten]
        for c in fact_check_episode(cfg, ep, only=rewritten, notes=notes).lines:
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


def board_rules(short: bool, style: str = "documentary") -> str:
    """What the storyboard pass (stickboard.storyboard) may use: the sets, furniture, objects, drawings and rules."""
    return (f"Settings: living-room, classroom, exam-hall, office, street, park, shop, bedroom, bathroom, kitchen, "
            f"'mine' (a desert mountainside with a mine entrance), 'tunnel' (underground), 'garage' (shelves of boxes), "
            f"'warehouse' (racks and a conveyor), 'blank' (with backdrop_svg: your own drawing). {_furniture_help()}\n"
            f"Spots: far-left, left, center, right, far-right" + (" (a Short: at most 3 people, left/center/right)" if short else "")
            + f". Objects ('things'): {THING_HELP}\n" + (DOC_SHOTS + "\n" if style == "documentary" else "")
            + f"{VISUAL_SAFETY}\n{DRAWINGS}\n{PROOF}")


def close_gaps(cfg: Config, ep: "Episode", hook_at: tuple[int, int] | None, progress: Progress, issues: list[str]) -> "Episode":
    """A documentary is narrated beat by beat, so a line the fact-check cut leaves a dead, silent shot: those are
    dropped (and a scene left empty with them). When the cut line was the hook, the new first line is rewritten as
    a hook from the facts that passed (one small call, no new facts) and checked once more; if that new hook can't
    be confirmed, the first line stays as it was. (The Amazon test opened on a silent shot after its hook was cut.)"""
    hook_cut = hook_at is not None and not ep.scenes[hook_at[0]].lines[hook_at[1]].line.strip()
    for sc in ep.scenes:
        sc.lines = [ln for ln in sc.lines if ln.line.strip()]
    ep.scenes = [sc for sc in ep.scenes if sc.lines]
    if not hook_cut or not ep.scenes:
        return ep
    first = ep.scenes[0].lines[0]
    beats = [(si, ln) for si, sc in enumerate(ep.scenes) for ln in sc.lines]
    numbered = "\n".join(f"{k}. {ln.line}" for k, (_, ln) in enumerate(beats))
    from .hooks import RULES

    class NewHook(BaseModel):
        line: str = Field(description="The new first line.")
        picture: int = Field(description="The number of the beat whose picture best shows what the hook says.")

    system = ("You write the first narration beat of a short narrated documentary so it hooks in under 3 seconds. " + RULES
              + "\nUse ONLY facts stated in the numbered narration you are given (they are checked); add nothing. About "
              "9-12 words. Also pick the beat whose picture shows what your hook is about.")
    try:
        got = ask(cfg.ai_backend, cfg.claude_model, system, f"Title: {ep.title}\nThe narration:\n{numbered[:3000]}\n"
                  f"Write a hook line to open it, placed before beat 0.", NewHook, effort="low", timeout=300)
        new = got.line.strip()
    except Exception as exc:  # noqa: BLE001 - the video still opens on its first confirmed line
        from .stopper import Paused
        if isinstance(exc, Paused):
            raise
        log.warning("Couldn't write a new hook: %s", exc)
        return ep
    if not new:
        return ep
    # The hook opens on the picture of the beat it's about, in that beat's place, held still (no walk that starts
    # off screen: the first Amazon fix opened on an empty office).
    si, like = beats[got.picture] if 0 <= got.picture < len(beats) else (0, first)
    still = [a.model_copy(update={"action": "none" if a.action.startswith("walk") else a.action}) for a in like.actors]
    hook = like.model_copy(update={"line": new, "actors": still, "pause_before": 0.1, "sounds": []})
    ep.scenes.insert(0, ep.scenes[si].model_copy(update={"lines": [hook]}))
    check = fact_check_episode(cfg, ep, only={"S1L1"})
    if any(c.ref == "S1L1" and c.verdict != "confirmed" for c in check.lines):
        ep.scenes.pop(0)
        issues.append("The hook was cut by the fact-check and a new one couldn't be confirmed: the video opens on its first confirmed line.")
    else:
        progress(f"The hook was cut by the fact-check; new hook from the confirmed facts: \"{new}\"")
    return ep


# ---------- from the episode to the editor's props ----------

def build(ep: Episode, req: StickRequest, cfg: Config, work: Path, progress: Progress,
          keep_music: tuple[Path, str] | None = None) -> dict:
    """`keep_music` (a re-make): this track and its label instead of a new one (it loops when the video grows)."""
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
    doc = req.style == "documentary"

    def record(speed: float, folder: str) -> None:
        # One take per character and emotion, cut per line: a character keeps one voice, and an angry line
        # is louder and lower while a sad one is slower and quieter.
        for cid, emo in sorted({(ln.speaker, ln.emotion) for _, _, ln in lines if ln.speaker in speakers and ln.line.strip()}):
            mine = [(si, li, ln) for si, li, ln in lines if ln.speaker == cid and ln.emotion == emo and ln.line.strip()]
            pace, pitch, loud = EMOTIONS.get(emo, (0, 0, 0))
            takes = synthesize_scenes([ln.line for _, _, ln in mine], voice_of.get(cid, voices["man"]),
                                      work / folder / cid / emo, cfg.tts_engine, cfg.kokoro_voice,
                                      _rate(speed, pace), f"{pitch:+d}Hz", f"{loud:+d}%")
            for (si, li, _), sa in zip(mine, takes):
                audio[(si, li)] = sa

    record(req.speed, "audio")
    # A documentary Short keeps to its length (the engine's 4-second beats): narration that runs over by more than
    # 8% is recorded once more, faster by the overshoot (at most 1.3x), with the shots' pauses trimmed below.
    if doc and short:
        target = req.seconds or 45
        spoken_s = sum(min(ln.pause_before, DOC_LEAD) + media_seconds(audio[(si, li)].path) + DOC_TAIL
                       for si, li, ln in lines if (si, li) in audio)
        if spoken_s > target * 1.08:
            faster = min(req.speed * 1.3, req.speed * spoken_s / target)
            progress(f"The narration ran {spoken_s:.0f} s for a {target} s Short: recording it again at {faster:.2f}x")
            record(faster, "audio-fit")

    sfx = write_sfx(work / "sfx")
    sfx.update(media.uploaded_for(cfg, list(sfx), work / "sfx"))
    rel = lambda p: Path(p).relative_to(work).as_posix()  # noqa: E731
    shots, cues, spoken, used = [], [], [], {}
    steps = None  # the footsteps sound, written the first time a documentary needs it
    place = [_scene_x(sc, short) for sc in ep.scenes]
    spacing = SHORT_GAP if short else SETS["spacing"]
    furniture = [[{"kind": p.kind, "x": round(place[si][p.spot]), "width": _piece_width(p.kind, p.seats, spacing)}
                  for p in (sc.furniture or _default_pieces(sc.setting))] for si, sc in enumerate(ep.scenes)]
    # Claude's own drawings, reduced to plain shapes (no scripts, links, images, styles or text).
    from .toon import clean_svg

    def art(svg: str, uid: str, limit: int, shapes: int) -> str | None:
        return clean_svg(svg, uid, limit, shapes) or None if (svg or "").strip() else None

    backdrops = [art(sc.backdrop_svg, f"b{si}", 6000, 260) for si, sc in enumerate(ep.scenes)]
    # Proof pictures from Wikimedia Commons, one download per search, credited in the description.
    from . import evidence

    # What was found is kept in evidence/index.json: a second build (after the picture check, or a re-make at
    # another speed) uses the same pictures without searching again.
    index_file = work / "evidence" / "index.json"
    try:
        cache = json.loads(index_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    found: dict[str, dict | None] = {}
    credits: list[str] = []

    def proof(words: str) -> dict | None:
        key = (words or "").strip().lower()
        if not key:
            return None
        if key not in found:
            hit = cache.get(key)
            if hit and (work / hit["src"]).exists():
                found[key] = {k: hit[k] for k in ("src", "w", "h")}
                credits.append(hit["credit"])
                return found[key]
            pic = evidence.find(key, work / "evidence", f"e{len(cache):02d}")
            found[key] = {"src": rel(pic.path), "w": pic.width, "h": pic.height} if pic else None
            if pic:
                credits.append(pic.credit())
                cache[key] = {**found[key], "credit": pic.credit()}
                index_file.write_text(json.dumps(cache, indent=1, ensure_ascii=False), encoding="utf-8")
                progress(f"Proof picture: {pic.title.removeprefix('File:')} ({pic.licence})")
        return found[key]

    t = 0.0
    for si, li, ln in lines:
        scene = ep.scenes[si]
        sa = audio.get((si, li))
        lead = round(min(ln.pause_before, DOC_LEAD) if doc else ln.pause_before, 2)
        talk = media_seconds(sa.path) if sa else 0.0
        duration = round(lead + (talk + (DOC_TAIL if doc else 0.3) if sa else max(1.1, 0.9)), 3)
        words = [{"text": w.text, "start": round(w.start, 3), "end": round(w.end, 3)} for w in (sa.words if sa else [])]
        xs = place[si]
        things = [{"name": th.name.strip().lower()[:40] or "box", "x": round(xs[th.spot]), "table": th.on_table,
                   "big": th.big, "effect": th.effect, "svg": art(th.svg, f"t{si}-{k}", 1500, 80),
                   "photo": proof(th.photo)} for k, th in enumerate(ln.things)]
        actors = [{"id": a.id, "x": round(xs[a.spot]), "pose": a.pose, "face": a.face,
                   "facing": 1 if a.facing == "right" else -1, "emote": a.emote, "prop": a.prop,
                   "propText": a.prop_text[:6],
                   "propThing": a.prop_thing.strip().lower()[:40], "action": a.action,
                   "back": a.from_behind, "far": a.far} for a in ln.actors if a.id in looks]
        shots.append({"start": round(t, 3), "duration": duration, "scene": si, "setting": scene.setting,
                      "sign": scene.sign or None,
                      "washing": scene.setting == "kitchen" and scene.washing, "furniture": furniture[si], "things": things, "caption": ln.caption or None, "camera": ln.camera,
                      "focus": ln.focus or None, "actors": actors, "weather": scene.weather, "light": scene.light,
                      "backdropSvg": backdrops[si],
                      "speaker": ln.speaker if sa else None, "emotion": ln.emotion, "text": ln.line if sa else None, "words": words,
                      "audio": rel(sa.path) if sa else None, "lead": lead})
        if sa:
            spoken += [(t + lead + w.start, t + lead + w.end) for w in sa.words]
            cues += media.resolve_cues([c for c in ln.sounds if c.word.strip() != "*"], sa.words, t + lead, cfg,
                                       work / "sfx", rel, 2, used)
        for c in [c for c in ln.sounds if c.word.strip() == "*"][:1]:
            cues += media.resolve_cues([c.model_copy(update={"word": "beat"})], [_Word("beat", lead, lead + 0.3)], t, cfg,
                                       work / "sfx", rel, 1, used)
        # Footsteps under a step or a walk (documentaries, whose sound is the place's own).
        if req.style == "documentary" and any(a["action"] in ("step", "walk-across") for a in actors):
            steps = steps or write_cue_sounds(work / "sfx", {"footsteps"}).get("footsteps")
            walk = next(a["action"] for a in actors if a["action"] in ("step", "walk-across"))
            if steps:
                cues.append({"src": rel(steps), "at": round(t + (0.8 if walk == "step" else 0.1), 3),
                             "volume": 0.35, "name": "footsteps"})
        if li == 0 and si > 0 and "whoosh" in sfx and req.style != "documentary":  # a new place: a whoosh on the cut
            cues.append({"src": rel(sfx["whoosh"]), "at": round(max(0.0, t - 0.1), 3), "volume": 0.4, "name": "whoosh"})
        t += duration
    t += 0.6
    # Each scene's ambience (wind, rain, room tone...) as a quiet bed under it.
    ambience = []
    for si, sc_ in enumerate(ep.scenes):
        span = [s_ for s_ in shots if s_["scene"] == si]
        if sc_.ambience != "none" and span:
            a, b = span[0]["start"], span[-1]["start"] + span[-1]["duration"] + (0.6 if si == len(ep.scenes) - 1 else 0)
            bed = music.ambience(sc_.ambience, b - a, int(uuid.uuid4().int % 2**31), work / "music" / f"ambience{si:02d}.wav")
            if bed:
                ambience.append({"src": rel(bed), "from": round(a, 3), "to": round(b, 3)})
    # A track of its own for every video: composed in the mood Claude picked, from a fresh seed (key,
    # tempo, chords), following each scene's intensity; one of the user's tracks only when Claude picked it.
    choice = (ep.music or "compose").strip()
    mine = {m.name for m in media.music(cfg) if m.path is not None}
    ai = {}
    if keep_music:  # a re-make keeps the video's own track
        ai["main"], kept_label = keep_music
    elif choice not in mine and choice != "none" and aimusic.available(cfg):  # new music from the AI music model
        seed = int(uuid.uuid4().int % 2**31)
        genre = aimusic.pick_genre(cfg, ep.mood, seed)
        energy = sum(sc_.intensity for sc_ in ep.scenes) / max(1, len(ep.scenes))
        ai = aimusic.make(cfg, [aimusic.track("main", work / "music" / "ai-main.wav", t + 1, genre, ep.mood, energy,
                                              ep.music_prompt, seed)], work, progress, "Music (AI)")
        if ai:
            aimusic.remember(cfg, genre)
    if keep_music:
        track, choice = ai["main"], kept_label
    elif "main" in ai:
        track, choice = ai["main"], f"generated (ACE-Step, {genre})"
    elif choice in mine and media.fresh_track(cfg, choice):  # never the upload a recent video used
        track = media.pick_music(cfg, choice, work / "music", t)
    elif choice == "none":
        track = None
    else:
        from . import music as composer

        starts = [next(s["start"] for s in shots if s["scene"] == si) for si in range(len(ep.scenes)) if any(s["scene"] == si for s in shots)]
        sections = [composer.Section(a, b, ep.scenes[si].intensity) for si, (a, b) in enumerate(zip(starts, [*starts[1:], t]))]
        (work / "music").mkdir(parents=True, exist_ok=True)
        track = composer.compose(ep.mood, sections, t, int(uuid.uuid4().int % 2**31), work / "music" / "score.wav")
        media.note_music(cfg, f"mood:{ep.mood}")
        choice = f"composed ({ep.mood})"
    props = {
        "fps": cfg.fps, "duration": round(t, 3), "title": ep.title, "vertical": short,
        "art": "ink",
        "cast": [{"id": c.id, "name": c.name, "look": c.look, "outfit": _outfits(ep.cast)[c.id],
                  "design": ink_design(c.design, c.look, i)} for i, c in enumerate(ep.cast)],
        "shots": shots, "music": rel(track) if track else None, "musicChoice": choice, "cues": cues,
        "speech": media.speech_spans(spoken), "sfx": {k: rel(p) for k, p in sfx.items()}, "ambience": ambience,
        "credits": credits,
    }
    # Subtitles (the Stick tab's choice): auto = on, but off for a documentary (the narration is heard, not shown).
    if req.subtitles == "off" or (req.subtitles != "on" and req.style == "documentary" and not cfg.captions):
        props["dialogue"] = "none"
    props["sfxLevels"] = media.level_sounds(props, work, [s["audio"] for s in shots if s.get("audio")])
    props["musicLevels"] = media.level_music(props, work, [s["audio"] for s in shots if s.get("audio")], "StickStory")  # the music under the voice
    return props


# ---------- the run ----------

def _history(cfg: Config) -> Path:
    return cfg.output_dir / "stick_history.json"


CHECKPOINT = "stick-checkpoint.json"  # its own name: the Shorts/long resume never picks a Stick video up


def run_stick(cfg: Config, req: StickRequest, progress: Progress = log.info, resume: str | None = None) -> dict:
    """One Stick video. Progress is saved after every step (`CHECKPOINT`: written, checked, boarded, built,
    rendered), so a closed app, a Pause or a failure continues from the last step on Resume: the writing and
    fact-check (the Claude tokens) are never paid twice."""
    from .fsutil import move
    from .llm import meter_add_earlier, meter_records, summarize_usage
    from .pipeline import _render_slot, pause_point, slugify

    short = req.format == "short"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    work = cfg.output_dir / resume if resume else cfg.output_dir / f"{stamp}-{uuid.uuid4().hex[:4]}-stick-working"
    work.mkdir(parents=True, exist_ok=True)
    progress(f"Saving progress in {work.name}")
    state = json.loads((work / CHECKPOINT).read_text(encoding="utf-8")) if (work / CHECKPOINT).exists() else {}
    stamp = state.get("stamp", stamp)
    if state.get("usage"):
        meter_add_earlier(state["usage"])  # the tokens spent before the stop still count for this video

    def save(stage: str, **changes) -> None:
        state.update(changes, stage=stage, stamp=stamp, request=asdict(req), usage=meter_records())
        if "ep" in changes:
            state["ep"] = changes["ep"].model_dump()
        (work / CHECKPOINT).write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        pause_point()

    stage = state.get("stage", "")
    order = ["written", "checked", "boarded", "built", "rendered"]
    done = lambda st: stage in order and order.index(stage) >= order.index(st)  # noqa: E731
    if stage:
        progress(f"Resuming after: {stage}")
    ep = Episode.model_validate(state["ep"]) if state.get("ep") else None
    from . import stickboard

    if not done("written"):
        recent = made_before(cfg)
        progress(("Claude is researching and writing" if req.style in TRUE_STYLES else "Claude is writing")
                 + (" the Short" if short else " the episode"))
        ep = write_episode(cfg, req, recent)
        # A story too close to one already made is written again once (not when you gave the idea).
        twin = None if req.idea.strip() else too_close(ep, recent)
        if twin:
            progress(f"That story was already made (\"{twin.get('title')}\"); Claude is writing a different one")
            ep = write_episode(cfg, req, recent, avoid=f"\"{twin.get('title')}\": {twin.get('logline', '')}")
        if req.style != "documentary":  # a documentary's people are dressed for their own story, never kept
            lock_designs(cfg, ep, parse_cast(req.cast))  # a recurring character keeps their look
        from .hooks import sharpen
        sharpen(cfg, [next((ln for s in ep.scenes for ln in s.lines if ln.line.strip()), None)], ep.logline, progress)
        # Remembered now, before voices and render: a video made at the same time sees it.
        remember(cfg, {"title": ep.title, "logline": ep.logline, "style": req.style,
                       "places": list(dict.fromkeys(sc.setting for sc in ep.scenes)), "music": ep.mood})
        save("written", ep=ep)
    if not done("checked"):
        fact_issues, findings, sources, dropped = [], [], [], []
        if req.style in TRUE_STYLES:
            hook_at = next(((si, li) for si, sc in enumerate(ep.scenes) for li, ln in enumerate(sc.lines) if ln.line.strip()), None)
            ep, fact_issues, findings = check_facts(cfg, ep, progress)
            if req.style == "documentary":
                ep = close_gaps(cfg, ep, hook_at, progress, fact_issues)
            sources, dropped = verify_sources(ep.sources)
        save("checked", ep=ep, fact_issues=fact_issues, findings=findings, sources=sources, dropped=dropped)
    fact_issues, findings = state.get("fact_issues", []), state.get("findings", [])
    sources, dropped = state.get("sources", []), state.get("dropped", [])
    if not done("boarded"):
        # Every line gets a picture of what it says, for every type (stickboard.py; the user: "not only changes for
        # documentry do it for all stick video generation").
        progress("Storyboarding: a picture of what every line says")
        ep = stickboard.storyboard(cfg, ep, board_rules(short, req.style), progress, narrated=req.style == "documentary")
        (work / "episode.json").write_text(ep.model_dump_json(indent=2), encoding="utf-8")
        save("boarded", ep=ep)
    if not done("built"):
        props = build(ep, req, cfg, work, progress)
        bad = stickboard.check(cfg, props, ep, work, short, progress)  # every type: pictures checked against their lines
        board_note = {"flagged": len(bad), "beats": {str(k): v for k, v in bad.items()}}
        if bad:
            progress(f"{len(bad)} picture(s) didn't show their line: staging them again")
            ep = stickboard.storyboard(cfg, ep, board_rules(short, req.style), progress, only=bad,
                                       narrated=req.style == "documentary")
            (work / "episode.json").write_text(ep.model_dump_json(indent=2), encoding="utf-8")
            props = build(ep, req, cfg, work, progress)
        (work / "props.json").write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
        save("built", ep=ep, board_note=board_note)
    props = json.loads((work / "props.json").read_text(encoding="utf-8"))
    board_note = state.get("board_note")
    out = work / "reel.mp4"
    if not done("rendered") or not out.exists():
        progress(f"Editing the video ({props['duration'] / 60:.1f} min)")
        cli = _remotion_cli()
        if cli is None:
            raise RuntimeError("Node.js or the Remotion packages are not installed (run start.bat / start.sh)")
        with _render_slot(cfg):
            _render_remotion(cli, props, out, composition="StickStory", crf=18, progress=progress)
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", "2", "-i", str(out), "-frames:v", "1", "-q:v", "3",
                        str(work / "thumbnail.jpg")], check=False)
        save("rendered")
    progress("Verifying video quality")
    info = probe(out)
    want = (1080, 1920) if short else (1920, 1080)
    issues = list(fact_issues)
    if req.style in TRUE_STYLES and not sources:
        issues.append("No source link could be opened; check the facts before posting.")
    if (info.get("width"), info.get("height")) != want:
        issues.append(f"Resolution is {info.get('width')}x{info.get('height')}, expected {want[0]}x{want[1]}.")
    if not info.get("has_audio"):
        issues.append("No audio track.")
    (work / CHECKPOINT).unlink(missing_ok=True)
    final = cfg.output_dir / f"{stamp}-{slugify(ep.title)}-stick"
    move(work, final)
    report = {
        "id": final.name, "format": "short" if short else "long", "length": "short" if short else "stick",
        "source": "stick", "topic": ep.title, "topic_source": "stick story",
        "style": {"facts": "facts", "documentary": "facts", "fiction": "story"}.get(req.style, "comedy"),
        "stick_type": req.style,
        **({"picture_check": board_note} if board_note is not None else {}),
        "category": ep.category if ep.category in CATEGORIES and req.style != "comedy"
        else {"fiction": "Stories", "facts": "Science & Space", "documentary": "History"}.get(req.style, "Comedy"),
        "title": ep.title, "why_chosen": ep.logline, "narration": " ".join(l.line for s in ep.scenes for l in s.lines if l.line),
        "created_at": stamp, "verified": not issues, "score": None, "issues": issues, "checks": {"probe": info},
        "attempts": 1, "video": str(final / "reel.mp4"), "thumbnail": str(final / "thumbnail.jpg"),
        "duration_seconds": round(props["duration"], 1), "editor": "remotion (StickStory)",
        "captions": props.get("dialogue") != "none", "stick_request": asdict(req),  # for a re-make (remake)
        "music": props.get("musicChoice", ""),
        "voice": req.language, "youtube_title": ep.title[:100],
        "youtube_description": with_sources(ep.youtube_description.strip(), sources, props.get("credits") or []), "youtube_hashtags": ep.hashtags[:3],
        "youtube_tags": ep.tags, "caption": ep.youtube_description.strip(), "hashtags": ep.hashtags,
    }
    if req.style in TRUE_STYLES:
        report.update({"fact_check": findings, "sources": sources, "sources_unreachable": dropped})
    (final / "props.json").write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
    report["usage"] = summarize_usage(meter_records())
    (final / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    remember(cfg, {"title": ep.title, "logline": ep.logline, "style": req.style,
                   "places": list(dict.fromkeys(sc.setting for sc in ep.scenes)), "music": props.get("musicChoice", "")})
    progress("Done" if not issues else "Done, but it did not pass every check — review before posting")
    return report


def remake(cfg: Config, folder: Path, speed: float | None, subtitles: str | None, progress: Progress = log.info) -> dict:
    """A finished Stick video again at another speaking speed and/or with subtitles on or off (the user: "why speed
    slider changes ... not inside this stick create tab"): the same episode, pictures, proof photos and music, only
    the voices recorded again and the edit re-timed. No Claude, nothing searched again. The video is replaced in place."""
    from .fsutil import move
    from .pipeline import _render_slot

    report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
    ep = Episode.model_validate_json((folder / "episode.json").read_text(encoding="utf-8"))
    old = json.loads((folder / "props.json").read_text(encoding="utf-8"))
    known = {k: v for k, v in (report.get("stick_request") or {}).items() if k in StickRequest.__dataclass_fields__}
    req = StickRequest(**known) if known else StickRequest(  # videos made before the request was kept
        format="short" if report.get("format") == "short" else "long", style=report.get("stick_type") or "comedy",
        language=report.get("voice") if report.get("voice") in ("english", "hindi") else "english",
        speed=1.0 if report.get("stick_type") == "documentary" else 1.5)
    if speed:
        req.speed = min(2.0, max(0.8, float(speed)))
    if subtitles in ("auto", "on", "off"):
        req.subtitles = subtitles
    work = folder / "_remake"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    try:
        if (folder / "evidence").is_dir():
            shutil.copytree(folder / "evidence", work / "evidence")
        keep = None
        if old.get("music") and (folder / old["music"]).exists():
            (work / "music").mkdir(exist_ok=True)
            kept = work / "music" / ("kept-" + Path(old["music"]).name)
            shutil.copy2(folder / old["music"], kept)
            keep = (kept, old.get("musicChoice") or "kept")
        progress(f"Speaking speed {req.speed:g}x, subtitles {req.subtitles}")
        props = build(ep, req, cfg, work, progress, keep_music=keep)
        progress(f"Editing the video ({props['duration'] / 60:.1f} min)")
        cli = _remotion_cli()
        if cli is None:
            raise RuntimeError("Node.js or the Remotion packages are not installed (run start.bat / start.sh)")
        with _render_slot(cfg):
            _render_remotion(cli, props, work / "reel.mp4", composition="StickStory", crf=18, progress=progress)
        info = probe(work / "reel.mp4")
        if not info.get("has_audio") or not info.get("width"):
            raise RuntimeError("The re-made video came out broken; the original is kept.")
        progress("Replacing the video")
        for sub in ("audio", "audio-fit", "sfx", "music", "evidence"):
            shutil.rmtree(folder / sub, ignore_errors=True)
            if (work / sub).is_dir():
                move(work / sub, folder / sub)
        move(work / "reel.mp4", folder / "reel.mp4.new")
        (folder / "reel.mp4").unlink(missing_ok=True)
        move(folder / "reel.mp4.new", folder / "reel.mp4")
        (folder / "props.json").write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", "2", "-i", str(folder / "reel.mp4"), "-frames:v", "1",
                        "-q:v", "3", str(folder / "thumbnail.jpg")], check=False)
        report.update({"stick_request": asdict(req), "duration_seconds": round(props["duration"], 1),
                       "captions": props.get("dialogue") != "none", "checks": {**(report.get("checks") or {}), "probe": info}})
        (folder / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        progress("Done")
        return report
    finally:
        shutil.rmtree(work, ignore_errors=True)


def run_stick_job(cfg: Config, req: StickRequest, count: int, progress: Progress, resume: list[str] | None = None) -> list[dict]:
    """The app's job: `count` episodes or Shorts, one after another, in the shared video slot (or resume saved ones)."""
    from .llm import set_limit_reporter, start_meter, usage_line
    from .pipeline import Paused, _video_slot, done_line, set_pause_check

    reports = []
    should_pause = getattr(progress, "should_pause", None)
    todo = list(resume or []) or [None] * count
    count = len(todo)
    for i, folder in enumerate(todo):
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
                saved = folder and cfg.output_dir / folder / CHECKPOINT
                mine = StickRequest(**(json.loads(saved.read_text(encoding="utf-8")).get("request") or asdict(req))) \
                    if saved and saved.exists() else req
                reports.append(run_stick(cfg, mine, vp, folder))
                vp(done_line(reports[-1]))
            except Paused:
                vp("Paused: progress saved. Press Resume to carry on from here.")
            except Exception as exc:
                log.exception("Stick video %d failed", i + 1)
                vp(f"Video {i + 1} failed: {exc}")
    return reports


def unfinished_sticks(cfg: Config) -> list[str]:
    return sorted(p.parent.name for p in cfg.output_dir.glob(f"*-stick-working/{CHECKPOINT}"))


def stick_unfinished(cfg: Config) -> list[dict]:
    """Unfinished Stick videos for the app's "Unfinished videos" list (same shape as pipeline.unfinished)."""
    done = {"written": "the script", "checked": "script and fact-check", "boarded": "script, fact-check and storyboard",
            "built": "everything but the edit", "rendered": "everything but the checks"}
    out = []
    for folder in unfinished_sticks(cfg):
        path = cfg.output_dir / folder / CHECKPOINT
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        req, ep = state.get("request") or {}, state.get("ep") or {}
        out.append({"id": folder, "topic": ep.get("title") or req.get("idea") or "Stick video", "title": ep.get("title", ""),
                    "style": {"facts": "facts", "documentary": "facts", "fiction": "story"}.get(req.get("style"), "comedy"),
                    "length": "stick-short" if req.get("format") == "short" else "stick", "attempt": 1,
                    "done": done.get(state.get("stage") or "", "nothing yet"), "updated": path.stat().st_mtime})
    return out


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
