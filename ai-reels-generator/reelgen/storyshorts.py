"""Shorts Studio (tab "Shorts+"; the module kept its first name, Story Shorts): 9:16 Shorts built from the other
pipelines' pieces in any combination, one Short or a series (part 1, part 2... each at most 30 s, its own hook, its
piece of the story or explanation and a cliffhanger into the next).

Built from the pieces the other pipelines already have, in any combination (tab "Story", job `story_input`):
- the story: Claude writes it (`source: ai`: an original story, a true story fact-checked like every pipeline
  here, or comedy) or it is the user's own text (`source: script`: cut into lines and parts in code, so no spoken
  word changes; one Claude call storyboards it);
- the voice: English, Hinglish or Hindi (Sarvam and the Hindi voices get the mixed script, `hinglish.py`), with
  the words on screen in English or in the voice's language;
- the pictures: AI animation (every shot a clip, or only the key shots), AI pictures moved by the camera, stock
  footage (Pexels, like the Create tab's Shorts), or the long videos' motion graphics (`graphics`: numbers, charts,
  timelines, steps, icons, 3D, photo backdrops, laid out for 9:16 by the Long composition's `vertical` frame);
- what it is: an original story, a true story, an explainer, this week's news or comedy (true ones fact-checked).
The AI stages (pictures, picture check, clips, upscale, music) run once over the whole series, then every part is
edited on its own with the Anim composition in 9:16 (`vertical`), so it lands in the library as its own Short.

Its own checkpoint (`story-checkpoint.json` in `*-story-working`); finished parts go to `<stamp>-<slug>-p<N>`
folders (report `source: "storyshorts"`, `series`, `part`, `parts`), the shared files to `*-story-files`.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import shutil
import subprocess
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal

from pydantic import BaseModel, Field, create_model

from . import aimusic, anim_engine, animated, media, repeats
from .animated import ART_STYLES, CAMERAS, NEGATIVE, TRANSITION_SOUND, ACharacter, Camera, Fx, Transition
from .categories import CATEGORIES
from .config import Config
from .llm import ask
from .longform import (LBeat, LChapter, LongScript, LSource, LVisual, _visual_text, build_long, object_icon,
                       verify_sources, with_sources)
from .script_writer import AI_CLICHES, SoundCue, news_rules
from .sfx import write_sfx
from .toon import MusicMood, ScriptCheck
from .verify import probe
from .video import FFMPEG, _remotion_cli, _render_remotion, media_seconds
from .voice import synthesize_scenes

log = logging.getLogger(__name__)
Progress = Callable[[str], None]

CHECKPOINT = "story-checkpoint.json"
LANGUAGES = ("english", "hinglish", "hindi")
VISUALS = ("anim", "key", "pictures", "footage", "graphics")  # graphics: the long videos' motion graphics, 9:16
KINDS = ("story", "facts", "explainer", "news", "comedy")
TRUE_KINDS = ("facts", "explainer", "news")  # written with web search and fact-checked
WPS = {"english": 2.7, "hinglish": 2.5, "hindi": 2.4}  # spoken words a second (edge +8%, Sarvam at pace 1)
MAX_PARTS = 6
PORTRAIT = (768, 1344)  # SDXL's own 9:16 size
HD_CLIP, HD_PICTURE = (1080, 1920), (1440, 2560)
FOOTAGE_ACCENTS = ["#FFD23F", "#4CC9F0", "#F72585", "#06D6A0", "#FF9F1C"]

LANGUAGE_RULES = {
    "english": "Simple, natural spoken English: a gripping storyteller talking to one viewer.",
    "hinglish": "Natural spoken Hinglish, the way Indian creators talk on Shorts: Hindi sentences with the everyday English "
                "words people really use, written in Roman letters (e.g. 'Us raat signal achanak band ho gaya, aur kisi ko "
                "pata nahi tha kyun.'). Not formal Hindi, and not English with a few Hindi words.",
    "hindi": "Simple spoken Hindi in Devanagari, the way people talk (not formal or shuddh Hindi); the everyday English words "
             "people use (phone, signal, internet) may stay as they are.",
}
KIND_RULES = {
    "story": "An original fiction story (never a retelling of a known film, book or viral story): a character the viewer "
             "cares about wants something, the obstacle grows, a detail planted early pays off in the twist at the end.",
    "facts": "A true story: real events told as a story. Every name, number, date and event is true and confirmed with web "
             "search (put the pages you opened in `sources`); speculation is said as a possibility. Real people may be "
             "named in the narration but are never drawn as characters. No politics, no rumours.",
    "comedy": "A funny story: an everyday situation everyone knows that escalates step by step; the jokes come from the "
              "characters and surprises, every part lands a punchline before its cliffhanger. Clean humour.",
    "explainer": "A clear explainer: one surprising question answered step by step with real facts, numbers and how it "
                 "works; each part gets one step closer and the full answer lands at the end. Every name, number and date "
                 "is true and confirmed with web search (put the pages you opened in `sources`). No politics, no rumours.",
    "news": "One real news story told so a viewer instantly gets why it matters. Every fact confirmed with web search (pages "
            "in `sources`).",
}


@dataclass
class StoryRequest:
    source: str = "ai"  # ai: Claude writes it | script: the user's own text, every word kept
    topic: str = ""  # ai: optional
    kind: str = "story"  # ai: story | facts | comedy
    script: str = ""  # script: the story, optionally with 'Part 2' headings
    title: str = ""  # script: optional series title
    parts: int = 3  # ai: how many Shorts; script: decided by its length (or its Part headings)
    split: str = "auto"  # script: auto (one Short at its natural length; parts only at the user's 'Part 2' lines) |
    # length (cut into the fewest parts within `seconds`) | one (always one Short, Part lines ignored)
    seconds: int = 30  # each part at most
    language: str = "english"  # what the voice speaks (and Claude writes in)
    screen_text: str = "english"  # english | voice: the words on screen
    visuals: str = "anim"  # anim (every shot a clip) | key (key shots) | pictures (camera moves) | footage (Pexels)
    style: str = "auto"  # art style for the AI pictures
    quality: str = "auto"  # clip size (animated.CLIP_SIZES)
    upscale: bool = True
    voice: str = ""  # empty: by language
    speed: int = 8  # free voices' rate %
    captions: bool = False
    watermark: str = ""


def default_voice(language: str) -> str:
    if language == "english":
        return "en-US-AndrewMultilingualNeural"
    if os.environ.get("SARVAM_API_KEY", "").strip():
        return "sarvam:shubh_enhi_ads" if language == "hinglish" else "sarvam:shubh_hi_stories_mixed"
    return "hi-IN-MadhurNeural"


def _ai_pictures(req: StoryRequest) -> bool:
    return req.visuals in ("anim", "key", "pictures")


# ---------- what Claude writes ----------

class SVisual(BaseModel):
    meaning: str = Field(description="What the viewer must understand here, in a few words.")
    importance: Literal["low", "medium", "high", "critical"]
    emphasis: str = Field(default="", description="The few words of the line that carry it, copied exactly from the line, or empty.")
    show: str = Field(default="", description="How those words appear on screen, max 4 words, in the on-screen language "
                      "(see the rules); empty when nothing is shown.")
    emphasis_fx: list[Fx] = Field(default_factory=list, description="On the emphasised words: text (they land on screen), "
                                  "zoom (punch-in), shake, flash, pause (a beat after the line). None for low lines.")
    scene: str = Field(description="The picture of this moment for the image model, 20-60 words, composed for a tall 9:16 "
                       "phone screen: who/what is in frame doing what, the setting, the shot (close-up / medium / low angle "
                       "looking up...), light and mood. Never text, signs, labels or screens with writing.")
    characters: list[str] = Field(default_factory=list, description="Cast ids in frame (0-2), the main one first.")
    same_place: bool = Field(default=False, description="True when this shot continues in the previous shot's place.")
    motion: str = Field(description="What moves during the clip, 8-30 words: one clear action plus small life.")
    camera: Camera
    transition: Transition = Field(description="How this shot comes in: cut (most), whip (energy), flash (a reveal), zoom "
                                   "(into detail), crossfade (time passes), dip (black, a big turn).")
    footage: str = Field(description="An English stock-video search for this moment, 2-4 words, concrete and filmable "
                         "(no named people, brands or events), e.g. 'rain on window night', 'old man walking alone'.")
    on_screen: str = Field(default="", description="0-4 words for a figure, date or name worth seeing, in the on-screen "
                           "language; mostly empty.")
    sounds: list[SoundCue] = Field(default_factory=list, description="0-2 effects from the sound list on exact words of the "
                                   "line; most lines get none.")


def _fields(model) -> dict:
    return {name: (f.annotation, f) for name, f in model.model_fields.items()}


SShot = create_model("SShot", line=(str, Field(description="One spoken sentence, 4-18 words: what the narrator says over this shot.")),
                     **_fields(SVisual))
BoardShot = create_model("BoardShot", n=(int, Field(description="The line number.")), **_fields(SVisual))


class PartInfo(BaseModel):
    title: str = Field(description="This part's own short title (what happens in it), in the on-screen language.")
    music: str = Field(description="This part's music for a music model, 10-30 words: the feeling, the energy (building to "
                       "the part's cliffhanger) and 1-2 sound colours from the story's world. No genre name: it is chosen "
                       "so no two videos sound alike.")
    bpm: int = Field(ge=60, le=170)
    mood: MusicMood = Field(description="The same feeling as a composer mood (used when no music model is available).")
    youtube_title: str = Field(description="This Short's YouTube title, max 70 characters, in the on-screen language, with "
                               "'Part N' in it when the story has several parts. Honest curiosity, no clickbait it doesn't deliver.")
    description: str = Field(description="1-3 sentences for YouTube, in the on-screen language; for parts before the last, "
                             "a line saying the next part continues the story.")
    hashtags: list[str] = Field(description="3-5 hashtags without '#', including 'shorts'.")


SPart = create_model("SPart", shots=(list[SShot], Field(description="The shots in order: 5-9, a new shot every 2.5-4.5 seconds.")),
                     **_fields(PartInfo))


class StorySeries(BaseModel):
    subject: str = Field(description="The one subject or premise of the story, in a few English words.")
    title: str = Field(description="The series title, max 60 characters, in the on-screen language.")
    premise: str = Field(description="One English sentence: what the story is and why viewers will follow it to the end.")
    art_style: str = Field(description="One of the art style keys listed.")
    style_notes: str = Field(description="This story's own look within the style, 10-40 words: palette, light, texture, era.")
    characters: list[ACharacter] = Field(default_factory=list, description="1-4 recurring characters (never real, named "
                                         "people); their design is repeated in every shot, so it is specific and fixed.")
    parts: list[SPart]
    music_track: str = Field(default="generate", description="One of the user's own tracks from the list when it truly fits "
                             "the whole story, else 'generate'.")
    sources: list[LSource] = Field(default_factory=list, description="True stories: 2-8 pages you opened that confirm "
                                   "every real fact. Empty for fiction.")
    category: str = Field(default="Stories", description="One of " + ", ".join(CATEGORIES) + ".")
    tags: list[str] = Field(default_factory=list, description="5-12 search tags.")


class StoryBoard(BaseModel):
    """The user's own story: Claude only sees and hears it (the words are theirs)."""
    subject: str = Field(description="The one subject or premise of the story, in a few English words.")
    title: str = Field(description="The series title, max 60 characters, in the on-screen language (the user's title "
                       "exactly when they gave one).")
    premise: str = Field(description="One English sentence: what the story is.")
    art_style: str = Field(description="One of the art style keys listed.")
    style_notes: str = Field(description="This story's own look within the style, 10-40 words.")
    characters: list[ACharacter] = Field(default_factory=list, description="1-4 recurring characters from the story.")
    parts: list[PartInfo] = Field(description="One per part, in order.")
    shots: list[BoardShot] = Field(description="One per numbered line, in order, every line.")
    music_track: str = Field(default="generate", description="One of the user's own tracks when it truly fits, else 'generate'.")
    category: str = Field(default="Stories", description="One of " + ", ".join(CATEGORIES) + ".")
    tags: list[str] = Field(default_factory=list)


