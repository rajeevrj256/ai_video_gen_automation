"""The Sticky job: write the film, time it, make the soundtrack, render, check, file it in the library. Each step is
saved (sticky-checkpoint.json), so Pause or a crash continues from the last finished step."""
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
from . import film as F
from .mixdown import mix
from .render import render
from .timeline import build, repair

log = logging.getLogger(__name__)
CHECKPOINT = "sticky-checkpoint.json"
STAGES = ("written", "mixed", "rendered")


@dataclass
class StickyRequest:
    topic: str = ""  # the problem; empty = Claude picks one the last films didn't use
    minutes: float = 3.0  # 2.5-4, like the reference films
    whispers: bool = True  # the inner voice's lines whispered (three of the seven references do)


def _thumb_time(props: dict) -> float:
    """A frame that sells the film: the first face close-up, else the turn's first scene, else 40% in."""
    for kind, act in (("face", None), ("scene", "turn"), ("scene", "loop")):
        for s in props["shots"]:
            if s["kind"] == kind and (act is None or s.get("act") == act):
                return s["start"] + s["duration"] * 0.6
    return props["duration"] * 0.4


def run_sticky(cfg: Config, req: StickyRequest, progress, resume: str | None = None) -> dict:
    from ..llm import meter_records, summarize_usage
    from ..pipeline import _render_slot, pause_point, slugify
    from ..verify import probe

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    work = cfg.output_dir / resume if resume else cfg.output_dir / f"{stamp}-{uuid.uuid4().hex[:4]}-sticky-working"
    work.mkdir(parents=True, exist_ok=True)
    progress(f"Saving progress in {work.name}")
    ck = work / CHECKPOINT
    state = json.loads(ck.read_text(encoding="utf-8")) if ck.exists() else {"stage": "", "stamp": stamp, "request": asdict(req)}
    stamp = state.get("stamp", stamp)

    def save(stage: str) -> None:
        state["stage"] = stage
        ck.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    film_path = work / "film.json"
    if film_path.exists():
        film = F.load(film_path)
    else:
        progress(f"Claude is writing the film ({req.minutes:g} min{', about ' + req.topic if req.topic else ''})")
        film = F.write_film(cfg, req.topic.strip(), max(2.0, min(4.5, req.minutes)), progress)
        F.save(film, film_path)
        F.remember(cfg, film)
        save("written")
    pause_point()
    notes = repair(film)
    props, cues, sections = build(film)
    shots = len(props["shots"])
    progress(f"'{film.title}': {shots} shots, {props['duration'] / 60:.1f} min · {film.problem}")
    soundtrack = work / "soundtrack.wav"
    mixed = state.get("mix") if soundtrack.exists() else None
    if not mixed:
        progress("Making the music and the sound design")
        seed = int(uuid.uuid5(uuid.NAMESPACE_DNS, film.title + stamp).int % 100000)
        mixed = mix(cfg, props, cues, sections, work, soundtrack, seed, req.whispers, progress)
        state["mix"] = mixed
        save("mixed")
    pause_point()
    out = work / "reel.mp4"
    if state.get("stage") != "rendered" or not out.exists():
        progress("Editing the film")
        with _render_slot(cfg):
            render(props, soundtrack, work, out, progress)
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", f"{_thumb_time(props):.2f}", "-i", str(out), "-frames:v", "1",
                        "-q:v", "3", str(work / "thumbnail.jpg")], check=False)
        save("rendered")
    progress("Checking the film")
    info = probe(out)
    issues = list(notes)
    if (info.get("width"), info.get("height")) != (1920, 1080):
        issues.append(f"Resolution is {info.get('width')}x{info.get('height')}, expected 1920x1080.")
    if not info.get("has_audio"):
        issues.append("No audio track.")
    if abs(float(info.get("duration") or 0) - props["duration"]) > 2:
        issues.append(f"The film runs {info.get('duration')} s, the timeline {props['duration']:.1f} s.")
    ck.unlink(missing_ok=True)
    final = cfg.output_dir / f"{stamp}-{slugify(film.title.strip('. '))}-sticky"
    move(work, final)
    captions = [line for s in props["shots"] for line in (s.get("caption") or {}).get("lines", [])]
    report = {
        "id": final.name, "format": "long", "length": "sticky", "source": "sticky", "topic": film.problem,
        "topic_source": req.topic and "your topic" or "Claude's pick", "style": "story", "category": "Life & People",
        "title": film.title.strip(), "why_chosen": film.problem, "narration": " ".join(captions),
        "created_at": stamp, "verified": not issues, "score": None, "issues": issues, "checks": {"probe": info},
        "attempts": 1, "video": str(final / "reel.mp4"), "thumbnail": str(final / "thumbnail.jpg"),
        "duration_seconds": round(props["duration"], 1), "editor": "remotion (Sticky)", "captions": True,
        "music": mixed.get("music", ""), "sound_cues": mixed.get("sound_cues"), "whispers": mixed.get("whispers"),
        "sticky_request": asdict(req), "thumbnail_text": film.thumbnail_text, "meter": film.meter.model_dump(),
        "youtube_title": film.youtube_title[:100], "youtube_description": film.description.strip(),
        "youtube_tags": film.tags, "youtube_hashtags": film.hashtags[:3], "caption": film.description.strip(), "hashtags": film.hashtags,
    }
    (final / "props.json").write_text(json.dumps({**props, "cues": cues, "sections": sections}, ensure_ascii=False), encoding="utf-8")
    report["usage"] = summarize_usage(meter_records())
    (final / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    progress("Done" if not issues else "Done, but it did not pass every check: review before posting")
    return report


def run_sticky_job(cfg: Config, req: StickyRequest, count: int, progress, resume: list[str] | None = None) -> list[dict]:
    """The app's job: `count` films one after another in the shared video slot (or the saved ones resumed)."""
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
                mine = StickyRequest(**json.loads(saved.read_text(encoding="utf-8")).get("request", {})) if saved and saved.exists() else req
                reports.append(run_sticky(cfg, mine, vp, folder))
                vp(done_line(reports[-1]))
            except Paused:
                vp("Paused: progress saved. Press Resume to carry on from here.")
            except Exception as exc:  # noqa: BLE001
                log.exception("Sticky film %d failed", i + 1)
                vp(f"Video {i + 1} failed: {exc}")
    return reports


def unfinished(cfg: Config) -> list[str]:
    return sorted(p.parent.name for p in Path(cfg.output_dir).glob(f"*-sticky-working/{CHECKPOINT}"))
