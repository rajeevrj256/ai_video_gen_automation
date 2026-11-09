"""🎭 Cast intro: a short film (about a minute, 16:9 by default) that introduces the recurring cast one by one like a
movie's opening, the user: "create intro of each chara on short 1 min 16:9 with different camera angle of each.
equally divide the char screen time in 1 min, while showing, add name and role just like movie intro".

Code decides the timing and the cameras, Claude only the staging: who is shown where, doing what (one call, no web,
the writer's model at low effort; a plan in code when the call fails). Every person gets the same screen time
(`seconds / people`), cut into 1-3 shots of ~3.5 s, each from a camera that person hasn't had and that the shot before
didn't use; their name and role come up over their segment (props `cards`, `NameCard` in the editor). No narration:
the score carries it (the mix places a silent film's music as the lead)."""
from __future__ import annotations

import logging
import re
from typing import Literal

from pydantic import BaseModel, Field

from ..config import Config
from . import story as S

log = logging.getLogger(__name__)

SHOT_SECONDS = 3.5  # about this long a shot; a person gets 1-3 of them
MAX_SHOTS = 3
# cameras for one standing or sitting person (no vehicle, insert or lying-only cameras)
POOL = ["medium", "low", "face", "wide", "front", "orbit", "crash-zoom"]  # no back, side, top or aerial: an intro shows faces (a profile hid Mia behind her hair)
OUTDOOR_ONLY: set[str] = set()
OUTDOOR = {"street", "park", "busstop", "rooftop", "construction", "alley"}
IntroSet = Literal["bedroom", "hallway", "street", "park", "kitchen", "living", "office", "bathroom", "gym", "cafe", "busstop",
                   "rooftop", "construction", "alley", "lab"]
IntroAction = Literal["stand", "walk", "sit", "phone", "type", "read", "drink", "eat", "look-out", "wave", "point", "cheer", "nod",
                      "think", "stretch", "shrug", "jog", "pushup", "lift", "talk", "crouch", "kneel", "look-hands", "reach"]
FREEZE_CAMS = ["medium", "low", "front", "crash-zoom", "face"]  # the name lands on a face, never a wide or an orbit
AWAY_SPOTS = {"counter", "window", "mirror", "door"}  # spots where people face away from the room: their back to us
HERO_WHO = "the man every film is about: quiet, kind, always half a step behind his own life"


class IntroShot(BaseModel):
    action: IntroAction = Field(description="what they do in this shot: something that shows who they are")
    expression: S.ExprName
    hold: S.HoldName = Field("none", description="what is in their hand")
    spot: S.SpotName = Field("center", description="where in the place (a seat spot for sit/type)")
    things: list[S.ThingName] = Field(default_factory=list, description="0-2 objects put down near them")
    camera: S.CamName = Field("medium", description="a preference; the code makes every shot's camera different")


class IntroPerson(BaseModel):
    name: str = Field(description="exactly as listed")
    role: str = Field(description="2-5 words, shown small under the name like a movie's character intro, in their relation "
                                  "to him and/or their job: 'HIS SISTER · NURSE', 'THE BOSS', 'BEST FRIEND'; for him: "
                                  "'THE ONE IT'S ALL ABOUT' or similar")
    set: IntroSet = Field(description="the place that is theirs: their work, their home, where he meets them")
    light: S.LightName
    shots: list[IntroShot]


class IntroPlan(BaseModel):
    title: str = Field(description="2-5 words ('Meet the Cast', 'The People in His Life')")
    youtube_title: str
    description: str = Field(description="2 sentences for the post")
    tags: list[str]
    hashtags: list[str]
    mood: S.Mood
    music_prompt: str = Field(description="the theme's feeling in a few words (a warm, building character theme...)")
    tagline: str = Field("", description="the closing movie poster's tagline, 3-7 words, an action film's ('ONE CITY. NO SMALL PARTS.')")
    people: list[IntroPerson]


