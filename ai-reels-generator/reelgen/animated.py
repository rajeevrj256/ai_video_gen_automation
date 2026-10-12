"""Animated videos: 6-8 minute 16:9 explainers where every shot is AI-made animation, made on this computer.

Claude writes and directs the script (fact-checked like every pipeline here), designs the cast and picks an
art style the last videos didn't use; the local AI engine (reelgen/anim_engine.py, anim_worker/worker.py)
then draws a character sheet for each character and a picture for every shot (SDXL-Lightning, IP-Adapter
keeps each character's look), turns the pictures into moving clips (LTX-Video 2B), and writes new music for
the hook and every chapter (ACE-Step 1.5). Remotion (composition `Anim`, remotion/src/anim/) times the clips
to the voice and adds the emphasised words, chapter cards, transitions and sounds.

Slow by design on a small graphics card (a 4 GB GTX 1650: about a day for 7 minutes with every shot
animated); every picture, clip and track is saved as it's made and Resume carries on from the next one.
`motion` chooses how much is real AI video: `full` (every shot), `key` (the hook and the important shots;
the rest are pictures moved by the camera) or `stills` (pictures only, a few hours).

Separate from every other pipeline: tab Anim, job `anim_input`, checkpoint `anim-checkpoint.json`, memory
`anim_history.json`, folders `*-anim-working` → `*-anim`, report `source: "anim"`.
"""

from __future__ import annotations

import json
import logging
import math
import random
import subprocess
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal

from pydantic import BaseModel, Field

from . import anim_engine, media, repeats
from .categories import CATEGORIES
from .config import Config
from .llm import ask
from .longform import LSource, verify_sources, with_sources
from .script_writer import AI_CLICHES, SoundCue
from .sfx import write_sfx
from .toon import TONES, VOICES, Kind, ScriptCheck, Tone, _find_phrase
from .verify import probe
from .video import FFMPEG, _remotion_cli, _render_remotion, media_seconds
from .voice import synthesize_scenes

log = logging.getLogger(__name__)
Progress = Callable[[str], None]

CHECKPOINT = "anim-checkpoint.json"
HISTORY = "anim_history.json"
WORDS_PER_SECOND = 2.6
TITLE_SECONDS, CHAPTER_SECONDS = 3.2, 2.4
_lock = threading.Lock()

# Art styles: the look of every picture. The video's style is never one of the last 3 videos' (code checks).
ART_STYLES = {
    "flat-vector": ("flat 2D vector cartoon illustration, bold clean outlines, simple shapes, soft gradients, vibrant colors", "#FFB703"),
    "storybook": ("children's storybook illustration, gouache and watercolor textures, warm soft light, hand-painted", "#E76F51"),
    "paper-cutout": ("layered paper cut-out craft style, visible paper texture, soft drop shadows, handmade diorama", "#F4A261"),
    "anime": ("2D anime cel-shaded illustration, crisp line art, vivid skies, detailed painted backgrounds", "#4CC9F0"),
    "comic": ("bold comic book art, thick ink lines, halftone shading, dynamic angles, saturated flat colors", "#FF006E"),
    "clay": ("claymation stop-motion look, soft rounded plasticine characters, miniature handmade set, studio lighting", "#FF9F1C"),
    "retro-cartoon": ("1950s retro cartoon, limited color palette, grainy print texture, rubber-hose style characters", "#E9C46A"),
    "low-poly": ("stylized low-poly 3D render, faceted shapes, soft pastel lighting, clean minimal scene", "#72EFDD"),
    "3d-animated": ("stylized 3D animated film still, expressive characters, soft global illumination, rich colors", "#F72585"),
    "ink-wash": ("ink wash and watercolor painting, loose expressive brush strokes, muted earthy tones, paper grain", "#8D99AE"),
    "pixel-art": ("detailed 16-bit pixel art scene, crisp pixels, limited vibrant palette, retro game look", "#06D6A0"),
    "neon-synth": ("neon synthwave illustration, glowing outlines, dark purple night, magenta and cyan light", "#F15BB5"),
}
CAMERAS = {"push-in": "the camera slowly pushes in", "pull-out": "the camera slowly pulls back",
           "pan-left": "the camera pans left", "pan-right": "the camera pans right", "tilt-up": "the camera tilts up",
           "tilt-down": "the camera tilts down", "orbit": "the camera orbits slightly around the subject",
           "handheld": "a gentle handheld camera", "static": "static camera"}
Camera = Literal["push-in", "pull-out", "pan-left", "pan-right", "tilt-up", "tilt-down", "orbit", "handheld", "static"]
Transition = Literal["cut", "crossfade", "whip", "flash", "zoom", "dip"]
Fx = Literal["text", "zoom", "shake", "flash", "pause"]
NEGATIVE = ("text, letters, words, caption, watermark, logo, signature, frame, border, blurry, lowres, jpeg artifacts, "
            "deformed, disfigured, extra fingers, extra limbs, bad anatomy, duplicate, cropped head")
TRANSITION_SOUND = {"whip": ("whoosh", 0.55), "zoom": ("swish", 0.45), "flash": ("shimmer", 0.4), "cut": ("swish", 0.25)}


@dataclass
class AnimRequest:
    topic: str = ""
    minutes: float = 7.0
    style: str = "auto"  # an ART_STYLES key, or auto (Claude picks one the last videos didn't use)
    motion: str = "full"  # full | key | stills
    quality: str = "auto"  # CLIP_SIZES key, or auto (fast on cards under 6 GB, else standard)
    upscale: bool = True  # sharpen clips and pictures to full HD with the AI upscaler (anim_worker `upscale`)
    voice: str = "en-US-AndrewMultilingualNeural"
    speed: int = 8
    captions: bool = False
    watermark: str = ""


# ---------- what Claude writes ----------

class ACharacter(BaseModel):
    id: str = Field(description="Short id used in the shots, e.g. 'mira'.")
    name: str
    role: str = Field(description="Who they are in the story. Never a real, named person.")
    design: str = Field(description="How they look, for the picture model, 25-60 words: species or age/build, face, hair, "
                        "clothes with colours, one signature item. Specific and fixed: it is repeated in every shot.")


class AShot(BaseModel):
    line: str = Field(description="One spoken sentence, 6-28 words. The whole video is these lines in order.")
    meaning: str = Field(description="What the viewer must understand here, in a few words.")
    kind: Kind
    importance: Literal["low", "medium", "high", "critical"]
    tone: Tone
    emphasis: str = Field(default="", description="The few words that carry the line, copied exactly, or empty.")
    emphasis_fx: list[Fx] = Field(default_factory=list, description="On the emphasised words: text (they land big on "
                                  "screen), zoom (punch-in), shake, flash, pause (a beat after the line). 0 for low lines.")
    scene: str = Field(description="The picture of this moment for the image model, 25-70 words: who/what is in frame "
                       "doing what (pose, expression), the setting, composition (close-up / wide / over-the-shoulder / "
                       "bird's-eye...), lighting and mood. Concrete and visual; a metaphor for anything abstract. At most "
                       "two people near the camera, each fully in frame with the face visible; groups only small in the "
                       "distance. Never text, signs, labels, numbers, logos or screens with writing (the editor adds words).")
    characters: list[str] = Field(default_factory=list, description="Cast ids in frame (0-2), the main one first.")
    same_place: bool = Field(default=False, description="True when this shot continues in the same place as the shot "
                             "before (its picture is drawn from that one, so the setting stays the same).")
    motion: str = Field(description="What moves during the 4-5 second clip, 10-35 words: one clear action (she turns and "
                        "points, the tower cracks and leans, rain starts), plus small life (hair, smoke, crowds).")
    camera: Camera
    transition: Transition = Field(description="How this shot comes in: cut (most), crossfade (time passes, calm), whip "
                                   "(energy, the hook), flash (a reveal), zoom (into detail), dip (black, a new beat).")
    on_screen: str = Field(default="", description="0-4 words the editor writes on screen when a figure, date or name "
                           "matters (\"1859\", \"40% LESS\"); mostly empty.")
    sounds: list[SoundCue] = Field(default_factory=list, description="0-2 effects from the sound list on exact words; "
                                   "most lines get none.")