# ---------- motion graphics (the long videos' templates, 9:16): one visual per line ----------

LMood = LongScript.model_fields["mood"].annotation
LAmbience = LChapter.model_fields["ambience"].annotation
_GVIS = {"visual": (LVisual, Field(description="What we see while it is said: exactly what the line says, laid out for a "
                                    "tall 9:16 phone screen.")),
         "sounds": (list[SoundCue], Field(default_factory=list, description="0-2 effects from the sound list on exact "
                                          "words of the line; most lines get none."))}
GShot = create_model("GShot", line=(str, Field(description="One spoken sentence, 4-18 words: what the narrator says over this visual.")), **_GVIS)
BoardGShot = create_model("BoardGShot", n=(int, Field(description="The line number.")), **_GVIS)


class GPartInfo(PartInfo):
    backdrop: str = LChapter.model_fields["backdrop"]
    intensity: int = LChapter.model_fields["intensity"]
    ambience: LAmbience = LChapter.model_fields["ambience"]  # type: ignore[valid-type]


GPart = create_model("GPart", shots=(list[GShot], Field(description="The visuals in order: 5-9, a new one every 2.5-4.5 seconds.")),
                     **_fields(GPartInfo))


class GSeries(BaseModel):
    subject: str = Field(description="The one subject or premise, in a few English words.")
    title: str = Field(description="The series title, max 60 characters, in the on-screen language.")
    premise: str = Field(description="One English sentence: what it is and why viewers will follow it to the end.")
    mood: LMood = LongScript.model_fields["mood"]  # type: ignore[valid-type]
    parts: list[GPart]
    music_track: str = Field(default="generate", description="One of the user's own tracks from the list when it truly fits, else 'generate'.")
    sources: list[LSource] = Field(default_factory=list, description="True stories, explainers and news: 2-8 pages you "
                                   "opened that confirm every real fact. Empty for fiction.")
    category: str = Field(default="Stories", description="One of " + ", ".join(CATEGORIES) + ".")
    tags: list[str] = Field(default_factory=list, description="5-12 search tags.")


class GBoard(BaseModel):
    subject: str = Field(description="The one subject or premise, in a few English words.")
    title: str = Field(description="The series title, max 60 characters, in the on-screen language (the user's title exactly when given).")
    premise: str = Field(description="One English sentence: what it is.")
    mood: LMood = LongScript.model_fields["mood"]  # type: ignore[valid-type]
    parts: list[GPartInfo] = Field(description="One per part, in order.")
    shots: list[BoardGShot] = Field(description="One per numbered line, in order, every line.")
    music_track: str = Field(default="generate", description="One of the user's own tracks when it truly fits, else 'generate'.")
    category: str = Field(default="Stories", description="One of " + ", ".join(CATEGORIES) + ".")
    tags: list[str] = Field(default_factory=list)


def _graphics_rules(req: StoryRequest) -> str:
    """The long writer's own rules for visuals, minus what a Short has no use for (chapter cards, the hook's own
    track), plus the tall frame's limits."""
    from .longform import _system as long_system

    style = {"facts": "facts", "explainer": "facts", "news": "news", "comedy": "comedy"}.get(req.kind, "story")
    full = long_system(style, "English")
    rules = full[full.index("Show, don't write"):full.index("Accuracy:")].strip()
    rules = re.sub(r"\n- (Chapter breaks|Backgrounds):.*?(?=\n- |\n\n)", "", rules, flags=re.S)
    rules = re.sub(r"Music and sound:.*?\n\n", "", rules, flags=re.S)
    return f"""Every shot is a motion-graphics visual (the long videos' own templates) on a tall 9:16 phone screen.
- Tall layout: timelines (2-5 dates) and steps (2-4) stack top to bottom, compare shows two tall bars, a chart has 3-6
points. Keep the words short: a keyword at most 3 words, a headline at most 6, item labels at most 3 words and item texts
at most 5.
- The first visual of every part is the hook: the most striking evidence (a big number, footage, a 3D object, a
keyword slam), never a slow title card.
- Each part is one chapter: give it a `backdrop` (a stock-photo search for its real setting), an `intensity` for its
music and an `ambience` where a place matters.
- {_screen_rule(req)}

{rules}"""


def _safe_visual(line: str) -> LVisual:
    """A corrected line's visual: an icon, no figures (the old one may show the figure the checker refused)."""
    return LVisual(type="icons", headline="", sub="", items=[], icons=[object_icon(line)], camera="push")


def assemble_graphics(req: StoryRequest, board: GBoard, parts: list[list[str]]) -> GSeries:
    shots = {sh.n: sh for sh in board.shots}
    out, n = [], 0
    for k, lines in enumerate(parts):
        info = board.parts[k] if k < len(board.parts) else (board.parts[-1] if board.parts else None)
        rows = []
        for line in lines:
            n += 1
            got = shots.get(n)
            rows.append(GShot(line=line, visual=got.visual if got else _safe_visual(line), sounds=got.sounds if got else []))
        meta = info.model_dump() if info else {"title": f"Part {k + 1}", "music": "cinematic", "bpm": 100, "mood": "curious",
                                               "youtube_title": f"{board.title} Part {k + 1}", "description": "", "hashtags": ["shorts"]}
        out.append(GPart(shots=rows, **meta))
    assert [sh.line for p in out for sh in p.shots] == [x for p in parts for x in p]  # not one spoken word changed
    return GSeries(subject=board.subject, title=req.title.strip() or board.title, premise=board.premise, mood=board.mood,
                   parts=out, music_track=board.music_track, category=board.category, tags=board.tags)


# ---------- the prompts ----------

