"""The film Claude writes: a closed vocabulary the editor can draw (remotion/src/sticky/types.ts), and the rules that
made the reference films work (ANALYSIS.md)."""
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

Tone = Literal["cream", "grey", "peach", "tan", "brown", "pale"]
Wear = Literal["none", "hood", "bob", "ponytail", "short", "beanie", "cap", "headband", "bun", "curly", "scarf", "hardhat",
               "long", "bald"]
Pose = Literal["stand", "walk", "run", "sit", "sit_bed", "lie", "curl", "kneel", "slump", "reach", "phone", "type", "shake",
               "pushup", "punch", "climb", "cheer", "hug", "hold_out", "write", "wave", "fall", "think", "guitar", "sleep"]
Face = Literal["neutral", "tired", "sad", "cry", "worried", "anxious", "angry", "determined", "happy", "smile", "shock",
               "embarrassed", "numb", "smug"]
Prop = Literal["none", "phone", "book", "guitar", "drawing", "umbrella", "coffee", "ball", "bag", "pen", "note", "cup", "gift",
               "laptop"]
SetName = Literal["bedroom", "desk", "living", "kitchen", "bathroom", "hallway", "street", "busstop", "cafe", "classroom",
                  "gym", "office", "stairs", "rooftop", "hill", "park", "court", "stage", "void"]
Light = Literal["night", "lamp", "dawn", "day", "dusk", "grey", "neon"]
Colour = Literal["black", "charcoal", "grey", "white", "navy", "blue", "red", "orange", "yellow", "green", "brown", "pink",
                 "purple", "teal"]
Accent = Literal["pink", "red", "purple", "amber", "cyan"]
Sound = Literal["ding", "notify", "buzz", "typing", "tap", "send", "knock", "door", "footsteps", "alarm", "heartbeat",
                "rumble", "static", "chime", "bell", "pop", "swoosh", "scribble", "tick", "page", "coins", "rain", "cheer",
                "thud"]
Act = Literal["open", "loop", "low", "turn", "day1", "climb", "test", "resolve", "thesis", "title"]
Mood = Literal["calm", "dark", "emotional", "suspense", "uplifting", "curious", "playful"]

COLOURS = {"black": "#1E1E22", "charcoal": "#4A505C", "grey": "#8C929C", "white": "#E8E8E4", "navy": "#2C3E66",
           "blue": "#3C78D8", "red": "#C8424A", "orange": "#E8822E", "yellow": "#E8BE2E", "green": "#3E9A5A",
           "brown": "#6B4A32", "pink": "#E88AAE", "purple": "#7A5AB8", "teal": "#2E9A9A"}
ACCENTS = {"pink": "#FF4FA3", "red": "#FF3B3B", "purple": "#A86BFF", "amber": "#FFB238", "cyan": "#3FD0FF"}


class FCast(BaseModel):
    id: str = Field(description="Short lowercase id, e.g. 'leo'. The hero is first.")
    name: str
    role: str = Field(description="Who they are to the hero: 'the hero', 'his little sister', 'best friend', 'mum'...")
    tone: Tone = Field(description="Skin: cream for most; background strangers are 'grey' (the editor greys them too).")
    wear: Wear = Field(description="The ONE item (or hair) that tells this person apart at a glance: hood, bob, beanie, headband...")
    color: Colour = Field(description="Its colour.")
    kid: bool = Field(default=False, description="A child (drawn smaller).")
    extra: Wear = Field(default="none", description="A second item, rarely: a scarf with a bob. 'none' usually.")


class FActor(BaseModel):
    id: str = Field(description="A cast id.")
    x: int = Field(ge=0, le=100, description="Where on the floor, 0 (left) to 100 (right). Two people talking stand 15-25 apart.")
    pose: Pose = Field(description="What the body does. lie/sleep/sit_bed go on the set's bed, sit on its chair or couch; walk/run/climb move from x to 'to'.")
    face: Face
    facing: Literal["left", "right"] = "right"
    to: int = Field(default=-1, ge=-1, le=100, description="walk/run/climb: where they end up; -1 otherwise.")
    prop: Prop = "none"
    glow: bool = Field(default=False, description="A phone screen lights the face (night scrolling).")
    tear: bool = False
    sweat: bool = False
    face2: Face | Literal[""] = Field(default="", description="A change of face during the shot (the realisation), or empty.")
    face_at: float = Field(default=0, description="Seconds into the shot when face2 replaces face.")


