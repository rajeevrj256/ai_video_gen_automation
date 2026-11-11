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
# On this computer every stage is drawn FROM THE BASE picture (the first from the fixed camera), moving further from it
# the more has changed since: a test that drew each stage from the one before it compounded the model's artifacts
# (sharpening and colour noise grew every step until the sand was confetti). Hugging Face's edit model changes the
# photo before it (`edit_from`): editing keeps a photo's quality.
POINTS = {"small": 1, "medium": 2, "large": 3}


def strength(points: int) -> float:
    """Hugging Face edits / a stage with no mask: how far from the base picture."""
    return round(min(0.72, 0.34 + 0.05 * points), 2)


# Drawn from the base picture alone, a stage barely changed (a test's sprout was a few sticks, its storm invisible):
# img2img strong enough to grow a palm also loses the place. So on this computer each later stage is two passes in the
# worker: the whole frame a little (the light and the weather), then the subject drawn anew inside a soft mask that
# grows with it (`MASK_STRENGTH`). Claude marks where the subject is when it checks the base picture.
MASK_STRENGTH = 0.95
DEFAULT_BOX = [0.35, 0.45, 0.65, 0.9]


def light_strength(base_light: str, light: str) -> float:
    """How far the whole frame may move from the base for this stage's light and weather. Even at 0.64 a test's storm
    stage looked like the sunny base (the model won't repaint a sky from a picture), so the editor grades each
    stage's light and draws the rain (run.grade); here only a little drift, so the place stays put."""
    if light == base_light:
        return 0.22
    return 0.35


def mask_path(work: Path, k: int) -> Path:
    return work / "keyframes" / f"m{k:02d}.png"


def write_mask(out: Path, box: list[float], size: float, base_size: float, keep: bool = False) -> None:
    """A soft white shape over where the subject is and will grow: from the ground under it up to its new height.
    `keep`: the base subject stays (a palm grows out of the coconut): the lower part of its box is left out, else
    redrawing at full strength made the coconut vanish under the new palm."""
    from PIL import Image, ImageDraw, ImageFilter

    x0, y0, x1, y1 = (max(0.0, min(1.0, float(v))) for v in (box + DEFAULT_BOX)[:4])
    tall = max(y1 - y0, float(size or 0.3), float(base_size or 0.3) * 0.5) * 1.35
    cx, bottom = (x0 + x1) / 2, min(1.0, y1 + 0.04)
    top = max(0.0, bottom - tall)
    wide = max((x1 - x0) * 1.5, tall * 1.25 * H / W)
    m = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(m)
    d.ellipse([(cx - wide / 2) * W, top * H, (cx + wide / 2) * W, (bottom + 0.06) * H], fill=255)
    if keep:
        d.ellipse([(x0 - 0.01) * W, (y0 + (y1 - y0) * 0.35) * H, (x1 + 0.01) * W, (y1 + 0.03) * H], fill=0)
    out.parent.mkdir(parents=True, exist_ok=True)
    m.filter(ImageFilter.GaussianBlur(28)).save(out)


def path(work: Path, k: int) -> Path:
    return work / "keyframes" / f"k{k:02d}.jpg"


def prompt(j: Journey, k: int, picture: str, chain: bool = False) -> str:
    """The camera first: SDXL weighs the start of a prompt most, and a stage drawn fresh from the writer's words
    (subject first, camera last) came out from above instead of from the low fixed camera. The opening event shot
    (stage 1 before a cut) keeps its own framing, which its words give."""
    opening = k == 0 and any(s.cut for s in j.stages[1:])
    camera = f"Photo from a {j.camera.strip().rstrip('.')}."
    place = "" if j.place.strip()[:40].lower() in picture.lower() else f" Setting: {j.place.strip()}"
    if chain:  # drawn from the base picture, whose framing it keeps: what the subject is now comes first
        return f"{picture.strip()}{place} {camera} {LOOK}"
    return f"{'' if opening else camera + ' '}{picture.strip()}{place} {LOOK}"