def _screen_rule(req: StoryRequest) -> str:
    if req.screen_text == "english" and req.language != "english":
        return ("Words on screen: every word the viewer reads (`show`, `on_screen`, titles) is short, natural English, "
                f"although the voice speaks {req.language.title()}: write what the words mean, never a Hindi or Hinglish "
                "word and never Devanagari on screen. Names, places and units stay as they are, numbers in digits.")
    return "Words on screen: in the narration's own language and script, short."


def _directing(req: StoryRequest, styles: str) -> str:
    if req.visuals == "graphics":
        return _graphics_rules(req)
    footage = req.visuals == "footage"
    pictures = ("The pictures are stock footage: give every shot a precise `footage` search; `scene` and `motion` are one "
                "short sentence each (they aren't drawn), `characters` empty." if footage else
                f"""Every shot is drawn by an image model from `scene` and {'brought to life by a video model from `motion`'
                if req.visuals != 'pictures' else 'moved by the camera'}, in this art style (pick the one that fits):
{styles}
- `scene` is a vertical film frame, not a slide: the subject big in the middle band of a tall frame (close-ups, medium
shots, low angles looking up, depth going away from the camera), a setting and a light. The top tenth and the bottom fifth
of the frame hold nothing important (the Shorts title, buttons and captions sit there). Never the same composition twice
in a row; abstract ideas become visual metaphors.
- Characters: 1-4 recurring ones in `characters` (their `design` is reused in every shot) and who is in frame per shot.
The image model breaks close groups: at most two people near the camera, each whole and inside the frame with the face
showing, faces big (medium shot or close-up), crowds only small and far away, simple hands, nothing written.
- `same_place` when the shot stays in the previous shot's place; `motion` one clear action for a 3-5 second clip.
- `footage`: still give a stock search for every shot (the same story can be made from footage too).""")
    return f"""Directing every shot:
{pictures}
- Importance sets the intensity: low = calm, no words on screen; high = the emphasised words on screen; critical (the
hook, reveals, the cliffhanger) = words, punch-in and a flash on the same word. `show` only for high and critical lines.
- Transitions: mostly cuts, whips for energy, a flash for a reveal; never the same non-cut transition twice in a row.
- Music: describe each part's music for a music model and give the matching composer mood.
- {_screen_rule(req)}"""


def _system(req: StoryRequest, styles: str, recent: str, sounds: str) -> str:
    words = int((req.seconds - 3) * WPS.get(req.language, 2.6))
    many = req.parts > 1
    return f"""You write and direct short vertical stories for YouTube Shorts and Reels: one story told in {req.parts} \
part{'s' if many else ''}, each part a Short of at most {req.seconds} seconds (about {words} spoken words, never more).

The story: {KIND_RULES.get(req.kind, KIND_RULES['story'])}{news_rules() if req.kind == "news" else ""}
- {"One story across the parts: each part moves it forward with its own turn and ends on a cliffhanger that makes the viewer want the next part; the last part pays everything off. " if many else "One complete story in one Short, with a turn and a pay-off. "}\
Every part works on its own for a viewer who never saw the others.
- The first line of every part hooks in under 2 seconds (4-10 words: a question, a shock, a contradiction, a mystery).\
{" Parts 2 and later open by re-catching a new viewer with the situation in one line, never 'in the last part' or 'previous video'." if many else ""}
- Fast: a new shot every 2.5-4.5 seconds (5-9 shots a part), short lines pushing forward (but, so, then); no greeting, no
'in this video', no 'like and subscribe' in the narration.
- Never use: {", ".join(AI_CLICHES)}.
- Your own story and words: never copy another video's script, characters or structure.{recent}

The voice speaks: {LANGUAGE_RULES[req.language]}

{_directing(req, styles)}

{sounds}"""


def _styles_block(req: StoryRequest, cfg: Config) -> str:
    if req.style in ART_STYLES:
        return f"- {req.style}: {ART_STYLES[req.style][0]} (chosen by the user: use this one)"
    recent = animated._recent_styles(cfg)
    return "\n".join(f"- {k}: {v[0]}" for k, v in ART_STYLES.items() if k not in recent)


def _sounds_block(cfg: Config) -> str:
    return (media.prompt_block(cfg) + "\nFor this story `music_track` names one of the user's own tracks only when it fits "
            "the whole story; otherwise 'generate'.")


def write_series(cfg: Config, req: StoryRequest, avoid: str = "") -> StorySeries | GSeries:
    past = animated._history(cfg)[-6:]
    recent = ("\n- The last videos looked like this; make this one different (characters, palette, music): "
              + "; ".join(f"{p.get('style')} / {p.get('notes', '')[:60]}" for p in past)) if past else ""
    topic = req.topic.strip()
    if topic:
        prompt = f"Topic, chosen by the user: {topic}\nThe story is about exactly this. Don't replace it."
    else:
        prompt = ("Topic: pick a story people would binge part after part (a mystery, a survival, an unlikely hero, a "
                  "strange true event, a twist on everyday life).") + repeats.prompt_block(cfg, repeats.EVERY)
    if avoid:
        prompt += f"\n\n{avoid}"
    prompt += f"\n\nWrite exactly {req.parts} part(s)."
    from .hooks import block as hook_block

    prompt += hook_block(cfg)
    if req.kind in TRUE_KINDS:
        prompt += "\n- Research budget: at most 6 web searches and 5 opened pages, then write."
    return ask(cfg.ai_backend, cfg.claude_model, _system(req, _styles_block(req, cfg), recent, _sounds_block(cfg)), prompt,
               GSeries if req.visuals == "graphics" else StorySeries, allow_web=req.kind in TRUE_KINDS,
               effort=cfg.claude_effort, timeout=1800)


# ---------- the user's own story: lines and parts in code ----------

_SENTENCE = re.compile(r"(?<=[.!?…।])[\"'”’)\]]*\s+")
# Only an explicit "Part 2" / "Episode 2" / "भाग 2" line starts a new part: a '---' scene break once cut a 64-second
# story into two Shorts.
_PART = re.compile(r"^\s*[#*_]*\s*(part|episode|भाग)\s*\d+\b.*$", re.I)
FIT = 1.15  # a script up to 15% over the length stays one Short, spoken a little faster


def _plain(text: str) -> str:
    """Markdown marks the voice would read out ('**To be continued...**', '## Heading', '> quote')."""
    text = re.sub(r"\*\*|__|~~|`", "", text)
    text = re.sub(r"(?<!\w)\*(?=\S)|(?<=\S)\*(?!\w)", "", text)
    return re.sub(r"(?m)^\s*(#{1,6}|>)\s*", "", text)


def _words(text: str) -> int:
    return len(text.split())


def _split_long(sentence: str, limit: int = 18) -> list[str]:
    if _words(sentence) <= limit:
        return [sentence]
    cuts = [m.end() for m in re.finditer(r"[,;:]\s+|\s+[–—-]\s+", sentence)]
    if not cuts:
        return [sentence]
    mid = len(sentence) / 2
    at = min(cuts, key=lambda c: abs(c - mid))
    return _split_long(sentence[:at].strip(), limit) + _split_long(sentence[at:].strip(), limit)


def _lines(text: str) -> list[str]:
    """Shot-sized lines (about 4-14 words): sentences, a long one cut at a comma, very short ones joined."""
    out: list[str] = []
    for para in re.split(r"\n\s*\n", _plain(text).strip()):
        flat = " ".join(para.split())
        if not flat:
            continue
        acc = ""
        for s in (p for sent in _SENTENCE.split(flat) if sent.strip() for p in _split_long(sent.strip())):
            if acc and _words(acc) + _words(s) > 14:
                out.append(acc)
                acc = ""
            acc = f"{acc} {s}".strip()
            if _words(acc) >= 6:
                out.append(acc)
                acc = ""
        if acc:
            if out and _words(acc) < 4 and _words(out[-1]) + _words(acc) <= 20:
                out[-1] = f"{out[-1]} {acc}"
            else:
                out.append(acc)
    return out


def split_parts(text: str, language: str, seconds: int, split: str = "auto") -> list[list[str]]:
    """The user's script as parts of lines. `auto`: one Short at whatever length it runs (the user: "use what length
    goes"), split only at their own 'Part 2' lines; `one`: always one Short; `length`: at their Part lines, else cut by
    length into the fewest parts within `seconds` (one Short when it is at most FIT over). Lines never split."""
    if split == "one":
        return [ls] if (ls := _lines(text)) else []
    blocks, cur = [], []
    for row in text.replace("\r\n", "\n").split("\n"):
        if _PART.match(row):
            if "".join(cur).strip():
                blocks.append("\n".join(cur))
            cur = []
        else:
            cur.append(row)
    if "".join(cur).strip():
        blocks.append("\n".join(cur))
    if len(blocks) > 1:
        return [ls for ls in (_lines(b) for b in blocks) if ls]
    lines = _lines(text)
    if not lines or split != "length":
        return [lines] if lines else []
    budget = max(20, (seconds - 3) * WPS.get(language, 2.6))
    total = sum(_words(x) for x in lines)
    if total <= budget * FIT:
        return [lines]
    cum, run = [], 0
    for line in lines:
        run += _words(line)
        cum.append(run)
    n = max(2, math.ceil(total / budget))
    while True:  # the fewest parts of about equal length (cut at the line nearest each equal share) that all fit
        cuts = sorted({min(range(len(lines)), key=lambda j: abs(cum[j] - total * k / n)) + 1 for k in range(1, n)})
        cuts = [c for c in cuts if 0 < c < len(lines)]
        parts = [lines[a:b] for a, b in zip([0, *cuts], [*cuts, len(lines)])]
        if all(sum(_words(x) for x in p) <= budget for p in parts) or n >= len(lines):
            return parts
        n += 1


