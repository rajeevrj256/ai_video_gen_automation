"""Memes that make a concept land, and the funny-explainer way of writing that goes with them (the user: "add option
to add memes on video for making funny to explain concepts", after an 18-minute Hinglish economics explainer that
explains every idea with an everyday example and a meme: opportunity cost as a sweating guy between two red buttons
labelled NETFLIX BINGE and CAREER/STUDY).

Setting `memes` (Settings > Content, and per video on the Create page, the Script tab and Shorts+): off / some / lots.
On, the long writer explains like a funny friend (everyday examples, a recurring everyday character, jokes that never
bend a fact) and uses 'meme' visuals; the storyboards of Script Videos, Shoot and Shorts+ graphics (whose words are
final) only add the memes. Every meme is drawn by the editor (remotion/src/long/Meme.tsx: the classic formats redrawn
with flat cartoon people, nothing copied from a meme picture or a real person), or is one of the user's own meme files
(Settings > Media library > Memes) with top and bottom text. The reference video used photos of real people and film
stills, and opened with a copyright disclaimer; this never does.

FORMATS and FACES are mirrored in remotion/src/long/types.ts (MemeFormat, MemeFace): keep the lists in step.
"""

from __future__ import annotations

import re

from .config import Config

LEVELS = ("off", "some", "lots")
EVERY = {"some": 8, "lots": 4}  # about one meme in N beats
HOOK = {"some": 1, "lots": 2}  # memes in the cinematic hook (the user: "why memes not inside the hooks???")
MOST = {"some": 6, "lots": 3}  # never more than one in N (checked)
LABEL_WORDS = 8

# format: (what each label is, in order; when the format fits)
FORMATS: dict[str, tuple[tuple[str, ...], str]] = {
    "two-buttons": (("left button", "right button"),
                    "a sweating person between two big red buttons: a hard choice, a trade-off, opportunity cost"),
    "nope-yep": (("the option refused", "the option preferred"),
                 "a person pushing one option away and pointing happily at the other: the smarter choice, the better deal"),
    "distracted": (("the new temptation", "who gets distracted", "what they already have"),
                   "someone turning to look at something new while what they already have glares: switching, new trends, "
                   "imports vs local; set icons[0] to a Lucide icon for the temptation when it's a thing"),
    "brain": (("basic idea", "smarter", "smarter still", "enlightened (or ironic)"),
              "3-4 rows from a dim brain to a glowing one: levels of understanding one idea"),
    "this-is-fine": (("the situation", "what they say (empty: 'This is fine.')"),
                     "someone calmly sipping tea in a room on fire: ignoring an obvious problem"),
    "panik-kalm": (("the scare", "the reason to relax", "the twist that brings the panic back"),
                   "panic, calm, panic again: a scare, a reassurance, then the catch"),
    "expectation-reality": (("the expectation", "the reality"),
                            "a happy panel and a rainy, crying one: what people expect vs what really happens"),
    "nobody-me": (("what I do (without 'Me:')", "the first line (empty: 'Nobody:')"),
                  "'Nobody: / Me: ...' with a person laughing: doing something nobody asked for"),
    "stonks": (("what went up",), "a proud man in a suit before a rising chart: something that paid off"),
    "not-stonks": (("what went down",), "the same man before a falling chart: something that lost value or backfired"),
    "change-my-mind": (("the bold opinion",), "a person at a table with a sign: a bold, debatable claim the video then tests"),
    "plan": (("step 1", "step 2", "step 3: the flaw"),
             "a presenter at a flip chart, 4 panels, shocked at the last (step 3 shown twice): a plan that backfires"),
    "pointing": (("one side", "the other side"), "two identical people pointing at each other: two sides blaming each other, "
                 "or two things that are really the same"),
    "starter-pack": (("the group or situation", "item 1", "item 2", "item 3", "item 4"),
                     "a title and 4 tiles: the typical things of a group or situation; icons: one Lucide icon per item"),
    "reaction": (("top text: the setup", "bottom text: the punchline"),
                 "a big cartoon face (set face) with classic top and bottom text: shock at a number, crying at a price, "
                 "side-eye at a claim, mind blown by a fact"),
}
FACES = ("shocked", "crying", "laughing", "side-eye", "smug", "sweating", "mind-blown", "confused", "angry", "deadpan")


def level(cfg: Config) -> str:
    v = (getattr(cfg, "memes", "off") or "off").lower()
    return v if v in LEVELS else "off"


def own_files(cfg: Config) -> list:
    """The user's meme pictures and clips (Settings > Media library > Memes), licence set and not banned."""
    from . import media

    return media._files(cfg, "memes")


def catalogue() -> str:
    return "\n".join(f"  - {k}: {about}. labels: {' | '.join(slots)}" for k, (slots, about) in FORMATS.items())


