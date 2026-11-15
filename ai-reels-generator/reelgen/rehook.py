"""Re-create only the hook of a finished long, medium or Script video, as a new, separate video.

The user: "add option at video section to re-create hooks only, provide different templates of hook, demo as well ...
re-create hook means only create hook again and append further video, and always create new separate video by just
copy paste and recreating hooks, not editing the actual video."

Two steps, both from the video page:
1. `make_hook` (a preview): Claude writes a new hook for the chosen template (cinehook.TEMPLATES) from the video's own
   script (an AI video's hook lines are rewritten, using only what the script states; a Script Video keeps the user's
   hook words and only gets new shots); its voice, AI pictures and music are made and only the hook is rendered, into
   `<video>/hooks/<key>.mp4` (+ .json, the timeline and files in `hooks/<key>/`). Several can be made and compared
   with the original's hook.
2. `save_as_new` (a job): the video folder is copied to a new one, the new hook is rendered there already, and it is
   joined to the original video's story (everything after the old hook's silence, re-encoded once, never re-edited:
   minutes instead of the hour a re-edit takes). props.json gets the new hook and every later time shifted, so the new
   video can be re-made, re-voiced or have sounds removed like any other; the report's chapter stamps move with it.
   The original video is never touched.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from pydantic import BaseModel, Field

from . import aimusic, cinehook, media, sound_design, stopper
from .config import Config
from .fsutil import move

log = logging.getLogger(__name__)
Progress = Callable[[str], None]

HOOKS = "hooks"  # in the video folder: the hooks made for it
PREFIX = "hook2"  # in the new video's folder: the new hook's own files (never mixed with the story's)
NOT_FOR = ("shoot", "stick", "anim", "toon", "storyshorts")  # their hooks aren't long-pipeline hooks
SKIP_COPY = {HOOKS, "demos", "myvoice", "_rerender", "reel-myvoice.mp4", "reel-original.mp4", "reel-sd.mp4",
             "render-parts"}


def why_not(folder: Path) -> str:
    """'' when this video's hook can be re-created, else the reason."""
    try:
        report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "This video has no report."
    if report.get("format") != "long" or report.get("source") in NOT_FOR:
        return "Hooks can be re-created for long, medium and Script videos."
    if not (folder / "props.json").exists() or not (folder / "script.json").exists():
        return "This video's edit wasn't saved with it."
    hook = (json.loads((folder / "props.json").read_text(encoding="utf-8")).get("hook") or {})
    if not hook.get("shots"):
        return "This video has no hook to replace."
    return ""


class NewHook(BaseModel):
    shots: list = Field(description="The hook's shots in order.")


def _write(cfg: Config, script, template: str, keep_words: bool, minutes: float):
    """The new hook's shots (longform.HookShot), written by Claude for the template from the video's own script."""
    from .llm import ask
    from . import memes, memeweb
    from .longform import LLM_TIMEOUT, HookShot, _system
    from pydantic import create_model

    schema = create_model("NewHook", shots=(list[HookShot], Field(description="The hook's shots in order.")))
    # Memes in every template: the Settings level, or 'some' for a video that already has memes in it.
    level = memes.level(cfg)
    if level == "off" and any(b.visual.type in ("meme", "web_meme") for c in script.chapters for b in c.beats):
        level = "some"
    full = _system(cfg.video_style, cfg.long_language, minutes, level, memes.own_files(cfg),
                   memeweb.prompt_block(replace(cfg, memes=level)) if level != "off" else "", hook_template=template)
    visuals = full[full.index("Show, don't write"):full.index("Accuracy:")].strip()
    old = [h.line for h in script.hook if h.line.strip()]
    story = "\n".join(f"{c.title}: " + " ".join(b.narration for b in c.beats) for c in script.chapters)
    if keep_words:
        words = ("The hook's words are the user's own and final: give every line below exactly one shot, in order, "
                 "with the line exactly as written (never change, add or drop a word); at most 2 extra silent shots "
                 "(empty line).\n" + "\n".join(f"H{i} {line}" for i, line in enumerate(old, 1)))
    else:
        words = ("Write new hook lines for this template. Use only facts the script below states (no new figure, "
                 "date, name or claim), never the answer it keeps for the end. The old hook, for reference only:\n"
                 + "\n".join(old))
    system = f"""You re-create the cold open (hook) of a finished YouTube video so it holds viewers from the first \
second. The rest of the video stays exactly as it is.

{cinehook.rules(minutes, template)}

{visuals}"""
    prompt = (f"Title: {script.youtube_title}\nThe question the video answers: {script.hook_question}\n"
              f"The answer (keep it hidden in the hook): {script.answer}\n\n{words}\n\nThe video's script:\n{story}")
    out = ask(cfg.ai_backend, cfg.claude_model, system, prompt, schema, allow_web=False, effort=cfg.claude_effort,
              timeout=LLM_TIMEOUT)
    shots = list(out.shots)
    if keep_words:  # every line once, in order, word for word, whatever came back
        lines = iter(old)
        kept = []
        for s in shots:
            if s.line.strip():
                nxt = next(lines, None)
                if nxt is None:
                    continue
                s = s.model_copy(update={"line": nxt})
            kept.append(s)
        for rest in lines:
            kept.append(HookShot(beat="gap", line=rest, visual=script.hook[-1].visual))
        shots = kept
    return shots


