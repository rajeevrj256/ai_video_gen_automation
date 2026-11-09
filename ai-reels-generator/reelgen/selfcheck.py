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


def lowpoly_lists() -> None:
    """The low-poly writer offers exactly what the editor draws (story.py Literals = lowpoly/types.ts unions), every
    set's spots exist in Sets.tsx, and the hero is the same man in Python and in the editor."""
    import re
    import typing

    from .lowpoly import story as S
    from .lowpoly.timeline import chunks

    ts = (ROOT / "remotion" / "src" / "lowpoly" / "types.ts").read_text(encoding="utf-8")
    for ts_name, py in (("SetName", S.SetName), ("Light", S.LightName), ("Cam", S.CamName), ("Action", S.ActionName),
                        ("Expr", S.ExprName), ("Spot", S.SpotName), ("Hold", S.HoldName)):
        block = re.search(rf"export type {ts_name} =(.*?);", ts, re.S)
        theirs = set(re.findall(r"'([a-z-]+)'", block.group(1))) if block else set()
        ours = set(typing.get_args(py))
        if ours != theirs:
            fail(f"lowpoly {ts_name}: only in story.py {sorted(ours - theirs)}, only in types.ts {sorted(theirs - ours)}")
    things = re.search(r"kind: ('phone'[^;]+);", ts)
    if not things or set(re.findall(r"'([a-z]+)'", things.group(1))) != set(typing.get_args(S.ThingName)):
        fail("lowpoly Thing kinds differ between story.py ThingName and types.ts")
    sets_ts = (ROOT / "remotion" / "src" / "lowpoly" / "Sets.tsx").read_text(encoding="utf-8")
    for name, spots in S.SPOTS.items():
        var = {"void": "voidSet", "sky": "skySet"}.get(name, name)
        body = re.search(rf"const {var}: SetDef = \{{(.*?)\n  wide:", sets_ts, re.S)
        drawn = set(re.findall(r"(\w+): \{x:", body.group(1))) if body else set()
        if spots != drawn:
            fail(f"lowpoly set {name}: story.SPOTS {sorted(spots)} but Sets.tsx has {sorted(drawn)}")
    man = (ROOT / "remotion" / "src" / "lowpoly" / "Man.tsx").read_text(encoding="utf-8")
    for key in ("skin", "hair", "top", "trousers"):
        if f"{key}: '{S.HERO[key]}'" not in man:
            fail(f"lowpoly hero: {key} {S.HERO[key]} in story.HERO is not the editor's HERO")
    got = [c[2] for c in chunks([("He", 0, .2), ("pictures", .2, .6), ("a", .6, .7), ("5:30", .7, 1.1), ("run.", 1.1, 1.4),
                                 ("Tomorrow,", 1.6, 2.0), ("for", 2.0, 2.1), ("real.", 2.1, 2.5)])]
    if got != ["He pictures a", "5:30 run.", "Tomorrow, for", "real."] and got != ["He pictures a", "5:30 run.", "Tomorrow,", "for real."]:
        fail(f"lowpoly captions: {got}")
    from .lowpoly.timeline import build
    shot = dict(set="bedroom", light="night", camera="face", actors=[S.LPActor(who="hero", action="lie", expression="tired", spot="bed")])
    story = S.Story(title="t", problem="p", youtube_title="t", description="d", tags=[], hashtags=[], thumbnail_text="t", mood="calm",
                    end_mood="calm", music_prompt="m", shots=[S.LPShot(stamp="11:47 P.M.", line="He sets the alarm.", **shot),
                                                              S.LPShot(line="He means it.", red=True, **shot)])
    audio = {0: {"path": "a.wav", "seconds": 1.2, "words": [["He", 0, .2], ["sets", .2, .5], ["the", .5, .6], ["alarm", .6, 1.0]]},
             1: {"path": "b.wav", "seconds": 0.8, "words": [["He", 0, .2], ["means", .2, .5], ["it", .5, .7]]}}
    seen = {w: [c["text"] for c in build(story, audio, vertical=True, watermark="", seed=1, words=w)[0]["captions"]] for w in ("on", "stamps", "off")}
    if not (len(seen["on"]) >= 3 and seen["stamps"] == ["11:47 P.M."] and seen["off"] == []):
        fail(f"lowpoly words on screen (on / time stamps only / off): {seen}")
    # fiction: the big things and effects are the editor's own, a power move brings its effects and sounds, the
    # speaker's mouth moves on their words, the score follows the story, and nobody shares a voice
    for ts_name, py in (("BigKind", S.BigName), ("BigMotion", S.MotionName), ("FxKind", S.FxName)):
        block = re.search(rf"export type {ts_name} =(.*?);", ts, re.S)
        theirs = set(re.findall(r"'([a-z-]+)'", re.sub(r"//[^\n]*", "", block.group(1)))) if block else set()
        if set(typing.get_args(py)) != theirs:
            fail(f"lowpoly {ts_name}: story.py {sorted(typing.get_args(py))} but types.ts {sorted(theirs)}")
    block = re.search(r"export type MoveRole =(.*?);", ts, re.S)
    theirs = set(re.findall(r"'([a-z_]+)'", block.group(1))) if block else set()
    if set(typing.get_args(S.MOVES)) - {""} != theirs:
        fail(f"lowpoly MoveRole: story.py {sorted(typing.get_args(S.MOVES))} but types.ts {sorted(theirs)}")
    # the user's own shot-by-shot script (their dinosaur film came out with the man in every shot): sections and lines
    # read word for word, the lines put back if the writer changed them, no man in a film without people, a creature
    # named as an actor left out, a flying creature with no canopy over it
    sample = ("# WHAT IF?\n### 0–6 SEC — THE HOOK\n**Visual:** A T-Rex roars in a jungle.\n**Narrator:**\n\"Dinosaurs ruled Earth "
              "for 165 million years... but what if the asteroid never hit?\"\n### 55–60 SEC — ENDING\n**Visual:** An egg hatches.\n"
              "**Narrator (whispering):**\n\"Maybe it was never over.\"\n**CUT TO BLACK.**\nTEXT: WOULD YOU SURVIVE?")
    secs = S.parse_script(sample)
    lines = S.script_lines(secs or [])
    if not secs or lines != ["Dinosaurs ruled Earth for 165 million years...", "but what if the asteroid never hit?", "Maybe it was never over."] \
            or secs[-1]["text"] != ["WOULD YOU SURVIVE?"] or not secs[-1]["black"] or S.parse_script("A man forgets his keys.") is not None:
        fail(f"lowpoly script: not read section by section: {secs}")
    rex = S.LPMade(name="T-Rex", what="a dinosaur", travel="legs", parts=[
        S.LPPart(shape="sphere", at=[0, 3, 0], size=[2, 2, 5], color="#556b2f"),
        S.LPPart(shape="box", at=[0, 4, 3], size=[1, 1, 2], color="#556b2f", move="head")])
    bird = S.LPMade(name="Pterosaur", what="a flying reptile", travel="air", parts=[
        S.LPPart(shape="sphere", at=[0, 0.6, 0], size=[0.6, 0.6, 1.6], color="#8a6a4a"),
        S.LPPart(shape="box", at=[2, 0.6, 0], size=[4, 0.06, 1.2], color="#c09a6a", move="wing_l")])
    dino = S.Story(title="t", problem="p", youtube_title="y", description="d", tags=[], hashtags=[], thumbnail_text="t", mood="mystery",
                   end_mood="dark", music_prompt="m", made=[rex, bird], kind="fiction", hero=False, shots=[
                       S.LPShot(line="Dinosaurs ruled Earth for 165 million years", set="jungle", light="day", camera="low",
                                actors=[S.LPActor(who="T-Rex", action="stand", expression="neutral", spot="center")],
                                big=[S.LPBig(kind="made", made="T-Rex", motion="roar")]),
                       S.LPShot(line="what if it never hit", set="jungle", light="day", camera="wide", actors=[]),
                       S.LPShot(line="", set="cave", light="dark", camera="wide", actors=[], stamp="WOULD YOU SURVIVE?")])
    dino.shots[1].overgrown = "ruined"  # a jungle isn't a city: nothing to overgrow
    S.keep_script_lines(dino, lines)
    S.repair(dino)
    if dino.shots[1].overgrown:
        fail("lowpoly: 'overgrown' kept on a place that isn't the city's")
    if [x.line for x in dino.shots if x.line] != lines or any(x.actors for x in dino.shots) or dino.shots[0].big[0].motion != "roar":
        fail(f"lowpoly creature film: {[(x.line, [a.who for a in x.actors], [b.motion for b in x.big]) for x in dino.shots]}")
    if any(p.get("glass") for p in S.design_for_editor(bird)["parts"]) or S.design_for_editor(bird)["seats"] \
            or S.design_for_editor(rex)["parts"][1].get("move") != "head":
        fail("lowpoly creatures: a flying creature got a cockpit, or a moving part lost its role")
    from .lowpoly.sounds import MAKERS
    from .lowpoly.timeline import ACTION_SOUNDS, FX_SOUNDS, MOTION_SOUNDS
    wanted = {x for v in list(ACTION_SOUNDS.values()) + list(MOTION_SOUNDS.values()) for x, _ in v} | set(FX_SOUNDS.values())
    wanted |= set(typing.get_args(S.SoundName))
    if wanted - set(MAKERS):
        fail(f"lowpoly sounds with no maker: {sorted(wanted - set(MAKERS))}")
    page = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    for key, field in (("skin", "skin"), ("hair", "hair"), ("hair_style", "hair_style"), ("top", "top"), ("top_kind", "top_kind"),
                       ("trousers", "trousers"), ("hat", "hat")):
        m = re.search(rf"\n  {key}: \[([^\]]*)\]", page)
        got = set(re.findall(r'"([a-z-]+)"', m.group(1))) if m else set()
        if got != set(typing.get_args(S.LPDesign.model_fields[field].annotation)):
            fail(f"lowpoly tab LP_LOOK.{key} differs from story.LPDesign.{field}")
    for c in S.CAST_LIBRARY:
        S.LPCast(name=c["name"], who=c["who"], design=S.LPDesign(**c["design"]), voice=c["voice"])
    hero = S.LPActor(who="hero", action="catch", expression="determined", spot="center")
    sara = S.LPCast(name="Sara", who="a worker", design=S.LPDesign(hat="hardhat"), voice="young-woman")
    dana = S.LPCast(name="Dana", who="a friend", design=S.LPDesign(), voice="young-woman")
    fic = S.Story(title="t", problem="p", youtube_title="t", description="d", tags=[], hashtags=[], thumbnail_text="t", mood="calm",
                  end_mood="calm", music_prompt="m", kind="fiction", cast=[sara, dana],
                  score=[S.ScorePart(from_shot=1, mood="calm", energy="low"), S.ScorePart(from_shot=2, mood="suspense", energy="high")],
                  shots=[S.LPShot(line="Watch out!", speaker="Sara", set="construction", light="day", camera="wide",
                                  actors=[hero, S.LPActor(who="Sara", action="cower", expression="scared", spot="left")],
                                  big=[S.LPBig(kind="beam", spot="center", motion="caught", at=0.5)]),
                         S.LPShot(line="", set="alley", light="night", camera="low", pause=1.5,
                                  actors=[S.LPActor(who="hero", action="land", expression="angry", spot="center")])])
    S.repair(fic)
    props, _, cues, sections = build(fic, {0: {"path": "a.wav", "seconds": 0.9, "words": [["Watch", 0, .3], ["out!", .35, .8]]}},
                                     vertical=False, watermark="", seed=1)
    sh = props["shots"]
    if not (sh[0]["actors"][1].get("talk") and sh[0]["actors"][0].get("at") == sh[0]["big"][0].get("at")):
        fail(f"lowpoly fiction: talk spans or the catch's moment are wrong: {sh[0]['actors']} {sh[0].get('big')}")
    if not {"shockwave", "crack", "dust", "shake"} <= {f["kind"] for f in sh[1].get("fx", [])}:
        fail(f"lowpoly fiction: a landing didn't bring its effects: {sh[1].get('fx')}")
    if not {"impact"} <= {c["sound"] for c in cues} or len(sections) != 2:
        fail(f"lowpoly fiction: sounds {sorted({c['sound'] for c in cues})} / sections {len(sections)}")
    vs = S.voices_for(fic, "en-US-ChristopherNeural")
    if len(set(vs.values())) != len(vs):
        fail(f"lowpoly voices shared: {vs}")
    # footsteps land when the feet do: the strides and speeds are the walk cycles' own (poses.ts, LowPoly.tsx)
    from .lowpoly.timeline import SLOW, SPEED, STRIDE
    poses = (ROOT / "remotion" / "src" / "lowpoly" / "poses.ts").read_text(encoding="utf-8")
    speed_ts = dict(re.findall(r"(\w+): ([\d.]+)", re.search(r"export const SPEED[^=]*= \{([^}]*)\}", poses).group(1)))
    if {k: float(v) for k, v in speed_ts.items()} != SPEED:
        fail(f"lowpoly footsteps: timeline.SPEED {SPEED} differs from poses.ts SPEED {speed_ts}")
    walk = re.search(r"const f = action === 'run' \? ([\d.]+) : action === 'jog' \? ([\d.]+) : ([\d.]+);", poses)
    legs = {a_: float(f_) for a_, f_ in re.findall(r"case '(dash|flee|carry)':[^}]*?runLegs\(p, t, ([\d.]+)", poses, re.S)}
    want = {"run": float(walk.group(1)), "jog": float(walk.group(2)), "walk": float(walk.group(3)), **legs} if walk else {}
    if want != STRIDE:
        fail(f"lowpoly footsteps: timeline.STRIDE {STRIDE} differs from the walk cycles in poses.ts {want}")
    lp_tsx = (ROOT / "remotion" / "src" / "lowpoly" / "LowPoly.tsx").read_text(encoding="utf-8")
    if f"export const SLOW = {SLOW};" not in lp_tsx:
        fail("lowpoly footsteps: timeline.SLOW differs from LowPoly.tsx SLOW")
    # a walk up to someone stops in front of them: the editor and the footsteps agree on where
    from .lowpoly.timeline import SEAT_SPOTS, STOP_SEATED, STOP_SHORT
    seats_ts = re.search(r"const SEAT_SPOTS = new Set\(\[([^\]]*)\]\)", lp_tsx)
    if (f"export const STOP_SHORT = {STOP_SHORT};" not in lp_tsx or f"export const STOP_SEATED = {STOP_SEATED};" not in lp_tsx
            or not seats_ts or set(re.findall(r"'([\w-]+)'", seats_ts.group(1))) != SEAT_SPOTS):
        fail("lowpoly: timeline STOP_SHORT / STOP_SEATED / SEAT_SPOTS differ from LowPoly.tsx")
    # who sits on a seat spot and where everyone else stands at one (the user's hero stood inside the bus stop's bench)
    from .lowpoly.timeline import LYING_ACTIONS, SEATED_ACTIONS, set_spots
    for name, mine in (("SEATED", SEATED_ACTIONS), ("LYING", LYING_ACTIONS)):
        theirs = re.search(rf"const {name} = new Set<Action>\(\[([^\]]*)\]\)", lp_tsx)
        if not theirs or set(re.findall(r"'([\w-]+)'", theirs.group(1))) != mine:
            fail(f"lowpoly: timeline {name}_ACTIONS differs from LowPoly.tsx {name}")
    seats = [(st, k, v) for st, sp in set_spots().items() for k, v in sp.items() if k in SEAT_SPOTS]
    if not seats or any(v[:2] == v[2:] for _st, _k, v in seats) or set_spots()["busstop"]["chair"][2:] != (0.0, -0.85):
        fail(f"lowpoly: a seat spot without a standing place in Sets.tsx: {[(a, b) for a, b, v in seats if v[:2] == v[2:]]}")
    # who looks at whom (the user's son had to point AT his dad on the chair, the camera showing both)
    lib = {c["name"]: c for c in S.CAST_LIBRARY}
    cast = [S.LPCast(name=n, who=lib[n]["who"], design=S.LPDesign(**lib[n]["design"]), voice=lib[n]["voice"])
            for n in ("his dad", "Kai")]
    staged = S.Story(title="t", problem="", youtube_title="", description="", tags=[], hashtags=[], thumbnail_text="",
                      mood="calm", end_mood="calm", music_prompt="", cast=cast, shots=[
                          S.LPShot(line="", set="park", light="day", camera="front", subject="kai", actors=[
                              S.LPActor(who="Kai", action="point", expression="worried", spot="center"),
                              S.LPActor(who="his dad", action="sit", expression="neutral", spot="chair")]),
                          S.LPShot(line="Dad.", speaker="Kai", set="park", light="day", camera="medium", actors=[
                              S.LPActor(who="hero", action="stand", expression="neutral", spot="left"),
                              S.LPActor(who="Kai", action="talk", expression="neutral", spot="center", look_at="nobody")])])
    S.repair(staged)
    s1, s2 = staged.shots
    if (s1.subject, s1.camera, s1.actors[0].look_at) != ("Kai", "medium", "his dad"):
        fail(f"lowpoly staging: pointing at his dad gave subject {s1.subject}, camera {s1.camera}, look {s1.actors[0].look_at}")
    if (s2.subject, s2.actors[0].look_at, s2.actors[1].look_at) != ("Kai", "Kai", "hero"):
        fail(f"lowpoly staging: a line said to someone gave {s2.subject}, {[a.look_at for a in s2.actors]}")
    stop = S.Story(title="t", problem="", youtube_title="", description="", tags=[], hashtags=[], thumbnail_text="",
                   mood="calm", end_mood="calm", music_prompt="", shots=[S.LPShot(
                       line="", set="busstop", light="day", camera="front", actors=[
                           S.LPActor(who="hero", action="push-stop", expression="angry", spot="center")],
                       big=[S.LPBig(kind="bus", spot="center", motion="stop", at=0.4)])], kind="fiction")
    S.repair(stop)
    if stop.shots[0].camera != "side":
        fail(f"lowpoly staging: a man stopping a bus kept the '{stop.shots[0].camera}' camera, which stands where the bus stops")
    shot1 = build(staged, {}, vertical=False, watermark="", seed=1)[0]["shots"][0]
    if shot1["focus"] != 0 or shot1["actors"][0].get("look") != "his dad":
        fail(f"lowpoly staging: props lost the subject or the look: {shot1['focus']}, {shot1['actors'][0]}")
    from .lowpoly.sounds import BANK, FLOORS
    for floor, (sets, *_rest) in FLOORS.items():
        if not all(list(BANK.glob(f"{x}-*.ogg")) for x in sets):
            fail(f"lowpoly footsteps: the recordings for {floor} ({sets}) are missing from {BANK}")
    # the mix's loudness meter reads the BS.1770 reference tone right, and the music stays down across a short pause
    import numpy as np

    from .lowpoly.mix import RATE, lufs, speech_envelope
    t = np.arange(RATE * 3) / RATE
    if abs(lufs(np.sin(2 * np.pi * 997 * t)[:, None]) + 3.01) > 0.05:
        fail("lowpoly mix: the loudness meter misreads a full-scale 997 Hz tone (should be -3.01 LUFS)")
    v = np.zeros((RATE * 4, 2), np.float32)
    v[RATE:int(RATE * 1.5)] = 0.2
    v[int(RATE * 2.2):int(RATE * 2.6)] = 0.2
    e = speech_envelope(v)
    if not (e[int(RATE * 1.85)] > 0.99 and e[int(RATE * 0.5)] < 0.01):
        fail("lowpoly mix: the music should stay down across a 0.7 s pause between lines and be up long before them")


