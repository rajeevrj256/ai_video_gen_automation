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
import threading
import time
import uuid
from dataclasses import asdict, replace
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Callable

from .fsutil import move, rebase
from .config import MAX_SECONDS, Config
from .llm import meter_add_earlier, meter_records, set_limit_reporter, start_meter, summarize_usage, usage_line
from .notifier import notify
from .post_copy import apply_post_copy, save_post_text
from .script_writer import STYLE_NAMES, STYLES as MIX, ReelScript, write_script
from . import repeats
from .trends import Trend, collect_trends, load_history, save_history
from .shortfix import claims_changed, fact_check_scenes, fix_scenes, new_facts
from .verify import VerifyResult, check_script, check_video, fact_check_script, review_with_claude
from .video import render_video, voice_seconds
from .visuals import fetch_backgrounds
from .voice import SceneAudio, Word, synthesize_scenes

log = logging.getLogger(__name__)

Progress = Callable[[str], None]

FACT_FIXES = 2  # script rewrites allowed per attempt to fix fact-check findings

# Videos can run in parallel (cfg.parallel_videos). Most of a video's time is spent
# waiting on Claude and downloads, so those overlap freely. Two things take turns:
# - picking a trending topic, so parallel videos never grab the same one;
# - the Remotion edit, which already uses every CPU core (cfg.parallel_renders slots).
_topic_lock = threading.Lock()
_history_lock = threading.Lock()
_claimed: set[str] = set()  # topics taken by videos still in progress
_render_slots: threading.Semaphore | None = None
_render_slots_size = 0
_video_slots: threading.Semaphore | None = None  # shared by every job, not per batch
_video_slots_size = 0
_slots_lock = threading.Lock()


def slugify(text: str, max_len: int = 40) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:max_len] or "reel"


def run_once(cfg: Config, topic: str | None = None, progress: Progress = log.info, angle_note: str = "") -> dict:
    history_path = cfg.output_dir / "history.json"

    progress("Finding trending topics")
    first_script = None
    if topic:
        # A typed topic is narrowed first to one subject not made before (a small call, checked in code).
        subject = repeats.narrow(cfg, topic, ("short",), progress) if cfg.video_style == "facts" else ""
        candidates = [Trend(title=topic, source="manual", context=" ".join(x for x in (subject, angle_note) if x))]
    else:
        # One video at a time picks from the trends, skipping topics already used or
        # being made right now by a parallel video.
        with _topic_lock:
            with _history_lock:
                used = load_history(history_path)
            candidates = collect_trends(cfg.geo, used + sorted(_claimed))
            progress("[attempt 1/%d] Claude is picking the topic and writing the script" % cfg.max_attempts)
            first_script = write_script(cfg, candidates, "", None)
            first_script = repeats.guard(cfg, first_script, ("short",),
                                         lambda why: write_script(cfg, candidates, why, first_script), progress)
            _claimed.add(first_script.topic)
    claimed = first_script.topic if first_script else None

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_dir = cfg.output_dir / f"{stamp}-{uuid.uuid4().hex[:4]}-working"  # parallel videos can start in the same second
    run_dir.mkdir(parents=True, exist_ok=True)
    progress(f"Saving progress in {run_dir.name}")  # lets a failed job resume from here
    try:
        return _make_video(cfg, topic, progress, candidates, first_script, run_dir, stamp, history_path)
    finally:
        if claimed:
            _claimed.discard(claimed)


