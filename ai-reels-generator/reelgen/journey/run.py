"""The Journey job: write and fact-check the stages, draw them, check the pictures, animate between them, join
them, lay the place's sounds, edit, check, file it in the library. Every step is saved (journey-checkpoint.json),
so Pause, a crash or a day without Hugging Face minutes carries on from the last finished step."""
from __future__ import annotations

import json
import logging
import subprocess
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .. import anim_engine, hfcloud
from ..config import Config
from ..fsutil import move
from ..video import FFMPEG
from . import frames, motion, sound
from . import story as S

log = logging.getLogger(__name__)
CHECKPOINT = "journey-checkpoint.json"
ENGINES = ("auto", "cloud", "local")


@dataclass
class JourneyRequest:
    idea: str = ""  # what goes on the journey ('a tomato that falls off a truck'); empty = Claude picks
    seconds: int = 60  # 30-90
    top: str = ""  # your own line above the picture (else Claude's)
    bottom: str = ""  # your own line below it
    words: bool = True  # the two lines on screen
    labels: bool = False  # the real time under the picture at each stage ('WEEK 6')
    engine: str = "auto"  # auto (Hugging Face while its free minutes last, then this computer) | cloud | local


def can_make(engine: str = "auto") -> str:
    """'' when something can draw and animate, else why not (said before Claude writes anything)."""
    if engine == "cloud" and not hfcloud.ready():
        return "No Hugging Face token: save it in the Anim tab (Hugging Face box), or choose 'This computer'"
    if engine == "local" and not anim_engine.installed():
        return "The AI engine isn't installed: install it in the Anim tab, or choose Hugging Face"
    if not hfcloud.ready() and not anim_engine.installed():
        return ("Nothing here can draw photoreal pictures yet: install the free AI engine (Anim tab), or save a free "
                "Hugging Face token (Anim tab, Hugging Face box)")
    return ""


def grade(j: S.Journey, starts: list[float]) -> list[dict]:
    """Each stage's light for the editor, with a lightning flash where the stage's thunder falls."""
    out = []
    for k, s in enumerate(j.stages):
        g = {"at": starts[k], "until": round(starts[k] + s.seconds, 3), "light": s.light}
        thunder = [x for x in s.sounds if x.name == "thunder"]
        if thunder:
            g["flash"] = round(starts[k] + thunder[0].at * s.seconds, 3)
        out.append(g)
    return out


