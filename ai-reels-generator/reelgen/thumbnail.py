"""YouTube thumbnails, made on request from the video page, with Gemini (no API key).

1. Plan: Claude looks at the video (its title, story, hook and a sheet of its frames, so it knows
   the subject and the colours) and designs a click-worthy thumbnail: one bold subject, 2-4 huge
   words that pair with the title's keyword (never repeat it), the video's palette. It writes a
   prompt for Gemini's image generator (the Gemini app > Images, Nano Banana, 16:9) that leaves
   room for the words, plus a version where Gemini draws the words itself and two other concepts
   to test.
2. The user makes the image in the Gemini desktop app with their own account and uploads it.
3. By default Reel Studio adds the words itself (Remotion `Thumbnail` composition: exact
   spelling, outlined type in the video's colours), since image models misspell text.
4. Claude checks the result against the video: same subject and look, words right and readable
   at phone size, a click-worthiness score; a failed check comes with a corrected prompt.

The video's frames are only shown to Claude; they never appear in the thumbnail.
Files: thumbnail-youtube.jpg (the result) and thumb/ (frames sheet, the upload, the drawn one);
the report gets `thumbnail_design`.
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Literal

from PIL import Image
from pydantic import BaseModel, Field

from .config import Config
from .llm import ask
from .video import FFMPEG, REMOTION_DIR

log = logging.getLogger(__name__)

OUT = "thumbnail-youtube.jpg"
FOLDER = "thumb"
FRAMES = 10
MAX_BYTES = 2 * 1024 * 1024  # YouTube's thumbnail limit


class Concept(BaseModel):
    idea: str = Field(description="The picture in one sentence.")
    gemini_prompt: str = Field(description="Complete prompt for Gemini's image generator for this concept (no text in the image).")


class ThumbPlan(BaseModel):
    idea: str = Field(description="The picture in one sentence: one subject from the video, the moment of tension or surprise.")
    text: str = Field(description="2-4 words, the biggest thing on the thumbnail. From the video's own title, hook or lines; a figure only if the video says it. Pairs with the YouTube title (adds curiosity), never repeats it word for word.")
    highlight: str = Field(description="The word or two of `text` to colour in the accent colour (the surprising part).")
    sub: str = Field(default="", description="Optional small badge, max 4 words: a date or figure the video states, or empty.")
    side: Literal["left", "right", "top", "bottom"] = Field(description="Where the words go; the image keeps that area simple and dark.")
    gemini_prompt: str = Field(description="Complete prompt for Gemini's image generator (Nano Banana): the subject, style (cinematic photo-real or bold 3D render, whichever suits the video), dramatic lighting, the video's colours by name and hex, close framing on one subject, the "
                               "`side` area left empty and dark for big words, 16:9 landscape (9:16 for a Short), sharp, high contrast, no text, no letters, no logos, no watermarks, no real people's faces.")
    gemini_prompt_with_text: str = Field(description="The same picture, but asking Gemini to also write `text` in huge bold white letters with a thick black outline on the `side` (spell it out letter by letter in quotes).")
    alternatives: list[Concept] = Field(description="Two different concepts for A/B testing (YouTube's Test & Compare).")
    title_pairing: str = Field(description="One sentence: how the words and the title work together (the title carries the search keyword, the thumbnail the curiosity).")
    why: str = Field(description="One sentence: why someone scrolling stops and clicks, and why it matches the video.")


class ThumbCheck(BaseModel):
    matches_video: bool = Field(description="Does it show the video's subject and fit its look (a viewer who clicks sees what was promised)?")
    text_ok: bool = Field(description="Words spelled right, readable at phone size (160 px wide), true to the video?")
    clickable: int = Field(description="1-10: would someone scrolling past stop and click? One clear subject, contrast, curiosity, readable at small size.")
    passed: bool = Field(description="True only if it matches the video, the text is right and clickable is 7 or more.")
    issues: list[str] = Field(default_factory=list, description="Specific problems.")
    better_prompt: str = Field(default="", description="If it failed: a corrected Gemini prompt that fixes the issues.")


PLAN_SYSTEM = """You are a YouTube thumbnail designer for a faceless channel, and you design for \
click-through: one big subject, one emotion or tension, 2-4 huge words, high contrast, readable on \
a phone at 160 px wide, and a curiosity gap that the title completes (the title holds the search \
keyword; the thumbnail must not repeat it). The thumbnail must match the video: a viewer who clicks \
must find that subject and look in it. Never invent a figure, claim or quote: every word comes from \
the video. No fake news imagery, no real people's faces, nothing misleading."""

