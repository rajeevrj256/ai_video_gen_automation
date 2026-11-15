"""The cinematic hook: how long videos and Script Videos open (and what the Anim cold open and every Short borrow).

Modelled on a documentary cold open the user sent ("i need this type of audio and graphics animation on hooks";
a ~75 s open of ~48 picture changes that keeps people watching): each beat in its own colour grade under film
grain and flicker, typed yellow labels, whips, VHS glitches, a photo flown in, paper torn across the frame, a
split-second montage at the climax, then the music stops dead for a breath of silence and the story starts with
a question that re-asks the hook. Sound: a dark drone from the first frame, a deep sub boom on the big cuts, a
whips, typewriter ticks, and silence. (The riser into the big cuts was taken out: the user banned it.)

This module holds the parts shared by the pipelines: the writer's rules, shot timing, the hook's sound design
and its AI film stills (the AI engine's keyframes stage, when installed). The editor side is remotion/src/cine/.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable, Literal

from . import sfx as synth

log = logging.getLogger(__name__)
Progress = Callable[[str], None]

GRADES = ("amber", "red", "noir", "fire", "cold", "natural")
TRANSITIONS = ("whip", "glitch", "photo", "split", "dip", "punch", "cut")
Grade = Literal["amber", "red", "noir", "fire", "cold", "natural"]
Transition = Literal["whip", "glitch", "photo", "split", "dip", "punch", "cut"]

DROP = 1.6  # seconds of silence between the hook and the story (music and drone cut, a subscribe button clicked)
LABEL_AT = 0.3  # seconds into a shot when its label starts typing: keep in step with remotion/src/cine/types.ts
FLASH = (0.72, 0.6, 0.52, 0.46, 0.42, 0.4)  # the climax montage's shots, each shorter than the last
MAX_FLASH = 6
STRETCH_MAX = 1.2  # seconds a shot may be held past its line to reach the hook's length
PHOTO_LAND = 0.4  # seconds into a photo transition when the print lands (CineIn 'photo')

GRADE_HELP = ("The shot's colour, following the emotion: amber (the past, an archive, warmth), noir (black and white: "
              "memory, secrecy, the record), red (danger, violence, alarm), fire (destruction, fury, heat), cold "
              "(technology, night, isolation), natural. Change it as the story escalates; never 4 shots in a row alike.")
TRANSITION_HELP = ("How the shot comes in: whip (energy, a jump in place or time), glitch (something hidden, a lie "
                   "exposed, tech), photo (an archive picture or a document flown in over the last shot), split "
                   "(paper torn across: the other side, before/after), punch (a hard cut closer, for emphasis), dip "
                   "(out of black: a new beat), cut. Vary them; whips and cuts most often.")
BOOM_HELP = "A deep boom as this shot cuts in: only the 2-4 biggest moments of the hook (the first shot always gets one)."
FLASH_HELP = ("A split-second shot (about half a second, no line) in the rapid montage just before the hook's last "
              "line: 3-6 of them in a row at the climax, each a different striking image.")
PICTURE_HELP = ("This shot as a cinematic film still for an image model, 15-45 words: the subject, the setting and "
                "era, the light, the lens. Never text, signs, logos or a real person's face (people from behind, in "
                "silhouette, far away, or only hands). Empty where a number, a chart or a timeline is the evidence "
                "(the visual is shown then); the visual is also shown when no picture can be drawn.")
LABEL_HELP = ("A typed label for this shot, 1-5 words, typed onto the picture: a place and year ('DAMASCUS, 1965'), a "
              "name, a number, a status ('CLASSIFIED'), or empty. About half the shots have one. A label states a "
              "fact, so it must be true.")

RULES = """The hook ({lo}-{hi} seconds, before chapter 1) is a cinematic cold open, cut like a documentary \
trailer, NOT the story starting. 8-14 shots, plus a montage of 3-6 flash shots, that escalate:
- Shot 1 lands the single most arresting image or fact of the story with a boom; it never explains.
- Then a ladder of WHAT, never HOW: each shot raises the stakes over the one before (a strange fact, who or what is \
involved, what was at risk, the most visceral, highest-stakes moment last). Short punchy lines (3-12 words), \
statements or questions, present tense where it works; some shots have no line and let picture and sound carry \
them. Never give the answer away.
- Near the end, the montage: 3-6 flash shots (flash: true, no line), each a different striking image, building to \
the peak; then the last line lands the big question this video answers.
- The hook then drops to silence for a breath, and chapter 1's first line re-asks it in new words (a short \
question), before the story starts.
- Every shot gets a grade and a transition that follow the story's emotion; mark boom on the 2-4 biggest moments; \
give about half the shots a typed label (text, 1-5 words: a place and year, a name, a number, a status), true like \
everything else; give most shots a picture (a film-still prompt, no text, no real person's face), keeping a visual \
for every shot (it is shown when no picture can be drawn, and is the evidence for numbers and dates)."""

# A plain storyboard or an older script (no grades or transitions): a grade per beat role and varied cuts, so a
# re-made video gets the cinematic hook too.
BY_BEAT = {"curiosity": "amber", "unexpected": "cold", "tension": "red", "problem": "noir", "gap": "fire"}
CYCLE = ("whip", "glitch", "punch", "whip", "split", "cut", "photo", "glitch")
GRADE_CYCLE = ("amber", "cold", "noir", "red", "amber", "fire", "noir", "red")

CINE_LOOK = ("cinematic film still, 35mm documentary photograph, dramatic natural light, deep shadows, shallow depth "
             "of field, realistic, highly detailed, no text")
PIC_NEGATIVE = ", portrait, close-up of a face, cartoon, illustration, anime, 3d render, painting"


# ---------- hook templates ----------
# The user, after a cinematic hook of slow dark stills with a small typed word: "hooks not energetic ... must be hook
# retention at start, look like simple slide, read text". The energetic templates (remotion/src/cine/Energy.tsx)
# open at full energy on frame 0 and keep something moving every half second; the cinematic one stays as a choice.
TEMPLATES = {
    "kinetic": ("⚡ Kinetic words", "The hardest-hitting words of each line slam onto the screen, huge, in colour "
                "(every spoken word only with subtitles on). Fast voice, a beat from the first frame."),
    "rapid": ("🎬 Fast cuts", "Full, bright pictures with a jump-cut zoom every half second, an RGB hit on every cut and "
              "bold 2-3 word captions with the spoken word lit up when subtitles are on."),
    "stakes": ("💥 Big stakes", "Each shot's number or key words slam in giant and shake the frame (numbers count up), "
               "the line in small captions below when subtitles are on."),
    "myth": ("🚫 Myth buster", "Opens on what most people believe and stamps it MYTH in red, then teases the truth "
             "with key words slammed over bright pictures."),
    "mirror": ("👉 It's you", "Speaks to the viewer about a moment they live, each line popping up like a phone "
               "notification over bright everyday pictures, then the turn they didn't see coming."),
    "rewind": ("⏪ Ending first", "Opens on how it ends, then the tape rewinds (VHS lines, a time stamp) and the hook "
               "climbs back toward that moment."),
    "promise": ("✅ Promise + list", "The most striking fact, then exactly what you'll know by the end: the points tick "
                "onto a checklist as they're said."),
    "teaser": ("🎞 Coming up", "A trailer of the video's own best moments, a COMING UP tag and jump cuts, then the big "
               "question."),
    "bulletin": ("📟 Bulletin", "A green terminal screen: a numbered bulletin tag, each shot's words typed in or its "
                 "number counted up in big pixel digits, a status flashed in an inverse block, the source at the foot."),
    "frontpage": ("📰 Front page", "Each shot a newspaper front page: its headline in huge condensed capitals on "
                  "stained paper, a typed caption strip; the first page spins in, the next ones slide over it."),
    "cinematic": ("🎞 Cinematic", "The documentary cold open: colour grades, film grain, typed labels, whips and a dark "
                  "drone. Slower and moodier."),
}
# The user (600 impressions, 17 views, 1:47 watched on average) asked for more hook templates after research on
# retention hooks: the five above the cinematic one are the openings the guides name again and again (a belief
# proved wrong, the viewer's own situation, the ending first, a specific promise, a preview of the payoff). They all
# open at full energy (cine/Energy.tsx); only the words' shape and the overlay differ.
ENERGETIC = ("kinetic", "rapid", "stakes", "myth", "mirror", "rewind", "promise", "teaser", "bulletin", "frontpage")
# From the user's reference hooks of a news-explainer channel (a green 'emergency bulletin' terminal, a newspaper front
# page), taken as styles: these draw the whole screen from each shot's text and kicker (cine/Screens.tsx), no picture.
SCREEN_TEMPLATES = ("bulletin", "frontpage")
ENERGY_DROP = 0.9  # the breath of silence after an energetic hook (the cinematic one keeps DROP)
ENERGY_LOOK = ("vivid cinematic photograph, bright punchy colours, high contrast, crisp detail, dynamic angle, "
               "realistic, no text")
_MEMORY = "hook_templates.json"


def energetic(template: str | None) -> bool:
    return (template or "cinematic") in ENERGETIC


def recent_templates(cfg) -> list[str]:
    try:
        return json.loads((cfg.output_dir / _MEMORY).read_text(encoding="utf-8"))[-6:]
    except (OSError, ValueError):
        return []


def remember_template(cfg, template: str) -> None:
    try:
        path = cfg.output_dir / _MEMORY
        path.write_text(json.dumps((recent_templates(cfg) + [template])[-12:]), encoding="utf-8")
    except OSError:
        pass


def pick_template(cfg, chosen: str = "") -> str:
    """The template for a new video: the one asked for, else (auto) an energetic one the last video didn't use."""
    want = (chosen or getattr(cfg, "hook_template", "") or "auto").strip()
    if want in TEMPLATES:
        return want
    last = (recent_templates(cfg) or [""])[-1]
    fresh = [t for t in ENERGETIC if t not in recent_templates(cfg)[-3:]] or [t for t in ENERGETIC if t != last]
    import random
    return random.choice(fresh)


