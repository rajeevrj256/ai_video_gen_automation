"""From the written story and the recorded narration to the editor's props: each shot lasts its line plus a breath
(a silent stamp beat ~1.6 s), the narrator's words become captions two or three at a time (a stamp takes the
caption's place while it shows, as in the original), the last line is red and fades out, and the world's sounds
are put on their frames (footsteps under walks, the alarm, typing, Claude's own sounds on their words)."""
from __future__ import annotations

import re

from .story import COLOURS, HERO, Story, _key, editor_design

FPS = 30
LEAD = 0.25  # the line starts this long after its shot does
TAIL = 0.35  # and the shot holds this long after it
SILENT = 1.6  # a shot with no line
STAMP = 0.9  # a stamp shows alone this long before its shot's line starts
FADE_END = 1.1  # the last shot holds and fades to black
CHUNK_WORDS = 3
CHUNK_CHARS = 19
LYING = {"lie", "lie-side", "lie-phone", "sit-up"}


def chunks(words: list[tuple[str, float, float]]) -> list[tuple[float, float, str]]:
    """Captions of up to three words (or 19 letters), broken after punctuation and at pauses: (start, end, text)."""
    out: list[list[tuple[str, float, float]]] = []
    cur: list[tuple[str, float, float]] = []
    for w in words:
        text = w[0].strip()
        if not text:
            continue
        if cur and (len(cur) >= CHUNK_WORDS or len(" ".join(x[0] for x in cur + [w])) > CHUNK_CHARS or w[1] - cur[-1][2] > 0.35
                    or re.search(r"[,.!?;:—]$", cur[-1][0])):
            out.append(cur)
            cur = []
        cur.append(w)
    if cur:
        out.append(cur)
    res = []
    for k, c in enumerate(out):
        end = out[k + 1][0][1] if k + 1 < len(out) else c[-1][2] + 0.35
        res.append((c[0][1], end, " ".join(x[0] for x in c)))
    return res


def written(line: str, words: list) -> list:
    """The words with the line's own spelling and punctuation ('Tomorrow, for real.'), matched by position when the
    voice gives as many words as the line has (it drops the punctuation)."""
    tokens = line.split()
    if len(tokens) == len(words):
        return [[t, w[1], w[2]] for t, w in zip(tokens, words)]
    return words


def spoken(a: dict) -> float:
    """How long a line takes: to the end of its last word (the take's silent tail doesn't count)."""
    if a.get("words"):
        return min(float(a["seconds"]), float(a["words"][-1][2]) + 0.08)
    return float(a["seconds"])


WORDS = ("on", "stamps", "off")  # words on screen: subtitles + time stamps / time stamps only / nothing

# ---------------------------------------------------------------- fiction: key moments, effects and sounds

# the big thing each power action handles (keep in step with ACT_BIG in remotion/src/lowpoly/LowPoly.tsx)
ACT_BIG = {"catch": ("caught", "hang"), "lift": ("lifted", "held", "thrown"), "throw": ("thrown", "held"), "push-stop": ("stop",)}
# when an action's moment comes if the story doesn't say, as a fraction of the shot
MOMENT = {"land": 0.3, "super-jump": 0.35, "catch": 0.45, "lift": 0.35, "throw": 0.55, "push-stop": 0.4, "punch": 0.4,
          "fall": 0.25, "crush": 0.4, "gasp": 0.2}
# what comes with each action at its moment: effects (if the shot hasn't got that kind) and sounds
ACTION_FX = {"land": ("shockwave", "crack", "dust", "shake"), "super-jump": ("dust", "shockwave"), "push-stop": ("sparks", "dust", "shake"),
             "catch": ("dust", "shake"), "punch": ("debris", "dust", "shake"), "lift": ("dust",)}
