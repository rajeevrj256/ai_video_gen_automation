"""Long videos: 8-10 minute, 16:9, fully animated (no stock footage), for YouTube.

trend -> Claude writes a chaptered script where every beat has a narration line and an
animated visual -> fact-check and fix (before anything is recorded) -> Indian English
voice, one take per chapter -> Remotion "Long" composition -> checks -> Claude review of
frames from every chapter -> report with YouTube chapter timestamps and post text.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal

from PIL import Image
from pydantic import BaseModel, Field

from .fsutil import move
from .config import Config
from .llm import ask, meter_add_earlier, meter_records, start_meter, summarize_usage, usage_line
from .post_copy import PostCopy, clean_tags, save_post_text
from .script_writer import AI_CLICHES
from .sfx import write_sfx
from .trends import collect_trends, load_history, save_history, trends_as_json, Trend
from .verify import FactCheck, VerifyResult, Review, probe
from .video import FFMPEG, _pick_music, _remotion_cli, _render_remotion, media_seconds
from .voice import synthesize_scenes

log = logging.getLogger(__name__)
Progress = Callable[[str], None]

WIDTH, HEIGHT = 1920, 1080
CARD_SECONDS = 2.4  # chapter title card
CHAPTER_GAP = 0.5  # breath at the end of each chapter
WORDS_PER_SECOND = 2.5  # measured presenter pace at +10%, pauses included
MIN_MINUTES, MAX_MINUTES = 6.5, 11.0
FACT_FIXES = 2
LLM_TIMEOUT = 2400  # a 1,300-word script with research at high effort can take well over 15 minutes
LONG_ATTEMPTS = 2  # a long render takes a long time; one full retry at most
VISUAL_TYPES = ("title", "stat", "timeline", "compare", "steps", "icons", "quote", "keyword", "chart")


# ---------- the script ----------

class LItem(BaseModel):
    label: str = Field(description="timeline: the date or year. compare/chart: the side or the time point. steps: the step's short name.")
    text: str = Field(description="timeline: what happened (max 6 words). steps: one short detail. Empty otherwise.")
    value: float = Field(description="compare/chart: the real number used for the bar or point. 0 otherwise.")
    display: str = Field(description="compare/chart: how the number is written, e.g. '₹2.4 lakh crore', '46,000'. Empty otherwise.")


class LVisual(BaseModel):
    type: Literal["title", "stat", "timeline", "compare", "steps", "icons", "quote", "keyword", "chart"] = Field(
        description="title: a big headline. stat: one striking number. timeline: 2-5 dated moments. compare: "
                    "exactly 2 things side by side. steps: 2-4 steps of how something works. icons: 1-3 icons "
                    "that picture the line. quote: a real, verified quote. keyword: one word or short phrase. "
                    "chart: 3-6 real data points over time.")
    headline: str = Field(description="title/keyword: the text (keyword max 3 words). stat: the number exactly as shown, e.g. '₹1.2 lakh'. quote: the quote. icons/timeline/compare/steps/chart: a short heading (max 7 words).")
    sub: str = Field(description="A short supporting line (max 10 words): what the stat is, who said the quote, the chart's unit. Can be empty.")
    items: list[LItem] = Field(description="timeline: 2-5, compare: exactly 2, steps: 2-4, chart: 3-6. Empty for the other types.")
    icons: list[str] = Field(description="icons: 1-3 Lucide icon names in kebab-case that picture the line, e.g. 'cloud-rain', 'train-front', 'indian-rupee', 'landmark', 'satellite'. Empty for other types.")


class LBeat(BaseModel):
    narration: str = Field(description="What the narrator says over this visual: 1-2 sentences, 12-30 words.")
    visual: LVisual


class LChapter(BaseModel):
    title: str = Field(description="Chapter title for the title card and YouTube chapters, 2-5 words. Chapter 1 (the cold open) is 'Intro'.")
    beats: list[LBeat] = Field(description="6-14 beats. Each beat's visual shows what its narration says.")


class LongScript(BaseModel):
    topic: str = Field(description="The trending topic you chose, exactly as written in the candidate list (fiction: the theme you used).")
    why_chosen: str = Field(description="One sentence: why this will hold viewers for 8 minutes, and the one story you will tell.")
    facts_checked: str = Field(description="The key facts the script relies on and where they come from.")
    category: Literal["Sports", "Money", "Science & Space", "Tech", "History", "Nature & Animals", "Weather",
                      "Entertainment", "India", "Life & People", "Stories", "Comedy"] = Field(
        description="The library shelf this video belongs on. Fiction is 'Stories', jokes are 'Comedy'; otherwise the subject area.")
    subject: str = Field(description="The one subject the whole video explores in depth.")
    hook_question: str = Field(description="The one big question the cold open plants; the video answers it only in the last chapter.")
    answer: str = Field(description="The answer or twist the last chapter delivers, in one sentence.")
    youtube_title: str = Field(description="YouTube title, max 70 characters: curiosity plus the main search keyword, no clickbait the video doesn't deliver.")
    chapters: list[LChapter] = Field(description="6-8 chapters in order. The first is the cold open ('Intro').")


def _system(style: str, language: str) -> str:
    kind = ("a true story told like a documentary, every fact checked" if style != "story"
            else "an original fiction story, clearly presented as a story")
    return f"""You write 8 to 10 minute YouTube videos that people watch to the end: {kind}. \