def storyboard(cfg: Config, req: StoryRequest, parts: list[list[str]]) -> StorySeries | GSeries:
    """One Claude call: the visuals, characters, music and post text for the user's own lines."""
    numbered, n = [], 0
    for k, lines in enumerate(parts, 1):
        numbered.append(f"## Part {k}")
        for line in lines:
            n += 1
            numbered.append(f"{n} {line}")
    system = f"""You storyboard a story the user wrote, told as {len(parts)} YouTube Shorts (9:16, each at most \
{req.seconds} s). The words are final: never change, add, remove or reorder a spoken word; you only decide what the \
viewer sees and hears, and write each part's title, music and post text. For every numbered line give its shot (n = the \
line number), showing exactly what that line says. The parts are fixed (## Part lines).

The voice speaks the user's own text ({req.language.title()}).

{_directing(req, _styles_block(req, cfg))}

{_sounds_block(cfg)}"""
    prompt = ((f"Series title, chosen by the user: {req.title.strip()}\n\n" if req.title.strip() else "")
              + "\n".join(numbered) + f"\n\nReturn {len(parts)} part entries and exactly {n} shots, one per line.")
    if req.visuals == "graphics":
        gboard = ask(cfg.ai_backend, cfg.claude_model, system, prompt, GBoard, allow_web=False, effort=cfg.claude_effort,
                     timeout=1200)
        return assemble_graphics(req, gboard, parts)
    board = ask(cfg.ai_backend, cfg.claude_model, system, prompt, StoryBoard, allow_web=False, effort=cfg.claude_effort,
                timeout=1200)
    return assemble(req, board, parts)


def assemble(req: StoryRequest, board: StoryBoard, parts: list[list[str]]) -> StorySeries:
    shots = {s.n: s for s in board.shots}
    out, n = [], 0
    for k, lines in enumerate(parts):
        info = board.parts[k] if k < len(board.parts) else (board.parts[-1] if board.parts else None)
        rows = []
        for line in lines:
            n += 1
            got = shots.get(n)
            vis = got.model_dump(exclude={"n"}) if got else {
                "meaning": "", "importance": "low", "scene": board.premise, "motion": "gentle movement", "camera": "push-in",
                "transition": "cut", "footage": board.subject}
            rows.append(SShot(line=line, **vis))
        meta = info.model_dump() if info else {"title": f"Part {k + 1}", "music": "cinematic", "bpm": 100, "mood": "curious",
                                               "youtube_title": f"{board.title} Part {k + 1}", "description": "", "hashtags": ["shorts"]}
        out.append(SPart(shots=rows, **meta))
    assert [sh.line for p in out for sh in p.shots] == [x for p in parts for x in p]  # not one spoken word changed
    return StorySeries(subject=board.subject, title=req.title.strip() or board.title, premise=board.premise,
                       art_style=board.art_style, style_notes=board.style_notes, characters=board.characters, parts=out,
                       music_track=board.music_track, category=board.category, tags=board.tags)


# ---------- a part Claude wrote too long: shortened before anything is recorded ----------

class LineCut(BaseModel):
    i: int = Field(description="The line's number in its part (1 = the first).")
    line: str = Field(description="The line to keep, tightened if needed (same facts, same language), or empty to drop it.")


class PartCut(BaseModel):
    part: int
    lines: list[LineCut] = Field(description="Every line to keep, in order.")


class Cuts(BaseModel):
    parts: list[PartCut]


def _part_words(part) -> int:
    return sum(_words(sh.line) for sh in part.shots)


def trim_parts(cfg: Config, req: StoryRequest, series, progress: Progress, ask_fn=None):
    """A part over its word budget (it would run past the Short's length, and speaking faster only goes so far) is
    shortened by Claude: lines tightened or dropped, never a new fact; the hook and the cliffhanger stay. Each kept
    line keeps its own visual. The user's own script is never touched."""
    budget = int((req.seconds - 3) * WPS.get(req.language, 2.6))
    over = [k for k, p in enumerate(series.parts) if _part_words(p) > budget * 1.08]
    if not over:
        return series
    progress(f"Part {', '.join(str(k + 1) for k in over)} {'runs' if len(over) == 1 else 'run'} long: shortening "
             f"to about {budget} words")
    blocks = []
    for k in over:
        part = series.parts[k]
        blocks.append(f"Part {k + 1} ({_part_words(part)} words, at most {budget}):\n"
                      + "\n".join(f"{i}. {sh.line}" for i, sh in enumerate(part.shots, 1)))
    system = ("You shorten the narration of YouTube Shorts so each part fits its length. Tighten wording and drop the "
              "least needed lines; keep the first line (the hook) and the last line (the cliffhanger or pay-off) strong; "
              "never add a fact, a number or a name, never change what a fact says, keep the language and the voice. "
              "Return every line to keep with its number, in order.")
    call = ask_fn or (lambda sy, pr: ask(cfg.ai_backend, cfg.claude_model, sy, pr, Cuts, effort="low", timeout=600))
    try:
        cuts = call(system, "\n\n".join(blocks))
    except Exception as exc:  # noqa: BLE001 - a long part is still made (spoken faster), never lost
        from .stopper import Paused
        if isinstance(exc, Paused):
            raise
        log.warning("Shortening failed: %s", exc)
        return series
    for cut in cuts.parts:
        k = cut.part - 1
        if k not in over:
            continue
        part = series.parts[k]
        keep = [(c.i, c.line.strip()) for c in cut.lines if 1 <= c.i <= len(part.shots) and c.line.strip()]
        shots = [part.shots[i - 1].model_copy(update={"line": line}) for i, line in dict(keep).items()]
        if shots and sum(_words(sh.line) for sh in shots) < _part_words(part):
            part.shots = shots
    return series


# ---------- fact-check (true stories Claude wrote) ----------

def _refs(series: StorySeries) -> dict:
    return {f"P{k + 1}.{i + 1}": sh for k, p in enumerate(series.parts) for i, sh in enumerate(p.shots)}


def _check(cfg: Config, series: StorySeries, only: set[str] | None = None) -> ScriptCheck:
    rows = [f"{r}{' >>' if only and r in only else ''} {sh.line}" + _shown(sh)
            for r, sh in _refs(series).items() if sh.line.strip() and (not only or r in only)]
    system = ("You fact-check a true story told as short videos. Search the web and open reliable pages. A line is "
              "confirmed only if a source you opened says the same; figures and dates must match. Story framing and "
              "lines said as a possibility are fine as long as they state no false fact. A fix keeps the line's language.")
    prompt = (f"Story: {series.title}\nThe writer's sources: " + "; ".join(f"{s.title} {s.url}" for s in series.sources)
              + "\n\n" + "\n".join(rows))
    return ask(cfg.ai_backend, cfg.fact_model, system, prompt, ScriptCheck, allow_web=True, effort=cfg.fact_effort, timeout=1200)


def _shown(sh) -> str:
    """What the viewer reads with the line (checked with it: a figure on screen must be right too)."""
    if hasattr(sh, "visual"):
        return " " + _visual_text(sh.visual)
    return f" (on screen: {sh.on_screen})" if sh.on_screen else ""


def check_facts(cfg: Config, series, progress: Progress) -> tuple:
    """Every factual line checked; a wrong one is replaced by the checker's true rewrite and checked once more; one
    still unconfirmed is cut."""
    findings, refs, changed = [], _refs(series), set()
    progress("Fact-checking every claim")
    for c in _check(cfg, series).lines:
        findings.append(c.model_dump())
        sh = refs.get(c.ref)
        if sh is None or c.verdict == "confirmed":
            continue
        sh.line = c.fix.strip()
        if hasattr(sh, "visual"):
            sh.visual = _safe_visual(sh.line)
        else:
            sh.on_screen, sh.show = "", ""
        changed.add(c.ref)
    issues = []
    rewritten = {r for r in changed if refs[r].line}
    if rewritten:
        progress(f"Re-checking the {len(rewritten)} corrected line(s)")
        for c in _check(cfg, series, only=rewritten).lines:
            if c.ref in rewritten:
                findings.append({**c.model_dump(), "round": 2})
                if c.verdict != "confirmed":
                    issues.append(f"{c.ref}: still not confirmed ({c.note}); the shot was cut.")
                    refs[c.ref].line = ""
    for p in series.parts:
        p.shots = [sh for sh in p.shots if sh.line.strip()]
    series.parts = [p for p in series.parts if p.shots]
    return series, issues, findings