def job(j: Journey, work: Path, seed: int, fixes: dict | None = None, boxes: dict | None = None) -> dict:
    """The worker's `keyframes` job (also what hfcloud.draw takes). `fixes`: {id: {"prompt", "round"}} from the check;
    `boxes`: {base id: [x0, y0, x1, y1]} where the subject is in each base picture (masks are made from them)."""
    fixes, boxes = fixes or {}, boxes or {}
    items, base, points = [], 0, 0
    for k, s in enumerate(j.stages):
        chain = bool(k and not s.cut)
        it = {"id": f"k{k:02d}", "out": str(path(work, k)), "seed": seed + (0 if k == 0 or not s.cut else 50),
              "prompt": prompt(j, k, s.picture, chain)}
        if k == 0 or s.cut:
            base, points = k, 0
        else:  # grows out of the base picture (here) or the stage before (Hugging Face's edit)
            points += POINTS[s.change]
            it.update(init=str(path(work, base)), strength=light_strength(j.stages[base].light, s.light),
                      edit=s.what.strip(), edit_from=str(path(work, k - 1)), mask=str(mask_path(work, k)),
                      mask_strength=1.0 if s.size >= 1.8 * j.stages[base].size else MASK_STRENGTH,
                      box=boxes.get(f"k{base:02d}") or DEFAULT_BOX, size=s.size, base_size=j.stages[base].size,
                      keep=bool(s.keeps))
        fix = fixes.get(it["id"])
        if fix:
            it["seed"] += 1000 * int(fix.get("round", 1))
            it["prompt"] = prompt(j, k, fix["prompt"], chain)
            if "strength" in it:  # a stage that didn't change enough is allowed to move further
                it["strength"] = min(0.8, it["strength"] + 0.08)
                it["box"] = [max(0.0, it["box"][0] - 0.04), max(0.0, it["box"][1] - 0.04), min(1.0, it["box"][2] + 0.04), it["box"][3]]
        items.append(it)
    return {"characters": [], "shots": items, "negative": NEGATIVE, "width": W, "height": H, "steps": 5,
            "guidance": 1.5, "model": "photoreal", "ip_adapter": False}


def draw(jb: dict, work: Path, progress, engine: str, stop) -> str:
    """Draw what isn't drawn yet. Returns the engine that drew ('cloud' or 'local'). Cloud first when chosen; when
    the day's free GPU minutes run out, the rest is drawn on this computer if its AI engine is installed."""
    if all(Path(it["out"]).exists() and Path(it["out"] + ".ok").exists() for it in jb["shots"]):
        return "done"
    for it in jb["shots"]:
        if it.get("mask"):
            write_mask(Path(it["mask"]), it["box"], it["size"], it["base_size"], it.get("keep", False))
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


class SubjectBox(BaseModel):
    id: str = Field(description="The picture's label")
    box: list[float] = Field(description="Where the subject is: [left, top, right, bottom] as fractions 0-1 of the "
                                         "picture's width and height")


class PicReview(BaseModel):
    broken: list[PicIssue] = Field(default_factory=list)
    subjects: list[SubjectBox] = Field(default_factory=list, description="Only when asked: the subject's box in each "
                                                                         "picture that passes")


CHECK_SYSTEM = """You check the photographs of a nature time-lapse before they are animated (minutes of work each). The
tiles are the stages in order, label in the corner; each stage's description is listed. Flag a picture only when a
viewer would notice: it doesn't show its stage truthfully (the wrong plant or animal, wrong colours or parts for that
age, a stage that looks like a different moment), it looks fake (cartoon, plastic, CGI, garbled shapes, duplicated
objects, impossible anatomy), there is writing or a frame, the subject is cut off by the edge, or the place and camera
jump so much from the picture before that it can't be the same spot (a little change of light and weather is right).
When unsure, let it pass. For each broken one give a new prompt the image model can draw."""


