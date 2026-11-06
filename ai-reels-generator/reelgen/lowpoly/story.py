"""The writer for the low-poly films: one Claude call (no web) writes the narration and stages every shot in the
editor's own vocabulary (sets, lights, cameras, actions, faces, things, sounds), for a Short (9:16, 20-60 s) or a
short film (3-4 min). Modelled on the user's own Short 'Life of a Man' (analysed: 33 s, 11 shots of ~3 s, a calm
narrator in short present-tense sentences, time stamps as chapter marks (11:47 P.M. -> 5:30 A.M. -> 6:10 A.M. ->
7:45 A.M.), the promise getting smaller each time, a last line in red that stings). The hero is always the same man
(remotion/src/lowpoly/Man.tsx HERO); anyone else is designed once and kept by name (<output>/lowpoly_cast.json)."""
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

SetName = Literal["bedroom", "hallway", "street", "park", "kitchen", "living", "office", "bathroom", "gym", "cafe", "busstop", "rooftop", "void"]
LightName = Literal["night", "lamp", "dawn", "morning", "day", "evening", "dark"]
CamName = Literal["face", "face-top", "top", "medium", "wide", "side", "front", "back", "low", "detail"]
ActionName = Literal[
    "stand", "walk", "run", "sit", "sit-floor", "lie", "lie-side", "lie-phone", "phone", "type", "reach", "sit-up", "get-up", "shoes",
    "head-in-hands", "slump", "stretch", "sigh", "nod", "shake-head", "shrug", "think", "drink", "eat", "look-out", "wave", "point",
    "cheer", "jog", "pushup", "read", "cry"]
ExprName = Literal["neutral", "tired", "sad", "worried", "surprised", "happy", "determined", "annoyed", "asleep", "blank"]
SpotName = Literal["center", "left", "right", "bed", "chair", "desk", "door", "window", "couch", "mirror", "counter", "far"]
HoldName = Literal["none", "phone", "mug", "book", "laptop", "shoes", "bag", "keys", "fork"]
ThingName = Literal["phone", "alarm", "mug", "laptop", "book", "shoes", "plate", "bag", "plant", "bottle", "calendar", "note", "pizza"]
SoundName = Literal["alarm", "footsteps", "door", "knock", "notify", "buzz", "typing", "tap", "ding", "chime", "bell", "page", "rain",
                    "thud", "heartbeat", "tick", "coins", "cheer", "pop", "scribble", "swoosh", "send"]
Mood = Literal["calm", "emotional", "uplifting", "curious", "mystery", "dark"]

# what each set has (the spots the editor knows there); the writer is told, and `repair` falls back to 'center'
SPOTS: dict[str, set[str]] = {
    "bedroom": {"bed", "center", "left", "right", "window", "door", "chair"},
    "hallway": {"door", "center", "chair", "left", "right"},
    "street": {"center", "left", "right", "door"},
    "park": {"center", "left", "right", "chair", "far"},
    "kitchen": {"counter", "chair", "desk", "center", "left", "right", "window"},
    "living": {"couch", "chair", "center", "window", "left", "right"},
    "office": {"desk", "chair", "center", "window", "left", "right", "door"},
    "bathroom": {"mirror", "center", "left", "right", "door"},
    "gym": {"center", "chair", "left", "right", "mirror"},
    "cafe": {"chair", "counter", "center", "left", "right", "window"},
    "busstop": {"chair", "center", "left", "right"},
    "rooftop": {"center", "left", "right", "chair"},
    "void": {"center", "left", "right", "chair"},
}
SEATS = {"bed", "chair", "desk", "couch"}

