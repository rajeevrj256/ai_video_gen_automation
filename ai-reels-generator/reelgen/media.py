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

import json
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


# The licence of every uploaded file, kept next to the files (<folder>/licences.json). A file is only
# used in videos once its licence is known: an unlicensed track can bring Content ID claims or a
# copyright strike, and a CC BY file needs a credit (added to the video's description).
LICENCES = {
    "own": "Made or recorded by me",
    "royalty-free": "Royalty-free, cleared for YouTube (bought, or e.g. Pixabay, Mixkit, YouTube Audio Library)",
    "cc0": "CC0 / public domain",
    "cc-by": "CC BY: free with a credit",
    "unknown": "Unknown: not used in videos",
}
USABLE = ("own", "royalty-free", "cc0", "cc-by")
LICENCE_FILE = "licences.json"


def licences(cfg: Config, kind: str) -> dict[str, dict]:
    path = folder(cfg, kind) / LICENCE_FILE
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        return {}


def set_licence(cfg: Config, kind: str, filename: str, licence: str, credit: str = "") -> None:
    if kind not in KINDS or licence not in LICENCES:
        raise ValueError("Unknown licence")
    root = folder(cfg, kind)
    if not (root / Path(filename).name).is_file():
        raise ValueError("No such file")
    data = licences(cfg, kind)
    data[Path(filename).name] = {"licence": licence, "credit": credit.strip()[:300]}
    (root / LICENCE_FILE).write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")


def set_all_licences(cfg: Config, licence: str, only_unknown: bool = True) -> int:
    """Give every file in the library (or only those without a licence yet) this licence; returns how many."""
    if licence not in LICENCES:
        raise ValueError("Unknown licence")
    count = 0
    for kind in KINDS:
        lic = licences(cfg, kind)
        for item in _files(cfg, kind, everything=True):
            old = lic.get(item.path.name, {}).get("licence", "unknown")
            if only_unknown and old != "unknown":
                continue
            set_licence(cfg, kind, item.path.name, licence, lic.get(item.path.name, {}).get("credit", ""))
            count += 1
    return count


def credits(cfg: Config, used_files: list[tuple[str, str]]) -> list[str]:
    """Credit lines for the CC BY files a video used ((kind, file name) pairs), as their licence asks."""
    out = []
    for kind, name in dict.fromkeys(used_files):
        lic = licences(cfg, kind).get(name, {})
        if lic.get("licence") == "cc-by":
            out.append(lic.get("credit") or f"{Path(name).stem} (CC BY)")
    return out


def _files(cfg: Config, kind: str, everything: bool = False) -> list[Item]:
    """The user's files of this kind; only those with a known licence unless `everything`."""
    root = folder(cfg, kind)
    types = MODEL_TYPES if kind == "models3d" else AUDIO_TYPES
    lic = licences(cfg, kind)
    items, seen = [], set()
    for path in sorted(root.glob("*")) if root.exists() else []:
        if path.suffix.lower() not in types:
            continue
        if not everything and lic.get(path.name, {}).get("licence") not in USABLE:
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
    """The user's tracks first, then the built-in beds: a video uses an upload only when one fits it
    (Claude picks by the file names), never just because it's the only file there."""
    mine = _files(cfg, "music")
    return [*mine, *[Item(n, about, None) for n, (about, _) in BEDS.items() if n not in {m.name for m in mine}]]


# What each automatic sound (transition, pop, click, the long videos' sound design) is for, as words
# an uploaded file's name may contain. An upload whose name matches plays that role; otherwise the
# built-in sound does.
ROLE_WORDS = {
    "whoosh": ("whoosh", "swoosh", "woosh", "whip", "swipe", "transition"),
    "swish": ("swish", "swoosh", "whoosh", "woosh", "whip", "swipe"),
    "impact": ("impact", "punch", "slam", "thud", "hit"),
    "glitch": ("glitch", "digital", "static", "distort"),
    "shimmer": ("shimmer", "sparkle", "magic", "chime", "twinkle", "glitter"),
    "pop": ("pop", "bubble", "blip"),
    "click": ("click", "tick", "tap", "blip"),
    "ding": ("ding", "bell", "chime", "notification"),
    "rumble": ("rumble", "earthquake", "quake"),
    "heartbeat": ("heartbeat", "heart", "pulse"),
    "typing": ("typing", "keyboard"),
    "flyby": ("flyby", "fly", "plane", "jet"),
    "cash": ("cash", "coin", "coins", "money", "register"),
    "drone": ("drone", "ambient", "tension"),
    "tick": ("tick", "clock", "timer"),
    "sword": ("sword", "blade", "slash", "katana"),
    "riser": ("riser", "uplifter", "swell", "build"),
    "sad": ("sad", "fail", "trombone", "lose"),
}


def uploaded_for(cfg: Config, roles, out_dir: Path) -> dict[str, Path]:
    """Copies of the user's sound files whose names match these roles (whole words of the file name);
    roles with no matching upload are left out, so the built-in sound plays there."""
    files = _files(cfg, "sfx")
    out: dict[str, Path] = {}
    for role in roles:
        words = ROLE_WORDS.get(role, (role,))
        match = next((f for w in words for f in files if {w, w + "s"} & set(f.name.split("-"))), None)
        if match is None:
            continue
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / f"u-{match.name}{match.path.suffix.lower()}"
        if not dest.exists():
            shutil.copy(match.path, dest)
        out[role] = dest
    return out


def models(cfg: Config) -> list[Item]:
    return _files(cfg, "models3d")