# ---------- voice and timing, one part at a time ----------

def _norm(w: str) -> str:
    return re.sub(r"[\W_]", "", w.lower())  # keeps Devanagari letters (toon's matcher keeps only a-z0-9)


def _find_phrase(words, phrase: str) -> tuple[float, float] | None:
    want = "".join(_norm(w) for w in phrase.split())
    if not want or not words:
        return None
    text, owner = "", []
    for k, w in enumerate(words):
        n = _norm(w.text)
        text += n
        owner += [k] * len(n)
    at = text.find(want)
    if at < 0:
        first = _norm(phrase.split()[0])
        at, want = text.find(first), first
        if not first or at < 0:
            return None
    return words[owner[at]].start, words[owner[at + len(want) - 1]].end


def _fit_length(req: StoryRequest) -> bool:
    """Whether a part must fit `seconds`: Claude's parts, and a script the user asked to cut by length. Otherwise the
    user's script runs at its natural length and pace."""
    return req.source != "script" or req.split == "length"


def _labels(req: StoryRequest, k: int, n: int) -> tuple[str | None, str | None]:
    if n < 2:
        return None, None
    word = "भाग" if req.language == "hindi" and req.screen_text != "english" else "PART"
    return f"{word} {k}/{n}", (f"{word} {k + 1} →" if k < n else None)


def voice_part(series: StorySeries, k: int, req: StoryRequest, cfg: Config, work: Path, progress: Progress) -> dict:
    """Record part k (0-based) in one take and lay out its shots; a part over its length is spoken again a little
    faster (twice at most)."""
    part = series.parts[k]
    voice = req.voice or default_voice(req.language)
    lines = [sh.line for sh in part.shots]
    speed, factor = req.speed, 1.0
    for attempt in range(3):
        audio = synthesize_scenes(lines, voice, work / "audio" / f"p{k + 1}-{attempt}", cfg.tts_engine, cfg.kokoro_voice,
                                  f"{max(-30, min(50, speed)):+d}%", delivery="hook", sarvam_speed=factor)
        talk = sum(media_seconds(a.path) for a in audio)
        need = talk + 0.12 * len(lines) + 1.3
        if not _fit_length(req) or need <= req.seconds or attempt == 2 or need > req.seconds * (FIT + 0.05):
            break
        progress(f"Part {k + 1} runs {talk:.0f} s: speaking it a little faster")
        speed, factor = speed + 8, factor * 1.08
    return _layout(series, k, req, cfg, work, audio)


def _layout(series: StorySeries, k: int, req: StoryRequest, cfg: Config, work: Path, audio: list) -> dict:
    part = series.parts[k]
    n_parts = len(series.parts)
    sfx = write_sfx(work / "sfx")
    sfx.update(media.uploaded_for(cfg, list(sfx), work / "sfx"))
    rel = lambda p: Path(p).relative_to(work).as_posix()  # noqa: E731
    cues, spoken, used, shots = [], [], {}, []
    cue = lambda name, at, vol: cues.append({"src": rel(sfx[name]), "at": round(max(0.0, at), 3), "volume": vol, "name": name}) if name in sfx else None  # noqa: E731
    english_screen = req.screen_text == "english" and req.language != "english"
    t, last_tr = 0.0, ""
    for i, (sh, sa) in enumerate(zip(part.shots, audio)):
        lead = 0.12 if i == 0 else 0.06
        last = i == len(part.shots) - 1
        tail = (1.35 if k + 1 < n_parts else 0.8) if last else (0.45 if "pause" in sh.emphasis_fx else 0.1)
        talk = media_seconds(sa.path)
        duration = round(max(1.6, lead + talk + tail), 3)
        span = _find_phrase(sa.words, sh.emphasis) if sh.emphasis.strip() else None
        shown = sh.show.strip() or ("" if english_screen else sh.emphasis.strip())  # never the voice's words in English mode
        emph = {"text": shown[:40], "at": round(lead + span[0], 3), "end": round(lead + span[1], 3)} if span else None
        fx = [f for f in dict.fromkeys(sh.emphasis_fx) if f != "text" or shown][:4] if span else []
        tr = sh.transition if not (sh.transition == last_tr and sh.transition != "cut") else "cut"
        last_tr = tr
        sid = f"p{k + 1}s{i:02d}"
        shots.append({"id": sid, "type": "shot", "start": round(t, 3), "duration": duration, "lead": lead,
                      "audio": rel(sa.path), "text": sh.line,
                      "words": [{"text": w.text, "start": round(w.start, 3), "end": round(w.end, 3)} for w in sa.words],
                      "chapter": 0 if i else -1, "image": f"keyframes/{sid}.jpg", "clip": None, "camera": sh.camera,
                      "transition": tr if i else "cut", "importance": sh.importance, "emphasis": emph,
                      "emphasisFx": fx,
                      "onScreen": sh.on_screen.strip()[:28] or None, "query": sh.footage.strip()})
        loud = {"low": 0.5, "medium": 0.6, "high": 0.75, "critical": 0.85}[sh.importance]
        if i and tr in TRANSITION_SOUND:
            name, vol = TRANSITION_SOUND[tr]
            cue(name, t - 0.05, vol)
        if span and sh.importance in ("high", "critical"):
            cue("impact" if sh.importance == "critical" else "pop", t + lead + span[0], loud)
        cues += media.resolve_cues(sh.sounds, sa.words, t + lead, cfg, work / "sfx", rel, 2, used)
        spoken += [(t + lead + w.start, t + lead + w.end) for w in sa.words]
        t += duration
    if k + 1 < n_parts:
        cue("whoosh", t - 1.2, 0.45)
    return {"shots": shots, "duration": round(t, 3), "speech": media.speech_spans(spoken), "cues": cues}


# ---------- pictures, clips, footage, music ----------

def _plan(series: StorySeries, tls: list[dict]) -> list[tuple[dict, object]]:
    return [(row, sh) for p, tl in zip(series.parts, tls) for row, sh in zip(tl["shots"], p.shots)]


def _look(series: StorySeries, style: str) -> str:
    return f"{ART_STYLES[style][0]}, {series.style_notes.strip()}".strip(", ")


def keyframe_job(series: StorySeries, tls: list[dict], style: str, work: Path, seed: int, fixes: dict | None = None) -> dict:
    fixes = fixes or {}
    look = _look(series, style)
    designs = {c.id: c for c in series.characters}
    chars = [{"id": f"char-{c.id}", "out": str(work / "keyframes" / f"char-{c.id}.jpg"), "seed": seed + 7 + j,
              "prompt": f"Character design of {c.name}: {c.design}. Full body, standing, front view, centered, plain light "
                        f"background. {look}"} for j, c in enumerate(series.characters)]
    items, prev = [], None
    for n, (row, sh) in enumerate(_plan(series, tls)):
        cast = [designs[c] for c in sh.characters if c in designs][:2]
        who = " ".join(f"{c.name}: {c.design}" for c in cast)
        item = {"id": row["id"], "out": str(work / row["image"]), "seed": seed + 100 + n,
                "prompt": f"{sh.scene} {who} {look}, vertical composition, cinematic, highly detailed".strip()}
        if cast:
            item["ref"] = str(work / "keyframes" / f"char-{cast[0].id}.jpg")
        if sh.same_place and prev and row["id"].split("s")[0] == prev["id"].split("s")[0]:  # the same part's shot before
            item.update(init=str(work / prev["image"]), strength=0.62)
        items.append(item)
        prev = row
    for it in chars + items:
        fix = fixes.get(it["id"])
        if fix:
            it["seed"] += 1000 * int(fix.get("round", 1))
            it["prompt"] = (f"Character design: {fix['prompt']}. Full body, standing, front view, centered, plain light "
                            f"background. {look}" if it["id"].startswith("char-") else
                            f"{fix['prompt']} {look}, vertical composition, cinematic, highly detailed")
            it.pop("init", None)
    return {"characters": chars, "shots": items, "negative": NEGATIVE, "width": PORTRAIT[0], "height": PORTRAIT[1], "steps": 4}


def check_pictures(cfg: Config, series: StorySeries, tls: list[dict], work: Path, ids: list[str] | None = None):
    lines = {f"char-{c.id}": f"character sheet of {c.name}: {c.design}" for c in series.characters}
    lines.update({row["id"]: f"{sh.line} (meant: {sh.scene})" for row, sh in _plan(series, tls)})
    pics = [(label, work / "keyframes" / f"{label}.jpg") for label in lines
            if (work / "keyframes" / f"{label}.jpg").exists() and (ids is None or label in ids)]
    if not pics:
        return []
    sheets = animated._pic_sheets(pics, work, tile=(300, 533), across=4)
    prompt = (f"Story: {series.title}. Recurring characters: {', '.join(c.name for c in series.characters) or 'none'}. "
              "The pictures are tall (9:16).\n" + "\n".join(f"{label}: {lines[label]}" for label, _ in pics)
              + f"\n\n{len(sheets)} contact sheet(s) attached. List only the broken pictures.")
    review = ask(cfg.ai_backend, cfg.claude_model, animated.PIC_SYSTEM, prompt, animated.PicReview, images=sheets,
                 effort=cfg.claude_effort, timeout=900)
    known = {label for label, _ in pics}
    return [b for b in review.broken if b.id in known and b.prompt.strip()]