The video is fully animated motion graphics (no footage), so every beat pairs one narration line with \
one animated visual that shows exactly what that line says.

Language and voice: write in {language}. For Indian English that means natural, educated Indian English \
as a sharp Indian presenter speaks it: clear and warm, not American slang, not Hinglish. Use lakh and \
crore with rupees for Indian money, metric units, and Indian comparisons (a Mumbai local train, a \
cricket ground, the monsoon) where they genuinely make a number easier to picture. Read by \
text-to-speech: no abbreviations, symbols or emojis in narration; write numbers as they are spoken.

Retention structure (the most important rules):
- Chapter 1, the cold open (45-75 seconds): the first sentence (12 words or fewer) plants one big \
question without the answer, e.g. "Do you know how [place] was founded?". Then raise the stakes and \
promise what the viewer will understand by the end. No greeting, no "in this video".
- 5 to 7 more chapters of 60-100 seconds. Each opens with a mini-hook (a new question or surprise) \
and ends on an open loop that pulls into the next ("But that created a bigger problem.").
- Around the middle, a twist that changes how the story looks.
- The big question is answered only in the last chapter, which ties back to the first line and ends \
with one short, natural line asking viewers to subscribe for the next story.
- One subject, in depth: the whole video stays on the subject you name. Every chapter goes a level \
deeper (how, why, the telling detail, what it caused, what nobody expects). Never a list of \
separate examples.
- Scenes are linked by "but" and "so", never "and also". Vary sentence length. No filler.
- Never use these phrases: {", ".join(AI_CLICHES)}.

Visuals:
- Every visual must match its line. Numbers on screen must be real, sourced and identical to what \
the narration says; no made-up, rounded-up or "illustrative" data. A chart needs real figures; \
otherwise use a stat or a keyword. A quote must be a real, verified quote with its speaker; if you \
can't verify one, don't use a quote.
- Vary the types; never the same type twice in a row. Use 'title' sparingly, mostly for turns in \
the story. Prefer icons, timelines, steps, compares and stats that make the idea visual.

