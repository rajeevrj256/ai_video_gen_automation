"""The writer for the low-poly films: one Claude call (no web) writes the narration and stages every shot in the
editor's own vocabulary (sets, lights, cameras, actions, faces, things, sounds), for a Short (9:16, 20-60 s) or a
short film (3-4 min). Modelled on the user's own Short 'Life of a Man' (analysed: 33 s, 11 shots of ~3 s, a calm
narrator in short present-tense sentences, time stamps as chapter marks (11:47 P.M. -> 5:30 A.M. -> 6:10 A.M. ->
7:45 A.M.), the promise getting smaller each time, a last line in red that stings). The hero is always the same man
(remotion/src/lowpoly/Man.tsx HERO); anyone else is designed once and kept by name (<output>/lowpoly_cast.json),
which starts with a library of recurring people (CAST_LIBRARY: his sister, his best friend, his parents, his boss...)
that every film can use. Two kinds of story: `life` (the reference's small everyday struggle) and `fiction` (the
user's brief for a cinematic film: dialogue in each person's own voice, superpowers, big objects, effects, slow motion)."""
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

SetName = Literal["bedroom", "hallway", "street", "park", "kitchen", "living", "office", "bathroom", "gym", "cafe", "busstop", "rooftop",
                  "construction", "highway", "alley", "lab", "void"]
LightName = Literal["night", "lamp", "dawn", "morning", "day", "evening", "dark"]
CamName = Literal["face", "face-top", "top", "medium", "wide", "side", "front", "back", "low", "detail", "aerial", "orbit", "crash-zoom"]
ActionName = Literal[
    "stand", "walk", "run", "sit", "sit-floor", "lie", "lie-side", "lie-phone", "phone", "type", "reach", "sit-up", "get-up", "shoes",
    "head-in-hands", "slump", "stretch", "sigh", "nod", "shake-head", "shrug", "think", "drink", "eat", "look-out", "wave", "point",
    "cheer", "jog", "pushup", "read", "cry",
    "lift", "catch", "push-stop", "throw", "super-jump", "land", "dash", "punch", "crush", "look-hands", "crouch", "kneel", "carry",
    "carried", "fall", "flee", "cower", "help-up", "talk", "gasp"]
ExprName = Literal["neutral", "tired", "sad", "worried", "surprised", "happy", "determined", "annoyed", "asleep", "blank", "scared",
                   "angry", "amazed", "pained"]
SpotName = Literal["center", "left", "right", "bed", "chair", "desk", "door", "window", "couch", "mirror", "counter", "far"]
HoldName = Literal["none", "phone", "mug", "book", "laptop", "shoes", "bag", "keys", "fork"]
ThingName = Literal["phone", "alarm", "mug", "laptop", "book", "shoes", "plate", "bag", "plant", "bottle", "calendar", "note", "pizza"]
SoundName = Literal["alarm", "footsteps", "door", "knock", "notify", "buzz", "typing", "tap", "ding", "chime", "bell", "page", "rain",
                    "thud", "heartbeat", "tick", "coins", "cheer", "pop", "scribble", "swoosh", "send",
                    "impact", "crash", "glass", "crack", "creak", "skid", "siren", "wind", "fire", "sparks", "rumble", "flyby", "crowd"]
Mood = Literal["calm", "emotional", "uplifting", "curious", "mystery", "dark", "suspense", "energetic"]
BigName = Literal["car", "bus", "truck", "beam", "crate", "boulder", "barbell", "pipe", "door", "ball"]
MotionName = Literal["still", "fall", "caught", "lifted", "held", "thrown", "stop", "drive", "crushed", "hang", "shake"]
FxName = Literal["shockwave", "crack", "dust", "speed", "sparks", "debris", "glass", "smoke", "fire", "shake", "flash", "alarm", "rain", "wind"]
VoiceKind = Literal["man", "young-man", "woman", "young-woman", "older-man", "older-woman", "child", "deep-man", "british-man",
                    "british-woman"]
KINDS = ("life", "fiction")

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
    "construction": {"center", "left", "right", "far", "chair", "door"},
    "highway": {"center", "left", "right", "far", "door"},
    "alley": {"center", "left", "right", "far", "door", "chair"},
    "lab": {"center", "left", "right", "desk", "chair", "counter", "far", "door"},
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
    hat: Literal["none", "hardhat", "cap"] = "none"


class LPCast(BaseModel):
    name: str = Field(description="how the narrator names them: 'his mum', 'Sara', 'his boss' (never the hero)")
    who: str = Field(description="one line: who they are to him")
    design: LPDesign
    voice: VoiceKind = Field("man", description="the kind of voice they speak in, when they have lines")


class LPActor(BaseModel):
    who: str = Field(description="'hero' for him, else a cast member's name exactly")
    action: ActionName
    expression: ExprName
    spot: SpotName
    to: SpotName | None = Field(None, description="walk/run/jog only: the spot he walks to (else he walks across the frame)")
    facing: Literal["camera", "left", "right", "away"] = Field("camera", description="camera = the spot's natural way (at the desk toward the screen, otherwise toward the camera); away = his back to the camera, facing the counter, window or door; left/right "
                                                              "= across the room. Seated and lying people keep their seat's way")
    hold: HoldName = "none"
    covered: bool = Field(False, description="in bed under the blanket")
    at: float | None = Field(None, description="for an action with a moment (catch, lift, throw, push-stop, super-jump, land, punch, "
                                               "fall): when it happens, as a fraction 0-1 of the shot; else none")
    look_at: str = Field("", description="the person in this shot they look at, talk to, point at or walk up to: 'hero' or "
                                         "that person's name exactly; empty when nobody in particular. They turn to face "
                                         "them (seated or walking: their head turns)")