def _key(template: str) -> str:
    return f"{template}-{uuid.uuid4().hex[:6]}"


def hooks(folder: Path) -> list[dict]:
    """The hooks made for this video (newest first)."""
    out = []
    for f in (folder / HOOKS).glob("*.json") if (folder / HOOKS).is_dir() else []:
        try:
            info = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (folder / HOOKS / f"{f.stem}.mp4").exists():
            out.append(info)
    return sorted(out, key=lambda d: d.get("made", ""), reverse=True)


def _render_hook(cfg: Config, script, template: str, work: Path, look: dict, seed: int, hook_seconds, pct: int,
                 progress: Progress, title: str, fps: int, currency: str = "", vertical: bool = False) -> dict:
    """Only the hook of `script`, built (voice, pictures, music, sounds) and rendered into work/hook.mp4: its props."""
    from .longform import _build_hook
    from .sfx import write_cue_sounds, write_sfx
    from .video import _remotion_cli, _render_remotion

    hook, lines, spoken, cues = _build_hook(
        script, cfg, work, look, seed, progress, hook_seconds=hook_seconds, hook_voices=None, overrides={},
        remake=False, pct=pct, sarvam_speed=round(1 + pct / 100, 3),  # a factor on Sarvam's own pace setting
        template=template, clip_ids=set(), used={})
    rel = lambda p: p.relative_to(work).as_posix()  # noqa: E731
    if aimusic.available(cfg) and look.get("aiGenre") and not hook.get("own"):  # the video's genre, a new hook track
        want = [aimusic.track("hook", work / "music" / "ai-hook.wav", hook["duration"] - hook["drop"] + 0.5,
                              look["aiGenre"], script.mood, 1.0 if cinehook.energetic(template) else 0.9,
                              script.music_prompt, seed + 11, hook=True, cine=not cinehook.energetic(template))]
        made = aimusic.make(cfg, want, work, progress, "Hook music (AI)")
        if "hook" in made:
            hook["music"], hook["ai"] = rel(made["hook"]), look["aiGenre"]
    sfx = write_sfx(work / "sfx")
    sfx.update(media.uploaded_for(cfg, list(sfx), work / "sfx"))
    hook_cues, hook["drone"] = cinehook.sound_design(hook["shots"], hook["duration"] - hook["drop"], work, rel,
                                                     {k: rel(p) for k, p in sfx.items()}, None, template=template)
    cues += hook_cues
    captions = [{"start": g[0]["start"], "end": round(g[-1]["end"] + 0.25, 3), "words": g} for g in lines]
    for a, b in zip(captions, captions[1:]):
        a["end"] = min(a["end"], b["start"])
    props = {"title": title, "fps": fps, "duration": hook["duration"], "look": look, "hook": hook, "chapters": [],
             "beats": [], "captions": captions if cfg.captions else [], "all_captions": captions, "music": None,
             "musicFrom": hook["duration"], "ambience": [], "musicParts": [],
             "sfx": {k: rel(p) for k, p in sfx.items()}, "cues": cues, "speech": media.speech_spans(spoken),
             "currency": currency, "musicChoice": "hook only"}
    if vertical:
        props["vertical"] = True
    auto = sound_design.design(props, look.get("transition", "smooth"))
    needed = {n for n, _, _ in auto} - set(sfx)
    files = {**props["sfx"], **{k: rel(p) for k, p in write_cue_sounds(work / "sfx", needed).items()}}
    props["cues"] = cues + [{"src": files[n], "at": at, "name": n, "volume": vol} for n, at, vol in auto if n in files]
    voice = [sh["audio"] for sh in hook["shots"] if sh.get("audio")]
    props["sfxLevels"] = media.level_sounds(props, work, voice)
    props["musicLevels"] = media.level_music(props, work, voice, "Long")
    cli = _remotion_cli()
    if cli is None:
        raise RuntimeError("Node.js or the Remotion packages are not installed (run start.bat / start.sh)")
    progress(f"Editing the hook ({hook['duration']:.0f} s)")
    _render_remotion(cli, props, work / "hook.mp4", composition="Long", crf=18, progress=progress)
    (work / "props.json").write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
    return props


