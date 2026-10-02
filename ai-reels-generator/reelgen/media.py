"""The media library: sound effects, background music and 3D models the editor can use.

Built in (synthesised in code, always there):
- sound effects in `sfx.CUE_SOUNDS` (sword, riser, heartbeat, ...)
- three quiet music beds (calm, tension, playful), used only when no music was added

Added by the user (from the app's Settings > Media library, or copied into the folder):
- assets/sfx/       .mp3/.wav/.ogg sound effects, e.g. from pixabay.com/sound-effects
- assets/music/     .mp3/.wav/.ogg background tracks
- assets/models3d/  .glb 3D models, e.g. a plane

A file's name is its description, so name files for what they are: Pixabay's own names
("sword-slash-swoosh-12345.mp3", "mysterious-cinematic-ambient-5678.mp3") already work.
Claude reads the list, picks sounds for the words that deserve them and a track that fits
the video; `resolve_cues` turns its picks into times on the timeline.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .config import PROJECT_ROOT, Config
from .sfx import CUE_SOUNDS, RATE, _write

SFX_DIR = PROJECT_ROOT / "assets" / "sfx"
MODELS_DIR = PROJECT_ROOT / "assets" / "models3d"
AUDIO_TYPES = {".mp3", ".wav", ".ogg", ".m4a"}
MODEL_TYPES = {".glb"}
KINDS = ("sfx", "music", "models3d")

# How loud each cue is, before the file's own level.
VOLUMES = {"soft": 0.35, "medium": 0.6, "strong": 0.9}
UPLOADED_GAIN = 0.55  # downloaded effects are mastered loud; built-ins are already quiet
HOOK_CUES, SCENE_CUES, TOTAL_CUES = 4, 2, 9  # most per hook, per later scene, per Short


@dataclass
class Item:
    name: str  # what Claude writes to pick it
    about: str  # what it sounds or looks like
    path: Path | None  # None = built in, made on demand


def folder(cfg: Config, kind: str) -> Path:
    return {"sfx": SFX_DIR, "music": cfg.music_dir, "models3d": MODELS_DIR}[kind]


def slug(name: str) -> str:
    """'Sword Slash Swoosh-12345.mp3' -> 'sword-slash-swoosh'. Pixabay's trailing ids are dropped."""
    words = re.findall(r"[a-z]+|\d+", Path(name).stem.lower())
    while words and words[-1].isdigit() and len(words) > 1:
        words.pop()
    return "-".join(words)[:60] or "file"


def _files(cfg: Config, kind: str) -> list[Item]:
    root = folder(cfg, kind)
    types = MODEL_TYPES if kind == "models3d" else AUDIO_TYPES
    items, seen = [], set()
    for path in sorted(root.glob("*")) if root.exists() else []:
        if path.suffix.lower() not in types:
            continue
        name = slug(path.name)
        while name in seen:
            name += "-2"
        seen.add(name)
        items.append(Item(name, name.replace("-", " "), path))
    return items


def sounds(cfg: Config) -> list[Item]:
    built = [Item(n, about, None) for n, (_, _, _, about) in CUE_SOUNDS.items()]
    return [*_files(cfg, "sfx"), *[b for b in built if b.name not in {f.name for f in _files(cfg, "sfx")}]]


def music(cfg: Config) -> list[Item]:
    return _files(cfg, "music") or [Item(n, about, None) for n, (about, _) in BEDS.items()]


def models(cfg: Config) -> list[Item]:
    return _files(cfg, "models3d")


def listing(cfg: Config) -> list[dict]:
    """Everything in the library, for the app."""
    out = []
    for kind in KINDS:
        builtin = {"sfx": [Item(n, a, None) for n, (_, _, _, a) in CUE_SOUNDS.items()],
                   "music": [Item(n, a, None) for n, (a, _) in BEDS.items()], "models3d": []}[kind]
        for item in [*_files(cfg, kind), *builtin]:
            out.append({"kind": kind, "name": item.name, "about": item.about, "builtin": item.path is None,
                        "file": item.path.name if item.path else "",
                        "size": item.path.stat().st_size if item.path else 0})
    return out