SYSTEM = """You stage a crime-caper film's CAST INTRODUCTION (fast, cinematic, full of attitude) for a low-poly 3D animated channel: one person after another,
each in the place that is theirs, doing the one thing that says who they are, while their name and role come up on
screen. No dialogue, no narration: music only.

For each person, in the order given:
- `set`: their own place (a nurse at home in the hallway or kitchen, a foreman at the construction site, a barista at the
  cafe, a trainer at the gym, a scientist in the lab, a police officer on the street, a boss in the office, a grandfather
  in the park, a child in the park or living room, a neighbour in the hallway, a rich businessman on the rooftop).
  Neighbours in the list may share a place only when it truly is theirs; vary it otherwise.
- `light`: suits them and varies down the list (morning, day, evening, lamp, night, dawn).
- exactly the number of `shots` asked for, each a different moment of the same character: a signature action
  (the trainer lifts, the barista holds a mug, the boss types at the desk or stands arms folded with the 'point'
  gesture, the child cheers or jogs, the grandfather sits and reads), then a look or a nod to us. Seated actions
  (sit, type, read with a seat) need a seat spot of the place (chair, couch, desk, bed); otherwise use center, left
  or right (never counter, window, mirror or door: people face away there and we'd see their back). Expressions show
  their personality.
- `role`: 2-5 words, the way a crime-caper film's freeze-frame intro tags a character: who they are to him and what
  they're known for, with attitude, in your own words for each person (the shape of 'THE LANDLORD. ALWAYS COLLECTS.',
  'HIS COUSIN. TALKS TOO MUCH.'; never copy these).
- The picture freezes a beat or two into each person's last shot and their name slams on: make that shot's action land
  early and hit a pose (a look to us, a point, a nod, a lift, a sip, a cheer), with an expression full of attitude.
Only the person being introduced is in their shots."""


def people(cfg: Config, names: list[str], hero_name: str) -> list[dict]:
    """The people to introduce, in order: him first (when chosen), then the saved cast in its order. `names` empty = all."""
    saved = S.seed_library(cfg)
    want = [S._key(n) for n in names if n.strip()]
    out = []
    if not want or "hero" in want:
        out.append({"key": "hero", "name": hero_name.strip() or "Ethan", "who": HERO_WHO, "design": None})
    for k, c in saved.items():
        if (not want or k in want) and k != "hero":
            out.append({"key": k, "name": c.get("name", k), "who": c.get("who", ""), "design": c.get("design"),
                        "voice": c.get("voice", "man")})
    if not out:
        raise RuntimeError("Pick at least one person for the cast intro")
    return out


BPM = (100, 124)  # the groove the cuts and freezes land on: a crime-caper strut, not a march
RAMP = 1.35  # the action plays this much faster before it freezes (a speed ramp into the freeze-frame)


def beat_grid(seconds: float, n: int) -> tuple[int, float, float, float]:
    """(shots per person, each shot's length, bpm, where the last shot freezes): every person the same time, each
    shot a whole number of beats, so every cut and every freeze lands on the beat of the composed score (the user: "intro
    must be energetic, not just slide changes, mafia style"). ~3.5 s a shot, 1-3 shots each; the minute may come out a
    little over or under to stay on the beat."""
    seg = seconds / n
    per = max(1, min(MAX_SHOTS, round(seg / SHOT_SECONDS)))
    want = seg / per
    best = None
    for beats in range(2, 13):
        bpm = 60 * beats / want
        for b in (int(bpm), int(bpm) + 1):
            if BPM[0] <= b <= BPM[1]:
                cost = abs(beats * 60 / b - want) * 10 + abs(b - 112) / 40
                if best is None or cost < best[0]:
                    best = (cost, beats, b)
    if best is None:  # (a very long or short shot: the nearest tempo)
        beats = max(2, round(want * 112 / 60))
        best = (0, beats, max(BPM[0], min(BPM[1], round(60 * beats / want))))
    _, beats, bpm = best
    beat = 60 / bpm
    each = beats * beat
    freeze = max(1, round(beats * 0.38)) * beat  # a beat or two of action, then the freeze and the name
    return per, round(each, 4), float(bpm), round(freeze, 4)


def split(seconds: float, n: int) -> tuple[int, float]:
    """Shots per person and each shot's length (on the beat grid)."""
    per, each, _, _ = beat_grid(seconds, n)
    return per, each


def _role(who: str) -> str:
    words = re.split(r"[,;]", who or "")[0].split()
    return " ".join(words[:4]).upper() or "A FRIEND"


