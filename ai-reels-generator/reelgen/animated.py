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
    quality: str = "standard"  # standard (832x480 clips) | high (1024x576)
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
                       "bird's-eye...), lighting and mood. Concrete and visual; a metaphor for anything abstract. Never "
                       "text, signs, labels, numbers, logos or screens with writing (the editor adds words).")
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
crowds, nature) so the film breathes.
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


def _frames(seconds: float, fps: int = 24) -> int:
    """Frames to generate for a shot shown `seconds` long: up to 5 s (longer shots slow the clip down a little and
    then hold its last frame), always 8k+1 for LTX."""
    target = min(5.0, max(2.0, seconds))
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
                "onScreen": sh.on_screen.strip()[:28] or None, "frames": _frames(duration)}
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


def keyframe_job(sc: AnimScript, tl: dict, style: str, work: Path, seed: int) -> dict:
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
    return {"characters": chars, "shots": items, "negative": NEGATIVE, "width": 1344, "height": 768, "steps": 4}


def clip_jobs(sc: AnimScript, tl: dict, style: str, req: AnimRequest, work: Path, seed: int) -> tuple[dict, dict]:
    look = ART_STYLES[style][0]
    plan = [sh for sh in sc.cold_open] + [sh for ch in sc.chapters for sh in ch.shots]
    rows = [x for x in tl["shots"] if x["type"] == "shot"]
    shots = []
    for n, (row, sh) in enumerate(zip(rows, plan)):
        if not _motion_wanted(row, req.motion):
            continue
        shots.append({"id": row["id"], "image": str(work / row["image"]), "out": str(work / "clips" / f"{row['id']}.mp4"),
                      "emb": str(work / "clips" / f"{row['id']}.pt"), "frames": row["frames"], "seed": seed + 500 + n,
                      "prompt": f"{sh.motion.strip()} {CAMERAS.get(sh.camera, '')}. {sh.scene} {look}. Smooth, natural "
                                f"animation, consistent character, no text."})
    W, H = (1024, 576) if req.quality == "high" else (832, 480)
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


def _music_fallback(sc: AnimScript, tl: dict, work: Path, seed: int, cfg: Config) -> tuple[str | None, list[dict], str]:
    """Without the engine (or if ACE-Step fails): a trailer for the hook and a composed track per chapter."""
    from . import music as composer
    from .toon import MusicMood

    rel = lambda p: Path(p).relative_to(work).as_posix()  # noqa: E731
    (work / "music").mkdir(parents=True, exist_ok=True)
    hook = None
    if tl["hookEnd"] > 0:
        style = random.Random(seed).choice(composer.TRAILERS)
        hook = rel(composer.trailer(style, tl["hookEnd"] + TITLE_SECONDS, [], seed, work / "music" / "hook-composed.wav"))
    parts = []
    starts = sorted(tl["chapterAt"].items())
    moods = list(MusicMood.__args__)
    for k, (ci, a) in enumerate(starts):
        b = starts[k + 1][1] if k + 1 < len(starts) else tl["duration"]
        mood = moods[(seed + ci) % len(moods)]
        path = composer.compose(mood, [composer.Section(0, b - a + 2, sc.chapters[ci].intensity)], b - a + 2,
                                seed + ci, work / "music" / f"ch{ci + 1}-composed.wav")
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
        try:
            job = music_job(sc, tl, work, seed)
            anim_engine.run_stage("music", job, work, progress, "Music (ACE-Step)")
            for m in job["tracks"]:
                _loudnorm(Path(m["out"]))
            hook = rel(job["tracks"][0]["out"]) if tl["hookEnd"] > 0 else None
            parts = []
            for k, (ci, a) in enumerate(starts):
                b = starts[k + 1][1] if k + 1 < len(starts) else tl["duration"]
                parts.append({"src": rel(work / "music" / f"ch{ci + 1}.wav"), "from": round(max(0.0, a - 1.0), 3),
                              "to": round(min(tl["duration"], b + 1.5), 3)})
            return hook, parts, "generated (ACE-Step)"
        except Exception as exc:  # noqa: BLE001 - music must never stop the video
            from .stopper import Paused
            if isinstance(exc, Paused):
                raise
            progress(f"Music: ACE-Step didn't work ({str(exc)[:160]}); composing instead")
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
    anim_engine.run_stage("keyframes", keyframe_job(sc, tl, style, work, seed), work, progress, "Drawing the pictures")
    save(stage="pictures")
    emb, clipjob = clip_jobs(sc, tl, style, req, work, seed)
    if clipjob["shots"]:
        anim_engine.run_stage("embed", emb, work, progress, "Reading the motion prompts")
        anim_engine.run_stage("clips", clipjob, work, progress, "Animating the shots")
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
        "characters": [c.model_dump() for c in sc.characters],
    }
    (final / "script.json").write_text(sc.model_dump_json(indent=2), encoding="utf-8")
    (final / "props.json").write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
    report["usage"] = summarize_usage(meter_records())
    (final / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    progress("Done" if not issues else "Done, but it did not pass every check — review before posting")
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
                    "done": done.get(state.get("stage") or "", "nothing yet") + (f" ({clips_done} clips)" if clips_done else ""),
                    "updated": path.stat().st_mtime})
    return out
