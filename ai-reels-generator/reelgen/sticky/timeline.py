"""From the written film to the editor's props (remotion/src/sticky/types.ts), the sound cues and the music's sections.

Every shot holds long enough to read its words (a caption, a whisper, the bubbles, a chat); the sounds of a shot are
timed with the same formulas the editor animates with (a chat bubble pops in as it appears, a calendar tick is
scribbled as it is drawn), so the sound lands on the picture."""
from __future__ import annotations

from .film import ACCENTS, COLOURS, Film, FShot

FPS = 30
MAX_SHOT = 9.0


def _words(lines) -> int:
    return sum(len(str(x).split()) for x in lines)


def hold(s: FShot, act: str) -> float:
    """How long the shot needs: Claude's length, at least the time to read what is on it."""
    need = s.seconds
    if s.caption:
        need = max(need, _words(s.caption) / 2.6 + (1.8 if s.kind == "card" else 1.2))
    if s.whisper:
        need = max(need, len(s.whisper) / 16 + 1.1)
    if s.bubbles:
        need = max(need, len(s.bubbles) * 1.0 + _words(b.text for b in s.bubbles) / 3.2 + 0.6)
    if s.kind == "phone" and s.phone and s.phone.mode == "chat":
        need = max(need, len(s.phone.messages) * 0.7 + len(s.phone.typing) / 14 + 1.2)
    if s.kind == "object" and s.object:
        need = max(need, len(s.object.lines) * 0.7 + 1.6)
    if s.notes:
        need = max(need, 2.0 + len(s.notes) * 0.25)
    if act == "title":
        need = max(need, 6.5)
    return round(min(MAX_SHOT if act != "title" else 8.0, max(1.5, need)), 2)


def _shot(film: Film, s: FShot, act: str, start: float, dur: float) -> dict:
    hero = film.cast[0].id
    others = [a.id for a in s.actors if a.id != hero]
    out: dict = {"start": round(start, 3), "duration": dur, "kind": "title" if act == "title" else s.kind, "act": act,
                 "transition": s.transition, "camera": s.camera, "grade": s.grade}
    if s.kind in ("scene", "face"):
        out.update(set=s.set, light=s.light)
        out["actors"] = [{k: v for k, v in {
            "id": a.id, "x": a.x, "pose": a.pose, "face": a.face, "facing": a.facing, "to": a.to if a.to >= 0 else None,
            "prop": a.prop, "glow": a.glow, "tear": a.tear, "sweat": a.sweat,
            "face2": a.face2 or None, "faceAt": a.face_at if a.face2 else None}.items() if v is not None} for a in s.actors]
        if s.shadow:
            out["shadow"] = {"x": s.shadow.x, "size": s.shadow.size, "act": s.shadow.act,
                             **({"copy": s.shadow.copy_of} if s.shadow.copy_of else {})}
        if s.kind == "face":
            out["focus"] = (s.actors[0].id if s.actors else hero)
    if s.clock:
        out["clock"] = s.clock
    if s.kind == "phone":
        p = s.phone
        out["phone"] = {"mode": p.mode if p else "lock", "title": p.title if p else "", "time": p.time if p else "",
                        "typing": p.typing if p else "", "items": p.items if p else [], "seen": bool(p and p.seen),
                        "messages": [m.model_dump() for m in (p.messages if p else [])]}
    if s.kind == "calendar" and s.calendar:
        out["calendar"] = s.calendar.model_dump()  # continuity added by `_calendars`
    if s.kind == "object" and s.object:
        out["object"] = s.object.model_dump()
    if s.kind == "graph" and s.graph:
        out["graph"] = s.graph.model_dump()
    caption = s.caption or (film.thesis if act == "thesis" and s.kind == "card" else [])
    if caption and act != "title":
        # a calendar or a paper fills the top of the frame: its words go below it (they covered the month's name)
        pos = ("center" if s.kind == "card" else "bottom" if s.kind == "calendar"
               else "top" if s.kind == "object" and s.object and s.object.kind == "drawing" else "bottom" if s.kind == "object" else s.caption_pos)
        out["caption"] = {"lines": caption[:3], "pos": pos}
    if s.whisper:
        out["whisper"] = {"text": s.whisper, "x": s.whisper_x, "y": s.whisper_y}
    if s.bubbles:
        out["bubbles"] = [{"who": hero if b.me else (others[0] if others else hero), "text": b.text} for b in s.bubbles]
    for k in ("notes", "pills"):
        if getattr(s, k):
            out[k] = getattr(s, k)
    if s.stamp:
        out["stamp"] = s.stamp
    if s.meter:
        out["meter"] = s.meter[:2]
    if s.day:
        out["day"] = s.day
    if s.time:
        out["time"] = s.time
    return out


