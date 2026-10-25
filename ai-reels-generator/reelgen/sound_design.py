"""Sound for every visual action in a long video, placed automatically.

Claude places a few sound effects on words (media.resolve_cues). This module adds the layer
an editor would: each thing that moves on screen gets its sound, timed to the animation.

  beat changes         -> the transition sound of this video's look (whoosh, glitch, swish...)
  items appearing      -> pops (timeline points, steps, icons)
  a number counting up -> clicks, then a ding when it lands
  scene actors         -> whoosh (enter/flee), impact (drop/fall), rumble (shake),
                          heartbeat (pulse), pops (multiply), swish (spin/orbit)
  3D objects           -> a flyby when something flies, a whoosh otherwise
  the hook             -> a whoosh/glitch on every cut, a glitch into the video (the cinematic hook: its own
                          sounds from cinehook.py, and nothing in its silence)

Timings mirror the animations in remotion/src/long (Visuals.tsx, Scene.tsx); scene actor
times are computed here and passed to the editor, so they can't drift apart.
"""

from __future__ import annotations

FPS = 30
TRANSITION_SOUND = {"smooth": ("shimmer", 0.2), "whip": ("whoosh", 0.3), "zoom": (None, 0.0),
                    "glitch": ("glitch", 0.22), "flash": ("swish", 0.3), "slide": ("swish", 0.28)}
ACTOR_SOUND = {"enter-left": "whoosh", "enter-right": "whoosh", "walk-across": "swish", "approach": None,
               "flee": "whoosh", "drop-in": "impact", "fall": "impact", "shake": "rumble", "grow": None,
               "shrink": "swish", "pulse": "heartbeat", "spin": "swish", "orbit": "swish", "rise": None,
               "multiply": "pop"}
MIN_GAP = 0.18  # two sounds of the same kind closer than this sound like one smeared sound


def actor_times(n: int, duration: float) -> list[float]:
    """When each scene actor starts acting, in seconds from the beat's start."""
    step = min(0.9, max(0.3, duration * 0.55 / max(1, n)))
    return [round(0.25 + i * step, 3) for i in range(n)]


def impact_time(duration: float) -> float:
    return round(min(0.6, duration * 0.3), 3)


def _visual_events(v: dict, start: float, duration: float) -> list[tuple[str, float, float]]:
    """(sound, time, volume) for one visual's own animation."""
    frames = duration * FPS
    kind = v.get("type")
    out: list[tuple[str, float, float]] = []
    items = v.get("items") or []
    if kind == "timeline" and items:
        span = min(max(20, frames * 0.6), 75)
        out += [("pop", start + (4 + (span - 4) * ((i + 0.5) / len(items))) / FPS, 0.3) for i in range(len(items))]
    elif kind == "steps" and items:
        span = min(max(20, frames * 0.55), 75)
        out += [("pop", start + (4 + span * i / len(items)) / FPS, 0.3) for i in range(len(items))]
    elif kind == "icons":
        out += [("pop", start + i * 6 / FPS, 0.28) for i in range(len(v.get("icons") or [1]))]
    elif kind == "stat":
        out += [("click", start + 0.15 + i * 0.16, 0.22) for i in range(4)] + [("ding", start + 0.95, 0.3)]
    elif kind == "compare":
        out += [("swish", start + 0.1, 0.25), ("swish", start + 0.45, 0.25)]
    elif kind in ("keyword", "title"):
        out.append(("click", start + 0.05, 0.3))
    elif kind == "quote":
        out.append(("typing", start + 0.1, 0.18))
    elif kind == "model3d":
        out.append(("flyby" if v.get("scene") == "sky" else "whoosh", start + 0.1, 0.35))
    elif kind == "scene":
        for a in v.get("actors") or []:
            sound = ACTOR_SOUND.get(a.get("action", ""), "pop")
            if sound:  # None: that action's sound was removed
                out.append((sound, start + float(a.get("at", 0.3)), 0.32 if sound != "impact" else 0.4))
            if a.get("action") == "multiply":
                out += [("pop", start + float(a.get("at", 0.3)) + k * 0.12, 0.2) for k in range(1, 4)]
    elif kind in ("flow", "checklist", "receipt", "dates"):  # the Briefing template's builds (long/brief/Brief.tsx landAt)
        n = len(items) or 1
        first, span = (10, max(20, frames * 0.7)) if kind == "checklist" else (6, max(20, frames * (0.42 if kind == "dates" else 0.7)))
        out += [("pop", start + (first + (span - first) * i / n + (8 if kind == "checklist" else 0)) / FPS, 0.28) for i in range(n)]
    elif kind == "terminal":
        out.append(("typing", start + 0.2, 0.18))
    elif kind == "card":
        out.append(("pop", start + 14 / FPS, 0.3))
    elif kind == "scale":
        out += [("swish", start + 0.25, 0.22), ("ding", start + max(30, frames * 0.5) / FPS, 0.28)]
    elif kind == "grid":
        out += [("click", start + 0.2 + i * 0.2, 0.18) for i in range(4)]
    elif kind == "meme":
        out += _meme_events(v, start, duration)
    # The impact's boom and hit sounds were removed at the user's request (silent now).
    return out