class LPThing(BaseModel):
    kind: ThingName
    label: str = Field("", description="the alarm clock's time ('5:30'), a note's or calendar's word; empty otherwise")
    glow: bool = Field(False, description="a lit screen")


class LPSound(BaseModel):
    sound: SoundName
    word: str = Field("", description="a word of this shot's line it lands on; empty = the start of the shot")


class LPBig(BaseModel):
    kind: BigName
    spot: SpotName = "center"
    motion: MotionName = Field(description="still; fall (drops from high onto its spot); caught (drops into the hands of the one who "
                                           "'catch'es); hang (swings from the crane's cable; with `at` the cable snaps then and it "
                                           "falls into the hands of the one who 'catch'es); lifted (raised overhead by the one who "
                                           "'lift's); held (already overhead, or carried); thrown (flung from overhead by the one who "
                                           "'throw's); stop (drives at the one who 'push-stop's and stops against his hands); drive "
                                           "(drives across); crushed; shake")
    at: float | None = Field(None, description="when its moment happens, a fraction 0-1 of the shot")
    color: Literal["", "red", "navy", "green", "mustard", "grey", "white", "black", "teal", "blue", "orange", "maroon"] = ""


class LPFx(BaseModel):
    kind: FxName
    at: float | None = Field(None, description="when it starts, a fraction 0-1 of the shot (rain and wind run the whole shot)")
    spot: SpotName | None = Field(None, description="where; none = where the action is")


class LPShot(BaseModel):
    stamp: str = Field("", description="a time or day stamp shown big as the shot starts ('11:47 P.M.', '5:30 A.M.', 'DAY 3', "
                                         "'SATURDAY'); empty for most shots")
    line: str = Field(description="the words over this shot: one short sentence or a fragment, at most 12 words; "
                                  "'' for a silent beat")
    speaker: str = Field("narrator", description="who says the line: 'narrator', 'hero' (he speaks), or a cast member's name "
                                                 "exactly (their mouth moves if they are in the shot)")
    set: SetName
    light: LightName
    camera: CamName
    subject: str = Field("", description="who the camera is on: 'hero' or the name of someone in the shot (the one who "
                                         "speaks, points, reacts or acts in this moment); empty = him")
    actors: list[LPActor] = Field(description="who is in the shot and what they do (the hero in nearly every shot)")
    things: list[LPThing] = Field(default_factory=list, description="objects put down in the place (on the bedside table, the "
                                                                     "desk, the kitchen table)")
    sounds: list[LPSound] = Field(default_factory=list)
    pause: float = Field(0.0, description="extra seconds of silence after the line, for a beat to land or an action to play out "
                                          "(0-2; fiction up to 4)")
    red: bool = Field(False, description="the last line's punch, shown in red; only on the final line")
    big: list[LPBig] = Field(default_factory=list, description="big objects in the shot and what they do (fiction)")
    fx: list[LPFx] = Field(default_factory=list, description="effects (fiction): most come with the actions by themselves")
    slowmo: bool = Field(False, description="the action in slow motion (the key rescue moment, a catch); give it a longer pause")


class ScorePart(BaseModel):
    from_shot: int = Field(description="the shot (1 = first) where this part of the score starts")
    mood: Mood
    energy: Literal["low", "medium", "high"]


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
    score: list[ScorePart] = Field(default_factory=list, description="fiction: the score's parts as the story moves (3-7), the "
                                                                    "first from shot 1; empty for life stories")
    kind: Literal["life", "fiction"] = "life"


# Two or more people in a shot (the user: the son should look at and point to his dad on the chair, not walk off; and
# people walked through each other). Shared by every kind of film.
STAGING = """
TWO OR MORE PEOPLE IN A SHOT (stage it like a film director):
- Each person on their own spot (left, center, right, chair, door...), never two on one spot unless they sit on a \
couch together. People who walk side by side are both 'walk' from the same spot; the editor keeps them apart.
- `look_at` on everyone who looks at, talks to, answers, points at, reaches for or walks up to someone: that person's \
name or 'hero'. They turn to face them (sitting or walking, their head turns). A line said to someone always has \
`look_at` on the speaker and on the one listening. "He points to his dad on the chair" = the one pointing stands \
('point', `look_at` the dad), the dad sits on 'chair'; nobody walks away in that shot.
- `subject` = who the moment is about (the one who speaks, points, reacts or acts); the camera is on them.
- Cameras with two people: 'medium' = both in frame (a two-shot: who looks at whom is clear); 'back' = over the \
subject's shoulder at the person they face; 'face' = one face only (a reaction), so never for a gesture at someone \
else; 'wide' = the whole place and everyone in it. A shot whose line or action is about someone else in the room \
(points at him, looks at her, walks up to him) must show both people: 'medium', 'back' or 'wide'.
- A walk with a purpose: 'walk' with `to` the spot of the person they go to (they stop in front of them, facing \
them) and `look_at` that person.
"""


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
""" + STAGING + """
LENGTH: {length}. Each shot holds about 2-4 seconds (its line plus a breath); a silent stamp beat about 2 s."""

SHORT = ("a 9:16 Short of {seconds} seconds: {shots} shots, about {words} words of narration in all, a stamp every 2-4 "
         "shots, one person (him) in nearly every shot")
FILM = ("a 16:9 short film of {minutes} minutes: {shots} shots, about {words} words. Shape it in acts: the habit and the "
        "promise (stamps through one night and morning), the loop (the same failure on more days, a bit smaller each time), "
        "the low point (a silent beat or two), a small turn that comes from outside him (a person, a message, a moment he "
        "sees himself), the climb (DAY stamps, short shots of small real progress in new places), a test, and the ending "
        "line in red. Two or three other people at most, each introduced by the narration ('His sister, Mia.').")

FICTION = """You write and direct original cinematic 3D animated short films with dialogue, starring the channel's own \
low-poly man (a big faceted head, curly brown hair, square glasses, a red sweater: 'hero'; the same man in every film). \
The user gives you a brief: follow it closely, it is the film they want. Make it feel like a scene from a big-budget \
animated movie, told through the editor below, which draws exactly what you set.