def lowpoly_vehicles() -> None:
    """People in and on vehicles, the vehicles' motions and cameras, and the things the writer designs: a driver with no
    car gets one, a plane can't race on the road nor a car fly, a design is centred with its bottom on the ground, the
    editor gets `on` (counted from 0) and the designs, an engine plays under a car under way, and the editor's numbers
    are the same as Python's (the jump's time in the air)."""
    import re

    from .lowpoly import story as S
    from .lowpoly.timeline import JUMP_TIME, build

    big = (ROOT / "remotion" / "src" / "lowpoly" / "Big.tsx").read_text(encoding="utf-8")
    m = re.search(r"case 'jump': \{[^}]*?const T = ([0-9.]+);", big, re.S)
    if not m or float(m.group(1)) != JUMP_TIME:
        fail(f"lowpoly vehicles: the jump's time in the air differs (Big.tsx {m and m.group(1)}, timeline.JUMP_TIME {JUMP_TIME})")
    rider = re.search(r"RIDER_SCALE[^=]*= \{[^}]*made: ([0-9.]+)", big)
    if not rider or float(rider.group(1)) != S.RIDER_MADE:
        fail(f"lowpoly vehicles: someone seated in a design is drawn at {rider and rider.group(1)} in Big.tsx, story.RIDER_MADE {S.RIDER_MADE}")
    ts_under = set(re.findall(r"'([a-z]+)'", re.search(r"export const UNDERWAY = new Set\(\[([^\]]*)\]", big).group(1)))
    if ts_under != S.GROUND_UNDERWAY | S.AIR_MOTIONS:
        fail(f"lowpoly vehicles: Big.tsx UNDERWAY {sorted(ts_under)} but story.py {sorted(S.GROUND_UNDERWAY | S.AIR_MOTIONS)}")
    P = S.LPPart
    plane = S.LPMade(name="the jet", what="a small plane", travel="air", seats=[[3, 1.4, 1.0]], top=1.0, parts=[
        P(shape="cylinder", at=[3, 2.0, 0], size=[1.2, 8, 0.8], turn=[90, 0, 0], color="#e9e6df"),
        P(shape="box", at=[3, 1.6, 0], size=[9, 0.15, 1.6], color="#c1121f"),
        P(shape="box", at=[3, 2.0, 4.1], size=[2.2, 0.1, 0.06], color="#22252a", spin="z")])
    hero = lambda **k: S.LPActor(**{"who": "hero", "expression": "determined", "spot": "center", **k})
    st = S.Story(title="t", problem="p", youtube_title="t", description="d", tags=[], hashtags=[], thumbnail_text="t", mood="calm",
                 end_mood="calm", music_prompt="m", kind="fiction", made=[plane], shots=[
                     S.LPShot(line="", set="highway", light="day", camera="chase", pause=2, actors=[hero(action="drive")]),
                     S.LPShot(line="", set="sky", light="day", camera="tracking", pause=2, actors=[hero(action="drive", on=1)],
                              big=[S.LPBig(kind="made", made="The Jet", motion="race")]),
                     S.LPShot(line="", set="kitchen", light="day", camera="pass-by", pause=2, actors=[],
                              big=[S.LPBig(kind="car", motion="fly", at=0.5)]),
                     S.LPShot(line="", set="highway", light="day", camera="face", pause=2, actors=[hero(action="skydive")])])
    S.repair(st)
    s0, s1, s2, s3 = st.shots
    if not (s0.big and s0.big[0].kind == "car" and s0.actors[0].on == 1 and s0.big[0].motion == "race"):
        fail(f"lowpoly vehicles: a driver with no car got {[(b.kind, b.motion) for b in s0.big]}, on {s0.actors[0].on}")
    if s1.big[0].motion != "fly" or s1.big[0].made != "the jet":
        fail(f"lowpoly vehicles: a plane told to race ({s1.big[0].motion}, design '{s1.big[0].made}')")
    if s2.big[0].motion != "race" or s2.set != "highway" or s2.actors:
        fail(f"lowpoly vehicles: a flying car in a kitchen became {s2.big[0].motion} in '{s2.set}' with {len(s2.actors)} people")
    if s3.set != "sky":
        fail(f"lowpoly vehicles: someone falling free stayed in '{s3.set}'")
    d = S.design_for_editor(plane)
    xs = [p["at"][0] for p in d["parts"]]
    if abs(min(xs) + max(xs)) > 0.01 or d["dims"][1] <= 0 or d["seats"][0][0] != 0.0 or not 8.9 <= d["dims"][0] <= 9.1:
        fail(f"lowpoly vehicles: the design wasn't centred or sized ({d['dims']}, seats {d['seats']})")
    if not any(p.get("glass") and p["shape"] == "sphere" for p in d["parts"]):
        fail("lowpoly vehicles: a plane with no canopy over its pilot didn't get one")
    props, _, cues, _ = build(st, {}, vertical=True, watermark="", seed=1)
    if props["shots"][1]["actors"][0].get("on") != 0 or "the jet" not in props.get("made", {}):
        fail("lowpoly vehicles: the editor didn't get `on` (from 0) or the design")
    names = [c["sound"] for c in cues]
    if "engine" not in names or "propeller" not in names or "wind" not in names:
        fail(f"lowpoly vehicles: no engine, propeller or wind under the shots ({sorted(set(names))})")
    # the split-second cut-ins: foot on the accelerator as a race sets off (not again in the chase's next shot), on the
    # brake before a stop, hands on the wheel before a drift, never in a shot that is itself on the pedal
    from .lowpoly.timeline import RACE_SURGE

    race = re.search(r"case 'race':\s*(?://[^\n]*\s*)*p\.keys = \[\[0, [0-9.]+\], \[([0-9.]+),", big)
    if not race or float(race.group(1)) != RACE_SURGE:
        fail(f"lowpoly vehicles: a race surges at {race and race.group(1)} in Big.tsx, timeline.RACE_SURGE {RACE_SURGE}")
    car = lambda m, at=None: [S.LPBig(kind="car", motion=m, at=at)]
    drv = lambda: [hero(action="drive", on=1)]
    st2 = S.Story(title="t", problem="p", youtube_title="t", description="d", tags=[], hashtags=[], thumbnail_text="t", mood="calm",
                  end_mood="calm", music_prompt="m", kind="fiction", shots=[
                      S.LPShot(line="", set="highway", light="day", camera="chase", pause=2, actors=drv(), big=car("race")),
                      S.LPShot(line="", set="highway", light="day", camera="tracking", pause=2, actors=drv(), big=car("race")),
                      S.LPShot(line="", set="highway", light="day", camera="bumper", pause=2, actors=drv(), big=car("drift", 0.6)),
                      S.LPShot(line="", set="street", light="night", camera="pass-by", pause=2, actors=drv(), big=car("stop", 0.6)),
                      S.LPShot(line="", set="street", light="night", camera="pedal", pause=2, actors=drv(), big=car("stop", 0.6)),
                      S.LPShot(line="", set="highway", light="day", camera="chase", pause=2, actors=[], big=car("drift", 0.6))])
    S.repair(st2)
    props, _, cues, _ = build(st2, {}, vertical=False, watermark="", seed=1)
    allins = [x.get("inserts", []) for x in props["shots"]]
    got = ["+".join(i["cam"] + ("/" + i["pedal"] if i.get("pedal") else "") for i in x) for x in allins]
    want = ["pedal/gas+speedo", "", "wheel", "pedal/brake", "", ""]
    if [x.get("camera") for x in props["shots"]][4] != "pedal":
        want[4] = got[4]  # (a whole pedal shot only once every CUT_SHOT_EVERY shots: repair may have changed it)
    if got != want:
        fail(f"lowpoly vehicles: cut-ins {got}, wanted {want}")
    ins = [x[0] if x else None for x in allins]
    for i in (2, 3):
        x, sh = ins[i], props["shots"][i]
        if x and not (0.1 <= x["from"] < x["to"] < sh["big"][0]["at"] < sh["duration"]):
            fail(f"lowpoly vehicles: shot {i + 1}'s cut-in {x} doesn't come before its moment {sh['big'][0]['at']}")
    if "rev" not in [c["sound"] for c in cues]:
        fail("lowpoly vehicles: no rev as the foot goes down on the accelerator")
    # a car's engine follows its own speed (car.engine, from the user's recording), its tyres squeal by kind
    import numpy as np

    from .lowpoly import car as C

    if not any(c["sound"] == "engine" and c.get("car") for c in cues) or not {c.get("skid") for c in cues} >= {"drift", "brake"}:
        fail("lowpoly vehicles: no car engine following its speed, or no brake/drift squeal among the cues")
    for motion in ("race", "drift", "spin", "stop", "jump"):
        m = re.search(rf"case '{motion}':\s*\{{?(?:\s*//[^\n]*)*\s*p\.keys = (\[\[.*?\]\]);", big, re.S)
        theirs = re.findall(r"\[([^\[\]]+)\]", m.group(1)) if m else []
        if len(theirs) != len(C.speed_keys(motion, 1.0, 4.0)):
            fail(f"lowpoly vehicles: car.speed_keys('{motion}') no longer matches Big.tsx ({m and m.group(1)})")
    r, _ = C.revs("race", 1.6, 4.0)
    if not (r[0] < r[-1] and (np.diff(r) < -0.5).any()):
        fail("lowpoly vehicles: a race's revs should climb and drop at a gear change")
    x = C.engine("stop", 1.6, 3.0)
    if C.RECORDING.exists() and (x is None or not np.isfinite(x).all() or len(x) != int(3.0 * C.RATE)):
        fail("lowpoly vehicles: the engine from the recording didn't come out")
    # a jump on the open highway leaps the broken bridge, with the chase into it; a shot of someone on foot stays
    st3 = S.Story(title="t", problem="p", youtube_title="t", description="d", tags=[], hashtags=[], thumbnail_text="t", mood="calm",
                  end_mood="calm", music_prompt="m", kind="fiction", shots=[
                      S.LPShot(line="", set="highway", light="day", camera="wide", pause=2, actors=[hero(action="stand")]),
                      S.LPShot(line="", set="highway", light="day", camera="chase", pause=2, actors=drv(), big=car("race")),
                      S.LPShot(line="", set="highway", light="day", camera="pass-by", pause=2, actors=drv(), big=car("jump", 0.5)),
                      S.LPShot(line="", set="highway", light="day", camera="lead", pause=2, actors=drv(), big=car("race")),
                      S.LPShot(line="", set="street", light="day", camera="chase", pause=2, actors=drv(), big=car("race"))])
    S.repair(st3)
    if [x.set for x in st3.shots] != ["highway", "bridge", "bridge", "bridge", "street"]:
        fail(f"lowpoly vehicles: a jump on the highway gave the places {[x.set for x in st3.shots]}")
    sets_ts = (ROOT / "remotion" / "src" / "lowpoly" / "Sets.tsx").read_text(encoding="utf-8")
    for name in ("bridge", "rooftop"):
        body = re.search(rf"const {name}: SetDef = \{{(.*?)\n  Draw:", sets_ts, re.S)
        if not body or "gap:" not in body.group(1) or "jumpAt:" not in body.group(1):
            fail(f"lowpoly vehicles: the {name} set has no gap or no place a jump takes off")


