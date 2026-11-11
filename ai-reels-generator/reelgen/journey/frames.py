"""The Journey's pictures: one photograph per stage, all from the same fixed camera.

The first stage (and the stage after the opening cut) is drawn from its words; every other stage is drawn FROM the
stage before it (img2img on this computer, or an edit of that photo on Hugging Face), changing only what the stage
changes, so the place, the camera and the light carry on like one time-lapse. Then Claude looks at every picture
(`check`): it must show its stage truthfully (the real plant, colours, parts) and keep the place; broken ones are
drawn again."""
from __future__ import annotations

import logging
from pathlib import Path

from pydantic import BaseModel, Field

from .. import anim_engine, hfcloud
from ..config import Config
from ..llm import ask
from .story import Journey

log = logging.getLogger(__name__)

W, H = 1344, 768
LOOK = "RAW photo, photorealistic, natural colours, shallow depth of field, shot on a full-frame camera"
NEGATIVE = ("text, letters, watermark, logo, frame, border, split screen, collage, cartoon, illustration, painting, "
            "drawing, 3d render, cgi, plastic, toy, oversaturated, oversharpened, hdr, blurry subject, deformed, "
            "duplicate, people's faces, aerial view, top-down view, bird's-eye view, drone shot")
STRENGTH = {"small": 0.38, "medium": 0.52, "large": 0.66}  # how far img2img may move from the stage before


def path(work: Path, k: int) -> Path:
    return work / "keyframes" / f"k{k:02d}.jpg"


def prompt(j: Journey, k: int, picture: str) -> str:
    """The camera first: SDXL weighs the start of a prompt most, and a stage drawn fresh from the writer's words
    (subject first, camera last) came out from above instead of from the low fixed camera. The opening event shot
    (stage 1 before a cut) keeps its own framing, which its words give."""
    opening = k == 0 and any(s.cut for s in j.stages[1:])
    lead = "" if opening else f"Photo from a {j.camera.strip().rstrip('.')}. "
    return f"{lead}{picture.strip()} {LOOK}"


def job(j: Journey, work: Path, seed: int, fixes: dict | None = None) -> dict:
    """The worker's `keyframes` job (also what hfcloud.draw takes). `fixes`: {id: {"prompt", "round"}} from the check."""
    fixes = fixes or {}
    items = []
    for k, s in enumerate(j.stages):
        it = {"id": f"k{k:02d}", "out": str(path(work, k)), "seed": seed + (0 if k == 0 or not s.cut else 50),
              "prompt": prompt(j, k, s.picture)}
        if k and not s.cut:  # grows out of the picture before it
            it.update(init=str(path(work, k - 1)), strength=STRENGTH[s.change], edit=s.what.strip())
        fix = fixes.get(it["id"])
        if fix:
            it["seed"] += 1000 * int(fix.get("round", 1))
            it["prompt"] = prompt(j, k, fix["prompt"])
            if "strength" in it:  # a stage that didn't change enough is allowed to move further
                it["strength"] = min(0.8, it["strength"] + 0.12)
        items.append(it)
    return {"characters": [], "shots": items, "negative": NEGATIVE, "width": W, "height": H, "steps": 5,
            "guidance": 1.5, "model": "photoreal", "ip_adapter": False}


def draw(jb: dict, work: Path, progress, engine: str, stop) -> str:
    """Draw what isn't drawn yet. Returns the engine that drew ('cloud' or 'local'). Cloud first when chosen; when
    the day's free GPU minutes run out, the rest is drawn on this computer if its AI engine is installed."""
    if all(Path(it["out"]).exists() and Path(it["out"] + ".ok").exists() for it in jb["shots"]):
        return "done"
    if engine in ("cloud", "auto") and hfcloud.ready():
        try:
            hfcloud.draw(jb, work, progress, stop, size=(W, H))
            return "cloud"
        except hfcloud.CloudOut as exc:
            if engine == "cloud" or not anim_engine.installed():
                raise
            progress(f"Hugging Face is out of free minutes for today ({str(exc)[:80]}); drawing the rest on this computer")
    if not anim_engine.installed():
        raise RuntimeError("Nothing can draw the pictures: install the AI engine (Anim tab) or save a Hugging Face "
                           "token (Anim tab, Hugging Face box)")
    anim_engine.run_stage("keyframes", jb, work, progress, "Drawing the stages")
    return "local"


# ---------- Claude looks at every picture ----------

class PicIssue(BaseModel):
    id: str = Field(description="The label on the picture, e.g. k03")
    problem: str = Field(description="What is wrong, a few words")
    prompt: str = Field(description="A new photo prompt for this stage, 45-90 words, same rules: the subject's true "
                                    "state first, then the place and camera words unchanged, then the light")


class PicReview(BaseModel):
    broken: list[PicIssue] = Field(default_factory=list)