def drop_for(template: str | None) -> float:
    return ENERGY_DROP if energetic(template) else DROP


def seconds_for(minutes: float, template: str | None = None) -> tuple[float, float]:
    """How long the hook runs (the silence included): a medium video's is shorter, an energetic one shorter still."""
    if energetic(template):  # the promise lands in ~10 s; the guides call a 45 s opening too long
        return (14.0, 26.0) if minutes < 7 else (16.0, 30.0)
    return (28.0, 38.0) if minutes < 7 else (32.0, 45.0)


TEMPLATE_TEXT = {
    "kinetic": "Give every shot's text the 1-3 words of its line that hit hardest (they are drawn bigger, in colour, as "
               "the line is spoken).",
    "rapid": "Leave text empty on shots with a line (the line itself is the caption); a silent shot may carry 1-3 words.",
    "stakes": "Every shot's text is its giant slam: the number with its unit ('₹1 lakh', '90%', '3 days') or 1-3 "
              "shocking words, true and stated in the story (never a ratio or total you work out yourself); a number "
              "counts up on screen.",
    "myth": "Every shot's text is 1-3 key words of its line, slammed in big; the belief's shot gets its stamp.",
    "mirror": "Every shot's text is its line as a short phone notification or message the viewer would get, 2-6 words "
              "('Salary credited', 'Balance low', 'This month I save'), never a fact the story doesn't state.",
    "rewind": "The rewind shot's text is the time jump exactly as the story states it ('2019', '10 DAYS EARLIER', 'THE "
              "START'), shown like a camcorder's time stamp; other shots 1-3 key words of the line.",
    "promise": "Shots 1-2: text = 1-3 key words, slammed. Each point the video covers: text = a 2-4 word checklist item "
               "(they stack up on screen and tick as they're said).",
    "teaser": "Every shot's text is a 2-4 word tag for the moment it teases (shown under a COMING UP tag).",
    "bulletin": "The template draws the whole screen, so leave picture empty. Every shot's text is what the terminal "
                "shows, 1-5 words: a number with its unit ('$50', '1,200+ websites') counted up in pixel digits, or "
                "a short report line ('Targets: 1,200+ websites'); kicker = its status, 1-4 words flashed in an "
                "inverse block ('Exploit attempt detected', 'Breached: 100+'), or empty. Both only from the story.",
    "frontpage": "The template draws the whole screen, so leave picture empty. Every shot's text is a newspaper "
                 "headline, 3-7 words, in the story's own words (never presented as a real paper's headline unless "
                 "the script quotes that paper's headline); kicker = the caption strip, only on shots the story "
                 "dates or sources ('Reported 19 October', or the outlet and date when the script names them), else "
                 "empty. Never a real newspaper's name as if it printed words it didn't.",
}
KICKER_HELP = ("Bulletin and Front page hooks only: the bulletin's status block (1-4 words) or the newspaper's caption "
               "strip (a source and date the script names); empty otherwise.")

