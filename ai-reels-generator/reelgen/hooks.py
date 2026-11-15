"""The first 3-5 seconds, for every pipeline's writer: shared rules for an energetic, specific opening, the openings
the last videos used (never the same move twice in a row), and a check for generic openers ("Did you know",
"In this video", "Doston, aaj hum...") that the Shorts and long pipelines send back to their own line fixers and the
others repair with one small call (`fix_first_line`). Scripts the user wrote are never touched.
"""

from __future__ import annotations

import json
import logging
import re

from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

RULES = """The opening (the first 3-5 seconds decide whether anyone stays):
- Open on the most surprising concrete thing in the video, in the first words: a shocking number, a bold claim, a
moment of action already happening, a contradiction, a mystery the viewer needs solved, a stake for the viewer. No
warm-up, no context first.
- High energy: short, punchy, specific (a name, a number, a place, an image), a verb early. It sounds like a creator
who can't wait to tell this, never like a narrator clearing their throat.
- Never open with a greeting, the channel, "Did you know", "Have you ever wondered", "In this video", "Today we...",
"Let me tell you", "So,", "Here's", "Imagine", "Doston", "Aaj hum", "Kya aapko pata hai", a dictionary definition or a
slow date-and-place setup.
- It promises what the video really delivers: no clickbait.
- Pick the kind of opening that fits this material (shock figure, bold claim, cold-open action, contradiction, stakes
question, countdown, "you" in the situation) and never the one the last videos used."""

WEAK = re.compile(
    r"^\W*(did you know|have you ever|ever wondered|in this video|in today'?s video|today,? (we|i|let'?s)|let me tell you|"
    r"hi\b|hey\b|hello\b|welcome\b|namaste\b|doston\b|dosto\b|aaj hum\b|aaj ki (is )?video|kya aapko pata hai|kya aap jaante|"
    r"so,|here'?s (the|a|why|how|what)\b|imagine\b|picture this\b)", re.I)


def weak(line: str) -> str:
    """The generic opener a line starts with, or ''."""
    m = WEAK.match(line.strip())
    return m.group(1).strip() if m else ""


def recent_openings(cfg, n: int = 10) -> list[str]:
    """The first sentence of the last videos made (every pipeline), newest first."""
    out = []
    root = cfg.output_dir
    for path in sorted(root.glob("*/report.json"), reverse=True)[: n * 3] if root.exists() else []:
        try:
            narration = json.loads(path.read_text(encoding="utf-8")).get("narration") or ""
        except (OSError, ValueError):
            continue
        first = re.split(r"(?<=[.?!।])\s", narration.strip(), maxsplit=1)[0].strip()
        if first and first not in out:
            out.append(" ".join(first.split()[:16]))
        if len(out) >= n:
            break
    return out


def block(cfg) -> str:
    """The rules plus the openings the last videos used, for a writer's prompt."""
    recent = recent_openings(cfg)
    tail = ("\nThe last videos opened like this; open differently (another kind of opening, other words):\n"
            + "\n".join(f"- {x}" for x in recent)) if recent else ""
    return "\n\n" + RULES + tail


class Opening(BaseModel):
    line: str = Field(description="The new first line.")


def fix_first_line(cfg, line: str, context: str, ask_fn=None) -> str:
    """One small call: the same first line without its generic opener, as energetic as the rules ask, same facts,
    same language, about the same length. The line as it was when anything goes wrong."""
    from .llm import ask

    system = ("You rewrite the first line of a short video so it hooks in under 3 seconds. " + RULES
              + "\nKeep the facts and the language (Hinglish stays Hinglish), never add a fact, and keep it about as long.")
    prompt = f"The video: {context[:600]}\nFirst line now: {line}\nIt opens with a generic phrase ({weak(line)}). Rewrite it."
    try:
        call = ask_fn or (lambda sy, pr: ask(cfg.ai_backend, cfg.claude_model, sy, pr, Opening, effort="low", timeout=300))
        new = call(system, prompt).line.strip()
    except Exception as exc:  # noqa: BLE001 - a plainer opening is better than no video
        from .stopper import Paused
        if isinstance(exc, Paused):
            raise
        log.warning("Couldn't sharpen the opening: %s", exc)
        return line
    return new if new and not weak(new) and len(new.split()) <= max(20, 2 * len(line.split())) else line


def sharpen(cfg, items: list, context: str, progress=log.info, attr: str = "line") -> int:
    """For writers without a line fixer of their own: each item (a shot, a part's first shot) whose `attr` opens with
    a generic phrase gets its line rewritten (fix_first_line), before the fact-check. Returns how many changed."""
    changed = 0
    for it in items:
        line = getattr(it, attr, "") if it is not None else ""
        if line and weak(line):
            new = fix_first_line(cfg, line, context)
            if new != line:
                progress(f"Sharper opening: \"{new}\" (was \"{line}\")")
                setattr(it, attr, new)
                changed += 1
    return changed