ACTION_SOUNDS = {"land": (("swoosh", -0.35), ("impact", 0), ("rumble", 0.02)), "super-jump": (("swoosh", 0), ("thud", 0)),
                 "push-stop": (("skid", -0.8), ("crash", 0), ("creak", 0.25)), "catch": (("impact", 0), ("creak", 0.12)),
                 "lift": (("creak", 0.2),), "throw": (("swoosh", 0),), "punch": (("impact", 0), ("crack", 0.02)),
                 "crush": (("crack", 0),), "fall": (("thud", 0.3),), "dash": (("flyby", -9),)}
MOTION_FX = {"fall": ("dust", "debris", "shake")}
MOTION_SOUNDS = {"fall": (("swoosh", -0.5), ("crash", 0)), "drive": (("flyby", -0.7),), "hang": (("creak", -9),),
                 "stop": (), "thrown": ()}
FX_SOUNDS = {"glass": "glass", "sparks": "sparks", "fire": "fire", "rain": "rain", "wind": "wind", "alarm": "siren"}
LOOPING = {"fire", "rain", "wind", "siren", "sparks"}
VEHICLE = {"car", "bus", "truck"}
HEAVY = VEHICLE | {"beam", "boulder", "crate", "pipe"}
OUTDOOR = {"street", "park", "busstop", "rooftop", "construction", "highway", "alley"}
SCORE_ACT = {"low": "thesis", "medium": "loop", "high": "climb"}  # energy -> the music's act (sticky.mixdown.INTENSITY)


# ---------------------------------------------------------------- footsteps where the feet land

# The walk cycles in remotion/src/lowpoly/poses.ts: a leg's swing is sin(t * f * PI + k) (k = actor index * 1.7 + the
# shot's seed), and a heel lands when a leg is furthest forward: t = ((0.5 + n) - k / PI) / f, a step every 1 / f s.
STRIDE = {"walk": 1.75, "run": 2.7, "jog": 2.2, "dash": 5.5, "flee": 2.7, "carry": 1.75}  # f in poses.ts
SPEED = {"walk": 1.0, "run": 2.6, "jog": 1.7, "dash": 16.0, "flee": 2.8, "carry": 0.8}  # = SPEED in poses.ts
SLOW = 0.4  # = SLOW in LowPoly.tsx
STOP_SHORT = 1.2  # = STOP_SHORT in LowPoly.tsx: a walk to someone's spot ends this far in front of them
STOP_SEATED = 1.65  # = STOP_SEATED in LowPoly.tsx: ...or of someone on a seat (past their knees and the table)
SEAT_SPOTS = {"chair", "couch", "desk", "bed"}  # = SEAT_SPOTS in LowPoly.tsx
FLOOR = {"bedroom": "wood", "hallway": "wood", "living": "wood", "cafe": "wood", "office": "carpet", "gym": "rubber",
         "kitchen": "tile", "bathroom": "tile", "lab": "tile", "street": "concrete", "busstop": "concrete", "rooftop": "concrete",
         "highway": "concrete", "alley": "wet", "park": "path", "construction": "gravel", "void": "studio"}
CAMERA_NEAR = {"wide": 0.55, "aerial": 0.4, "top": 0.6, "side": 1.0, "front": 1.0, "back": 0.9, "low": 1.0, "orbit": 0.9,
               "face": 0.75, "face-top": 0.7, "medium": 0.8, "detail": 0.7, "crash-zoom": 0.8}
_SPOTS: dict[str, dict[str, tuple[float, float]]] | None = None


# = SEATED and LYING in LowPoly.tsx: who sits on (or lies in) a seat spot's seat; anyone else there stands at its `stand`
SEATED_ACTIONS = {"sit", "type", "eat", "shoes", "get-up", "read", "phone", "head-in-hands", "slump", "think", "drink", "sigh",
                  "nod", "shake-head", "shrug", "cry", "stretch", "reach"}
LYING_ACTIONS = {"lie", "lie-side", "lie-phone", "sit-up"}