class FShadow(BaseModel):
    x: int = Field(ge=0, le=100)
    size: Literal["small", "normal", "giant"]
    act: Literal["appear", "lean", "grow", "whisper", "dissolve", "loom"]
    copy_of: str = Field(default="", description="A cast id when the voice has learned to look like him (late in the story); else empty.")


class FMessage(BaseModel):
    me: bool = Field(description="True: sent by the hero (blue, right). False: received (grey, left).")
    text: str = Field(description="Real texting style: lowercase, short, specific ('day 30 bro', 'i relapsed.', 'u coming tonight?').")


class FPhone(BaseModel):
    mode: Literal["chat", "feed", "notif", "lock", "dialog", "call", "video", "post"]
    title: str = Field(default="", description="chat: the contact's name. call: who calls. dialog: the question ('delete page?'). video/post: its title.")
    messages: list[FMessage] = Field(default_factory=list, description="chat only: up to 5, in order.")
    typing: str = Field(default="", description="chat: what he types during the shot (often never sent); empty otherwise.")
    items: list[str] = Field(default_factory=list, description="feed: 3-5 Lucide icon names for the posts ('hamburger', 'car', 'cat', 'dumbbell', 'palmtree'). notif: 2-4 short notification texts. dialog/post: the two buttons.")
    time: str = Field(default="", description="lock/notif: the time on the lock screen, e.g. '2:41'.")
    seen: bool = Field(default=False, description="chat: 'Seen' under the last message.")


class FCalendar(BaseModel):
    month: str
    checks: int = Field(ge=0, le=31, description="Days ticked so far.")
    marks: list[int] = Field(default_factory=list, description="Day numbers scribbled in the accent colour (the day he slipped).")


class FObject(BaseModel):
    kind: Literal["drawing", "note", "letter", "poster", "list", "bill"]
    title: str = Field(default="", description="drawing: what a child wrote on it ('ME + MY BROTHER'). note/letter/poster/list: its heading. bill: 'FINAL NOTICE' etc.")
    lines: list[str] = Field(default_factory=list, description="Up to 5 short handwritten lines.")
    who: list[str] = Field(default_factory=list, description="drawing only: the figures drawn, 1-3, e.g. ['me', 'brother phone'] (a word 'phone' draws a phone for a face, 'heart' adds a heart).")
    checked: int = Field(default=0, description="list only: how many lines are ticked.")


class FGraph(BaseModel):
    shape: Literal["wave", "spikes", "rise", "plateau", "dip_rise", "fall"]
    labels: list[str] = Field(default_factory=list, description="1-3 handwritten words placed along the line ('craving', 'relief', 'regret').")


class FSoundCue(BaseModel):
    sound: Sound
    at: float = Field(ge=0, description="Seconds into the shot.")