THE FILM:
- A visual HOOK in the first 5 seconds: open on the most spectacular moment from later (a steel beam caught overhead in \
slow motion, a truck stopped by bare hands), cut away on it, then a stamp ('THREE DAYS EARLIER') and the story from \
its start. The audience must want to know how he got there.
- Then build in acts: his ordinary life (one or two shots, a person who matters to him); the discovery by accident \
(he crushes a mug without trying, a door handle comes off, he catches something falling before it falls) with fear \
and wonder on his face; testing it, each test bigger (a barbell, then a car overhead, a super-speed dash, a super-jump \
over the city, reflexes); the danger, where innocent people need him (a beam falling at workers, a truck out of \
control toward a child), the rescue in slow motion, the hook's moment coming back in its place; the consequences of \
too much power (people afraid of him, someone he loves looks at him differently, things break when he isn't careful, \
someone wants to use him); and an ending that turns to the viewer with one thought-provoking question, in red.
- Every shot has a beginning, an action and an end: choose an action with a moment (`at`), and let the next shot pick \
up from it (he lands, the next shot is the ground cracking; he looks up, the next shot is what he sees). Cut on \
action. No two shots running with the same action, place and camera. Never a static shot of him just standing unless \
the moment is stillness.
- WORDS: mostly dialogue, in short natural lines (`speaker` = 'hero' or a cast name; a speaker should be in the shot). \
A narrator only where it earns its place (the hook's stamp, a time jump, the ending question), calm and brief. Many \
action shots have no line at all: the picture and the sound carry them (give them a `pause` of 1-3 s so they play out).
- People: use the recurring cast below when the story needs that kind of person (their look and voice are kept); \
invent a new person only when nobody fits, and give them a fitting look and voice. Three to six people, each with a \
reason to be there. Name them through the dialogue.
- No killing, no blood, no one hurt on screen; he never punches a person (only a wall, a boulder, the ground); danger \
is about saving people. No capes, costumes, logos or names from existing superhero films; no real brands or people.

THE EDITOR'S VOCABULARY (use only these):
- Places and their spots: {spots}. 'construction' = a building site with a steel frame, a tower crane, barriers, a site \
office (door) and crates (chair); 'highway' = a wide road along the frame, guard rails, the city beyond ('center' and \
the near lane 'left'/'right' are on the road, 'door' is the roadside); 'alley' = a narrow brick alley (night is best), \
a dumpster, a door with a lamp, a fire escape; 'lab' = a white lab with a glowing chamber ('far' = inside it), a \
console ('desk'/'counter') and screens; 'rooftop' over the city; 'gym' for the barbell; 'street', 'park', and his \
flat (bedroom, kitchen, living, hallway, bathroom).
- Power actions: 'catch' (arms up, the thing lands in his hands at `at`; pair with a big thing 'caught' or 'hang' with \
`at`), 'lift' (crouch, then overhead at `at`; pair with 'lifted'), 'throw' (pair with 'thrown'), 'push-stop' (braced; \
a 'car'/'bus'/'truck' with 'stop' hits his hands at `at` and he is driven back; best with the 'side' or 'wide' camera), \
'super-jump' (crouch, then up out of the shot at `at`), 'land' (drops from the sky into a one-knee landing at `at`), \
'dash' (super speed across the place: speed streaks), 'punch' (at a wall or the ground), 'crush' (squeezes a thing in \
his hand: hold a mug, a phone), 'look-hands' (stares at his own hands). Everyone: 'talk', 'gasp', 'flee' (runs away \
scared), 'cower' (crouched, arms over the head), 'fall' (knocked down), 'help-up' (a hand down to someone), 'kneel', \
'crouch', 'carry' (carries a person who is 'carried' in the same shot, the carrier listed first; with `to` he walks).
- Big things ('big'): car, bus, truck, beam (steel girder), crate, boulder, barbell, pipe, door, ball, with a motion \
and `at`. Effects ('fx'): shockwave, crack, dust, speed, sparks, debris, glass, smoke, fire, shake, flash, alarm (red \
and blue emergency light), rain, wind. The editor already adds the usual ones to an action (a landing cracks the \
ground with a shockwave and dust and shakes the camera; a stopped truck throws sparks; a dash leaves streaks), so add \
only what else the moment needs (fire and smoke after a crash, rain for mood, glass when a window breaks).
- Cameras: 'face' (close-up), 'medium', 'wide', 'side' (tracks a run, best for the dash and the stop), 'front', 'back' \
(over his shoulder at what he faces), 'low' (from the ground: power, landings), 'detail' (what he holds), 'aerial' \
(high above, circling, outdoors: the city, the scale of the danger), 'orbit' (circles him at his height: the moment he \
understands), 'crash-zoom' (a fast push into his face: a realisation). 'top' and 'face-top' for lying down. Mix close \
and far; a cinematic rhythm.
- `slowmo` on the two or three key moments (the catch, the stop, the save), with a longer `pause`.
- Light follows time and mood: 'day', 'morning', 'dawn', 'evening' (golden), 'night', 'dark', 'lamp' indoors at night.
- Sounds: the world's sounds where they happen ('crash', 'glass', 'skid', 'siren', 'creak' for straining metal, \
'crowd' for frightened people, 'wind', 'fire', 'heartbeat' before the moment, 'impact'); the editor adds the usual ones \
to actions. The score: `score` parts that follow the story (calm for his life, mystery for the discovery, energetic \
for the tests, suspense for the danger, emotional for the consequences, a quiet end).
""" + STAGING + """
LENGTH: {length}."""

FICTION_SHORT = ("a 9:16 Short of {seconds} seconds: {shots} shots of 1.5-4 s, about {words} words in all (dialogue and a "
                 "little narration); hook in the first 2 seconds, the turn in the middle, the question at the end")
FICTION_FILM = ("a 16:9 film of {minutes} minutes: {shots} shots of 2-5 s, about {words} words in all, most shots short and "
                "full of action, a few quiet ones that let a feeling land")

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


def _d(**kw) -> dict:
    return LPDesign(**kw).model_dump()


# The recurring people every film can use (the user: "build some more character and store and use that on films"):
# put into <output>/lowpoly_cast.json the first time, then kept like anyone Claude invents. Edit a look there or in
# the tab; a saved look always wins.
CAST_LIBRARY: list[dict] = [
    {"name": "Mia", "who": "his younger sister, a nurse, sharp and protective of him", "voice": "young-woman",
     "design": _d(skin="light", hair="auburn", hair_style="long", top="teal", top_kind="sweater", trousers="denim")},
    {"name": "Sam", "who": "his best friend since school, loud, funny and loyal", "voice": "man",
     "design": _d(skin="brown", hair="black", hair_style="short", top="mustard", top_kind="hoodie", trousers="black", beard=True)},
    {"name": "his mum", "who": "his mother, warm, worries about him, calls every Sunday", "voice": "older-woman",
     "design": _d(skin="light", hair="grey", hair_style="bun", glasses=True, top="cream", top_kind="sweater", trousers="brown")},
    {"name": "his dad", "who": "his father, quiet, fixes things, says little and means it", "voice": "older-man",
     "design": _d(skin="fair", hair="grey", hair_style="bald", glasses=True, top="navy", top_kind="shirt", trousers="grey", beard=True)},
    {"name": "Mr. Hale", "who": "his boss, strict, always in a suit, never smiles", "voice": "deep-man",
     "design": _d(skin="pale", hair="grey", hair_style="short", top="black", top_kind="suit", trousers="black")},
    {"name": "Priya", "who": "his neighbour across the hall, a medical student he likes", "voice": "young-woman",
     "design": _d(skin="tan", hair="black", hair_style="ponytail", top="purple", top_kind="sweater", trousers="navy")},
    {"name": "Leo", "who": "the neighbours' eight-year-old son, curious about everything", "voice": "child",
     "design": _d(skin="fair", hair="blonde", hair_style="curly", top="orange", top_kind="hoodie", trousers="denim", kid=True)},
    {"name": "Dr. Lena Voss", "who": "a scientist who wants to study what is happening to him", "voice": "british-woman",
     "design": _d(skin="pale", hair="white", hair_style="bun", glasses=True, top="white", top_kind="shirt", trousers="grey")},
    {"name": "Rafi", "who": "the foreman at the building site on his street", "voice": "man",
     "design": _d(skin="brown", hair="black", hair_style="short", top="orange", top_kind="hoodie", trousers="navy", beard=True,
                  hat="hardhat")},
    {"name": "Officer Dana", "who": "a police officer in his neighbourhood, calm under pressure", "voice": "woman",
     "design": _d(skin="dark", hair="black", hair_style="bun", top="navy", top_kind="shirt", trousers="navy", hat="cap")},
    {"name": "Grandpa Joe", "who": "his grandfather, tells old stories, sees more than he says", "voice": "older-man",
     "design": _d(skin="light", hair="white", hair_style="short", glasses=True, top="brown", top_kind="sweater", trousers="beige",
                  beard=True)},
    {"name": "Kai", "who": "the trainer at his gym, big-hearted and hard to impress", "voice": "young-man",
     "design": _d(skin="dark", hair="black", hair_style="bald", top="black", top_kind="hoodie", trousers="grey")},
    {"name": "Nora", "who": "the barista at the cafe he goes to every morning", "voice": "young-woman",
     "design": _d(skin="light", hair="blonde", hair_style="ponytail", top="green", top_kind="shirt", trousers="black")},
    {"name": "Victor Crane", "who": "a rich, smooth businessman who wants to own what others can do", "voice": "british-man",
     "design": _d(skin="pale", hair="black", hair_style="short", top="maroon", top_kind="suit", trousers="black")},
]

# edge-tts voices for each kind of voice (the first one free is taken; the narrator's and the hero's are never reused)
VOICES: dict[str, list[str]] = {
    "man": ["en-US-GuyNeural", "en-US-EricNeural"], "young-man": ["en-US-BrianNeural", "en-US-EricNeural"],
    "woman": ["en-US-AriaNeural", "en-US-JennyNeural"], "young-woman": ["en-US-EmmaNeural", "en-US-AvaNeural"],
    "older-man": ["en-US-RogerNeural", "en-US-SteffanNeural"], "older-woman": ["en-US-MichelleNeural", "en-US-JennyNeural"],
    "child": ["en-US-AnaNeural"], "deep-man": ["en-US-SteffanNeural", "en-US-RogerNeural"],
    "british-man": ["en-GB-RyanNeural", "en-GB-ThomasNeural"], "british-woman": ["en-GB-SoniaNeural", "en-GB-LibbyNeural"],
}
HERO_VOICES = ["en-US-AndrewNeural", "en-US-BrianNeural"]  # a warm young man's voice for him when he speaks


def seed_library(cfg: Config) -> dict[str, dict]:
    """The saved cast with the library's people added (never over a saved look)."""
    saved = saved_cast(cfg)
    added = False
    for c in CAST_LIBRARY:
        k = _key(c["name"])
        if k not in saved:
            saved[k] = dict(c, library=True)
            added = True
    if added:
        try:
            _cast_path(cfg).parent.mkdir(parents=True, exist_ok=True)
            _cast_path(cfg).write_text(json.dumps(saved, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass
    return saved


def add_person(cfg: Config, name: str, who: str, design: dict, voice: str = "man") -> dict:
    """A person the user designed in the tab, kept for every film from now on (a saved name gets the new look)."""
    saved = seed_library(cfg)
    entry = {"name": name.strip()[:40], "who": who.strip()[:160], "design": LPDesign(**design).model_dump(),
             "voice": voice if voice in VOICES else "man", "mine": True}
    saved[_key(entry["name"])] = entry
    _cast_path(cfg).write_text(json.dumps(saved, ensure_ascii=False, indent=1), encoding="utf-8")
    return entry


def remove_person(cfg: Config, name: str) -> bool:
    saved = saved_cast(cfg)
    if _key(name) not in saved:
        return False
    del saved[_key(name)]
    _cast_path(cfg).write_text(json.dumps(saved, ensure_ascii=False, indent=1), encoding="utf-8")
    return True


def voices_for(story: Story, narrator: str) -> dict[str, str]:
    """Each speaker's edge voice: 'narrator' the chosen narrator, 'hero' a warm young man's, each cast member the first
    free voice of their kind (two people never share one)."""
    out = {"narrator": narrator}
    used = {narrator}
    hero = next((v for v in HERO_VOICES if v not in used), HERO_VOICES[0])
    out["hero"] = hero
    used.add(hero)
    for c in story.cast:
        pool = VOICES.get(c.voice, VOICES["man"])
        pick = next((v for v in pool if v not in used), None)
        if not pick:  # the kind's voices are taken: any voice nobody has
            pick = next((v for p in VOICES.values() for v in p if v not in used), pool[0])
        out[_key(c.name)] = pick
        used.add(pick)
    return out


def lock_cast(cfg: Config, story: Story) -> None:
    """Someone met before (or from the library) keeps the look and voice they had; someone new is saved for the next
    films."""
    saved = seed_library(cfg)
    changed = False
    # someone from the recurring cast who acts or speaks in a shot but was left out of the story's cast list comes in
    # with their saved look (else repair would turn them into a second hero)
    listed = {_key(c.name) for c in story.cast}
    named = {a.who for s in story.shots for a in s.actors if a.who != "hero"} | {s.speaker for s in story.shots}
    for name in sorted(named):
        k = _key(name)
        if k in saved and k not in listed:
            v = saved[k]
            story.cast.append(LPCast(name=v["name"], who=v.get("who", ""), design=LPDesign(**v["design"]),
                                     voice=v.get("voice") if v.get("voice") in VOICES else "man"))
            listed.add(k)
    for c in story.cast:
        k = _key(c.name)
        if not k or k in {"hero", "he", "him"}:
            continue
        if k in saved:
            c.design = LPDesign(**saved[k]["design"])
            if saved[k].get("voice") in VOICES:
                c.voice = saved[k]["voice"]
        else:
            saved[k] = {"name": c.name, "who": c.who, "design": c.design.model_dump(), "voice": c.voice}
            changed = True
    if changed:
        try:
            _cast_path(cfg).write_text(json.dumps(saved, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass


def editor_design(d: LPDesign) -> dict:
    return {"skin": SKIN[d.skin], "hair": HAIR[d.hair], "hairStyle": d.hair_style, "glasses": d.glasses, "top": COLOURS[d.top],
            "topKind": d.top_kind, "trousers": COLOURS[d.trousers], "shoes": "#eeece7" if d.top_kind != "suit" else "#2a2a2e",
            "beard": d.beard, "height": 0.72 if d.kid else (0.97 if d.hair_style in ("long", "bun", "ponytail") else 1.0),
            "hat": d.hat}


def _known(cfg: Config) -> str:
    saved = seed_library(cfg)
    if not saved:
        return ""
    lines = "\n".join(f"- {v['name']}: {v['who']} ({v.get('voice', 'man')} voice)" for v in list(saved.values())[-40:])
    return ("\n\nTHE RECURRING CAST (people from the channel's films; when the story needs someone like one of them, use them "
            "with this exact name: their look and voice are kept, so the films share one world):\n" + lines)


# ---------------------------------------------------------------- writing

# ---------------------------------------------------------------- long films: an outline, then each act

LONG_FROM = 5.0  # minutes: a film this long is written as an outline and then act by act (one answer can't hold 300 shots)


class ActPlan(BaseModel):
    name: str = Field(description="a short working name ('The storm', 'Testing it')")
    minutes: float = Field(description="how long this act runs")
    summary: str = Field(description="what happens in it, beat by beat, in 3-6 sentences: who, where, what changes")
    places: list[SetName] = Field(description="the places it uses")
    ends_with: str = Field(description="the moment it ends on, which the next act picks up from")
    mood: Mood = Field(description="the score's mood under it")
    energy: Literal["low", "medium", "high"]


class Outline(BaseModel):
    title: str = Field(description="2-5 words")
    problem: str = Field(description="the story in one plain line")
    youtube_title: str
    description: str = Field(description="2-3 sentences for the post, plain, no hashtags")
    tags: list[str]
    hashtags: list[str]
    thumbnail_text: str = Field(description="2-4 words")
    mood: Mood
    end_mood: Mood
    music_prompt: str = Field(description="the feeling of the score in a few words; no genre")
    cast: list[LPCast] = Field(default_factory=list, description="everyone besides him the whole film needs")
    acts: list[ActPlan] = Field(description="the film's acts in order, their minutes adding up to its length")


class ActShots(BaseModel):
    shots: list[LPShot]


def _act_len(fiction: bool, minutes: float) -> tuple[int, int]:
    """Shots and words for this many minutes."""
    return (round(minutes * 60 / (3.0 if fiction else 3.3)), int(minutes * 60 * (1.3 if fiction else 1.8)))


def write_long(cfg: Config, ask_for: str, made: str, *, minutes: float, fiction: bool, progress=log.info,
               save_to: Path | None = None) -> Story:
    """A 6-15 minute film: one call plans it (title, cast, acts with their minutes, places, moods), then one call per act
    writes that act's shots knowing the whole plan and how the act before it ended. Each finished part is kept in
    `save_to`, so a stopped or failed run carries on from the next act."""
    spots = "; ".join(f"{k}: {', '.join(sorted(v))}" for k, v in SPOTS.items())
    n_acts = max(4, min(9, round(minutes / 1.7)))
    shots, words = _act_len(fiction, minutes)
    whole = (FICTION_FILM if fiction else FILM).format(minutes=f"{minutes:g}", shots=f"{shots - 10}-{shots + 10}", words=words)
    plan_system = (FICTION if fiction else RULES).format(spots=spots, length=whole) + f"""

THIS FILM IS LONG ({minutes:g} minutes), so plan it first: {n_acts} acts (give or take one) whose minutes add up to
{minutes:g}. A long film needs more than a long version of a short one: a fuller world (more places, two to six people
with their own wants), a middle that turns more than once, set-ups paid off later, quiet scenes between the big ones,
and the ending's line in red. Write the outline only; the shots come next, act by act."""
    saved = json.loads(save_to.read_text(encoding="utf-8")) if save_to and save_to.exists() else {}
    if "outline" in saved:
        outline = Outline.model_validate(saved["outline"])
    else:
        progress(f"Planning the {minutes:g}-minute film in acts")
        outline = ask(cfg.ai_backend, cfg.claude_model, plan_system, f"{ask_for}\n\nAlready made (never the same story or title "
                      f"again):\n{made}{_known(cfg)}", Outline, allow_web=False, effort=cfg.claude_effort, timeout=2400)
        saved = {"outline": outline.model_dump(), "acts": []}
        if save_to:
            save_to.write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")
    acts: list[list[LPShot]] = [[LPShot.model_validate(x) for x in a] for a in saved.get("acts", [])]
    plan = "\n".join(f"Act {i + 1} ({a.minutes:g} min, {a.name}): {a.summary} Ends with: {a.ends_with}" for i, a in enumerate(outline.acts))
    cast = "\n".join(f"- {c.name}: {c.who} ({c.voice} voice)" for c in outline.cast) or "- nobody else"
    for i, act in enumerate(outline.acts):
        if i < len(acts):
            continue
        a_shots, a_words = _act_len(fiction, act.minutes)
        length = (f"this act only, about {act.minutes:g} minutes: {max(6, a_shots - 4)}-{a_shots + 4} shots, about {a_words} words")
        system = (FICTION if fiction else RULES).format(spots=spots, length=length)
        before = acts[-1][-6:] if acts else []
        before_text = "\n".join(f"- [{x.set}, {x.camera}] {x.speaker + ': ' if x.line else ''}{x.line or '(silent)'} "
                                 f"({'; '.join(f'{y.who} {y.action}' for y in x.actors)})" for x in before)
        first, last = i == 0, i == len(outline.acts) - 1
        progress(f"Writing act {i + 1} of {len(outline.acts)}: {act.name} ({act.minutes:g} min)")
        prompt = (f"{ask_for}\n\nTHE FILM: '{outline.title}': {outline.problem}\nThe acts:\n{plan}\n\nThe people (use these names "
                  f"exactly):\n{cast}\n\nWrite ACT {i + 1} of {len(outline.acts)} now, and only it: {act.summary} It ends with: "
                  f"{act.ends_with} Places: {', '.join(act.places)}.\n"
                  + ("This is the first act: it opens on the film's hook.\n" if first else
                     f"Carry straight on from how act {i} ended:\n{before_text}\n")
                  + ("This is the last act: it ends on the film's last line, set `red`.\n" if last else
                     "Not the last act: no `red` line, no ending yet.\n"))
        part = ask(cfg.ai_backend, cfg.claude_model, system, prompt, ActShots, allow_web=False, effort=cfg.claude_effort, timeout=2400)
        acts.append(part.shots)
        if save_to:
            saved["acts"] = [[x.model_dump() for x in a] for a in acts]
            save_to.write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")
    all_shots = [x for a in acts for x in a]
    starts, k = [], 1
    for a in acts:
        starts.append(k)
        k += len(a)
    score = [ScorePart(from_shot=st, mood=act.mood, energy=act.energy) for st, act in zip(starts, outline.acts)]
    o = outline.model_dump(exclude={"acts"})
    o["cast"] = outline.cast
    return Story(**o, shots=all_shots, score=score, kind="fiction" if fiction else "life")


def write(cfg: Config, topic: str, *, short: bool, seconds: int = 35, minutes: float = 3.5, progress=log.info,
          kind: str = "life", save_to: Path | None = None) -> Story:
    fiction = kind == "fiction"
    spots = "; ".join(f"{k}: {', '.join(sorted(v))}" for k, v in SPOTS.items())
    if fiction:
        if short:
            length = FICTION_SHORT.format(seconds=seconds, shots=max(9, round(seconds / 2.6)), words=int(seconds * 1.3))
        else:
            shots = round(minutes * 60 / 3.0)
            length = FICTION_FILM.format(minutes=f"{minutes:g}", shots=f"{shots - 8}-{shots + 8}", words=int(minutes * 60 * 1.3))
        system = FICTION.format(spots=spots, length=length)
    else:
        if short:
            shots = max(7, round(seconds / 3.0))
            length = SHORT.format(seconds=seconds, shots=shots, words=int(seconds * 1.85))
        else:
            shots = round(minutes * 60 / 3.3)
            length = FILM.format(minutes=f"{minutes:g}", shots=f"{shots - 8}-{shots + 6}", words=int(minutes * 60 * 1.8))
        system = RULES.format(spots=spots, length=length)
    past = recent(cfg)
    made = "\n".join(f"- {p['title']} ({p['problem']})" for p in past[-40:]) or "- none yet"
    if fiction:
        ask_for = (f"THE BRIEF (the user's own; follow it closely):\n{topic}" if topic else
                   "Invent an original sci-fi or fantasy premise for him (an ordinary man meets something extraordinary), "
                   "different from the films already made.")
    else:
        ask_for = (f"Write it about: {topic}." if topic else
                   "Choose the struggle yourself, different from the ones already made. Ideas (not a list to copy): " + ", ".join(TOPICS) + ".")
    if not short and minutes > LONG_FROM:
        story = write_long(cfg, ask_for, made, minutes=minutes, fiction=fiction, progress=progress, save_to=save_to)
        story.kind = "fiction" if fiction else "life"
        return story
    prompt = f"{ask_for}\n\nAlready made (never the same struggle, story or title again):\n{made}{_known(cfg)}"
    story = ask(cfg.ai_backend, cfg.claude_model, system, prompt, Story, allow_web=False, effort=cfg.claude_effort, timeout=2400)
    near = too_close(story, past) if not topic else ""
    if near:
        progress(f"That story is too close to '{near}'; writing a different one")
        story = ask(cfg.ai_backend, cfg.claude_model, system, prompt + f"\n\nYour first idea was too close to '{near}'. Pick a "
                    "different struggle and story.", Story, allow_web=False, effort=cfg.claude_effort, timeout=2400)
    if short and "#shorts" not in [h.lower() for h in story.hashtags]:
        story.hashtags = story.hashtags[:2] + ["#shorts"]
    story.kind = "fiction" if fiction else "life"
    return story


def repair(story: Story) -> list[str]:
    """Fix what the editor can't draw, in code: an unknown spot, a lying action away from a bed, a cast member who
    isn't in the cast, more than one red line. Returns notes for the report."""
    notes = []
    names = {_key(c.name) for c in story.cast}
    fiction = story.kind == "fiction"
    for i, s in enumerate(story.shots):
        s.pause = max(0.0, min(4.0 if fiction else 2.0, s.pause))
        sp = (s.speaker or "narrator").strip()
        s.speaker = "hero" if sp.lower() in ("hero", "he", "him") else "narrator" if _key(sp) not in names else sp
        for a in s.actors:
            if a.at is not None:
                a.at = max(0.0, min(1.0, a.at))
        for b in s.big:
            b.at = None if b.at is None else max(0.0, min(1.0, b.at))
            if b.spot not in SPOTS[s.set]:
                b.spot = "center"
        for f in s.fx:
            f.at = None if f.at is None else max(0.0, min(1.0, f.at))
            if f.spot and f.spot not in SPOTS[s.set]:
                f.spot = None
        # a thing that needs a man to handle it, without him: it falls or drives instead (and a man who stops,
        # catches or lifts nothing gets the thing he needs)
        acts = {a.action for a in s.actors}
        for b in s.big:
            need = {"caught": "catch", "lifted": "lift", "held": None, "thrown": "throw", "stop": "push-stop"}.get(b.motion, "")
            if need and need not in acts and not (b.motion == "thrown" and "lift" in acts):
                b.motion = {"caught": "fall", "lifted": "still", "thrown": "fall", "stop": "drive"}[b.motion]
                notes.append(f"Shot {i + 1}: the {b.kind} had nobody to handle it; it {b.motion}s instead.")
        for b in s.big:
            if b.motion == "hang" and b.at is None and "catch" in acts:
                b.at = 0.3  # the one who catches needs it to fall
        motions = {b.motion for b in s.big}
        for a in s.actors:
            if a.action == "push-stop" and "stop" not in motions:
                s.big.append(LPBig(kind="truck" if s.set == "highway" else "car", spot=a.spot, motion="stop", at=a.at or 0.4))
            if a.action == "catch" and not motions & {"caught", "hang"} and s.set == "construction":
                s.big.append(LPBig(kind="beam", spot=a.spot, motion="caught", at=a.at or 0.45))
            if a.action == "lift" and not motions & {"lifted", "held"} and s.set in ("highway", "street", "construction", "gym"):
                s.big.append(LPBig(kind="barbell" if s.set == "gym" else "car", spot=a.spot, motion="lifted", at=a.at or 0.35))
        if any(a.action == "carried" for a in s.actors) and not any(a.action == "carry" for a in s.actors):
            for a in s.actors:
                if a.action == "carried":
                    a.action = "lie"
        s.actors.sort(key=lambda a: a.action == "carried")  # the one carried after the one carrying him
        for a in s.actors:
            if a.who != "hero" and _key(a.who) not in names:
                a.who = "hero"
            if a.spot not in SPOTS[s.set]:
                a.spot = "bed" if a.action.startswith("lie") and "bed" in SPOTS[s.set] else "center"
            if a.action == "lie" and fiction and "bed" not in SPOTS[s.set]:
                a.action = "fall"  # knocked down outdoors, not lying in a bed that isn't there
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
        notes += [f"Shot {i + 1}: {n}" for n in _stage(story, s)]
    reds = [i for i, s in enumerate(story.shots) if s.red]
    for i in reds[:-1]:
        story.shots[i].red = False
    if not reds and story.shots:
        last = next((s for s in reversed(story.shots) if s.line.strip()), None)
        if last:
            last.red = True
    return notes


GESTURES = {"point", "help-up", "wave", "carry"}  # an action at another person: both must be in the picture
ONE_FACE = {"face", "face-top", "front", "detail", "top", "low", "crash-zoom"}  # cameras that show only the subject


def who_key(name: str) -> str:
    n = (name or "").strip()
    return "hero" if n.lower() in ("hero", "he", "him", "his") else _key(n) if n else ""


def _stage(story: Story, s: LPShot) -> list[str]:
    """Who looks at whom and who the camera is on, in code: a `look_at` or `subject` naming nobody in the shot is
    dropped; a line said to someone has the speaker and the listeners looking at each other; someone pointing with
    one other person there points at them; the camera is on the subject; and a gesture at someone else (pointing at
    his dad) is never a one-face camera, which left the dad out of the picture."""
    notes = []
    names = {"hero": "hero", **{_key(c.name): c.name for c in story.cast}}
    here: dict[str, LPActor] = {}
    for a in s.actors:
        here.setdefault(who_key(a.who), a)
    for a in s.actors:
        k = who_key(a.look_at)
        a.look_at = names.get(k, "") if k in here and k != who_key(a.who) else ""
    subject = who_key(s.subject)
    spk = "" if s.speaker == "narrator" else who_key(s.speaker)
    if subject not in here:
        subject = spk if spk in here else "hero" if "hero" in here else who_key(s.actors[0].who)
    s.subject = names.get(subject, "hero")
    if len(here) < 2:
        return notes
    if spk in here:  # a line said to someone: they look at each other
        other = subject if subject != spk else next(k for k in here if k != spk)
        if not here[spk].look_at:
            here[spk].look_at = names[other]
        for k, a in here.items():
            if k != spk and not a.look_at:
                a.look_at = names[spk]
    for a in s.actors:
        if a.action == "point" and not a.look_at and len(here) == 2 and not s.big:
            a.look_at = names[next(k for k in here if k != who_key(a.who))]
    lead = here[subject]
    if lead.action in GESTURES and lead.look_at and s.camera in ONE_FACE:
        notes.append(f"'{lead.action}' at {lead.look_at} with the '{s.camera}' camera showed only one of them: 'medium'")
        s.camera = "medium"
    return notes


def save(story: Story, path: Path) -> None:
    path.write_text(story.model_dump_json(indent=1), encoding="utf-8")


def load(path: Path) -> Story:
    return Story.model_validate_json(path.read_text(encoding="utf-8"))