GUESS = [  # a place for the code's own plan, from the words of who someone is
    (("nurse", "doctor", "scientist", "lab", "student"), "lab"), (("foreman", "building", "site", "builder"), "construction"),
    (("barista", "cafe", "coffee"), "cafe"), (("trainer", "gym", "coach"), "gym"), (("police", "officer"), "street"),
    (("boss", "manager", "office"), "office"), (("businessman", "rich", "ceo"), "rooftop"), (("grand", "old"), "park"),
    (("son", "child", "kid", "year-old"), "park"), (("mother", "mum", "mom"), "kitchen"), (("father", "dad"), "living"),
    (("neighbour", "neighbor"), "hallway"), (("friend",), "street"), (("sister", "brother"), "living"),
]
SIGNATURE = {"gym": ("lift", "none"), "cafe": ("drink", "mug"), "office": ("type", "none"), "lab": ("read", "book"),
             "construction": ("point", "none"), "street": ("look-out", "none"), "park": ("cheer", "none"),
             "kitchen": ("drink", "mug"), "living": ("read", "book"), "hallway": ("phone", "phone"), "rooftop": ("look-out", "none"),
             "bedroom": ("stretch", "none")}
SEAT = {"office": "desk", "living": "couch", "lab": "center", "cafe": "chair", "kitchen": "chair"}


def fallback_plan(cast: list[dict], per: int) -> IntroPlan:
    """No Claude: a place from who they are, their signature action, then a nod to us."""
    lights = ["morning", "day", "evening", "lamp", "dawn", "day"]
    out = []
    for k, p in enumerate(cast):
        words = (p["who"] or "").lower()
        place = "street" if p["key"] == "hero" else next((s for ks, s in GUESS if any(w in words for w in ks)), "park")
        act, hold = SIGNATURE.get(place, ("stand", "none"))
        spot = SEAT.get(place, "center") if act in ("type", "read") and place in SEAT else "center"
        moves = [IntroShot(action=act, expression="determined" if act == "lift" else "happy", hold=hold, spot=spot),
                 IntroShot(action="nod", expression="happy", spot="center"), IntroShot(action="stand", expression="neutral", spot="center")]
        if p["key"] == "hero":
            moves = [IntroShot(action="walk", expression="neutral"), IntroShot(action="look-out", expression="neutral"),
                     IntroShot(action="nod", expression="happy")]
        out.append(IntroPerson(name=p["name"], role="THE ONE IT'S ALL ABOUT" if p["key"] == "hero" else _role(p["who"]),
                               set=place, light=lights[k % len(lights)], shots=moves[:per]))
    return IntroPlan(title="Meet the Cast", youtube_title="Meet the Cast", description="The people in his life, one by one.",
                     tags=["low poly", "animation", "characters"], hashtags=["#animation", "#lowpoly", "#cast"], mood="uplifting",
                     music_prompt="a warm character theme that builds", people=out)


def cameras(plan_cams: list[list[str]], sets: list[str], seed: int = 0) -> list[list[str]]:
    """Every shot's camera: the intro goes round every angle before it uses one again, a person's shots never share
    one, and no shot repeats the camera of the shot before. The writer's choice is kept when it is one of the least
    used so far."""
    out, prev = [], ""
    used = {c: 0 for c in POOL + sorted(OUTDOOR_ONLY)}
    order = POOL[seed % len(POOL):] + POOL[: seed % len(POOL)]
    for cams, place in zip(plan_cams, sets):
        pool = order + (sorted(OUTDOOR_ONLY) if place in OUTDOOR else [])
        mine: list[str] = []
        for j, c in enumerate(cams):
            free = [x for x in pool if x not in mine and x != prev]
            if j == len(cams) - 1:  # the freeze-frame: always a camera that has their face, close enough to read
                free = [x for x in free if x in FREEZE_CAMS] or [x for x in FREEZE_CAMS if x != prev]
            least = min(used[x] for x in free)
            fresh = [x for x in free if used[x] == least]
            pick = c if c in fresh else fresh[0]
            mine.append(pick)
            used[pick] += 1
            prev = pick
        out.append(mine)
    return out


