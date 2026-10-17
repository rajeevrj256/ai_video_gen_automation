"""Re-make a finished video with another voice and/or subtitles on or off.

Keeps the script, graphics and (for Shorts) the same footage clips; only the voiceover is
recorded again and the video rendered again. No Claude calls, so no tokens.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Callable

import requests

from .config import Config
from .fsutil import move

log = logging.getLogger(__name__)
Progress = Callable[[str], None]


def made_pace(cfg: Config, report: dict) -> str:
    """The pace a video was spoken at: its report's, else (videos made before it was saved) what that kind of video
    used then: the Shorts' pace setting for the free voices, a Sarvam voice's own pace (+0%)."""
    if report.get("voice_rate"):
        return report["voice_rate"]
    return "+0%" if str(report.get("voice", "")).startswith("sarvam:") else cfg.voice_rate


def _settings(cfg: Config, report: dict, voice: str | None, pace: str | None,
              captions: bool | None) -> tuple[Config, str, str, bool]:
    """The settings a re-make (or its demo) uses: (cfg, pace, the pace it was made at, whether a pace was picked)."""
    cfg = replace(cfg, captions=report.get("captions", True) if captions is None else captions)
    old_pace = made_pace(cfg, report)
    chosen = bool(pace and re.fullmatch(r"[+-]\d{1,2}%", pace))  # a speed picked: the voice is recorded again
    pace = pace if chosen else old_pace
    if report.get("format") == "long":
        cfg = replace(cfg, long_voice=voice or report.get("voice") or cfg.long_voice, long_voice_rate=pace)
    else:
        cfg = replace(cfg, voice=voice or report.get("voice") or cfg.voice, voice_rate=pace)
    return cfg, pace, old_pace, chosen


def rerender(cfg: Config, folder: Path, voice: str | None = None, captions: bool | None = None,
             progress: Progress = log.info, pace: str | None = None) -> dict:
    """`pace` ('-10%', '+0%'...): the same voice spoken slower or faster, everything else kept (the user: "re-edit
    only speed")."""
    report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
    long = report.get("format") == "long"
    cfg, pace, old_pace, chosen = _settings(cfg, report, voice, pace, captions)
    if pace != old_pace:
        progress(f"Speaking pace {old_pace} → {pace}")
    work = folder / "_rerender"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    try:
        same_voice = (not voice or voice == report.get("voice")) and not chosen
        info = (_long(cfg, folder, work, report, progress, same_voice) if long
                else _short(cfg, folder, work, progress))
        progress("Replacing the video")
        move(work / "reel.mp4", folder / "reel.mp4.new")
        (folder / "reel.mp4").unlink(missing_ok=True)
        move(folder / "reel.mp4.new", folder / "reel.mp4")
        if not long and (work / "props.json").exists():  # the new timings, for recording your own voice
            move(work / "props.json", folder / "props.json")
        if (work / "thumbnail.jpg").exists():
            move(work / "thumbnail.jpg", folder / "thumbnail.jpg.new")
            (folder / "thumbnail.jpg").unlink(missing_ok=True)
            move(folder / "thumbnail.jpg.new", folder / "thumbnail.jpg")
        if long and not same_voice:  # the new voice and sounds go with the new props.json (subtitles-only re-makes,
            for sub in MEDIA_DIRS:  # sound removal and My voice read them from the folder)
                if (work / sub).is_dir():
                    shutil.rmtree(folder / sub, ignore_errors=True)
                    move(work / sub, folder / sub)
        shutil.rmtree(folder / DEMOS, ignore_errors=True)  # demos of the old edit
        report.update(info, voice=cfg.long_voice if long else cfg.voice, captions=cfg.captions, voice_rate=pace)
        (folder / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        progress("Done")
        return report
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _short(cfg: Config, folder: Path, work: Path, progress: Progress) -> dict:
    from .script_writer import ReelScript
    from .video import render_video
    from .visuals import fetch_backgrounds
    from .voice import synthesize_scenes

    data = json.loads((folder / "script.json").read_text(encoding="utf-8"))
    for field in ("subject", "hook_question", "answer"):  # scripts from before these fields
        data.setdefault(field, "")
    data.setdefault("category", "Life & People")
    script = ReelScript.model_validate(data)
    from .config import MAX_SECONDS
    from .video import voice_seconds

    progress(f"Recording voiceover ({cfg.voice})")
    rate = int(re.sub(r"[^\d-]", "", cfg.voice_rate) or 0)
    for _ in range(3):  # a slower voice can push a Short past 30s: speak a little faster instead
        scenes = synthesize_scenes([s.narration for s in script.scenes], cfg.voice, work / "audio",
                                   cfg.tts_engine, cfg.kokoro_voice, f"{rate:+d}%")
        if voice_seconds(scenes) <= MAX_SECONDS - 1:
            break
        rate += 6
        shutil.rmtree(work / "audio", ignore_errors=True)
        progress(f"That voice runs long; recording again at {rate:+d}% speed")
    progress("Downloading footage")
    backgrounds = _same_footage(folder, work, len(script.scenes))
    if backgrounds is None:  # videos made before links were saved: search again with the same queries
        backgrounds = fetch_backgrounds([s.visual_queries for s in script.scenes], cfg.pexels_api_key,
                                        cfg.width, cfg.height, work / "backgrounds")
    progress("Editing the video (takes a few minutes)")
    from .pipeline import _render_slot
    with _render_slot(cfg):  # one edit at a time: two renders only slow each other down
        rendered = render_video(script.title, scenes, backgrounds, cfg, work / "reel.mp4",
                                graphics=[s.graphic for s in script.scenes],
                                transitions=[s.transition for s in script.scenes],
                                sounds=[s.sounds for s in script.scenes], music=script.music,
                                music_file=_kept_music(folder))
    return {"duration_seconds": rendered["duration_seconds"], "editor": rendered.get("editor", "")}


def _kept_music(folder: Path) -> Path | None:
    """A Short's own music track, so a re-make sounds the same (it is composed new for every video)."""
    try:
        name = json.loads((folder / "props.json").read_text(encoding="utf-8")).get("music")
    except (OSError, ValueError):
        return None
    return folder / name if name and (folder / name).exists() else None


def _same_voice_props(folder: Path, work: Path, cfg: Config, music_name: str) -> dict | None:
    """The saved edit with only the subtitles switched, when its voice and sound files are still
    there: no new voiceover, so the timings (and YouTube chapters) stay exactly the same."""
    path = folder / "props.json"
    if not path.exists():
        return None
    props = json.loads(path.read_text(encoding="utf-8"))
    captions = props.get("all_captions", props.get("captions") or [])
    if cfg.captions and not captions:
        return None  # made with subtitles off and no saved lines: record again to get word timings
    files = [b["audio"] for b in props.get("beats", []) if b.get("audio")] + [c["src"] for c in props.get("cues", [])]
    files += [v for v in (props.get("sfx") or {}).values()] + [a["src"] for a in props.get("ambience", [])]
    files += [x for x in ((props.get("hook") or {}).get("music"),) if x]
    files += [x["audio"] for x in (props.get("hook") or {}).get("shots", []) if x.get("audio")]
    files += [x["visual"]["src"] for x in (props.get("hook") or {}).get("shots", []) if x["visual"].get("src")]
    look = props.get("look") or {}  # the background photos, as drawn and as prepared
    files += [x for x in [*(look.get("plates") or {}).values(), look.get("hookPlate"),
                          *(look.get("platesBaked") or {}).values()] if x]
    if props.get("musicFrom") is not None and props.get("music"):
        files.append(props["music"])  # composed tracks are kept with the video
    files += [b["visual"]["src"] for b in props.get("beats", []) if b["visual"].get("src")]
    if not all((folder / f).exists() for f in files):
        return None
    for f in files:  # the render reads everything from its own folder
        (work / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(folder / f, work / f)
    if props.get("music"):  # finished videos made before it was kept: make or copy the same track again
        if (folder / props["music"]).exists():
            shutil.copy(folder / props["music"], work / props["music"])
        else:
            from .media import pick_music
            track = pick_music(cfg, music_name, work, props["duration"])
            props["music"] = track.relative_to(work).as_posix() if track else None
    props["captions"] = captions if cfg.captions else []
    props["all_captions"] = captions
    return props


def _same_footage(folder: Path, work: Path, count: int) -> list[list[Path]] | None:
    path = folder / "footage.json"
    if not path.exists():
        return None
    sources = json.loads(path.read_text(encoding="utf-8"))
    if len(sources) != count or not any(url for row in sources for url in row):
        return None
    out_dir = work / "backgrounds"
    out_dir.mkdir(parents=True, exist_ok=True)
    result = []
    for i, row in enumerate(sources):
        clips = []
        for j, url in enumerate(row):
            if not url:
                continue
            dest = out_dir / f"bg_{i:02d}_{j}.mp4"
            try:
                with requests.get(url, stream=True, timeout=60) as dl:
                    dl.raise_for_status()
                    with open(dest, "wb") as fh:
                        for block in dl.iter_content(1 << 20):
                            fh.write(block)
                clips.append(dest)
            except requests.RequestException as exc:
                log.warning("Couldn't download the same clip again (%s)", exc)
        if not clips:
            from .visuals import gradient_image
            clips.append(gradient_image(1080, 1920, out_dir / f"gradient_{i:02d}.png", seed=i))
        result.append(clips)
    return result


# The finished video's own files a re-make reuses (longform.build_long `remake`).
KEEP = ("hook-pictures", "plates", "footage", "music", "models", "memes")
# Every folder of a long video's files; a re-make that recorded a new voice replaces them with its own.
MEDIA_DIRS = KEEP + ("audio", "sfx")


def _remake_look(cfg: Config, old: dict) -> tuple[Config, dict | None]:
    """The finished video's look for a re-make, with its hook music style and AI music genre (kept in the look since
    the speed re-edit; read from the props for older videos), and real memes taken from the cache they came from."""
    look = old.get("look")
    if look is not None:
        look = dict(look)
        look.setdefault("hookStyle", (old.get("hook") or {}).get("style") or "")  # videos made before it was kept
        ai = next((p.get("name", "") for p in old.get("musicParts") or [] if p.get("name", "").startswith("AI music (")), "")
        if ai:
            look.setdefault("aiGenre", ai[len("AI music ("):-1])
    visuals = [b.get("visual") or {} for b in old.get("beats", [])] + [
        s.get("visual") or {} for s in (old.get("hook") or {}).get("shots", [])]
    if any(v.get("webName") for v in visuals):  # real memes: from the cache they were fetched into
        cfg = replace(cfg, meme_source="web")
    return cfg, look


def _long(cfg: Config, folder: Path, work: Path, report: dict, progress: Progress, same_voice: bool = False) -> dict:
    from .longform import FFMPEG, HOOK_SECONDS, SCRIPT_HOOK_SECONDS, LongScript, build_long, youtube_chapters
    from .pipeline import _render_slot
    from .video import _remotion_cli, _render_remotion

    script = LongScript.model_validate_json((folder / "script.json").read_text(encoding="utf-8"))
    props = _same_voice_props(folder, work, cfg, script.music) if same_voice else None
    if props is None:
        old_path = folder / "props.json"
        old = json.loads(old_path.read_text(encoding="utf-8")) if old_path.exists() else {}
        cfg, look = _remake_look(cfg, old)
        # Everything the video was made with, so only the voice is new: nothing drawn, generated or searched again.
        for sub in KEEP:
            if (folder / sub).is_dir():
                shutil.copytree(folder / sub, work / sub, dirs_exist_ok=True)
        hook_seconds = SCRIPT_HOOK_SECONDS if report.get("source") == "script" else HOOK_SECONDS
        progress("Recording the voice again and re-timing the same edit to it (the pictures, footage, memes and music "
                 "stay)")
        props = build_long(script, cfg, work, progress, look=look, hook_seconds=hook_seconds, remake=True)
    else:
        progress("Same voice: keeping the recorded voiceover and timings, only the subtitles change")
    cli = _remotion_cli()
    if cli is None:
        raise RuntimeError("Node.js or the Remotion packages are not installed (run start.bat / start.sh)")
    slot = _render_slot(cfg)
    if not slot.acquire(blocking=False):  # one edit at a time: two renders only slow each other down
        progress("Waiting for the editor: another video is being edited")
        slot.acquire()
    try:
        progress(f"Editing the video ({props['duration'] / 60:.1f} min of animation; this takes a while)")
        _render_remotion(cli, props, work / "reel.mp4", composition="Long", crf=18, progress=progress)
    finally:
        slot.release()
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", "3", "-i", str(work / "reel.mp4"), "-frames:v", "1",
                    "-q:v", "3", str(work / "thumbnail.jpg")], check=False)
    (folder / "props.json").write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
    # A new voice changes the timings, so the YouTube chapter stamps change too.
    if report.get("source") == "script":  # your description stays as written; the stamps are separate
        return {"duration_seconds": round(props["duration"], 1),
                "chapters": [{"title": c["title"], "start": c["start"]} for c in props["chapters"]],
                "youtube_chapters": youtube_chapters(props)}
    description = re.split(r"\n\nChapters:\n", report.get("youtube_description", ""), maxsplit=1)[0]
    return {"duration_seconds": round(props["duration"], 1),
            "chapters": [{"title": c["title"], "start": c["start"]} for c in props["chapters"]],
            "youtube_description": description + "\n\nChapters:\n" + youtube_chapters(props)}


# ---------- a demo before re-making (the video page's "Try it first") ----------
# The user: "add demo as well of 15-20 sec of original video acc to setting so i can decide which is best". The story's
# first lines (right after the hook, where the narration's pace is heard) are spoken with the chosen voice and speed
# and edited exactly as the re-make would (build_long `remake`), into `demos/<key>.mp4`; the page plays it next to the
# same lines of the finished video. Only the files those lines use are copied in: nothing is drawn, generated or
# downloaded, no Claude.

DEMOS = "demos"
DEMO_SECONDS = 15  # at least this much of the finished video's lines; a demo ends on a line, so about 15-20 s


def demo_window(script, old: dict) -> tuple[int, float, float] | None:
    """(lines, start, end): how many of the story's lines the demo speaks, and where they are in the finished video
    (seconds). None when the saved edit doesn't match the script (an older video)."""
    beats = old.get("beats") or []
    if not beats or len(beats) != sum(len(c.beats) for c in script.chapters):
        return None
    total, k = 0.0, 0
    while k < len(beats) and total < DEMO_SECONDS:
        total += float(beats[k]["duration"])
        k += 1
    return k, round(float(beats[0]["start"]), 3), round(float(beats[k - 1]["start"]) + float(beats[k - 1]["duration"]), 3)


def demo_key(voice: str, pace: str, captions: bool) -> str:
    import hashlib

    return hashlib.sha1(f"{voice}|{pace}|{captions}".encode("utf-8")).hexdigest()[:10]


def demos(folder: Path) -> list[dict]:
    """The demos already made for this video (newest first)."""
    out = []
    for f in (folder / DEMOS).glob("*.json") if (folder / DEMOS).is_dir() else []:
        try:
            info = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (folder / DEMOS / f"{f.stem}.mp4").exists():
            out.append(info)
    return sorted(out, key=lambda d: d.get("made", ""), reverse=True)


def _demo_files(folder: Path, work: Path, chapters: int, lines: int) -> None:
    """Copy in only what the demo's lines use: background photos, their footage clips and meme files, and their
    chapters' AI music. Copies, never links: the edit writes files with these names again (prepared photos, music)."""
    def take(pattern: str, sub: str) -> None:
        for f in (folder / sub).glob(pattern) if (folder / sub).is_dir() else []:
            if f.is_file() and not f.stem.endswith(("-bg", "-mx", "-lv")):
                (work / sub).mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, work / sub / f.name)

    take("*.jpg", "plates")
    take("*.url", "plates")
    for i in range(lines):
        take(f"beat{i:03d}.*", "footage")
        take(f"beat{i:03d}.*", "memes")
    for c in range(chapters):
        take(f"ai-ch{c:02d}.*", "music")