Accuracy: only state facts you are confident about or have looked up with web search. Never invent \
details, dialogue or figures in a true story. Timeless wording: never "today", "this week" or "five \
days ago"; use dates. No politics or politicians, tragedies, violence, or rumours about real people. \
Fiction uses invented characters only and never presents itself as real events."""


def write_long_script(cfg: Config, candidates: list[Trend], minutes: float, feedback: str = "",
                      previous: LongScript | None = None) -> LongScript:
    words = int(minutes * 60 * WORDS_PER_SECOND)
    task = ("Pick the candidate with the richest story behind it and write the video." if cfg.video_style != "story"
            else "Write an original fiction story; the topics are only inspiration.")
    prompt = (f"Candidate topics trending now (region {cfg.geo}):\n{trends_as_json(candidates)}\n\n{task}\n"
              f"- Length: about {words} words of narration in total ({minutes:g} minutes), no less than "
              f"{int(words * 0.9)} and no more than {int(words * 1.1)}.\n"
              f"- 6 to 8 chapters, 6 to 14 beats each.")
    if len(candidates) == 1 and candidates[0].source == "manual":
        prompt += f"\n- The user asked for this topic: {candidates[0].title}. Use it."
    if feedback:
        prompt += f"\n\nThe previous draft was rejected. Fix every point:\n{feedback}"
        if previous is not None:
            prompt += (f"\n\nThe rejected draft:\n{previous.model_dump_json()}\n"
                       "Keep what works; rewrite what was flagged. Don't reuse a flagged claim in softer words.")
    script = ask(cfg.ai_backend, cfg.claude_model, _system(cfg.video_style, cfg.long_language), prompt,
                 LongScript, allow_web=True, effort=cfg.claude_effort, timeout=LLM_TIMEOUT)
    log.info("Long video topic: %s (%s)", script.topic, script.why_chosen)
    return script


class BeatFix(BaseModel):
    chapter: int = Field(description="Chapter number, 1-based, as in the numbered script (3.4 = chapter 3).")
    beat: int = Field(description="Beat number within the chapter, 1-based (3.4 = beat 4).")
    narration: str = Field(description="The corrected line, same length and flow as before.")
    visual: LVisual = Field(description="The corrected visual; unchanged if only the words were wrong.")


class ScriptFixes(BaseModel):
    fixes: list[BeatFix] = Field(description="One entry per line that must change. Only the flagged lines.")


FIX_SYSTEM = """You correct flagged lines in a finished documentary script. Change only what the fact-check \
flagged, keep each line's length, tone and place in the story, and keep every number on screen identical to \
its narration. If a claim can't be stated accurately, replace it with a nearby fact you are sure of, or make \
the line less specific. Use web search when you need to confirm the corrected fact."""


def fix_long_script(script: LongScript, cfg: Config, issues: list[str], instructions: str) -> LongScript:
    """Rewrite only the flagged beats. Regenerating the whole script to fix one figure
    brought new small errors each time; a targeted fix leaves everything else untouched."""
    numbered = "\n".join(f"{ci}.{bi} {b.narration}  {_visual_text(b.visual)}"
                         for ci, c in enumerate(script.chapters, 1) for bi, b in enumerate(c.beats, 1))
    prompt = (f"The script, numbered chapter.beat:\n{numbered}\n\nThe fact-check flagged:\n" + "\n".join(issues)
              + (f"\n\nSuggested fixes: {instructions}" if instructions else "")
              + "\n\nReturn the corrected lines only.")
    result = ask(cfg.ai_backend, cfg.claude_model, FIX_SYSTEM, prompt, ScriptFixes, allow_web=True,
                 effort=cfg.claude_effort, timeout=LLM_TIMEOUT)
    fixed = script.model_copy(deep=True)
    for f in result.fixes:
        if 1 <= f.chapter <= len(fixed.chapters) and 1 <= f.beat <= len(fixed.chapters[f.chapter - 1].beats):
            fixed.chapters[f.chapter - 1].beats[f.beat - 1] = LBeat(narration=f.narration, visual=f.visual)
    log.info("Fixed %d line(s): %s", len(result.fixes), ", ".join(f"{f.chapter}.{f.beat}" for f in result.fixes))
    return fixed


def narration_words(script: LongScript) -> int:
    return sum(len(b.narration.split()) for c in script.chapters for b in c.beats)


def check_long_script(script: LongScript, minutes: float) -> VerifyResult:
    result = VerifyResult()
    words = narration_words(script)
    target = minutes * 60 * WORDS_PER_SECOND
    result.checks["word_count"] = words
    if not target * 0.85 <= words <= target * 1.15:
        result.fail(f"Narration is {words} words; write about {int(target)} for {minutes:g} minutes.")
    if not 5 <= len(script.chapters) <= 9:
        result.fail(f"{len(script.chapters)} chapters; use 6 to 8.")
    lowered = " ".join(b.narration for c in script.chapters for b in c.beats).lower()
    found = [p for p in AI_CLICHES if re.search(rf"\b{re.escape(p)}\b", lowered)]
    if found:
        result.fail(f"Uses AI-sounding phrases: {', '.join(found)}.")
    first = script.chapters[0].beats[0].narration if script.chapters and script.chapters[0].beats else ""
    hook = re.split(r"(?<=[.?!])\s", first.strip(), maxsplit=1)[0]
    result.checks["hook"] = hook
    if len(hook.split()) > 14:
        result.fail(f"The opening sentence is {len(hook.split())} words ('{hook}'); make the hook 12 words or fewer.")
    for ci, chapter in enumerate(script.chapters, 1):
        for bi, beat in enumerate(chapter.beats, 1):
            v = beat.visual
            need = {"timeline": (2, 5), "compare": (2, 2), "steps": (2, 4), "chart": (3, 6)}.get(v.type)
            if need and not need[0] <= len(v.items) <= need[1]:
                result.fail(f"Chapter {ci} beat {bi}: a {v.type} needs {need[0]}-{need[1]} items, it has {len(v.items)}.")
    return result


FACT_SYSTEM = """You fact-check scripts for long YouTube documentaries before they are produced. Check every \
factual claim in the narration and in the on-screen visuals (numbers, dates, quotes and who said them). \
Use web search to confirm anything you are not certain of. Flag wrong or outdated facts, numbers that don't \
match sources, quotes you can't verify word for word, invented details or dialogue presented as fact, \
exaggerations, myths stated as fact, and lines that contradict each other. Don't comment on style. Be \
strict: a viewer who knows the subject should find nothing to correct in the comments."""


