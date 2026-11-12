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
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, Field
from pydantic.json_schema import SkipJsonSchema

from ..config import Config
from ..llm import ask
from ..sfx import drop_removed

log = logging.getLogger(__name__)

SetName = Literal["bedroom", "hallway", "street", "park", "kitchen", "living", "office", "bathroom", "gym", "cafe", "busstop", "rooftop",
                  "construction", "highway", "bridge", "alley", "lab", "sky", "jungle", "plain", "cave", "void"]
LightName = Literal["night", "lamp", "dawn", "morning", "day", "evening", "dark"]
CamName = Literal["face", "face-top", "top", "medium", "wide", "side", "front", "back", "low", "detail", "aerial", "orbit", "crash-zoom",
                  "chase", "lead", "tracking", "pass-by", "heli", "drone", "cockpit", "bumper", "pedal", "wheel", "speedo"]
ActionName = Literal[
    "stand", "walk", "run", "sit", "sit-floor", "lie", "lie-side", "lie-phone", "phone", "type", "reach", "sit-up", "get-up", "shoes",
    "head-in-hands", "slump", "stretch", "sigh", "nod", "shake-head", "shrug", "think", "drink", "eat", "look-out", "wave", "point",
    "cheer", "jog", "pushup", "read", "cry",
    "lift", "catch", "push-stop", "throw", "super-jump", "land", "dash", "punch", "crush", "look-hands", "crouch", "kneel", "carry",
    "carried", "fall", "flee", "cower", "help-up", "talk", "gasp",
    "drive", "ride", "jump-off", "skydive", "brace"]
ExprName = Literal["neutral", "tired", "sad", "worried", "surprised", "happy", "determined", "annoyed", "asleep", "blank", "scared",
                   "angry", "amazed", "pained"]
SpotName = Literal["center", "left", "right", "bed", "chair", "desk", "door", "window", "couch", "mirror", "counter", "far"]
HoldName = Literal["none", "phone", "mug", "book", "laptop", "shoes", "bag", "keys", "fork"]
ThingName = Literal["phone", "alarm", "mug", "laptop", "book", "shoes", "plate", "bag", "plant", "bottle", "calendar", "note", "pizza"]
SoundName = Literal["alarm", "footsteps", "door", "knock", "notify", "buzz", "typing", "tap", "ding", "chime", "bell", "page", "rain",
                    "thud", "heartbeat", "tick", "coins", "cheer", "pop", "scribble", "swoosh", "send",
                    "impact", "crash", "glass", "crack", "creak", "skid", "siren", "wind", "fire", "sparks", "flyby", "crowd", "roar", "stomp", "flap"]
Mood = Literal["calm", "emotional", "uplifting", "curious", "mystery", "dark", "suspense", "energetic"]
BigName = Literal["car", "bus", "truck", "beam", "crate", "boulder", "barbell", "pipe", "door", "ball", "made"]
MotionName = Literal["still", "fall", "caught", "lifted", "held", "thrown", "stop", "drive", "crushed", "hang", "shake",
                     "race", "drift", "spin", "reverse", "jump", "fly", "climb", "dive", "bank", "roll",
                     "walk", "charge", "roar", "hatch"]
GROUND_UNDERWAY = {"race", "drift", "spin", "reverse", "jump"}  # = UNDERWAY in Big.tsx, on the ground...
OVERGROWN_SETS = {"street", "highway", "busstop", "rooftop", "bridge", "alley"}  # = OVERGROWN in Sets.tsx
CREATURE_MOTIONS = {"walk", "charge", "roar", "hatch"}  # what an animal or creature design does (= Big.tsx)
MOVES = Literal["", "head", "neck", "jaw", "tail", "leg_l", "leg_r", "leg_fl", "leg_fr", "leg_bl", "leg_br", "arm_l", "arm_r",
                "wing_l", "wing_r", "shell_top"]
AIR_MOTIONS = {"fly", "climb", "dive", "bank", "roll"}  # ...and in the air
VEHICLES = {"car", "bus", "truck"}  # built in; a design ('made') that travels is one too
FxName = Literal["shockwave", "crack", "dust", "speed", "sparks", "debris", "glass", "smoke", "fire", "shake", "flash", "alarm", "rain", "wind", "meteor"]
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
    "bridge": {"center", "left", "right", "far", "door"},
    "alley": {"center", "left", "right", "far", "door", "chair"},
    "lab": {"center", "left", "right", "desk", "chair", "counter", "far", "door"},
    "sky": {"center", "left", "right", "far"},
    "jungle": {"center", "left", "right", "far"},
    "plain": {"center", "left", "right", "far"},
    "cave": {"center", "left", "right", "far"},
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
# his own colours, from the concept still the user picked (brick-red sweater, dark brown trousers, chestnut hair, beige
# shoes); not the shared COLOURS, so nobody else's "red" changes with him
HERO = {"skin": SKIN["light"], "hair": "#704632", "hairStyle": "curly", "glasses": True, "top": "#9e3529", "topKind": "sweater",
        "trousers": "#3f2d24", "shoes": "#d6cdbd"}


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


class LPMessage(BaseModel):
    me: bool = Field(False, description="true = sent by the person holding the phone (right, blue); false = received")
    text: str = Field(description="the message as typed, short and real-sounding ('Where are you??', 'Dinner's cold')")


# What a held phone shows (the user: "on this video there [is a] family message 'where are you', but [the] phone [is]
# showing just blank, must use what need to show on phone"); drawn on the screen by Man.tsx `phoneScreen`.
SCREEN_KINDS = ["chat", "call", "notification", "alarm", "lock", "feed", "map"]


class LPScreen(BaseModel):
    kind: Literal["chat", "call", "notification", "alarm", "lock", "feed", "map"] = Field(
        description="chat = a conversation; call = an incoming call; notification = the lock screen with a message on it; "
                    "alarm = an alarm ringing; lock = the lock screen only; feed = scrolling posts; map = directions")
    name: str = Field("", description="who: the contact's name as it would be saved ('Mom', 'Dad', 'Mia', 'Boss'); for "
                                      "feed and map what it is ('Home', 'City Hospital'); never a brand or real app name")
    messages: list[LPMessage] = Field(default_factory=list, description="chat: 1-6 messages in order, the last arriving "
                                      "during the shot; notification: the one message; feed: 1-3 post captions")
    time: str = Field("", description="the phone's clock ('11:47') or the alarm's time; empty = the shot's stamp")


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
    screen: LPScreen | None = Field(None, description="with a phone in hand ('phone', 'lie-phone', or hold 'phone'): what "
                                    "its screen shows, from the story (the message the line is about, who is calling); none "
                                    "when it doesn't matter")
    on: int = Field(0, description="0 = on the ground; n = in or on this shot's n-th big thing (1 = the first in `big`): "
                                   "'drive' at its wheel or controls, 'ride' in a passenger seat, any other action standing "
                                   "on it (a car's roof, a plane's wing: 'brace', 'punch', 'jump-off'...); they go with it")


class LPThing(BaseModel):
    kind: ThingName
    label: str = Field("", description="the alarm clock's time ('5:30'), a note's or calendar's word; empty otherwise")
    glow: bool = Field(False, description="a lit screen")


class LPSound(BaseModel):
    sound: SoundName
    word: str = Field("", description="a word of this shot's line it lands on; empty = the start of the shot")


# older stories may still name a sound the user removed (sfx.REMOVED_SOUNDS): it is dropped when read
Sounds = Annotated[list[LPSound], BeforeValidator(drop_removed)]


class LPBig(BaseModel):
    kind: BigName = Field(description="one of the editor's own, or 'made' = one of this film's own designs (`made`)")
    spot: SpotName = "center"
    motion: MotionName = Field(description="still; fall (drops from high onto its spot); caught (drops into the hands of the one who "
                                           "'catch'es); hang (swings from the crane's cable; with `at` the cable snaps then and it "
                                           "falls into the hands of the one who 'catch'es); lifted (raised overhead by the one who "
                                           "'lift's); held (already overhead, or carried); thrown (flung from overhead by the one who "
                                           "'throw's); stop (drives at the one who 'push-stop's and stops against his hands); drive "
                                           "(drives across; with someone at the wheel it is under way like 'race'); crushed; shake. "
                                           "Under way (anyone on it goes with it, the camera can follow it): race, drift, spin, "
                                           "reverse, jump, and 'stop' (brakes to a stop at `at`) with a driver; in the air: fly, "
                                           "climb, dive, bank, roll")
    at: float | None = Field(None, description="when its moment happens, a fraction 0-1 of the shot")
    color: Literal["", "red", "navy", "green", "mustard", "grey", "white", "black", "teal", "blue", "orange", "maroon"] = ""
    made: str = Field("", description="kind 'made': the name of the film's design it is, exactly")


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
    actors: list[LPActor] = Field(description="who is in the shot and what they do (the hero in nearly every shot; empty for "
                                              "a shot of only a vehicle under way, which the camera follows)")
    things: list[LPThing] = Field(default_factory=list, description="objects put down in the place (on the bedside table, the "
                                                                     "desk, the kitchen table)")
    sounds: Sounds = Field(default_factory=list)
    pause: float = Field(0.0, description="extra seconds of silence after the line, for a beat to land or an action to play out "
                                          "(0-2; fiction up to 4)")
    red: bool = Field(False, description="the last line's punch, shown in red; only on the final line")
    big: list[LPBig] = Field(default_factory=list, description="big objects in the shot and what they do (fiction)")
    fx: list[LPFx] = Field(default_factory=list, description="effects (fiction): most come with the actions by themselves")
    slowmo: bool = Field(False, description="the action in slow motion (the key rescue moment, a catch); give it a longer pause")
    overgrown: Literal["", "ruined", "growing"] = Field(
        "", description="the city taken back by nature: 'ruined' = abandoned and overgrown (vines down the buildings and over "
                        "rusted cars, dark windows, grass, ferns and jungle trees breaking through the road); 'growing' = it "
                        "happens during the shot (the modern place turning into jungle as we watch); '' = as it is")