def save_upload(cfg: Config, kind: str, filename: str, data: bytes) -> Path:
    if kind not in KINDS:
        raise ValueError("Unknown library folder")
    ext = Path(filename).suffix.lower()
    if ext not in (MODEL_TYPES if kind == "models3d" else AUDIO_TYPES):
        raise ValueError(f"Can't use a {ext or 'file without an extension'} here")
    if len(data) > 60 * 1024 * 1024:
        raise ValueError("That file is over 60 MB")
    root = folder(cfg, kind)
    root.mkdir(parents=True, exist_ok=True)
    path = root / (slug(filename) + ext)
    path.write_bytes(data)
    return path


def remove(cfg: Config, kind: str, filename: str) -> None:
    path = folder(cfg, kind) / Path(filename).name  # no paths from outside the folder
    if kind in KINDS and path.is_file():
        path.unlink()


def prompt_block(cfg: Config, long: bool = False) -> str:
    """The sound design instructions and the library, for the script writer."""
    fx = "\n".join(f"  - {s.name}: {s.about}" for s in sounds(cfg))
    tracks = "\n".join(f"  - {m.name}: {m.about}" for m in music(cfg))
    where = ("the cold open (up to 4 layered cues) and at most 1 cue in a later beat, only on its key word, "
             "and no more than one cue every few beats" if long else
             "scene 1, the hook (2 to 4 cues layered on its words, e.g. a riser into the key word, a sword "
             "on it, a low drone underneath), and 0 to 2 in each later scene, only on the words that deserve "
             "them (the twist, a big number, the punchline)")
    return (
        "Sound design: sound effects land on single words of the narration, like a trailer editor would place "
        f"them. Put them in {where}. Each cue names the exact word it lands on, copied from that line's "
        "narration. Pick a sound whose meaning matches the words (money: cash; time running out: tick; a "
        "reveal: sword; a dark mystery: drone or heartbeat). Never a sound that jokes about something "
        "serious (death, a crash, a disaster, illness): there use only drone, heartbeat or none. Less is more: "
        "most lines get no sound, and 'soft' is the usual volume.\n"
        f"Sound effects you can use:\n{fx}\n"
        "Background music: pick the one track whose mood fits the whole video (it plays quietly under the "
        f"voice), or 'none' for no music:\n{tracks}\n"
    )


def models_block(cfg: Config) -> str:
    found = models(cfg)
    if not found:
        return ""
    return ("3D models already in the library (use their words in 'search' when one fits; any other object "
            "is found online or built from your parts):\n" + "\n".join(f"  - {m.about}" for m in found) + "\n")


def pick_music(cfg: Config, name: str, out_dir: Path, seconds: float) -> Path | None:
    """The track Claude chose (or the first that exists), copied or made in out_dir."""
    if name == "none":
        return None
    items = music(cfg)
    item = next((m for m in items if m.name == name), None) or (items[0] if items else None)
    if item is None:
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    if item.path is not None:
        return Path(shutil.copy(item.path, out_dir / f"music{item.path.suffix.lower()}"))
    return _write(out_dir / "music.wav", BEDS[item.name][1](min(seconds + 2, 90)), peak=0.5)


def _norm(word: str) -> str:
    return re.sub(r"[^\w]", "", word.lower())


def resolve_cues(cues: list, words: list, start: float, cfg: Config, out_dir: Path, rel,
                 limit: int, used: dict[str, str]) -> list[dict]:
    """Turn one line's cues (sound + word + volume) into {src, at, volume} on the timeline.

    `words` are the line's timed words (seconds from the line's start), `start` where the
    line begins. A cue whose word isn't in the line is dropped. `used` maps a
    sound to its file in the render folder, so each file is written or copied once.
    """
    library = {s.name: s for s in sounds(cfg)}
    out = []
    for cue in cues[:limit]:
        item = library.get(cue.sound)
        if item is None or not words:
            continue
        target = _norm(cue.word)
        hit = next((w for w in words if _norm(w.text) == target), None) \
            or next((w for w in words if target and target in _norm(w.text)), None)
        if hit is None:  # the line was rewritten after the sound was placed: a misplaced hit is worse than none
            continue
        lead = CUE_SOUNDS[item.name][2] if item.path is None else 0.0
        if item.name not in used:
            out_dir.mkdir(parents=True, exist_ok=True)
            if item.path is None:
                used[item.name] = rel(_write(out_dir / f"{item.name}.wav", CUE_SOUNDS[item.name][0](),
                                             peak=CUE_SOUNDS[item.name][1]))
            else:
                used[item.name] = rel(Path(shutil.copy(item.path, out_dir / f"u-{item.name}{item.path.suffix.lower()}")))
        volume = VOLUMES.get(cue.volume, VOLUMES["soft"]) * (UPLOADED_GAIN if item.path else 1.0)
        at = start + hit.start - lead
        # Too close to the start for its full lead: cut the front off so it still peaks on the word.
        out.append({"src": used[item.name], "at": round(max(0.0, at), 3), "trim": round(max(0.0, -at), 3),
                    "volume": round(volume, 3), "name": item.name})
    return out


