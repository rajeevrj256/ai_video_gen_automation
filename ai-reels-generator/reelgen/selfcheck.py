"""A few seconds' check of the code every video runs through, before each commit:

    .venv/bin/python -m reelgen.selfcheck      (Windows: .venv\\Scripts\\python -m reelgen.selfcheck)

1. every module imports;
2. no module defines the same top-level name twice: a prompt named DEVANAGARI replaced the regex of the same name in
   hinglish.py, and every Hinglish video then failed at its voice with "'str' object has no attribute 'findall'";
3. the shared text functions answer as they should (Hinglish detection, word matching, script cutting, word repair),
   and Update & restart's helper never ends itself and finds the old window.
No network, no Claude, no models. Exits 1 and says what broke.
"""

from __future__ import annotations

import ast
import collections
import importlib
import pkgutil
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILS: list[str] = []


def fail(what: str) -> None:
    FAILS.append(what)
    print("FAIL", what)


def imports() -> None:
    import reelgen

    for mod in pkgutil.iter_modules(reelgen.__path__):
        if mod.name in ("__main__", "selfcheck", "updater"):
            continue
        try:
            importlib.import_module(f"reelgen.{mod.name}")
        except Exception as exc:  # noqa: BLE001
            fail(f"import reelgen.{mod.name}: {type(exc).__name__}: {exc}")


def duplicate_names() -> None:
    files = [*sorted((ROOT / "reelgen").glob("*.py")), *sorted((ROOT / "voice_worker").glob("*.py")),
             *sorted((ROOT / "anim_worker").glob("*.py"))]
    for f in files:
        seen: dict[str, list[int]] = collections.defaultdict(list)
        for node in ast.parse(f.read_text(encoding="utf-8")).body:
            names = []
            if isinstance(node, ast.Assign):
                names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names = [node.target.id]
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names = [node.name]
            for n in names:
                seen[n].append(node.lineno)
        for name, lines in seen.items():
            if len(lines) > 1 and name not in ("log", "__all__"):
                fail(f"{f.relative_to(ROOT)}: '{name}' is defined twice (lines {lines}); the second replaces the first")


SCRIPT = """## Shuruaat
Microsoft ne is saal 1,400 se zyada flaws fix kiye. Kya aapka PC safe hai? Chaliye dekhte hain kaise.

## Patch kya hai
Pehle samjhiye patch kya hota hai."""
SCRIPT_WORDS = [w for line in SCRIPT.splitlines() if line and not line.startswith("##") for w in line.split()]
HOOK = "Microsoft ne 1,400 flaws fix kiye. Lekin sawaal hai... kya aapka PC ab bhi khatre mein hai?"