class LPPart(BaseModel):
    shape: Literal["box", "cylinder", "cone", "sphere", "wedge"] = Field(
        description="box; cylinder and cone along their own y (turn [90,0,0] to lie along z); sphere (squashed by size); "
                    "wedge = a box narrowing to its front (+z): noses, tails, fins")
    at: list[float] = Field(description="[x, y, z] its centre in metres: x right, y up from the ground, z forward")
    size: list[float] = Field(description="box, sphere, wedge: [width, height, length]; cylinder: [diameter, length, end "
                                          "diameter]; cone: [base diameter, length, 0]")
    turn: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0], description="degrees about x, y, z")
    color: str = Field(description="#rrggbb, flat and muted like the sets (#c1121f red, #e9e6df white, #22252a near-black...)")
    glow: bool = Field(False, description="lights, jet exhausts, screens")
    glass: bool = Field(False, description="see-through: a canopy, a windscreen")
    spin: Literal["", "x", "y", "z"] = Field("", description="turns fast about this axis while it moves: a propeller (z), "
                                                             "a rotor (y), a wheel (x)")
    move: MOVES = Field("", description="an animal or creature's moving part (every part of that body part gets the same "
                                        "role, and moves together): head (with its eyes, horns, upper teeth), neck, jaw (the "
                                        "lower jaw: it opens to roar), tail, legs (a two-legged creature: leg_l, leg_r; four "
                                        "legs: leg_fl, leg_fr, leg_bl, leg_br; each leg's parts hang from its top), arm_l, "
                                        "arm_r, wing_l, wing_r (they flap), shell_top (an egg's top half, which bursts off "
                                        "when it hatches); '' for the body and anything rigid")


class LPMade(BaseModel):
    name: str = Field(description="what the shots call it in big.made: 'the jet', 'Victor's plane', 'the motorbike'")
    what: str = Field(description="one line: what it is")
    travel: Literal["ground", "air", "water", "legs", "none"] = Field(
        description="how it moves when it goes: a vehicle on the ground, anything flying (a plane, or a creature with "
                    "wings), on water, 'legs' = an animal or creature that walks on its legs, or not at all (a big object, "
                    "an egg)")
    parts: list[LPPart] = Field(description="8-40 parts, front toward +z, its bottom at y = 0, centred")
    seats: list[list[float]] = Field(default_factory=list, description="[x, seat height, z] where people sit, the driver's or "
                                                                        "pilot's first; on top of or inside the body so head "
                                                                        "and shoulders show")
    top: float = Field(0.0, description="the height of the surface someone stands on (a wing's top, a roof)")


class ScorePart(BaseModel):
    from_shot: int = Field(description="the shot (1 = first) where this part of the score starts")
    mood: Mood
    energy: Literal["low", "medium", "high"]


class IntroCard(BaseModel):
    """🎭 Cast intro: one person's segment (their shots in a row) and the movie-style card shown over it."""
    who: str  # 'hero' or the person's name
    name: str  # as shown
    role: str  # as shown, small under the name
    first: int  # the segment's first shot (0-based)
    shots: int  # how many shots in a row
    seconds: float  # each of those shots' length
    freeze: float = 0.0  # seconds into the segment's last shot where the picture freezes and the name slams in (on a beat)
    bpm: float = 0.0  # the beat the cuts and freezes land on (the score is composed at it)


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
    made: list[LPMade] = Field(default_factory=list, description="vehicles and big things the film needs that the editor "
                                                                "hasn't got (a plane, a jet, a helicopter, a motorbike, a "
                                                                "boat), designed from parts; empty for most films")
    kind: Literal["life", "fiction"] = "life"
    hero: bool = Field(True, description="the channel's man is in this film; false when the brief has no people in it (a "
                                         "film about animals, creatures or a place) or none who could be him")
    poster: SkipJsonSchema[dict] = {}  # 🎭 the cast intro's closing poster: title, tagline, the face over the city
    intro: SkipJsonSchema[list[IntroCard]] = []  # 🎭 a cast intro's segments (intro.py), never asked of the writer


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
- Driving: 'drive' with `on` 1 and a 'car' in `big` (motion 'drive') on the 'street' or 'highway': he is at the wheel \
inside it; film it with 'cockpit' (his face through the windscreen), 'back' (his view down the road), 'tracking' or \
'pass-by'. A passenger: 'ride' with the same `on`.
- Things: 'alarm' with its time as `label` on the bedside table, a 'phone' with `glow`, a 'mug', a 'laptop'; held \
things go in `hold` (a phone in his hand, a mug).
- The phone's screen: whenever someone holds a phone and the story is about what's on it, give that actor a `screen` \
that shows exactly that, so the viewer can read it: a family chat 'Mom' with 'Where are you?' and 'Dinner's ready', \
a missed 'call' from 'Dad', a 'notification' from 'Boss', the 'alarm' at '5:30', directions on a 'map'. Messages are \
short and real-sounding, the person's own replies `me` true; a message the line reacts to comes last (it arrives \
during the shot, with a 'notify' sound). Film it with 'detail' (his view of the screen) when the words matter. Never a \
brand, a real app or a real person's name on a screen.
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