def _motion_wanted(row: dict, sh, visuals: str) -> bool:
    if visuals == "anim":
        return True
    return visuals == "key" and (row["id"].endswith("s00") or sh.importance in ("high", "critical"))


def clip_size(req: StoryRequest) -> tuple[int, int, float]:
    W, H, longest = animated.CLIP_SIZES[animated.clip_quality(req)]  # type: ignore[arg-type]
    return H, W, longest  # the same pixels, standing up (all multiples of 32)


def clip_jobs(series: StorySeries, tls: list[dict], style: str, req: StoryRequest, work: Path, seed: int) -> tuple[dict, dict]:
    look = ART_STYLES[style][0]
    W, H, longest = clip_size(req)
    shots = []
    for n, (row, sh) in enumerate(_plan(series, tls)):
        if not _motion_wanted(row, sh, req.visuals):
            continue
        shots.append({"id": row["id"], "image": str(work / row["image"]), "out": str(work / "clips" / f"{row['id']}.mp4"),
                      "emb": str(work / "clips" / f"{row['id']}.pt"), "frames": animated._frames(row["duration"], longest),
                      "seed": seed + 500 + n,
                      "prompt": f"{sh.motion.strip()} {CAMERAS.get(sh.camera, '')}. {sh.scene} {look}. Smooth, natural "
                                f"animation, consistent character, vertical video, no text."})
    return {"shots": shots}, {"shots": shots, "width": W, "height": H, "fps": 24}


def _frame(src: Path, out: Path, at_end: bool) -> None:
    args = ["-sseof", "-0.25"] if at_end else ["-ss", "0.05"]
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", *args, "-i", str(src), "-frames:v", "1", "-q:v", "3", str(out)],
                   capture_output=True)


def fetch_footage(series: StorySeries, tls: list[dict], cfg: Config, work: Path, progress: Progress) -> None:
    """Stock clips for every shot (portrait Pexels, like the Create tab's Shorts): the shot's own search, then the
    story's subject; a shot nothing was found for reuses the clip before it."""
    from .visuals import gradient_image, pexels_video

    if not cfg.pexels_api_key:
        raise RuntimeError("Stock footage needs a Pexels key (Settings), or pick AI pictures")
    (work / "footage").mkdir(parents=True, exist_ok=True)
    (work / "keyframes").mkdir(parents=True, exist_ok=True)
    used: set[int] = set()
    rows = [row for tl in tls for row in tl["shots"]]
    progress(f"Downloading stock footage for {len(rows)} shots")
    last = None
    for n, row in enumerate(rows):
        out = work / "footage" / f"{row['id']}.mp4"
        if not (out.exists() and Path(str(out) + ".ok").exists()):
            got = None
            for q in dict.fromkeys(x for x in (row.get("query", ""), series.subject) if x.strip()):
                try:
                    got = pexels_video(q, cfg.pexels_api_key, out, used)
                except Exception as exc:  # noqa: BLE001 - one search failing never stops the video
                    log.warning("Pexels search %r failed: %s", q, exc)
                if got:
                    break
            if got:
                Path(str(out) + ".ok").write_text("", encoding="utf-8")
            elif last is not None:
                shutil.copy(last, out)
                Path(str(out) + ".ok").write_text("", encoding="utf-8")
        if out.exists():
            last = out
            _frame(out, work / row["image"], at_end=False)
            _frame(out, out.with_suffix(".last.jpg"), at_end=True)
        else:
            gradient_image(HD_CLIP[0], HD_CLIP[1], work / row["image"], n)
        if n % 6 == 5:
            progress(f"Downloading stock footage: {n + 1} of {len(rows)}")


def make_music(series: StorySeries, tls: list[dict], req: StoryRequest, cfg: Config, work: Path, seed: int,
               progress: Progress) -> tuple[list[str], str]:
    """One track per part: the user's track when Claude picked one that fits, else the AI music model (reelgen/aimusic.py,
    any look) with a composed track for any it didn't make, else composed."""
    from . import music as composer

    rel = lambda p: Path(p).relative_to(work).as_posix()  # noqa: E731
    (work / "music").mkdir(parents=True, exist_ok=True)
    mine = {m.name for m in media.music(cfg) if m.path is not None}
    if series.music_track in mine and media.fresh_track(cfg, series.music_track):
        picked = [media.pick_music(cfg, series.music_track, work / "music", tl["duration"] + 1) for tl in tls]
        if all(picked):
            progress(f"Music: your track '{series.music_track}'")
            media.note_music(cfg, series.music_track)
            return [rel(x) for x in picked], series.music_track
    made: dict[str, Path] = {}
    genre = ""
    tracks = [{"id": f"p{k + 1}", "out": str(work / "music" / f"p{k + 1}.wav"), "seed": seed + 20 + k, "bpm": p.bpm,
               "caption": f"{p.music}, instrumental, no vocals", "duration": round(min(120, tl["duration"] + 2), 1)}
              for k, (p, tl) in enumerate(zip(series.parts, tls))]
    if aimusic.available(cfg):  # one genre for the series (none of the last videos'), each part at its own energy
        genre = aimusic.pick_genre(cfg, series.parts[0].mood, seed)
        tracks = [aimusic.track(t["id"], Path(t["out"]), t["duration"], genre, p.mood, min(1.0, 0.6 + 0.1 * k), p.music,
                                t["seed"], hook=True) for k, (t, p) in enumerate(zip(tracks, series.parts))]
        made = aimusic.make(cfg, tracks, work, progress, "Music (AI)")
        if made:
            aimusic.remember(cfg, genre)
    out = []
    for k, (p, tl) in enumerate(zip(series.parts, tls)):
        path = made.get(f"p{k + 1}")
        if path is None:
            path = composer.compose(p.mood, [composer.Section(0, tl["duration"] + 1, min(1.0, 0.45 + 0.12 * k))],
                                    tl["duration"] + 1, seed + k, work / "music" / f"p{k + 1}-composed.wav")
        out.append(rel(path))
    choice = (f"generated (ACE-Step, {genre})" if len(made) == len(tracks) else
              f"generated (ACE-Step, {genre}) for {len(made)} of {len(tracks)} parts, composed for the rest" if made else "composed")
    media.note_music(cfg, *dict.fromkeys(f"mood:{p.mood}" for k, p in enumerate(series.parts) if f"p{k + 1}" not in made))
    return out, choice


# ---------- props, render, reports ----------

def props_for(series: StorySeries, k: int, tl: dict, req: StoryRequest, style: str, cfg: Config, work: Path,
              music_src: str, music_choice: str, seed: int) -> dict:
    shots = []
    for x in tl["shots"]:
        x = dict(x)
        x.pop("query", None)
        clip = work / ("footage" if req.visuals == "footage" else "clips") / f"{x['id']}.mp4"
        if clip.exists() and Path(str(clip) + ".ok").exists():
            x["clip"] = clip.relative_to(work).as_posix()
            x["clipSeconds"] = round(media_seconds(clip), 3)
            last = clip.with_suffix(".last.jpg")
            x["last"] = last.relative_to(work).as_posix() if last.exists() else None
        if not (work / x["image"]).exists():
            x["image"] = next((s["image"] for s in reversed(shots) if (work / s["image"]).exists()), x["image"])
        shots.append(x)
    if _ai_pictures(req):
        shots = animated._hd_props(shots, work)
    label, nxt = _labels(req, k + 1, len(series.parts))
    accent = ART_STYLES[style][1] if style in ART_STYLES else FOOTAGE_ACCENTS[seed % len(FOOTAGE_ACCENTS)]
    props = {"fps": animated.ANIM_FPS if _ai_pictures(req) else 30, "vertical": True, "duration": tl["duration"],
             "title": series.title, "style": style, "accent": accent, "shots": shots, "captions": req.captions,
             "watermark": req.watermark.strip()[:40] or None, "hookMusic": None, "hookEnd": 0,
             "musicParts": [{"src": music_src, "from": 0, "to": tl["duration"]}], "musicChoice": music_choice,
             "speech": tl["speech"], "cues": tl["cues"], "partLabel": label, "nextLabel": nxt}
    props["sfxLevels"] = media.level_sounds(props, work, [s["audio"] for s in shots if s.get("audio")])
    props["musicLevels"] = media.level_music(props, work, [s["audio"] for s in shots if s.get("audio")], "Anim")  # the music under the voice
    return props