def behaviour() -> None:
    from . import hinglish, scriptvideo, shoot, stickstory, wordfix
    from .numbers import speakable, speakable_for
    from .voice import Word

    hinglish_line = ["Aaj hum baat karenge ki Microsoft ne 1,400 se zyada security flaws kaise fix kiye aur aapka PC kitna safe hai"]
    english_line = ["Microsoft fixed more than fourteen hundred security flaws this year, and here is what that means for you"]
    checks = [
        ("hinglish.needs_mixing(Hinglish, Madhur)", lambda: hinglish.needs_mixing("hi-IN-MadhurNeural", hinglish_line), True),
        ("hinglish.needs_mixing(English, Andrew)", lambda: hinglish.needs_mixing("en-US-AndrewMultilingualNeural", english_line), False),
        ("hinglish.looks_hinglish", lambda: hinglish.looks_hinglish(hinglish_line), True),
        ("shoot.skeleton('commands') == skeleton('कमान्ट्स')", lambda: shoot.skeleton("commands") == shoot.skeleton("कमान्ट्स"), True),
        ("shoot.alike(future, फुछर) > 0", lambda: shoot.alike(shoot.skeleton("future"), shoot.skeleton("फुछर")) > 0, True),
        ("wordfix.misheard(2024 / 2023)", lambda: wordfix.misheard(["2024"], [Word("2023", 0, 0)]), False),
        ("wordfix.misheard(already / पल्रदी)", lambda: wordfix.misheard(["already"], [Word("पल्रदी", 0, 0)]), True),
        ("scriptvideo.parse_script keeps every word and the chapters", lambda: (
            " ".join(scriptvideo.parse_script(SCRIPT)[0]).split(), [t for _, t in scriptvideo.parse_script(SCRIPT)[1]]),
         (SCRIPT_WORDS, ["Shuruaat", "Patch kya hai"])),
        ("scriptvideo.parse_script: '## heading' straight above its lines is a chapter, never narration", lambda:
            scriptvideo.parse_script("## One\nFirst line here.\n## Two\nSecond line,\nwrapped here.\n\nChapter 3: Three\nThird."),
         (["First line here.", "Second line, wrapped here.", "Third."], [(0, "One"), (1, "Two"), (2, "Three")])),
        ("stickstory.parse_stick_script: 'Narrator:' alone is a label, not a line", lambda: [
            (b["speaker"], b["line"]) for b in stickstory.parse_stick_script(
                "Narrator:\nThey met in 2005.\n\n**Ben:**\nWait.\n\nHere is what happened:\nIt grew.\n"
                "Narrator (V.O.): Google bought it.\nIn 2005: nothing.")],
         [("narrator", "They met in 2005."), ("Ben", "Wait."), ("narrator", "Here is what happened:"),
          ("narrator", "It grew."), ("narrator", "Google bought it."), ("narrator", "In 2005: nothing.")]),
        ("numbers.speakable_for (Sarvam lines: numbers in the line's language)", lambda: [
            speakable_for("Spent ₹5,000 for a ₹200 reward."), speakable_for("मैंने ₹1,25,000 खर्च किए, 18% ज़्यादा")],
         ["Spent five thousand rupees for a two hundred rupees reward.",
          "मैंने एक लाख पच्चीस हज़ार रुपये खर्च किए, अठारह प्रतिशत ज़्यादा"]),
        ("scriptvideo.parse_hook keeps every word", lambda: " ".join(scriptvideo.parse_hook(HOOK)).split() == HOOK.split(), True),
        ("numbers.speakable (English voices read numbers in English)", lambda: speakable(
            "1 lakh in 2024, ₹2.5 crore, 1,00,000 and 18% at 7:30 in the 1990s; 5G and COVID-19 stay."),
         "one lakh in twenty twenty-four, two point five crore rupees, one lakh and eighteen percent at seven thirty "
         "in the nineteen nineties; 5G and COVID-nineteen stay."),
    ]
    for name, fn, want in checks:
        try:
            got = fn()
        except Exception:  # noqa: BLE001
            fail(f"{name} raised:\n{traceback.format_exc(limit=3)}")
            continue
        if got != want:
            fail(f"{name}: got {got!r}, expected {want!r}")
    lines = ["Scientists already human brain signals ko computer commands mein convert karne par kaam kar rahe hain."]
    said = "Scientists already human brain signals ko commands mein convert karne par kaam kar rahe hain.".split()
    heard = [Word(w, i * 0.4, i * 0.4 + 0.3) for i, w in enumerate(said)]
    try:
        gaps = wordfix.gaps(lines, heard)
        if [(g["text"], g["kind"]) for g in gaps] != [("computer", "skipped")]:
            fail(f"wordfix.gaps on a skipped word: {[(g['text'], g['kind']) for g in gaps]}")
        rows = shoot.align(lines, heard, heard[-1].end + 0.5)
        if not 0.9 <= rows[0]["matched"] < 1:
            fail(f"shoot.align matched {rows[0]['matched']} with one word skipped")
    except Exception:  # noqa: BLE001
        fail(f"word repair checks raised:\n{traceback.format_exc(limit=3)}")


def update_helper() -> None:
    """Update & restart on Windows: window cmd.exe → .venv launcher → app → launcher → helper. The helper once ended
    its own launcher (a child of the old app) and with it itself, so nothing restarted."""
    from . import updater

    table = {10: (1, "explorer.exe"), 20: (10, "cmd.exe"), 30: (20, "python.exe"), 40: (30, "python.exe"),
             50: (40, "python.exe"), 60: (50, "python.exe"), 70: (40, "cloudflared.exe"), 80: (40, "node.exe")}
    mine = {60, *updater._chain(60, table)}
    got = (updater._window(40, table), sorted(updater._children(40, table, mine)))
    if got != (([30], 20), [70, 80]):
        fail(f"updater: window/children of the old app {got}, expected (([30], 20), [70, 80])")