STAMP_HELP = ("Energetic hooks: a rubber stamp slammed across this shot right after its line, 1-2 capital words: MYTH, "
              "WRONG or NOT TRUE only on a line stating a belief the story proves false, TRUE or CONFIRMED on a "
              "surprising line the story confirms; empty for almost every shot (at most 2 per hook).")
REWIND_HELP = ("'Ending first' hooks only: true on the one shot where the hook jumps back in time after showing how it "
               "ends (the tape rewinds into it).")

SHAPE = """- Shot 1 says the single most shocking, concrete, specific thing in the story in at most 8 words: a number, a \
contradiction, a stake for the viewer ("Your salary is gone by the 10th."). Never a greeting, a setup, context, or a \
question about what the viewer knows.
- Then 5-9 more shots, each line 3-9 words, every one raising the stakes or opening a new loop (what, who, how much, \
what nobody tells you), with a turn word where it fits ("But", "Except", "Then"). Never give the answer.
- The last line is the big question or the promise of the payoff, under 10 words."""
SHAPES = {
    "myth": """- Shot 1 states, in the viewer's own words, the belief most people hold about this subject (at most 9 \
words) that the script shows is wrong or only half the story; it gets stamp 'MYTH' (or 'WRONG'). Only a belief the \
script itself corrects: never a straw man, never a claim about a real person.
- Shot 2 turns it hard ("Except that's not why."), then 3-6 shots of the surprising facts the script states, each \
raising the stakes, never the full answer.
- The last line is the question the real answer settles, under 10 words.""",
    "mirror": """- Speak to the viewer as "you" about a moment they live that this story is about. Shot 1 names that \
exact moment in at most 8 words, concrete and everyday ("Your salary lands on the first.").
- 2-3 shots make it sharper and more personal, then the turn: what they never noticed about it, from the script's \
facts ("But nobody told you this."). Never a greeting, never 'Have you ever...'.
- The last line is the question or promise the video answers, under 10 words.""",
    "rewind": """- Shots 1-2 open on how the story ends: its most dramatic outcome or moment, vivid and concrete (what \
happened, never why). Then one shot with rewind true jumps back (its line and text say when, as the script states it).
- Then 3-5 shots climb back toward the ending, each raising the stakes, with a turn word where it fits.
- The last line asks how or why it ended like that, under 10 words; the answer stays for the end.""",
    "promise": """- Shot 1 is the most striking concrete fact of the story in at most 8 words.
- Shot 2 is the promise, specific and in the title's words: what the viewer will know by the end ("By the end, \
you'll know exactly where it goes.").
- Then 3 shots, one per point the video really covers, in its order, each a short teaser (never the answer).
- The last line says why it matters to the viewer, under 10 words.""",
    "teaser": """- A trailer of this video's own best moments: 4-6 shots, each teasing one striking moment from a \
different chapter, in the video's order; the line a short tease of it (at most 9 words, never its explanation) and \
the visual the same as that moment's visual in the script.
- The last line is the big question the video answers, under 10 words.""",
}