def _make_video(cfg: Config, topic: str | None, progress: Progress, candidates: list, first_script,
                run_dir, stamp: str, history_path, resume: dict | None = None) -> dict:
    """The attempt loop. After every finished step it saves a checkpoint (checkpoint.json in
    run_dir); with `resume` it starts at the saved attempt and skips the finished steps."""
    resume = resume or {}
    feedback = resume.get("feedback", "")
    script = ReelScript.model_validate(resume["script"]) if resume.get("script") else None
    best: dict | None = _dec_best(resume.get("best"))
    start = resume.get("attempt", 1)
    meter_add_earlier(resume.get("usage"))
    state = {"topic": topic, "stamp": stamp, "style": cfg.video_style, "candidates": [asdict(c) for c in candidates],
             "best": resume.get("best")}

    def save(**changes) -> None:
        state.update(changes, usage=meter_records())
        (run_dir / CHECKPOINT).write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        pause_point()

    revise: dict | None = None  # after a failed review: fix the flagged scenes, never a new script
    for attempt in range(start, cfg.max_attempts + 1):
        tag = f"[attempt {attempt}/{cfg.max_attempts}]"
        stage = resume.get("stage") if attempt == start else None
        changed: set[int] | None = None  # scenes whose words changed this attempt (None = a new script)
        recheck_web = True  # False when the corrections bring no new figure or name
        earlier: list[str] | None = None  # the fact-check findings the corrections answer
        if stage == "revise":
            revise = {"issues": resume.get("review_issues") or [feedback], "fix": resume.get("review_fix", ""),
                      "facts": bool(resume.get("revise_facts"))}
            stage = None
        if stage:
            progress(f"{tag} Resuming: {STAGE_DONE[stage]} already done")
            facts = _dec_result(resume.get("facts"))
        elif revise and script is not None:
            # A failed review fixes the flagged scenes only: a new script cost ~400k tokens plus a
            # full fact-check, and brought new errors.
            progress(f"{tag} Fixing the scenes the reviewer flagged (keeping the rest of the script)")
            old = script
            script, changed = fix_scenes(script, cfg, revise["issues"], revise["fix"], web=cfg.video_style == "facts")
            changed = claims_changed(old, script, changed)  # new footage queries need no fact-check
            if revise.get("facts") and not changed:
                changed = None  # facts were still unconfirmed and no words changed: check it all again
            recheck_web = new_facts(old, script, changed)
            earlier = list(revise["issues"])
            revise = None
        elif attempt == 1 and first_script is not None:
            script = first_script  # already written while holding the topic lock
        else:
            progress(f"{tag} Claude is picking the topic and writing the script")
            first_write = script is None
            script = write_script(cfg, candidates, feedback, previous=script if feedback else None)
            if first_write:  # never the same video twice: checked before anything else is spent
                script = repeats.guard(cfg, script, ("short",),
                                       lambda why: write_script(cfg, candidates, why, script), progress)
        if not stage:  # readable from the Create tab while the video is still being made
            (run_dir / "draft.json").write_text(script.model_dump_json(), encoding="utf-8")
        if not stage:
            if not topic:  # keep later attempts on the chosen topic
                candidates = [c for c in candidates if c.title.lower() == script.topic.lower()] or candidates

            verdict = check_script(script, cfg)
            if not verdict.passed:  # a rule break in a few lines: fix those lines first, no rewrite
                progress(f"{tag} Fixing the script: {'; '.join(verdict.issues)}")
                fixed, now = fix_scenes(script, cfg, verdict.issues, web=False)
                if now and check_script(fixed, cfg).passed:
                    if changed is not None:  # a new script is fact-checked in full anyway
                        now = claims_changed(script, fixed, now)
                        recheck_web = recheck_web or new_facts(script, fixed, now)
                        changed |= now
                    script = fixed
                    verdict = check_script(script, cfg)
            if not verdict.passed:
                progress(f"{tag} Script rejected: {'; '.join(verdict.issues)}")
                feedback = "\n".join(verdict.issues)
                save(attempt=attempt + 1, stage=None, feedback=feedback, script=script.model_dump())
                continue

            # Fact-check the words before paying for voice, footage and a render: the whole
            # script once, then only the scenes corrected since (marked >>). Fixes change only
            # the flagged scenes. Fiction and comedy have no factual claims; the review guards them.
            facts = VerifyResult()  # passes unless the fact-check below finds something
            for fix in range(FACT_FIXES + 1 if cfg.video_style == "facts" else 0):
                if changed:
                    progress(f"{tag} Claude is fact-checking the {len(changed)} corrected scene(s)")
                    facts = fact_check_scenes(script, cfg, changed, web=recheck_web, earlier=earlier)
                elif changed is None:
                    progress(f"{tag} Claude is fact-checking the script")
                    facts = fact_check_script(script, cfg)
                else:  # revised, but nothing changed: the old check stands
                    facts = _dec_result(resume.get("facts")) if resume.get("facts") else VerifyResult()
                if facts.passed or fix == FACT_FIXES:
                    break
                progress(f"{tag} Fixing facts: {'; '.join(facts.issues)}")
                fixes = facts.checks["fact_check"].get("fix_instructions", "")
                # The fact-check already searched and says what to write: no second search to fix it.
                fixed, now = fix_scenes(script, cfg, facts.issues, fixes, web=not fixes)
                now = claims_changed(script, fixed, now)
                if not now or not check_script(fixed, cfg).passed:
                    break  # keep the last script that passed the basic checks
                recheck_web, earlier = new_facts(script, fixed, now), list(facts.issues) + ([fixes] if fixes else [])
                script, changed = fixed, now
            if cfg.video_style == "facts" and not facts.passed:
                progress(f"{tag} Still has unconfirmed facts after fixing: {'; '.join(facts.issues)}")
                if attempt < cfg.max_attempts:
                    # A render takes minutes and the review would fail on these same facts:
                    # fix those scenes again next attempt (no new script).
                    feedback = "\n".join(facts.issues)
                    revise = {"issues": list(facts.issues), "fix": facts.checks["fact_check"].get("fix_instructions", ""),
                              "facts": True}
                    save(attempt=attempt + 1, stage="revise", feedback=feedback, script=script.model_dump(),
                         review_issues=revise["issues"], review_fix=revise["fix"], revise_facts=True)
                    continue

            save(attempt=attempt, stage="scripted", script=script.model_dump(), facts=_enc_result(facts),
                 feedback=feedback)

        if stage in ("voiced", "footage", "rendered") and not all(
                Path(x["path"]).exists() for x in resume.get("scenes") or [{"path": ""}]):
            progress(f"{tag} The saved voiceover files are gone; recording it again")
            stage = "scripted"
        if stage in ("footage", "rendered") and not all(
                Path(p).exists() for clips in resume.get("backgrounds") or [[""]] for p in clips):
            progress(f"{tag} The saved footage files are gone; downloading them again")
            stage = "voiced"
        if stage in ("voiced", "footage", "rendered"):
            scenes = _dec_scenes(resume["scenes"])
        else:
            progress(f"{tag} Recording voiceover")
            scenes = synthesize_scenes([s.narration for s in script.scenes], cfg.voice, run_dir / "audio",
                                       cfg.tts_engine, cfg.kokoro_voice, cfg.voice_rate)
            spoken = voice_seconds(scenes)
            for _ in range(2):  # too long: trim the longest scenes and re-record, no new script
                if spoken <= MAX_SECONDS - 1:
                    break
                words = sum(len(s.narration.split()) for s in script.scenes)
                target = int(words * (MAX_SECONDS - 3) / spoken)
                progress(f"{tag} Voiceover runs {spoken:.1f}s: trimming to about {target} words")
                trimmed, now = fix_scenes(script, cfg, [f"The voiceover runs {spoken:.1f}s; the video must stay under "
                                                        f"{MAX_SECONDS}s. Cut the narration from {words} to about {target} "
                                                        "words by shortening the longest scenes; keep every fact and the hook."],
                                          web=False)
                if not now or not check_script(trimmed, cfg).passed:
                    break
                if cfg.video_style == "facts":
                    now = claims_changed(script, trimmed, now)
                    trimmed_facts = fact_check_scenes(trimmed, cfg, now, web=new_facts(script, trimmed, now)) if now else facts
                    if not trimmed_facts.passed:
                        break
                script = trimmed
                scenes = synthesize_scenes([s.narration for s in script.scenes], cfg.voice, run_dir / "audio",
                                           cfg.tts_engine, cfg.kokoro_voice, cfg.voice_rate)
                spoken = voice_seconds(scenes)
            if spoken > MAX_SECONDS - 1 and attempt < cfg.max_attempts:
                # Too long to fit: skip the render and ask for a shorter script. (On the last
                # attempt it's rendered anyway, so there's still a video to look at.)
                words = sum(len(s.narration.split()) for s in script.scenes)
                feedback = (f"The voiceover runs {spoken:.1f}s but the whole video must stay under {MAX_SECONDS}s. "
                            f"Cut the narration from {words} to about {int(words * (MAX_SECONDS - 3) / spoken)} words.")
                progress(f"{tag} Script too long: {feedback}")
                save(attempt=attempt + 1, stage=None, feedback=feedback, script=script.model_dump())
                continue
            save(stage="voiced", scenes=_enc_scenes(scenes))
        if stage in ("footage", "rendered"):
            backgrounds = [[Path(p) for p in clips] for clips in resume["backgrounds"]]
        else:
            progress(f"{tag} Downloading footage")
            backgrounds = fetch_backgrounds([s.visual_queries for s in script.scenes], cfg.pexels_api_key,
                                            cfg.width, cfg.height, run_dir / "backgrounds")
            save(stage="footage", backgrounds=[[str(p) for p in clips] for clips in backgrounds])
        if stage == "rendered" and (run_dir / "reel.mp4").exists():
            rendered = resume["rendered"]
        else:
            progress(f"{tag} Editing the video (takes a few minutes)")
            with _render_slot(cfg):  # waits here if other videos are being edited
                rendered = render_video(script.title, scenes, backgrounds, cfg, run_dir / "reel.mp4",
                                        graphics=[s.graphic for s in script.scenes],
                                        transitions=[s.transition for s in script.scenes],
                                        sounds=[s.sounds for s in script.scenes], music=script.music)
            save(stage="rendered", rendered=rendered)

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

        attempt_result = {"script": script, "rendered": rendered, "verdict": verdict, "attempt": attempt,
                          "sources": footage_sources(backgrounds)}
        if best is None or (verdict.score or 0) >= (best["verdict"].score or 0):
            best = attempt_result
            # Keep the best attempt's files; later attempts render into a scratch copy.
            _snapshot(run_dir)
            save(best=_enc_best(best))

        if verdict.passed:
            progress(f"{tag} Passed verification (score {verdict.score})")
            break
        progress(f"{tag} Failed verification: {'; '.join(verdict.issues)}")
        review = verdict.checks.get("review", {})
        feedback = "\n".join(verdict.issues + ([review["fix_instructions"]] if review.get("fix_instructions") else []))
        # Next attempt fixes the flagged scenes (and their footage queries) instead of a new script.
        revise = {"issues": list(verdict.issues), "fix": review.get("fix_instructions", "")}
        save(attempt=attempt + 1, stage="revise", feedback=feedback, script=script.model_dump(),
             review_issues=revise["issues"], review_fix=revise["fix"], revise_facts=False, facts=_enc_result(facts))

    if best is None:
        shutil.rmtree(run_dir, ignore_errors=True)
        raise RuntimeError(f"No usable script after {cfg.max_attempts} attempts: {feedback}")

    _restore_snapshot(run_dir)
    final_dir = cfg.output_dir / f"{stamp}-{slugify(best['script'].topic)}"
    move(run_dir, final_dir)  # retries through OneDrive/antivirus locks on Windows
    (final_dir / CHECKPOINT).unlink(missing_ok=True)  # finished: nothing left to resume
    script, verdict = best["script"], best["verdict"]
    # The footage links, so "change voice" / "subtitles off" can re-render with the same clips.
    (final_dir / "footage.json").write_text(json.dumps(best.get("sources", [])), encoding="utf-8")
    (final_dir / "script.json").write_text(script.model_dump_json(indent=2), encoding="utf-8")

    source = next((c.source for c in candidates if c.title.lower() == script.topic.lower()), "manual" if topic else "unknown")
    report = {
        "id": final_dir.name,
        "topic": script.topic,
        "topic_source": source,
        "style": cfg.video_style,
        "category": script.category,
        "voice": cfg.voice,
        "captions": cfg.captions,
        "why_chosen": script.why_chosen,
        "subject": script.subject,
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
    report["usage"] = summarize_usage(meter_records())  # every Claude step for this video, post text included
    (final_dir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    with _history_lock:
        save_history(history_path, script.topic)

    notify(report, cfg.telegram_bot_token, cfg.telegram_chat_id)
    progress("Done" if report["verified"] else "Done, but it did not pass every check — review before posting")
    return report


# ---- pause: stop at the next step boundary, resume later from the checkpoint ----

class Paused(Exception):
    """Raised at a step boundary when the user pressed Pause; the checkpoint is already saved."""


_pause = threading.local()


def set_pause_check(fn) -> None:
    _pause.fn = fn


def pause_point() -> None:
    fn = getattr(_pause, "fn", None)
    if fn and fn():
        raise Paused()


def footage_sources(backgrounds: list[list[Path]]) -> list[list[str | None]]:
    """The download link of every clip (saved next to it by visuals.pexels_video)."""
    out = []
    for clips in backgrounds:
        row = []
        for p in clips:
            link = Path(p).with_suffix(".url")
            row.append(link.read_text(encoding="utf-8").strip() if link.exists() else None)
        out.append(row)
    return out


def done_line(report: dict) -> str:
    """Progress line the app uses to link a finished video (and its tokens) to its job."""
    total = (report.get("usage") or {}).get("total", {})
    return "§done " + json.dumps({"id": report["id"], "title": report.get("title", ""), "tokens": total.get("tokens", 0),
                                  "cost_usd": total.get("cost_usd", 0), "verified": report.get("verified")})


# ---- checkpoints: resume a failed video from its last finished step ----

CHECKPOINT = "checkpoint.json"
STAGE_DONE = {"revise": "script (revising after review)", "scripted": "script and fact-check", "voiced": "script and voiceover",
              "footage": "script, voiceover and footage", "rendered": "script, voiceover, footage and edit"}


def _enc_result(r: VerifyResult | None) -> dict | None:
    return asdict(r) if r is not None else None


def _dec_result(d: dict | None) -> VerifyResult:
    return VerifyResult(**d) if d else VerifyResult()


def _enc_scenes(scenes: list[SceneAudio]) -> list[dict]:
    return [{"path": str(s.path), "words": [asdict(w) for w in s.words]} for s in scenes]


def _dec_scenes(data: list[dict]) -> list[SceneAudio]:
    return [SceneAudio(Path(s["path"]), [Word(**w) for w in s["words"]]) for s in data]


def _enc_best(best: dict | None) -> dict | None:
    if best is None:
        return None
    return {"script": best["script"].model_dump(), "rendered": best["rendered"],
            "verdict": _enc_result(best["verdict"]), "attempt": best["attempt"], "sources": best.get("sources", [])}


def _dec_best(d: dict | None) -> dict | None:
    if not d:
        return None
    return {"script": ReelScript.model_validate(d["script"]), "rendered": d["rendered"],
            "verdict": _dec_result(d["verdict"]), "attempt": d["attempt"], "sources": d.get("sources", [])}


def unfinished(cfg: Config) -> list[dict]:
    """Working folders of videos that stopped part-way and can be resumed."""
    out = []
    for folder in sorted(cfg.output_dir.glob("*-working")):
        path = folder / CHECKPOINT
        if not path.exists():
            continue
        state = json.loads(path.read_text(encoding="utf-8"))
        script = state.get("script") or {}
        out.append({"id": folder.name, "topic": script.get("topic") or state.get("topic") or "Trending topic",
                    "title": script.get("title", ""), "style": state.get("style", "facts"),
                    "length": "script" if state.get("manual") else
                              "medium" if state.get("length") == "long" and (state.get("minutes") or 8) < 7
                              else state.get("length", "short"), "attempt": state.get("attempt", 1),
                    "done": STAGE_DONE.get(state.get("stage") or "", "nothing yet"),
                    "updated": path.stat().st_mtime})
    return out


def resume_video(cfg: Config, folder_id: str, progress: Progress = log.info) -> dict:
    """Carry on a stopped video from its checkpoint instead of starting again."""
    run_dir = cfg.output_dir / folder_id
    if run_dir.parent.resolve() != cfg.output_dir.resolve() or not (run_dir / CHECKPOINT).exists():
        raise RuntimeError(f"Nothing to resume in {folder_id}")
    state = rebase(json.loads((run_dir / CHECKPOINT).read_text(encoding="utf-8")), run_dir)
    if state.get("length") == "long":
        from .longform import resume_long
        return resume_long(cfg, run_dir, state, progress)
    cfg = replace(cfg, video_style=state.get("style", cfg.video_style))
    candidates = [Trend(**c) for c in state.get("candidates", [])]
    progress(f"Resuming {folder_id}")
    progress(f"Saving progress in {folder_id}")
    return _make_video(cfg, state.get("topic"), progress, candidates, None, run_dir, state["stamp"],
                       cfg.output_dir / "history.json", resume=state)


def _merge(a: VerifyResult, b: VerifyResult) -> VerifyResult:
    return VerifyResult(passed=a.passed and b.passed, score=b.score, issues=a.issues + b.issues,
                        checks={**a.checks, **b.checks})


def _snapshot(run_dir) -> None:
    best = run_dir / "_best"
    shutil.rmtree(best, ignore_errors=True)
    best.mkdir()
    for name in ("reel.mp4", "thumbnail.jpg", "review_frames.jpg", "props.json"):
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
    for scratch in run_dir.glob("music.*"):  # render input for Remotion; props.json stays (timings for "my voice")
        scratch.unlink(missing_ok=True)


def _video_slot(cfg: Config) -> threading.Semaphore:
    """At most cfg.parallel_videos videos run at once across all jobs, so a second job
    starts as soon as a slot is free instead of waiting for the first job to finish."""
    global _video_slots, _video_slots_size
    size = max(1, cfg.parallel_videos)
    with _slots_lock:
        if _video_slots is None or size != _video_slots_size:
            _video_slots, _video_slots_size = threading.Semaphore(size), size
        return _video_slots


def _render_slot(cfg: Config) -> threading.Semaphore:
    global _render_slots, _render_slots_size
    size = max(1, cfg.parallel_renders)
    if _render_slots is None or size != _render_slots_size:
        _render_slots, _render_slots_size = threading.Semaphore(size), size
    return _render_slots


def run(cfg: Config, count: int = 1, topic: str | None = None, progress: Progress = log.info) -> list[dict]:
    """Make `count` videos. Each waits for one of the cfg.parallel_videos slots shared by all
    jobs. In a batch every progress line is tagged "[V<n>] " so the app shows one row per video."""
    results: dict[int, dict] = {}
    done_titles: list[str] = []

    should_pause = getattr(progress, "should_pause", None)

    def one(i: int) -> None:
        with _video_slot(cfg):  # holds the same semaphore object it acquired, even if resized
            if should_pause and should_pause():  # paused before this video started
                progress((f"[V{i + 1}] " if count > 1 else "") + "§skip {}")
                return
            set_pause_check(should_pause)
            make(i)

    def make(i: int) -> None:
        vp = (lambda m: progress(f"[V{i + 1}] {m}")) if count > 1 else progress
        set_limit_reporter(vp)  # a usage-limit pause shows up in this video's log
        start_meter(lambda r: vp(usage_line(r)))  # count this video's Claude tokens
        vp(f"=== Video {i + 1}/{count} ===")
        # "mix" rotates true story, fiction and comedy through a batch.
        vcfg = replace(cfg, video_style=MIX[i % len(MIX)]) if cfg.video_style == "mix" else cfg
        if vcfg.video_style != "facts" or cfg.video_style == "mix":
            vp(f"Style: {STYLE_NAMES.get(vcfg.video_style, vcfg.video_style)}")
        # Trending batches get a new topic each time (used and in-progress topics are
        # skipped). A batch on one fixed topic needs a different angle per video.
        angle = ""
        if topic and count > 1:
            made = "; ".join(done_titles) or "none yet"
            angle = (f"Video {i + 1} of {count} on this topic; the others in this batch take other angles. "
                     f"Already made: {made}. Pick a clearly different angle, facts and hook, still on this topic.")
        try:
            report = run_once(vcfg, topic, vp, angle)
            vp(done_line(report))
            results[i] = report
            done_titles.append(f"'{report['title']}' ({report['topic']})")
        except Paused:
            vp("Paused: progress saved. Press Resume to carry on from here.")
        except Exception as exc:
            log.exception("Video %d failed", i + 1)
            vp(f"Video {i + 1} failed: {exc}")

    with ThreadPoolExecutor(max_workers=count) as pool:
        for i in range(count):
            pool.submit(one, i)
            time.sleep(0.2)  # keeps videos taking slots roughly in order
    return [results[i] for i in sorted(results)]


def resume_batch(cfg: Config, folders: list[str], progress: Progress = log.info) -> list[dict]:
    """Resume several stopped videos, each in one of the shared video slots."""
    reports: list[dict] = []
    should_pause = getattr(progress, "should_pause", None)

    def one(i: int, folder: str) -> None:
        vp = (lambda m: progress(f"[V{i + 1}] {m}")) if len(folders) > 1 else progress
        with _video_slot(cfg):
            if should_pause and should_pause():
                vp(f"Saving progress in {folder}")  # still resumable next time
                return
            set_pause_check(should_pause)
            set_limit_reporter(vp)
            start_meter(lambda r: vp(usage_line(r)))
            vp(f"=== Video {i + 1}/{len(folders)} ===")
            try:
                reports.append(resume_video(cfg, folder, vp))
                vp(done_line(reports[-1]))
            except Paused:
                vp("Paused: progress saved. Press Resume to carry on from here.")
            except Exception as exc:
                log.exception("Resuming %s failed", folder)
                vp(f"Video {i + 1} failed: {exc}")

    with ThreadPoolExecutor(max_workers=max(1, len(folders))) as pool:
        for i, folder in enumerate(folders):
            pool.submit(one, i, folder)
    return reports