def check(cfg: Config, j: Journey, work: Path, only: list[str] | None = None, boxes: dict | None = None,
          weather_later: bool = False) -> list[dict]:
    """The broken pictures; with `boxes` (a dict) given, also fills it with the subject's box in each picture.
    `weather_later`: the editor adds light and weather (pictures from this computer, run.grade): don't fail a
    picture for a missing storm or night."""
    from ..animated import _pic_sheets

    pics = [(f"k{k:02d}", path(work, k)) for k in range(len(j.stages))]
    pics = [(i, p) for i, p in pics if p.exists() and (only is None or i in only)]
    if not pics:
        return []
    sheets = _pic_sheets(pics, work / "keyframes")
    rows = "\n".join(f"k{k:02d}: [{s.elapsed}] {s.what}"
                     + (" (NEW CAMERA SET-UP: the planned cut to the fixed close camera; a new framing of the same place is "
                        "right here, judge only that it is the same place)" if k and s.cut else "")
                     for k, s in enumerate(j.stages) if only is None or f"k{k:02d}" in only)
    prompt = (f"Subject: {j.subject}\nPlace: {j.place}\nCamera: {j.camera}\n\nStages:\n{rows}\n\n"
              "The pictures are attached as contact sheets."
              + ("\nFor every picture that passes, also give `subjects`: the box around the subject itself (the fruit, "
                 "the seed, the plant), as fractions of that picture." if boxes is not None else "")
              + ("\nThe light and weather of each stage (storm clouds, rain, night, golden evening) are added to these "
                 "pictures afterwards by the editor: don't fail a picture for its light, sky or rain; judge the subject "
                 "(its state, its parts, wet or dry) and the place." if weather_later else ""))
    review = ask(cfg.ai_backend, cfg.fact_model, CHECK_SYSTEM, prompt, PicReview, images=sheets, allow_web=False,
                 effort=cfg.fact_effort, timeout=900)
    ids = {i for i, _ in pics}
    if boxes is not None:
        for sb in review.subjects:
            if sb.id in ids and len(sb.box) == 4 and sb.box[2] > sb.box[0] and sb.box[3] > sb.box[1]:
                boxes[sb.id] = [round(float(v), 3) for v in sb.box]
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
        boxes = state.setdefault("boxes", {})
        missing = [i for i in base if i not in boxes and (work / "keyframes" / f"{i}.jpg").exists()]
        if phase == "chain" and missing:  # a base picture redrawn last wasn't looked at: where is its subject?
            try:
                check(cfg, j, work, missing, boxes)
            except Exception as exc:  # noqa: BLE001 - the default box then
                if exc.__class__.__name__ in ("Paused", "Stopped"):
                    raise
                log.warning("Finding the subject failed: %s", exc)
        got = draw(_only(job(j, work, seed, fixes, boxes), ids), work, progress, engine, stop)
        drew = drew if got == "done" and drew else got
        state["drew"] = drew
        only = ids if phase == "base" else [i for i in (f"k{k:02d}" for k in range(len(j.stages))) if i not in base]
        for rnd in range(state.get(f"pic_round_{phase}", 0), ROUNDS):
            blank = blank_pictures(work, only)
            if blank:
                for b in blank:
                    for p in (work / "keyframes" / f"{b}.jpg", work / "keyframes" / f"{b}.jpg.ok"):
                        p.unlink(missing_ok=True)
                draw(_only(job(j, work, seed, fixes, boxes), ids), work, progress, engine, stop)
                if blank_pictures(work, only):
                    raise RuntimeError("The pictures keep coming out black: the graphics card's numbers break (see the log)")
            if not only:
                break
            progress(("Claude is checking the first pictures" if phase == "base" else "Claude is checking the pictures")
                     + (" again" if rnd else ""))
            try:
                broken = check(cfg, j, work, only, boxes if phase == "base" else None, weather_later=drew == "local")
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
            draw(_only(job(j, work, seed, fixes, boxes), ids), work, progress, engine, stop)
            only = [b["id"] for b in broken]
        state[f"pics_{phase}"] = True
        state.update(pic_fixes=fixes, pic_found=found)
        save("pictures")
    return found, drew