ENERGY_RULES = """The hook ({lo}-{hi} seconds, before chapter 1) is a high-energy cold open built to stop the scroll \
and hold viewers through the first 30 seconds; the first 2 seconds decide whether they stay.
- It confirms the title's promise at once: the viewer clicked for the title, so by the third shot (about 10 \
seconds) they know exactly what this video will show them, in the title's own terms.
{shape}
- After the hook a short breath of silence, then chapter 1's first line re-asks its question.
- This hook is drawn as '{name}': {desc} {text}
- Visuals are real, concrete and fill the frame (picture, footage, stat, compare, scene, model3d, meme): never a \
keyword or title slide in the hook (the template draws the words). Give most shots a picture (a bright, vivid photo \
prompt: no text, no real person's face). No flash montage; leave grade natural and transition cut; mark boom on the \
2-3 biggest moments."""


def rules(minutes: float, template: str | None = None) -> str:
    lo, hi = seconds_for(minutes, template)
    if energetic(template):
        name, desc = TEMPLATES[template]
        return ENERGY_RULES.format(lo=int(lo), hi=int(hi), name=name.split(" ", 1)[1], desc=desc, text=TEMPLATE_TEXT[template],
                                   shape=SHAPES.get(template, SHAPE))
    return RULES.format(lo=int(lo), hi=int(hi))