COLOURS = {  # muted, like the reference's sweater and trousers
    "red": "#b2414e", "navy": "#2f3e5c", "green": "#4c6b46", "mustard": "#c49a3c", "grey": "#7d8088", "white": "#e7e3dc",
    "black": "#2a2a2e", "teal": "#2f6f73", "purple": "#6a4f7f", "pink": "#d0868f", "brown": "#6a4a33", "beige": "#c9b393",
    "blue": "#4f74a8", "orange": "#c8703a", "olive": "#6d6b3e", "maroon": "#7a2e3a", "denim": "#4a6584", "cream": "#e9dfc9",
}
HAIR = {"black": "#26211f", "dark-brown": "#4a3022", "brown": "#94593a", "auburn": "#8e3f22", "blonde": "#c9a35f", "grey": "#9c9a98",
        "white": "#e2e0dc", "red": "#a8492a"}
SKIN = {"pale": "#ece2d8", "light": "#e6d8cb", "fair": "#e2c6ab", "tan": "#c99e78", "brown": "#9c6d4c", "dark": "#6b4630"}
HERO = {"skin": SKIN["light"], "hair": HAIR["brown"], "hairStyle": "curly", "glasses": True, "top": COLOURS["red"], "topKind": "sweater",
        "trousers": COLOURS["brown"], "shoes": "#eeece7"}


class LPDesign(BaseModel):
    skin: Literal["pale", "light", "fair", "tan", "brown", "dark"] = "light"
    hair: Literal["black", "dark-brown", "brown", "auburn", "blonde", "grey", "white", "red"] = "dark-brown"
    hair_style: Literal["curly", "short", "long", "bun", "bald", "ponytail"] = "short"
    glasses: bool = False
    top: Literal["red", "navy", "green", "mustard", "grey", "white", "black", "teal", "purple", "pink", "brown", "beige", "blue", "orange",
                 "olive", "maroon", "denim", "cream"] = "navy"
    top_kind: Literal["sweater", "shirt", "dress", "hoodie", "suit"] = "sweater"
    trousers: Literal["navy", "grey", "black", "brown", "beige", "denim", "olive"] = "grey"
    beard: bool = False
    kid: bool = False


class LPCast(BaseModel):
    name: str = Field(description="how the narrator names them: 'his mum', 'Sara', 'his boss' (never the hero)")
    who: str = Field(description="one line: who they are to him")
    design: LPDesign


class LPActor(BaseModel):
    who: str = Field(description="'hero' for him, else a cast member's name exactly")
    action: ActionName
    expression: ExprName
    spot: SpotName
    to: SpotName | None = Field(None, description="walk/run/jog only: the spot he walks to (else he walks across the frame)")
    facing: Literal["camera", "left", "right", "away"] = "camera"
    hold: HoldName = "none"
    covered: bool = Field(False, description="in bed under the blanket")


class LPThing(BaseModel):
    kind: ThingName
    label: str = Field("", description="the alarm clock's time ('5:30'), a note's or calendar's word; empty otherwise")
    glow: bool = Field(False, description="a lit screen")


class LPSound(BaseModel):
    sound: SoundName
    word: str = Field("", description="a word of this shot's line it lands on; empty = the start of the shot")


class LPShot(BaseModel):
    stamp: str = Field("", description="a time or day stamp shown big as the shot starts ('11:47 P.M.', '5:30 A.M.', 'DAY 3', "
                                         "'SATURDAY'); empty for most shots")
    line: str = Field(description="the narrator's words over this shot: one short sentence or a fragment, at most 12 words; "
                                  "'' for a silent beat")
    set: SetName
    light: LightName
    camera: CamName
    actors: list[LPActor] = Field(description="who is in the shot and what they do (the hero in nearly every shot)")
    things: list[LPThing] = Field(default_factory=list, description="objects put down in the place (on the bedside table, the "
                                                                     "desk, the kitchen table)")
    sounds: list[LPSound] = Field(default_factory=list)
    pause: float = Field(0.0, description="extra seconds of silence after the line, for a beat to land (0-2)")
    red: bool = Field(False, description="the last line's punch, shown in red; only on the final line")