def lowpoly_intro() -> None:
    """🎭 Cast intro (lowpoly/intro.py), offline with the code's own plan: the time divided equally, every camera
    different within a person and from the shot before, the whole pool used before a camera repeats, a card per
    person over exactly their segment, nobody shown from behind."""
    import tempfile
    from dataclasses import replace

    from .config import Config
    from .lowpoly import intro as I
    from .lowpoly import story as S
    from .lowpoly.timeline import build

    with tempfile.TemporaryDirectory() as tmp:
        cfg = replace(Config(), output_dir=Path(tmp))
        for seconds, names in ((60, ["hero", "Mia", "Kai", "Nora", "Rafi"]), (60, []), (30, ["Mia"])):
            cast = I.people(cfg, names, "Ethan")
            per, each = I.split(seconds, len(cast))
            plan = I.fallback_plan(cast, per)
            for p in plan.people:  # the writer asking for the same camera and a facing-away spot every time
                for sh in p.shots:
                    sh.camera, sh.spot = "medium", "counter"
            story = I.assemble(plan, cast, per, each, seconds)
            S.repair(story)
            props = build(story, {}, vertical=False, watermark="", seed=1, words="off")[0]
            assert abs(props["duration"] - seconds) < 0.01, props["duration"]
            assert len(props["cards"]) == len(cast)
            cams = [s["camera"] for s in props["shots"]]
            assert all(a != b for a, b in zip(cams, cams[1:])), cams
            for c in story.intro:
                mine = cams[c.first:c.first + c.shots]
                assert len(set(mine)) == len(mine), mine
            assert len(set(cams[: len(I.POOL)])) == min(len(cams), len(I.POOL)), cams
            for c, card in zip(story.intro, props["cards"]):
                seg = props["shots"][c.first]
                assert abs(card["start"] - seg["start"]) < 0.01 and abs(card["end"] - card["start"] - seconds / len(cast)) < 0.02
            assert not any(a["spot"] in I.AWAY_SPOTS for s in props["shots"] for a in s["actors"])
            assert props["cards"][0]["name"] == ("Ethan" if not names or "hero" in names else cast[0]["name"])