def run_story(cfg: Config, req: StoryRequest, progress: Progress = log.info, resume: str | None = None) -> list[dict]:
    from .fsutil import move
    from .pipeline import pause_point, slugify

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    work = cfg.output_dir / resume if resume else cfg.output_dir / f"{stamp}-{uuid.uuid4().hex[:4]}-story-working"
    work.mkdir(parents=True, exist_ok=True)
    progress(f"Saving progress in {work.name}")
    state = json.loads((work / CHECKPOINT).read_text(encoding="utf-8")) if (work / CHECKPOINT).exists() else {}
    stamp = state.get("stamp", stamp)
    seed = state.get("seed") or int(uuid.uuid4().int % 2**31)

    def save(**changes) -> None:
        state.update(changes, stamp=stamp, seed=seed, request=asdict(req))
        (work / CHECKPOINT).write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        pause_point()

    if _ai_pictures(req) and not anim_engine.installed():
        raise RuntimeError("AI pictures need the AI engine: open the Anim tab and press 'Install the AI engine' "
                           "(or pick stock footage)")
    # 1. the story
    if state.get("series"):
        series = (GSeries if req.visuals == "graphics" else StorySeries).model_validate(state["series"])
        issues, findings = state.get("issues", []), state.get("findings", [])
        progress("Resuming: the story is already written")
    else:
        if req.source == "script":
            parts = split_parts(req.script, req.language, req.seconds, req.split)
            if not parts:
                raise ValueError("The story is empty.")
            progress(f"Your story: {sum(len(p) for p in parts)} lines in {len(parts)} part(s)")
            progress("Claude is storyboarding your story (pictures, sounds, music)")
            series = storyboard(cfg, req, parts)
            repeats.claim(cfg, {"title": series.title, "subject": series.subject, "topic": series.title, "kind": "short"})
            issues, findings = [], []
        else:
            progress("Claude is writing the story and storyboard")
            series = write_series(cfg, req)
            if req.topic.strip():
                repeats.claim(cfg, {"title": series.title, "subject": series.subject, "topic": req.topic.strip(), "kind": "short"})
            else:
                series = repeats.guard(cfg, series, repeats.EVERY, lambda why: write_series(cfg, req, why), progress)
            series = trim_parts(cfg, req, series, progress)
            from .hooks import sharpen
            sharpen(cfg, [p.shots[0] for p in series.parts if p.shots], series.premise, progress)  # every part's hook
            (work / "draft.json").write_text(series.model_dump_json(indent=1), encoding="utf-8")
            issues, findings = [], []
            if req.kind in TRUE_KINDS:
                series, issues, findings = check_facts(cfg, series, progress)
        save(stage="scripted", series=series.model_dump(), issues=issues, findings=findings)
    if not series.parts:
        raise RuntimeError("Nothing left of the story after the fact-check.")
    cli = _remotion_cli()
    if cli is None:
        raise RuntimeError("Node.js or the Remotion packages are not installed (run start.bat / start.sh)")
    slug = slugify(series.title) if slugify(series.title) != "reel" else (slugify(series.subject) or "story")
    sources, dropped = verify_sources(series.sources) if series.sources else ([], [])
    if req.kind in TRUE_KINDS and req.source == "ai" and not sources:
        issues = [*issues, "No source link could be opened; check the facts before posting."]
    finish = _Finisher(cfg, req, series, work, stamp, seed, slug, sources, dropped, findings, state, save, progress)
    if req.visuals == "graphics":
        reports = _graphics_parts(cfg, req, series, work, state, save, issues, finish, cli, progress)
    else:
        reports = _picture_parts(cfg, req, series, work, state, save, issues, finish, cli, seed, progress)
    (work / CHECKPOINT).unlink(missing_ok=True)
    if any(work.iterdir()):
        move(work, cfg.output_dir / f"{stamp}-{slug}-story-files")
    else:
        work.rmdir()
    progress("Done" if all(r["verified"] for r in reports) else "Done, but some parts did not pass every check — review before posting")
    return reports