class Story(BaseModel):
    title: str = Field(description="2-5 words, the feeling or the promise ('The Ten-Minute Promise')")
    problem: str = Field(description="the everyday struggle in one plain line")
    youtube_title: str
    description: str = Field(description="2-3 sentences for the post, plain, no hashtags")
    tags: list[str]
    hashtags: list[str]
    thumbnail_text: str = Field(description="2-4 words")
    mood: Mood = Field(description="the music's mood for most of it")
    end_mood: Mood = Field(description="the music's mood for the ending")
    music_prompt: str = Field(description="the feeling of the score in a few words (soft felt piano...); no genre")
    cast: list[LPCast] = Field(default_factory=list, description="anyone besides him; keep it to the people the story needs")
    shots: list[LPShot]


RULES = """You write narrated 3D animated shorts in the style of the channel's own Short 'Life of a Man': one low-poly \
man (a big faceted head, curly brown hair, square glasses, a red sweater) living one small, relatable everyday \
struggle, told by a calm narrator over quiet piano. Captions show the words two or three at a time.

THE TELLING (study of the original, 33 s, 11 shots):
- Third person, present tense, about "he" (never a name unless one is given). Short plain sentences and fragments: \
"He pictures a 5:30 run. Tomorrow, for real." / "He sets the alarm. He means it." / "Smaller. Ten minutes. Then out." \
No metaphors, no lecture, no "we all...", no "and that's when he realised"; never address the viewer.
- Time you can feel: STAMPS ('11:47 P.M.', '5:30 A.M.', '6:10 A.M.', '7:45 A.M.', 'DAY 4', 'SUNDAY') mark the jumps; the \
clock only moves forward. A stamp shot may have a line or be a silent beat with a sound (the alarm).
- One specific struggle seen in specific details (a 5:30 run, ten minutes, shoes on but still inside). The promise or \
hope shrinks or grows each beat; the narration states facts and lets the picture carry the feeling.
- The ending lands in one short line, set `red` on that shot: a quiet sting or a small win, never a moral ("He \
couldn't keep a ten-minute promise." / "Day one counted anyway."). It may call back to the start.
- Nothing sexual, no self-harm, no violence, no real brands or real people; sadness with dignity.

THE PICTURES (the editor draws exactly what you set):
- Show what the line says: "He sets the alarm" = lying in bed, 'reach' or 'lie-phone'; "Shoes on." = 'shoes' sitting \
in the hallway; "He doesn't move" = 'lie' with the 'top' camera; a run he imagines = 'run' on the 'street' or in the \
'park'.
- Cameras: 'face' close-ups for feelings (in bed it looks down on his face), 'top' straight down on him lying, 'wide' \
for the room, 'side' and 'front' for walks and runs, 'medium' chest up, 'back' over his shoulder at what he faces, \
'low' from the floor, 'detail' for what he holds or the thing on the table. Never the same camera three shots running; \
mix close and far like the original (face, side, face, face, top, front, wide, side, top, side, face).
- Light follows the clock: late night 'night' or 'lamp', 5-6 A.M. 'dawn', morning 'morning', 'day', 'evening'.
- Spots per place (use only these): {spots}. Seats: bed (in the bedroom he lies on it or sits on its edge), chair, \
desk, couch. Lying actions ('lie', 'lie-side', 'lie-phone', 'sit-up') are for the bed (set `covered` under the blanket \
at night and early morning).
- Walking: 'walk'/'run'/'jog' move him; give `to` inside a room (to the door, the window), none outside (he crosses \
the street or comes down the park path toward the camera with 'front').
- Things: 'alarm' with its time as `label` on the bedside table, a 'phone' with `glow`, a 'mug', a 'laptop'; held \
things go in `hold` (a phone in his hand, a mug).
- Sounds: the world's own sounds where they happen: 'alarm' on the alarm, 'footsteps' are added to walks by the editor, \
'door', 'notify'/'buzz' for a phone, 'typing', 'tick' for time passing. A few, not on every shot.

LENGTH: {length}. Each shot holds about 2-4 seconds (its line plus a breath); a silent stamp beat about 2 s."""