def lowpoly_boards() -> None:
    """✍ Storyboards to read first (lowpoly/boards.py), offline: a draft read shot by shot, rejecting the last open one
    asks for a new round (not after an approval), a rejected one can still be approved but only once, an approved one
    becomes an unfinished video at stage 'written' (a long film's outline: its acts are written from it), and a draft's
    new person is kept only once approved."""
    import json
    import tempfile
    from dataclasses import asdict, replace

    from .config import Config
    from .lowpoly import boards as B
    from .lowpoly import story as S
    from .lowpoly.run import LowPolyRequest

    with tempfile.TemporaryDirectory() as tmp:
        cfg = replace(Config(), output_dir=Path(tmp))
        A = S.LPActor
        shots = [S.LPShot(stamp="11:47 P.M.", line="He sets the alarm for five.", set="bedroom", light="night", camera="face",
                          actors=[A(who="hero", action="lie-phone", expression="tired", spot="bed")]),
                 S.LPShot(line="", set="kitchen", light="morning", camera="medium", actors=[A(who="Zed Quill", action="stand", expression="happy", spot="counter")])]
        story = S.Story(title="Five A.M.", problem="the run", youtube_title="y", description="d", tags=[], hashtags=[], thumbnail_text="t",
                        mood="calm", end_mood="uplifting", music_prompt="m", shots=shots,
                        cast=[S.LPCast(name="Zed Quill", who="a neighbour", design=S.LPDesign(**S.CAST_LIBRARY[0]["design"]))])
        st = B.new_set(cfg, asdict(LowPolyRequest(topic="the run")), 2)
        for n in (1, 2):
            (Path(tmp) / B.DIR / st["id"] / f"draft-{n}.json").write_text(json.dumps(story.model_dump()), encoding="utf-8")
        B._update(cfg, st["id"], lambda x: x["drafts"].extend({"n": n, "state": "ready", "title": f"T{n}", "take": "", "problem": "p"} for n in (1, 2)))
        v = B.view(cfg, st["id"], 1)
        if len(v["shots"]) != 2 or v["shots"][0]["stamp"] != "11:47 P.M." or not v["shots"][0]["people"][0].startswith("him: lie phone"):
            fail(f"lowpoly boards: a storyboard doesn't read shot by shot: {v['shots'][:1]}")
        if B.estimate(story) <= 0:
            fail("lowpoly boards: no running time estimated")
        if B.reject(cfg, st["id"], 1, "too sad") or not B.reject(cfg, st["id"], 2):
            fail("lowpoly boards: only rejecting the last open storyboard asks for new ones")
        work, _ = B.prepare_build(cfg, st["id"], 1)
        ck = json.loads((Path(tmp) / work / "lowpoly-checkpoint.json").read_text(encoding="utf-8"))
        if ck.get("stage") != "written" or not (Path(tmp) / work / "story.json").exists() or ck.get("board", {}).get("draft") != 1:
            fail(f"lowpoly boards: an approved storyboard isn't an unfinished video at 'written': {ck.get('stage')}")
        if "zed quill" not in json.loads((Path(tmp) / "lowpoly_cast.json").read_text(encoding="utf-8")):
            fail("lowpoly boards: an approved storyboard's new person wasn't kept for later films")
        try:
            B.prepare_build(cfg, st["id"], 1)
            fail("lowpoly boards: the same storyboard was approved twice")
        except ValueError:
            pass
        st2 = B.new_set(cfg, asdict(LowPolyRequest(topic="x")), 2)
        (Path(tmp) / B.DIR / st2["id"] / "draft-1.json").write_text(json.dumps(story.model_dump()), encoding="utf-8")
        B._update(cfg, st2["id"], lambda x: x["drafts"].append({"n": 1, "state": "ready", "title": "T", "take": "", "problem": "p"}))
        B._update(cfg, st2["id"], lambda x: x["drafts"].append({"n": 2, "state": "ready", "title": "U", "take": "", "problem": "p"}))
        B.prepare_build(cfg, st2["id"], 1)
        if B.reject(cfg, st2["id"], 2):
            fail("lowpoly boards: new storyboards were asked for after one was approved")
        # ✏ Change it: the draft rewritten with the user's words as a new draft beside it, the original untouched
        asked = {}

        def revised(cfg_, story_, instruction, **kw):
            asked["text"] = instruction
            return story_.model_copy(update={"title": "Five A.M., at night"})
        (Path(tmp) / B.DIR / st2["id"] / "draft-2.json").write_text(json.dumps(story.model_dump()), encoding="utf-8")
        real = S.revise
        S.revise = revised
        try:
            m = B.change_round(cfg, st2["id"], 2, "set it at night", lambda *a: None)
        finally:
            S.revise = real
        drafts = {d["n"]: d for d in B.load(cfg, st2["id"])["drafts"]}
        if (m != 3 or asked.get("text") != "set it at night" or drafts[3]["state"] != "ready" or drafts[3].get("from") != 2
                or drafts[3]["title"] != "Five A.M., at night" or drafts[2]["state"] != "rejected"
                or B.view(cfg, st2["id"], 3)["title"] != "Five A.M., at night"):
            fail(f"lowpoly boards: ✏ Change it didn't write a changed storyboard beside the original: {drafts}")


def main() -> int:
    sys.path.insert(0, str(ROOT))
    imports()
    duplicate_names()
    behaviour()
    update_helper()
    meme_lists()
    hook_templates()
    visual_templates()
    lowpoly_lists()
    lowpoly_vehicles()
    lowpoly_boards()
    lowpoly_intro()
    print("selfcheck:", "OK" if not FAILS else f"{len(FAILS)} problem(s)")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