def set_spots() -> dict[str, dict[str, tuple[float, float, float, float]]]:
    """Every set's spots from remotion/src/lowpoly/Sets.tsx, for how far a walk goes: (x, z, stand x, stand z), the
    stand being where someone who isn't sitting stands at a seat spot (the spot itself elsewhere)."""
    global _SPOTS
    if _SPOTS is None:
        from pathlib import Path

        _SPOTS = {}
        try:
            src = (Path(__file__).resolve().parents[2] / "remotion" / "src" / "lowpoly" / "Sets.tsx").read_text(encoding="utf-8")
        except OSError:
            return _SPOTS
        for m in re.finditer(r"const (\w+): SetDef = \{(.*?)\n  wide:", src, re.S):
            name = "void" if m.group(1) == "voidSet" else m.group(1)
            spots = {}
            for k, x, z, rest in re.findall(r"(\w+): \{x: (-?[\d.]+), z: (-?[\d.]+)([^}]*)\}", m.group(2)):
                st = re.search(r"stand: \[(-?[\d.]+), (-?[\d.]+)\]", rest)
                spots[k] = (float(x), float(z), *((float(st.group(1)), float(st.group(2))) if st else (float(x), float(z))))
            _SPOTS[name] = spots
    return _SPOTS


def step_times(actor, k: int, s, dur: float, seed: int) -> tuple[list[float], float | None]:
    """When this walker's feet land (seconds into the shot) and when he arrives (None: he walks all shot long). In slow
    motion the steps come 2.5 times further apart, as the picture does."""
    import math

    f = STRIDE[actor.action]
    slow = SLOW if s.slowmo else 1.0
    end = dur * slow  # in the action's own time
    arrive = None
    if actor.to:
        spots = set_spots().get(s.set, {})
        a, b = spots.get(actor.spot), spots.get(actor.to)
        if a and b:
            # he sets off from where he stands (a seat spot's standing place); someone sitting or standing where he
            # goes: he stops in front of them (LowPoly.tsx `layoutFor`, STOP_SHORT), else at the spot's standing place
            occ = next((o for o in s.actors if o is not actor and o.spot == actor.to and o.action not in STRIDE), None)
            if occ is not None:
                down = occ.action in SEATED_ACTIONS or occ.action in LYING_ACTIONS or occ.action == "sit"
                ox, oz = (b[0], b[1]) if down else (b[2], b[3])
                if actor.to == "bed" and down and occ.action not in LYING_ACTIONS:
                    oz = -0.45  # sitting on the bed's edge (LowPoly.tsx `place`)
                short = STOP_SEATED if actor.to in SEAT_SPOTS else STOP_SHORT
                arrive = max(0.0, math.hypot(ox - a[2], oz - a[3]) - short) / SPEED[actor.action]
            else:
                arrive = math.hypot(b[2] - a[2], b[3] - a[3]) / SPEED[actor.action]
            end = min(end, arrive)
    phase = k * 1.7 + seed
    first = ((0.5 - phase / math.pi) % 1.0) / f
    steps = [first + n / f for n in range(int((end - first) * f) + 1) if 0.03 <= first + n / f <= end - 0.02]
    out = [round(x / slow, 3) for x in steps]
    if arrive is not None and arrive < dur * slow:
        out.append(round(arrive / slow + 0.12, 3))  # the last foot coming down beside the other
        return out, round(arrive / slow, 3)
    return out, None


def _talk(words: list, lead: float) -> list[list[float]]:
    """When a speaker's mouth moves: their words merged where the gap is short (seconds into the shot)."""
    spans: list[list[float]] = []
    for w in words:
        a, b = lead + float(w[1]), lead + float(w[2])
        if spans and a - spans[-1][1] < 0.3:
            spans[-1][1] = b
        else:
            spans.append([a, b])
    return [[round(a, 3), round(b, 3)] for a, b in spans]


