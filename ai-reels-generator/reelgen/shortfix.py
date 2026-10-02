"""Targeted fixes for Shorts: change only the scenes a check flagged, then check only those.

A Short used to cost ~1.2M Claude tokens: every fact-check fix and every failed review wrote a
whole new script (with research) and fact-checked all of it again from scratch. Long videos
already fix only the flagged lines (longform.fix_long_script); this does the same for Shorts:

- `fix_scenes`: Claude returns only the scenes it changed (and the on-screen hook if needed);
  everything else, including its sounds and transitions, stays as it was.
- `fact_check_scenes`: re-checks only the changed scenes (marked >>), the rest is context.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from .config import Config
from .llm import ask
from .script_writer import Graphic, ReelScript, word_range
from .verify import FACT_CHECK_SYSTEM, FactCheck, VerifyResult

log = logging.getLogger(__name__)


class SceneFix(BaseModel):
    scene: int = Field(description="Scene number (1 = first). 0 = the on-screen hook text only.")
    narration: str = Field(default="", description="The corrected voiceover for this scene (empty for scene 0).")
    visual_queries: list[str] = Field(default_factory=list, description="2-3 stock-footage queries; repeat the old ones unless the footage was the problem.")
    graphic: Graphic | None = Field(default=None, description="The corrected graphic, or the same one; type 'none' to drop it.")
    title: str = Field(default="", description="Scene 0 only: the new on-screen hook text, max 6 words.")


class ScriptFixes(BaseModel):
    fixes: list[SceneFix] = Field(description="Only the scenes you changed, each in full.")


FIX_SYSTEM = """You correct a short-form video script. Change only the scenes the problems are \
about, as little as needed, keeping the voice, the story, the hook and the length. Never invent a \
figure: use web search to get it right, or drop the claim. A graphic's numbers must match its \
scene's voiceover. Return only the scenes you changed."""


def _numbered(script: ReelScript, mark: set[int] | None = None) -> str:
    lines = [f"{'>>' if mark and 0 in mark else '  '} 0 hook on screen: {script.title}"]
    for i, s in enumerate(script.scenes, 1):
        g = s.graphic
        graphic = "" if g.type == "none" else f" | graphic ({g.type}): {g.headline} | {g.label}" + (
            " | " + ", ".join(f"{p.label}={p.display}" for p in g.points) if g.points else "")
        lines.append(f"{'>>' if mark and i in mark else '  '} {i} voiceover: {s.narration}{graphic} | footage: {', '.join(s.visual_queries)}")
    return "\n".join(lines)


def fix_scenes(script: ReelScript, cfg: Config, issues: list[str], instructions: str = "",
               web: bool = True) -> tuple[ReelScript, set[int]]:
    """Rewrite only the flagged scenes. Returns the script and which scenes changed (0 = hook)."""
    low, high = word_range(cfg.target_seconds)
    words = sum(len(s.narration.split()) for s in script.scenes)
    prompt = (f"Topic: {script.topic}\nThe script ({words} words; it must stay {low}-{high} words), numbered:\n"
              f"{_numbered(script)}\n\nProblems:\n" + "\n".join(issues)
              + (f"\n\nSuggested fixes: {instructions}" if instructions else "")
              + "\n\nReturn only the scenes you changed.")
    result = ask(cfg.ai_backend, cfg.claude_model, FIX_SYSTEM, prompt, ScriptFixes, allow_web=web,
                 effort=cfg.claude_effort)
    fixed = script.model_copy(deep=True)
    changed: set[int] = set()
    for f in result.fixes:
        if f.scene == 0 and f.title.strip():
            fixed.title = f.title.strip()
            changed.add(0)
        elif 1 <= f.scene <= len(fixed.scenes) and f.narration.strip():
            old = fixed.scenes[f.scene - 1]
            fixed.scenes[f.scene - 1] = old.model_copy(update={
                "narration": f.narration.strip(),
                "visual_queries": f.visual_queries or old.visual_queries,
                "graphic": f.graphic if f.graphic is not None else old.graphic,
            })  # sounds and transition stay; a sound whose word is gone is dropped at render
            changed.add(f.scene)
    log.info("Fixed scene(s): %s", ", ".join("hook" if c == 0 else str(c) for c in sorted(changed)) or "none")
    return fixed, changed


def fact_check_scenes(script: ReelScript, cfg: Config, only: set[int]) -> VerifyResult:
    """Fact-check only the scenes marked >> (just corrected); the rest was checked before."""
    prompt = (f"Topic: {script.topic}\nThe writer's sources: {script.facts_checked}\n\n{_numbered(script, only)}\n\n"
              "Only the lines marked >> were just corrected; the others were already checked. Fact-check the "
              ">> lines (and any contradiction they create with the rest). Don't flag unmarked lines.")
    check = ask(cfg.ai_backend, cfg.claude_model, FACT_CHECK_SYSTEM, prompt, FactCheck, allow_web=True,
                effort=cfg.claude_effort)
    result = VerifyResult()
    result.checks["fact_check"] = check.model_dump()
    for issue in check.blocking_issues:
        result.fail("Fact-check: " + issue)
    return result
