"""AI music for every video, every pipeline: a new track made by the local music model (ACE-Step, through
reelgen/anim_engine.py) from the video's own brief: its mood, energy and pace, and the sound of its world as the writer
describes it (`music_prompt` in each script), in a genre none of the last videos used (GENRES, remembered in
<output>/music_used.json as 'genre:<key>'). Composed music (reelgen/music.py) stays the fallback: no AI engine, the
setting `ai_music` off, the card busy with another video for over BUSY_WAIT seconds, or a track the model didn't
finish. The tracks are levelled under the voice later (media.level_music) like every other music.
"""

from __future__ import annotations

import logging
import random
from pathlib import Path
from typing import Callable

from . import anim_engine, media

log = logging.getLogger(__name__)
Progress = Callable[[str], None]

BUSY_WAIT = 120  # seconds a video waits for the card when another video's AI step holds it, then composes
LONGEST = 300  # seconds of one generated track (longer parts loop it)
RECENT = 4  # a genre rests for this many videos

# Genre: (what the music model hears, the moods it suits). Every video gets one the last RECENT didn't use.
GENRES = {
    "cinematic-orchestral": ("cinematic orchestral score, strings, brass swells, timpani", {"suspense", "dark", "emotional", "uplifting", "mystery"}),
    "dark-synth": ("dark synthwave, analog bass pulse, arpeggiated synths, gated drums", {"suspense", "dark", "mystery", "energetic"}),
    "lofi": ("lo-fi hip hop, dusty drums, warm Rhodes piano, soft vinyl texture", {"calm", "curious", "playful"}),
    "ambient-electronic": ("ambient electronic, evolving pads, soft pulses, glassy textures", {"calm", "curious", "mystery", "emotional"}),
    "piano-minimal": ("minimal felt piano, gentle strings underneath", {"emotional", "calm", "curious"}),
    "acoustic-folk": ("acoustic folk, fingerpicked guitar, light hand percussion, warm", {"uplifting", "calm", "playful", "emotional"}),
    "indian-fusion": ("Indian fusion, tabla groove, sitar and bansuri phrases, modern bass", {"curious", "uplifting", "energetic", "mystery"}),
    "cinematic-trap": ("cinematic trap, deep 808 bass, crisp hi-hats, dark choir stabs", {"energetic", "suspense", "dark"}),
    "quirky-funk": ("quirky funk, slap bass, pizzicato strings, playful brass hits", {"playful", "quirky"}),
    "noir-jazz": ("noir jazz, brushed drums, upright bass, muted trumpet", {"mystery", "suspense", "quirky"}),
    "electro-pop": ("upbeat electro pop, bright synth plucks, four-on-the-floor kick", {"energetic", "uplifting", "playful"}),
    "world-percussion": ("world percussion, hand drums, marimba, earthy and driving", {"energetic", "curious", "uplifting"}),
    "post-rock": ("post-rock, shimmering delayed guitars, building drums", {"uplifting", "emotional", "energetic"}),
    "chiptune": ("chiptune, 8-bit arpeggios, square-wave bass, game-like", {"playful", "quirky"}),
    "industrial-tension": ("industrial tension, metallic hits, low drones, ticking percussion", {"suspense", "dark"}),
    "orchestral-whimsy": ("whimsical orchestral, pizzicato, glockenspiel, bassoon", {"playful", "quirky", "curious"}),
    "desert-blues": ("desert blues, hypnotic electric guitar riffs, hand claps, deep groove", {"mystery", "curious", "energetic"}),
    "neo-classical": ("neo-classical, string quartet ostinato, solo cello", {"emotional", "suspense", "mystery"}),
}
MOOD_WORDS = {"mystery": "mysterious, curious tension", "suspense": "suspenseful, pulsing, tense", "emotional": "emotional, heartfelt",
              "uplifting": "uplifting, hopeful, bright", "curious": "curious, light and inquisitive", "dark": "dark, ominous, brooding",
              "energetic": "energetic, punchy, driving", "calm": "calm, warm, unhurried", "playful": "playful, bouncy, fun",
              "quirky": "quirky, offbeat, cheeky"}