# The user's film 'Born to Fly' (a driver nobody can catch) had car shots with nobody in them and the hero stood on the
# road: the writer had no words for a man at the wheel. And the user: "this cars movement, angle movement must be
# hollywood style", "may be i ask more in future like jumping from flying plane, flying the actual plane, fighting with
# enemies on aircraft ... claude can understand this char or object needed so it build at run time if needed".
VEHICLE_RULES = """
VEHICLES AND STUNTS (shoot them like a Hollywood car chase or an air-to-air sequence):
- People in and on vehicles: an actor with `on` = n is in or on this shot's n-th big thing. 'drive' = at the wheel or \
the controls (the first seat), 'ride' = a passenger seat, any other action = standing on it ('brace' to keep balance \
on a car's roof or a plane's wing while it moves, 'punch' or 'talk' up there, 'jump-off' = he leaps off it at `at`). \
Cars are low luxury sports cars; with someone in them the roof is off, so the driver is seen at the wheel. Whoever the \
story says is driving is IN the car every time we see it move: never a man standing on the road while his car drives \
past him, and never a parked car while the line says he is racing.
- Vehicle motions under way (it travels the whole shot and anyone on it goes with it): 'race' (flat out, \
accelerating), 'drift' (at `at` the tail slides out, tyres smoking, and it slides through), 'spin' (a full spin at \
`at`), 'jump' (leaves the ground at `at` and lands about a second later; on 'rooftop' it jumps the gap to the next \
roof, on 'bridge' it flies the collapsed span of a broken highway bridge: a jump over a broken road is always on \
'bridge', and the chase before it on 'bridge' too), 'reverse', 'stop' with a driver (brakes hard to a stop at `at`); in the air: 'fly', 'climb', 'dive', 'bank' \
(a turn, leaning into it), 'roll' (a barrel roll at `at`). 'drive' with a driver is under way too. A car goes along \
the road: 'highway' (a long open road), 'street' (past the city), 'rooftop' (along the roofs); a plane through 'sky' \
(high over a sea of clouds; on 'highway' a plane with 'fly' and `at` runs along the road and takes off at `at`). Two \
vehicles under way in one shot (a chase): the second follows behind the first in the next lane.
- A shot of only a vehicle (no actors) is fine: the camera follows it. A shot of someone falling free: 'skydive' in \
'sky' (face down, arms out, the camera falling with him); after a 'jump-off' from a plane he is already falling.
- Vehicle cameras: 'chase' (from a camera car behind it), 'lead' (ahead of it, low, looking back as it gains), \
'tracking' (beside it at its speed), 'pass-by' (from the roadside as it whooshes past, a long lens panning), 'heli' \
(a helicopter shot from high behind and to the side), 'drone' (straight down), 'cockpit' (on the dashboard, on the \
driver's or pilot's face, the world rushing away behind him), 'bumper' (low at its front corner along its flank; on a \
plane the wing tip), 'orbit' (circling it as it goes). On someone in a vehicle, 'face' and 'medium' are close on him \
at the wheel and 'back' is his point of view over his shoulder down the road. Cut it like a film: establish with \
'heli' or 'pass-by', then 'chase', 'cockpit' on his face, 'bumper' or 'tracking' as it drifts or jumps, 'lead' as it \
comes at us, a 'pass-by' whoosh; short shots (1.5-3 s), never the same camera twice running, `slowmo` on the jump or \
the leap.
- Cut-ins come by themselves: in a shot where he drives a car that races off, jumps, brakes ('stop'), drifts or spins, \
the editor cuts for a split second to his foot slamming the accelerator or the brake, or to his hands yanking the \
wheel, then back to your camera on what the car does. So give those shots a camera that shows the car (chase, \
tracking, bumper, pass-by, lead, heli), not his face. A race also cuts to the speedometer, its needle climbing. \
'pedal' (his foot on the pedal), 'wheel' (his hands on the wheel) and 'speedo' (the speedometer) as a whole shot \
only for one short tense beat (1-1.5 s), at most one such shot in a film's every 15 shots.

THINGS THE EDITOR HASN'T GOT: when the brief needs a vehicle or a big object that isn't in the list (a plane, a jet, \
an enemy's plane, a helicopter, a motorbike, a boat, a spaceship, a tank, a drone), design it in `made` and use it in \
shots as a big thing of kind 'made' with `made` = its name. Build it from 8-40 low-poly parts, front toward +z, its \
bottom at y = 0, centred on x = 0, to the man's scale (he is about 2 m to the top of his hair, his shoulders at 1.24 \
m; a car is 1.7 wide, 0.95 high, 3.9 long; a small plane about 9 m long with 10 m wings; a motorbike 0.7 wide, 1.1 \
high, 2.1 long). A plane: a cylinder body turned [90,0,0], a cone nose turned [90,0,0], box wings, a box fin and \
tailplane, a propeller (a thin box, 'spin' 'z') or glowing exhausts, a glass canopy (a sphere) over the seat, wheels. \
`seats`: where the pilot or rider sits ([x, seat height, z], the seat's top; his hips just above it), the driver's \
first, IN the body and never on top of it: the seat's top about 0.35 m below the top of the body around it, and in \
anything that flies a closed cockpit with a ceiling, a glass canopy over his head and shoulders (a sphere about 1.0 \
wide, 0.95 high, 1.8 long, its centre 0.8 m over the seat; the editor adds one if you leave it out). A motorbike or a \
jet ski has no canopy. `top`: the height someone stands on (a wing's top). \
Two designs that meet (his plane and the enemy's) look clearly different (colours, shape). Design only what the film \
needs, once, and use the same design in every shot it is in.
"""


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
- No killing, no blood, no one hurt on screen; he never punches a person (only a wall, a boulder, the ground) unless \
the brief has a fight, and then it plays like a family action film (a shove, a punch that knocks someone off balance, \
nobody shown hurt); danger is about saving people. No capes, costumes, logos or names from existing superhero films; no real brands or people.