def run_journey(cfg: Config, req: JourneyRequest, progress, resume: str | None = None) -> dict:
    from ..llm import meter_records, summarize_usage
    from ..pipeline import _render_slot, pause_point, slugify
    from ..sticky.render import render
    from ..verify import probe

    engine = req.engine if req.engine in ENGINES else "auto"
    why = can_make(engine)
    if why:
        raise RuntimeError(why)
    seconds = max(30, min(90, int(req.seconds or 60)))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    work = cfg.output_dir / resume if resume else cfg.output_dir / f"{stamp}-{uuid.uuid4().hex[:4]}-journey-working"
    work.mkdir(parents=True, exist_ok=True)
    progress(f"Saving progress in {work.name}")
    ck = work / CHECKPOINT
    state = json.loads(ck.read_text(encoding="utf-8")) if ck.exists() else {"stage": "", "stamp": stamp, "request": asdict(req),
                                                                            "seed": uuid.uuid4().int % 100000}
    stamp, seed = state.get("stamp", stamp), int(state.get("seed", 4242))

    def save(stage: str) -> None:
        state["stage"] = stage
        ck.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    # 1. the story, fact-checked
    path = work / "journey.json"
    if path.exists():
        j = S.load(path)
        progress(f"Resuming '{j.title}'")
    else:
        j = S.write(cfg, req.idea, seconds, progress, req.top, req.bottom)
        S.save(j, work / "draft.json")
        j, issues, findings = S.check(cfg, j, progress)
        state["issues"], state["findings"] = issues, findings
        state["notes"] = S.repair(j, seconds)
        S.save(j, path)
        S.remember(cfg, j)
        save("written")
    pause_point()
    progress(f"'{j.title}': {j.subject}, {len(j.stages)} stages, {sum(s.seconds for s in j.stages):.0f} s · "
             f"'{j.top_text}' / '{j.bottom_text}'")
    # 2. the pictures, each checked by Claude (the base ones before the chain grows from them)
    state["picture_check"], state["drew"] = frames.make(cfg, j, work, seed, state, progress, engine, pause_point, save)
    pause_point()
    # 3. the motion between them
    made_by = motion.make(j, work, seed, engine, progress, pause_point)
    state["clips"] = made_by
    save("clips")
    pause_point()
    story, bg, starts = motion.join(j, work, made_by, progress)
    total = round(sum(s.seconds for s in j.stages), 3)
    # 4. the place's sounds
    soundtrack = work / "soundtrack.wav"
    if not soundtrack.exists() or not state.get("sound"):
        progress("Laying the sounds of the place")
        state["sound"] = sound.mix(j, soundtrack, seed)
        save("mixed")
    # 5. the edit
    props = {"fps": motion.FPS, "duration": total, "story": story.name, "bg": bg.name,
             "top": j.top_text if req.words else "", "bottom": j.bottom_text if req.words else "",
             "labels": [{"at": starts[k] + 0.2, "until": starts[k] + s.seconds - 0.1, "text": s.elapsed.upper()}
                        for k, s in enumerate(j.stages)] if req.labels else []}
    if state.get("drew") == "local":  # this computer's pictures can't repaint a sky: the editor grades each stage's light
        props["grade"] = grade(j, starts)
    out = work / "reel.mp4"
    if state.get("stage") != "rendered" or not out.exists():
        progress("Editing the Short")
        with _render_slot(cfg):
            render(props, soundtrack, work, out, progress, composition="Journey")
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", f"{total * 0.92:.2f}", "-i", str(out), "-frames:v", "1",
                        "-q:v", "3", str(work / "thumbnail.jpg")], check=False)
        save("rendered")
    # 6. checks and the library
    progress("Checking the video")
    info = probe(out)
    issues = list(state.get("issues") or [])
    if (info.get("width"), info.get("height")) != (1080, 1920):
        issues.append(f"Resolution is {info.get('width')}x{info.get('height')}, expected 1080x1920.")
    if not info.get("has_audio"):
        issues.append("No audio track.")
    if abs(float(info.get("duration") or 0) - total) > 1.5:
        issues.append(f"The video runs {info.get('duration')} s, the stages {total:.1f} s.")
    made = sorted(set(made_by.values()))
    if "dissolve" in made:
        issues.append(f"{sum(1 for v in made_by.values() if v == 'dissolve')} stage(s) could not be animated and "
                      "dissolve instead (Resume when Hugging Face has minutes or the AI engine is free)")
    ck.unlink(missing_ok=True)
    final = cfg.output_dir / f"{stamp}-{slugify(j.title)}-journey"
    move(work, final)
    credits = state.get("sound", {}).get("credits", [])
    desc = j.description.strip() + ("\n\n" + "\n".join(credits) if credits else "")
    report = {
        "id": final.name, "format": "short", "length": "short", "source": "journey", "style": "facts",
        "topic": j.subject, "topic_source": "your idea" if req.idea.strip() else "Claude's pick", "category": j.category,
        "title": j.title.strip(), "why_chosen": j.theme, "narration": "", "created_at": stamp,
        "verified": not issues, "score": None, "issues": issues, "checks": {"probe": info}, "attempts": 1,
        "video": str(final / "reel.mp4"), "thumbnail": str(final / "thumbnail.jpg"),
        "duration_seconds": round(total, 1), "editor": "remotion (Journey)", "captions": bool(req.words),
        "journey": {"subject": j.subject, "place": j.place, "top": j.top_text, "bottom": j.bottom_text,
                    "stages": [{"elapsed": s.elapsed, "what": s.what, "fact": s.fact} for s in j.stages]},
        "fact_check": state.get("findings"), "picture_check": state.get("picture_check"), "pictures_by": state.get("drew"),
        "clips_by": made_by, "sound_cues": state.get("sound", {}).get("sounds"), "credits": credits,
        "journey_request": asdict(req), "thumbnail_text": j.thumbnail_text, "music": "none (only the place's sounds)",
        "youtube_title": j.youtube_title[:100], "youtube_description": desc, "youtube_tags": j.tags,
        "youtube_hashtags": j.hashtags[:3], "caption": desc, "hashtags": j.hashtags, "staging_fixes": state.get("notes"),
    }
    (final / "props.json").write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
    report["usage"] = summarize_usage(meter_records())
    (final / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    progress("Done" if not issues else "Done, but it did not pass every check: review before posting")
    return report


def run_journey_job(cfg: Config, req: JourneyRequest, count: int, progress, resume: list[str] | None = None) -> list[dict]:
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
                mine = JourneyRequest(**json.loads(saved.read_text(encoding="utf-8")).get("request", {})) if saved and saved.exists() else req
                reports.append(run_journey(cfg, mine, vp, folder))
                vp(done_line(reports[-1]))
            except Paused:
                vp("Paused: progress saved. Press Resume to carry on from here.")
            except hfcloud.CloudOut as exc:
                vp(f"Paused: {exc}")
            except Exception as exc:  # noqa: BLE001
                log.exception("Journey %d failed", i + 1)
                vp(f"Video {i + 1} failed: {exc}")
    return reports


def unfinished(cfg: Config) -> list[str]:
    return sorted(p.parent.name for p in Path(cfg.output_dir).glob(f"*-journey-working/{CHECKPOINT}"))