def _visual_text(v: LVisual) -> str:
    items = "; ".join(f"{i.label} {i.text} {i.display}".strip() for i in v.items)
    return f"[{v.type}: {v.headline}" + (f" | {v.sub}" if v.sub else "") + (f" | {items}" if items else "") + "]"


def fact_check_long(script: LongScript, cfg: Config) -> VerifyResult:
    lines = []
    for ci, c in enumerate(script.chapters, 1):
        lines.append(f"\nChapter {ci}: {c.title}")
        for bi, b in enumerate(c.beats, 1):
            lines.append(f"{ci}.{bi} {b.narration}  {_visual_text(b.visual)}")
    prompt = (f"Topic: {script.topic}\nThe writer's sources: {script.facts_checked}\n" + "\n".join(lines)
              + "\n\nFact-check this script. Refer to lines by their numbers (e.g. 3.4).")
    check = ask(cfg.ai_backend, cfg.claude_model, FACT_SYSTEM, prompt, FactCheck, allow_web=True, effort=cfg.claude_effort,
                timeout=LLM_TIMEOUT)
    result = VerifyResult()
    result.checks["fact_check"] = check.model_dump()
    for issue in check.blocking_issues:
        result.fail("Fact-check: " + issue)
    return result


# ---------- voice, timeline, props ----------

def _group_words(words: list[dict], max_words: int = 9, pause: float = 0.22) -> list[list[dict]]:
    """Subtitle lines for one beat: up to max_words, breaking where the voice pauses (the
    word timings carry no punctuation, but sentence and comma breaks are audible gaps)."""
    groups, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        gap = words[i + 1]["start"] - w["end"] if i + 1 < len(words) else 0
        left = len(words) - i - 1
        if (len(cur) >= max_words and left > 2) or (gap > pause and len(cur) >= 3):
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    return groups


def build_long(script: LongScript, cfg: Config, work: Path, progress: Progress) -> dict:
    """Record the voice (one take per chapter) and lay out every beat on the timeline."""
    beats, chapters, lines = [], [], []
    t = 0.0
    for ci, chapter in enumerate(script.chapters):
        card = CARD_SECONDS if ci > 0 else 0.0
        chapters.append({"index": ci, "title": chapter.title, "start": round(t, 3), "card": card})
        t += card
        progress(f"Recording voiceover: chapter {ci + 1} of {len(script.chapters)}")
        audio = synthesize_scenes([b.narration for b in chapter.beats], cfg.long_voice, work / "audio" / f"ch{ci:02d}",
                                  cfg.tts_engine, cfg.kokoro_voice, cfg.voice_rate)
        for beat, sa in zip(chapter.beats, audio):
            duration = media_seconds(sa.path)
            v = beat.visual.model_dump()
            v["icons"] = [i.strip().lower().replace(" ", "-") for i in v["icons"]]
            beats.append({"start": round(t, 3), "duration": round(duration, 3), "chapter": ci,
                          "audio": sa.path.relative_to(work).as_posix(), "visual": v})
            lines += _group_words([{"text": w.text, "start": round(t + w.start, 3), "end": round(t + w.end, 3)}
                                   for w in sa.words])
            t += duration
        t += CHAPTER_GAP
    captions = []
    for g in lines:
        captions.append({"start": g[0]["start"], "end": round(g[-1]["end"] + 0.25, 3), "words": g})
    for a, b in zip(captions, captions[1:]):  # never two subtitle lines at once
        a["end"] = min(a["end"], b["start"])
    music = _pick_music(cfg, work)
    sfx = write_sfx(work / "sfx")
    return {
        "title": script.youtube_title,
        "fps": cfg.fps,
        "duration": round(t, 3),
        "chapters": chapters,
        "beats": beats,
        "captions": captions,
        "music": music.relative_to(work).as_posix() if music else None,
        "sfx": {k: p.relative_to(work).as_posix() for k, p in sfx.items()},
    }