def board_rules(template: str | None) -> str:
    """The Script Video storyboard's hook paragraph for an energetic template (the user's hook words are final)."""
    name, desc = TEMPLATES[template]
    return f"""The hook is a high-energy cold open before the video, drawn as '{name.split(" ", 1)[1]}': {desc} \
It is built from the user's hook lines H1, H2...: give every hook line exactly one shot, in order; add a silent shot \
(line 0) only where a picture lands harder without words (at most 2). The viewer decides in the first 2 seconds: \
shot 1's picture is the most striking, concrete image of the story. Visuals are real, concrete and fill the frame \
(picture, footage, stat, compare, scene, model3d, meme), never a keyword or title slide (the template draws the \
words). {TEMPLATE_TEXT[template]} Text comes only from the hook or the script, never a fact they don't state and \
never a number they don't say (no ratio, total or change you work out yourself, e.g. no '4X' for 20 to 80). Give \
most shots a picture (a bright, vivid photo prompt for an image model: no text, no real person's face), keeping a \
visual for every shot. No flash montage; grade natural; transition cut; boom on the 2-3 biggest moments. After the \
hook a short breath of silence, then the script starts.{BOARD_EXTRA.get(template, "")}"""


BOARD_EXTRA = {  # the user's words are final: a template's shape only where their lines already have it
    "myth": " Give stamp 'MYTH' to a hook line that states a belief the script proves wrong (none if no line does).",
    "rewind": " Set rewind true on the hook line where the hook jumps back in time (none if it never does).",
    "teaser": " Where a hook line teases a moment of the script, use that moment's visual.",
    "bulletin": " Text and kicker come from the hook line's own words and figures.",
    "frontpage": " Each headline is the hook line's own words, shortened; a caption only with a source the script names.",
}


def stamp_at(shot: dict) -> float:
    """Seconds into a shot when its stamp lands: just after its line (keep in step with cine/Energy.tsx stampAt)."""
    words = shot.get("words") or []
    at = float(words[-1]["end"]) + 0.12 if words else float(shot["duration"]) * 0.55
    return min(at, max(0.2, float(shot["duration"]) - 0.35))