def _calendars(shots: list[dict]) -> None:
    """One wall calendar per month through the whole film: a later calendar of the same month keeps every tick and
    scribble already shown and never has fewer ticks (Claude's later calendars restarted, or skipped days the earlier
    one had ticked). `before`/`beforeMarks` tell the editor what is already drawn, so only new days are animated."""
    seen: dict[str, dict] = {}
    for sh in shots:
        c = sh.get("calendar")
        if not c:
            continue
        key = c["month"].strip().upper()
        prev = seen.get(key)
        if prev:
            c["checks"] = max(c["checks"], prev["checks"])
            c["marks"] = sorted(set(c.get("marks") or []) | set(prev["marks"]))
            c["before"], c["beforeMarks"] = prev["checks"], list(prev["marks"])
        seen[key] = {"checks": c["checks"], "marks": list(c.get("marks") or [])}


def _cues(s: FShot, at: float, dur: float, cal: dict | None = None) -> list[dict]:
    """The automatic sounds of one shot, timed like the editor animates it."""
    c: list[dict] = []
    add = lambda name, t, vol=1.0, length=None: c.append({"sound": name, "at": round(at + max(0.0, t), 3), "volume": vol,  # noqa: E731
                                                           **({"length": round(length, 3)} if length else {})})
    if s.kind == "phone" and s.phone:
        p = s.phone
        if p.mode == "chat":
            each = max(0.35, min(1.1, dur * 0.55 / max(1, len(p.messages))))
            for i, m in enumerate(p.messages):
                add("send" if m.me else "ding", i * each * 0.6, 0.7 if m.me else 0.8)
            if p.typing:
                start = len(p.messages) * each * 0.6 + 0.3
                add("typing", start, 0.6, max(0.4, dur * 0.85 - start))
        elif p.mode == "feed":
            k = 0.4
            while k < dur - 0.3:
                add("swoosh", k, 0.35)
                k += 1.25
        elif p.mode == "notif":
            for i, _ in enumerate(p.items):
                add("notify", 0.2 + i * 0.35, 0.8)
        elif p.mode == "dialog":
            add("tap", dur * 0.7, 0.9)
        elif p.mode == "call":
            add("buzz", 0.0, 0.8, dur)
    elif s.kind == "clock":
        add("tick", 0.1, 0.6, min(dur, 2.0))
    elif s.kind == "calendar" and s.calendar:
        # one scribble per day ticked or crossed during the shot, at the times CalendarInsert draws them
        cal = cal or {}
        before = cal.get("before", max(0, s.calendar.checks - 7))
        fresh = max(0, cal.get("checks", s.calendar.checks) - before) + len(set(cal.get("marks", [])) - set(cal.get("beforeMarks", [])))
        span = max(0.6, dur * 0.7)
        for i in range(min(fresh, 12)):
            add("scribble", 0.3 + (span - 0.3) * i / max(1, fresh), 0.6)
    elif s.kind == "object":
        add("page", 0.0, 0.7)
    if s.bubbles:
        each = max(0.9, dur * 0.75 / max(1, len(s.bubbles)))
        for i, _ in enumerate(s.bubbles):
            add("pop", i * each, 0.8)
    if s.shadow:  # nothing under the whisper itself: it has to be heard
        if s.shadow.act in ("appear", "grow", "loom"):
            add("swell", 0.0, 0.7 if s.shadow.act == "appear" else 0.8)
        elif s.shadow.act == "dissolve":
            add("chime", 0.3, 0.8)
    for i, _ in enumerate(s.notes):
        add("tap", 0.1 + (max(0.5, dur * 0.7) - 0.1) * i / max(1, len(s.notes)), 0.6)
    for i, _ in enumerate(s.pills):
        add("notify", 0.2 + i * 0.4, 0.6)
    if s.stamp:
        add("bell", 0.15, 0.9)
    for a in s.actors:
        if a.pose in ("walk", "run", "climb"):
            add("footsteps", 0.0, 0.55 if a.pose != "run" else 0.75, dur)
            break
    if any(a.pose == "shake" for a in s.actors):
        add("heartbeat", 0.0, 0.7, dur)
    for snd in s.sounds:  # Claude's own sounds of the world and the feeling
        add(snd.sound, min(snd.at, max(0.0, dur - 0.2)), 0.85, dur - snd.at if snd.sound in ("rain", "typing", "footsteps", "tick", "heartbeat") else None)
    return c