class FShot(BaseModel):
    kind: Literal["scene", "phone", "clock", "calendar", "card", "object", "graph", "face"] = Field(
        description="scene: a set with people. phone: the phone close in his hands. clock: the alarm clock close (the time is story). "
                    "calendar: the wall calendar close. card: words on black only. object: a drawing, note, letter, list or bill held up close. "
                    "graph: a line drawn in the dark to explain an idea. face: a close-up of one face (a feeling).")
    seconds: float = Field(ge=1.5, le=9, description="How long it holds: 2-4 most shots, up to 6 for a line of text to be read, 1.5-2.5 in a montage.")
    set: SetName = Field(default="void", description="scene/face: the place. Reuse the hero's main place (usually his bedroom) so the loop is felt.")
    light: Light = Field(default="night")
    actors: list[FActor] = Field(default_factory=list, description="scene: 1-3 people; face: the one whose face it is.")
    shadow: FShadow | None = Field(default=None, description="The inner voice in the scene, when it is acting on him.")
    clock: str = Field(default="", description="The time on the alarm clock ('3:17'): in the bedroom on the nightstand, or the clock insert.")
    phone: FPhone | None = None
    calendar: FCalendar | None = None
    object: FObject | None = None
    graph: FGraph | None = None
    caption: list[str] = Field(default_factory=list, description="Narration: 0-2 short lines (max 9 words each). Most shots have none. The second line is the turn or punch.")
    caption_pos: Literal["top", "bottom", "center"] = "top"
    whisper: str = Field(default="", description="The inner voice's line in its colour by hand (max 6 words, lowercase): 'just one more.', 'you earned it.', 'start tomorrow.'")
    whisper_x: int = Field(default=70, ge=5, le=95)
    whisper_y: int = Field(default=26, ge=8, le=80)
    bubbles: list[FMessage] = Field(default_factory=list, description="Speech bubbles, spoken in order: me=True is the hero, me=False the other person in the scene. Short, real, specific.")
    notes: list[str] = Field(default_factory=list, description="Worries stuck on the wall as red sticky notes (overthinking), 2-12 words each max 3 words.")
    pills: list[str] = Field(default_factory=list, description="Notification pills floating around him: 'EVERYONE'S ONLINE', '99+ NEW'. 2-4 or none.")
    stamp: str = Field(default="", description="A big chalk line: only 'DAY 1.' at the turn (or 'DAY 1.' again at the end).")
    grade: Literal["normal", "grey", "cold", "warm"] = Field(default="normal", description="grey at the low point; cold in the spiral; warm as he heals.")
    transition: Literal["cut", "fade", "black"] = Field(default="cut", description="How this shot comes in: cut mostly, fade for time passing, black into a new act.")
    camera: Literal["still", "push", "drift"] = "still"
    meter: list[float] = Field(default_factory=list, description="The meter's value(s) during this shot (one number; two for a 'dual' meter). Set it whenever it changes.")
    day: str = Field(default="", description="The HUD day label once days are counted: 'DAY 23'. Empty before.")
    time: str = Field(default="", description="The HUD clock: '2:03 AM'. Empty when time doesn't matter.")
    quiet: bool = Field(default=False, description="The music drops away for this shot (the breath before the turn, a gut punch).")
    sounds: list[FSoundCue] = Field(default_factory=list, description="Sounds of the world and the feeling on this shot beyond the automatic ones (phone dings, steps, bubbles, the voice's rumble are added in code).")


class FAct(BaseModel):
    act: Act
    mood: Mood = Field(description="The music under this act.")
    shots: list[FShot]


class FMeter(BaseModel):
    kind: Literal["battery", "bar", "counter", "dual", "none"] = Field(description="battery: his energy in % (falls and recovers). bar: a progress bar with a label (SCREEN TIME, READY). counter: a number (DAY streak, REPS). dual: two counters side by side (SEEN / KNOWN). none only if the story truly has no number.")
    labels: list[str] = Field(description="battery: ['his battery']. bar: ['READY']. counter: ['DAY']. dual: ['SEEN', 'KNOWN'].")
    unit: str = Field(default="", description="'%' for battery/bar; empty otherwise.")