# A reaction face's sound, at its second beat (the bottom text, ~a third into the beat; Meme.tsx `later`).
FACE_SOUND = {"shocked": ("scratch", 0.0), "crying": ("sad", 0.32), "laughing": ("boing", 0.32), "side-eye": ("click", 0.3),
              "mind-blown": ("shimmer", 0.3), "sweating": ("tick", 0.05), "angry": ("rumble", 0.3), "confused": ("boing", 0.3),
              "smug": ("ding", 0.32)}


def _meme_events(v: dict, start: float, duration: float) -> list[tuple[str, float, float]]:
    """The meme's own sounds, on its reveals in remotion/src/long/Meme.tsx (keep the fractions in step)."""
    fmt, d, f = v.get("meme"), duration, duration * FPS
    if v.get("src"):  # the user's own meme file, or a real template (memeweb.py): a pop as each of its boxes lands
        n = len(v.get("webBoxes") or [])
        if n and not v.get("clipSeconds"):
            return [("pop", start + d * (0.04 + 0.5 * i / n), 0.28) for i in range(n)]
        return [("pop", start + 0.05, 0.3)]
    if fmt == "two-buttons":
        return [("pop", start + 6 / FPS, 0.28), ("pop", start + 12 / FPS, 0.28), ("tick", start + 0.6, 0.16)]
    if fmt == "nope-yep":
        return [("click", start + 0.05, 0.3), ("ding", start + d * 0.4, 0.3)]
    if fmt == "distracted":
        return [("swish", start + d * 0.25, 0.28), ("boing", start + d * 0.25 + 0.3, 0.26)]
    if fmt in ("brain", "panik-kalm"):
        n = max(2, min(4 if fmt == "brain" else 3, len(v.get("labels") or [])))
        first, span = (0.04, 0.74) if fmt == "brain" else (0.03, 0.7)
        at = [start + d * (first + span * i / n) for i in range(n)]
        if fmt == "brain":
            return [("pop", t, 0.26) for t in at[:-1]] + [("shimmer", at[-1], 0.32)]
        return [("pop", at[0], 0.26)] + [("ding" if i % 2 else "scratch", t, 0.28) for i, t in enumerate(at[1:], 1)]
    if fmt == "this-is-fine":
        return [("pop", start + d * 0.35, 0.28)]
    if fmt == "expectation-reality":
        return [("ding", start + 0.05, 0.22), ("sad", start + d * 0.42, 0.3)]
    if fmt == "nobody-me":
        return [("pop", start + d * 0.3, 0.28), ("boing", start + d * 0.3 + 0.35, 0.24)]
    if fmt == "stonks":
        return [("cash", start + 0.4, 0.3)]
    if fmt == "not-stonks":
        return [("sad", start + d * 0.45, 0.3)]
    if fmt == "change-my-mind":
        return [("click", start + 0.2, 0.3)]
    if fmt == "plan":
        return [("pop", start + d * (0.03 + i * 0.2), 0.26) for i in range(3)] + [("scratch", start + d * 0.63, 0.3)]
    if fmt == "pointing":
        return [("pop", start + 2 / FPS, 0.26), ("pop", start + 8 / FPS, 0.26)]
    if fmt == "starter-pack":
        n = min(4, max(0, len(v.get("labels") or []) - 1))
        return [("pop", start + (6 + i * max(4, f * 0.12)) / FPS, 0.26) for i in range(n)]
    sound = FACE_SOUND.get(v.get("face") or "shocked")
    return [(sound[0], start + d * sound[1] + 0.02, 0.3)] if sound else []


def design(props: dict, transition: str) -> list[tuple[str, float, float]]:
    """All automatic sounds for the video, as (name, time in seconds, volume)."""
    events: list[tuple[str, float, float]] = []
    t_sound, t_vol = TRANSITION_SOUND.get(transition, TRANSITION_SOUND["whip"])
    hook = props.get("hook") or {}
    cine = bool(hook.get("cine"))  # the cinematic hook brings its own cut sounds and ends in silence (cinehook.py)
    for i, shot in enumerate(hook.get("shots", [])):
        if i and not cine:
            events.append(("whoosh" if i % 2 else "glitch", shot["start"] - 0.05, 0.3))
        events += _visual_events(shot["visual"], shot["start"], shot["duration"])
    if hook.get("shots") and not cine:
        events.append(("glitch", hook["duration"] - 0.45, 0.3))
    quiet = (hook["duration"] - hook.get("drop", 0), hook["duration"]) if cine else (0.0, 0.0)
    prev_chapter = None
    for b in props["beats"]:
        if b["chapter"] == prev_chapter and t_sound:  # chapter cards bring their own whoosh
            events.append((t_sound, b["start"] - 0.08, t_vol))
        prev_chapter = b["chapter"]
        events += _visual_events(b["visual"], b["start"], b["duration"])
    # Keep them from piling up: one sound of a kind per MIN_GAP, and never on top of a word cue.
    taken = [c["at"] for c in props.get("cues", [])]
    out, last = [], {}
    for name, at, vol in sorted(events, key=lambda e: e[1]):
        if at < 0 or at - last.get(name, -9) < MIN_GAP or any(abs(at - c) < 0.25 for c in taken):
            continue
        if quiet[0] <= at < quiet[1]:  # nothing breaks the hook's silence
            continue
        last[name] = at
        out.append((name, round(at, 3), vol))
    return out