def listing(cfg: Config) -> list[dict]:
    """Everything in the library, for the app."""
    out = []
    for kind in KINDS:
        builtin = {"sfx": [Item(n, a, None) for n, (_, _, _, a) in CUE_SOUNDS.items()],
                   "music": [Item(n, a, None) for n, (a, _) in BEDS.items()], "models3d": []}[kind]
        lic = licences(cfg, kind)
        for item in [*_files(cfg, kind, everything=True), *builtin]:
            own = lic.get(item.path.name, {}) if item.path else {}
            out.append({"kind": kind, "name": item.name, "about": item.about, "builtin": item.path is None,
                        "file": item.path.name if item.path else "",
                        "size": item.path.stat().st_size if item.path else 0,
                        "licence": "builtin" if item.path is None else own.get("licence", "unknown"),
                        "credit": own.get("credit", "")})
    return out


def save_upload(cfg: Config, kind: str, filename: str, data: bytes, licence: str = "unknown",
                credit: str = "") -> Path:
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
    set_licence(cfg, kind, path.name, licence if licence in LICENCES else "unknown", credit)
    return path


def remove(cfg: Config, kind: str, filename: str) -> None:
    path = folder(cfg, kind) / Path(filename).name  # no paths from outside the folder
    if kind in KINDS and path.is_file() and path.name != LICENCE_FILE:
        path.unlink()
        data = licences(cfg, kind)
        if data.pop(path.name, None) is not None:
            (folder(cfg, kind) / LICENCE_FILE).write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")


def prompt_block(cfg: Config, long: bool = False) -> str:
    """The sound design instructions and the library, for the script writer."""
    mark = lambda i: " (the user's own file)" if i.path else " (built-in)"
    fx = "\n".join(f"  - {s.name}: {s.about}{mark(s)}" for s in sounds(cfg))
    tracks = "\n".join(f"  - {m.name}: {m.about}{mark(m)}" for m in music(cfg))
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
        "Use the user's own sound effects and music (listed first) wherever they fit the moment and the "
        "video; when none fits, use a built-in one" + (" or let the app compose the music" if long else "") + ". "
        "Never use a file only because it is there.\n"
        "Background music: pick the one track whose mood fits the whole video (it plays quietly under the "
        "voice)" + (", 'compose' to have a track composed for this video's mood" if long else "")
        + f", or 'none' for no music:\n{tracks}\n"
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
    # An unknown name gets a built-in bed, never the user's first track whatever it is.
    item = next((m for m in items if m.name == name), None) or next((m for m in items if m.path is None), None)
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


# ---------- sound-effect levels, measured against the voice ----------

SFX_UNDER_VOICE = 0.5  # every effect's loudness is at most half the narrator's (about -6 dB) ...
# ... and Cues in the editor lower it again while someone speaks (SPEECH_DUCK in Sound.tsx).


def _loudness(path: Path) -> float | None:
    """RMS of the audible part of a sound file (quiet tails ignored), 0-1; None if unreadable."""
    import subprocess

    from .video import FFMPEG

    try:
        raw = subprocess.run([FFMPEG, "-v", "error", "-i", str(path), "-ac", "1", "-ar", "22050", "-f", "f32le", "-"],
                             capture_output=True, timeout=60, check=True).stdout
    except (subprocess.SubprocessError, OSError):
        return None
    x = np.frombuffer(raw, dtype=np.float32)
    if not x.size:
        return None
    win = 1024
    frames = x[: x.size // win * win].reshape(-1, win) if x.size >= win else x.reshape(1, -1)
    rms = np.sqrt((frames ** 2).mean(axis=1))
    loud = rms[rms > max(1e-4, rms.max() * 0.1)]  # the part you actually hear
    return float(np.sqrt((loud ** 2).mean())) if loud.size else None


def level_sounds(props: dict, root: Path, voice_files: list[str]) -> dict:
    """Make every sound effect quieter than the voice, whatever its source: built-in, uploaded or
    synthesised. Each effect file louder than SFX_UNDER_VOICE x the narration is written again
    turned down (as <name>-lv.wav) and props point at that copy. Returns {file: gain} applied."""
    import wave

    voices = [v for v in (_loudness(root / f) for f in voice_files[:12] if f) if v]
    if not voices:
        return {}
    target = float(np.median(voices)) * SFX_UNDER_VOICE
    srcs = {c["src"] for c in props.get("cues") or []} | set((props.get("sfx") or {}).values())
    gains, moved = {}, {}
    for src in sorted(srcs):
        level = _loudness(root / src)
        if not level or level <= target:
            continue
        gain = target / level
        import subprocess

        from .video import FFMPEG

        out = (root / src).with_name((root / src).stem + "-lv.wav")
        try:
            raw = subprocess.run([FFMPEG, "-v", "error", "-i", str(root / src), "-ac", "2", "-ar", "44100", "-f", "f32le", "-"],
                                 capture_output=True, timeout=60, check=True).stdout
        except (subprocess.SubprocessError, OSError):
            continue
        pcm = np.clip(np.frombuffer(raw, dtype=np.float32) * gain, -1, 1)
        with wave.open(str(out), "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(44100)
            w.writeframes((pcm * 32767).astype("<i2").tobytes())
        moved[src] = out.relative_to(root).as_posix()
        gains[src] = round(gain, 3)
    for c in props.get("cues") or []:
        c["src"] = moved.get(c["src"], c["src"])
    if props.get("sfx"):
        props["sfx"] = {k: moved.get(v, v) for k, v in props["sfx"].items()}
    return gains