class Film(BaseModel):
    title: str = Field(description="One or two words and a full stop, the feeling or the trap: 'DOPAMINE.', 'READY.', 'OVERTHINKING.'")
    tagline: list[str] = Field(description="Two lines for the title card: a statement, then a dare: ['You'll never feel ready.', 'Start anyway.']")
    thesis: list[str] = Field(description="Two lines on black before the title, the truth the film proved: ['On day one, it shouts.', 'On day four hundred, it sounds like you.']")
    problem: str = Field(description="The everyday private problem, one sentence.")
    accent: Accent = Field(description="The inner voice's colour: pink for a craving, red for fear or anger, purple for doubt, amber/cyan otherwise.")
    meter: FMeter
    cast: list[FCast] = Field(description="1-4 people, the hero first.")
    acts: list[FAct] = Field(description="The acts in order: open, loop, low, turn, day1, climb, test, resolve, thesis, title (all ten, in this order).")
    youtube_title: str = Field(description="'TITLE | An Animated Short Film' style, max 60 characters.")
    thumbnail_text: str = Field(description="2-3 huge words for the thumbnail, a question or a blunt line ('WHERE IS SHE?', 'STAY.').")
    description: str = Field(description="YouTube description: 2-3 sentences that name the feeling, no hashtags.")
    tags: list[str] = Field(description="8-14 search tags.")
    hashtags: list[str] = Field(description="3 hashtags.")


TOPICS = [
    "doomscrolling at night instead of sleeping", "putting off the thing you most want to start", "overthinking a text that wasn't answered",
    "comparing your life to other people's posts", "gaming through the hours you meant to study", "skipping the gym after two good weeks",
    "saying yes to everything and burning out", "feeling lonely in a new city", "not calling your parents back",
    "a friendship slowly drifting apart", "spending money to feel better", "waking up late and losing the day",
    "eating junk at midnight", "fear of speaking up in class or at work", "perfectionism stopping you from finishing anything",
    "imposter syndrome at a new job", "jealousy when a friend succeeds", "staying in a comfort zone", "anger you take out on family",
    "waiting for motivation to arrive", "being glued to the phone at dinner", "the exam you keep not preparing for",
    "a sibling who wants your time", "pretending to be fine", "fear of starting over after failing", "procrastinating with productivity videos",
]

RULES = """You write voiceless animated short films (2.5-4 minutes, 16:9) in the style of channels like "Day One Films" \
and "Monk Mode Films": round-headed bean people, dark line-art rooms, a meter on screen, the inner voice drawn as a \
glowing shadow, a few lines of white text, and sound. They get 50k to millions of views without a voice-over. What \
works, from a study of seven of them:

THE PROBLEM: one private, everyday struggle viewers live alone at 2 AM and never say aloud (the phone, putting things \
off, overthinking, comparison, loneliness, a habit). Show it exactly as it happens, with specific details: 3:17 AM, \
'day 30 bro', a feed of burgers and cars, 'you too.' after 'enjoy your meal'. Specific beats generic every time. \
Never sexual content, self-harm, pills, suicide, violence, real brands or real people; mental health with hope, never \
medical advice.

THE DEVICES (use all four):
1. A METER that carries the story: his battery % falling and recovering, a SCREEN TIME bar, a DAY streak counter that \
crashes to 0 on a relapse, a READY bar stuck at 99%, two counters side by side. Set `meter` on every shot where it \
changes; it falls through the loop and climbs through the montage.
2. THE INNER VOICE as a character (`shadow` + `whisper`): it whispers the hero's own excuses ('just one more.', 'you \
earned it.', 'start tomorrow.', 'they'll all see you fail.'), grows when he gives in, returns smarter in the test \
('you've learned your lesson. one look won't hurt.'), may learn to look like him (copy_of), and dissolves when he \
walks away. For overthinking use `notes` (red sticky notes piling up); for the phone, `pills`.
3. THE TURN comes from outside him, never a lecture: a little sister's drawing with a phone for his face, a friend's \
text, a missed call, a kid watching through a window, mum asking 'are you okay?'.
4. TIME you can see: the alarm clock, the HUD time and DAY label, the calendar filling with ticks (a scribble on the \
day he slipped).

THE SHAPE (acts in this order):
- open (2-3 shots): a `card` on black with a two-line cold open, a fact then its twist ("His phone was always at \
100%." / "He never was."), then straight into his room.
- loop (8-14 shots): the same night repeated with the clock and the meter moving, a bit worse each time; the voice gets \
more persuasive; the people he lets down appear (a knock, a drawing, a text).
- low (3-5 shots): grade 'grey', small and alone; one short line names it ("So he stopped trying.").
- turn (3-6 shots): the outside moment; a face close-up for the realisation; `quiet` on the gut punch.
- day1 (1-2 shots): the `stamp` 'DAY 1.' and the first small act (the phone in a drawer, laces tied).
- climb (8-14 shots, 1.5-3 s each): a montage of days with DAY labels and the meter rising: small concrete habits, \
places that change (street at dawn, the gym, the park), grade 'warm' growing.
- test (4-8 shots): the voice returns smarter; he walks away (dissolve) or slips and gets back up ("Twenty two nights \
won. One lost.").
- resolve (3-6 shots): the callback to the opening image, now changed ("This time, she drew his face."); the person he \
lost is back.
- thesis (1-2 shots): `card` with the two thesis lines.
- title (1 shot): kind 'card' with no caption; the editor draws the title and tagline itself.

THE TELLING: pictures first. 15-30 caption lines in the whole film, most shots none. Captions are short, plain and \
human (max 9 words a line), the second line the turn in bold. Dialogue only in bubbles or chat, a few words. Change \
the picture every 2-4 s: wide room shots, a face close-up for a feeling, inserts of the phone, the clock, the calendar, \
a drawing. Keep the hero's main room so the loop is felt. Give every action a sound (`sounds`) where it isn't \
automatic: alarm, door, coins, rain, a heartbeat at the realisation, a chime or bell when something good lands, \
rumble under the voice. Total length {minutes} minutes: about {shots} shots."""