def moments(s, dur: float) -> tuple[list[float | None], list[float | None]]:
    """Each actor's and each big thing's moment in seconds into the shot (the story's fraction, else the thing he
    handles, else the action's usual moment). A beam on a crane snaps at its `at` and lands in his hands 0.8 s later."""
    bigs: list[float | None] = []
    for b in s.big:
        if b.at is not None:
            bigs.append(b.at * dur)
        else:
            bigs.append(None if b.motion in ("hang", "still", "crushed", "shake") else 0.4 * dur)
    acts: list[float | None] = []
    for a in s.actors:
        if a.at is not None:
            acts.append(a.at * dur)
            continue
        k = next((j for j, b in enumerate(s.big) if b.motion in ACT_BIG.get(a.action, ())), None)
        if k is not None and bigs[k] is not None:
            # the beam falls 0.8 s of action time after the cable snaps: 2 s on screen in slow motion
            fall = 0.8 / (0.4 if s.slowmo else 1.0)
            acts.append(bigs[k] + (fall if s.big[k].motion == "hang" else 0.0) if s.big[k].motion != "held" else None)
        elif a.action in MOMENT:
            acts.append(MOMENT[a.action] * dur)
        else:
            acts.append(None)
    return acts, bigs


def build(story: Story, audio: dict[int, dict], *, vertical: bool, watermark: str, seed: int,
          tail: float = TAIL, pauses: float = 1.0, words: str = "on") -> tuple[dict, list[dict], list[dict], list[dict]]:
    """props, voice clips [{at, path}], sound cues [{sound, at, volume, length?}], music sections. `tail` and `pauses`
    let a Short that runs long tighten its breaths; `words` turns the subtitles (and the stamps) off."""
    mode = words if words in WORDS else "on"  # (the loop below has its own `words`: each line's timed words)
    shots, captions, clips, cues = [], [], [], []
    t = 0.0
    cast = {"hero": HERO}
    for c in story.cast:
        cast[_key(c.name)] = editor_design(c.design)
    n = len(story.shots)
    for i, s in enumerate(story.shots):
        a = audio.get(i)
        line = bool(a and s.line.strip())
        length = spoken(a) if line else 0.0
        has_alarm = any(th.kind == "alarm" for th in s.things) or any(x.sound == "alarm" for x in s.sounds)
        lead = STAMP if s.stamp.strip() and mode != "off" else LEAD  # a stamp shows alone before its line
        dur = (lead + length + tail if line else SILENT + (0.8 if has_alarm else 0)) + s.pause * pauses
        if i == n - 1:
            dur += FADE_END
        dur = max(1.3, dur)
        act_at, big_at = moments(s, dur)
        speaker = "hero" if s.speaker == "hero" else _key(s.speaker) if s.speaker and s.speaker != "narrator" else ""
        actors = []
        for actor, at in zip(s.actors, act_at):
            d = {"who": "hero" if actor.who == "hero" else _key(actor.who), "action": actor.action, "expression": actor.expression,
                 "spot": actor.spot, "facing": actor.facing, "hold": actor.hold, "covered": actor.covered}
            if actor.to:
                d["to"] = actor.to
            if actor.look_at:
                d["look"] = "hero" if actor.look_at == "hero" else _key(actor.look_at)
            if at is not None:
                d["at"] = round(at, 3)
            if line and speaker and d["who"] == speaker and a.get("words"):
                lead0 = STAMP if s.stamp.strip() and mode != "off" else LEAD
                d["talk"] = _talk(a["words"], lead0)
            actors.append(d)
        subject = "hero" if (s.subject or "hero") == "hero" else _key(s.subject)  # who the camera is on
        focus = next((k for k, x in enumerate(actors) if x["who"] == subject),
                     next((k for k, x in enumerate(actors) if x["who"] == "hero"), 0))
        shot = {"start": round(t, 3), "duration": round(dur, 3), "set": s.set, "light": s.light, "camera": s.camera, "actors": actors,
                "things": [th.model_dump() | {"spot": "center"} for th in s.things], "focus": focus, "seed": seed + i * 13}
        big = []
        for b, at in zip(s.big, big_at):
            d = {"kind": b.kind, "spot": b.spot, "motion": b.motion}
            if at is not None:
                d["at"] = round(at, 3)
            if b.color:
                d["color"] = COLOURS.get(b.color, "")
            big.append(d)
        fx = [{"kind": f.kind, "at": round((f.at if f.at is not None else (0 if f.kind in ("rain", "wind") else 0.4)) * dur, 3),
               **({"spot": f.spot} if f.spot else {})} for f in s.fx]
        have = {f["kind"] for f in fx}
        heavy = {b.kind for b in s.big} & HEAVY
        for actor, at in zip(s.actors, act_at):  # what comes with each action
            for kind in ACTION_FX.get(actor.action, ()):
                if actor.action in ("catch", "lift") and (not heavy or (kind == "dust" and s.set not in OUTDOOR)):
                    continue  # a ball or a barbell indoors raises no dust and shakes nothing
                if kind not in have and (at is not None or kind == "speed"):
                    fx.append({"kind": kind, "at": round(at, 3)})
                    have.add(kind)
            if actor.action == "dash" and "speed" not in have:
                fx.append({"kind": "speed", "at": 0})
                have.add("speed")
        for b, at in zip(s.big, big_at):
            for kind in MOTION_FX.get(b.motion, ()):
                if kind not in have and at is not None:
                    fx.append({"kind": kind, "at": round(at, 3), "spot": b.spot})
                    have.add(kind)
            if b.motion == "fall" and b.kind in VEHICLE and at is not None and "glass" not in have:
                fx.append({"kind": "glass", "at": round(at, 3), "spot": b.spot})
                have.add("glass")
        if big:
            shot["big"] = big
        if fx:
            shot["fx"] = fx
        if s.slowmo:
            shot["slowmo"] = True
        if i == 0:
            shot["fadeIn"] = 0.35
        if i == n - 1:
            shot["fadeOut"] = 0.9
        shots.append(shot)
        # the words
        stamp_end = t
        if s.stamp.strip():
            stamp_end = t + (lead + (a["words"][0][1] if a.get("words") else 0) if line else dur)
            captions.append({"start": round(t, 3), "end": round(stamp_end, 3), "text": s.stamp.strip(), "stamp": True})
        if line:
            at = t + lead
            clips.append({"at": round(at, 3), "path": a["path"]})
            words = [(w[0], at + w[1], at + w[2]) for w in written(s.line.strip(), a["words"])]
            parts = chunks(words)
            for k, (c0, c1, text) in enumerate(parts):
                c1 = min(c1, t + dur - (0.02 if i < n - 1 else 0.0))
                if s.red and k == len(parts) - 1:
                    c1 = t + dur  # the last red words stay through the fade
                captions.append({"start": round(max(c0, stamp_end), 3), "end": round(c1, 3), "text": text, **({"red": True} if s.red else {})})
        # the sounds: each walker's own footsteps, landing when his feet do
        near = CAMERA_NEAR.get(s.camera, 0.8)
        for k, actor in enumerate(s.actors):
            if actor.action in STRIDE and (actor.action != "carry" or actor.to):
                steps, arrive = step_times(actor, k, s, dur, shot["seed"])
                if steps:
                    cues.append({"sound": "footsteps", "at": round(t, 3), "volume": round(near * (1.0 if k == focus else 0.7), 2),
                                 "steps": steps, "surface": FLOOR.get(s.set, "concrete"), "pace": actor.action, "slow": bool(s.slowmo),
                                 "seed": int(shot["seed"]) * 7 + k})
                if actor.to == "door":
                    cues.append({"sound": "door", "at": round(t + (arrive if arrive is not None else dur - 0.7), 3), "volume": 0.8})
            if actor.action == "type":
                cues.append({"sound": "typing", "at": round(t + 0.2, 3), "volume": 0.6, "length": round(max(0.5, dur - 0.4), 3)})
        if any(th.kind == "alarm" for th in s.things) and not any(x.sound == "alarm" for x in s.sounds):
            cues.append({"sound": "alarm", "at": round(t + 0.12, 3), "volume": 0.9, "length": round(min(2.6, dur - 0.2), 3)})
        def cue(sound: str, at: float, volume: float = 0.9, length: float | None = None) -> None:
            if any(c["sound"] == sound and abs(c["at"] - at) < 0.3 for c in cues):
                return
            c = {"sound": sound, "at": round(max(0.0, at), 3), "volume": volume}
            if length:
                c["length"] = round(length, 3)
            cues.append(c)

        for actor, at in zip(s.actors, act_at):
            for sound, off in ACTION_SOUNDS.get(actor.action, ()):
                if off <= -9:
                    cue(sound, t + 0.05, 0.8)
                elif at is not None:
                    cue(sound, t + at + off, 1.0 if sound in ("impact", "crash") else 0.8, 0.8 if sound == "skid" else None)
        for b, at in zip(s.big, big_at):
            for sound, off in MOTION_SOUNDS.get(b.motion, ()):
                if off <= -9:
                    cue(sound, t + 0.2, 0.7)
                elif at is not None:
                    cue(sound, t + at + off, 1.0 if sound == "crash" else 0.85)
            if b.motion == "hang" and b.at is not None:
                cue("crack", t + b.at * dur, 0.9)
                cue("swoosh", t + b.at * dur + 0.1, 0.8)
        for f in fx:
            sound = FX_SOUNDS.get(f["kind"])
            if sound:
                start = t + f["at"]
                cue(sound, start, 0.7 if sound in LOOPING else 0.9, max(0.6, t + dur - start - 0.1) if sound in LOOPING else None)
        for snd in s.sounds:
            at = t + 0.15
            if snd.word and line:
                want = re.sub(r"[^a-z0-9]", "", snd.word.lower())
                hit = next((w for w in a["words"] if re.sub(r"[^a-z0-9]", "", w[0].lower()) == want), None)
                if hit:
                    at = t + lead + hit[1]
            if snd.sound == "footsteps" and any(x.action in STRIDE for x in s.actors):
                continue  # the walker's own steps are already there, on his feet
            if snd.sound == "footsteps":  # someone walking nearby: a few steps on this place's floor
                cues.append({"sound": "footsteps", "at": round(at, 3), "volume": 0.6, "steps": [round(0.571 * j, 3) for j in range(5)],
                             "surface": FLOOR.get(s.set, "concrete"), "pace": "walk", "slow": False, "seed": int(shot["seed"]) + 3})
                continue
            cue = {"sound": snd.sound, "at": round(at, 3), "volume": 0.85}
            if snd.sound == "alarm":
                cue["length"] = round(min(2.6, max(0.8, dur - (at - t) - 0.1)), 3)
            cues.append(cue)
        t += dur
    total = round(t, 3)
    parts = sorted({max(1, min(n, p.from_shot)): p for p in story.score}.items()) if story.score else []
    if parts:
        # the score follows the story: one section per part, from its shot to the next part's
        parts[0] = (1, parts[0][1])
        sections = []
        for k, (first, p) in enumerate(parts):
            start = shots[first - 1]["start"]
            end = shots[parts[k + 1][0] - 1]["start"] if k + 1 < len(parts) else total
            if sections and sections[-1]["mood"] == p.mood and sections[-1]["act"] == SCORE_ACT[p.energy]:
                sections[-1]["end"] = end
            elif end > start:
                sections.append({"start": start, "end": end, "mood": p.mood, "act": SCORE_ACT[p.energy], "quiet": []})
    else:
        ending = shots[max(0, int(n * 0.75))]["start"] if n > 4 and story.end_mood != story.mood else total
        sections = [{"start": 0.0, "end": ending, "mood": story.mood, "act": "loop", "quiet": []}]
        if ending < total:
            sections.append({"start": ending, "end": total, "mood": story.end_mood, "act": "resolve", "quiet": []})
    shown = captions if mode == "on" else [c for c in captions if c.get("stamp")] if mode == "stamps" else []
    props = {"fps": FPS, "duration": total, "vertical": vertical, "watermark": watermark, "seed": seed, "cast": cast, "shots": shots,
             "captions": shown, "dof": True}
    return props, clips, cues, sections
