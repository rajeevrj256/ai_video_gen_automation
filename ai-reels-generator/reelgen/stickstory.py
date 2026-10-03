"""Stick Stories: stick-figure comedy episodes (16:9, 3-8 min) and Shorts (9:16) for the channel's
own style, with a recurring cast. One Claude call writes the episode (fiction, no web search, no
fact-check): scenes in sets, every line with its speaker, pose, face, camera and sounds. Each
character gets their own voice (one take per character, cut per line, so mouths move on the words);
the Remotion composition `StickStory` (remotion/src/story/) draws it all in SVG.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal, get_args

from pydantic import BaseModel, Field

from . import media
from .config import Config
from .llm import ask
from .script_writer import AI_CLICHES, SoundCue
from .sfx import write_sfx
from .verify import probe
from .video import FFMPEG, _remotion_cli, _render_remotion, media_seconds
from .voice import Word as _Word, synthesize_scenes

log = logging.getLogger(__name__)
Progress = Callable[[str], None]

Look = Literal["boy", "girl", "man", "woman", "kid", "old-man", "old-woman"]
Pose = Literal["stand", "walk", "run", "sit", "point", "arms-up", "facepalm", "shrug", "hands-on-hips", "think",
               "cry", "lie", "wave", "hold"]
Face = Literal["neutral", "happy", "laugh", "shock", "angry", "sad", "smirk", "cry", "nervous", "confused", "sleepy",
               "love", "dead"]
Emote = Literal["none", "!", "?", "!?", "sweat", "anger", "hearts", "zzz", "sparkle", "lines"]
Prop = Literal["none", "phone", "book", "paper", "cup", "bag", "laptop", "ball", "plate", "remote"]
Setting = Literal["living-room", "classroom", "kitchen", "bedroom", "street", "office", "bathroom", "park", "shop",
                  "exam-hall", "blank"]
Camera = Literal["wide", "close", "punch", "shake"]
Action = Literal["none", "jump", "shake", "fall", "spin", "walk-in-left", "walk-in-right", "walk-out-left",
                 "walk-out-right"]
Spot = Literal["far-left", "left", "center", "right", "far-right"]

DEFAULT_CAST = "Raju - boy\nPriya - girl\nMom - woman\nDad - man\nTeacher - man"
SPOTS = {"far-left": 320, "left": 640, "center": 960, "right": 1280, "far-right": 1600}
SHORT_GAP = 230  # 9:16: the cast stands this far apart, centred (heads are 168 px wide)
VOICES = {
    "english": {"boy": "en-US-AndrewMultilingualNeural", "kid": "en-US-AnaNeural", "girl": "en-US-AnaNeural",
                "man": "en-IN-PrabhatNeural", "woman": "en-IN-NeerjaExpressiveNeural",
                "old-man": "en-GB-RyanNeural", "old-woman": "en-IN-NeerjaNeural"},
    "hindi": {"boy": "hi-IN-MadhurNeural", "kid": "hi-IN-SwaraNeural", "girl": "hi-IN-SwaraNeural",
              "man": "hi-IN-MadhurNeural", "woman": "hi-IN-SwaraNeural",
              "old-man": "hi-IN-MadhurNeural", "old-woman": "hi-IN-SwaraNeural"},
}
WORDS_PER_SECOND = 2.2  # dialogue with comic pauses


@dataclass
class StickRequest:
    idea: str = ""
    format: str = "long"  # long (16:9 episode) | short (9:16)
    minutes: float = 5.0
    language: str = "english"
    cast: str = DEFAULT_CAST


# ---------- the episode Claude writes ----------

class SCast(BaseModel):
    id: str = Field(description="Short lowercase id, e.g. 'raju'.")
    name: str
    look: Look


class SActor(BaseModel):
    id: str = Field(description="A cast id.")
    spot: Spot = Field(description="Where they stand. Keep each character on the same spot within a scene unless they move.")
    pose: Pose
    face: Face
    facing: Literal["left", "right"] = Field(description="Who they look at: usually toward the person they talk to.")
    emote: Emote = "none"
    prop: Prop = "none"
    prop_text: str = Field(default="", description="1-4 characters on a paper or phone screen (e.g. 'F', '₹93'), or empty.")
    action: Action = Field(default="none", description="Movement during this line: enter or leave the scene, jump, shake, fall, spin.")


class SLine(BaseModel):
    speaker: str = Field(description="The cast id saying this line, or 'none' for a silent beat (a reaction, a look, a pause).")
    line: str = Field(default="", description="What they say, spoken naturally, max 22 words. Empty for a silent beat.")
    pause_before: float = Field(default=0.2, ge=0, le=1.5, description="Seconds of silence before it: 0.6-1.2 before a punchline or a reaction.")
    camera: Camera = Field(default="wide", description="'wide' most of the time, 'close' on a reaction, 'punch' on a punchline, 'shake' on a shock.")
    focus: str = Field(default="", description="Cast id the camera frames on 'close' (default: the speaker).")
    caption: str = Field(default="", description="A meme caption at the top ('POV: ...', 'Meanwhile...', '5 minutes later'), usually empty.")
    actors: list[SActor] = Field(description="Everyone on screen during this line, with their pose, face and position now.")
    sounds: list[SoundCue] = Field(default_factory=list, description="0-2 sound effects on a word of the line (or word '*' for a silent beat).")


class SScene(BaseModel):
    setting: Setting
    sign: str = Field(default="", description="A word on the set (a door sign, the board, a shop name), or empty.")
    lines: list[SLine]


class Episode(BaseModel):
    title: str = Field(description="The episode's title, a relatable situation (used as the YouTube title).")
    logline: str = Field(description="One sentence: the premise and the twist.")
    youtube_description: str = Field(description="2-3 natural sentences about the episode, then one line inviting viewers to subscribe. No hashtags.")
    tags: list[str] = Field(description="8-15 search tags.")
    hashtags: list[str] = Field(description="3 hashtags without '#'.")
    music: str = Field(default="light-playful", description="Background music name from the music list (the user's own track when one fits), or 'none'.")
    cast: list[SCast] = Field(description="The characters in this episode (from the given cast; add a minor one only if needed).")
    scenes: list[SScene]


def _system(short: bool, minutes: float, language: str) -> str:
    lang = ("natural Indian English, the way young Indians talk at home and school" if language == "english"
            else "everyday Hindi in Devanagari script, as families really talk")
    if short:
        form = """a YouTube Short (9:16), 25-50 seconds: ONE situation, 5-12 lines. The first line (with a 'POV:' \
caption) hooks in under 2 seconds; the punchline lands in the last 5 seconds, and the ending can loop back to \
the start. At most 3 characters, standing close together (spots left, center, right)."""
    else:
        words = int(minutes * 60 * WORDS_PER_SECOND)
        form = f"""a {minutes:g}-minute YouTube episode (16:9), about {words} words of dialogue in 4-8 scenes. One \
