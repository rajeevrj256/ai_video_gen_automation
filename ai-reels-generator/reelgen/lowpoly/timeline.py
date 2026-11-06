"""From the written story and the recorded narration to the editor's props: each shot lasts its line plus a breath
(a silent stamp beat ~1.6 s), the narrator's words become captions two or three at a time (a stamp takes the
caption's place while it shows, as in the original), the last line is red and fades out, and the world's sounds
are put on their frames (footsteps under walks, the alarm, typing, Claude's own sounds on their words)."""
from __future__ import annotations

import re

from .story import HERO, Story, _key, editor_design

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
        actors = []
        for actor in s.actors:
            d = {"who": "hero" if actor.who == "hero" else _key(actor.who), "action": actor.action, "expression": actor.expression,
                 "spot": actor.spot, "facing": actor.facing, "hold": actor.hold, "covered": actor.covered}
            if actor.to:
                d["to"] = actor.to
            actors.append(d)
        focus = next((k for k, x in enumerate(actors) if x["who"] == "hero"), 0)
        shot = {"start": round(t, 3), "duration": round(dur, 3), "set": s.set, "light": s.light, "camera": s.camera, "actors": actors,
                "things": [th.model_dump() | {"spot": "center"} for th in s.things], "focus": focus, "seed": seed + i * 13}
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
        # the sounds
        for actor in s.actors:
            if actor.action in ("walk", "run", "jog"):
                cues.append({"sound": "footsteps", "at": round(t + 0.1, 3), "volume": 0.8 if actor.action == "walk" else 1.0,
                             "length": round(max(0.5, dur - 0.25), 3)})
                if actor.to == "door":
                    cues.append({"sound": "door", "at": round(t + dur - 0.7, 3), "volume": 0.8})
            if actor.action == "type":
                cues.append({"sound": "typing", "at": round(t + 0.2, 3), "volume": 0.6, "length": round(max(0.5, dur - 0.4), 3)})
        if any(th.kind == "alarm" for th in s.things) and not any(x.sound == "alarm" for x in s.sounds):
            cues.append({"sound": "alarm", "at": round(t + 0.12, 3), "volume": 0.9, "length": round(min(2.6, dur - 0.2), 3)})
        for snd in s.sounds:
            at = t + 0.15
            if snd.word and line:
                want = re.sub(r"[^a-z0-9]", "", snd.word.lower())
                hit = next((w for w in a["words"] if re.sub(r"[^a-z0-9]", "", w[0].lower()) == want), None)
                if hit:
                    at = t + lead + hit[1]
            cue = {"sound": snd.sound, "at": round(at, 3), "volume": 0.85}
            if snd.sound == "alarm":
                cue["length"] = round(min(2.6, max(0.8, dur - (at - t) - 0.1)), 3)
            cues.append(cue)
        t += dur
    total = round(t, 3)
    ending = shots[max(0, int(n * 0.75))]["start"] if n > 4 and story.end_mood != story.mood else total
    sections = [{"start": 0.0, "end": ending, "mood": story.mood, "act": "loop", "quiet": []}]
    if ending < total:
        sections.append({"start": ending, "end": total, "mood": story.end_mood, "act": "resolve", "quiet": []})
    shown = captions if mode == "on" else [c for c in captions if c.get("stamp")] if mode == "stamps" else []
    props = {"fps": FPS, "duration": total, "vertical": vertical, "watermark": watermark, "seed": seed, "cast": cast, "shots": shots,
             "captions": shown, "dof": True}
    return props, clips, cues, sections
