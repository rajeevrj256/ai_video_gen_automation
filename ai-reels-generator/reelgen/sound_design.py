"""Sound for every visual action in a long video, placed automatically.

Claude places a few sound effects on words (media.resolve_cues). This module adds the layer
an editor would: each thing that moves on screen gets its sound, timed to the animation.

  beat changes         -> the transition sound of this video's look (whoosh, glitch, swish...)
  items appearing      -> pops (timeline points, steps, icons)
  a number counting up -> clicks, then a ding when it lands
  scene actors         -> whoosh (enter/flee), impact (drop/fall), rumble (shake),
                          heartbeat (pulse), pops (multiply), swish (spin/orbit)
  3D objects           -> a flyby when something flies, a whoosh otherwise
  the hook             -> a whoosh/glitch on every cut, a glitch into the video

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
    # The impact's boom and hit sounds were removed at the user's request (silent now).
    return out


def design(props: dict, transition: str) -> list[tuple[str, float, float]]:
    """All automatic sounds for the video, as (name, time in seconds, volume)."""
    events: list[tuple[str, float, float]] = []
    t_sound, t_vol = TRANSITION_SOUND.get(transition, TRANSITION_SOUND["whip"])
    hook = props.get("hook") or {}
    for i, shot in enumerate(hook.get("shots", [])):
        if i:
            events.append(("whoosh" if i % 2 else "glitch", shot["start"] - 0.05, 0.3))
        events += _visual_events(shot["visual"], shot["start"], shot["duration"])
    if hook.get("shots"):
        events.append(("glitch", hook["duration"] - 0.45, 0.3))
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
        last[name] = at
        out.append((name, round(at, 3), vol))
    return out