def youtube_chapters(props: dict) -> str:
    def stamp(s: float) -> str:
        s = int(s)
        return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"
    return "\n".join(f"{stamp(c['start'])} {c['title']}" for c in props["chapters"])


# ---------- checks and review ----------

def check_long_video(video: Path) -> VerifyResult:
    result = VerifyResult()
    if not video.exists() or video.stat().st_size < 500_000:
        result.fail("Video file missing or empty.")
        return result
    info = probe(video)
    result.checks["probe"] = info
    if (info.get("width"), info.get("height")) != (WIDTH, HEIGHT):
        result.fail(f"Resolution is {info.get('width')}x{info.get('height')}, expected {WIDTH}x{HEIGHT}.")
    minutes = info.get("duration", 0) / 60
    if not MIN_MINUTES <= minutes <= MAX_MINUTES:
        result.fail(f"Video is {minutes:.1f} minutes; it should be 8 to 10.")
    if not info.get("has_audio"):
        result.fail("No audio track.")
    result.checks["size_mb"] = round(video.stat().st_size / 1e6, 1)
    return result


def contact_sheet_long(video: Path, out: Path, props: dict) -> Path:
    """Two frames from every chapter (a third and two thirds in), 4 per row."""
    times = []
    for i, c in enumerate(props["chapters"]):
        end = props["chapters"][i + 1]["start"] if i + 1 < len(props["chapters"]) else props["duration"]
        body = c["start"] + c["card"]
        times += [body + (end - body) * 0.33, body + (end - body) * 0.7]
    tiles = []
    for k, t in enumerate(times):
        tile = out.with_name(f"_frame{k}.jpg")
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
                        "-vf", "scale=480:270", str(tile)], check=False)
        if tile.exists():
            tiles.append(Image.open(tile).convert("RGB"))
            tile.unlink()
    rows = (len(tiles) + 3) // 4
    sheet = Image.new("RGB", (480 * 4, 270 * max(rows, 1)), "black")
    for k, tile in enumerate(tiles):
        sheet.paste(tile, ((k % 4) * 480, (k // 4) * 270))
    sheet.save(out, quality=85)
    return out


LONG_REVIEW_SYSTEM = """You are a strict YouTube editor reviewing an 8-10 minute fully animated video before \
it is posted. You judge whether viewers would stay to the end: a cold open that plants one big question, \
chapters that each open with a mini-hook and end on an open loop, one subject explored in depth rather than \
a list, a twist near the middle and a payoff that answers the opening question. You also check that each \
animated visual matches its line and that nothing is inaccurate, exaggerated or unverifiable. Be honest and \
specific; don't pass mediocre work."""


def review_long(video: Path, script: LongScript, props: dict, cfg: Config) -> tuple[Review, VerifyResult]:
    sheet = contact_sheet_long(video, video.with_name("review_frames.jpg"), props)
    lines = []
    for ci, c in enumerate(script.chapters, 1):
        lines.append(f"\nChapter {ci}: {c.title}")
        lines += [f"{ci}.{bi} {b.narration}  {_visual_text(b.visual)}" for bi, b in enumerate(c.beats, 1)]
    prompt = (f"The image shows two frames from every chapter, left to right, top to bottom.\n\n"
              f"Title: {script.youtube_title}\nThe big question: {script.hook_question}\n"
              f"Style: {'fiction story' if cfg.video_style == 'story' else 'true story, fact-checked'}\n"
              + "\n".join(lines) + "\n\nScore it and list what to fix. For 'visuals_match', judge the animated "
              "visuals against their lines. For 'story', judge retention across the whole video.")
    review = ask(cfg.ai_backend, cfg.claude_model, LONG_REVIEW_SYSTEM, prompt, Review, images=[sheet],
                 effort=cfg.claude_effort, timeout=LLM_TIMEOUT)
    result = VerifyResult()
    scores = [review.human_feel, review.hook, review.visuals_match, review.accuracy, review.story]
    result.score = round(sum(scores) / len(scores), 1)
    result.checks["review"] = review.model_dump()
    if review.blocking_issues:
        for issue in review.blocking_issues:
            result.fail("Reviewer: " + issue)
    elif min(scores) < 6 or result.score < 7 or review.hook < 7:
        result.fail("Reviewer: " + "; ".join(review.issues or ["scores too low"]))
    return review, result


# ---------- post text ----------

POST_SYSTEM = """You are a YouTube channel manager. Write the text that goes with a finished long video so it \
gets found and clicked: a search-friendly title, a description whose first two lines hook the reader and \
contain the main keywords, and tags and hashtags that are really used for this topic now (check with web \
search). Never promise what the video doesn't deliver; keep facts identical to the script."""


def write_long_post(script: LongScript, props: dict, cfg: Config) -> dict:
    summary = " ".join(b.narration for c in script.chapters for b in c.beats)[:6000]
    prompt = (f"Topic: {script.topic}\nDraft title: {script.youtube_title}\nThe big question: {script.hook_question}\n"
              f"Narration (start): {summary}\n\nWrite the YouTube (and Instagram) post text for this "
              f"{'fiction story' if cfg.video_style == 'story' else 'documentary'} video.")
    post = ask(cfg.ai_backend, cfg.claude_model, POST_SYSTEM, prompt, PostCopy, allow_web=True, effort=cfg.claude_effort)
    description = post.youtube_description.strip() + "\n\nChapters:\n" + youtube_chapters(props)
    return {
        "caption": post.instagram_caption,
        "hashtags": clean_tags(post.instagram_hashtags),
        "youtube_title": post.youtube_title,
        "youtube_description": description,
        "youtube_hashtags": [t for t in clean_tags(post.youtube_hashtags) if t.lower() != "shorts"],
        "youtube_tags": [t.strip().lstrip("#") for t in post.youtube_tags if t.strip()],
        "hashtag_notes": post.hashtag_notes,
    }


# ---------- the run ----------

def run_long(cfg: Config, topic: str | None = None, progress: Progress = log.info) -> dict:
    """Make one long video. Returns its report (the same shape the app reads for Shorts)."""
    from .pipeline import _claimed, _history_lock, _render_slot, _topic_lock, slugify

    minutes = cfg.long_minutes
    history_path = cfg.output_dir / "history.json"
    progress("Finding trending topics")
    if topic:
        candidates = [Trend(title=topic, source="manual")]
    else:
        with _topic_lock:
            with _history_lock:
                used = load_history(history_path)
            candidates = collect_trends(cfg.geo, used + sorted(_claimed))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    work = cfg.output_dir / f"{stamp}-{uuid.uuid4().hex[:4]}-long-working"
    work.mkdir(parents=True, exist_ok=True)
    progress(f"Saving progress in {work.name}")  # lets a failed job resume from here
    return _long_loop(cfg, work, candidates, topic, stamp, progress)


def resume_long(cfg: Config, work: Path, state: dict, progress: Progress) -> dict:
    from dataclasses import replace

    cfg = replace(cfg, video_style=state.get("style", cfg.video_style))
    progress(f"Resuming {work.name}")
    progress(f"Saving progress in {work.name}")
    return _long_loop(cfg, work, [Trend(**c) for c in state.get("candidates", [])], state.get("topic"),
                      state["stamp"], progress, resume=state)


def _enc_long_best(best: dict | None) -> dict | None:
    return None if best is None else {"script": best["script"].model_dump(), "verdict": asdict(best["verdict"]),
                                      "props": best["props"], "attempt": best["attempt"], "file": str(best["file"])}


def _dec_long_best(d: dict | None) -> dict | None:
    return None if not d else {"script": LongScript.model_validate(d["script"]), "verdict": VerifyResult(**d["verdict"]),
                               "props": d["props"], "attempt": d["attempt"], "file": Path(d["file"])}


def _long_loop(cfg: Config, work: Path, candidates: list, topic: str | None, stamp: str, progress: Progress,
               resume: dict | None = None) -> dict:
    """The attempt loop for one long video. Saves checkpoint.json after the script, the
    voice and every render, so a stopped video can carry on instead of starting again."""
    from .pipeline import CHECKPOINT, STAGE_DONE, _history_lock, _render_slot, pause_point, slugify

    minutes = cfg.long_minutes
    history_path = cfg.output_dir / "history.json"
    resume = resume or {}
    feedback = resume.get("feedback", "")
    script = LongScript.model_validate(resume["script"]) if resume.get("script") else None
    best = _dec_long_best(resume.get("best"))
    start = resume.get("attempt", 1)
    meter_add_earlier(resume.get("usage"))
    state = {"length": "long", "topic": topic, "stamp": stamp, "style": cfg.video_style,
             "candidates": [asdict(c) for c in candidates], "best": resume.get("best")}

    def save(**changes) -> None:
        state.update(changes, usage=meter_records())
        (work / CHECKPOINT).write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        pause_point()

    try:
        for attempt in range(start, LONG_ATTEMPTS + 1):
            tag = f"[attempt {attempt}/{LONG_ATTEMPTS}]"
            stage = resume.get("stage") if attempt == start else None
            if stage:
                progress(f"{tag} Resuming: {STAGE_DONE.get(stage, stage)} already done")
            else:
                progress(f"{tag} Claude is picking the topic and writing the script (long video, a few minutes)")
                script = write_long_script(cfg, candidates, minutes, feedback, script if feedback else None)
            for fix in range(0 if stage else FACT_FIXES + 1):
                basic = check_long_script(script, minutes)
                if basic.passed and cfg.video_style != "story":
                    progress(f"{tag} Claude is fact-checking the script")
                facts = fact_check_long(script, cfg) if basic.passed and cfg.video_style != "story" else VerifyResult()
                if basic.passed and facts.passed:
                    break
                problems = basic.issues + facts.issues
                if fix == FACT_FIXES:
                    progress(f"{tag} Still has problems after rewriting: {'; '.join(problems)}")
                    break
                progress(f"{tag} Fixing the script: {'; '.join(problems)}")
                fixes = facts.checks.get("fact_check", {}).get("fix_instructions", "")
                if basic.passed:  # only facts are wrong: correct just those lines
                    script = fix_long_script(script, cfg, facts.issues, fixes)
                else:  # structure or length is off: that needs a real rewrite
                    script = write_long_script(cfg, candidates, minutes, "\n".join(problems + ([fixes] if fixes else [])), script)
            if not stage and not (basic.passed and facts.passed) and attempt < LONG_ATTEMPTS:
                feedback = "\n".join(problems)
                save(attempt=attempt + 1, stage=None, feedback=feedback, script=script.model_dump())
                continue
            if not stage:
                save(attempt=attempt, stage="scripted", script=script.model_dump(), feedback=feedback)

            if stage in ("voiced", "rendered"):
                props = resume["props"]
            else:
                for old in ("audio", "sfx"):
                    shutil.rmtree(work / old, ignore_errors=True)
                props = build_long(script, cfg, work, progress)
                save(stage="voiced", props=props)
            progress(f"{tag} Editing the video ({props['duration'] / 60:.1f} min of animation; this takes a while)")
            cli = _remotion_cli()
            if cli is None:
                raise RuntimeError("Node.js or the Remotion packages are not installed (run start.bat / start.sh)")
            out = work / "reel.mp4"
            if stage == "rendered" and out.exists():
                pass  # the edit finished before it stopped
            else:
                with _render_slot(cfg):
                    _render_remotion(cli, props, out, composition="Long", crf=20, timeout=4 * 3600)
                save(stage="rendered")
            subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", "3", "-i", str(out), "-frames:v", "1",
                            "-q:v", "3", str(work / "thumbnail.jpg")], check=False)

            progress(f"{tag} Verifying video quality")
            verdict = check_long_video(out)
            if verdict.passed:
                progress(f"{tag} Claude is reviewing the finished video")
                _, review = review_long(out, script, props, cfg)
                verdict.checks.update(review.checks)
                verdict.score = review.score
                if not review.passed:
                    verdict.passed = False
                    verdict.issues += review.issues
            # Keep each rendered attempt; the best one (passed, then highest score) becomes reel.mp4.
            kept = work / f"attempt{attempt}.mp4"
            move(out, kept)
            shutil.copy(work / "thumbnail.jpg", work / f"attempt{attempt}.jpg")
            this = {"script": script, "verdict": verdict, "props": props, "attempt": attempt, "file": kept}
            if best is None or (verdict.passed, verdict.score or 0) > (best["verdict"].passed, best["verdict"].score or 0):
                best = this
            save(best=_enc_long_best(best))
            if verdict.passed:
                progress(f"{tag} Passed verification (score {verdict.score})")
                break
            progress(f"{tag} Failed verification: {'; '.join(verdict.issues)}")
            review_fix = verdict.checks.get("review", {}).get("fix_instructions", "")
            feedback = "\n".join(verdict.issues + ([review_fix] if review_fix else []))
            save(attempt=attempt + 1, stage=None, feedback=feedback, script=script.model_dump())

        if best is None:
            raise RuntimeError(f"No usable long script after {LONG_ATTEMPTS} attempts: {feedback}")
        script, verdict, props = best["script"], best["verdict"], best["props"]
        move(best["file"], work / "reel.mp4")
        (work / f"attempt{best['attempt']}.jpg").replace(work / "thumbnail.jpg")
        for scratch in [*work.glob("attempt*.mp4"), *work.glob("attempt*.jpg"), work / "music.mp3"]:
            scratch.unlink(missing_ok=True)
        (work / "props.json").write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
        final_dir = cfg.output_dir / f"{stamp}-{slugify(script.topic)}-long"
        move(work, final_dir)
        (final_dir / CHECKPOINT).unlink(missing_ok=True)
        (final_dir / "script.json").write_text(script.model_dump_json(indent=2), encoding="utf-8")
        report = {
            "id": final_dir.name,
            "format": "long",
            "topic": script.topic,
            "topic_source": candidates[0].source if topic else next(
                (c.source for c in candidates if c.title.lower() == script.topic.lower()), "unknown"),
            "style": cfg.video_style,
            "category": script.category,
            "why_chosen": script.why_chosen,
            "title": script.youtube_title,
            "subject": script.subject,
            "hook_question": script.hook_question,
            "narration": " ".join(b.narration for c in script.chapters for b in c.beats),
            "facts_checked": script.facts_checked,
            "chapters": [{"title": c["title"], "start": c["start"]} for c in props["chapters"]],
            "created_at": stamp,
            "verified": verdict.passed,
            "score": verdict.score,
            "issues": verdict.issues,
            "checks": verdict.checks,
            "attempts": best["attempt"],
            "video": str(final_dir / "reel.mp4"),
            "thumbnail": str(final_dir / "thumbnail.jpg"),
            "duration_seconds": round(props["duration"], 1),
            "editor": "remotion (Long)",
        }
        progress("Claude is writing the title, description, chapters and tags")
        try:
            report.update(write_long_post(script, props, cfg))
        except Exception as exc:
            log.warning("Post text step failed: %s", exc)
            report.update({"caption": script.youtube_title, "hashtags": [], "youtube_title": script.youtube_title,
                           "youtube_description": "Chapters:\n" + youtube_chapters(props), "youtube_hashtags": [],
                           "youtube_tags": [], "post_text_error": str(exc)[:300]})
        save_post_text(report, final_dir)
        report["usage"] = summarize_usage(meter_records())
        (final_dir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        with _history_lock:
            save_history(history_path, script.topic)
        progress("Done" if report["verified"] else "Done, but it did not pass every check — review before posting")
        return report
    except Exception:
        # Keep the folder when it has a checkpoint: the video can be resumed from there.
        if work.exists() and not (work / CHECKPOINT).exists():
            shutil.rmtree(work, ignore_errors=True)
        raise


def run_long_batch(cfg: Config, count: int, topic: str | None, progress: Progress) -> list[dict]:
    """Several long videos, one after another (each takes the shared video slot). Jokes
    don't suit 8 minutes, so 'comedy' becomes a true story; 'mix' alternates true and fiction."""
    from dataclasses import replace

    from .llm import set_limit_reporter
    from .pipeline import Paused, _video_slot, done_line, set_pause_check

    reports = []
    should_pause = getattr(progress, "should_pause", None)
    for i in range(count):
        style = {"comedy": "facts", "mix": ("facts", "story")[i % 2]}.get(cfg.video_style, cfg.video_style)
        vp = (lambda m, n=i + 1: progress(f"[V{n}] {m}")) if count > 1 else progress
        with _video_slot(cfg):
            if should_pause and should_pause():
                progress((f"[V{i + 1}] " if count > 1 else "") + "§skip {}")
                continue
            set_pause_check(should_pause)
            set_limit_reporter(vp)
            start_meter(lambda r, vp=vp: vp(usage_line(r)))
            vp(f"=== Video {i + 1}/{count} ===")
            try:
                reports.append(run_long(replace(cfg, video_style=style), topic, vp))
                vp(done_line(reports[-1]))
            except Paused:
                vp("Paused: progress saved. Press Resume to carry on from here.")
            except Exception as exc:
                log.exception("Long video %d failed", i + 1)
                vp(f"Video {i + 1} failed: {exc}")
    return reports