def meme_lists() -> None:
    """The meme formats and faces the writer is offered (memes.py) are the ones the editor draws (types.ts)."""
    import re

    from . import memes
    from .longform import LVisual

    ts = (ROOT / "remotion" / "src" / "long" / "types.ts").read_text(encoding="utf-8")
    for name, ours in (("MemeFormat", set(memes.FORMATS)), ("MemeFace", set(memes.FACES))):
        block = re.search(rf"export type {name} =(.*?);", ts, re.S)
        theirs = set(re.findall(r"'([a-z-]+)'", block.group(1))) if block else set()
        if ours != theirs:
            fail(f"memes.py and types.ts {name} differ: only in Python {sorted(ours - theirs)}, only in the editor {sorted(theirs - ours)}")
    from . import memeweb

    page = ('memes=[{"id":181913649,"uid":27,"name":"Drake Hotline Bling","w":1200,"h":1200,"file_type":"jpg",'
            '"default_settings":"[{\\"type\\":\\"text\\",\\"x\\":612,\\"y\\":12,\\"w\\":576,\\"h\\":576}]"}];')
    found = memeweb._templates_on(page)
    if [b["x"] for b in memeweb.boxes(found.get(181913649, {"w": 1, "h": 1}))] != [0.51]:
        fail(f"memeweb: an Imgflip page's template boxes not read: {found}")
    if not memeweb.blocked("Bernie I Am Once Again Asking For Your Support") or memeweb.blocked("Drake Hotline Bling"):
        fail("memeweb.blocked: politicians must be left out, Drake kept")
    if memeweb.base36(181913649) != "30b1gx":
        fail("memeweb.base36: Drake's picture is i.imgflip.com/30b1gx.jpg")
    v = LVisual(type="meme", headline="", sub="", items=[], icons=[], meme="nope-yep", labels=["a", "b", "c", " "])
    memes.repair(v)
    if v.labels != ["a", "b"]:
        fail(f"memes.repair kept {v.labels} for a 2-label format")


def hook_templates() -> None:
    """The hook templates are the same in Python (cinehook.TEMPLATES), the page (HOOK_TPL) and the editor (types.ts);
    shift_props moves the story and keeps the new hook."""
    import re

    from . import cinehook, rehook

    ours = set(cinehook.TEMPLATES)
    page = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    block = re.search(r"const HOOK_TPL = \{(.*?)\n\};", page, re.S)
    theirs = set(re.findall(r"^\s+([a-z]+): \[", block.group(1), re.M)) if block else set()
    if ours != theirs:
        fail(f"hook templates differ: cinehook {sorted(ours)}, web/index.html HOOK_TPL {sorted(theirs)}")
    ts = (ROOT / "remotion" / "src" / "long" / "types.ts").read_text(encoding="utf-8")
    m = re.search(r"template\?: ('cinematic'[^;]+);", ts)  # the hook's (Look has its own 'template')
    if not m or set(re.findall(r"'([a-z]+)'", m.group(1))) != ours:
        fail("hook templates differ between cinehook.TEMPLATES and types.ts Hook.template")
    old = {"duration": 30.0, "hook": {"duration": 10.0, "shots": []}, "musicFrom": 10.0,
           "chapters": [{"start": 10.0, "end": 20.0}], "beats": [{"start": 10.5}], "musicParts": [], "ambience": [],
           "cues": [{"at": 2.0, "src": "a"}, {"at": 12.0, "src": "b"}], "speech": [[3.0, 4.0], [11.0, 12.0]],
           "captions": [], "all_captions": [{"start": 11.0, "end": 12.0, "words": [{"start": 11.0, "end": 11.5}]}]}
    new = rehook.shift_props(old, {"duration": 7.0}, {"cues": [{"at": 1.0}], "speech": [[1.0, 2.0]], "captions": []}, -3.0)
    if (new["duration"], new["beats"][0]["start"], [c["at"] for c in new["cues"]], new["all_captions"][0]["start"]) != (
            27.0, 7.5, [9.0, 1.0], 8.0):
        fail(f"rehook.shift_props: the story didn't move with the new hook: {new}")


def visual_templates() -> None:
    """The visual templates are the same in Python (briefing.TEMPLATES), the page (VIZ_TPL) and the editor's Look;
    the Briefing layouts are in the writer's schema and in types.ts VisualType."""
    import re

    from . import briefing
    from .longform import LVisual

    page = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    block = re.search(r"const VIZ_TPL = \{(.*?)\n\};", page, re.S)
    if not block or set(re.findall(r"^\s+([a-z]+): \[", block.group(1), re.M)) != set(briefing.TEMPLATES):
        fail("visual templates differ: briefing.TEMPLATES and web/index.html VIZ_TPL")
    ts = (ROOT / "remotion" / "src" / "long" / "types.ts").read_text(encoding="utf-8")
    m = re.search(r"template\?: ('classic'[^;]+);", ts)
    if not m or set(re.findall(r"'([a-z]+)'", m.group(1))) != set(briefing.TEMPLATES):
        fail("visual templates differ between briefing.TEMPLATES and types.ts Look.template")
    allowed = set(LVisual.model_fields["type"].annotation.__args__)
    missing = [t for t in briefing.BRIEFING_TYPES if t not in allowed or f"| '{t}'" not in ts]
    if missing:
        fail(f"Briefing layouts missing from LVisual.type or types.ts VisualType: {missing}")


def main() -> int:
    sys.path.insert(0, str(ROOT))
    imports()
    duplicate_names()
    behaviour()
    update_helper()
    meme_lists()
    hook_templates()
    visual_templates()
    print("selfcheck:", "OK" if not FAILS else f"{len(FAILS)} problem(s)")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