story: a relatable setup, an escalating problem with two or three complications, a twist, and a payoff that \
calls back to the start. Running gags and callbacks across scenes. Every scene ends on a laugh."""
    return f"""You write stick-figure comedy for the channel Stickcident: relatable everyday moments (school, \
exams, parents, siblings, friends, phones, food, chores) told with a small recurring cast. You write {form}

The dialogue is in {lang}. Short, punchy, natural lines; let silence and reactions do work (silent beats with \
speaker 'none', a 0.6-1.2 s pause before a punchline, the camera punching in or closing on a reaction). Show \
emotion with poses, faces and emotes: a facepalm, a shocked face with '!', sweat when nervous, a jump for joy, \
someone falling over when stunned.

Clean, family-friendly humour that anyone can relate to. No politics, religion, real people, brands, insults \
about groups, or anything mean-spirited. Never use these phrases: {", ".join(AI_CLICHES)}.

The lines appear as small subtitles under the scene, so keep each one short (a few words to one sentence). \
Use the kitchen sink (washing dishes), the sofa, the classroom desks or the bathroom door as the stage for \
everyday situations.

Staging: every line lists everyone on screen with their spot, pose, face and facing (toward who they talk \
to). Keep spots steady within a scene. Use walk-in/walk-out actions for entrances and exits, and change the \
setting for a new scene."""


def parse_cast(text: str) -> list[dict]:
    out = []
    for row in (text or DEFAULT_CAST).splitlines():
        if not row.strip():
            continue
        name, _, look = row.partition("-")
        look = look.strip().lower() or "boy"
        out.append({"id": re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-") or f"c{len(out)}",
                    "name": name.strip(), "look": look if look in get_args(Look) else "boy"})
    return out


def write_episode(cfg: Config, req: StickRequest, recent: list[str]) -> Episode:
    short = req.format == "short"
    cast = parse_cast(req.cast)
    prompt = ("The cast (use these ids and looks):\n" + "\n".join(f"- {c['id']}: {c['name']} ({c['look']})" for c in cast)
              + (f"\n\nThe idea: {req.idea}" if req.idea.strip() else "\n\nPick a fresh, relatable situation yourself.")
              + ("\n\nRecent episodes (don't repeat their premise):\n" + "\n".join(f"- {t}" for t in recent[-20:]) if recent else "")
              + "\n\n" + media.prompt_block(cfg))
    return ask(cfg.ai_backend, cfg.claude_model, _system(short, req.minutes, req.language), prompt, Episode,
               allow_web=False, effort=cfg.claude_effort, timeout=1800)


# ---------- from the episode to the editor's props ----------

def build(ep: Episode, req: StickRequest, cfg: Config, work: Path, progress: Progress) -> dict:
    short = req.format == "short"
    spots = SPOTS
    looks = {c.id: c.look for c in ep.cast}
    voices = VOICES.get(req.language, VOICES["english"])
    lines = [(si, li, ln) for si, sc in enumerate(ep.scenes) for li, ln in enumerate(sc.lines)]

    # One take per character (their lines in order), cut per line: each voice stays consistent.
    progress("Recording the voices")
    audio: dict[tuple[int, int], object] = {}
    for cid in sorted({ln.speaker for _, _, ln in lines if ln.speaker in looks and ln.line.strip()}):
        mine = [(si, li, ln) for si, li, ln in lines if ln.speaker == cid and ln.line.strip()]
        takes = synthesize_scenes([ln.line for _, _, ln in mine], voices.get(looks[cid], voices["man"]),
                                  work / "audio" / cid, cfg.tts_engine, cfg.kokoro_voice, cfg.voice_rate)
        for (si, li, _), sa in zip(mine, takes):
            audio[(si, li)] = sa

    sfx = write_sfx(work / "sfx")
    sfx.update(media.uploaded_for(cfg, list(sfx), work / "sfx"))
    rel = lambda p: Path(p).relative_to(work).as_posix()  # noqa: E731
    shots, cues, spoken, used = [], [], [], {}
    t = 0.0
    for si, li, ln in lines:
        scene = ep.scenes[si]
        sa = audio.get((si, li))
        lead = round(ln.pause_before, 2)
        talk = media_seconds(sa.path) if sa else 0.0
        duration = round(lead + (talk + 0.3 if sa else max(1.1, 0.9)), 3)
        words = [{"text": w.text, "start": round(w.start, 3), "end": round(w.end, 3)} for w in (sa.words if sa else [])]
        # A Short frames the cast close: whoever is on screen stands evenly spaced around the centre, in
        # the order of their spots, so big heads never overlap.
        order = sorted([a for a in ln.actors if a.id in looks], key=lambda a: list(SPOTS).index(a.spot))
        xs = {a.id: (960 + (k - (len(order) - 1) / 2) * SHORT_GAP if short else spots.get(a.spot, 960))
              for k, a in enumerate(order)}
        actors = [{"id": a.id, "x": round(xs[a.id]), "pose": a.pose, "face": a.face,
                   "facing": 1 if a.facing == "right" else -1, "emote": a.emote, "prop": a.prop,
                   "propText": a.prop_text[:6], "action": a.action} for a in ln.actors if a.id in looks]
        shots.append({"start": round(t, 3), "duration": duration, "scene": si, "setting": scene.setting,
                      "sign": scene.sign or None, "caption": ln.caption or None, "camera": ln.camera,
                      "focus": ln.focus or None, "actors": actors,
                      "speaker": ln.speaker if sa else None, "text": ln.line if sa else None, "words": words,
                      "audio": rel(sa.path) if sa else None, "lead": lead})
        if sa:
            spoken += [(t + lead + w.start, t + lead + w.end) for w in sa.words]
            cues += media.resolve_cues([c for c in ln.sounds if c.word.strip() != "*"], sa.words, t + lead, cfg,
                                       work / "sfx", rel, 2, used)
        for c in [c for c in ln.sounds if c.word.strip() == "*"][:1]:
            cues += media.resolve_cues([c.model_copy(update={"word": "beat"})], [_Word("beat", lead, lead + 0.3)], t, cfg,
                                       work / "sfx", rel, 1, used)
        if li == 0 and si > 0 and "whoosh" in sfx:  # a new place: a whoosh on the cut
            cues.append({"src": rel(sfx["whoosh"]), "at": round(max(0.0, t - 0.1), 3), "volume": 0.4, "name": "whoosh"})
        t += duration
    t += 0.6
    track = media.pick_music(cfg, ep.music or "light-playful", work / "music", t)
    props = {
        "fps": cfg.fps, "duration": round(t, 3), "title": ep.title, "vertical": short,
        "cast": [{"id": c.id, "name": c.name, "look": c.look} for c in ep.cast],
        "shots": shots, "music": rel(track) if track else None, "cues": cues,
        "speech": media.speech_spans(spoken), "sfx": {k: rel(p) for k, p in sfx.items()},
    }
    props["sfxLevels"] = media.level_sounds(props, work, [s["audio"] for s in shots if s.get("audio")])
    return props


# ---------- the run ----------

def _history(cfg: Config) -> Path:
    return cfg.output_dir / "stick_history.json"


def run_stick(cfg: Config, req: StickRequest, progress: Progress = log.info) -> dict:
    from .fsutil import move
    from .llm import meter_records, summarize_usage
    from .pipeline import _render_slot, slugify

    short = req.format == "short"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    work = cfg.output_dir / f"{stamp}-{uuid.uuid4().hex[:4]}-stick-working"
    work.mkdir(parents=True, exist_ok=True)
    progress(f"Saving progress in {work.name}")
    try:
        recent = json.loads(_history(cfg).read_text(encoding="utf-8")) if _history(cfg).exists() else []
        progress("Claude is writing the episode" if not short else "Claude is writing the Short")
        ep = write_episode(cfg, req, recent)
        (work / "episode.json").write_text(ep.model_dump_json(indent=2), encoding="utf-8")
        props = build(ep, req, cfg, work, progress)
        progress(f"Editing the video ({props['duration'] / 60:.1f} min)")
        cli = _remotion_cli()
        if cli is None:
            raise RuntimeError("Node.js or the Remotion packages are not installed (run start.bat / start.sh)")
        out = work / "reel.mp4"
        with _render_slot(cfg):
            _render_remotion(cli, props, out, composition="StickStory", crf=18, timeout=4 * 3600)
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", "2", "-i", str(out), "-frames:v", "1", "-q:v", "3",
                        str(work / "thumbnail.jpg")], check=False)
        progress("Verifying video quality")
        info = probe(out)
        want = (1080, 1920) if short else (1920, 1080)
        issues = []
        if (info.get("width"), info.get("height")) != want:
            issues.append(f"Resolution is {info.get('width')}x{info.get('height')}, expected {want[0]}x{want[1]}.")
        if not info.get("has_audio"):
            issues.append("No audio track.")
        final = cfg.output_dir / f"{stamp}-{slugify(ep.title)}-stick"
        move(work, final)
        report = {
            "id": final.name, "format": "short" if short else "long", "length": "short" if short else "stick",
            "source": "stick", "topic": ep.title, "topic_source": "stick story", "style": "comedy", "category": "Comedy",
            "title": ep.title, "why_chosen": ep.logline, "narration": " ".join(l.line for s in ep.scenes for l in s.lines if l.line),
            "created_at": stamp, "verified": not issues, "score": None, "issues": issues, "checks": {"probe": info},
            "attempts": 1, "video": str(final / "reel.mp4"), "thumbnail": str(final / "thumbnail.jpg"),
            "duration_seconds": round(props["duration"], 1), "editor": "remotion (StickStory)", "captions": False,
            "voice": req.language, "youtube_title": ep.title[:100],
            "youtube_description": ep.youtube_description.strip(), "youtube_hashtags": ep.hashtags[:3],
            "youtube_tags": ep.tags, "caption": ep.youtube_description.strip(), "hashtags": ep.hashtags,
        }
        (final / "props.json").write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
        report["usage"] = summarize_usage(meter_records())
        (final / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        _history(cfg).write_text(json.dumps((recent + [ep.title])[-60:], ensure_ascii=False), encoding="utf-8")
        progress("Done" if not issues else "Done, but it did not pass every check — review before posting")
        return report
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        raise


def run_stick_job(cfg: Config, req: StickRequest, count: int, progress: Progress) -> list[dict]:
    """The app's job: `count` episodes or Shorts, one after another, in the shared video slot."""
    from .llm import set_limit_reporter, start_meter, usage_line
    from .pipeline import Paused, _video_slot, done_line, set_pause_check

    reports = []
    should_pause = getattr(progress, "should_pause", None)
    for i in range(count):
        vp = (lambda m, n=i + 1: progress(f"[V{n}] {m}")) if count > 1 else progress
        with _video_slot(cfg):
            if should_pause and should_pause():
                vp("§skip {}")
                continue
            set_pause_check(should_pause)
            set_limit_reporter(vp)
            start_meter(lambda r, vp=vp: vp(usage_line(r)))
            vp(f"=== Video {i + 1}/{count} ===")
            try:
                reports.append(run_stick(cfg, req, vp))
                vp(done_line(reports[-1]))
            except Paused:
                vp("Paused.")
            except Exception as exc:
                log.exception("Stick video %d failed", i + 1)
                vp(f"Video {i + 1} failed: {exc}")
    return reports