class _Finisher:
    """Verifies an edited part, gives it its own library folder and report (shared by every look)."""

    def __init__(self, cfg, req, series, work, stamp, seed, slug, sources, dropped, findings, state, save, progress):
        self.__dict__.update(cfg=cfg, req=req, series=series, work=work, stamp=stamp, seed=seed, slug=slug, sources=sources,
                             dropped=dropped, findings=findings, state=state, save=save, progress=progress)
        self.done = dict(state.get("finals") or {})
        self.series_id = work.name.replace("-story-working", "")

    def finished(self, k: int) -> dict | None:
        folder = self.done.get(str(k + 1))
        path = self.cfg.output_dir / folder / "report.json" if folder else None
        return json.loads(path.read_text(encoding="utf-8")) if path and path.exists() else None

    def __call__(self, k: int, props: dict, video: Path, issues: list[str], extra: dict, folder: Path | None = None) -> dict:
        from .llm import meter_records, summarize_usage
        from .pipeline import done_line

        cfg, req, series = self.cfg, self.req, self.series
        part = series.parts[k]
        self.progress(f"Verifying part {k + 1}")
        info = probe(video)
        mine = [x for x in issues if not re.match(r"P\d+\.", x) or x.startswith(f"P{k + 1}.")]
        if (info.get("width"), info.get("height")) != HD_CLIP:
            mine.append(f"Resolution is {info.get('width')}x{info.get('height')}, expected 1080x1920.")
        if not info.get("has_audio"):
            mine.append("No audio track.")
        if _fit_length(req) and props["duration"] > req.seconds + 0.5:
            mine.append(f"Part {k + 1} runs {props['duration']:.0f} s, over {req.seconds} s.")
        final = cfg.output_dir / f"{self.stamp}-{self.slug}-p{k + 1}"
        if folder is not None:  # a part built in its own folder (motion graphics) keeps its files
            if final.exists():
                shutil.rmtree(final)
            folder.rename(final)
            video = final / video.name
        final.mkdir(parents=True, exist_ok=True)
        if video != final / "reel.mp4":
            video.replace(final / "reel.mp4")
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", "1", "-i", str(final / "reel.mp4"), "-frames:v", "1",
                        "-q:v", "3", str(final / "thumbnail.jpg")], check=False)
        (final / "props.json").write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
        (final / "script.json").write_text(series.model_dump_json(indent=2), encoding="utf-8")
        desc = part.description.strip()
        report = {
            "id": final.name, "format": "short", "length": "short", "source": "storyshorts", "series": self.series_id,
            "part": k + 1, "parts": len(series.parts), "series_title": series.title,
            "topic": series.subject, "subject": series.subject, "topic_source": "your script" if req.source == "script" else "shorts studio",
            "style": req.kind if req.source == "ai" else "story",
            "category": series.category if series.category in CATEGORIES else "Stories",
            "title": part.youtube_title or f"{series.title} {k + 1}", "why_chosen": series.premise,
            "narration": " ".join(sh.line for sh in part.shots), "created_at": self.stamp, "verified": not mine, "score": None,
            "issues": mine, "checks": {"probe": info}, "attempts": 1, "video": str(final / "reel.mp4"),
            "thumbnail": str(final / "thumbnail.jpg"), "duration_seconds": round(props["duration"], 1),
            "captions": req.captions, "voice": req.voice or default_voice(req.language), "language": req.language,
            "screen_text": req.screen_text, "visuals": req.visuals,
            "youtube_title": (part.youtube_title or series.title)[:100], "caption": desc,
            "hashtags": [h.lstrip("#") for h in part.hashtags],
            "youtube_description": with_sources(desc, self.sources, []) if self.sources else desc,
            "youtube_hashtags": [h.lstrip("#") for h in part.hashtags][:3], "youtube_tags": series.tags,
            "fact_check": self.findings if k == 0 else [], "sources": self.sources, "sources_unreachable": self.dropped,
            "seed": self.seed, **extra,
        }
        if k == 0:
            report["usage"] = summarize_usage(meter_records())
        (final / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        self.done[str(k + 1)] = final.name
        self.save(stage="rendering", finals=self.done)
        self.progress(done_line(report))
        return report


_PLATE_KEYS = ("plates", "plateUrls", "platesBaked", "hookPlate", "breaks")


def _long_script(series: GSeries, part, req: StoryRequest) -> LongScript:
    """One part as an ordinary long-video script: no trailer hook (the first line is the hook), one chapter."""
    mine = series.music_track if series.music_track not in ("", "generate") else "compose"
    beats = [LBeat(narration=sh.line, visual=sh.visual, sounds=sh.sounds) for sh in part.shots]
    chapter = LChapter(title=part.title, beats=beats, intensity=part.intensity, ambience=part.ambience, backdrop=part.backdrop)
    return LongScript(topic=series.subject, why_chosen=series.premise, facts_checked="", category="Stories",
                      subject=series.subject, hook_question="", answer="", youtube_title=part.youtube_title or series.title,
                      hook=[], mood=series.mood, chapters=[chapter], music=mine, music_prompt=part.music)


def _graphics_parts(cfg: Config, req: StoryRequest, series: GSeries, work: Path, state: dict, save, issues: list[str],
                    finish: _Finisher, cli, progress: Progress) -> list[dict]:
    """Every part built by the long-video builder (voice, sound design, music, backdrop photos, 3D, footage) in its own
    folder and edited with the Long composition in 9:16. Part 1's look (palette, backdrop style, transitions) is kept
    for the others, with their own photos."""
    from dataclasses import replace

    from .pipeline import _render_slot

    voice = req.voice or default_voice(req.language)
    first_look = state.get("look")
    reports = []
    n = len(series.parts)
    for k, part in enumerate(series.parts):
        if (old := finish.finished(k)) is not None:
            reports.append(old)
            continue
        pdir = work / f"p{k + 1}"
        shutil.rmtree(pdir, ignore_errors=True)  # a part stopped half-way is built again
        script = _long_script(series, part, req)
        look = None if first_look is None else {key: v for key, v in first_look.items() if key not in _PLATE_KEYS}
        label, nxt = _labels(req, k + 1, n)
        tail = 0.9 if nxt else 0.3
        speed, factor = req.speed, 1.0
        progress(f"Recording the voiceover for part {k + 1} of {n} ({voice})")
        for attempt in range(3):
            pcfg = replace(cfg, long_voice=voice, voice_rate=f"{max(-30, min(50, speed)):+d}%", captions=req.captions, fps=30)
            props = build_long(script, pcfg, pdir, progress, look=look, voice_opts={"delivery": "hook", "sarvam_speed": factor})
            if (not _fit_length(req) or props["duration"] + tail <= req.seconds or attempt == 2
                    or props["duration"] + tail > req.seconds * (FIT + 0.05)):
                break
            progress(f"Part {k + 1} runs {props['duration']:.0f} s: speaking it a little faster")
            speed, factor = speed + 8, factor * 1.08
            shutil.rmtree(pdir / "audio", ignore_errors=True)
        if first_look is None:
            first_look = props["look"]
            save(look=first_look)
        props.update(vertical=True, partLabel=label, nextLabel=nxt, duration=round(props["duration"] + tail, 3))
        out = pdir / "reel.mp4"
        progress(f"Editing part {k + 1} of {n} ({props['duration']:.0f} s)")
        with _render_slot(cfg):
            _render_remotion(cli, props, out, composition="Long", crf=18, progress=progress)
        reports.append(finish(k, props, out, issues, {"editor": "remotion (Long, 9:16)", "music": props.get("musicChoice", "")},
                              folder=pdir))
    return reports


def _picture_parts(cfg: Config, req: StoryRequest, series: StorySeries, work: Path, state: dict, save, issues: list[str],
                   finish: _Finisher, cli, seed: int, progress: Progress) -> list[dict]:
    """AI animation, AI pictures or stock footage: the voice, pictures, motion and music for the whole series in one
    go, then every part edited with the Anim composition in 9:16."""
    from .pipeline import _render_slot

    style = state.get("style") or (animated._style_of(series, req, cfg, seed) if _ai_pictures(req) else "footage")  # type: ignore[arg-type]
    # the voice, part by part
    tls = state.get("timelines") or []
    if len(tls) == len(series.parts) and all((work / s["audio"]).exists() for tl in tls for s in tl["shots"]):
        progress("Resuming: voiceover already recorded")
    else:
        progress(f"Recording the voiceover ({req.voice or default_voice(req.language)})")
        tls = [voice_part(series, k, req, cfg, work, progress) for k in range(len(series.parts))]
        save(stage="voiced", timelines=tls, style=style)
    progress(f"{len(series.parts)} part(s): " + ", ".join(f"{tl['duration']:.0f} s" for tl in tls)
             + (f"; art style {style}" if _ai_pictures(req) else "; stock footage"))
    # pictures and motion
    pic_found, up = state.get("pic_found") or [], None
    if _ai_pictures(req):
        anim_engine.run_stage("keyframes", keyframe_job(series, tls, style, work, seed, state.get("pic_fixes")), work,
                              progress, "Drawing the pictures")
        save(stage="pictures")
        if not state.get("pics_checked") and not any((work / "clips").glob("*.mp4.ok")):
            pic_found = animated._picture_rounds(
                cfg, None, {}, style, work, seed, state, progress, save,  # type: ignore[arg-type]
                check=lambda ids: check_pictures(cfg, series, tls, work, ids),
                job=lambda fixes: keyframe_job(series, tls, style, work, seed, fixes))
        emb, clipjob = clip_jobs(series, tls, style, req, work, seed)
        if clipjob["shots"]:
            W, H, longest = clip_size(req)
            progress(f"Clips: {W}x{H}, up to {longest:.0f} s each, {len(clipjob['shots'])} of "
                     f"{sum(len(tl['shots']) for tl in tls)} shots")
            anim_engine.run_stage("embed", emb, work, progress, "Reading the motion prompts")
            anim_engine.run_stage("clips", clipjob, work, progress, "Animating the shots")
        if req.upscale:
            up = animated.upscale_job([s for tl in tls for s in tl["shots"]], style, work, HD_CLIP, HD_PICTURE)
            if up and up["items"]:
                anim_engine.run_stage("upscale", up, work, progress, "Sharpening to full HD")
    else:
        fetch_footage(series, tls, cfg, work, progress)
    save(stage="clips")
    # music
    if state.get("music"):
        tracks, music_choice = state["music"]
    else:
        tracks, music_choice = make_music(series, tls, req, cfg, work, seed, progress)
        save(stage="music", music=[tracks, music_choice])
    # every part edited on its own
    reports = []
    for k, tl in enumerate(tls):
        if (old := finish.finished(k)) is not None:
            reports.append(old)
            continue
        props = props_for(series, k, tl, req, style, cfg, work, tracks[k], music_choice, seed)
        out = work / f"reel-p{k + 1}.mp4"
        progress(f"Editing part {k + 1} of {len(series.parts)} ({tl['duration']:.0f} s)")
        with _render_slot(cfg):
            _render_remotion(cli, props, out, composition="Anim", crf=18, progress=progress)
        animated_n = sum(1 for s in props["shots"] if s.get("clip"))
        reports.append(finish(k, props, out, issues, {
            "editor": "remotion (Anim, 9:16)", "art_style": style if _ai_pictures(req) else None, "music": music_choice,
            "animated_shots": f"{animated_n} of {len(props['shots'])}", "picture_check": pic_found if k == 0 else [],
            "upscaled": up["model"] if up and up.get("items") else None,
            "characters": [c.model_dump() for c in series.characters]}))
    if _ai_pictures(req):
        animated._remember(cfg, {"title": series.title, "subject": series.subject, "style": style,
                                 "notes": series.style_notes, "music": series.parts[0].music[:60], "kind": "story",
                                 "characters": [c.name for c in series.characters]})
    return reports


def run_story_job(cfg: Config, req: StoryRequest, progress: Progress, resume: list[str] | None = None) -> list[dict]:
    """The app's job: one series (or a saved one resumed), in the shared video slot, with token metering and pause."""
    from .llm import set_limit_reporter, start_meter, usage_line
    from .pipeline import Paused, _video_slot, set_pause_check

    should_pause = getattr(progress, "should_pause", None)
    reports: list[dict] = []
    with _video_slot(cfg):
        set_pause_check(should_pause)
        set_limit_reporter(progress)
        start_meter(lambda r: progress(usage_line(r)))
        progress("=== Video 1/1 ===")
        try:
            reports = run_story(cfg, req, progress, (resume or [None])[0])
        except Paused:
            progress("Paused: progress saved. Press Resume to carry on from here.")
        except Exception as exc:
            log.exception("Story Shorts failed")
            progress(f"Video 1 failed: {exc}")
    return reports


def unfinished_stories(cfg: Config) -> list[str]:
    return sorted(p.parent.name for p in cfg.output_dir.glob(f"*-story-working/{CHECKPOINT}"))


def story_unfinished(cfg: Config) -> list[dict]:
    done = {"scripted": "the story", "voiced": "story and voiceover", "pictures": "pictures", "clips": "pictures and motion",
            "music": "pictures, motion and music", "rendering": "some parts"}
    out = []
    for folder in unfinished_stories(cfg):
        path = cfg.output_dir / folder / CHECKPOINT
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        series = state.get("series") or {}
        req = state.get("request") or {}
        finals = state.get("finals") or {}
        out.append({"id": folder, "topic": series.get("subject") or req.get("topic") or "Story Shorts",
                    "title": series.get("title", ""), "style": req.get("kind", "story"), "length": "storyshorts",
                    "attempt": 1, "updated": path.stat().st_mtime,
                    "done": done.get(state.get("stage") or "", "nothing yet")
                            + (f" ({len(finals)} of {len(series.get('parts') or [])} parts edited)" if finals else "")})
    return out
