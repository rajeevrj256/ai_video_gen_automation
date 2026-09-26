"""End-to-end run: trends -> script -> voice -> visuals -> video -> verify -> notify.

A video that fails verification is regenerated with the reviewer's feedback, up
to `cfg.max_attempts` times. If every attempt fails, the best one is still
delivered but marked as not verified so you can decide.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from datetime import datetime, timezone
from typing import Callable

from .config import MAX_SECONDS, Config
from .notifier import notify
from .post_copy import apply_post_copy, save_post_text
from .script_writer import write_script
from .trends import Trend, collect_trends, load_history, save_history
from .verify import VerifyResult, check_script, check_video, fact_check_script, review_with_claude
from .video import render_video, voice_seconds
from .visuals import fetch_backgrounds
from .voice import synthesize_scenes

log = logging.getLogger(__name__)

Progress = Callable[[str], None]

FACT_FIXES = 2  # script rewrites allowed per attempt to fix fact-check findings


def slugify(text: str, max_len: int = 40) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:max_len] or "reel"


def run_once(cfg: Config, topic: str | None = None, progress: Progress = log.info, angle_note: str = "") -> dict:
    history_path = cfg.output_dir / "history.json"

    progress("Finding trending topics")
    if topic:
        candidates = [Trend(title=topic, source="manual", context=angle_note)]
    else:
        candidates = collect_trends(cfg.geo, load_history(history_path))

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_dir = cfg.output_dir / f"{stamp}-working"
    run_dir.mkdir(parents=True, exist_ok=True)

    feedback = ""
    script = None
    best: dict | None = None
    for attempt in range(1, cfg.max_attempts + 1):
        tag = f"[attempt {attempt}/{cfg.max_attempts}]"
        progress(f"{tag} Claude is picking the topic and writing the script")
        script = write_script(cfg, candidates, feedback, previous=script if feedback else None)
        if not topic:  # keep later attempts on the chosen topic
            candidates = [c for c in candidates if c.title.lower() == script.topic.lower()] or candidates

        verdict = check_script(script, cfg)
        if not verdict.passed:
            progress(f"{tag} Script rejected: {'; '.join(verdict.issues)}")
            feedback = "\n".join(verdict.issues)
            continue

        # Fact-check the words before paying for voice, footage and a render. A
        # flagged script is fixed here (up to FACT_FIXES times) without using up
        # an attempt; the final review then mostly judges the finished video.
        for fix in range(FACT_FIXES + 1):
            progress(f"{tag} Claude is fact-checking the script")
            facts = fact_check_script(script, cfg)
            if facts.passed or fix == FACT_FIXES:
                break
            progress(f"{tag} Fixing facts: {'; '.join(facts.issues)}")
            fixes = facts.checks["fact_check"].get("fix_instructions", "")
            fixed = write_script(cfg, candidates, "\n".join(facts.issues + ([fixes] if fixes else [])),
                                 previous=script)
            if not check_script(fixed, cfg).passed:
                break  # keep the last script that passed the basic checks
            script = fixed
        if not facts.passed:
            progress(f"{tag} Still has unconfirmed facts after rewriting: {'; '.join(facts.issues)}")

        progress(f"{tag} Recording voiceover")
        scenes = synthesize_scenes([s.narration for s in script.scenes], cfg.voice, run_dir / "audio",
                                   cfg.tts_engine, cfg.kokoro_voice)
        spoken = voice_seconds(scenes)
        if spoken > MAX_SECONDS - 1 and attempt < cfg.max_attempts:
            # Too long to fit: skip the render and ask for a shorter script. (On the last
            # attempt it's rendered anyway, so there's still a video to look at.)
            words = sum(len(s.narration.split()) for s in script.scenes)
            feedback = (f"The voiceover runs {spoken:.1f}s but the whole video must stay under {MAX_SECONDS}s. "
                        f"Cut the narration from {words} to about {int(words * (MAX_SECONDS - 3) / spoken)} words.")
            progress(f"{tag} Script too long: {feedback}")
            continue
        progress(f"{tag} Downloading footage")
        backgrounds = fetch_backgrounds([s.visual_queries for s in script.scenes], cfg.pexels_api_key,
                                        cfg.width, cfg.height, run_dir / "backgrounds")
        progress(f"{tag} Editing the video (takes a few minutes)")
        rendered = render_video(script.title, scenes, backgrounds, cfg, run_dir / "reel.mp4",
                                graphics=[s.graphic for s in script.scenes],
                                transitions=[s.transition for s in script.scenes])

        progress(f"{tag} Verifying video quality")
        verdict = check_video(run_dir / "reel.mp4", scenes, script, cfg)
        if verdict.passed:
            progress(f"{tag} Claude is reviewing the finished video")
            stock = any(p.suffix == ".mp4" for clips in backgrounds for p in clips)
            _, review = review_with_claude(run_dir / "reel.mp4", script, cfg, stock_footage=stock)
            verdict = _merge(verdict, review)
        if not facts.passed:  # unresolved fact-check findings also block "verified"
            verdict.passed = False
            verdict.issues += [i for i in facts.issues if i not in verdict.issues]

        attempt_result = {"script": script, "rendered": rendered, "verdict": verdict, "attempt": attempt}
        if best is None or (verdict.score or 0) >= (best["verdict"].score or 0):
            best = attempt_result
            # Keep the best attempt's files; later attempts render into a scratch copy.
            _snapshot(run_dir)

        if verdict.passed:
            progress(f"{tag} Passed verification (score {verdict.score})")
            break
        progress(f"{tag} Failed verification: {'; '.join(verdict.issues)}")
        review = verdict.checks.get("review", {})
        feedback = "\n".join(verdict.issues + ([review["fix_instructions"]] if review.get("fix_instructions") else []))

    if best is None:
        shutil.rmtree(run_dir, ignore_errors=True)
        raise RuntimeError(f"No usable script after {cfg.max_attempts} attempts: {feedback}")

    _restore_snapshot(run_dir)
    final_dir = cfg.output_dir / f"{stamp}-{slugify(best['script'].topic)}"
    run_dir.rename(final_dir)
    script, verdict = best["script"], best["verdict"]
    (final_dir / "script.json").write_text(script.model_dump_json(indent=2), encoding="utf-8")

    source = next((c.source for c in candidates if c.title.lower() == script.topic.lower()), "manual" if topic else "unknown")
    report = {
        "id": final_dir.name,
        "topic": script.topic,
        "topic_source": source,
        "why_chosen": script.why_chosen,
        "title": script.title,
        "youtube_title": script.youtube_title,
        "caption": script.caption,
        "hashtags": [h.lstrip("#") for h in script.hashtags],
        "narration": " ".join(s.narration for s in script.scenes),
        "facts_checked": script.facts_checked,
        "created_at": stamp,
        "verified": verdict.passed,
        "score": verdict.score,
        "issues": verdict.issues,
        "checks": verdict.checks,
        "attempts": best["attempt"],
        **{k: str(final_dir / v) for k, v in (("video", "reel.mp4"), ("thumbnail", "thumbnail.jpg"))},
        "duration_seconds": best["rendered"]["duration_seconds"],
        "editor": best["rendered"].get("editor", ""),
    }
    progress("Claude is writing the title, description and trending hashtags")
    try:
        apply_post_copy(report, script, cfg, final_dir)
    except Exception as exc:  # keep the script's draft text rather than lose the video
        log.warning("Post text step failed, keeping the draft caption: %s", exc)
        report.update({"youtube_description": script.caption, "youtube_hashtags": ["shorts"], "youtube_tags": [],
                       "post_text_error": str(exc)[:300]})
        save_post_text(report, final_dir)
    (final_dir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    save_history(history_path, script.topic)

    notify(report, cfg.telegram_bot_token, cfg.telegram_chat_id)
    progress("Done" if report["verified"] else "Done, but it did not pass every check — review before posting")
    return report


def _merge(a: VerifyResult, b: VerifyResult) -> VerifyResult:
    return VerifyResult(passed=a.passed and b.passed, score=b.score, issues=a.issues + b.issues,
                        checks={**a.checks, **b.checks})


def _snapshot(run_dir) -> None:
    best = run_dir / "_best"
    shutil.rmtree(best, ignore_errors=True)
    best.mkdir()
    for name in ("reel.mp4", "thumbnail.jpg", "review_frames.jpg"):
        if (run_dir / name).exists():
            shutil.copy2(run_dir / name, best / name)


def _restore_snapshot(run_dir) -> None:
    best = run_dir / "_best"
    if best.exists():
        for f in best.iterdir():
            shutil.move(str(f), run_dir / f.name)
        best.rmdir()
    for scratch in ("audio", "backgrounds", "sfx"):
        shutil.rmtree(run_dir / scratch, ignore_errors=True)
    for scratch in ("props.json", "music.mp3"):  # render inputs for Remotion
        (run_dir / scratch).unlink(missing_ok=True)


def run(cfg: Config, count: int = 1, topic: str | None = None, progress: Progress = log.info) -> list[dict]:
    reports = []
    for i in range(count):
        progress(f"=== Video {i + 1}/{count} ===")
        # Trending batches get a new topic each time (used topics are skipped). A batch on
        # one fixed topic needs a different angle per video, or they'd all come out alike.
        angle = ""
        if topic and count > 1:
            made = "; ".join(f"'{r['title']}' ({r['topic']})" for r in reports) or "none yet"
            angle = (f"Video {i + 1} of {count} on this topic. Already made: {made}. Pick a clearly "
                     "different angle, facts and hook from those, still on this topic.")
        try:
            reports.append(run_once(cfg, topic, progress, angle))
        except Exception as exc:
            log.exception("Video %d failed", i + 1)
            progress(f"Video {i + 1} failed: {exc}")
    return reports
