"""Every long video gets its own look and sound, so the channel never feels templated.

What stays the same (the brand): the font family, the line-icon style, the animation quality,
the audio levels and the editing rules. What changes per video: the colour palette, the
backdrop style, the transition style, the hook's trailer track, the music (mood from the
story, plus its own seed: key, tempo, progression and patterns) and the sound families.

`pick_look` avoids whatever the last few videos used; `remember` stores this video's choices
in <output>/variety.json. `recent_block` tells the script writer what was used lately, so it
can pick a different music mood and hook style when the story allows.
"""

from __future__ import annotations

import json
import random
import threading
from pathlib import Path

from .config import Config

KEEP = 6  # how many recent videos to remember
_lock = threading.Lock()

# Each palette: chapter colour worlds (a, b = backdrop gradient) + accents, and a hook grade.
PALETTES = {
    "midnight-gold": {"worlds": [("#0B1E3F", "#1B4F72"), ("#14213D", "#3D5A80"), ("#1F1F1F", "#4A4E69")], "accents": ["#FFD60A", "#FFB74D", "#FFE082"]},
    "neon-noir": {"worlds": [("#10002B", "#3C096C"), ("#03071E", "#370617"), ("#0B090A", "#2B2D42")], "accents": ["#F72585", "#4CC9F0", "#B5179E"]},
    "forest-amber": {"worlds": [("#0E2E24", "#1E6B4E"), ("#1B2A1E", "#3A5A40"), ("#13241D", "#2D6A4F")], "accents": ["#FFB703", "#E9C46A", "#F4A261"]},
    "crimson-cream": {"worlds": [("#3A0E14", "#8E2430"), ("#2B0A0F", "#6A1B24"), ("#1D0B0E", "#58181F")], "accents": ["#FFE8C2", "#FFD166", "#F8EDEB"]},
    "arctic-teal": {"worlds": [("#051923", "#003554"), ("#0A2E36", "#1B4965"), ("#08212B", "#0F4C5C")], "accents": ["#5EEAD4", "#A7F3D0", "#E0FBFC"]},
    "desert-dusk": {"worlds": [("#2D1E2F", "#6D3B47"), ("#3D2C2E", "#8C5E58"), ("#231A24", "#5C3D4E")], "accents": ["#F9C74F", "#F8961E", "#F3722C"]},
    "ink-lime": {"worlds": [("#111111", "#2B2B2B"), ("#161A1D", "#343A40"), ("#0F0F12", "#262630")], "accents": ["#B8F200", "#DDFF55", "#9EF01A"]},
    "royal-coral": {"worlds": [("#1A1446", "#3A2C85"), ("#221B55", "#4B3F9E"), ("#140F3A", "#2E2570")], "accents": ["#FF7F6B", "#FFB4A2", "#FFD6A5"]},
    "ocean-sunset": {"worlds": [("#023047", "#126782"), ("#0B3954", "#087E8B"), ("#03256C", "#2541B2")], "accents": ["#FB8500", "#FFB703", "#FF6B6B"]},
    "slate-mint": {"worlds": [("#1E2A38", "#3E5068"), ("#222831", "#393E46"), ("#1B262C", "#0F4C75")], "accents": ["#80ED99", "#57CC99", "#C7F9CC"]},
}
BACKDROPS = ("blobs", "grid", "rays", "waves", "dots", "paper")
TRANSITIONS = ("smooth", "whip", "zoom", "glitch", "flash", "slide")
TRAILERS = ("spy-pulse", "ticking-clock", "dark-pulse", "glitch-drive")


def _path(cfg: Config) -> Path:
    return cfg.output_dir / "variety.json"


def recent(cfg: Config) -> list[dict]:
    path = _path(cfg)
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    except (OSError, json.JSONDecodeError):
        return []


def _fresh(options, used: list[str], rng: random.Random) -> str:
    left = [o for o in options if o not in used]
    return rng.choice(left or list(options))


def pick_look(cfg: Config, seed: int) -> dict:
    """Palette, backdrop and transition style unlike the last few videos."""
    rng = random.Random(seed)
    past = recent(cfg)
    palette = _fresh(list(PALETTES), [p.get("palette") for p in past[-4:]], rng)
    return {
        "palette": palette,
        "worlds": [list(w) for w in PALETTES[palette]["worlds"]],
        "accents": PALETTES[palette]["accents"],
        "backdrop": _fresh(BACKDROPS, [p.get("backdrop") for p in past[-3:]], rng),
        "transition": _fresh(TRANSITIONS, [p.get("transition") for p in past[-3:]], rng),
        "seed": seed,
    }


def fresh_trailer(cfg: Config, wanted: str, seed: int) -> str:
    """Claude's trailer style, unless the last two videos already used it."""
    used = [p.get("hook_music") for p in recent(cfg)[-2:]]
    return wanted if wanted in TRAILERS and wanted not in used else _fresh(TRAILERS, used, random.Random(seed))


def recent_block(cfg: Config) -> str:
    past = recent(cfg)[-3:]
    if not past:
        return ""
    moods = ", ".join(p.get("mood", "?") for p in past)
    hooks = ", ".join(p.get("hook_music", "?") for p in past)
    forms = [p["form"] for p in recent(cfg)[-4:] if p.get("form")]
    return (f"\n- Variety: the last videos used music moods {moods} and hook tracks {hooks}. Pick a different "
            "mood and hook track unless this story clearly needs the same one."
            + (f"\n- The last videos were told as: {', '.join(forms)}. Use a different story form unless this "
               "material clearly fits only one of those." if forms else ""))


def remember(cfg: Config, look: dict, mood: str, hook_music: str, form: str = "", first_break: str = "") -> None:
    with _lock:
        past = recent(cfg)
        past.append({"palette": look["palette"], "backdrop": look["backdrop"], "transition": look["transition"],
                     "mood": mood, "hook_music": hook_music, "form": form, "break": first_break})
        path = _path(cfg)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(past[-KEEP:], indent=1), encoding="utf-8")


PHOTOS_KEEP = 400  # background photos used lately, never picked again for a new video


def used_photos(cfg: Config) -> set[int]:
    path = cfg.output_dir / "backdrop_photos.json"
    try:
        return set(json.loads(path.read_text(encoding="utf-8"))) if path.exists() else set()
    except (OSError, json.JSONDecodeError):
        return set()


def remember_photos(cfg: Config, ids: set[int]) -> None:
    with _lock:
        path = cfg.output_dir / "backdrop_photos.json"
        old = sorted(used_photos(cfg))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps((old + sorted(ids - set(old)))[-PHOTOS_KEEP:]), encoding="utf-8")