THE EDITOR'S VOCABULARY (use only these):
- Places and their spots: {spots}. 'construction' = a building site with a steel frame, a tower crane, barriers, a site \
office (door) and crates (chair); 'highway' = a wide road along the frame, guard rails, the city beyond ('center' and \
the near lane 'left'/'right' are on the road, 'door' is the roadside); 'bridge' = the same kind of road raised high \
over a river on concrete piers, its middle span collapsed into the river: jagged edges, rebar, a slab hanging into \
the gap, rubble and cones before it (the spots are on the road short of the gap; a car 'jump' there leaps it, a \
'stop' brakes at its edge); 'alley' = a narrow brick alley (night is best), \
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
and `at`. Cars, buses and trucks drive and stand on the road ('street' and 'busstop' have one in front of the \
pavement, on 'highway' the spots are the road); people wait on the pavement, out of their way; the man who stops one \
with his hands steps onto the road, filmed from the 'side' or 'wide'. Effects ('fx'): shockwave, crack, dust, speed, sparks, debris, glass, smoke, fire, shake, flash, alarm (red \
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
""" + VEHICLE_RULES + "{creatures}" + STAGING + """
LENGTH: {length}."""

FICTION_SHORT = ("a 9:16 Short of {seconds} seconds: {shots} shots of 1.5-4 s, about {words} words in all (dialogue and a "
                 "little narration); hook in the first 2 seconds, the turn in the middle, the question at the end")
FICTION_FILM = ("a 16:9 film of {minutes} minutes: {shots} shots of 2-5 s, about {words} words in all, most shots short and "
                "full of action, a few quiet ones that let a feeling land")

# The user's script 'WHAT IF DINOSAURS NEVER WENT EXTINCT?' (reel_8_1): every shot showed the man (the dinosaurs the
# writer named as actors were turned into him, and an empty shot got him), a T-Rex and an asteroid became him on a
# bench and a pebble: "why script not matched on video, why humans??". Animals and creatures are now designs with
# moving parts, and a film can be without him.
CREATURES = """
ANIMALS AND CREATURES (dinosaurs, a dragon, a whale, a wolf, a giant insect, a robot that walks): the editor has none built in. Design each one the film needs in `made` (travel 'legs' for anything that walks, 'air' for anything that flies, 'water' for anything that swims, 'none' for an egg or a fossil) from 10-40 parts, front toward +z, its bottom at y = 0, and give every moving body part its `move` role so the editor can animate it: the head (with its eyes, teeth and horns, all 'head'), the lower 'jaw' (it opens when it roars), the 'neck', the 'tail', the legs ('leg_l'/'leg_r' for two legs, 'leg_fl'/'leg_fr'/'leg_bl'/'leg_br' for four; each leg a long part hanging from its hip, its foot at y = 0), 'arm_l'/'arm_r', 'wing_l'/'wing_r'; an egg's top half is 'shell_top'. Real sizes against the man (2 m): a T-Rex about 12 m long and 4.5 m high, a Brachiosaurus about 22 m long with its head 12 m up on a long neck, a Triceratops about 8 m long and 3 m high with three horns and a frill, a Velociraptor about 2 m long and 0.8 m high, a Pterosaur with 8 m wings; colours of real animals (muted greens, browns, greys, sand). No seats. An egg is ONE egg shape, never two balls stacked: its body a sphere about [1.0, 1.3, 1.0] centred at y 0.65, and its 'shell_top' a slightly smaller sphere [0.96, 0.75, 0.96] centred at y 0.95 inside the top of it (in the same colour); a few darker speckles are fine, no sticks.
- In shots it is a big thing of kind 'made' with `made` = its name and a motion: 'still' (it breathes, its tail and head move), 'walk' (it walks across the place, legs striding), 'charge' (runs flat out), 'roar' (head up, jaw wide at `at`, the ground shakes), 'hatch' (an egg: it shakes, cracks and its top bursts off at `at`; a creature in the same spot with 'hatch' rises out of the shell after it), 'fly' / 'climb' / 'dive' / 'bank' for anything with wings, 'fall'. A herd: the same design three or four times in one shot on different spots ('left', 'center', 'right', 'far').
- A shot of only animals or creatures (no actors) is right: the camera is on the first big thing in the shot, and 'face' is close on its head, 'medium' all of it, 'wide' the place with it, 'low' up at it from the ground, 'side', 'front', 'back', 'aerial' from above, 'orbit' around it, 'detail' on its eye, 'crash-zoom' pushing in on its face.
- Places for them: 'jungle' (a dense prehistoric jungle: giant ferns, palms, a smoking volcano far away), 'plain' (an open grassland to the mountains, for a herd), 'cave' (deep underground, dark rock, a shaft of light, glowing crystals), and the man's places too: 'street' and 'highway' with the city, 'park'.
- 'meteor' in `fx`: a burning asteroid streaking across the sky (outdoors).
- A city taken back by nature: `overgrown` 'ruined' on a 'street', 'highway', 'busstop', 'rooftop', 'bridge' or 'alley' \
shot (abandoned: vines down the buildings and over rusted cars, dark windows, grass, ferns and jungle trees through \
the road); 'growing' when the script has the city turning into jungle (it grows over the shot as we watch, from the \
modern city to the jungle). Every shot after the change stays 'ruined'.
"""

SCRIPT_RULES = """

THE USER'S OWN SCRIPT: the brief is the user's finished script, section by section (a visual and the narrator's words). It is the film: stage it exactly, in order, and invent nothing it doesn't ask for.
- The spoken lines are given below, numbered: put them in shots IN THIS ORDER, WORD FOR WORD (never a word changed, added, dropped or moved to another speaker), one numbered line per shot. Every shot with a line has `speaker` 'narrator' unless the script says who speaks.
- Each section's VISUAL is what its shots show: split it into the shots it describes (one per sentence of the visual is a good guide) and give the visual's extra moments silent shots ('' line) with a `pause` of 1-2.5 s. What the visual names is on screen: its creatures, vehicles, objects, places and effects. A visual that names no person has no person in it: no actors at all, and the man only if the script is about him. If no section names a person, set `hero` false.
- Words the script puts on screen ('TEXT: ...') go in `stamp` of a silent shot at that place (they are shown, never spoken); 'CUT TO BLACK' is a silent shot in 'dark' light with nothing in it but that text.
- The title, description and tags come from the script's own title and subject.
"""

SCRIPT_LINE_WORDS = 12  # = LPShot.line's limit


def _say(text: str) -> str:
    text = re.sub(r"\*\*|__|\*|_", "", text)
    return re.sub(r"\s+", " ", text.strip().strip('"“”').strip())


def _line_pieces(text: str, most: int = SCRIPT_LINE_WORDS) -> list[str]:
    """The narrator's words cut into shot lines of at most `most` words, at sentence ends, then at '...' / ',' / '—',
    never changing a word."""
    out = []
    for sent in re.findall(r"[^.!?…]+(?:\.\.\.|[.!?…]+)?[\"”]?\s*", text):
        sent = sent.strip()
        if not sent:
            continue
        words = sent.split()
        while len(words) > most:
            # the last break (a comma, an ellipsis, a dash) within the limit, else the limit itself
            cut = max((i + 1 for i, w in enumerate(words[:most]) if re.search(r"(,|\.\.\.|…|—|-|;|:)$", w) and i >= 2), default=most)
            out.append(" ".join(words[:cut]))
            words = words[cut:]
        if words:
            out.append(" ".join(words))
    return out


SECTION = re.compile(r"^\s*(?:#{1,6}\s*)?(?:\*\*)?\s*(\d+\s*[–-]\s*\d+\s*(?:sec|s|seconds)\b[^\n]*|scene\s*\d+[^\n]*|shot\s*\d+[^\n]*)$", re.I | re.M)
LABEL = re.compile(r"^\s*(?:\*\*)?\s*(visual|narrator|voice[- ]?over|vo|text|on[- ]screen(?: text)?)\b[^:\n]*:?\s*(?:\*\*)?\s*:?\s*(.*)$", re.I)


def parse_script(brief: str) -> list[dict] | None:
    """A shot-by-shot script (sections with 'Visual:' and 'Narrator:' parts, like the user's dinosaur script), as
    sections {head, visual, lines, text}; None for an ordinary brief."""
    if len(re.findall(r"^\s*(?:\*\*)?\s*(?:narrator|voice[- ]?over|vo)\b", brief or "", re.I | re.M)) < 2:
        return None
    sections, cur, part = [], None, None
    for raw in (brief or "").splitlines():
        line = raw.strip()
        if not line or re.fullmatch(r"[-*_=]{3,}", line):
            part = None if not line else part
            continue
        if SECTION.match(line):
            cur = {"head": _say(line.lstrip("#")), "visual": [], "say": [], "text": []}
            sections.append(cur)
            part = None
            continue
        if cur is None:
            if line.startswith("#"):
                continue  # the script's title
            cur = {"head": "", "visual": [], "say": [], "text": []}
            sections.append(cur)
        m = LABEL.match(line)
        if m:
            kind = m.group(1).lower()
            part = "visual" if kind == "visual" else "text" if kind.startswith(("text", "on")) else "say"
            rest = _say(m.group(2))
            if rest:
                cur[part].append(rest)
            continue
        bare = _say(line)
        if re.fullmatch(r"cut to black\.?", bare, re.I):
            cur["text"].append("CUT TO BLACK")
            continue
        if bare:
            cur[part or "visual"].append(bare)
    out = []
    for c in sections:
        said = " ".join(c["say"])
        out.append({"head": c["head"], "visual": " ".join(c["visual"]), "lines": _line_pieces(said) if said else [],
                    "text": [t for t in c["text"] if t.upper() != "CUT TO BLACK"], "black": "CUT TO BLACK" in c["text"]})
    out = [c for c in out if c["visual"] or c["lines"] or c["text"]]
    return out if sum(len(c["lines"]) for c in out) >= 2 else None


def script_block(sections: list[dict]) -> str:
    """The script as the writer is given it: each section's visual and its numbered lines."""
    rows, n = [], 0
    for i, c in enumerate(sections, 1):
        rows.append(f"SECTION {i}{' (' + c['head'] + ')' if c['head'] else ''}")
        if c["visual"]:
            rows.append(f"  VISUAL: {c['visual']}")
        for ln in c["lines"]:
            n += 1
            rows.append(f"  LINE {n}: {ln}")
        for t in c["text"]:
            rows.append(f"  ON SCREEN (a stamp, not spoken): {t}")
        if c["black"]:
            rows.append("  CUT TO BLACK")
    return "\n".join(rows)


def script_lines(sections: list[dict]) -> list[str]:
    return [ln for c in sections for ln in c["lines"]]


def _words(s: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", s.lower().replace("’", "'"))


def keep_script_lines(story: Story, lines: list[str]) -> list[str]:
    """The script's words exactly as written, whatever the writer did with them: the shots' spoken lines in order are
    set to the script's lines (a shot left over goes silent, a line left over gets a silent shot's place, else a new
    shot after the last). Returns notes."""
    notes = []
    spoken = [s for s in story.shots if s.line.strip()]
    if [_words(s.line) for s in spoken] == [_words(x) for x in lines]:
        for s, x in zip(spoken, lines):
            s.line = x
        return notes
    notes.append("the narration was put back word for word as the script has it")
    k = 0
    for s in story.shots:
        if not s.line.strip():
            continue
        if k < len(lines):
            s.line = lines[k]
            k += 1
        else:
            s.line = ""
            s.speaker = "narrator"
    for x in lines[k:]:
        last = story.shots[-1] if story.shots else None
        story.shots.append(LPShot(line=x, set=last.set if last else "void", light=last.light if last else "day",
                                  camera=last.camera if last else "wide", actors=[], big=list(last.big) if last else []))
    return notes


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


def lock_cast(cfg: Config, story: Story, keep: bool = True) -> None:
    """Someone met before (or from the library) keeps the look and voice they had; someone new is saved for the next
    films (`keep`; a storyboard draft the user may still reject only borrows the saved looks)."""
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
    if changed and keep:
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
    made: list[LPMade] = Field(default_factory=list, description="vehicles and big things the whole film needs that the "
                                                                "editor hasn't got, designed from parts (see THINGS THE "
                                                                "EDITOR HASN'T GOT); empty for most films")
    acts: list[ActPlan] = Field(description="the film's acts in order, their minutes adding up to its length")


class ActShots(BaseModel):
    shots: list[LPShot]


def _act_len(fiction: bool, minutes: float) -> tuple[int, int]:
    """Shots and words for this many minutes."""
    return (round(minutes * 60 / (3.0 if fiction else 3.3)), int(minutes * 60 * (1.3 if fiction else 1.8)))


def _outline_system(fiction: bool, minutes: float) -> str:
    spots = "; ".join(f"{k}: {', '.join(sorted(v))}" for k, v in SPOTS.items())
    n_acts = max(4, min(9, round(minutes / 1.7)))
    shots, words = _act_len(fiction, minutes)
    whole = (FICTION_FILM if fiction else FILM).format(minutes=f"{minutes:g}", shots=f"{shots - 10}-{shots + 10}", words=words)
    return (FICTION if fiction else RULES).format(spots=spots, length=whole) + f"""

THIS FILM IS LONG ({minutes:g} minutes), so plan it first: {n_acts} acts (give or take one) whose minutes add up to
{minutes:g}. A long film needs more than a long version of a short one: a fuller world (more places, two to six people
with their own wants), a middle that turns more than once, set-ups paid off later, quiet scenes between the big ones,
and the ending's line in red. Write the outline only; the shots come next, act by act."""


# ✏ Change it (boards.py): the user liked a storyboard but wants some things changed
REVISE = """

THE USER HAS READ THIS STORYBOARD AND WANTS CHANGES. You get the storyboard as it is and the user's instructions.
Make exactly what the instructions ask, everywhere it applies (a renamed person renamed in every shot, a moved scene
with its lines and sounds, a new beat with the shots it needs), and keep everything else as it was: the same story,
shots, words, places, cameras and people wherever the instructions don't touch them. The rules above still hold (the
editor's vocabulary, the length, the staging). Return the whole storyboard, changed."""


def revise(cfg: Config, story: Story, instruction: str, *, short: bool, seconds: int, minutes: float) -> Story:
    """The same storyboard with the user's changes (one call, no web); everything they didn't ask about kept."""
    fiction = story.kind == "fiction"
    system = _system(fiction, short, seconds, minutes) + ("" if fiction else CREATURES) + REVISE
    prompt = (f"THE STORYBOARD AS IT IS:\n{story.model_dump_json(indent=1)}\n\nTHE USER'S CHANGES:\n{instruction.strip()}"
              f"{_known(cfg)}")
    out = ask(cfg.ai_backend, cfg.claude_model, system, prompt, Story, allow_web=False, effort=cfg.claude_effort, timeout=2400)
    out.kind = story.kind
    if short and "#shorts" not in [h.lower() for h in out.hashtags]:
        out.hashtags = out.hashtags[:2] + ["#shorts"]
    return out


def revise_outline(cfg: Config, outline: Outline, instruction: str, *, minutes: float, fiction: bool) -> Outline:
    """A long film's outline with the user's changes; the acts are written from it once approved."""
    prompt = (f"THE OUTLINE AS IT IS:\n{outline.model_dump_json(indent=1)}\n\nTHE USER'S CHANGES:\n{instruction.strip()}"
              f"{_known(cfg)}")
    return ask(cfg.ai_backend, cfg.claude_model, _outline_system(fiction, minutes) + REVISE.replace("STORYBOARD", "OUTLINE"),
               prompt, Outline, allow_web=False, effort=cfg.claude_effort, timeout=2400)


def plan_outline(cfg: Config, ask_for: str, made: str, *, minutes: float, fiction: bool, progress=log.info) -> Outline:
    """A long film's plan: title, cast and acts with their minutes, places and moods (the first step of `write_long`, and
    on its own the storyboard draft of a long film the user reads before it is written act by act)."""
    spots = "; ".join(f"{k}: {', '.join(sorted(v))}" for k, v in SPOTS.items())
    n_acts = max(4, min(9, round(minutes / 1.7)))
    shots, words = _act_len(fiction, minutes)
    whole = (FICTION_FILM if fiction else FILM).format(minutes=f"{minutes:g}", shots=f"{shots - 10}-{shots + 10}", words=words)
    plan_system = (FICTION if fiction else RULES).format(spots=spots, length=whole) + f"""

THIS FILM IS LONG ({minutes:g} minutes), so plan it first: {n_acts} acts (give or take one) whose minutes add up to
{minutes:g}. A long film needs more than a long version of a short one: a fuller world (more places, two to six people
with their own wants), a middle that turns more than once, set-ups paid off later, quiet scenes between the big ones,
and the ending's line in red. Write the outline only; the shots come next, act by act."""
    progress(f"Planning the {minutes:g}-minute film in acts")
    return ask(cfg.ai_backend, cfg.claude_model, plan_system, f"{ask_for}\n\nAlready made (never the same story or title "
               f"again):\n{made}{_known(cfg)}", Outline, allow_web=False, effort=cfg.claude_effort, timeout=2400)


def write_long(cfg: Config, ask_for: str, made: str, *, minutes: float, fiction: bool, progress=log.info,
               save_to: Path | None = None) -> Story:
    """A 6-15 minute film: one call plans it (title, cast, acts with their minutes, places, moods), then one call per act
    writes that act's shots knowing the whole plan and how the act before it ended. Each finished part is kept in
    `save_to`, so a stopped or failed run carries on from the next act; an approved storyboard draft (boards.py) puts
    its outline and take there first, so only the acts are written."""
    spots = "; ".join(f"{k}: {', '.join(sorted(v))}" for k, v in SPOTS.items())
    saved = json.loads(save_to.read_text(encoding="utf-8")) if save_to and save_to.exists() else {}
    if "outline" in saved:
        outline = Outline.model_validate(saved["outline"])
    else:
        outline = plan_outline(cfg, ask_for, made, minutes=minutes, fiction=fiction, progress=progress)
        saved = {"outline": outline.model_dump(), "acts": []}
        if save_to:
            save_to.write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")
    if saved.get("take") and TAKE_MARK not in ask_for:
        ask_for += TAKE.format(take=saved["take"])
    acts: list[list[LPShot]] = [[LPShot.model_validate(x) for x in a] for a in saved.get("acts", [])]
    plan = "\n".join(f"Act {i + 1} ({a.minutes:g} min, {a.name}): {a.summary} Ends with: {a.ends_with}" for i, a in enumerate(outline.acts))
    cast = "\n".join(f"- {c.name}: {c.who} ({c.voice} voice)" for c in outline.cast) or "- nobody else"
    if outline.made:
        cast += "\n\nThe film's own designs (a big thing of kind 'made' with `made` = the name exactly):\n" + "\n".join(
            f"- {m.name}: {m.what} ({m.travel}, {len(m.seats)} seat{'s' if len(m.seats) != 1 else ''})" for m in outline.made)
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


TAKE_MARK = "THIS VERSION'S TAKE"
TAKE = ("\n\n" + TAKE_MARK + " (one of several storyboards written from the same prompt for the user to choose from; tell "
        "it this way, and the prompt still holds):\n{take}")


def _system(fiction: bool, short: bool, seconds: int, minutes: float, script: bool = False) -> str:
    if script:  # the user's own script: their words and visuals, whatever the kind of film
        return _system(fiction, short, seconds, minutes) + ("" if fiction else CREATURES) + SCRIPT_RULES
    spots = "; ".join(f"{k}: {', '.join(sorted(v))}" for k, v in SPOTS.items())
    if fiction:
        if short:
            length = FICTION_SHORT.format(seconds=seconds, shots=max(9, round(seconds / 2.6)), words=int(seconds * 1.3))
        else:
            shots = round(minutes * 60 / 3.0)
            length = FICTION_FILM.format(minutes=f"{minutes:g}", shots=f"{shots - 8}-{shots + 8}", words=int(minutes * 60 * 1.3))
        return FICTION.format(spots=spots, length=length, creatures=CREATURES)
    if short:
        shots = max(7, round(seconds / 3.0))
        length = SHORT.format(seconds=seconds, shots=shots, words=int(seconds * 1.85))
    else:
        shots = round(minutes * 60 / 3.3)
        length = FILM.format(minutes=f"{minutes:g}", shots=f"{shots - 8}-{shots + 6}", words=int(minutes * 60 * 1.8))
    return RULES.format(spots=spots, length=length)


def _asking(cfg: Config, topic: str, fiction: bool, take: str = "") -> tuple[str, str, list[dict]]:
    """What the writer is asked for, the films already made (never again), and those films."""
    past = recent(cfg)
    made = "\n".join(f"- {p['title']} ({p['problem']})" for p in past[-40:]) or "- none yet"
    sections = parse_script(topic)
    if sections:
        ask_for = (f"THE USER'S SCRIPT (as they wrote it):\n{topic}\n\nITS SECTIONS, VISUALS AND NUMBERED SPOKEN LINES (use "
                   f"every line word for word, in order):\n{script_block(sections)}")
    elif fiction:
        ask_for = (f"THE BRIEF (the user's own; follow it closely):\n{topic}" if topic else
                   "Invent an original sci-fi or fantasy premise for him (an ordinary man meets something extraordinary), "
                   "different from the films already made.")
    else:
        ask_for = (f"Write it about: {topic}." if topic else
                   "Choose the struggle yourself, different from the ones already made. Ideas (not a list to copy): " + ", ".join(TOPICS) + ".")
    return ask_for + (TAKE.format(take=take) if take else ""), made, past


def write(cfg: Config, topic: str, *, short: bool, seconds: int = 35, minutes: float = 3.5, progress=log.info,
          kind: str = "life", save_to: Path | None = None, take: str = "") -> Story:
    """The story, shot by shot (a film over LONG_FROM minutes: outline, then act by act). `take`: this storyboard's own
    way of telling it, one of several drafts the user chooses from (boards.py)."""
    fiction = kind == "fiction"
    sections = parse_script(topic)
    system = _system(fiction, short, seconds, minutes, script=bool(sections))
    ask_for, made, past = _asking(cfg, topic, fiction, take)
    if sections:
        progress(f"Your script: {len(sections)} sections, {len(script_lines(sections))} spoken lines, staged as written")
    if not short and minutes > LONG_FROM and not sections:
        story = write_long(cfg, ask_for, made, minutes=minutes, fiction=fiction, progress=progress, save_to=save_to)
        story.kind = "fiction" if fiction else "life"
        return story
    prompt = f"{ask_for}\n\nAlready made (never the same struggle, story or title again):\n{made}{_known(cfg)}"
    story = ask(cfg.ai_backend, cfg.claude_model, system, prompt, Story, allow_web=False, effort=cfg.claude_effort, timeout=2400)
    near = too_close(story, past) if not topic and not take else ""
    if sections:
        keep_script_lines(story, script_lines(sections))
    if near:
        progress(f"That story is too close to '{near}'; writing a different one")
        story = ask(cfg.ai_backend, cfg.claude_model, system, prompt + f"\n\nYour first idea was too close to '{near}'. Pick a "
                    "different struggle and story.", Story, allow_web=False, effort=cfg.claude_effort, timeout=2400)
    if short and "#shorts" not in [h.lower() for h in story.hashtags]:
        story.hashtags = story.hashtags[:2] + ["#shorts"]
    story.kind = "fiction" if fiction else "life"
    return story



# ---------------------------------------------------------------- storyboards to choose from (boards.py)

class Pitch(BaseModel):
    title: str = Field(description="2-5 words")
    take: str = Field(description="this version in 3-5 plain sentences: what happens from the first shot to the last, the "
                                  "places, who is in it and how it ends")
    differs: str = Field(description="one line: what makes it unlike the other takes")


class Pitches(BaseModel):
    takes: list[Pitch]


PITCH = """

BEFORE ANY STORYBOARD IS WRITTEN: the user will read {n} different storyboards made from the same prompt and choose one
to build. Propose the {n} takes they will be written from. They differ in the story itself, not only in the wording: a
different moment of the struggle or angle on the brief, another structure, other places and people, another ending.
Each keeps to the prompt (the user's brief always holds), fits this channel's films and the length, and can be staged
with the places, actions and things above. Never one already written for this prompt. Write the takes only."""


def pitches(cfg: Config, topic: str, *, kind: str, short: bool, seconds: int, minutes: float, n: int,
            others: str = "") -> list[Pitch]:
    """`n` clearly different takes on one prompt, each the seed of one storyboard draft (written in parallel, they would
    otherwise not know about each other and could tell the same story three times)."""
    fiction = kind == "fiction"
    system = _system(fiction, short, seconds, minutes, script=bool(parse_script(topic))) + PITCH.format(n=n)
    ask_for, made, _ = _asking(cfg, topic, fiction)
    prompt = (f"{ask_for}\n\nAlready made (never the same struggle, story or title again):\n{made}{_known(cfg)}"
              + (f"\n\nStoryboards already written for this prompt (every new take must differ from each of them):\n{others}"
                 if others else "") + f"\n\nPropose {n} takes.")
    got = ask(cfg.ai_backend, cfg.claude_model, system, prompt, Pitches, allow_web=False, effort=cfg.claude_effort, timeout=1200)
    return got.takes[:n]

# ---------------------------------------------------------------- vehicles, and the things the writer designed

MAX_PARTS = 60
RIDER_MADE = 0.78  # = RIDER_SCALE.made in Big.tsx: how big someone seated in a design is drawn
CANOPY_OVER_SEAT = 0.82  # his head's centre over his seat at that size: a canopy is centred there
CANOPY = (1.0, 0.95, 1.8)  # its width, height, length: his head, his shoulders, room in front


def _hex(c: str) -> str:
    c = (c or "").strip()
    return c if re.fullmatch(r"#[0-9a-fA-F]{6}", c) else "#8a8f98"


def _part_box(p: LPPart) -> list[tuple[float, float, float]]:
    """A part's eight corners (turned as the editor turns it: Euler XYZ in degrees) relative to its centre."""
    import math

    a, b, c = (max(0.02, min(40.0, float(v))) for v in (list(p.size) + [0.0, 0.0, 0.0])[:3])
    if p.shape in ("cylinder", "cone"):
        d = max(a, c if p.shape == "cylinder" else 0.0)
        ext = (d / 2, b / 2, d / 2)
    else:
        ext = (a / 2, b / 2, c / 2)
    rx, ry, rz = (math.radians(float(v)) for v in (list(p.turn) + [0.0, 0.0, 0.0])[:3])
    out = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz in (-1, 1):
                x, y, z = sx * ext[0], sy * ext[1], sz * ext[2]
                # three.js Euler 'XYZ': the vector is turned about z, then y, then x
                x, y = x * math.cos(rz) - y * math.sin(rz), x * math.sin(rz) + y * math.cos(rz)
                x, z = x * math.cos(ry) + z * math.sin(ry), -x * math.sin(ry) + z * math.cos(ry)
                y, z = y * math.cos(rx) - z * math.sin(rx), y * math.sin(rx) + z * math.cos(rx)
                out.append((x, y, z))
    return out


def design_for_editor(m: LPMade) -> dict:
    """A design as the editor builds it: at most MAX_PARTS parts with sane sizes and colours, moved so it is centred on
    x and z with its bottom at y = 0, its size (dims) from its parts, seats and the standing height moved with it."""
    parts = [p for p in m.parts if len(p.at) >= 3 and len(p.size) >= 2][:MAX_PARTS]
    if not parts:
        parts = [LPPart(shape="box", at=[0, 0.5, 0], size=[1, 1, 1], color="#8a8f98")]
    lo, hi = [1e9] * 3, [-1e9] * 3
    for p in parts:
        for cx, cy, cz in _part_box(p):
            pt = (float(p.at[0]) + cx, float(p.at[1]) + cy, float(p.at[2]) + cz)
            lo = [min(a, b) for a, b in zip(lo, pt)]
            hi = [max(a, b) for a, b in zip(hi, pt)]
    shift = (-(lo[0] + hi[0]) / 2, -lo[1], -(lo[2] + hi[2]) / 2)
    dims = [round(hi[k] - lo[k], 3) for k in range(3)]
    out = []
    for p in parts:
        size = [round(max(0.02, min(40.0, float(v))), 3) for v in (list(p.size) + [0.0, 0.0, 0.0])[:3]]
        d = {"shape": p.shape, "at": [round(float(p.at[k]) + shift[k], 3) for k in range(3)], "size": size,
             "turn": [round(float(v), 2) for v in (list(p.turn) + [0.0, 0.0, 0.0])[:3]], "color": _hex(p.color)}
        if p.glow:
            d["glow"] = True
        if p.glass:
            d["glass"] = True
        if p.spin:
            d["spin"] = p.spin
        if p.move:
            d["move"] = p.move
        out.append(d)
    seats = [[round(float(x[0]) + shift[0], 3), round(max(0.0, float(x[1]) + shift[1]), 3), round(float(x[2]) + shift[2], 3)]
             for x in m.seats if len(x) >= 3][:6]
    creature = m.travel == "legs" or any(p.move for p in parts)
    if not seats and not creature:
        seats = [[0.0, round(dims[1] * 0.45, 3), round(dims[2] * 0.1, 3)]]
    if m.travel == "air" and not creature:
        # a closed cockpit over every seat (the user: "add ceiling on the car or aircraft": the pilots sat on top of
        # the planes with their heads and shoulders out): a glass canopy where Claude's design has none over his head
        boxes = []
        for p in out:
            if p.get("glass"):
                pp = LPPart.model_validate(p)
                corners = _part_box(pp)
                boxes.append([(p["at"][k] + min(c[k] for c in corners), p["at"][k] + max(c[k] for c in corners)) for k in range(3)])
        for sx, sy, sz in seats:
            head = (sx, sy + CANOPY_OVER_SEAT, sz)
            if any(all(lo <= head[k] <= hi for k, (lo, hi) in enumerate(b)) for b in boxes):
                continue
            out.append({"shape": "sphere", "at": [sx, round(sy + CANOPY_OVER_SEAT, 3), sz], "size": list(CANOPY), "turn": [0, 0, 0],
                        "color": "#9fb6c8", "glass": True})
            out.append({"shape": "box", "at": [sx, round(sy + CANOPY_OVER_SEAT + CANOPY[1] / 2 - 0.01, 3), sz],
                        "size": [0.05, 0.03, round(CANOPY[2] * 0.8, 3)], "turn": [0, 0, 0], "color": "#22252a"})
            dims[1] = max(dims[1], round(sy + CANOPY_OVER_SEAT + CANOPY[1] / 2, 3))
    top = float(m.top) + shift[1] if m.top > 0 else dims[1]
    return {"parts": out, "seats": seats, "top": round(max(0.0, min(dims[1], top)), 3), "travel": m.travel, "dims": dims}


def designs(story: Story) -> dict[str, LPMade]:
    return {_key(m.name): m for m in story.made}


def travel_of(story: Story, b: LPBig) -> str:
    """How a big thing moves when it goes: 'ground' for a car, bus or truck, a design's own way, else 'none'."""
    if b.kind in VEHICLES:
        return "ground"
    if b.kind == "made":
        m = designs(story).get(_key(b.made))
        return m.travel if m else "none"
    return "none"


CUT_SHOT_EVERY = 15  # shots: at most one whole shot on the pedal, the wheel or the speedometer in this many
CUT_SHOT_INSTEAD = {"pedal": "chase", "wheel": "cockpit", "speedo": "chase"}


def _cut_shots(story: Story) -> list[str]:
    """A whole shot on his foot, his hands or the dial is a beat a film uses once in a while (the user's 55 s film had
    five on the pedal, floating shoes each time): only with someone driving a car in it, at most one every
    `CUT_SHOT_EVERY` shots; the others get the car's own camera (the cut-ins come by themselves inside shots)."""
    notes, last = [], -CUT_SHOT_EVERY
    for i, s in enumerate(story.shots):
        if s.camera not in CUT_SHOT_INSTEAD:
            continue
        driving = any(a.action == "drive" and a.on and a.on <= len(s.big) and s.big[a.on - 1].kind == "car" for a in s.actors)
        if driving and i - last >= CUT_SHOT_EVERY:
            last = i
            continue
        new = CUT_SHOT_INSTEAD[s.camera]
        notes.append(f"Shot {i + 1}: '{s.camera}' as a whole shot again so soon (or with nobody driving) became '{new}'")
        s.camera = new
    return notes


def _broken_bridge(story: Story) -> list[str]:
    """A car jumping on the open highway jumped over nothing (the user: "this not look real broken highway"): it leaps
    the fallen span of the 'bridge' instead, and the shots of vehicles under way on the highway right before and after
    it (the run-up, the landing) go onto that bridge with it."""
    def jumps(s: LPShot) -> bool:
        return any(b.motion == "jump" and travel_of(story, b) == "ground" for b in s.big)

    def under_way(s: LPShot) -> bool:
        return any(travel_of(story, b) == "ground" and (b.motion in GROUND_UNDERWAY or b.motion in ("drive", "stop")) for b in s.big)

    # a story about a road (the user's first broken-highway film was staged on the roofs, and a re-make kept it there):
    # its car jumps on the roofs go to the bridge too
    told = " ".join([story.title, story.problem, *(x.line for x in story.shots)]).lower()
    roads = bool(re.search(r"\b(highway|bridge|flyover|overpass|freeway|expressway|motorway|road)s?\b", told))
    places = {"highway", "rooftop"} if roads else {"highway"}
    notes, shots = [], story.shots
    for i, s in enumerate(shots):
        if s.set not in places or not jumps(s):
            continue
        run = [i]
        for step in (-1, 1):
            j = i + step
            while 0 <= j < len(shots) and shots[j].set == s.set and under_way(shots[j]):
                run.append(j)
                j += step
        for j in sorted(run):
            shots[j].set = "bridge"
        notes.append(f"Shots {', '.join(str(j + 1) for j in sorted(run))}: the jump leaps a broken bridge ('bridge')")
    return notes


def _vehicles(story: Story, s: LPShot) -> list[str]:
    """Notes; fixes what the editor can't draw about vehicles in a shot (a design that doesn't exist, a car flying, a
    driver with no car, two at one wheel, someone falling free on the ground)."""
    notes = []
    known = designs(story)
    keep = []
    for b in s.big:
        if b.kind == "made":
            m = known.get(_key(b.made)) or (next(iter(known.values())) if len(known) == 1 else None)
            if not m:
                notes.append(f"a design '{b.made}' that the film doesn't have was left out")
                continue
            b.made = m.name
        else:
            b.made = ""
        keep.append(b)
    # (people `on` a thing that was left out: renumbered, or on the ground)
    if len(keep) != len(s.big):
        index = {id(b): k for k, b in enumerate(keep)}
        for a in s.actors:
            if a.on:
                old = s.big[a.on - 1] if 0 < a.on <= len(s.big) else None
                a.on = index[id(old)] + 1 if old is not None and id(old) in index else 0
        s.big = keep
    for b in s.big:
        way = travel_of(story, b)
        if way == "legs":  # an animal or creature: it walks, charges, roars, hatches; never races or flies
            if b.motion in GROUND_UNDERWAY or b.motion in AIR_MOTIONS or b.motion in ("drive", "stop"):
                b.motion = "charge" if b.motion in GROUND_UNDERWAY else "walk"
            continue
        if b.motion in CREATURE_MOTIONS and b.motion != "hatch" and way != "air":
            b.motion = "still" if way == "none" else "drive"
        elif b.motion in ("walk", "charge", "roar") and way == "air":
            b.motion = "fly"
        if way == "air" and (b.motion in GROUND_UNDERWAY or b.motion in ("drive", "stop")):
            b.motion = "fly"
        elif way in ("ground", "water") and b.motion in AIR_MOTIONS:
            b.motion = "race"
        elif way == "none" and (b.motion in GROUND_UNDERWAY or b.motion in AIR_MOTIONS):
            b.motion = "still"
    vehicles = [k for k, b in enumerate(s.big) if travel_of(story, b) not in ("none", "legs")]
    drivers: dict[int, int] = {}
    for a in s.actors:
        if a.on and (a.on > len(s.big) or (a.on - 1) not in vehicles):
            a.on = 0
        if a.action == "skydive":
            a.on = 0
            if s.set != "sky":
                s.set = "sky"
                notes.append("someone falling free goes in the sky")
        if a.action in ("drive", "ride") and not a.on:
            if vehicles:
                a.on = vehicles[0] + 1
            elif s.set == "sky":
                air = next((m for m in story.made if m.travel == "air"), None)
                if air:
                    s.big.append(LPBig(kind="made", made=air.name, spot="center", motion="fly"))
                    a.on = len(s.big)
                    vehicles.append(len(s.big) - 1)
                else:
                    a.action = "skydive"
            else:
                s.big.append(LPBig(kind="car", spot="center", motion="race" if story.kind == "fiction" else "drive"))
                a.on = len(s.big)
                vehicles.append(len(s.big) - 1)
                notes.append(f"{a.who} was at the wheel of nothing: a car added")
        if a.on and a.action == "drive":
            if a.on in drivers:
                a.action = "ride"  # one at the wheel; the next one a passenger
            drivers[a.on] = 1
        if a.on and a.action in ("walk", "run", "jog", "dash", "flee"):
            a.action = "brace"
        if a.on:
            a.to = None
    # a car under way in a room (or a plane): out to the road or into the sky
    under = [b for b in s.big if b.motion in GROUND_UNDERWAY or b.motion in AIR_MOTIONS or (b.motion in ("drive", "stop") and any(
        a.on and s.big[a.on - 1] is b for a in s.actors))]
    if under and s.set not in OUTDOOR_SETS and s.set != "sky":
        flying = any(b.motion in AIR_MOTIONS for b in under)
        s.set = "sky" if flying else "highway"
        notes.append(f"a vehicle under way can't be indoors: '{s.set}'")
    return notes


def repair(story: Story) -> list[str]:
    """Fix what the editor can't draw, in code: an unknown spot, a lying action away from a bed, a cast member who
    isn't in the cast, more than one red line, vehicles (vehicles_ above). Returns notes for the report: staging the
    editor fixed by itself, not faults of the video."""
    notes = []
    names = {_key(c.name) for c in story.cast}
    fiction = story.kind == "fiction"
    seen_made: set[str] = set()
    story.made = [m for m in story.made if not (_key(m.name) in seen_made or seen_made.add(_key(m.name)))]
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
            ridden = any(a.on and a.on - 1 < len(s.big) and s.big[a.on - 1] is b for a in s.actors)
            if need and need not in acts and not (b.motion == "thrown" and "lift" in acts) and not (b.motion == "stop" and ridden):
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
        # someone who isn't in the cast: a creature the writer named as an actor ('T-Rex') is left out (it is a design,
        # never the man: the user's dinosaur script showed him in every shot); in a film with him, anyone else unknown
        # is him
        made_names = {_key(m.name) for m in story.made}
        keep = []
        for a in s.actors:
            if a.who != "hero" and _key(a.who) not in names:
                if not story.hero or _key(a.who) in made_names or re.search(
                        r"saur|rex|raptor|dino|dragon|creature|monster|beast|animal|wolf|lion|tiger|bird|whale|shark|egg|baby", a.who, re.I):
                    notes.append(f"Shot {i + 1}: '{a.who}' isn't a person in the film; left out")
                    continue
                a.who = "hero"
            if a.who == "hero" and not story.hero:
                notes.append(f"Shot {i + 1}: the film has no man in it; he was left out")
                continue
            keep.append(a)
        s.actors = keep
        for a in s.actors:
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
        if s.overgrown and s.set not in OVERGROWN_SETS:
            s.overgrown = ""  # only the city's places are drawn taken back by nature (= Overgrowth in Sets.tsx)
        notes += [f"Shot {i + 1}: {n}" for n in _vehicles(story, s)]
        # a shot with nobody in it: fine when a vehicle or something else is there (the camera follows the car); a
        # shot of nothing at all gets him
        if not s.actors and not s.big and not s.fx and story.hero and not s.stamp:
            s.actors = [LPActor(who="hero", action="stand", expression="neutral", spot="center")]
            notes.append(f"Shot {i + 1} had nothing in it; he stands there.")
        notes += [f"Shot {i + 1}: {n}" for n in _stage(story, s)]
    notes += _broken_bridge(story)
    notes += _cut_shots(story)
    reds = [i for i, s in enumerate(story.shots) if s.red]
    for i in reds[:-1]:
        story.shots[i].red = False
    if not reds and story.shots:
        last = next((s for s in reversed(story.shots) if s.line.strip()), None)
        if last:
            last.red = True
    return notes


# ---------------------------------------------------------------- the same film, shot again (the video page's 🎬 New angles)
# The user: "add option to re-generate same with same data but different angles. storyboard". The words, speakers, order,
# stamps and pauses stay as they were (so the voices, the music and the timing are reused); only the pictures change.

class ShotStaging(BaseModel):
    shot: int = Field(description="the shot's number as given (1 = first)")
    set: SetName
    light: LightName
    camera: CamName
    subject: str = Field("", description="who the camera is on: 'hero' or a name of someone in the shot")
    actors: list[LPActor]
    things: list[LPThing] = Field(default_factory=list)
    sounds: Sounds = Field(default_factory=list)
    big: list[LPBig] = Field(default_factory=list)
    fx: list[LPFx] = Field(default_factory=list)
    slowmo: bool = False
    overgrown: Literal["", "ruined", "growing"] = ""


class Restaging(BaseModel):
    shots: list[ShotStaging] = Field(description="every shot asked for, in order, each with its new staging")


RESTAGE = """

YOU ARE DIRECTING A FINISHED FILM AGAIN. Its words, speakers, order, time stamps and pauses are final: they are
recorded and timed. You choose new pictures for them, shot by shot (the shot numbers as given):
- A new camera for every shot: a different one from the camera it had (shown), unless only that one can show the
  moment; close and far mixed like a film, never the same camera three shots running.
- Better staging where you can: the action that shows what the line says, who looks at whom (`look_at`), who the
  camera is on (`subject`), everyone on their own spot, the speaker in the shot when someone speaks.
- Keep each scene's place and light unless a line plainly happens somewhere else; keep the same people in each shot
  (leave out someone with nothing to do there, or bring in someone of the cast who is plainly present).
- Keep the big things and effects the story needs (the bus, the crash, the catch), timed and placed so they read better.
"""
RESTAGE_BATCH = 40  # shots per call: a long film's whole storyboard would not fit one answer


def _staged(s: LPShot) -> str:
    who = "; ".join(f"{a.who} {a.action}" + (f" on big {a.on}" if a.on else f"@{a.spot}") + (f"->{a.to}" if a.to else "")
                    + (f" looks at {a.look_at}" if a.look_at else "") for a in s.actors) or "(nobody)"
    extra = "".join([f"; big: {', '.join(f'{b.made or b.kind} {b.motion}' for b in s.big)}" if s.big else "",
                     f"; fx: {', '.join(f.kind for f in s.fx)}" if s.fx else "", "; slow motion" if s.slowmo else ""])
    return f"[{s.set}, {s.light}, camera {s.camera}, on {s.subject or 'hero'}] {who}{extra}"


def restage(cfg: Config, story: Story, progress=log.info) -> Story:
    """The same film with a new storyboard: Claude stages every shot again (cameras, actions, spots, who looks at
    whom), in batches that each know how the shots before them were staged. A shot Claude leaves out keeps its old
    staging."""
    spots = "; ".join(f"{k}: {', '.join(sorted(v))}" for k, v in SPOTS.items())
    fiction = story.kind == "fiction"
    system = ((FICTION if fiction else RULES).format(spots=spots, length="the same shots as given, one staging each", creatures=CREATURES)
              + ("" if fiction else CREATURES) + RESTAGE)
    if story.made:
        system += "\nThis film's own designs (big things of kind 'made', names exactly): " + "; ".join(
            f"{m.name} ({m.what}, {m.travel})" for m in story.made) + "\n"
    if not story.hero:
        system += "\nThis film has no people in it: no actors at all, only its creatures, things and places.\n"
    cast = "\n".join(f"- {c.name}: {c.who}" for c in story.cast) or "- nobody else"
    new = [s.model_copy(deep=True) for s in story.shots]
    for start in range(0, len(new), RESTAGE_BATCH):
        part = range(start, min(len(new), start + RESTAGE_BATCH))
        if len(new) > RESTAGE_BATCH:
            progress(f"Claude is writing the new storyboard: shots {part[0] + 1}-{part[-1] + 1} of {len(new)}")
        listing = "\n".join(f"{i + 1}. " + (f"STAMP '{s.stamp}' " if s.stamp else "") + (f"{s.speaker}: \"{s.line}\"" if s.line.strip() else "(silent)")
                            + (f" (+{s.pause:g} s pause)" if s.pause else "") + f"\n   was: {_staged(story.shots[i])}"
                            for i, s in ((i, story.shots[i]) for i in part))
        before = "\n".join(f"{i + 1}. {_staged(new[i])}" for i in range(max(0, start - 4), start))
        prompt = (f"THE FILM: '{story.title}': {story.problem}\nThe people besides him (names exactly):\n{cast}\n\n"
                  + (f"How the shots just before were staged in this new version:\n{before}\n\n" if before else "")
                  + f"Stage shots {part[0] + 1} to {part[-1] + 1} again:\n{listing}")
        got = ask(cfg.ai_backend, cfg.claude_model, system, prompt, Restaging, allow_web=False, effort=cfg.claude_effort, timeout=2400)
        for st in got.shots:
            i = st.shot - 1
            if i in part:
                new[i] = LPShot.model_validate({**new[i].model_dump(), **st.model_dump(exclude={"shot"})})
    out = story.model_copy(update={"shots": new})
    repair(out)
    return out


# cameras that can show a moment, by what the subject does (`new_angles`); aerial only outdoors
OUTDOOR_SETS = {"street", "park", "busstop", "rooftop", "construction", "highway", "bridge", "alley", "sky", "jungle", "plain"}  # = outdoor: true in Sets.tsx
_LYING_ACTS = {"lie", "lie-side", "lie-phone", "sit-up"}
_MOVING_ACTS = {"walk", "run", "jog", "dash", "flee", "carry"}
_POWER_ACTS = {"catch", "lift", "throw", "push-stop", "super-jump", "land", "punch", "fall", "crush"}
_HELD_ACTS = {"phone", "drink", "read", "eat", "type", "look-hands"}
ANGLES = {
    "lying": ["top", "face-top", "wide", "side", "medium"],
    "moving": ["side", "front", "back", "wide", "low", "medium", "aerial"],
    "power": ["side", "wide", "low", "orbit", "medium", "aerial"],
    "stop": ["side", "wide"],
    "held": ["detail", "face", "medium", "back", "side", "wide"],
    "other": ["face", "medium", "back", "wide", "side", "front", "low", "orbit", "crash-zoom"],
    # in or on a vehicle under way, or a shot of only the vehicle: the car-chase and air-to-air cameras
    "vehicle": ["chase", "tracking", "cockpit", "lead", "pass-by", "heli", "bumper", "back", "face", "orbit", "drone"],
    "falling": ["back", "side", "front", "orbit", "face"],
}


def new_angles(story: Story, seed: int) -> Story:
    """The same film and staging with a new camera on every shot (no Claude): one that can show what the subject does,
    never the one it had (unless nothing else fits), never the shot before's, mostly not the last few, close and far
    mixed. A different `seed` gives a different set of angles."""
    import random

    rnd = random.Random(seed)
    new = [s.model_copy(deep=True) for s in story.shots]
    recent: list[str] = []
    for s in new:
        here = {who_key(a.who): a for a in s.actors}
        lead = here.get(who_key(s.subject or "hero")) or (s.actors[0] if s.actors else None)
        act = lead.action if lead else "stand"
        kind = ("vehicle" if (lead and lead.on) or (not s.actors and s.big) else "falling" if act in ("skydive", "jump-off")
                else "stop" if act == "push-stop" else "lying" if act in _LYING_ACTS else "moving" if act in _MOVING_ACTS
                else "power" if act in _POWER_ACTS else "held" if act in _HELD_ACTS or (lead and lead.hold != "none") else "other")
        pool = [c for c in ANGLES[kind] if c != "aerial" or s.set in OUTDOOR_SETS]
        if lead and lead.look_at and s.camera in ("medium", "back") and kind == "other":
            pool = ["medium", "back", "wide", "side"]  # a look or a gesture at someone: both in the picture
        fresh = [c for c in pool if c != s.camera and c not in recent[-1:]] or [c for c in pool if c not in recent[-1:]] or pool
        weights = [0.3 if c == "crash-zoom" else 0.5 if c in recent[-3:] else 1.0 for c in fresh]
        s.camera = rnd.choices(fresh, weights)[0]
        recent.append(s.camera)
    out = story.model_copy(update={"shots": new})
    repair(out)
    return out


GESTURES = {"point", "help-up", "wave", "carry"}  # an action at another person: both must be in the picture
ONE_FACE = {"face", "face-top", "front", "detail", "top", "low", "crash-zoom"}  # cameras that show only the subject
IN_FRONT = {"face", "front", "low", "crash-zoom", "detail"}  # cameras placed in front of the subject's face


def who_key(name: str) -> str:
    n = (name or "").strip()
    return "hero" if n.lower() in ("hero", "he", "him", "his") else _key(n) if n else ""


def _stage(story: Story, s: LPShot) -> list[str]:
    """Who looks at whom and who the camera is on, in code: a `look_at` or `subject` naming nobody in the shot is
    dropped; a line said to someone has the speaker and the listeners looking at each other; someone pointing with
    one other person there points at them; the camera is on the subject; and a gesture at someone else (pointing at
    his dad) is never a one-face camera, which left the dad out of the picture."""
    notes = []
    if not s.actors:  # only a vehicle or a place: the camera is on it
        s.subject = ""
        return notes
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
    # stopping a car or bus with his hands: a camera in front of him stands where it stops (the editor's camera ended
    # up inside the bus); from the side
    stops = [a for a in s.actors if a.action == "push-stop"]
    if stops and who_key(stops[0].who) == subject and s.camera in IN_FRONT:
        notes.append(f"'{s.camera}' on a man stopping a vehicle stood where it stops: 'side'")
        s.camera = "side"
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