def _recent(cfg: Config) -> list[dict]:
    try:
        return json.loads((cfg.output_dir / "sticky_history.json").read_text(encoding="utf-8"))[-40:]
    except (OSError, ValueError):
        return []


def remember(cfg: Config, film: Film) -> None:
    path = cfg.output_dir / "sticky_history.json"
    items = _recent(cfg) + [{"title": film.title, "problem": film.problem}]
    try:
        path.write_text(json.dumps(items[-200:], ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def _words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", s.lower()) if len(w) > 3}


def too_close(film: Film, past: list[dict]) -> str:
    mine = _words(film.problem + " " + film.title)
    for p in past:
        theirs = _words(p.get("problem", "") + " " + p.get("title", ""))
        if film.title.strip(". ").lower() == p.get("title", "").strip(". ").lower():
            return p.get("title", "")
        if mine and theirs and len(mine & theirs) / max(1, min(len(mine), len(theirs))) >= 0.6:
            return p.get("title", "")
    return ""


def write_film(cfg: Config, topic: str, minutes: float, progress=log.info) -> Film:
    """One call writes the whole film; a story too close to an earlier one is written once more."""
    shots = int(minutes * 60 / 3.2)
    system = RULES.format(minutes=f"{minutes:g}", shots=shots)
    past = _recent(cfg)
    made = "\n".join(f"- {p['title']} ({p['problem']})" for p in past[-30:]) or "- none yet"
    ask_for = (f"Write the film about: {topic}." if topic else
               "Choose the problem yourself: a relatable everyday struggle, different from the films already made. "
               f"Ideas (not a list to copy): {', '.join(TOPICS)}.")
    prompt = f"{ask_for}\n\nFilms already made (never the same story, problem or title again):\n{made}"
    film = ask(cfg.ai_backend, cfg.claude_model, system, prompt, Film, allow_web=False, effort=cfg.claude_effort, timeout=2400)
    near = too_close(film, past) if not topic else ""
    if near:
        progress(f"That story is too close to '{near}'; writing a different one")
        film = ask(cfg.ai_backend, cfg.claude_model, system, prompt + f"\n\nYour first idea was too close to '{near}'. "
                   "Pick a different problem and story.", Film, allow_web=False, effort=cfg.claude_effort, timeout=2400)
    return film


def save(film: Film, path: Path) -> None:
    path.write_text(json.dumps(film.model_dump(), ensure_ascii=False, indent=1), encoding="utf-8")


def load(path: Path) -> Film:
    return Film.model_validate(json.loads(path.read_text(encoding="utf-8")))