SHORT = ("a 9:16 Short of {seconds} seconds: {shots} shots, about {words} words of narration in all, a stamp every 2-4 "
         "shots, one person (him) in nearly every shot")
FILM = ("a 16:9 short film of {minutes} minutes: {shots} shots, about {words} words. Shape it in acts: the habit and the "
        "promise (stamps through one night and morning), the loop (the same failure on more days, a bit smaller each time), "
        "the low point (a silent beat or two), a small turn that comes from outside him (a person, a message, a moment he "
        "sees himself), the climb (DAY stamps, short shots of small real progress in new places), a test, and the ending "
        "line in red. Two or three other people at most, each introduced by the narration ('His sister, Mia.').")

TOPICS = [
    "the 5 A.M. run that never happens", "one more episode before bed", "the gym bag packed every night, never opened",
    "the book on the bedside table", "calling his mum back tomorrow", "the side project that stays a folder",
    "cooking instead of ordering in", "the language app streak", "replying 'on my way' while still in bed",
    "the drawer of guitar strings", "drinking water instead of the fourth coffee", "the friend he keeps meaning to text",
    "standing up to stretch every hour", "going to bed before midnight", "saving a little every week", "the walk at lunch",
    "the dentist appointment he keeps moving", "cleaning the room on Sunday", "asking for the raise", "the first page of the journal",
]


def _history_path(cfg: Config) -> Path:
    return cfg.output_dir / "lowpoly_history.json"


def recent(cfg: Config) -> list[dict]:
    try:
        return json.loads(_history_path(cfg).read_text(encoding="utf-8"))[-60:]
    except (OSError, ValueError):
        return []