def demo(cfg: Config, folder: Path, voice: str | None = None, pace: str | None = None, captions: bool | None = None,
         progress: Progress = log.info) -> dict:
    """A 15-20 s demo of a long, medium or Script video with another voice, speed or subtitles: its info
    (`demos/<key>.json`: key, voice, pace, captions, seconds, the same lines' place in the finished video)."""
    from datetime import datetime

    from .longform import LongScript, build_long
    from .video import _remotion_cli, _render_remotion

    report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
    if report.get("format") != "long" or report.get("source") in ("shoot", "stick", "anim", "toon", "storyshorts"):
        raise ValueError("Demos are made for long, medium and Script videos")
    if not (folder / "props.json").exists() or not (folder / "script.json").exists():
        raise ValueError("This video's edit wasn't saved with it, so a demo can't be cut from it")
    script = LongScript.model_validate_json((folder / "script.json").read_text(encoding="utf-8"))
    old = json.loads((folder / "props.json").read_text(encoding="utf-8"))
    window = demo_window(script, old)
    if window is None:
        raise ValueError("This video's saved edit doesn't match its script, so a demo can't be cut from it")
    lines, start, end = window
    cfg, pace, _, _ = _settings(cfg, report, voice, pace, captions)
    cfg, look = _remake_look(cfg, old)
    key = demo_key(cfg.long_voice, pace, cfg.captions)
    chapters, left = [], lines
    for ch in script.chapters:  # the story's first lines, chapter by chapter
        if left <= 0:
            break
        chapters.append(ch.model_copy(update={"beats": ch.beats[:left]}))
        left -= len(chapters[-1].beats)
    short = script.model_copy(update={"hook": [], "chapters": chapters})
    work = folder / DEMOS / f"_{key}"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    try:
        _demo_files(folder, work, len(chapters), lines)
        progress(f"Recording {lines} lines at {pace}")
        props = build_long(short, cfg, work, progress, look=look, remake=True)
        cli = _remotion_cli()
        if cli is None:
            raise RuntimeError("Node.js or the Remotion packages are not installed (run start.bat / start.sh)")
        progress(f"Editing the demo ({props['duration']:.0f} s)")
        _render_remotion(cli, props, work / "reel.mp4", composition="Long", crf=20, progress=progress)
        move(work / "reel.mp4", folder / DEMOS / f"{key}.mp4")
        info = {"key": key, "voice": cfg.long_voice, "pace": pace, "captions": cfg.captions,
                "seconds": round(float(props["duration"]), 1), "lines": lines, "original": [start, end],
                "made": datetime.now().isoformat(timespec="seconds")}
        (folder / DEMOS / f"{key}.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
        return info
    finally:
        shutil.rmtree(work, ignore_errors=True)