class AChapter(BaseModel):
    title: str
    card_text: str = Field(description="The chapter card's line (a question or short phrase, max 8 words).")
    music: str = Field(description="This chapter's music for the music model, 12-40 words: genre, instruments, mood, "
                       "energy, e.g. 'tense cinematic strings and low synth pulse, building, sparse percussion'. Each "
                       "chapter different from the others, following its story beat. Instrumental.")
    bpm: int = Field(ge=60, le=170)
    intensity: float = Field(default=0.5, ge=0, le=1)
    shots: list[AShot]


class AnimScript(BaseModel):
    subject: str = Field(description="The one specific subject of the video.")
    title: str = Field(description="Max 70 characters: curiosity plus the main search phrase, honest.")
    hook: str = Field(description="One sentence: why someone keeps watching.")
    art_style: str = Field(description="One of the art style keys listed.")
    style_notes: str = Field(description="This video's own look within the style, 10-40 words: palette, light, texture, "
                             "era (e.g. 'warm amber and teal, dusty late-afternoon light, 1930s details').")
    characters: list[ACharacter] = Field(default_factory=list, description="1-5 recurring characters (generic people, "
                                         "animals or personified things; never real named people).")
    title_scene: str = Field(description="The picture behind the title card, 20-50 words, no text.")
    hook_music: str = Field(description="The cold open's music for the music model, 12-40 words, energetic and tense.")
    hook_bpm: int = Field(ge=70, le=170)
    cold_open: list[AShot] = Field(description="The hook, 25-40 seconds (70-100 spoken words, 6-9 shots) before the title.")
    chapters: list[AChapter]
    music_track: str = Field(default="generate", description="One of the user's own tracks from the list when it truly "
                             "fits the whole video, else 'generate'.")
    sources: list[LSource] = Field(default_factory=list, description="3-10 pages you opened that confirm every real fact.")
    youtube_description: str = Field(description="2-4 natural sentences, then one line inviting viewers to subscribe.")
    tags: list[str]
    hashtags: list[str] = Field(description="3 hashtags without '#'.")
    category: str = Field(default="", description="One of " + ", ".join(CATEGORIES) + ".")


def _system(minutes: float, styles: str, recent: str, sounds: str) -> str:
    words = int(minutes * 60 * WORDS_PER_SECOND)
    return f"""You write and direct fully animated YouTube videos (16:9, {minutes:g} minutes). Every shot is drawn by an \
image model from your `scene` and brought to life by a video model from your `motion`, so you are the director, \
storyboard artist and writer at once.

Length: about {words} spoken words in total: a 25-40 second cold open, a title card, then 5-7 chapters of 7-14 shots.
One line = one shot (4-7 seconds). Something visibly happens in every shot.

Art style (pick the one that fits the subject best; every picture is drawn in it):
{styles}{recent}

The narration:
- American English, a warm, confident storyteller talking to one viewer; short and long sentences mixed; every line
pushes forward (but, so, which means). Each chapter raises the stakes or answers the question the last one left.
- Cold open: a startling first line in 12 words or fewer, then the most surprising moments of the video, a turn, and a
cliffhanger into the title. No greeting, no "in this video".
- Never use: {", ".join(AI_CLICHES)}.
- Accuracy first: every real name, number, date and event is true and confirmed with web search (put the pages in
`sources`); speculation is said as a possibility. No real people as characters, no politics, no rumours.
- Your own words and story: never copy another video's script, characters or structure.

Directing every shot (think: meaning → emotion → picture → motion → camera → sound):
- `scene` is a film frame, not a slide: a concrete moment with a subject doing something, a setting, a composition and a
light. Vary the shot size and angle (wide establishing, medium, close-up on hands or eyes, over-the-shoulder, bird's-eye,
low angle) and never the same composition twice in a row. Abstract ideas become visual metaphors.
- Characters: design 1-5 recurring characters in `characters` (their `design` is reused in every shot, so it is
specific and fixed) and list who is in frame per shot (main first). Bring in scenes without them too (places, objects,
distant crowds, nature) so the film breathes. The image model breaks close groups (people without heads, merged
bodies, extra arms): at most two people near the camera, each whole and inside the frame with the face showing; a
crowd only far away; hands simple (resting, pointing, holding one big object).
- `same_place`: true when the shot stays in the previous shot's location (a new angle or moment there); a chapter usually
has 2-3 places.
- `motion`: one clear action the video model can show in 4-5 seconds, plus small life (wind, light, crowds). Big
moments get big motion; calm lines get gentle motion.
- Importance sets the intensity: low = gentle motion, no text; medium = a clear action; high = a strong action and the
emphasised words on screen; critical (reveals, turns, the hook's key lines) = everything on the same word: words,
punch-in, flash, a sound. Most lines are low or medium.
- `on_screen` only for a number, date or name worth seeing (the picture model can't write).
- Transitions: mostly cuts; whips in the hook, crossfades for time passing, a flash for a reveal, dip to black for a
big turn. Never the same non-cut transition twice in a row.
- Music: describe the hook's and each chapter's music for a music model (genre, instruments, mood, energy), different
in every chapter and following the story (calm curiosity, rising tension, wonder, resolution...).

{sounds}"""