def remember(cfg: Config, story: Story) -> None:
    items = recent(cfg) + [{"title": story.title, "problem": story.problem}]
    try:
        _history_path(cfg).write_text(json.dumps(items[-300:], ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def _words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", s.lower()) if len(w) > 3}


def too_close(story: Story, past: list[dict]) -> str:
    mine = _words(story.problem + " " + story.title)
    for p in past:
        theirs = _words(p.get("problem", "") + " " + p.get("title", ""))
        if story.title.strip(". ").lower() == p.get("title", "").strip(". ").lower():
            return p.get("title", "")
        if mine and theirs and len(mine & theirs) / max(1, min(len(mine), len(theirs))) >= 0.6:
            return p.get("title", "")
    return ""


# ---------------------------------------------------------------- the cast, kept by name

def _cast_path(cfg: Config) -> Path:
    return cfg.output_dir / "lowpoly_cast.json"


def saved_cast(cfg: Config) -> dict[str, dict]:
    try:
        return json.loads(_cast_path(cfg).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def lock_cast(cfg: Config, story: Story) -> None:
    """Someone met before keeps the look they had; someone new is saved for the next films."""
    saved = saved_cast(cfg)
    changed = False
    for c in story.cast:
        k = _key(c.name)
        if not k or k in {"hero", "he", "him"}:
            continue
        if k in saved:
            c.design = LPDesign(**saved[k]["design"])
        else:
            saved[k] = {"name": c.name, "who": c.who, "design": c.design.model_dump()}
            changed = True
    if changed:
        try:
            _cast_path(cfg).write_text(json.dumps(saved, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass


def editor_design(d: LPDesign) -> dict:
    return {"skin": SKIN[d.skin], "hair": HAIR[d.hair], "hairStyle": d.hair_style, "glasses": d.glasses, "top": COLOURS[d.top],
            "topKind": d.top_kind, "trousers": COLOURS[d.trousers], "shoes": "#eeece7" if d.top_kind != "suit" else "#2a2a2e",
            "beard": d.beard, "height": 0.72 if d.kid else (0.97 if d.hair_style in ("long", "bun", "ponytail") else 1.0)}


def _known(cfg: Config) -> str:
    saved = saved_cast(cfg)
    if not saved:
        return ""
    lines = "\n".join(f"- {v['name']}: {v['who']}" for v in list(saved.values())[-20:])
    return ("\n\nPeople from earlier films (use the same name if one of them fits this story; their look is kept):\n" + lines)


# ---------------------------------------------------------------- writing

def write(cfg: Config, topic: str, *, short: bool, seconds: int = 35, minutes: float = 3.5, progress=log.info) -> Story:
    if short:
        shots = max(7, round(seconds / 3.0))
        length = SHORT.format(seconds=seconds, shots=shots, words=int(seconds * 1.85))
    else:
        shots = round(minutes * 60 / 3.3)
        length = FILM.format(minutes=f"{minutes:g}", shots=f"{shots - 8}-{shots + 6}", words=int(minutes * 60 * 1.8))
    spots = "; ".join(f"{k}: {', '.join(sorted(v))}" for k, v in SPOTS.items())
    system = RULES.format(spots=spots, length=length)
    past = recent(cfg)
    made = "\n".join(f"- {p['title']} ({p['problem']})" for p in past[-40:]) or "- none yet"
    ask_for = (f"Write it about: {topic}." if topic else
               "Choose the struggle yourself, different from the ones already made. Ideas (not a list to copy): " + ", ".join(TOPICS) + ".")
    prompt = f"{ask_for}\n\nAlready made (never the same struggle, story or title again):\n{made}{_known(cfg)}"
    story = ask(cfg.ai_backend, cfg.claude_model, system, prompt, Story, allow_web=False, effort=cfg.claude_effort, timeout=2400)
    near = too_close(story, past) if not topic else ""
    if near:
        progress(f"That story is too close to '{near}'; writing a different one")
        story = ask(cfg.ai_backend, cfg.claude_model, system, prompt + f"\n\nYour first idea was too close to '{near}'. Pick a "
                    "different struggle and story.", Story, allow_web=False, effort=cfg.claude_effort, timeout=2400)
    if short and "#shorts" not in [h.lower() for h in story.hashtags]:
        story.hashtags = story.hashtags[:2] + ["#shorts"]
    return story


def repair(story: Story) -> list[str]:
    """Fix what the editor can't draw, in code: an unknown spot, a lying action away from a bed, a cast member who
    isn't in the cast, more than one red line. Returns notes for the report."""
    notes = []
    names = {_key(c.name) for c in story.cast}
    for i, s in enumerate(story.shots):
        s.pause = max(0.0, min(2.0, s.pause))
        for a in s.actors:
            if a.who != "hero" and _key(a.who) not in names:
                a.who = "hero"
            if a.spot not in SPOTS[s.set]:
                a.spot = "bed" if a.action.startswith("lie") and "bed" in SPOTS[s.set] else "center"
            if a.action in ("lie", "lie-side", "lie-phone", "sit-up") and a.spot != "bed":
                if "bed" in SPOTS[s.set]:
                    a.spot = "bed"
                elif a.action == "sit-up":
                    a.action = "sit"
            if a.to and a.to not in SPOTS[s.set]:
                a.to = None
        if not s.actors:
            s.actors = [LPActor(who="hero", action="stand", expression="neutral", spot="center")]
            notes.append(f"Shot {i + 1} had nobody in it; he stands there.")
    reds = [i for i, s in enumerate(story.shots) if s.red]
    for i in reds[:-1]:
        story.shots[i].red = False
    if not reds and story.shots:
        last = next((s for s in reversed(story.shots) if s.line.strip()), None)
        if last:
            last.red = True
    return notes


def save(story: Story, path: Path) -> None:
    path.write_text(story.model_dump_json(indent=1), encoding="utf-8")


def load(path: Path) -> Story:
    return Story.model_validate_json(path.read_text(encoding="utf-8"))