def make_hook(cfg: Config, folder: Path, template: str, rewrite: bool = True, progress: Progress = log.info,
              pace: str | None = None) -> dict:
    """A new hook for this video, rendered on its own as a preview (see the module's notes). `pace` ('-3%'): how fast
    the hook is spoken; none = the video's own pace, so the hook matches the story after it."""
    from .longform import SCRIPT_HOOK_SECONDS, LongScript, _seed
    from .rerender import _remake_look, made_pace

    reason = why_not(folder)
    if reason:
        raise ValueError(reason)
    if template not in cinehook.TEMPLATES:
        raise ValueError(f"Unknown hook template {template!r}")
    report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
    script = LongScript.model_validate_json((folder / "script.json").read_text(encoding="utf-8"))
    old = json.loads((folder / "props.json").read_text(encoding="utf-8"))
    yours = report.get("source") == "script"  # a Script Video: the hook's words are the user's
    minutes = float(report.get("duration_seconds") or 540) / 60
    video_pace = made_pace(cfg, report)
    pace = pace if pace and re.fullmatch(r"[+-]\d{1,2}%", pace) else video_pace
    cfg = replace(cfg, long_voice=report.get("voice") or cfg.long_voice, long_voice_rate=pace, hook_template=template,
                  long_minutes=minutes, captions=report.get("captions", False))
    cfg, look = _remake_look(cfg, old)
    look = dict(look or {})
    key = _key(template)
    work = folder / HOOKS / key
    work.mkdir(parents=True, exist_ok=True)
    progress(f"Claude is writing a new hook ({cinehook.TEMPLATES[template][0]}"
             + (", your words kept)" if yours or not rewrite else ")"))
    shots = _write(cfg, script, template, yours or not rewrite, minutes)
    new = script.model_copy(update={"hook": shots})
    (work / "hook-script.json").write_text(json.dumps([s.model_dump() for s in shots], ensure_ascii=False, indent=2),
                                           encoding="utf-8")
    if (folder / "plates" / "hook.jpg").exists():  # the hook's own background photo, as the video had it
        (work / "plates").mkdir(exist_ok=True)
        shutil.copy2(folder / "plates" / "hook.jpg", work / "plates" / "hook.jpg")
    look["plates"], look["platesBaked"] = {}, {}
    look["hookPlate"] = "plates/hook.jpg" if (work / "plates" / "hook.jpg").exists() else None
    pct = int(re.sub(r"[^\d-]", "", pace or "") or 0)
    props = _render_hook(cfg, new, template, work, look, _seed(script),
                         SCRIPT_HOOK_SECONDS if yours else cinehook.seconds_for(minutes, template), pct, progress,
                         title=old.get("title", script.youtube_title), fps=old.get("fps", cfg.fps),
                         currency=old.get("currency", ""), vertical=bool(old.get("vertical")))
    hook = props["hook"]
    shutil.copy2(work / "hook.mp4", folder / HOOKS / f"{key}.mp4")
    old_end = float(old["hook"]["duration"])
    info = {"key": key, "template": template, "name": cinehook.TEMPLATES[template][0], "pace": pace,
            "video_pace": video_pace, "rewritten": not (yours or not rewrite),
            "seconds": round(hook["duration"], 1), "old_seconds": round(old_end, 1),
            "lines": [s.get("text") or "" for s in hook["shots"]], "said": [h.line for h in shots if h.line.strip()],
            "made": datetime.now().isoformat(timespec="seconds")}
    (folder / HOOKS / f"{key}.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    return info


# ---------- step 2: a new video with the new hook ----------

def _prefixed(value, prefix: str):
    """Every relative file path in a hook's props, moved under `prefix/`."""
    if isinstance(value, dict):
        return {k: (f"{prefix}/{v}" if k in ("src", "audio", "music", "drone") and isinstance(v, str) and v else
                    _prefixed(v, prefix)) for k, v in value.items()}
    if isinstance(value, list):
        return [_prefixed(v, prefix) for v in value]
    return value


def shift_props(old: dict, new_hook: dict, extra: dict, delta: float) -> dict:
    """The old timeline with its hook replaced: everything from the old hook's end on moved by `delta` seconds.
    `extra`: the new hook's own cues, speech and caption lines (already prefixed)."""
    end = float(old["hook"]["duration"])
    mv = lambda x: round(float(x) + delta, 3)  # noqa: E731
    p = json.loads(json.dumps(old))
    p["hook"] = new_hook
    p["duration"] = mv(p["duration"])
    if p.get("musicFrom") is not None:
        p["musicFrom"] = mv(p["musicFrom"])
    for c in p.get("chapters", []):
        c["start"] = mv(c["start"])
        if c.get("end") is not None:
            c["end"] = mv(c["end"])
    for b in p.get("beats", []):
        b["start"] = mv(b["start"])
    for part in p.get("musicParts", []) + p.get("ambience", []):
        part["from"], part["to"] = mv(part["from"]), mv(part["to"])
    p["cues"] = [{**c, "at": mv(c["at"])} for c in p.get("cues", []) if float(c["at"]) >= end - 0.01] + extra["cues"]
    p["speech"] = [[mv(a), mv(b)] for a, b in p.get("speech", []) if float(a) >= end - 0.01] + extra["speech"]

    def lines(caps: list) -> list:
        out = []
        for cap in caps:
            if float(cap["start"]) < end - 0.01:
                continue
            out.append({**cap, "start": mv(cap["start"]), "end": mv(cap["end"]),
                        "words": [{**w, "start": mv(w["start"]), "end": mv(w["end"])} for w in cap.get("words", [])]})
        return out
    keep = bool(p.get("captions"))
    p["all_captions"] = extra["captions"] + lines(p.get("all_captions", p.get("captions", [])))
    p["captions"] = p["all_captions"] if keep else []
    return p


def _encoders(ffmpeg: str) -> list[list[str]]:
    """The video encoders to try for the join: the NVIDIA one first when the machine has it, then x264."""
    out = subprocess.run([ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    tries = [["-c:v", "libx264", "-preset", "veryfast", "-crf", "18"]]
    if "h264_nvenc" in out:
        tries.insert(0, ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "19", "-b:v", "0"])
    return tries


def join(hook: Path, video: Path, body_from: float, out: Path, progress: Progress = log.info) -> None:
    """The new hook, then `video` from `body_from` seconds on, as one file (frame-exact: the story re-encoded once)."""
    from .longform import FFMPEG

    err = ""
    for enc in _encoders(FFMPEG):
        cmd = [FFMPEG, "-y", "-loglevel", "error", "-i", str(hook), "-ss", f"{body_from:.3f}", "-i", str(video),
               "-filter_complex", "[0:v]fps=30,format=yuv420p,setsar=1[a];[1:v]fps=30,format=yuv420p,setsar=1[b];"
               "[0:a]aresample=48000[c];[1:a]aresample=48000[d];[a][c][b][d]concat=n=2:v=1:a=1[v][au]",
               "-map", "[v]", "-map", "[au]", *enc, "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k",
               "-movflags", "+faststart", str(out)]
        progress(f"Joining the new hook to the story ({enc[1]}; no re-edit, a few minutes)")
        proc = stopper.run(cmd, capture_output=True, text=True)
        if proc.returncode == 0 and out.exists():
            return
        err = (proc.stderr or "").strip()[-400:]
        log.warning("Join with %s failed: %s", enc[1], err)
    raise RuntimeError(f"Couldn't join the new hook to the video: {err}")


def _seconds(path: Path) -> float:
    from .longform import media_seconds
    return media_seconds(path)


def save_as_new(cfg: Config, folder: Path, key: str, progress: Progress = log.info) -> dict:
    """A new video: this one copied, with the hook `key` (made by make_hook) in place of its own."""
    from .longform import youtube_chapters

    info_path = folder / HOOKS / f"{key}.json"
    work = folder / HOOKS / key
    if not info_path.exists() or not (work / "props.json").exists() or not (work / "hook.mp4").exists():
        raise ValueError("That hook isn't there any more; make it again.")
    info = json.loads(info_path.read_text(encoding="utf-8"))
    report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
    old = json.loads((folder / "props.json").read_text(encoding="utf-8"))
    hp = json.loads((work / "props.json").read_text(encoding="utf-8"))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    base = re.sub(r"^\d{8}-\d{6}-", "", folder.name)[:60]
    dest = cfg.output_dir / f"{stamp}-{base}-{info['template']}-hook"
    temp = cfg.output_dir / f"{dest.name}-working"
    progress(f"Copying the video to a new one ({dest.name})")
    shutil.copytree(folder, temp, ignore=lambda d, names: [n for n in names if Path(d) == folder and
                                                            (n in SKIP_COPY or re.fullmatch(r"attempt\d+\.mp4", n))])
    try:
        files = temp / PREFIX
        shutil.copytree(work, files, ignore=shutil.ignore_patterns("hook.mp4", "props*.json", "render-parts"))
        old_end = float(old["hook"]["duration"])
        new_end = float(hp["hook"]["duration"])
        delta = new_end - old_end
        new_hook = _prefixed(hp["hook"], PREFIX)
        extra = {"cues": _prefixed(hp.get("cues", []), PREFIX), "speech": hp.get("speech", []),
                 "captions": hp.get("all_captions", [])}
        props = shift_props(old, new_hook, extra, delta)
        if hp.get("look", {}).get("hookTemplate"):
            props.setdefault("look", {})["hookTemplate"] = hp["look"]["hookTemplate"]
        join(work / "hook.mp4", folder / "reel.mp4", old_end, temp / "reel.new.mp4", progress)  # ffmpeg needs .mp4
        (temp / "reel.mp4").unlink(missing_ok=True)
        move(temp / "reel.new.mp4", temp / "reel.mp4")
        got, want = _seconds(temp / "reel.mp4"), _seconds(folder / "reel.mp4") + delta
        if abs(got - want) > 1.0:
            raise RuntimeError(f"The joined video is {got:.1f} s long, expected {want:.1f} s")
        (temp / "props.json").write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
        new_report = {k: v for k, v in report.items() if k not in ("review", "my_voice", "removed_sounds")}
        chapters = youtube_chapters(props)
        new_report.update(duration_seconds=round(props["duration"], 1), hook_template=info["template"],
                          hook_from=folder.name, created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                          chapters=[{"title": c["title"], "start": c["start"]} for c in props["chapters"]])
        if report.get("source") == "script":
            new_report["youtube_chapters"] = chapters
        elif new_report.get("youtube_description"):
            desc = re.split(r"\n\nChapters:\n", new_report["youtube_description"], maxsplit=1)[0]
            new_report["youtube_description"] = desc + "\n\nChapters:\n" + chapters
        (temp / "report.json").write_text(json.dumps(new_report, indent=2, ensure_ascii=False), encoding="utf-8")
        move(temp, dest)
    except BaseException:
        shutil.rmtree(temp, ignore_errors=True)
        raise
    progress(f"New video with the {info['name']} hook: {dest.name} ({props['duration'] / 60:.1f} min)")
    return {**new_report, "id": dest.name, "folder": str(dest)}


# ---------- what each template looks like (the Script tab, the Create page, Settings) ----------

SAMPLES = "hook-samples"
SAMPLE_VERSION = 6  # bump when a template changes, so the examples are made again
SAMPLE = [  # an everyday story every viewer knows; no figure that needs a source
    ("Your salary lands on the first.", "salary lands", "1st",
     {"type": "scene", "actors": [{"icon": "banknote", "action": "drop-in"}, {"icon": "smartphone", "action": "pulse"}]}),
    ("By the tenth, it's already gone.", "already gone", "10th",
     {"type": "scene", "actors": [{"icon": "wallet", "action": "shrink"}, {"icon": "calendar", "action": "shake"}]}),
    ("Rent. EMIs. Groceries. Subscriptions.", "Rent EMIs", "Rent. EMIs.",
     {"type": "icons", "icons": ["house", "credit-card", "shopping-cart"]}),
    ("You worked a whole month for this.", "whole month", "30 days",
     {"type": "scene", "actors": [{"icon": "user", "action": "fall"}]}),
    ("So where does your money really go?", "really go", "Where?",
     {"type": "scene", "actors": [{"icon": "indian-rupee", "action": "flee"}, {"icon": "search", "action": "approach"}]}),
]


# The templates with their own shape tell the same story their way: (line, text, picture of SAMPLE[k], extras).
SHAPED = {
    "myth": [("You think a bigger salary will fix it.", "BIGGER SALARY", 0, {"stamp": "MYTH"}),
             ("A raise often vanishes the same way.", "SAME WAY", 1, {}),
             ("Rent. EMIs. Groceries. Subscriptions.", "RENT. EMIS.", 2, {}),
             ("The leak is in the small things.", "SMALL THINGS", 3, {}),
             ("So where does your money really go?", "WHERE?", 4, {})],
    "mirror": [("Your salary lands on the first.", "Salary credited", 0, {}),
               ("You promise yourself: this month, I save.", "This month I save", 3, {}),
               ("By the tenth, it's already gone.", "Balance low", 1, {}),
               ("You didn't even buy anything big.", "Nothing big?", 2, {}),
               ("So where does your money really go?", "Where did it go?", 4, {})],
    "rewind": [("The tenth. Your account is almost empty.", "ALMOST EMPTY", 1, {}),
               ("And you didn't buy anything big.", "NOTHING BIG", 3, {}),
               ("Ten days earlier, your salary landed.", "10 DAYS EARLIER", 0, {"rewind": True}),
               ("Rent. EMIs. Groceries. Subscriptions.", "RENT. EMIS.", 2, {}),
               ("So where did it really go?", "WHERE?", 4, {})],
    "promise": [("By the tenth, your salary is gone.", "GONE BY THE 10TH", 1, {}),
                ("By the end, you'll know exactly where.", "EXACTLY WHERE", 4, {}),
                ("The bills you see.", "Bills you see", 2, {}),
                ("The leaks you don't.", "Leaks you don't", 3, {}),
                ("And the one habit that stops it.", "The one habit", 0, {}),
                ("Because it happens every single month.", "EVERY MONTH", 3, {})],
    "bulletin": [("Your salary lands on the first.", "Salary credited", 0, {"kicker": "Day 1"}),
                 ("By the tenth, it's already gone.", "Day 10", 1, {"kicker": "Balance low"}),
                 ("Rent. EMIs. Groceries. Subscriptions.", "4 debits", 2, {}),
                 ("You worked a whole month for this.", "30 days", 3, {}),
                 ("So where does your money really go?", "Where did it go?", 4, {"kicker": "Unknown"})],
    "frontpage": [("Your salary lands on the first.", "Salary lands on the 1st", 0, {"kicker": "Every month"}),
                  ("By the tenth, it's already gone.", "Gone by the tenth", 1, {}),
                  ("Rent, EMIs, groceries.", "Rent, EMIs, groceries", 2, {}),
                  ("You worked a whole month for this.", "A month's work", 3, {}),
                  ("So where does your money really go?", "Where does it go?", 4, {})],
    "teaser": [("A salary that's gone in ten days.", "10 DAYS", 1, {}),
               ("The bills you pay without looking.", "THE BILLS", 2, {}),
               ("The subscriptions you forgot.", "FORGOTTEN", 0, {}),
               ("The month you worked for nothing.", "A WHOLE MONTH", 3, {}),
               ("So where does your money really go?", "WHERE?", 4, {})],
}


SAMPLE_MEME = {  # shot 4 of every example is a meme (the user: memes in every template): (format, labels, face)
    "": ("reaction", ["Worked the whole month", "Gone by the 10th"], "crying"),
    "myth": ("two-buttons", ["Cancel subscriptions", "Keep them all"], ""),
    "mirror": ("reaction", ["Didn't buy anything big", "Money still gone"], "confused"),
    "rewind": ("reaction", ["Rent, EMIs, groceries", "Subscriptions too?"], "shocked"),
    "promise": ("reaction", ["Me: I barely spend", "The small leaks"], "side-eye"),
    "teaser": ("reaction", ["Worked all month", "For nothing"], "crying"),
}


def sample_path(cfg: Config, template: str) -> Path:
    return cfg.output_dir / SAMPLES / f"{template}-v{SAMPLE_VERSION}.mp4"


def make_sample(cfg: Config, template: str, progress: Progress = log.info) -> Path:
    """A short example hook in `template` (made once, kept in <output>/hook-samples/)."""
    from .longform import HookShot, LongScript, LVisual

    out = sample_path(cfg, template)
    if out.exists():
        return out
    work = out.parent / f"_{template}"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    shots = []
    rows = SHAPED.get(template) or [(line, hot if template == "kinetic" else slam if template == "stakes"
                                     else "" if template == "rapid" else slam.upper(), k, {})
                                    for k, (line, hot, slam, _) in enumerate(SAMPLE)]
    for i, (line, text, k, extra) in enumerate(rows):
        v = SAMPLE[k][3]
        visual = LVisual(headline="", sub="", items=[], icons=v.get("icons", []), actors=v.get("actors", []),
                         type=v["type"], camera="push")
        if i == 3:
            fmt, labels, face = SAMPLE_MEME.get(template if template in SHAPED else "", SAMPLE_MEME[""])
            visual = LVisual(headline="", sub="", items=[], icons=[], type="meme", meme=fmt, labels=labels, face=face,
                             camera="still")
        shots.append(HookShot(beat="curiosity", line=line, text=text, boom=i in (0, 4), **extra, visual=visual))
    script = LongScript(topic="Where your salary goes", why_chosen="example", facts_checked="none", category="Money",
                        subject="salary", hook_question="Where does it go?", answer="-", youtube_title="Example hook",
                        hook=shots, chapters=[], mood="energetic", hook_music="spy-pulse")
    cfg = replace(cfg, hook_pictures=False, ai_music=False, captions=False, long_minutes=9)
    try:
        from .variety import pick_look
        props = _render_hook(cfg, script, template, work, dict(pick_look(cfg, 7)), 7, (0.0, 600.0), 0, progress,
                             "Example hook", cfg.fps)
        del props
        move(work / "hook.mp4", out)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return out