def _history(cfg: Config) -> list[dict]:
    try:
        return json.loads((cfg.output_dir / HISTORY).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _remember(cfg: Config, entry: dict) -> None:
    with _lock:
        past = _history(cfg)
        past.append(entry)
        (cfg.output_dir / HISTORY).write_text(json.dumps(past[-60:], indent=1), encoding="utf-8")


def _recent_styles(cfg: Config, n: int = 3) -> list[str]:
    return [h.get("style") for h in _history(cfg)[-n:]]


def write_script(cfg: Config, req: AnimRequest, avoid: str = "") -> AnimScript:
    recent_styles = _recent_styles(cfg)
    if req.style in ART_STYLES:
        styles = f"- {req.style}: {ART_STYLES[req.style][0]} (chosen by the user: use this one)"
    else:
        styles = "\n".join(f"- {k}: {v[0]}" for k, v in ART_STYLES.items() if k not in recent_styles)
    past = _history(cfg)[-6:]
    recent = ("\nThe last videos looked like this; make this one different (characters, palette, music): "
              + "; ".join(f"{p.get('style')} / {p.get('notes', '')[:60]} / music: {p.get('music', '')[:60]}" for p in past)) if past else ""
    topic = req.topic.strip()
    if topic:
        prompt = (f"Topic, chosen by the user: {topic}\nThe video is about exactly this topic. Don't replace it.")
    else:
        prompt = ("Topic: pick a subject people are curious about right now (science, history, nature, space, technology, "
                  "the human body, money) that would make a gripping animated story.") + repeats.prompt_block(cfg, repeats.EVERY)
    if avoid:
        prompt += f"\n\n{avoid}"
    prompt += "\n- Research budget: at most 8 web searches and 6 opened pages, then write."
    sounds = media.prompt_block(cfg) + "\nIn this video `music_track` names one of the user's own tracks only when it fits; otherwise 'generate'."
    return ask(cfg.ai_backend, cfg.claude_model, _system(req.minutes, styles, recent, sounds), prompt, AnimScript,
               allow_web=True, effort=cfg.claude_effort, timeout=2400)


# ---------- fact-check: every factual line, a true rewrite re-checked once, the rest cut ----------

def _refs(sc: AnimScript) -> dict[str, AShot]:
    refs = {f"H{i + 1}": sh for i, sh in enumerate(sc.cold_open)}
    refs.update({f"C{ci + 1}.{i + 1}": sh for ci, ch in enumerate(sc.chapters) for i, sh in enumerate(ch.shots)})
    return refs


def _check(cfg: Config, sc: AnimScript, only: set[str] | None = None) -> ScriptCheck:
    rows = [f"{r}{' >>' if only and r in only else ''} {sh.line}" + (f" (on screen: {sh.on_screen})" if sh.on_screen else "")
            for r, sh in _refs(sc).items() if sh.line.strip() and (not only or r in only)]
    system = ("You fact-check an animated documentary. Search the web and open reliable pages. A line is confirmed only if "
              "a source you opened says the same; figures and dates must match. Lines framed as a possibility or a "
              "story device are fine as long as they state no false fact.")
    prompt = (f"Title: {sc.title}\nThe writer's sources: " + "; ".join(f"{s.title} {s.url}" for s in sc.sources)
              + "\n\n" + "\n".join(rows))
    return ask(cfg.ai_backend, cfg.fact_model, system, prompt, ScriptCheck, allow_web=True, effort=cfg.fact_effort, timeout=1200)


def check_facts(cfg: Config, sc: AnimScript, progress: Progress) -> tuple[AnimScript, list[str], list[dict]]:
    findings: list[dict] = []
    refs = _refs(sc)
    progress("Fact-checking every claim")
    changed: set[str] = set()
    for c in _check(cfg, sc).lines:
        findings.append(c.model_dump())
        sh = refs.get(c.ref)
        if sh is None or c.verdict == "confirmed":
            continue
        sh.line, sh.on_screen = c.fix.strip(), ""
        changed.add(c.ref)
    issues = []
    rewritten = {r for r in changed if refs[r].line}
    if rewritten:
        progress(f"Re-checking the {len(rewritten)} corrected line(s)")
        for c in _check(cfg, sc, only=rewritten).lines:
            if c.ref in rewritten:
                findings.append({**c.model_dump(), "round": 2})
                if c.verdict != "confirmed":
                    issues.append(f"{c.ref}: still not confirmed ({c.note}); the shot was cut.")
                    refs[c.ref].line = ""
    sc.cold_open = [sh for sh in sc.cold_open if sh.line.strip()]
    for ch in sc.chapters:
        ch.shots = [sh for sh in ch.shots if sh.line.strip()]
    sc.chapters = [ch for ch in sc.chapters if ch.shots]
    return sc, issues, findings


# ---------- the timeline: voice, cards, shots ----------

def _style_of(sc: AnimScript, req: AnimRequest, cfg: Config, seed: int) -> str:
    """The user's pick; else Claude's, unless one of the last 3 videos used it (then a fresh one)."""
    if req.style in ART_STYLES:
        return req.style
    recent = _recent_styles(cfg)
    if sc.art_style in ART_STYLES and sc.art_style not in recent:
        return sc.art_style
    return random.Random(seed).choice([k for k in ART_STYLES if k not in recent] or list(ART_STYLES))


# Clip size and longest clip per quality. LTX's work grows with width x height x frames (and attention with its
# square): a GTX 1650 took ~13.6 min for an 832x480, 5 s clip; fast is about a third of the pixels and frames.
CLIP_SIZES = {"fast": (640, 352, 3.0), "standard": (832, 480, 5.0), "high": (1024, 576, 5.0)}
QUALITIES = ("auto", *CLIP_SIZES)


# The AI upscaler (Real-ESRGAN compact, anim_worker `upscale`): the anime model keeps flat and inked styles
# crisp, the general one suits painted and 3D looks; pixel art is left alone (it would smear its pixels).
SR_FOR = {"flat-vector": "anime", "anime": "anime", "comic": "anime", "retro-cartoon": "anime", "neon-synth": "anime",
          "paper-cutout": "anime", "pixel-art": None}
HD_CLIP = (1920, 1080)
HD_PICTURE = (2560, 1440)  # the camera moves zoom into the pictures


def _hd(path: Path) -> Path:
    """clips/s000.mp4 -> clips/s000.hd.mp4 (its last frame: s000.hd.last.jpg)."""
    return path.with_name(path.stem + ".hd" + path.suffix)


def _ready(path: Path) -> bool:
    return path.exists() and Path(str(path) + ".ok").exists()


def upscale_job(shots: list[dict], style: str, work: Path) -> dict | None:
    """Every finished clip, and the pictures shown as pictures (shots without a clip, title and chapter cards)."""
    model = SR_FOR.get(style, "general")
    if not model:
        return None
    items, seen = [], set()
    for x in shots:
        clip = work / "clips" / f"{x['id']}.mp4"
        if x["type"] == "shot" and _ready(clip):
            items.append({"id": x["id"], "src": str(clip), "out": str(_hd(clip)), "kind": "video",
                          "w": HD_CLIP[0], "h": HD_CLIP[1]})
            continue
        img = work / x["image"]
        if img.exists() and img not in seen and not img.stem.endswith(".hd"):
            seen.add(img)
            items.append({"id": img.stem, "src": str(img), "out": str(_hd(img)), "kind": "image",
                          "w": HD_PICTURE[0], "h": HD_PICTURE[1]})
    return {"items": items, "model": model, "sr_dir": str(anim_engine.MODELS / "upscale")}


def _hd_props(shots: list[dict], work: Path) -> list[dict]:
    """Point the editor at the upscaled clips and pictures that exist."""
    out = []
    for x in shots:
        x = dict(x)
        if x.get("clip"):
            hd = _hd(work / x["clip"])
            if _ready(hd) and not x["clip"].endswith(".hd.mp4"):
                x["clip"] = hd.relative_to(work).as_posix()
                x["clipSeconds"] = round(media_seconds(hd), 3)
                last = hd.with_suffix(".last.jpg")
                x["last"] = last.relative_to(work).as_posix() if last.exists() else x.get("last")
        hd = _hd(work / x["image"])
        if _ready(hd) and not x["image"].endswith(".hd.jpg"):
            x["image"] = hd.relative_to(work).as_posix()
        out.append(x)
    return out


def clip_quality(req: AnimRequest) -> str:
    if req.quality in CLIP_SIZES:
        return req.quality
    vram = float(anim_engine.probe().get("vram_gb") or 0)
    return "fast" if vram < 6 else "standard"


def _frames(seconds: float, longest: float = 5.0, fps: int = 24) -> int:
    """Frames to generate for a shot shown `seconds` long: up to `longest` s (longer shots slow the clip down a
    little and then hold its last frame), always 8k+1 for LTX."""
    target = min(longest, max(2.0, seconds))
    return min(121, max(25, math.ceil(target * fps / 8) * 8 + 1))


def timeline(sc: AnimScript, req: AnimRequest, cfg: Config, work: Path, progress: Progress, seed: int) -> dict:
    """Record the voice and lay out every card and shot (times, words, emphasis, sounds). Pictures and clips are
    filled in later by the AI stages; their file names are fixed here."""
    progress("Recording the voiceover")
    plan: list[tuple[int, AShot]] = [(-1, sh) for sh in sc.cold_open]
    plan += [(ci, sh) for ci, ch in enumerate(sc.chapters) for sh in ch.shots]
    voice = req.voice if req.voice in VOICES else "en-US-AndrewMultilingualNeural"
    audio: list = [None] * len(plan)
    i = 0
    while i < len(plan):  # one take per run of lines in the same tone (see toon.TONES)
        j = i
        while j + 1 < len(plan) and plan[j + 1][1].tone == plan[i][1].tone:
            j += 1
        pace, pitch, loud = TONES.get(plan[i][1].tone, (0, 0, 0))
        audio[i:j + 1] = synthesize_scenes([sh.line for _, sh in plan[i:j + 1]], voice, work / "audio" / f"take{i:03d}",
                                           cfg.tts_engine, cfg.kokoro_voice, f"{max(-30, min(50, req.speed + pace)):+d}%",
                                           f"{pitch:+d}Hz", f"{loud:+d}%")
        i = j + 1
    sfx = write_sfx(work / "sfx")
    sfx.update(media.uploaded_for(cfg, list(sfx), work / "sfx"))
    rel = lambda p: Path(p).relative_to(work).as_posix()  # noqa: E731
    cues, spoken, used, shots = [], [], {}, []
    cue = lambda name, at, vol: cues.append({"src": rel(sfx[name]), "at": round(max(0.0, at), 3), "volume": vol, "name": name}) if name in sfx else None  # noqa: E731
    t, hook_end, titled = 0.0, 0.0, False
    chapter_at: dict[int, float] = {}
    last_tr = ""
    for n, ((ci, sh), sa) in enumerate(zip(plan, audio)):
        if ci >= 0 and ci not in chapter_at:
            if not titled:  # the title card, once, after the cold open
                titled, hook_end = True, t
                shots.append({"id": "title", "type": "title", "start": round(t, 3), "duration": TITLE_SECONDS,
                              "image": "keyframes/title.jpg", "cardText": sc.title, "chapter": -1, "transition": "flash"})
                cue("whoosh", t - 0.15, 0.6)
                cue("impact", t + 0.2, 0.7)
                cue("shimmer", t + 0.5, 0.45)
                t += TITLE_SECONDS
            chapter_at[ci] = t
            ch = sc.chapters[ci]
            first = next(k for k, (cj, _) in enumerate(plan) if cj == ci)
            shots.append({"id": f"card{ci + 1}", "type": "chapter", "start": round(t, 3), "duration": CHAPTER_SECONDS,
                          "image": f"keyframes/s{first:03d}.jpg", "cardText": ch.card_text or ch.title,
                          "chapterNo": ci + 1, "chapters": len(sc.chapters), "chapter": ci, "transition": "dip"})
            cue("whoosh", t + 0.1, 0.45)
            t += CHAPTER_SECONDS
        imp = sh.importance
        lead = 0.45 if imp == "critical" or sh.kind == "reveal" else 0.15
        talk = media_seconds(sa.path)
        tail = 0.65 if "pause" in sh.emphasis_fx else 0.25
        duration = round(max(2.2, lead + talk + tail), 3)
        span = _find_phrase(sa.words, sh.emphasis) if sh.emphasis.strip() else None
        emph = {"text": sh.emphasis.strip()[:48], "at": round(lead + span[0], 3), "end": round(lead + span[1], 3)} if span else None
        tr = sh.transition if not (sh.transition == last_tr and sh.transition != "cut") else "cut"
        last_tr = tr
        shot = {"id": f"s{n:03d}", "type": "shot", "start": round(t, 3), "duration": duration, "lead": lead,
                "audio": rel(sa.path), "text": sh.line,
                "words": [{"text": w.text, "start": round(w.start, 3), "end": round(w.end, 3)} for w in sa.words],
                "chapter": ci, "image": f"keyframes/s{n:03d}.jpg", "clip": None, "camera": sh.camera, "transition": tr,
                "importance": imp, "emphasis": emph, "emphasisFx": list(dict.fromkeys(sh.emphasis_fx))[:4] if emph else [],
                "onScreen": sh.on_screen.strip()[:28] or None}
        loud = {"low": 0.5, "medium": 0.6, "high": 0.75, "critical": 0.85}[imp]
        if tr in TRANSITION_SOUND and shots:
            name, vol = TRANSITION_SOUND[tr]
            cue(name, t - 0.05, vol)
        if emph and imp in ("high", "critical"):
            cue("impact" if imp == "critical" else "pop", t + emph["at"], loud)
            if imp == "critical":
                cue("shimmer", t + emph["at"] + 0.15, 0.45)
        cues += media.resolve_cues(sh.sounds, sa.words, t + lead, cfg, work / "sfx", rel, 2, used)
        spoken += [(t + lead + w.start, t + lead + w.end) for w in sa.words]
        shots.append(shot)
        t += duration
    return {"shots": shots, "duration": round(t + 1.0, 3), "hookEnd": round(hook_end, 3), "chapterAt": chapter_at,
            "speech": media.speech_spans(spoken), "cues": cues}


# ---------- the AI stages ----------

def _motion_wanted(shot: dict, motion: str) -> bool:
    if shot["type"] != "shot" or motion == "stills":
        return False
    return motion == "full" or shot["chapter"] < 0 or shot["importance"] in ("high", "critical")


def keyframe_job(sc: AnimScript, tl: dict, style: str, work: Path, seed: int, fixes: dict | None = None) -> dict:
    """`fixes`: pictures the picture check sent back, {id: {"prompt": easier scene, "round": n}}: drawn again from
    that prompt with a new seed."""
    fixes = fixes or {}
    look = f"{ART_STYLES[style][0]}, {sc.style_notes.strip()}".strip(", ")
    designs = {c.id: c for c in sc.characters}
    chars = [{"id": f"char-{c.id}", "out": str(work / "keyframes" / f"char-{c.id}.jpg"), "seed": seed + 7 + k,
              "prompt": f"Character design of {c.name}: {c.design}. Full body, standing, front view, centered, plain "
                        f"light background. {look}"} for k, c in enumerate(sc.characters)]
    plan = [sh for sh in sc.cold_open] + [sh for ch in sc.chapters for sh in ch.shots]
    items = [{"id": "title", "out": str(work / "keyframes" / "title.jpg"), "seed": seed + 1,
              "prompt": f"{sc.title_scene}. {look}, cinematic composition, wide shot"}]
    shot_rows = [x for x in tl["shots"] if x["type"] == "shot"]
    for n, (row, sh) in enumerate(zip(shot_rows, plan)):
        cast = [designs[c] for c in sh.characters if c in designs][:2]
        who = " ".join(f"{c.name}: {c.design}" for c in cast)
        item = {"id": row["id"], "out": str(work / row["image"]), "seed": seed + 100 + n,
                "prompt": f"{sh.scene} {who} {look}, cinematic composition, highly detailed".strip()}
        if cast:
            item["ref"] = str(work / "keyframes" / f"char-{cast[0].id}.jpg")
        if sh.same_place and n > 0:
            item.update(init=str(work / shot_rows[n - 1]["image"]), strength=0.62)
        items.append(item)
    for it in chars + items:
        fix = fixes.get(it["id"])
        if fix:
            it["seed"] += 1000 * int(fix.get("round", 1))
            it["prompt"] = (f"Character design: {fix['prompt']}. Full body, standing, front view, centered, plain light "
                            f"background. {look}" if it["id"].startswith("char-") else
                            f"{fix['prompt']} {look}, cinematic composition, highly detailed")
            it.pop("init", None)  # drawn fresh, not from the shot before
    return {"characters": chars, "shots": items, "negative": NEGATIVE, "width": 1344, "height": 768, "steps": 4}


# ---------- the picture check: Claude looks at every picture before anything is animated ----------

class PicIssue(BaseModel):
    id: str = Field(description="The label printed on the picture, e.g. s012 or char-mira.")
    problem: str = Field(description="What is wrong, a few words: 'man on the left has no head'.")
    prompt: str = Field(description="A new picture prompt for it, 25-70 words: the same moment, made easy to draw "
                        "(see the rules). No art-style words: the style is added.")


class PicReview(BaseModel):
    broken: list[PicIssue] = Field(default_factory=list)


PIC_SYSTEM = """You check AI-drawn pictures for an animated film before they are animated (each one becomes a moving clip, minutes of work, so a broken picture must be caught now). Each tile has its label in the corner and the line it illustrates is listed in the prompt. Flag only defects a viewer would notice: a person without a head or face, a face cut off by the frame edge or melted, extra or missing arms, legs or fingers, bodies merged or duplicated, a recurring character drawn as someone else, garbled writing or fake letters, or a picture that plainly shows something else than its line. Style quirks, soft backgrounds and small imperfections are fine; when unsure, let it pass. For each broken picture give its label, the problem, and a new prompt for the same moment that the image model can draw: at most two people near the camera, each whole and inside the frame, faces fully visible (front or three-quarter view), a crowd only small in the distance, simple hands, nothing written."""
PIC_ROUNDS = 2  # check, redraw what failed, check those again, redraw once more
PIC_TILE = (640, 360)
PIC_PER_SHEET = 12


def _pic_sheets(pics: list[tuple[str, Path]], out_dir: Path) -> list[Path]:
    from PIL import Image, ImageDraw, ImageFont

    try:
        font = ImageFont.load_default(size=30)
    except TypeError:  # Pillow before 10.1
        font = ImageFont.load_default()
    sheets = []
    for k in range(0, len(pics), PIC_PER_SHEET):
        part = pics[k:k + PIC_PER_SHEET]
        rows = (len(part) + 2) // 3
        sheet = Image.new("RGB", (PIC_TILE[0] * 3, PIC_TILE[1] * rows), "black")
        for i, (label, path) in enumerate(part):
            tile = Image.open(path).convert("RGB")
            tile.thumbnail((PIC_TILE[0] - 6, PIC_TILE[1] - 6))
            x, y = (i % 3) * PIC_TILE[0] + 3, (i // 3) * PIC_TILE[1] + 3
            sheet.paste(tile, (x, y))
            d = ImageDraw.Draw(sheet)
            d.rectangle([x, y, x + 16 + 18 * len(label), y + 42], fill=(0, 0, 0))
            d.text((x + 8, y + 4), label, fill=(255, 220, 0), font=font)
        path = out_dir / f"picture-check-{k // PIC_PER_SHEET + 1}.jpg"
        sheet.save(path, quality=88)
        sheets.append(path)
    return sheets


def check_pictures(cfg: Config, sc: AnimScript, tl: dict, work: Path, ids: list[str] | None = None) -> list[PicIssue]:
    """The pictures Claude finds broken (all of them, or only `ids`)."""
    plan = [sh for sh in sc.cold_open] + [sh for ch in sc.chapters for sh in ch.shots]
    rows = [x for x in tl["shots"] if x["type"] == "shot"]
    lines = {"title": f"title card behind \"{sc.title}\""}
    lines.update({f"char-{c.id}": f"character sheet of {c.name}: {c.design}" for c in sc.characters})
    lines.update({row["id"]: f"{sh.line} (meant: {sh.scene})" for row, sh in zip(rows, plan)})
    pics = []
    for label in lines:
        path = work / "keyframes" / f"{label}.jpg"
        if path.exists() and (ids is None or label in ids):
            pics.append((label, path))
    if not pics:
        return []
    sheets = _pic_sheets(pics, work)
    names = {c.name for c in sc.characters}
    prompt = (f"Film: {sc.title}. Recurring characters: {', '.join(names) or 'none'}.\n"
              + "\n".join(f"{label}: {lines[label]}" for label, _ in pics)
              + f"\n\n{len(sheets)} contact sheet(s) attached. List only the broken pictures.")
    review = ask(cfg.ai_backend, cfg.claude_model, PIC_SYSTEM, prompt, PicReview, images=sheets,
                 effort=cfg.claude_effort, timeout=900)
    known = {label for label, _ in pics}
    return [b for b in review.broken if b.id in known and b.prompt.strip()]


def _picture_rounds(cfg: Config, sc: AnimScript, tl: dict, style: str, work: Path, seed: int, state: dict,
                    progress: Progress, save) -> list[dict]:
    """Check every picture, redraw the broken ones from easier prompts, check those again (PIC_ROUNDS)."""
    from .pipeline import Paused

    fixes: dict = state.get("pic_fixes") or {}
    found: list[dict] = state.get("pic_found") or []
    ids = None
    for rnd in range(int(state.get("pic_round") or 0), PIC_ROUNDS):
        progress("Checking the pictures for broken people and objects" if ids is None
                 else f"Checking the {len(ids)} redrawn pictures")
        try:
            broken = check_pictures(cfg, sc, tl, work, ids)
        except Paused:
            raise
        except Exception as exc:  # noqa: BLE001 - a check that can't run never stops the video
            log.warning("Picture check failed: %s", exc)
            progress(f"Picture check skipped ({str(exc)[:120]})")
            break
        if not broken:
            break
        for b in broken:
            fixes[b.id] = {"prompt": b.prompt.strip(), "round": rnd + 1}
            found.append({"id": b.id, "problem": b.problem, "round": rnd + 1})
            for f in (work / "keyframes" / f"{b.id}.jpg", work / "keyframes" / f"{b.id}.jpg.ok"):
                f.unlink(missing_ok=True)
        progress(f"Redrawing {len(broken)} picture(s): " + "; ".join(f"{b.id} {b.problem}" for b in broken[:6]))
        save(pic_fixes=fixes, pic_found=found, pic_round=rnd + 1)
        anim_engine.run_stage("keyframes", keyframe_job(sc, tl, style, work, seed, fixes), work, progress,
                              "Drawing the pictures")
        ids = [b.id for b in broken]
    save(pic_fixes=fixes, pic_found=found, pic_round=PIC_ROUNDS, pics_checked=True)
    return found


def clip_jobs(sc: AnimScript, tl: dict, style: str, req: AnimRequest, work: Path, seed: int) -> tuple[dict, dict]:
    look = ART_STYLES[style][0]
    plan = [sh for sh in sc.cold_open] + [sh for ch in sc.chapters for sh in ch.shots]
    rows = [x for x in tl["shots"] if x["type"] == "shot"]
    W, H, longest = CLIP_SIZES[clip_quality(req)]
    shots = []
    for n, (row, sh) in enumerate(zip(rows, plan)):
        if not _motion_wanted(row, req.motion):
            continue
        shots.append({"id": row["id"], "image": str(work / row["image"]), "out": str(work / "clips" / f"{row['id']}.mp4"),
                      "emb": str(work / "clips" / f"{row['id']}.pt"), "frames": _frames(row["duration"], longest), "seed": seed + 500 + n,
                      "prompt": f"{sh.motion.strip()} {CAMERAS.get(sh.camera, '')}. {sh.scene} {look}. Smooth, natural "
                                f"animation, consistent character, no text."})
    return {"shots": shots}, {"shots": shots, "width": W, "height": H, "fps": 24}


def music_job(sc: AnimScript, tl: dict, work: Path, seed: int) -> dict:
    tracks = []
    if tl["hookEnd"] > 0:
        tracks.append({"id": "hook", "out": str(work / "music" / "hook.wav"), "seed": seed + 11, "bpm": sc.hook_bpm,
                       "caption": f"{sc.hook_music}, instrumental, cinematic trailer energy",
                       "duration": round(min(120, tl["hookEnd"] + TITLE_SECONDS + 2), 1)})
    starts = sorted(tl["chapterAt"].items())
    for k, (ci, a) in enumerate(starts):
        b = starts[k + 1][1] if k + 1 < len(starts) else tl["duration"]
        ch = sc.chapters[ci]
        tracks.append({"id": f"ch{ci + 1}", "out": str(work / "music" / f"ch{ci + 1}.wav"), "seed": seed + 20 + ci,
                       "bpm": ch.bpm, "caption": f"{ch.music}, instrumental, no vocals",
                       "duration": round(min(360, b - a + 3), 1)})
    return {"tracks": tracks, "ace_root": str(anim_engine.ENGINE)}


def _loudnorm(path: Path) -> None:
    """Generated songs come out at their own loudness; bring each to the same level under the voice."""
    tmp = path.with_suffix(".norm.wav")
    proc = subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(path), "-af", "loudnorm=I=-20:TP=-2:LRA=11",
                           "-ar", "48000", "-ac", "2", str(tmp)], capture_output=True)
    if proc.returncode == 0 and tmp.exists():
        tmp.replace(path)