def speech_spans(words: list[tuple[float, float]], gap: float = 0.6) -> list[list[float]]:
    """Where the voice is talking (merged across short pauses), for ducking the music."""
    spans: list[list[float]] = []
    for a, b in sorted(words):
        if spans and a - spans[-1][1] < gap:
            spans[-1][1] = max(spans[-1][1], b)
        else:
            spans.append([round(a, 3), round(b, 3)])
    return [[round(a, 3), round(b, 3)] for a, b in spans]


# ---------- built-in music beds (quiet, slow, loop cleanly) ----------

def _pad(seconds: float, chords: list[list[float]], bar: float, shimmer: float = 0.0) -> np.ndarray:
    t = np.arange(int(RATE * seconds)) / RATE
    out = np.zeros_like(t)
    for i, chord in enumerate(chords * int(seconds / (bar * len(chords)) + 1)):
        a = i * bar
        if a >= seconds:
            break
        seg = (t >= a) & (t < a + bar + 1.0)
        tt = t[seg] - a
        env = np.clip(tt / 0.9, 0, 1) * np.clip((bar + 1.0 - tt) / 1.2, 0, 1)
        for f in chord:
            for detune in (0.998, 1.0, 1.002):
                out[seg] += np.sin(2 * np.pi * f * detune * tt) * env / (1 + f / 400)
            if shimmer:
                out[seg] += shimmer * np.sin(2 * np.pi * f * 2 * tt) * env * (0.5 + 0.5 * np.sin(2 * np.pi * 0.25 * tt))
    return out


def _calm(seconds: float) -> np.ndarray:
    # Am - F - C - G, low and soft: documentary, history, nature.
    return _pad(seconds, [[110, 220, 261.6, 329.6], [87.3, 174.6, 220, 261.6],
                          [130.8, 196, 261.6, 329.6], [98, 196, 246.9, 293.7]], bar=4.0, shimmer=0.12)


def _tension(seconds: float) -> np.ndarray:
    # A low drone with a slow pulse and a minor second rubbing on top: mystery, suspense.
    t = np.arange(int(RATE * seconds)) / RATE
    drone = sum(np.sin(2 * np.pi * f * t) / (i + 1) for i, f in enumerate((55, 110, 164.8)))
    pulse = np.sin(2 * np.pi * 55 * t) * np.exp(-((t % 1.2) * 5)) * 0.8
    rub = (np.sin(2 * np.pi * 233.1 * t) + np.sin(2 * np.pi * 220 * t)) * 0.12 * (0.5 + 0.5 * np.sin(2 * np.pi * t / 8))
    return drone * 0.6 + pulse + rub


def _playful(seconds: float) -> np.ndarray:
    # Light plucked pentatonic notes over a soft bass: comedy and light stories.
    t = np.arange(int(RATE * seconds)) / RATE
    out = _pad(seconds, [[130.8, 196], [110, 164.8], [146.8, 220], [98, 146.8]], bar=2.0) * 0.5
    notes = [523.3, 587.3, 659.3, 784, 880, 784, 659.3, 587.3]
    step = 0.25
    rng = np.random.default_rng(3)
    for k in range(int(seconds / step)):
        if rng.random() < 0.45:
            continue
        a = k * step
        seg = (t >= a) & (t < a + 0.6)
        tt = t[seg] - a
        f = notes[(k * 3 + int(rng.integers(0, 3))) % len(notes)]
        out[seg] += (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(4 * np.pi * f * tt)) * np.exp(-tt * 9) * 0.35
    return out


BEDS = {
    "calm-documentary": ("built-in soft piano-like pad: history, science, nature, calm true stories", _calm),
    "dark-tension": ("built-in low drone with a slow pulse: mystery, crime, suspense, disasters", _tension),
    "light-playful": ("built-in light plucks: comedy, fun facts, light stories", _playful),
}
