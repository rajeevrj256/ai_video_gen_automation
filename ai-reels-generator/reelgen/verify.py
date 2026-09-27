"""Automatic quality check before a video is delivered.

Three layers:
1. Script checks  – AI-sounding phrases, length, structure (instant, free).
2. Technical checks – resolution, duration, audio level, black frames, captions
   (ffmpeg, a few seconds).
3. Claude review – Claude looks at frames from the finished video plus the
   script and judges whether it feels human-made, hooks fast, and is accurate.
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import imageio_ffmpeg
from PIL import Image
from pydantic import BaseModel, Field

from .config import MAX_SECONDS, Config
from .llm import ask
from .script_writer import AI_CLICHES, ReelScript, word_range
from .voice import SceneAudio

log = logging.getLogger(__name__)
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


@dataclass
class VerifyResult:
    passed: bool = True
    score: float | None = None
    issues: list[str] = field(default_factory=list)
    checks: dict = field(default_factory=dict)

    def fail(self, issue: str) -> None:
        self.passed = False
        self.issues.append(issue)


# ---------- 1. script ----------

def check_script(script: ReelScript, cfg: Config) -> VerifyResult:
    result = VerifyResult()
    narration = " ".join(s.narration for s in script.scenes)
    lowered = narration.lower() + " " + script.title.lower() + " " + script.caption.lower()

    found = [p for p in AI_CLICHES if re.search(rf"\b{re.escape(p)}\b", lowered)]
    result.checks["ai_phrases"] = found
    if found:
        result.fail(f"Uses AI-sounding phrases: {', '.join(found)}. Rephrase them the way a person would say it.")

    words = len(narration.split())
    result.checks["word_count"] = words
    low, high = word_range(cfg.target_seconds)
    if not low * 0.85 <= words <= high:  # over the top means over 30 seconds
        result.fail(f"Narration is {words} words; use {low}-{high} for a {cfg.target_seconds}s video.")

    if not 4 <= len(script.scenes) <= 8:
        result.fail(f"{len(script.scenes)} scenes; use 5-7.")
    if script.scenes:
        hook = re.split(r"(?<=[.?!])\s", script.scenes[0].narration.strip(), maxsplit=1)[0]
        result.checks["hook"] = hook
        if len(hook.split()) > 14:
            result.fail(f"The hook sentence is {len(hook.split())} words ('{hook}'). Make it 12 words or "
                        "fewer, so it lands in the first 2 seconds.")
    if re.search(r"https?://|www\.|[#@*_]", narration):
        result.fail("Narration contains URLs or symbols that text-to-speech will read out loud.")

    graphics = [s.graphic for s in script.scenes if s.graphic.type != "none"]
    result.checks["graphics"] = [g.type for g in graphics]
    if not 2 <= len(graphics) <= 5:
        result.fail(f"{len(graphics)} on-screen graphics; design 3 or 4.")
    for i, scene in enumerate(script.scenes, 1):
        g = scene.graphic
        if g.type == "chart" and not 3 <= len(g.points) <= 6:
            result.fail(f"Scene {i}: a chart needs 3-6 real data points, it has {len(g.points)}. "
                        "Use a stat if there is only one number.")
        if g.type == "compare" and len(g.points) != 2:
            result.fail(f"Scene {i}: a compare needs exactly 2 points, it has {len(g.points)}.")
        if g.type == "stat" and not re.search(r"\d", g.headline):
            result.fail(f"Scene {i}: a stat headline must be a number, got '{g.headline}'. Use a keyword instead.")
    return result


class FactCheck(BaseModel):
    blocking_issues: list[str] = Field(description="Every claim in the voiceover, hook or graphics that is wrong, outdated, exaggerated, a popular myth stated as fact, contradicted by another line, or a precise figure you could not confirm. Quote the line. Empty if none.")
    fix_instructions: str = Field(description="Concrete rewrite instructions for exactly the flagged lines: what to say instead, or to drop the claim. Empty if none.")


FACT_CHECK_SYSTEM = """You fact-check short-form video scripts before they are produced. Check every \
factual claim in the voiceover, the on-screen hook and the graphics. Use web search to confirm \
anything you are not certain of. Flag wrong or outdated facts, numbers that don't match sources, \
lines that contradict each other, exaggerations and popular myths stated as fact ("we only use \
10% of our brain"), and precise figures you cannot confirm. Don't comment on style. Be strict: a \
viewer who knows the subject should find nothing to correct in the comments."""


def fact_check_script(script: ReelScript, cfg: Config) -> VerifyResult:
    """Catch factual problems before any voice, footage or rendering is spent on them."""
    lines = [f"Hook on screen: {script.title}"]
    for i, scene in enumerate(script.scenes, 1):
        lines.append(f"Scene {i} voiceover: {scene.narration}")
        g = scene.graphic
        if g.type != "none":
            pts = ", ".join(f"{p.label}={p.display}" for p in g.points)
            lines.append(f"Scene {i} graphic ({g.type}): {g.headline} | {g.label}" + (f" | {pts}" if pts else ""))
    prompt = (f"Topic: {script.topic}\nThe writer's sources: {script.facts_checked}\n\n" + "\n".join(lines)
              + "\n\nFact-check this script.")
    check = ask(cfg.ai_backend, cfg.claude_model, FACT_CHECK_SYSTEM, prompt, FactCheck, allow_web=True, effort=cfg.claude_effort)
    result = VerifyResult()
    result.checks["fact_check"] = check.model_dump()
    for issue in check.blocking_issues:
        result.fail("Fact-check: " + issue)
    return result


# ---------- 2. technical ----------

def _ffmpeg(args: list[str]) -> str:
    proc = subprocess.run([FFMPEG, "-hide_banner", *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=300)
    return proc.stderr or ""


def probe(video: Path) -> dict:
    info = _ffmpeg(["-i", str(video)])
    out: dict = {}
    if m := re.search(r"Duration: (\d+):(\d+):([\d.]+)", info):
        out["duration"] = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
    if m := re.search(r"Video: .*?, (\d{2,5})x(\d{2,5})", info):
        out["width"], out["height"] = int(m[1]), int(m[2])
    if m := re.search(r"([\d.]+) fps", info):
        out["fps"] = float(m[1])
    out["has_audio"] = "Audio:" in info
    return out


def check_video(video: Path, scenes: list[SceneAudio], script: ReelScript, cfg: Config) -> VerifyResult:
    result = VerifyResult()
    if not video.exists() or video.stat().st_size < 50_000:
        result.fail("Video file missing or empty.")
        return result

    info = probe(video)
    result.checks["probe"] = info
    if (info.get("width"), info.get("height")) != (cfg.width, cfg.height):
        result.fail(f"Resolution is {info.get('width')}x{info.get('height')}, expected {cfg.width}x{cfg.height}.")
    duration = info.get("duration", 0)
    if duration > MAX_SECONDS:
        words = sum(len(s.narration.split()) for s in script.scenes)
        result.fail(f"Video is {duration:.1f}s; the limit is {MAX_SECONDS}s. Cut the narration from {words} "
                    f"to about {int(words * (MAX_SECONDS - 2) / duration)} words.")
    elif duration < 10:
        result.fail(f"Video is only {duration:.1f}s long.")
    if not info.get("has_audio"):
        result.fail("Video has no audio track.")

    vol = _ffmpeg(["-i", str(video), "-vn", "-af", "volumedetect", "-f", "null", "-"])
    if m := re.search(r"mean_volume: (-?[\d.]+) dB", vol):
        mean = float(m[1])
        result.checks["mean_volume_db"] = mean
        if mean < -35:
            result.fail(f"Audio is almost silent (mean {mean} dB).")

    black = _ffmpeg(["-i", str(video), "-an", "-vf", "blackdetect=d=0.4:pix_th=0.08", "-f", "null", "-"])
    black_total = sum(float(x) for x in re.findall(r"black_duration:([\d.]+)", black))
    result.checks["black_seconds"] = round(black_total, 2)
    if black_total > 0.8:
        result.fail(f"{black_total:.1f}s of black frames.")

    spoken = sum(len(s.words) for s in scenes)
    written = sum(len(s.narration.split()) for s in script.scenes)
    result.checks["caption_coverage"] = round(spoken / max(written, 1), 2)
    if spoken < written * 0.8:
        result.fail("Captions are missing for part of the narration (voice timing data incomplete).")

    size_mb = video.stat().st_size / 1e6
    result.checks["size_mb"] = round(size_mb, 1)
    if size_mb > 100:
        result.fail(f"File is {size_mb:.0f} MB; too large for easy upload.")
    return result


# ---------- 3. Claude review ----------

class Review(BaseModel):
    human_feel: int = Field(description="1-10: does this look and sound like a real creator made it (10) or obviously AI-generated (1)?")
    hook: int = Field(description="1-10: does the first sentence plant a specific question the viewer wants answered (10), or is it a statement of the topic, background, or the answer given away (1-4)? Would it stop someone scrolling?")
    visuals_match: int = Field(description="1-10: do the frames fit what's being said? Theme-appropriate stock footage counts as a match; only contradicting or misleading footage scores low.")
    accuracy: int = Field(description="1-10: are the claims correct and not misleading, as far as you know?")
    story: int = Field(description="1-10: is it one story where each scene follows from the last ('but'/'so'), the hook's question is held back and answered only at the end, and the last line ties back to the first (10)? Or a list of loosely connected facts, or a news recap (1-4)?")
    blocking_issues: list[str] = Field(description="Problems that must be fixed before posting: factual errors, contradictions between scenes, misleading or exaggerated claims, anything that sounds obviously AI-written, a weak first line, or a video that is a list of facts instead of one story. Empty if none.")
    issues: list[str] = Field(description="Smaller improvements worth making. Empty if none.")
    fix_instructions: str = Field(description="Concrete instructions for the writer to fix the issues in the next draft. Empty if none.")


REVIEW_SYSTEM = """You are a strict short-form video editor reviewing a Reel/Short before it is posted. \
You judge whether it feels made by a real human creator (a confident, well-informed presenter), hooks instantly, matches visuals to words, \
and is accurate. Be honest and specific; don't pass mediocre work. Anything that would embarrass \
the creator in the comments (a wrong fact, a line that contradicts another, a clickbait exaggeration) \
is a blocking issue, and so is stating an unconfirmed claim about a real person as fact.