def _composed_hook(tl: dict, work: Path, seed: int) -> Path:
    from . import music as composer

    (work / "music").mkdir(parents=True, exist_ok=True)
    style = random.Random(seed).choice(composer.TRAILERS)
    return composer.trailer(style, tl["hookEnd"] + TITLE_SECONDS, [], seed, work / "music" / "hook-composed.wav")


def _composed_chapter(sc: AnimScript, ci: int, seconds: float, work: Path, seed: int) -> Path:
    from . import music as composer
    from .toon import MusicMood

    (work / "music").mkdir(parents=True, exist_ok=True)
    moods = list(MusicMood.__args__)
    return composer.compose(moods[(seed + ci) % len(moods)], [composer.Section(0, seconds, sc.chapters[ci].intensity)],
                            seconds, seed + ci, work / "music" / f"ch{ci + 1}-composed.wav")


def _music_fallback(sc: AnimScript, tl: dict, work: Path, seed: int, cfg: Config) -> tuple[str | None, list[dict], str]:
    """Without the engine (or if ACE-Step made nothing): a trailer for the hook and a composed track per chapter."""
    rel = lambda p: Path(p).relative_to(work).as_posix()  # noqa: E731
    hook = rel(_composed_hook(tl, work, seed)) if tl["hookEnd"] > 0 else None
    parts = []
    starts = sorted(tl["chapterAt"].items())
    for k, (ci, a) in enumerate(starts):
        b = starts[k + 1][1] if k + 1 < len(starts) else tl["duration"]
        path = _composed_chapter(sc, ci, b - a + 2, work, seed)
        parts.append({"src": rel(path), "from": round(max(0.0, a - 1.0), 3), "to": round(min(tl["duration"], b + 1.0), 3)})
    return hook, parts, "composed"


