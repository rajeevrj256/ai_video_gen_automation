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


def rerender(cfg: Config, folder: Path, voice: str | None = None, captions: bool | None = None,
             progress: Progress = log.info) -> dict:
    report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
    long = report.get("format") == "long"
    cfg = replace(cfg, captions=report.get("captions", True) if captions is None else captions)
    if long:
        cfg = replace(cfg, long_voice=voice or report.get("voice") or cfg.long_voice)
    else:
        cfg = replace(cfg, voice=voice or report.get("voice") or cfg.voice)
    work = folder / "_rerender"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    try:
        info = _long(cfg, folder, work, report, progress) if long else _short(cfg, folder, work, progress)
        progress("Replacing the video")
        move(work / "reel.mp4", folder / "reel.mp4.new")
        (folder / "reel.mp4").unlink(missing_ok=True)
        move(folder / "reel.mp4.new", folder / "reel.mp4")
        if (work / "thumbnail.jpg").exists():
            move(work / "thumbnail.jpg", folder / "thumbnail.jpg.new")
            (folder / "thumbnail.jpg").unlink(missing_ok=True)
            move(folder / "thumbnail.jpg.new", folder / "thumbnail.jpg")
        report.update(info, voice=cfg.long_voice if long else cfg.voice, captions=cfg.captions)
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
    rendered = render_video(script.title, scenes, backgrounds, cfg, work / "reel.mp4",
                            graphics=[s.graphic for s in script.scenes],
                            transitions=[s.transition for s in script.scenes])
    return {"duration_seconds": rendered["duration_seconds"], "editor": rendered.get("editor", "")}


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


def _long(cfg: Config, folder: Path, work: Path, report: dict, progress: Progress) -> dict:
    from .longform import FFMPEG, LongScript, build_long, youtube_chapters
    from .video import _remotion_cli, _render_remotion

    script = LongScript.model_validate_json((folder / "script.json").read_text(encoding="utf-8"))
    props = build_long(script, cfg, work, progress)
    progress(f"Editing the video ({props['duration'] / 60:.1f} min of animation; this takes a while)")
    cli = _remotion_cli()
    if cli is None:
        raise RuntimeError("Node.js or the Remotion packages are not installed (run start.bat / start.sh)")
    _render_remotion(cli, props, work / "reel.mp4", composition="Long", crf=18, timeout=4 * 3600)
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", "3", "-i", str(work / "reel.mp4"), "-frames:v", "1",
                    "-q:v", "3", str(work / "thumbnail.jpg")], check=False)
    (folder / "props.json").write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
    # A new voice changes the timings, so the YouTube chapter stamps change too.
    description = re.split(r"\n\nChapters:\n", report.get("youtube_description", ""), maxsplit=1)[0]
    return {"duration_seconds": round(props["duration"], 1),
            "chapters": [{"title": c["title"], "start": c["start"]} for c in props["chapters"]],
            "youtube_description": description + "\n\nChapters:\n" + youtube_chapters(props)}