def timing(lengths: list[float | None], flashes: list[bool], seconds: tuple[float, float], drop: float = DROP,
           breath: float = 0.4) -> list[float]:
    """Shot lengths: each line plus a breath, a silent shot a short hold, flash shots faster and faster (never
    stretched), and the rest stretched (at most STRETCH_MAX each) or tightened so the whole hook, its silence
    included, fits `seconds`."""
    n_flash = 0
    base, floor, fixed = [], [], []
    for ln, fl in zip(lengths, flashes):
        if fl and not ln:
            d = FLASH[min(n_flash, len(FLASH) - 1)]
            n_flash += 1
            base.append(d), floor.append(d), fixed.append(True)
        else:
            n_flash = 0
            base.append((ln + breath) if ln else 1.8 if breath >= 0.4 else 1.0)
            floor.append((ln + min(0.12, breath)) if ln else 1.2 if breath >= 0.4 else 0.8)
            fixed.append(False)
    lo, hi = seconds[0] - drop, seconds[1] - drop
    total = sum(base)
    free = sum(b for b, f in zip(base, fixed) if not f)
    if total < lo and free:  # hold the shots longer, but never into a dead pause: a short hook stays short
        k = (lo - (total - free)) / free
        base = [b if f else min(b * k, b + STRETCH_MAX) for b, f in zip(base, fixed)]
    elif total > hi:  # tighten the holds, never cutting into a line
        spare = sum(b - fl for b, fl, f in zip(base, floor, fixed) if not f)
        cut = min(spare, total - hi)
        base = [b if f else b - (b - fl) * (cut / spare if spare else 0) for b, fl, f in zip(base, floor, fixed)]
    return [round(b, 3) for b in base]


def fill_defaults(shots: list[dict], grades: bool = False) -> None:
    """Shots whose grades or transitions were all left plain (a plain storyboard, an older script, a writer that
    skipped them) get them from their role, so the hook never runs in one colour with plain cuts. `grades`: no roles
    to go by (the Anim cold open): the colours rotate."""
    if shots and all(s.get("grade") in (None, "", "natural") for s in shots):
        for i, s in enumerate(shots):
            s["grade"] = (GRADE_CYCLE[i % len(GRADE_CYCLE)] if grades else
                          "noir" if s.get("flash") and i % 2 else BY_BEAT.get(s.get("beat", ""), "natural"))
    if shots and all(s.get("transition") in (None, "", "cut") for s in shots):
        for i, s in enumerate(shots):
            s["transition"] = ("punch" if i % 2 else "glitch") if s.get("flash") else CYCLE[i % len(CYCLE)]
    if shots:
        shots[0]["boom"] = True


# ---------- AI film stills ----------

def pictures(cfg, prompts: dict[int, str], work: Path, seed: int, title: str, progress: Progress,
             reuse: bool = False, look: str = CINE_LOOK) -> dict[int, Path]:
    """The hook's shots as AI film stills (the AI engine's keyframes stage, 1344x768), checked by Claude like the
    animated videos' pictures: a broken one is drawn once more from an easier prompt, and one still broken is left
    out (that shot shows its visual). {} when the engine isn't installed, is busy, or the setting is off."""
    from . import aimusic, anim_engine
    from .stopper import Paused

    prompts = {i: p.strip() for i, p in prompts.items() if p and p.strip()}
    if reuse:  # a re-make: the stills the video was made with (copied into work), nothing drawn or checked again
        try:
            gone = set(json.loads((work / "hook-pictures" / "check.json").read_text(encoding="utf-8")).get("dropped", []))
        except (OSError, ValueError):
            gone = set()
        return {i: p for i in prompts if f"h{i:02d}" not in gone
                and (p := work / "hook-pictures" / f"h{i:02d}.jpg").exists() and Path(str(p) + ".ok").exists()}
    if not prompts or not getattr(cfg, "hook_pictures", True) or not anim_engine.installed():
        return {}
    out_dir = work / "hook-pictures"
    out_dir.mkdir(parents=True, exist_ok=True)
    record_path = out_dir / "check.json"
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        record = {}
    fixes: dict[str, str] = record.get("fixes", {})
    dropped: set[str] = set(record.get("dropped", []))

    def job(ids: list[int]) -> dict:
        items = []
        for i in ids:
            key = f"h{i:02d}"
            again = key in fixes
            items.append({"id": key, "out": str(out_dir / f"{key}.jpg"), "seed": seed + 300 + i + (1000 if again else 0),
                          "prompt": f"{fixes.get(key, prompts[i])}, {look}"})
        from .animated import NEGATIVE
        return {"characters": [], "shots": items, "negative": NEGATIVE + PIC_NEGATIVE, "width": 1344, "height": 768, "steps": 4}

    def draw(ids: list[int], label: str) -> bool:
        try:
            anim_engine.run_stage("keyframes", job(ids), work, progress, label, wait=aimusic.BUSY_WAIT)
            return True
        except Paused:
            raise
        except Exception as exc:  # noqa: BLE001 - the hook falls back to its motion graphics
            log.warning("Hook pictures not drawn: %s", exc)
            progress(f"Hook pictures skipped ({str(exc)[:140]}); the hook uses motion graphics")
            return False

    ids = sorted(prompts)
    if not draw(ids, f"Drawing the hook's {len(ids)} film stills"):
        return {}
    if not record.get("checked"):
        broken = _check(cfg, {i: prompts[i] for i in ids}, out_dir, title, progress)
        if broken:
            for key, new in broken.items():
                fixes[key] = new
                for f in (out_dir / f"{key}.jpg", out_dir / f"{key}.jpg.ok"):
                    f.unlink(missing_ok=True)
            redo = [i for i in ids if f"h{i:02d}" in broken]
            progress(f"Redrawing {len(redo)} hook still(s) Claude found broken")
            if draw(redo, "Redrawing the hook's stills"):
                dropped |= set(_check(cfg, {i: fixes[f"h{i:02d}"] for i in redo}, out_dir, title, progress))
            else:
                dropped |= set(broken)
        record = {"checked": True, "fixes": fixes, "dropped": sorted(dropped)}
        record_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    made = {i: out_dir / f"h{i:02d}.jpg" for i in ids
            if f"h{i:02d}" not in dropped and (out_dir / f"h{i:02d}.jpg").exists()}
    if dropped:
        progress(f"{len(dropped)} hook still(s) still broken after a redraw: those shots use their motion graphics")
    return made


