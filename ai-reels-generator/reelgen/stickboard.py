"""Stick documentaries: every narration beat gets a picture of what that beat says, and the pictures are checked.

The user's 'How YouTube started' documentary (3 min) said "above a pizzeria", "Valentine's Day", "Sequoia invested
$3.5 million", "Google would buy YouTube" and "it happened at the zoo... two elephants" over three men standing in
the same street or office: one scene (one place) covered up to 20 narration lines, and nothing asked the writer to
show what a line names. Of 50 lines about a dozen showed their subject.

`storyboard` (one Claude call, no web, after the fact-check, so the words are final) stages every beat on its own:
the concrete thing the line names (`shows`), a place (built-in or drawn), objects (drawn, icons or Claude's own
SVG; a symbolic object for a number), the cast's poses and one action, the camera. `check` draws a still of every
beat (remotion/scripts/stills.mjs), puts each over its line on contact sheets and asks Claude which pictures don't
show their line; those beats are storyboarded once more with the reasons (`fix`). Narration, timing and voices are
never changed here: only the pictures.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import textwrap
from pathlib import Path
from typing import Callable

from pydantic import BaseModel, Field

from . import stopper
from .config import Config
from .llm import ask
from .stickstory import Camera, Setting, SActor, SPiece, SScene, SThing

# The scene's own choices, so Claude sees the same values as when it writes an episode.
Weather = SScene.model_fields["weather"].annotation
Light = SScene.model_fields["light"].annotation
Ambience = SScene.model_fields["ambience"].annotation

log = logging.getLogger(__name__)
Progress = Callable[[str], None]

PICTURE_RULES = """Every beat is its own picture, and the picture shows what THAT beat says. Read the line and find \
its concrete subject: a place ("above a pizzeria" = the pizzeria's front with the window above it), an object, an \
event ("the tsunami" = a big wave over a shore, far away, nobody harmed; "a Super Bowl half-time show" = a stadium \
stage with lights), a date ("Valentine's Day" = a calendar page with a red heart), a number or amount ("$3.5 \
million" = money bags or stacked bills; "25 million videos" = a wall of screens or boxes filling up; "a million \
views" = a play-button screen with a crowd), an action ("he uploaded the clip" = him at a computer with a progress \
bar on the screen). Write it in `shows`, then make the picture show it: the place, the objects in it, and the \
people doing the action. A person standing in a generic street or office while the line talks about something else \
is a failed picture. A line that goes back to an earlier moment goes back to that place ("it happened at the zoo... \
two elephants" = the zoo again with the elephants). Two beats in a row may share a place only when both lines are \
in it, and then the camera, the action or an object must change.

The PLACE is where the line happens, recognisable at a glance: a built-in setting only when it IS that place (an \
office line in an office); a pizzeria, a training ground, a stadium, an investor's boardroom, a 2005 bedroom office \
are drawn ('blank' + `backdrop_svg`, see Drawings) with their landmarks and their `sign`. A beat back in a place \
drawn before sets `same_as` to that beat's number instead of drawing it again. `place` names a real place the \
line names or is in ('San Mateo, California · 2005'); it shows as a tag the first time.

The ACTION is the line acted out: the people DO it ('kick' at a 'goal' for a shot at the crossbar, 'juggle', \
'type' at a 'screen', 'film' with a camera, 'handshake' on a deal, 'count-money', 'write' at a 'board', 'watch' a \
screen, 'carry' boxes, 'cheer', 'walk-in' through a door), facing what they act on. Standing still beside a small \
icon is a failed picture. A number, date or name the line says goes on an object as its `label`, exactly as said \
(a screen '1,000,000 views', money '$3.5 million', a calendar 'FEB 14', a board '20,000 videos a day'); a \
lucide icon alone never carries a number.

Cold-open beats (marked HOOK) are the video's trailer: the most dramatic picture for each line, a different place \
or framing every beat, camera 'punch' or 'close' on the big moments. A real logo, building, document or the real place appears only as a proof picture (a thing with \
`photo`, see Proof pictures), never drawn; no drawn real person's likeness."""

# Comedy, stories and the facts type are told in dialogue: a conversation may stay in one place for several lines.
DIALOGUE_RULES = """This video is told in dialogue, so a conversation may stay in one place for several lines; \
'every beat its own picture' then means: whatever a line mentions appears or is acted out on that line (the report \
card someone holds up, the volcano erupting, the phone with the message, the door slammed, the dog that ate the \
homework), the speaker's pose and face play the line, and a line about another place or time (a flashback, 'last \
night at the party') cuts there. People standing still while a line talks about something nobody can see is a \
failed picture. Keep the jokes' timing: the reveal object appears on the line that reveals it, not before."""


class BeatPicture(BaseModel):
    beat: int = Field(description="The beat's number.")
    shows: str = Field(description="The concrete subject of this beat's own words that the picture shows.")
    setting: Setting = Field(description="The place; 'blank' with backdrop_svg for a place no setting shows.")
    backdrop_svg: str = Field(default="", description="With setting 'blank': your drawing of the place (see Drawings).")
    sign: str = ""
    weather: Weather = "none"  # type: ignore[valid-type]
    light: Light = "day"  # type: ignore[valid-type]
    ambience: Ambience = "none"  # type: ignore[valid-type]
    place: str = Field(default="", description="A real place the line names or is in, for its tag ('San Mateo, California · 2005'); empty otherwise.")
    same_as: int = Field(default=-1, description="The number of an earlier beat whose drawn place this beat returns to (its backdrop is reused); -1 = none.")
    camera: Camera = "wide"
    focus: str = ""
    furniture: list[SPiece] = Field(default_factory=list, description="The place's furniture; empty = the usual.")
    actors: list[SActor] = Field(default_factory=list, description="Who is on screen, their spot, pose, face and ONE action.")
    things: list[SThing] = Field(default_factory=list, description="The objects that show what the line names.")


class Board(BaseModel):
    beats: list[BeatPicture]


class Verdict(BaseModel):
    beat: int
    matches: bool = Field(description="True when the picture shows what the line says.")
    problem: str = Field(default="", description="When it doesn't: what the line names that the picture lacks.")


class PictureCheck(BaseModel):
    beats: list[Verdict]


def beats_of(ep) -> list[tuple[int, int]]:
    return [(si, li) for si, sc in enumerate(ep.scenes) for li, ln in enumerate(sc.lines)]


def _numbered(ep) -> str:
    def say(ln) -> str:
        return f"[{ln.speaker}] {ln.line}" if ln.line.strip() else f"[silent beat: {ln.speaker}] {getattr(ln, 'note', '')}".rstrip()
    return "\n".join(f"{k}.{' HOOK' if ep.scenes[si].hook else ''} {say(ep.scenes[si].lines[li])}"
                     for k, (si, li) in enumerate(beats_of(ep)))


def storyboard(cfg: Config, ep, system_rules: str, progress: Progress, only: dict[int, str] | None = None,
               narrated: bool = True):
    """Stage every beat (or only the beats in `only`, with what was wrong) on its own picture. Returns the episode
    with one scene per run of beats in the same place; the narration is untouched. Any failure keeps it as it was."""
    pairs = beats_of(ep)
    cast = "; ".join(f"{c.id} ({c.look}, {c.design.top if c.design else 'clothes'})" for c in ep.cast)
    if only:
        ask_for = "\n".join(f"{k}. {ep.scenes[pairs[k][0]].lines[pairs[k][1]].line}\n   NOT SHOWN: {why}" for k, why in only.items())
        prompt = (f"Title: {ep.title}\nCast (ids): {cast}\nThe whole narration, for context:\n{_numbered(ep)}\n\n"
                  f"These beats' pictures didn't show their lines. Stage only these again, so each shows what it says:\n{ask_for}")
    else:
        prompt = f"Title: {ep.title}\nCast (ids): {cast}\nThe narration, one beat per line:\n{_numbered(ep)}\n\nStage every beat."
    try:
        board = ask(cfg.ai_backend, cfg.claude_model, PICTURE_RULES + ("" if narrated else "\n\n" + DIALOGUE_RULES)
                    + "\n\n" + system_rules, prompt, Board,
                    effort=cfg.claude_effort, timeout=1800)
    except Exception as exc:  # noqa: BLE001 - the episode's own staging is the fallback
        if isinstance(exc, stopper.Paused):
            raise
        log.warning("Couldn't storyboard the beats: %s", exc)
        return ep
    ids = {c.id for c in ep.cast}
    staged: dict[int, dict] = {}
    for b in sorted(board.beats, key=lambda x: x.beat):
        if not (0 <= b.beat < len(pairs)) or (only and b.beat not in only):
            continue
        actors = [a for a in b.actors if a.id in ids]
        backdrop, setting = b.backdrop_svg, b.setting
        if b.same_as in staged and staged[b.same_as]["scene"].backdrop_svg:  # back in a place drawn before
            backdrop, setting = staged[b.same_as]["scene"].backdrop_svg, "blank"
        scene_fields = SScene(setting=setting, sign=b.sign, furniture=b.furniture, backdrop_svg=backdrop,
                              weather=b.weather, light=b.light, ambience=b.ambience, place=b.place.strip()[:60], lines=[])
        things = b.things
        staged[b.beat] = {"scene": scene_fields, "camera": b.camera, "focus": b.focus if b.focus in ids else "",
                          "actors": actors, "things": things, "shows": b.shows}
    if not staged:
        return ep
    # One scene per run of beats in the same place (no cut flash inside a place); the line keeps its words.
    scenes: list = []
    for k, (si, li) in enumerate(pairs):
        old_scene, line = ep.scenes[si], ep.scenes[si].lines[li]
        s = staged.get(k)
        if s:
            line = line.model_copy(update={"camera": s["camera"], "focus": s["focus"], "actors": s["actors"],
                                           "things": s["things"]})
            place = s["scene"].model_copy(update={"intensity": old_scene.intensity, "hook": old_scene.hook})
        else:
            place = old_scene.model_copy(update={"lines": []})
        key = (place.setting, place.backdrop_svg, place.sign, place.weather, place.light, place.ambience, place.hook,
               place.place, json.dumps([p.model_dump() for p in place.furniture]))
        if scenes and scenes[-1][0] == key:
            scenes[-1][1].lines.append(line)
        else:
            scenes.append((key, place.model_copy(update={"lines": [line]})))
    progress(f"Storyboard: {len(staged)} beat(s) staged to show what they say"
             + (f" (e.g. \"{next(iter(staged.values()))['shows']}\")" if staged else ""))
    return ep.model_copy(update={"scenes": [sc for _, sc in scenes]})


def _stills(props: dict, work: Path, times: list[float], out_dir: Path, vertical: bool) -> list[Path]:
    from .video import REMOTION_DIR

    fps = props.get("fps", 30)
    out_dir.mkdir(parents=True, exist_ok=True)
    stills = [{"frame": round(t * fps), "out": str((out_dir / f"b{k:03d}.jpg").resolve()), "scale": 0.25}
              for k, t in enumerate(times)]
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump({"composition": "StickStory", "props": props, "publicDir": str(work.resolve()), "stills": stills}, f)
        job = f.name
    try:
        done = stopper.run(["node", str(REMOTION_DIR / "scripts" / "stills.mjs"), job], cwd=REMOTION_DIR,
                           capture_output=True, text=True, timeout=1800)
        if done.returncode != 0:
            raise RuntimeError((done.stderr or done.stdout).strip()[-500:])
    finally:
        os.unlink(job)
    return [Path(s["out"]) for s in stills]


def sheets(props: dict, work: Path, lines: list[str], vertical: bool) -> list[Path]:
    """Contact sheets of every beat's picture (60% into its shot) with its line written under it, 12 to a sheet."""
    from PIL import Image, ImageDraw, ImageFont

    shots = props["shots"]
    times = [s["start"] + s["duration"] * 0.6 for s in shots]
    folder = work / "_board"
    shutil.rmtree(folder, ignore_errors=True)
    files = _stills(props, work, times, folder, vertical)
    tw, th = (240, 427) if vertical else (480, 270)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 15)
    except OSError:
        font = ImageFont.load_default()
    tiles = []
    for k, (f, text) in enumerate(zip(files, lines)):
        tile = Image.new("RGB", (tw, th + 64), "white")
        tile.paste(Image.open(f).convert("RGB").resize((tw, th)), (0, 0))
        d = ImageDraw.Draw(tile)
        for r, row in enumerate(textwrap.wrap(f"{k}. {text}", 30 if vertical else 60)[:3]):
            d.text((4, th + 3 + r * 19), row, font=font, fill="black")
        tiles.append(tile)
    out, per, cols = [], 12, (6 if vertical else 3)
    for s in range(0, len(tiles), per):
        chunk = tiles[s:s + per]
        rows = (len(chunk) + cols - 1) // cols
        sheet = Image.new("RGB", (tw * cols, (th + 64) * rows), "white")
        for k, t in enumerate(chunk):
            sheet.paste(t, ((k % cols) * tw, (k // cols) * (th + 64)))
        path = folder / f"sheet{s // per}.jpg"
        sheet.save(path, quality=85)
        out.append(path)
    return out


CHECK_SYSTEM = ("You check a stick-figure video before it is posted. Each numbered picture sits over the line spoken "
                "while it is on screen (narration or a character's dialogue). Be strict: a viewer with the sound off must "
                "be able to tell what each line is about. A picture FAILS when: (1) people stand or sit doing nothing "
                "while the line describes something happening (a kick, a deal, an upload, a crowd watching): the action "
                "must be acted out; (2) the line's subject is shown only by a small icon on a table; (3) the line names "
                "a place (a pizzeria, a stadium, a city, an office of a named company) and the picture shows a generic "
                "room or street instead; (4) the line says a number, date or amount and nothing in the picture shows it "
                "(a screen, board, calendar or money with those words); (5) it shows a different place or moment than "
                "the line. In dialogue, people talking in the scene's place is fine when the line is talk, but whatever "
                "the line mentions must be shown. For each failure say exactly what is missing (the action, the place, "
                "the number).")


def check(cfg: Config, props: dict, ep, work: Path, vertical: bool, progress: Progress) -> dict[int, str]:
    """Which beats' pictures don't show their lines: {beat: what's missing}. Empty when all match or the check fails."""
    lines = [(f"[{ln.speaker}] {ln.line}" if ln.line.strip() else f"[silent: {ln.speaker}]")
             for ln in (ep.scenes[si].lines[li] for si, li in beats_of(ep))]
    if len(lines) != len(props.get("shots") or []):
        return {}
    try:
        progress("Checking that every picture shows what's said")
        paths = sheets(props, work, lines, vertical)
        verdict = ask(cfg.ai_backend, cfg.fact_model, CHECK_SYSTEM,
                      f"{len(lines)} pictures on {len(paths)} sheet(s). Give a verdict for every number.", PictureCheck,
                      images=paths, effort=cfg.fact_effort, timeout=900)
    except Exception as exc:  # noqa: BLE001 - a check that can't run never stops the video
        if isinstance(exc, stopper.Paused):
            raise
        log.warning("Couldn't check the pictures: %s", exc)
        return {}
    finally:
        shutil.rmtree(work / "_board", ignore_errors=True)
    return {v.beat: (v.problem or "it doesn't show the line") for v in verdict.beats if not v.matches and 0 <= v.beat < len(lines)}
