"""The low-poly job: write the story, record the narration, time it, mix the soundtrack, render, check, file it in the
library. Each step is saved (lowpoly-checkpoint.json), so Pause or a crash continues from the last finished step."""
from __future__ import annotations

import json
import logging
import subprocess
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..config import Config
from ..fsutil import move
from ..video import FFMPEG
from . import story as S
from .mix import mix
from .timeline import WORDS, build, spoken

log = logging.getLogger(__name__)
CHECKPOINT = "lowpoly-checkpoint.json"
DEFAULT_VOICE = "en-US-ChristopherNeural"  # calm and low, like the original's narrator
OVER = 1.08  # a Short may run this much over its length before it is tightened
TIGHT_TAIL = 0.2  # the breath after each line when a Short runs long (else timeline.TAIL)
MAX_FASTER = 18  # at most this much faster than asked (percent)


@dataclass
class LowPolyRequest:
    topic: str = ""  # the struggle; empty = Claude picks one the last films didn't use
    format: str = "short"  # short (9:16, `seconds`) | film (`minutes`, 16:9 unless `vertical`)
    seconds: int = 35  # Short: 20-60 (the original runs 33 s)
    minutes: float = 3.5  # film: 2.5-4.5
    vertical: bool = False  # film only: 9:16 instead of 16:9
    voice: str = ""  # '' = DEFAULT_VOICE
    pace: int = 0  # speaking speed in percent (-20..+20)
    watermark: str = "Life of a man"  # the channel's name at the top ('' = none)
    dof: bool = True  # depth of field (off renders faster on a slow machine)
    words: str = "on"  # words on screen: on (subtitles + time stamps, like the original) | stamps (time stamps only) | off