def _check(cfg, prompts: dict[int, str], out_dir: Path, title: str, progress: Progress) -> dict[str, str]:
    """{label: easier prompt} for the stills Claude finds broken; {} when all pass or the check can't run."""
    from .animated import PIC_SYSTEM, PicReview, _pic_sheets
    from .llm import ask
    from .stopper import Paused

    pics = [(f"h{i:02d}", out_dir / f"h{i:02d}.jpg") for i in sorted(prompts) if (out_dir / f"h{i:02d}.jpg").exists()]
    if not pics:
        return {}
    progress(f"Checking the hook's {len(pics)} stills for broken people and objects")
    try:
        sheets = _pic_sheets(pics, out_dir)
        prompt = (f"A documentary's cinematic cold open: {title}. Each still should look like a real film frame.\n"
                  + "\n".join(f"h{i:02d}: {prompts[i]}" for i in sorted(prompts))
                  + f"\n\n{len(sheets)} contact sheet(s) attached. Also flag any still with readable or fake writing, "
                    "or a recognisable face of a real person. List only the broken stills.")
        review = ask(cfg.ai_backend, cfg.fact_model, PIC_SYSTEM, prompt, PicReview, images=sheets, effort="low", timeout=900)
    except Paused:
        raise
    except Exception as exc:  # noqa: BLE001 - a check that can't run never stops the video
        log.warning("Hook still check failed: %s", exc)
        return {}
    known = {label for label, _ in pics}
    return {b.id: b.prompt.strip() for b in review.broken if b.id in known and b.prompt.strip()}


# ---------- sound ----------