def make_music(sc: AnimScript, tl: dict, work: Path, seed: int, cfg: Config, progress: Progress) -> tuple[str | None, list[dict], str]:
    rel = lambda p: Path(p).relative_to(work).as_posix()  # noqa: E731
    mine = {m.name for m in media.music(cfg) if m.path is not None}
    starts = sorted(tl["chapterAt"].items())
    if sc.music_track in mine and media.fresh_track(cfg, sc.music_track):  # the user's own track, picked by Claude
        progress(f"Music: your track '{sc.music_track}'")
        track = media.pick_music(cfg, sc.music_track, work / "music", tl["duration"])
        media.note_music(cfg, sc.music_track)
        a = starts[0][1] if starts else 0.0
        hook, _, _ = _music_fallback(sc, {**tl, "chapterAt": {}}, work, seed, cfg)
        return hook, [{"src": rel(track), "from": round(max(0.0, a - 1.0), 3), "to": tl["duration"]}], sc.music_track
    if anim_engine.installed():
        job = music_job(sc, tl, work, seed)
        try:
            anim_engine.run_stage("music", job, work, progress, "Music (ACE-Step)")
        except Exception as exc:  # noqa: BLE001 - music must never stop the video
            from .stopper import Paused
            if isinstance(exc, Paused):
                raise
            progress(f"Music: ACE-Step didn't finish ({str(exc)[:300]}); composing only the tracks it didn't make")
        # every track ACE-Step finished is used, even when it stopped before the last (7 of 8 were once thrown away)
        made = {m["id"]: Path(m["out"]) for m in job["tracks"] if _ready(Path(m["out"]))}
        if made:
            for path in made.values():
                _loudnorm(path)
            hook = None
            if tl["hookEnd"] > 0:
                hook = rel(made["hook"] if "hook" in made else _composed_hook(tl, work, seed))
            parts = []
            for k, (ci, a) in enumerate(starts):
                b = starts[k + 1][1] if k + 1 < len(starts) else tl["duration"]
                ace = made.get(f"ch{ci + 1}")
                parts.append({"src": rel(ace or _composed_chapter(sc, ci, b - a + 2, work, seed)),
                              "from": round(max(0.0, a - 1.0), 3), "to": round(min(tl["duration"], b + (1.5 if ace else 1.0)), 3)})
            total = len(job["tracks"])
            return hook, parts, ("generated (ACE-Step)" if len(made) == total
                                 else f"generated (ACE-Step) for {len(made)} of {total} tracks, composed for the rest")
    return _music_fallback(sc, tl, work, seed, cfg)