The footage is stock video: it can never show a specific named person, team or event. Generic \
footage that fits the theme (a soccer pitch for a football story, a trading screen for markets) is \
normal for this format and fine. Only footage that contradicts or misleads — the wrong sport or \
place, or a stranger presented as if they were the person being named — is a visuals problem. \

Big numbers in 'stat' graphics count up from zero during the first second of their scene, so a \
frame can catch one mid-count (e.g. 31,000 on its way to 52,000). That is the animation, not an \
error: judge the number against the graphic's headline listed with the voiceover."""


def contact_sheet(video: Path, out_path: Path, frames: int = 6) -> Path:
    duration = probe(video).get("duration", 10)
    tiles = []
    for i in range(frames):
        t = duration * (i + 0.5) / frames
        tile = out_path.with_name(f"_frame{i}.jpg")
        _ffmpeg(["-y", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1", "-vf", "scale=360:640", str(tile)])
        if tile.exists():
            tiles.append(Image.open(tile).convert("RGB"))
            tile.unlink()
    cols = 3
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (360 * cols, 640 * max(rows, 1)), "black")
    for i, tile in enumerate(tiles):
        sheet.paste(tile, ((i % cols) * 360, (i // cols) * 640))
    sheet.save(out_path, quality=85)
    return out_path


def _describe_graphic(g) -> str:
    if g.type == "none":
        return ""
    points = ", ".join(f"{p.label}: {p.display}" for p in g.points)
    return f"\n   [on-screen {g.type}: {g.headline!r}, {g.label}{f' ({points})' if points else ''}]"


def review_with_claude(video: Path, script: ReelScript, cfg: Config,
                       stock_footage: bool = True) -> tuple[Review, VerifyResult]:
    sheet = contact_sheet(video, video.with_name("review_frames.jpg"))
    narration = "\n".join(f"{i + 1}. {s.narration}{_describe_graphic(s.graphic)}"
                          for i, s in enumerate(script.scenes))
    prompt = (
        f"The image is a contact sheet of 6 frames sampled evenly through the video, left to right, "
        f"top to bottom.\n\nOn-screen hook: {script.title}\nTopic: {script.topic}\n"
        f"Facts used: {script.facts_checked}\n\nVoiceover by scene, with the animated graphic shown "
        f"on screen if any (its numbers are claims too):\n{narration}\n\n"
        f"Caption: {script.caption}\n\nScore it and list what to fix."
    )
    if not stock_footage:
        prompt += ("\nNote: backgrounds are plain placeholder gradients because no stock-footage key is "
                   "configured. Don't penalise that; score visuals_match 10 and judge the rest.")
    review = ask(cfg.ai_backend, cfg.claude_model, REVIEW_SYSTEM, prompt, Review, images=[sheet], effort=cfg.claude_effort)

    result = VerifyResult()
    scores = [review.human_feel, review.hook, review.visuals_match, review.accuracy, review.story]
    result.score = round(sum(scores) / len(scores), 1)
    result.checks["review"] = review.model_dump()
    if review.blocking_issues:
        for issue in review.blocking_issues:
            result.fail("Reviewer: " + issue)
    elif min(scores) < 6 or result.score < 7:
        result.fail("Reviewer: " + "; ".join(review.issues or ["scores too low"]))
    return review, result