def _thumb_time(props: dict) -> float:
    """A face close-up near the middle, else 40% in."""
    shots = props["shots"]
    for s in shots[len(shots) // 3:] + shots[: len(shots) // 3]:
        if s["camera"] in ("face", "face-top"):
            return s["start"] + s["duration"] * 0.5
    return props["duration"] * 0.4


def _record(cfg: Config, story: S.Story, req: LowPolyRequest, work: Path, progress, pace: int, take: str = "audio") -> dict[int, dict]:
    from ..voice import synthesize_scenes

    idx = [i for i, s in enumerate(story.shots) if s.line.strip()]
    voice = req.voice.strip() or DEFAULT_VOICE
    rate = f"{max(-30, min(30, int(pace))):+d}%"
    progress(f"Recording the narration ({len(idx)} lines, {voice.split(':')[-1]}, {rate})")
    takes = synthesize_scenes([story.shots[i].line.strip() for i in idx], voice, work / take, cfg.tts_engine, cfg.kokoro_voice, rate)
    from ..verify import probe

    out = {}
    for i, take in zip(idx, takes):
        secs = float(probe(take.path).get("duration") or 0) or (take.words[-1].end if take.words else 1.0)
        out[i] = {"path": str(take.path), "seconds": round(secs, 3), "words": [[w.text, round(w.start, 3), round(w.end, 3)] for w in take.words]}
    return out


def run_lowpoly(cfg: Config, req: LowPolyRequest, progress, resume: str | None = None) -> dict:
    from ..llm import meter_records, summarize_usage
    from ..pipeline import _render_slot, pause_point, slugify
    from ..sticky.render import render
    from ..verify import probe

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    work = cfg.output_dir / resume if resume else cfg.output_dir / f"{stamp}-{uuid.uuid4().hex[:4]}-lowpoly-working"
    work.mkdir(parents=True, exist_ok=True)
    progress(f"Saving progress in {work.name}")
    ck = work / CHECKPOINT
    state = json.loads(ck.read_text(encoding="utf-8")) if ck.exists() else {"stage": "", "stamp": stamp, "request": asdict(req)}
    stamp = state.get("stamp", stamp)

    def save(stage: str) -> None:
        state["stage"] = stage
        ck.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    short = req.format != "film"
    vertical = short or bool(req.vertical)
    seconds = max(20, min(60, int(req.seconds)))
    minutes = max(2.5, min(4.5, float(req.minutes)))
    story_path = work / "story.json"
    if story_path.exists():
        story = S.load(story_path)
    else:
        progress(f"Claude is writing the {'Short' if short else 'film'} ({f'{seconds} s' if short else f'{minutes:g} min'}"
                 f"{', about ' + req.topic if req.topic.strip() else ''})")
        story = S.write(cfg, req.topic.strip(), short=short, seconds=seconds, minutes=minutes, progress=progress)
        S.lock_cast(cfg, story)
        S.save(story, story_path)
        S.remember(cfg, story)
        save("written")
    notes = S.repair(story)
    pause_point()
    audio = {int(k): v for k, v in state.get("audio", {}).items()}
    seed = int(uuid.uuid5(uuid.NAMESPACE_DNS, story.title + stamp).int % 100000)
    look = dict(vertical=vertical, watermark=req.watermark.strip(), seed=seed, words=req.words if req.words in WORDS else "on")
    if not audio or not all(Path(v["path"]).exists() for v in audio.values()):
        pace = int(req.pace)
        audio = _record(cfg, story, req, work, progress, pace)
        if short:  # a Short keeps to its length: breaths tightened first, then spoken a little faster once
            full = build(story, audio, **look)[0]["duration"]
            tight = build(story, audio, tail=TIGHT_TAIL, pauses=0.5, **look)[0]["duration"]
            if tight > seconds * OVER:
                speech = sum(spoken(a) for a in audio.values())
                faster = min(MAX_FASTER, int(round((speech / max(1.0, speech - (tight - seconds)) - 1) * 100)) + 2)
                progress(f"It runs {full:.0f} s for {seconds} s: recording it {faster}% faster")
                pace = int(req.pace) + faster
                audio = _record(cfg, story, req, work, progress, pace, "audio-fast")
            state["pace"] = pace
        state["audio"] = audio
        save("voiced")
    pause_point()
    tighten = {}
    if short and build(story, audio, **look)[0]["duration"] > seconds * OVER:
        tighten = {"tail": TIGHT_TAIL, "pauses": 0.5}
    props, clips, cues, sections = build(story, audio, **look, **tighten)
    props["dof"] = bool(req.dof)
    progress(f"'{story.title}': {len(props['shots'])} shots, " + (f"{props['duration']:.0f} s" if props["duration"] < 90 else
             f"{props['duration'] / 60:.1f} min") + f", {'9:16' if vertical else '16:9'} · {story.problem}")
    soundtrack = work / "soundtrack.wav"
    mixed = state.get("mix") if soundtrack.exists() else None
    if not mixed:
        progress("Making the music and the sound")
        brief = f"soft score for a narrated low-poly animated short about {story.problem}; {story.music_prompt}"
        mixed = mix(cfg, props, clips, cues, sections, work, soundtrack, seed, progress, brief)
        state["mix"] = mixed
        save("mixed")
    pause_point()
    out = work / "reel.mp4"
    if state.get("stage") != "rendered" or not out.exists():
        progress("Editing the Short" if short else "Editing the film")
        with _render_slot(cfg):
            render(props, soundtrack, work, out, progress, composition="LowPoly")
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", f"{_thumb_time(props):.2f}", "-i", str(out), "-frames:v", "1",
                        "-q:v", "3", str(work / "thumbnail.jpg")], check=False)
        save("rendered")
    progress("Checking the video")
    info = probe(out)
    issues = list(notes)
    size = (1080, 1920) if vertical else (1920, 1080)
    if (info.get("width"), info.get("height")) != size:
        issues.append(f"Resolution is {info.get('width')}x{info.get('height')}, expected {size[0]}x{size[1]}.")
    if not info.get("has_audio"):
        issues.append("No audio track.")
    if abs(float(info.get("duration") or 0) - props["duration"]) > 2:
        issues.append(f"The video runs {info.get('duration')} s, the timeline {props['duration']:.1f} s.")
    if short and props["duration"] > 62:
        issues.append(f"The Short runs {props['duration']:.0f} s (over a minute).")
    ck.unlink(missing_ok=True)
    final = cfg.output_dir / f"{stamp}-{slugify(story.title.strip('. '))}-lowpoly{'-short' if short else ''}"
    move(work, final)
    narration = " ".join(s.line.strip() for s in story.shots if s.line.strip())
    report = {
        "id": final.name, "format": "short" if vertical and short else "long", "length": "short" if short else "lowpoly",
        "source": "lowpoly", "topic": story.problem, "topic_source": req.topic.strip() and "your topic" or "Claude's pick",
        "style": "story", "category": "Life & People", "title": story.title.strip(), "why_chosen": story.problem,
        "narration": narration, "created_at": stamp, "verified": not issues, "score": None, "issues": issues,
        "checks": {"probe": info}, "attempts": 1, "video": str(final / "reel.mp4"), "thumbnail": str(final / "thumbnail.jpg"),
        "duration_seconds": round(props["duration"], 1), "editor": "remotion (LowPoly)", "captions": look["words"] == "on", "words_on_screen": look["words"],
        "voice": req.voice.strip() or DEFAULT_VOICE, "voice_rate": f"{int(state.get('pace', req.pace)):+d}%", "music": mixed.get("music", ""),
        "sound_cues": mixed.get("sound_cues"), "lowpoly_request": asdict(req), "thumbnail_text": story.thumbnail_text,
        "cast": [c.name for c in story.cast], "youtube_title": story.youtube_title[:100], "youtube_description": story.description.strip(),
        "youtube_tags": story.tags, "youtube_hashtags": story.hashtags[:3], "caption": story.description.strip(),
        "hashtags": story.hashtags,
    }
    rel = [{**c, "path": str(Path(c["path"]).relative_to(work)) if Path(c["path"]).is_relative_to(work) else c["path"]} for c in clips]
    (final / "props.json").write_text(json.dumps({**props, "clips": rel, "cues": cues, "sections": sections}, ensure_ascii=False), encoding="utf-8")
    report["usage"] = summarize_usage(meter_records())
    (final / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    progress("Done" if not issues else "Done, but it did not pass every check: review before posting")
    return report


def run_lowpoly_job(cfg: Config, req: LowPolyRequest, count: int, progress, resume: list[str] | None = None) -> list[dict]:
    """The app's job: `count` videos one after another in the shared video slot (or the saved ones resumed)."""
    from ..llm import set_limit_reporter, start_meter, usage_line
    from ..pipeline import Paused, _video_slot, done_line, set_pause_check

    reports = []
    should_pause = getattr(progress, "should_pause", None)
    todo = list(resume or []) or [None] * count
    for i, folder in enumerate(todo):
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
                saved = folder and cfg.output_dir / folder / CHECKPOINT
                mine = LowPolyRequest(**json.loads(saved.read_text(encoding="utf-8")).get("request", {})) if saved and saved.exists() else req
                reports.append(run_lowpoly(cfg, mine, vp, folder))
                vp(done_line(reports[-1]))
            except Paused:
                vp("Paused: progress saved. Press Resume to carry on from here.")
            except Exception as exc:  # noqa: BLE001
                log.exception("Low-poly video %d failed", i + 1)
                vp(f"Video {i + 1} failed: {exc}")
    return reports


def unfinished(cfg: Config) -> list[str]:
    return sorted(p.parent.name for p in Path(cfg.output_dir).glob(f"*-lowpoly-working/{CHECKPOINT}"))