# ---------- props ----------

def props_for(sc: AnimScript, tl: dict, style: str, req: AnimRequest, cfg: Config, work: Path,
              hook: str | None, parts: list[dict], music_choice: str) -> dict:
    shots = []
    for x in tl["shots"]:
        x = dict(x)
        clip = work / "clips" / f"{x['id']}.mp4"
        if x["type"] == "shot" and clip.exists() and Path(str(clip) + ".ok").exists():
            x["clip"] = f"clips/{x['id']}.mp4"
            x["clipSeconds"] = round(media_seconds(clip), 3)
            last = clip.with_suffix(".last.jpg")
            x["last"] = f"clips/{last.name}" if last.exists() else None
        if not (work / x["image"]).exists():  # a picture that couldn't be made: the nearest one before it
            x["image"] = next((s["image"] for s in reversed(shots) if (work / s["image"]).exists()), x["image"])
        shots.append(x)
    shots = _hd_props(shots, work)
    accent = ART_STYLES[style][1]
    props = {"fps": cfg.fps, "duration": tl["duration"], "title": sc.title, "style": style, "accent": accent,
             "shots": shots, "captions": req.captions, "watermark": req.watermark.strip()[:40] or None,
             "hookMusic": hook, "hookEnd": tl["hookEnd"], "musicParts": parts, "musicChoice": music_choice,
             "speech": tl["speech"], "cues": tl["cues"]}
    props["sfxLevels"] = media.level_sounds(props, work, [s["audio"] for s in shots if s.get("audio")])
    return props


# ---------- the run ----------