def _hook_count(memes: str) -> str:
    return "exactly one" if HOOK[memes] == 1 else f"one or {HOOK[memes]}"


def visual_rules(memes: str, files: list | None = None, web: str = "") -> str:
    """For every writer and storyboard (inside the long writer's visual rules): when and how to use a meme."""
    if memes not in EVERY:
        return ""
    own = ""
    if files:
        own = ("\n- The user's own meme files (set 'file' to the name; the drawn format is then ignored, the labels become "
               "its top and bottom text): " + ", ".join(f.name for f in files) + ". Use one only where its name fits the "
               "line exactly.")
    return f"""- Memes (the user turned them on: {memes}): about one beat in {EVERY[memes]} is a 'meme' that makes that \
line's concept land, never two in a row and never more than one in {MOST[memes]}. The meme's format IS the shape of the \
idea: a trade-off is two-buttons, a better choice is nope-yep, a plan that backfires is plan, levels of understanding \
are brain. Set 'meme' to the format, 'labels' to its words in the format's order (each at most {LABEL_WORDS} words, \
in the words of this video, the punchline short), 'face' for a reaction. The line before sets it up and the meme \
pays it off; never a random meme, never on a sad or serious moment (a death, a disaster, poverty, illness). Labels \
state no figure or fact the narration doesn't. In the cold open (the hook's shots), when there is one: \
{_hook_count(memes)} hook shot{'' if HOOK[memes] == 1 else 's'} with a line {'is' if HOOK[memes] == 1 else 'are'} a meme too \
(a 'meme' visual, 'picture' empty, grade natural), whatever the hook's template: the funny jolt that makes the \
stakes relatable before the next beat; never a flash shot, never the first or the last shot (the big question). Formats:
{catalogue()}
  Faces (reaction): {', '.join(FACES)}.{own}{web}"""


def writing_rules(memes: str) -> str:
    """For writers who write the words (long videos): explain like a funny, sharp friend."""
    if memes not in EVERY:
        return ""
    return f"""Humour (the user turned memes on: {memes}): explain like a sharp, funny friend, not a lecturer.
- Every concept gets an everyday example the viewer has lived before (or instead of) the textbook definition: exams, \
a phone bill, a salary that's gone by the 10th, Netflix instead of studying, onion prices, a cricket match, a wedding \
buffet, an EMI. One recurring everyday character can carry the examples (a common first name and a situation, e.g. a \
student choosing what to do with ₹500); never a real person.
- Jokes come from the subject itself: the absurd consequence, the relatable struggle, expectation vs reality. Punch \
up, never down: no jokes about religion, caste, region, gender, bodies, poverty, tragedies, or any real person or politician.
- A joke never bends a fact: figures, dates and claims stay exact and sourced; an exaggeration is plainly a joke.
- Keep the pace: a joke is one short line, then the explanation moves on."""


def repair(v) -> None:
    """Fix a meme visual in code (an LVisual): an unknown format becomes a reaction, extra labels go, a reaction gets
    a face; a meme without words becomes a reaction of its headline, or an icon."""
    if v.type != "meme":
        return
    v.labels = [re.sub(r"\s+", " ", t).strip() for t in v.labels if t and t.strip()]
    if v.meme not in FORMATS:
        v.meme = "reaction"
    slots = len(FORMATS[v.meme][0])
    if len(v.labels) > slots:
        v.labels = v.labels[:slots]
    v.labels = [" ".join(t.split()[:LABEL_WORDS + 2]) for t in v.labels]
    if v.meme == "reaction" and v.face not in FACES:
        v.face = "shocked"
    if not v.labels and not v.file:
        if v.headline or v.sub:
            v.labels = [x for x in (v.headline, v.sub) if x]
            v.meme, v.face = "reaction", v.face if v.face in FACES else "shocked"
        else:  # nothing to say: an icon, never words of our own
            v.type, v.icons = "icons", ["laugh"]


def text(v) -> str:
    """A meme's words for the fact-checker."""
    return f"[meme {getattr(v, 'web_meme', '') or v.file or v.meme}: " + " | ".join(v.labels) + "]"


def issues(visuals: list, memes: str) -> list[str]:
    """Rule breaks worth a fix: memes back to back, or too many of them."""
    flags = [v.type == "meme" for v in visuals]
    out = []
    if any(a and b for a, b in zip(flags, flags[1:])):
        out.append("Two memes in a row; put an evidence visual between them.")
    most = MOST.get(memes, 3)
    if flags and sum(flags) > len(flags) / most + 1:
        out.append(f"{sum(flags)} of {len(flags)} beats are memes; at most one in {most}.")
    return out