BPM = {"mystery": (78, 96), "suspense": (96, 120), "emotional": (64, 80), "uplifting": (100, 118), "curious": (100, 122),
       "dark": (66, 84), "energetic": (124, 148), "calm": (78, 94), "playful": (106, 126), "quirky": (92, 112)}


def available(cfg) -> bool:
    return bool(getattr(cfg, "ai_music", True)) and anim_engine.installed()


def recent_genres(cfg) -> list[str]:
    return [n[6:] for n in media.recent_music(cfg) if n.startswith("genre:")][-RECENT:]


def pick_genre(cfg, mood: str, seed: int) -> str:
    """A genre that suits the mood and none of the last RECENT videos used (any unused one when none suits)."""
    recent = set(recent_genres(cfg))
    fits = [g for g, (_, moods) in GENRES.items() if mood in moods and g not in recent]
    pool = fits or [g for g in GENRES if g not in recent] or list(GENRES)
    return random.Random(seed).choice(pool)


def energy_words(energy: float) -> str:
    return ("sparse and quiet" if energy < 0.3 else "gentle, steady" if energy < 0.5 else "steady groove, building"
            if energy < 0.7 else "driving, full" if energy < 0.85 else "intense, powerful, big drums")


def caption(genre: str, mood: str, energy: float, brief: str = "", hook: bool = False) -> str:
    """What the music model hears: the genre, the mood and energy, the video's own sound colours, instrumental."""
    parts = [GENRES.get(genre, GENRES["cinematic-orchestral"])[0], MOOD_WORDS.get(mood, mood), energy_words(energy)]
    if hook:
        parts.append("an attention-grabbing opening that hits from the first second, trailer energy, punchy")
    if brief.strip():
        parts.append(brief.strip().rstrip("."))
    return ", ".join(parts) + ", instrumental, no vocals"


def bpm_for(mood: str, energy: float, seed: int) -> int:
    lo, hi = BPM.get(mood, (90, 115))
    return int(lo + (hi - lo) * min(1.0, max(0.0, 0.35 * random.Random(seed).random() + 0.65 * energy)))


def track(tid: str, out: Path, seconds: float, genre: str, mood: str, energy: float, brief: str, seed: int,
          hook: bool = False) -> dict:
    return {"id": tid, "out": str(out), "seed": seed, "bpm": bpm_for(mood, energy, seed),
            "caption": caption(genre, mood, energy, brief, hook), "duration": round(min(LONGEST, max(10.0, seconds)), 1)}


def make(cfg, tracks: list[dict], work: Path, progress: Progress, label: str = "Music (AI)") -> dict[str, Path]:
    """The tracks the music model made (finished earlier ones kept), each brought to one loudness; {} when it isn't
    available or busy. Missing ones are the caller's to compose."""
    from .animated import _loudnorm, _ready
    from .stopper import Paused

    if not tracks or not available(cfg):
        return {}
    todo = [t for t in tracks if not _ready(Path(t["out"]))]
    if todo:
        try:
            anim_engine.run_stage("music", {"tracks": todo, "ace_root": str(anim_engine.ENGINE)}, work, progress, label,
                                  wait=BUSY_WAIT)
        except anim_engine.EngineBusy:
            progress(f"{label}: the AI engine is busy with another video; composing the music instead")
        except Exception as exc:  # noqa: BLE001 - music never stops a video
            if isinstance(exc, Paused):
                raise
            log.warning("AI music failed: %s", exc)
            progress(f"{label}: the music model didn't finish ({str(exc)[:200]}); composing what's missing")
    made = {}
    for t in tracks:
        path = Path(t["out"])
        if _ready(path):
            if not Path(str(path) + ".norm").exists():
                _loudnorm(path)
                Path(str(path) + ".norm").write_text("", encoding="utf-8")
            made[t["id"]] = path
    return made


def remember(cfg, genre: str) -> None:
    media.note_music(cfg, f"genre:{genre}")


PROMPT_FIELD = ("What the music should carry for this video, 8-25 words: the feeling, the energy and 1-2 sound colours "
                "from its world (e.g. 'tense and curious, ticking clocks and radar pings', 'warm nostalgia, monsoon rain "
                "and soft tabla'). No genre name: the genre is chosen so no two videos sound alike.")