def sound_design(shots: list[dict], end: float, work: Path, rel, files: dict[str, str], rehook: float | None = None,
                 template: str | None = None) -> tuple[list[dict], str | None]:
    """The hook's sounds as cues, and its drone: a sub boom on the first shot, on the boom shots and on the story's
    first word after the silence (`rehook`); the transition's own sound (whip, glitch, photo: whip + shutter, split:
    paper tear, punch: impact); a typewriter take per label; a boom on the shot after the climax montage. No riser
    anywhere: the user banned it. `end`: where the silence starts (the drone stops there).
    `files`: the video's other effect files by name (glitch, impact), relative."""
    sfx_dir = work / "sfx"
    hype = energetic(template)
    # An energetic template has no dark drone and no typed labels: a whoosh on every cut and a hit on every slam.
    typed = not hype or template == "bulletin"  # the bulletin's terminal types its words too
    made = synth.write_hook_sounds(sfx_dir, 0.0 if hype else end + 0.5, tuple(s.get("text", "") for s in shots) if typed else ())
    f = {k: rel(p) for k, p in made.items()}
    cues: list[dict] = []

    def cue(name: str, at: float, volume: float, full: bool = False) -> None:
        src = f.get(name) or files.get(name)
        if src and at < end + (5 if name == "hook-boom" else 0):
            c = {"src": src, "at": round(max(0.0, at), 3), "name": name, "volume": volume}
            if full:
                c["full"] = True
            cues.append(c)

    flash_runs: list[tuple[int, int]] = []
    i = 0
    while i < len(shots):
        if shots[i].get("flash"):
            j = i
            while j + 1 < len(shots) and shots[j + 1].get("flash"):
                j += 1
            flash_runs.append((i, j))
            i = j + 1
        else:
            i += 1
    for k, s in enumerate(shots):
        start = float(s["start"])
        boom = k == 0 or bool(s.get("boom"))
        if boom:
            cue("hook-boom", start, 0.95, full=True)
        if hype:
            if k:
                cue("hook-whip", start - 0.08, 0.55)
            if template in ("stakes", "myth") and s.get("text") and not boom:
                cue("impact", start + 0.05, 0.6)
            if s.get("stamp"):
                cue("impact", start + stamp_at(s), 0.85, full=True)
            if s.get("rewind"):
                cue("glitch", start, 0.6)
                cue("hook-whip", start + 0.35, 0.5)
            if template in ("mirror", "promise", "teaser") and s.get("text"):
                cue("pop", start + 0.12, 0.55)
            if template == "bulletin" and s.get("text"):
                cue(f"hook-type-{len(s['text'])}", start + 0.1, 0.5)
                if s.get("kicker"):
                    cue("glitch", start + 0.1 + 0.045 * len(s["text"]) + 0.15, 0.45)
            if template == "frontpage":
                cue("hook-whip", start + (0.15 if k == 0 else -0.05), 0.6)  # the page spins in, the next slides over
            continue
        kind = s.get("transition") or "cut"
        hit = 1.45 if s.get("flash") else 1.0  # the montage is the climax: its cuts hit harder
        if kind == "whip":
            cue("hook-whip", start - 0.1, 0.6 * hit)
        elif kind == "glitch":
            cue("glitch", start, 0.45 * hit)
        elif kind == "photo":
            cue("hook-whip", start, 0.35)
            cue("hook-shutter", start + PHOTO_LAND, 0.6)
        elif kind == "split":
            cue("hook-tear", start, 0.6)
        elif kind == "punch" and not boom:
            cue("impact", start, 0.5 * hit)
        if s.get("text"):
            cue(f"hook-type-{len(s['text'])}", start + LABEL_AT, 0.5)
    for a, b in flash_runs:  # the montage lands on the shot after it
        after = float(shots[b]["start"]) + float(shots[b]["duration"])
        if b + 1 < len(shots) and not shots[b + 1].get("boom"):
            cue("hook-boom", after, 0.9, full=True)
    if rehook is not None:
        cue("hook-boom", rehook, 0.85, full=True)
    return cues, f.get("hook-drone")


def opening_boom(sfx_dir: Path, rel, at: float, volume: float = 0.85) -> dict:
    """The deep boom under a video's first word (Shorts, Toon, the Shorts Studio, a long video without a hook): the
    reference's first second. A cue dict (rel: path -> the props' relative path), never halved under the voice."""
    path = sfx_dir / "hook-boom.wav"
    if not path.exists():
        sfx_dir.mkdir(parents=True, exist_ok=True)
        synth._write(path, synth._sub_boom(), peak=synth.HOOK_SOUNDS["hook-boom"][1])
    return {"src": rel(path), "at": round(max(0.0, at), 3), "name": "hook-boom", "volume": volume, "full": True}