CHECK_SYSTEM = """You check the photographs of a nature time-lapse before they are animated (minutes of work each). The
tiles are the stages in order, label in the corner; each stage's description is listed. Flag a picture only when a
viewer would notice: it doesn't show its stage truthfully (the wrong plant or animal, wrong colours or parts for that
age, a stage that looks like a different moment), it looks fake (cartoon, plastic, CGI, garbled shapes, duplicated
objects, impossible anatomy), there is writing or a frame, the subject is cut off by the edge, or the place and camera
jump so much from the picture before that it can't be the same spot (a little change of light and weather is right).
When unsure, let it pass. For each broken one give a new prompt the image model can draw."""


def check(cfg: Config, j: Journey, work: Path, only: list[str] | None = None) -> list[dict]:
    from ..animated import _pic_sheets

    pics = [(f"k{k:02d}", path(work, k)) for k in range(len(j.stages))]
    pics = [(i, p) for i, p in pics if p.exists() and (only is None or i in only)]
    if not pics:
        return []
    sheets = _pic_sheets(pics, work / "keyframes")
    rows = "\n".join(f"k{k:02d}: [{s.elapsed}] {s.what}" for k, s in enumerate(j.stages)
                     if only is None or f"k{k:02d}" in only)
    prompt = (f"Subject: {j.subject}\nPlace: {j.place}\nCamera: {j.camera}\n\nStages:\n{rows}\n\n"
              "The pictures are attached as contact sheets.")
    review = ask(cfg.ai_backend, cfg.fact_model, CHECK_SYSTEM, prompt, PicReview, images=sheets, allow_web=False,
                 effort=cfg.fact_effort, timeout=900)
    ids = {i for i, _ in pics}
    return [b.model_dump() for b in review.broken if b.id in ids]


ROUNDS = 2


def _only(jb: dict, ids: list[str] | None) -> dict:
    return jb if ids is None else {**jb, "shots": [it for it in jb["shots"] if it["id"] in ids]}


def make(cfg: Config, j: Journey, work: Path, seed: int, state: dict, progress, engine: str, stop, save) -> tuple[list[dict], str]:
    """Draw and check in two phases. Every later stage is drawn from the one before it, so a broken base picture
    spreads down the whole chain (a test's second picture showed two coconuts joined by a stalk, and every stage
    after it would have too): first the pictures drawn from words (stage 1, and the first after the cut), checked
    and redrawn until they pass (twice at most); then the chain grows from them and is checked. Black pictures (a
    graphics card's broken numbers) are found in code and drawn again before Claude sees anything. Returns every
    finding and which engine drew."""
    from ..animated import blank_pictures

    found: list[dict] = state.get("pic_found") or []
    fixes = state.get("pic_fixes") or {}
    base = [it["id"] for it in job(j, work, seed)["shots"] if "init" not in it]
    drew = state.get("drew") or ""
    for phase, ids in (("base", base), ("chain", None)):
        if state.get(f"pics_{phase}"):
            continue
        got = draw(_only(job(j, work, seed, fixes), ids), work, progress, engine, stop)
        drew = drew if got == "done" and drew else got
        state["drew"] = drew
        only = ids if phase == "base" else [i for i in (f"k{k:02d}" for k in range(len(j.stages))) if i not in base]
        for rnd in range(state.get(f"pic_round_{phase}", 0), ROUNDS):
            blank = blank_pictures(work, only)
            if blank:
                for b in blank:
                    for p in (work / "keyframes" / f"{b}.jpg", work / "keyframes" / f"{b}.jpg.ok"):
                        p.unlink(missing_ok=True)
                draw(_only(job(j, work, seed, fixes), ids), work, progress, engine, stop)
                if blank_pictures(work, only):
                    raise RuntimeError("The pictures keep coming out black: the graphics card's numbers break (see the log)")
            if not only:
                break
            progress(("Claude is checking the first pictures" if phase == "base" else "Claude is checking the pictures")
                     + (" again" if rnd else ""))
            try:
                broken = check(cfg, j, work, only)
            except Exception as exc:  # noqa: BLE001 - a check that fails never stops the video
                if exc.__class__.__name__ in ("Paused", "Stopped"):
                    raise
                log.warning("Picture check failed: %s", exc)
                progress(f"The picture check didn't run ({str(exc)[:80]}); keeping the pictures")
                break
            found += [{**b, "round": rnd + 1, "phase": phase} for b in broken]
            if not broken:
                break
            progress(f"{len(broken)} picture(s) to draw again: " + "; ".join(f"{b['id']} {b['problem']}" for b in broken)[:200])
            for b in broken:
                fixes[b["id"]] = {"prompt": b["prompt"], "round": int(fixes.get(b["id"], {}).get("round", 0)) + 1}
                for p in (work / "keyframes" / f"{b['id']}.jpg", work / "keyframes" / f"{b['id']}.jpg.ok"):
                    p.unlink(missing_ok=True)
            state.update(pic_fixes=fixes, pic_found=found, **{f"pic_round_{phase}": rnd + 1})
            save("pictures")
            draw(_only(job(j, work, seed, fixes), ids), work, progress, engine, stop)
            only = [b["id"] for b in broken]
        state[f"pics_{phase}"] = True
        state.update(pic_fixes=fixes, pic_found=found)
        save("pictures")
    return found, drew