def run_anim(cfg: Config, req: AnimRequest, progress: Progress = log.info, resume: str | None = None) -> dict:
    from .fsutil import move
    from .llm import meter_records, summarize_usage
    from .pipeline import _render_slot, pause_point, slugify

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    work = cfg.output_dir / resume if resume else cfg.output_dir / f"{stamp}-{uuid.uuid4().hex[:4]}-anim-working"
    work.mkdir(parents=True, exist_ok=True)
    progress(f"Saving progress in {work.name}")
    state = json.loads((work / CHECKPOINT).read_text(encoding="utf-8")) if (work / CHECKPOINT).exists() else {}
    stamp = state.get("stamp", stamp)
    seed = state.get("seed") or int(uuid.uuid4().int % 2**31)

    def save(**changes) -> None:
        state.update(changes, stamp=stamp, seed=seed, request=asdict(req))
        (work / CHECKPOINT).write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        pause_point()

    if not anim_engine.installed():  # every mode draws its pictures with it
        raise RuntimeError("The AI engine isn't installed yet: open the Anim tab and press 'Install the AI engine'")
    if state.get("script"):
        sc = AnimScript.model_validate(state["script"])
        issues, findings = state.get("issues", []), state.get("findings", [])
        progress("Resuming: script and fact-check already done")
    else:
        progress("Claude is researching and writing the script and storyboard")
        sc = write_script(cfg, req)
        if req.topic.strip():
            twin = repeats.too_close(sc.subject, sc.title, [x for x in repeats.made(cfg) if x.get("kind", "short") in repeats.EVERY])
            if twin:
                progress(f"Note: a video like this exists already (\"{twin.get('title')}\"); keeping your topic")
            repeats.claim(cfg, {"title": sc.title, "subject": sc.subject, "topic": req.topic.strip(), "kind": "long"})
        else:
            sc = repeats.guard(cfg, sc, repeats.EVERY, lambda why: write_script(cfg, req, why), progress, kind="long")
        (work / "draft.json").write_text(sc.model_dump_json(indent=1), encoding="utf-8")
        sc, issues, findings = check_facts(cfg, sc, progress)
        save(stage="scripted", script=sc.model_dump(), issues=issues, findings=findings)
    style = state.get("style") or _style_of(sc, req, cfg, seed)
    if state.get("timeline") and all((work / s["audio"]).exists() for s in state["timeline"]["shots"] if s.get("audio")):
        tl = state["timeline"]
        tl["chapterAt"] = {int(k): v for k, v in tl["chapterAt"].items()}
        progress("Resuming: voiceover already recorded")
    else:
        tl = timeline(sc, req, cfg, work, progress, seed)
        save(stage="voiced", timeline=tl, style=style)
    progress(f"Art style: {style}. {len([s for s in tl['shots'] if s['type'] == 'shot'])} shots, "
             f"{tl['duration'] / 60:.1f} min")
    anim_engine.run_stage("keyframes", keyframe_job(sc, tl, style, work, seed, state.get("pic_fixes")), work, progress,
                          "Drawing the pictures")
    save(stage="pictures")
    pic_found = state.get("pic_found") or []
    if not state.get("pics_checked") and not any((work / "clips").glob("*.mp4.ok")):  # a redrawn picture's clip
        # would be the old one, so a video resumed after animation began (older checkpoints) keeps its pictures
        pic_found = _picture_rounds(cfg, sc, tl, style, work, seed, state, progress, save)
    emb, clipjob = clip_jobs(sc, tl, style, req, work, seed)
    if clipjob["shots"]:
        q = clip_quality(req)
        progress(f"Clips: {q}, {CLIP_SIZES[q][0]}x{CLIP_SIZES[q][1]}, up to {CLIP_SIZES[q][2]:.0f} s each")
        anim_engine.run_stage("embed", emb, work, progress, "Reading the motion prompts")
        anim_engine.run_stage("clips", clipjob, work, progress, "Animating the shots")
    up = upscale_job(tl["shots"], style, work) if req.upscale else None
    if up and up["items"]:
        anim_engine.run_stage("upscale", up, work, progress, "Sharpening to full HD")
    save(stage="clips")
    if state.get("music"):
        hook, parts, music_choice = state["music"]
    else:
        hook, parts, music_choice = make_music(sc, tl, work, seed, cfg, progress)
        save(stage="music", music=[hook, parts, music_choice])
    props = props_for(sc, tl, style, req, cfg, work, hook, parts, music_choice)
    progress(f"Editing the video ({props['duration'] / 60:.1f} min)")
    cli = _remotion_cli()
    if cli is None:
        raise RuntimeError("Node.js or the Remotion packages are not installed (run start.bat / start.sh)")
    out = work / "reel.mp4"
    if not (state.get("stage") == "rendered" and out.exists()):
        with _render_slot(cfg):
            _render_remotion(cli, props, out, composition="Anim", crf=18, progress=progress)
        save(stage="rendered")
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", "8", "-i", str(out), "-frames:v", "1", "-q:v", "3",
                    str(work / "thumbnail.jpg")], check=False)
    progress("Verifying video quality")
    info = probe(out)
    issues = list(issues)
    sources, dropped = verify_sources(sc.sources)
    if not sources:
        issues.append("No source link could be opened; check the facts before posting.")
    if (info.get("width"), info.get("height")) != (1920, 1080):
        issues.append(f"Resolution is {info.get('width')}x{info.get('height')}, expected 1920x1080.")
    if not info.get("has_audio"):
        issues.append("No audio track.")
    animated = sum(1 for s in props["shots"] if s.get("clip"))
    total = sum(1 for s in props["shots"] if s["type"] == "shot")
    _remember(cfg, {"title": sc.title, "subject": sc.subject, "style": style, "notes": sc.style_notes,
                    "music": "; ".join(ch.music[:40] for ch in sc.chapters[:3]),
                    "characters": [c.name for c in sc.characters]})
    final = cfg.output_dir / f"{stamp}-{slugify(sc.title)}-anim"
    (work / CHECKPOINT).unlink(missing_ok=True)
    move(work, final)
    narration = " ".join(sh.line for sh in sc.cold_open) + " " + " ".join(sh.line for ch in sc.chapters for sh in ch.shots)
    report = {
        "id": final.name, "format": "long", "length": "long" if props["duration"] >= 420 else "medium",
        "source": "anim", "topic": sc.subject, "subject": sc.subject, "topic_source": "animated video",
        "style": "facts", "category": sc.category if sc.category in CATEGORIES else "",
        "title": sc.title, "why_chosen": sc.hook, "narration": narration.strip(), "created_at": stamp,
        "verified": not issues, "score": None, "issues": issues, "checks": {"probe": info}, "attempts": 1,
        "video": str(final / "reel.mp4"), "thumbnail": str(final / "thumbnail.jpg"),
        "duration_seconds": round(props["duration"], 1), "editor": "remotion (Anim)", "captions": req.captions,
        "voice": req.voice, "youtube_title": sc.title[:100],
        "youtube_description": with_sources(sc.youtube_description.strip(), sources, []),
        "youtube_hashtags": sc.hashtags[:3], "youtube_tags": sc.tags, "caption": sc.youtube_description.strip(),
        "hashtags": sc.hashtags, "fact_check": findings, "sources": sources, "sources_unreachable": dropped,
        "art_style": style, "motion": req.motion, "animated_shots": f"{animated} of {total}", "music": music_choice,
        "seed": seed,
        "upscaled": up["model"] if up and up["items"] else None, "picture_check": pic_found,
        "characters": [c.model_dump() for c in sc.characters],
    }
    (final / "script.json").write_text(sc.model_dump_json(indent=2), encoding="utf-8")
    (final / "props.json").write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
    report["usage"] = summarize_usage(meter_records())
    (final / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    progress("Done" if not issues else "Done, but it did not pass every check — review before posting")
    return report


def sharpen_video(cfg: Config, folder: Path, progress: Progress = log.info) -> dict:
    """A finished animated video re-edited with its clips and pictures upscaled to full HD: no new animation,
    no Claude. The old edit stays as reel-sd.mp4."""
    from .pipeline import _render_slot, set_pause_check

    set_pause_check(getattr(progress, "should_pause", None))
    report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
    props = json.loads((folder / "props.json").read_text(encoding="utf-8"))
    if not anim_engine.installed():
        raise RuntimeError("The AI engine isn't installed: open the Anim tab and press 'Install the AI engine'")
    up = upscale_job(props["shots"], report.get("art_style", ""), folder)
    if not up:
        raise RuntimeError("Pixel art stays as it is: an upscaler would smear its pixels")
    if up["items"]:
        anim_engine.run_stage("upscale", up, folder, progress, "Sharpening to full HD")
    props["shots"] = _hd_props(props["shots"], folder)
    cli = _remotion_cli()
    if cli is None:
        raise RuntimeError("Node.js or the Remotion packages are not installed (run start.bat / start.sh)")
    progress(f"Editing the video ({props['duration'] / 60:.1f} min)")
    out = folder / "reel-hd.mp4"
    with _render_slot(cfg):
        _render_remotion(cli, props, out, composition="Anim", crf=18, progress=progress)
    progress("Verifying video quality")
    info = probe(out)
    if (info.get("width"), info.get("height")) != HD_CLIP or not info.get("has_audio"):
        raise RuntimeError(f"The new edit came out {info.get('width')}x{info.get('height')}"
                           + ("" if info.get("has_audio") else " without sound") + "; the old video is kept")
    if not (folder / "reel-sd.mp4").exists():
        (folder / "reel.mp4").replace(folder / "reel-sd.mp4")
    out.replace(folder / "reel.mp4")
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", "8", "-i", str(folder / "reel.mp4"), "-frames:v", "1",
                    "-q:v", "3", str(folder / "thumbnail.jpg")], check=False)
    report.update(upscaled=up["model"], checks={**report.get("checks", {}), "probe": info})
    (folder / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    progress("Done: sharpened to full HD (the old edit is kept as reel-sd.mp4)")
    return report


def music_redoable(report: dict) -> bool:
    """Composed music (ACE-Step failed or wasn't installed then), or only some tracks generated."""
    return report.get("source") == "anim" and (report.get("music") == "composed"
                                               or str(report.get("music", "")).startswith("generated (ACE-Step) for"))


def redo_music(cfg: Config, folder: Path, progress: Progress = log.info) -> dict:
    """A finished animated video with its music made by ACE-Step again: the tracks it already finished are kept
    (on the user's laptop 7 of 8 were made, then the model crashed and an older version composed all of it), only
    the missing ones are generated, and the new soundtrack is mixed and put under the same picture (no new edit)."""
    import hashlib

    from .pipeline import set_pause_check
    from .soundtrack import mix

    set_pause_check(getattr(progress, "should_pause", None))
    report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
    props = json.loads((folder / "props.json").read_text(encoding="utf-8"))
    sc = AnimScript.model_validate_json((folder / "script.json").read_text(encoding="utf-8"))
    if not anim_engine.installed():
        raise RuntimeError("The AI engine isn't installed: open the Anim tab and press 'Install the AI engine'")
    tl = {"hookEnd": props["hookEnd"], "duration": props["duration"],
          "chapterAt": {int(s_["chapter"]): s_["start"] for s_ in props["shots"] if s_.get("type") == "chapter"}}
    seed = int(report.get("seed") or int(hashlib.sha1(folder.name.encode()).hexdigest(), 16) % 2**31)
    hook, parts, choice = make_music(sc, tl, folder, seed, cfg, progress)
    if choice == "composed":
        raise RuntimeError("ACE-Step made no track this time either; the video keeps its music")
    props.update(hookMusic=hook, musicParts=parts, musicChoice=choice)
    progress("Mixing the new soundtrack")
    sound, out = folder / "soundtrack-new.wav", folder / "reel-newmusic.mp4"
    mix(props, "Anim", folder, sound, FFMPEG)
    proc = subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(folder / "reel.mp4"), "-i", str(sound),
                           "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "320k", "-shortest",
                           "-movflags", "+faststart", str(out)], capture_output=True, text=True)
    sound.unlink(missing_ok=True)
    info = probe(out) if proc.returncode == 0 and out.exists() else {}
    if not info.get("has_audio") or abs(float(info.get("duration") or 0) - props["duration"]) > 1.0:
        out.unlink(missing_ok=True)
        raise RuntimeError(f"Putting the new music under the video failed{': ' + proc.stderr[-300:] if proc.stderr else ''}; "
                           "the old video is kept")
    out.replace(folder / "reel.mp4")
    (folder / "props.json").write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
    report.update(music=choice, seed=seed, checks={**report.get("checks", {}), "probe": info})
    (folder / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    progress(f"Done: the music is now {choice}")
    return report


def run_anim_job(cfg: Config, req: AnimRequest, count: int, progress: Progress, resume: list[str] | None = None) -> list[dict]:
    """The app's job: `count` videos one after another (or resume saved ones)."""
    from .llm import set_limit_reporter, start_meter, usage_line
    from .pipeline import Paused, _video_slot, done_line, set_pause_check

    reports = []
    should_pause = getattr(progress, "should_pause", None)
    todo = [(r,) for r in (resume or [])] or [(None,)] * count
    for i, (folder,) in enumerate(todo):
        vp = (lambda m, n=i + 1: progress(f"[V{n}] {m}")) if len(todo) > 1 else progress
        with _video_slot(cfg):
            if should_pause and should_pause():
                vp("§skip {}")
                continue
            set_pause_check(should_pause)
            set_limit_reporter(vp)
            start_meter(lambda r, vp=vp: vp(usage_line(r)))
            vp(f"=== Video {i + 1}/{len(todo)} ===")
            try:
                reports.append(run_anim(cfg, req, vp, folder))
                vp(done_line(reports[-1]))
            except Paused:
                vp("Paused: progress saved. Press Resume to carry on from here.")
            except Exception as exc:
                log.exception("Animated video %d failed", i + 1)
                vp(f"Video {i + 1} failed: {exc}")
    return reports


def unfinished_anims(cfg: Config) -> list[str]:
    return sorted(p.parent.name for p in cfg.output_dir.glob(f"*-anim-working/{CHECKPOINT}"))


def music_failed(state: dict) -> bool:
    """The saved music is composed, or only partly from ACE-Step: the AI music step didn't finish."""
    m = state.get("music")
    return bool(m) and len(m) > 2 and (m[2] == "composed" or str(m[2]).startswith("generated (ACE-Step) for"))


def forget_music(work: Path) -> None:
    """'Resume with AI music': the checkpoint forgets its music, so the resumed video runs the music step again
    (the tracks ACE-Step already finished are kept, only the missing ones are made) and edits with it. On the
    user's laptop an older version threw 7 of 8 finished tracks away and composed everything instead."""
    path = work / CHECKPOINT
    state = json.loads(path.read_text(encoding="utf-8"))
    state.pop("music", None)
    if state.get("stage") in ("music", "rendered"):
        state["stage"] = "clips"
    path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def anim_unfinished(cfg: Config) -> list[dict]:
    done = {"scripted": "script and fact-check", "voiced": "script and voiceover", "pictures": "pictures",
            "clips": "pictures and animation", "music": "pictures, animation and music", "rendered": "everything but the checks"}
    out = []
    for folder in unfinished_anims(cfg):
        path = cfg.output_dir / folder / CHECKPOINT
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        script = state.get("script") or {}
        clips_done = len(list((cfg.output_dir / folder / "clips").glob("*.mp4.ok")))
        out.append({"id": folder, "topic": script.get("subject") or (state.get("request") or {}).get("topic") or "Animated",
                    "title": script.get("title", ""), "style": "facts", "length": "anim", "attempt": 1,
                    "done": done.get(state.get("stage") or "", "nothing yet") + (f" ({clips_done} clip{'s' * (clips_done > 1)})" if clips_done else ""),
                    "quality": (state.get("request") or {}).get("quality", "auto"),
                    "motion": (state.get("request") or {}).get("motion", "full"), "updated": path.stat().st_mtime,
                    "music_redo": music_failed(state) and anim_engine.installed(),
                    "music_made": len(list((cfg.output_dir / folder / "music").glob("*.wav.ok")))})
    return out