def _dedupe(cues: list[dict], gap: float = 0.6) -> list[dict]:
    """One sound once: Claude's own cue and the automatic one for the same moment (a call's buzz, the rumble under
    the inner voice) used to pile up, three rumbles in half a second. Of the same sound within `gap` s, the loudest
    (then the longest) is kept."""
    kept: list[dict] = []
    for c in sorted(cues, key=lambda c: (c["sound"], c["at"])):
        last = kept[-1] if kept and kept[-1]["sound"] == c["sound"] else None
        if last and c["at"] - last["at"] < gap:
            if (c.get("volume", 1), c.get("length", 0)) > (last.get("volume", 1), last.get("length", 0)):
                kept[-1] = {**c, "at": last["at"]}
            continue
        kept.append(c)
    return sorted(kept, key=lambda c: c["at"])


def build(film: Film) -> tuple[dict, list[dict], list[dict]]:
    """(props, cues, sections): the editor's props, every sound cue in film seconds, and one music section per act
    (with the spans its music drops away)."""
    shots, cues, sections = [], [], []
    t = 0.0
    for act in film.acts:
        a0 = t
        quiet = []
        for s in act.shots:
            dur = hold(s, act.act)
            shots.append(_shot(film, s, act.act, t, dur))
            if shots[-1].get("calendar"):
                _calendars(shots)
            cues += _cues(s, t, dur, shots[-1].get("calendar"))
            if s.quiet:
                quiet.append([round(t, 3), round(t + dur, 3)])
            t += dur
        if t > a0:
            sections.append({"act": act.act, "mood": act.mood, "start": round(a0, 3), "end": round(t, 3), "quiet": quiet})
    if not shots or shots[-1]["kind"] != "title":  # every film ends on its title card
        shots.append({"start": round(t, 3), "duration": 6.5, "kind": "title", "act": "title", "transition": "fade"})
        sections.append({"act": "title", "mood": "emotional", "start": round(t, 3), "end": round(t + 6.5, 3), "quiet": []})
        t += 6.5
    cues.append({"sound": "chime", "at": round(shots[-1]["start"] + 1.0, 3), "volume": 0.6})
    cues = _dedupe(cues)
    m = film.meter
    props = {
        "title": film.title.strip(), "tagline": (film.tagline + ["", ""])[:2], "accent": ACCENTS[film.accent],
        "meter": {"kind": m.kind, "labels": m.labels[:2], "unit": m.unit},
        "cast": [{"id": c.id, "name": c.name, "tone": c.tone, "wear": c.wear, "color": COLOURS[c.color], "kid": c.kid,
                  **({"extra": c.extra} if c.extra != "none" else {})} for c in film.cast],
        "shots": shots, "fps": FPS, "duration": round(t, 3),
    }
    return props, cues, sections


def repair(film: Film) -> list[str]:
    """Fix what the editor can't draw, in code: unknown cast ids dropped, inserts missing their content turned into a
    card or a plain scene. Returns notes for the report."""
    notes = []
    ids = {c.id for c in film.cast}
    if not film.cast:
        raise ValueError("The film has no cast.")
    for act in film.acts:
        for s in act.shots:
            before = len(s.actors)
            s.actors = [a for a in s.actors if a.id in ids][:3]
            if len(s.actors) < before:
                notes.append(f"{act.act}: dropped an actor not in the cast")
            if s.shadow and s.shadow.copy_of and s.shadow.copy_of not in ids:
                s.shadow.copy_of = ""
            need = {"phone": s.phone, "calendar": s.calendar, "object": s.object, "graph": s.graph}
            if s.kind in need and need[s.kind] is None:
                notes.append(f"{act.act}: a {s.kind} shot without its {s.kind}; shown as a scene")
                s.kind = "scene" if s.actors else "card"
            if s.kind == "scene" and not s.actors and not s.stamp and not s.caption and s.set == "void":
                s.kind = "card"
    return notes