CHECK_SYSTEM = """You check a YouTube thumbnail against its video. Be strict about accuracy and \
spelling (a word or figure the video doesn't support fails it) and about whether it would stop a \
scroll. Be practical about style."""


# ---------- what Claude sees ----------

def _report(folder: Path) -> dict:
    return json.loads((folder / "report.json").read_text(encoding="utf-8"))


def _frames_sheet(folder: Path, long: bool) -> Path:
    """A numbered sheet of the video's frames, so Claude knows its subject and colours."""
    out = folder / FOLDER
    out.mkdir(exist_ok=True)
    sheet_path = out / "frames.jpg"
    if sheet_path.exists():
        return sheet_path
    dur = float(_report(folder).get("duration_seconds") or 30)
    w, h = (480, 270) if long else (216, 384)
    cols = 5
    sheet = Image.new("RGB", (w * cols, h * ((FRAMES + cols - 1) // cols)), "black")
    for i in range(FRAMES):
        tile = out / f"_f{i}.jpg"
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", f"{dur * (i + 0.5) / FRAMES:.2f}",
                        "-i", str(folder / "reel.mp4"), "-frames:v", "1", "-vf", f"scale={w}:{h}", str(tile)], check=False)
        if tile.exists():
            sheet.paste(Image.open(tile).convert("RGB"), ((i % cols) * w, (i // cols) * h))
            tile.unlink()
    sheet.save(sheet_path, quality=85)
    return sheet_path


def _palette(folder: Path) -> list[str]:
    props = folder / "props.json"
    if props.exists():
        look = json.loads(props.read_text(encoding="utf-8")).get("look") or {}
        if look.get("accents"):
            return list(look["accents"])
    return ["#ffd23f", "#ff5a36"]


def _context(folder: Path, report: dict) -> str:
    script = json.loads((folder / "script.json").read_text(encoding="utf-8")) if (folder / "script.json").exists() else {}
    script = script.get("script", script)
    hook = [h.get("line", "") for h in script.get("hook", [])]
    lines = ([b.get("narration", "") for c in script.get("chapters", [])[:2] for b in c.get("beats", [])[:4]]
             or [s.get("narration", "") for s in script.get("scenes", [])[:4]])
    long = report.get("format") == "long"
    return (f"YouTube title: {report.get('youtube_title') or report.get('title')}\n"
            f"Format: {'long video, thumbnail 16:9 (1280x720)' if long else 'Short, thumbnail 9:16 (1080x1920)'}\n"
            f"The video's colours: {', '.join(_palette(folder))}\n"
            f"Subject: {script.get('subject', report.get('topic', ''))}\n"
            f"Big question: {script.get('hook_question', '')}\nAnswer (don't give it away): {script.get('answer', '')}\n"
            f"Hook lines: {' / '.join(hook)}\nOpening lines: {' '.join(lines)}")


def _unsupported(text: str, folder: Path) -> list[str]:
    """Figures in the thumbnail words that the video never shows or says."""
    said = " ".join((folder / n).read_text(encoding="utf-8") for n in ("script.json", "props.json") if (folder / n).exists())
    return [n for n in re.findall(r"\d[\d,.]*", text) if n.rstrip(".,") not in said]


def _store(folder: Path, report: dict, **changes) -> dict:
    design = {**(report.get("thumbnail_design") or {}), **changes}
    report["thumbnail_design"] = design
    (folder / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return design


# ---------- 1. plan ----------

def plan(cfg: Config, folder: Path, feedback: str = "") -> dict:
    report = _report(folder)
    sheet = _frames_sheet(folder, report.get("format") == "long")
    prompt = (f"{_context(folder, report)}\n\nThe image is a sheet of frames from the video (for its subject and look "
              f"only; the thumbnail is a new image made in Gemini, not a frame). Design the thumbnail."
              + (f"\nFix this from the last try: {feedback}" if feedback else ""))
    p = ask(cfg.ai_backend, cfg.claude_model, PLAN_SYSTEM, prompt, ThumbPlan, images=[sheet],
            effort=cfg.claude_effort, timeout=600)
    bad = _unsupported(f"{p.text} {p.sub}", folder)
    if bad and not feedback:
        return plan(cfg, folder, f"The figures {', '.join(bad)} are not in the video; use only what the video says.")
    return _store(folder, report, plan=p.model_dump(), planned=time.time())


# ---------- 2-4. upload, words, check ----------

def _run_stills(composition: str, props: dict, public: Path, out: Path) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump({"composition": composition, "props": props, "publicDir": str(public.resolve()),  # node runs in remotion/
                   "stills": [{"frame": 0, "out": str(out.resolve())}]}, f)
        job = f.name
    try:
        done = subprocess.run(["node", str(REMOTION_DIR / "scripts" / "stills.mjs"), job], cwd=REMOTION_DIR,
                              capture_output=True, text=True, timeout=600)
        if done.returncode != 0:
            raise RuntimeError((done.stderr or done.stdout).strip()[-600:])
    finally:
        os.unlink(job)


def _fit(src: Path | io.BytesIO, long: bool) -> Image.Image:
    """Crop and scale to 1280x720 (or 1080x1920 for a Short)."""
    im = Image.open(src).convert("RGB")
    size = (1280, 720) if long else (1080, 1920)
    ratio = max(size[0] / im.width, size[1] / im.height)
    im = im.resize((round(im.width * ratio), round(im.height * ratio)), Image.LANCZOS)
    left, top = (im.width - size[0]) // 2, (im.height - size[1]) // 2
    return im.crop((left, top, left + size[0], top + size[1]))


def _save_final(im: Image.Image, folder: Path) -> Path:
    out = folder / OUT
    for q in (92, 85, 78, 70):
        im.save(out, quality=q, optimize=True)
        if out.stat().st_size <= MAX_BYTES:
            break
    return out


def add_words(folder: Path, image: Path, plan_: dict, long: bool) -> Path:
    """Write the plan's words onto the Gemini image, in the video's colours (exact spelling)."""
    accents = _palette(folder)
    props = folder / "props.json"
    currency = json.loads(props.read_text(encoding="utf-8")).get("currency", "") if props.exists() else ""
    out = folder / FOLDER / "with-words.jpg"
    _run_stills("Thumbnail", {
        "src": image.relative_to(folder).as_posix(), "text": plan_["text"], "highlight": plan_.get("highlight", ""),
        "sub": plan_.get("sub", ""), "side": plan_.get("side", "left"), "focusX": 0.5, "focusY": 0.5, "zoom": 1,
        "accent": accents[0], "accent2": accents[1] if len(accents) > 1 else accents[0], "mark": "none",
        "currency": currency, "wide": long}, folder, out)
    return out


def check(cfg: Config, folder: Path, image: Path, report: dict) -> ThumbCheck:
    sheet = _frames_sheet(folder, report.get("format") == "long")
    small = folder / FOLDER / "small.jpg"
    Image.open(image).convert("RGB").resize((320, 180) if report.get("format") == "long" else (180, 320)).save(small)
    p = (report.get("thumbnail_design") or {}).get("plan") or {}
    prompt = (f"{_context(folder, report)}\nPlanned words: {p.get('text', '')}\n\nImage 1 is the thumbnail, image 2 the "
              "same at phone size, image 3 a sheet of frames from the video. Check it.")
    return ask(cfg.ai_backend, cfg.claude_model, CHECK_SYSTEM, prompt, ThumbCheck, images=[image, small, sheet],
               effort=cfg.claude_effort, timeout=600)


def upload(cfg: Config, folder: Path, data: bytes, words: bool = True) -> dict:
    """The image made in Gemini: fitted to YouTube's size, words added (unless Gemini wrote them),
    checked against the video, kept as the thumbnail."""
    report = _report(folder)
    long = report.get("format") == "long"
    try:
        Image.open(io.BytesIO(data)).verify()
    except Exception:
        raise ValueError("That file isn't an image")
    (folder / FOLDER).mkdir(exist_ok=True)
    picture = folder / FOLDER / "picture.jpg"
    _fit(io.BytesIO(data), long).save(picture, quality=95)
    p = (report.get("thumbnail_design") or {}).get("plan")
    final = picture
    if words and p:
        try:
            final = add_words(folder, picture, p, long)
        except Exception as exc:
            log.warning("Adding the words failed, keeping the picture as it is: %s", exc)
    verdict = check(cfg, folder, final, report)
    _save_final(Image.open(final).convert("RGB"), folder)
    return _store(folder, report, check=verdict.model_dump(), made=time.time(),
                  made_by="Gemini + words by Reel Studio" if final != picture else "Gemini")