def write(cfg: Config, names: list[str], seconds: float, hero_name: str, progress=lambda m: None, film_title: str = "") -> S.Story:
    from ..llm import ask

    cast = people(cfg, names, hero_name)
    seconds = max(20.0, min(180.0, float(seconds)))
    per, each = split(seconds, len(cast))
    progress(f"Claude is staging the cast intro: {len(cast)} people, {seconds / len(cast):.1f} s each "
             f"({per} shot{'s' if per > 1 else ''} of {each:.1f} s, every one from another camera)")
    listing = "\n".join(f"{k + 1}. {p['name']}: {p['who']}" for k, p in enumerate(cast))
    prompt = (f"Stage the cast intro. {per} shot{'s' if per > 1 else ''} for each person, in this order:\n{listing}\n\n"
              "Give each person their place, light, role and shots.")
    try:
        plan = ask(cfg.ai_backend, cfg.claude_model, SYSTEM, prompt, IntroPlan, allow_web=False, effort="low", timeout=900)
    except Exception as e:  # noqa: BLE001 - a plan in code is better than no video
        if type(e).__name__ in ("Paused", "Stopped"):
            raise
        log.warning("Cast intro plan failed (%s); staging it in code", e)
        progress(f"Claude couldn't stage it ({str(e)[:120]}); staging it in code")
        plan = fallback_plan(cast, per)
    story = assemble(plan, cast, per, each, seconds)
    if film_title.strip():  # the film's own name on the poster (the user: "The Unwritten")
        story.poster["title"] = film_title.strip()[:40]
    return story


def assemble(plan: IntroPlan, cast: list[dict], per: int, each: float, seconds: float, seed: int = 0) -> S.Story:
    """The Story the timeline and editor know: the people in order, each with exactly `per` shots of `each` seconds,
    every camera different, and the cards."""
    fall = fallback_plan(cast, per)
    _, each, bpm, freeze = beat_grid(seconds, len(cast))
    by = {S._key(p.name): p for p in plan.people}
    staged = []
    for k, p in enumerate(cast):
        mine = by.get(S._key(p["name"])) or (plan.people[k] if k < len(plan.people) and len(plan.people) == len(cast) else fall.people[k])
        shots = list(mine.shots)[:per]
        while len(shots) < per:
            shots.append(fall.people[k].shots[len(shots) % len(fall.people[k].shots)])
        staged.append((p, mine, shots))
    cams = cameras([[s.camera for s in shots] for _, _, shots in staged], [m.set for _, m, _ in staged], seed)
    story_cast, story_shots, cards = [], [], []
    for (p, mine, shots), cs in zip(staged, cams):
        who = "hero" if p["key"] == "hero" else p["name"]
        if who != "hero":
            story_cast.append(S.LPCast(name=p["name"], who=p["who"] or "a friend", design=S.LPDesign(**(p["design"] or {})),
                                       voice=p.get("voice", "man") if p.get("voice") in S.VOICES else "man"))
        cards.append(S.IntroCard(who=who, name=p["name"], role=(mine.role or _role(p["who"])).strip()[:40], first=len(story_shots),
                                 shots=per, seconds=each, freeze=freeze, bpm=bpm))
        for sh, cam in zip(shots, cs):
            story_shots.append(S.LPShot(
                line="", speaker="narrator", set=mine.set, light=mine.light, camera=cam, subject=who,
                actors=[S.LPActor(who=who, action=sh.action, expression=sh.expression,
                                  spot="center" if sh.spot in AWAY_SPOTS else sh.spot, hold=sh.hold,
                                  facing="camera")],
                things=[S.LPThing(kind=x) for x in sh.things[:2]]))
    n = len(story_shots)
    score = [S.ScorePart(from_shot=1, mood=plan.mood, energy="medium")]
    if n >= 4:
        score.append(S.ScorePart(from_shot=n // 2 + 1, mood=plan.mood, energy="high"))
    story = S.Story(title=plan.title.strip() or "Meet the Cast", problem="meet the cast: " + ", ".join(p["name"] for p in cast),
                    youtube_title=plan.youtube_title, description=plan.description, tags=plan.tags, hashtags=plan.hashtags,
                    thumbnail_text="MEET THE CAST", mood=plan.mood, end_mood=plan.mood, music_prompt=plan.music_prompt,
                    cast=story_cast, shots=story_shots, score=score, kind="fiction", hero=any(p["key"] == "hero" for p in cast))
    story.intro = cards
    # the closing poster: the whole cast in one action-movie one-sheet, the rival's face (else his) over the city
    keys = {S._key(p["name"]) for p in cast}
    story.poster = {"title": story.title, "tagline": (plan.tagline or "EVERYONE HAS A PART TO PLAY").strip()[:60],
                    "face": "victor crane" if "victor crane" in keys else "hero"}
    return story
