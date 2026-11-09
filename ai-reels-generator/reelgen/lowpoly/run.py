"""The low-poly job: write the story, record the narration, time it, mix the soundtrack, render, check, file it in the
library. Each step is saved (lowpoly-checkpoint.json), so Pause or a crash continues from the last finished step."""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..config import Config
from ..fsutil import move
from ..video import FFMPEG
from . import story as S
from .mix import mix
from .timeline import WORDS, build, spoken

log = logging.getLogger(__name__)
CHECKPOINT = "lowpoly-checkpoint.json"
DEFAULT_VOICE = "en-US-ChristopherNeural"  # calm and low, like the original's narrator
OVER = 1.08  # a Short may run this much over its length before it is tightened
TIGHT_TAIL = 0.2  # the breath after each line when a Short runs long (else timeline.TAIL)
MAX_FASTER = 18  # at most this much faster than asked (percent)


OLD_MARK = "life of a man"  # the channel name every video got by default before


@dataclass
class LowPolyRequest:
    topic: str = ""  # the struggle (life) or the user's whole brief (fiction, any length); empty = Claude picks
    kind: str = "life"  # life (a small everyday struggle, narrated) | fiction (the user's brief: dialogue, powers, action)
    format: str = "short"  # short (9:16, `seconds`) | film (`minutes`, 16:9 unless `vertical`)
    seconds: int = 35  # Short: 20-60 (the original runs 33 s)
    minutes: float = 3.5  # film: 2.5-15 (over 5: written as an outline, then act by act)
    vertical: bool = False  # film only: 9:16 instead of 16:9
    voice: str = ""  # '' = DEFAULT_VOICE
    pace: int = 0  # speaking speed in percent (-20..+20)
    watermark: str = ""  # the channel's name at the top ('' = none, the default)
    dof: bool = True  # depth of field (off renders faster on a slow machine)
    words: str = "on"  # words on screen: on (subtitles + time stamps, like the original) | stamps (time stamps only) | off
    people: list[str] = field(default_factory=list)  # 🎭 cast intro (kind 'intro'): who, 'hero' for him; empty = everyone
    hero_name: str = "Ethan"  # 🎭 his name on his card
    film_title: str = "The Unwritten"  # 🎭 the film's name on the closing poster ('' = the intro's own title)
    hero_look: str = "classic"  # 🧪 classic = the code-built man (as before) | model = the 3D model of him (HERO_MODEL)


# 🧪 The 3D model of him (branch claude/lowpoly-3d-ethan; the user: "lets do for one char and animation ethan ... not
# delete old code or old style of ethan"): made by an image-to-3D generator from an A-pose picture of him, given a
# skeleton by the editor (remotion/src/lowpoly/Model.tsx SKELETONS['ethan']). Chosen per video (`hero_look`); the
# classic code-built man stays the default and every other person keeps the classic body.
HERO_MODEL = "ethan"
MODELS = Path(__file__).parent / "models"


def use_model(props: dict, work: Path, look: str) -> None:
    """With `look` 'model': him drawn as the 3D model (the file copied next to props.json, the render's public folder)."""
    if look != "model" or not (MODELS / f"{HERO_MODEL}.glb").exists():
        return
    (work / "models").mkdir(parents=True, exist_ok=True)
    shutil.copy2(MODELS / f"{HERO_MODEL}.glb", work / "models" / f"{HERO_MODEL}.glb")
    hero = props.get("cast", {}).get("hero")
    if hero is not None:
        hero["model"] = HERO_MODEL


def _thumb_time(props: dict) -> float:
    """A face close-up near the middle, else 40% in."""
    shots = props["shots"]
    if shots and shots[-1].get("poster"):  # a cast intro: its closing poster, once the title is on
        return shots[-1]["start"] + min(2.5, shots[-1]["duration"] - 0.5)
    for s in shots[len(shots) // 3:] + shots[: len(shots) // 3]:
        if s["camera"] in ("face", "face-top"):
            return s["start"] + s["duration"] * 0.5
    return props["duration"] * 0.4


def speaker_key(speaker: str) -> str:
    sp = (speaker or "narrator").strip()
    return "hero" if sp == "hero" else "narrator" if sp == "narrator" else S._key(sp)


def _record(cfg: Config, story: S.Story, req: LowPolyRequest, work: Path, progress, pace: int, take: str = "audio") -> dict[int, dict]:
    """Every line in its speaker's voice: the narrator's (the one chosen), his own, each person's (S.voices_for); the
    lines of one voice are recorded together."""
    from ..verify import probe
    from ..voice import synthesize_scenes

    idx = [i for i, s in enumerate(story.shots) if s.line.strip()]
    narrator = req.voice.strip() or DEFAULT_VOICE
    voices = S.voices_for(story, narrator)
    groups: dict[str, list[int]] = {}
    for i in idx:
        groups.setdefault(voices.get(speaker_key(story.shots[i].speaker), narrator), []).append(i)
    rate = f"{max(-30, min(30, int(pace))):+d}%"
    who = narrator.split(":")[-1] if len(groups) == 1 else f"{len(groups)} voices"
    what = "narration" if len(groups) == 1 else "voices"
    progress(f"Recording the {what} ({len(idx)} lines, {who}, {rate})")
    # who speaks in each voice, for the progress lines (a film's voices took minutes with one unchanging line)
    names = {"narrator": "the narrator", "hero": "him", **{S._key(c.name): c.name for c in story.cast}}
    speaking = {}
    for key, v in voices.items():
        speaking.setdefault(v, []).append(names.get(key, key))
    out, before, said = {}, 0, [time.monotonic()]
    for n, (voice, items) in enumerate(groups.items()):
        folder = work / take if len(groups) == 1 else work / take / f"voice{n}"
        if len(groups) > 1:
            progress(f"Recording the voices: {' / '.join(speaking.get(voice, [voice]))} ({n + 1} of {len(groups)}, "
                     f"{len(items)} line{'s' if len(items) != 1 else ''}; {before} of {len(idx)} done)")
            said[0] = time.monotonic()

        def tick(done: int, total: int, before: int = before) -> None:
            if time.monotonic() - said[0] >= 15 and done < total:  # a long narration: a line every 15 s
                said[0] = time.monotonic()
                progress(f"Recording the {what}: {before + done} of {len(idx)} lines done")

        takes = synthesize_scenes([story.shots[i].line.strip() for i in items], voice, folder, cfg.tts_engine, cfg.kokoro_voice,
                                  rate, on_take=tick)
        before += len(items)
        for i, tk in zip(items, takes):
            secs = float(probe(tk.path).get("duration") or 0) or (tk.words[-1].end if tk.words else 1.0)
            out[i] = {"path": str(tk.path), "seconds": round(secs, 3), "voice": voice,
                      "words": [[w.text, round(w.start, 3), round(w.end, 3)] for w in tk.words]}
    return out


def run_lowpoly(cfg: Config, req: LowPolyRequest, progress, resume: str | None = None) -> dict:
    from ..llm import meter_records, summarize_usage
    from ..pipeline import _render_slot, pause_point, slugify
    from ..sticky.render import render
    from ..verify import probe

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    work = cfg.output_dir / resume if resume else cfg.output_dir / f"{stamp}-{uuid.uuid4().hex[:4]}-lowpoly-working"
    work.mkdir(parents=True, exist_ok=True)
    progress(f"Saving progress in {work.name}")
    ck = work / CHECKPOINT
    state = json.loads(ck.read_text(encoding="utf-8")) if ck.exists() else {"stage": "", "stamp": stamp, "request": asdict(req)}
    stamp = state.get("stamp", stamp)

    def save(stage: str) -> None:
        state["stage"] = stage
        ck.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    intro = req.kind == "intro"  # 🎭 the cast introduced one by one (intro.py): a film, music only
    short = req.format != "film" and not intro
    fiction = req.kind == "fiction"
    vertical = short or bool(req.vertical)
    seconds = max(20, min(60, int(req.seconds)))
    minutes = max(2.5, min(15.0, float(req.minutes)))
    story_path = work / "story.json"
    board = state.get("board")  # ✍ a storyboard the user read and approved (boards.py)
    if board and not state.get("board_said"):
        progress(f"Building the storyboard you approved: '{board.get('title', '')}'"
                 + ("" if story_path.exists() else " (its acts are written now from the outline you read)"))
        state["board_said"] = True
    if story_path.exists():
        story = S.load(story_path)
    elif intro:
        from . import intro as I

        story = I.write(cfg, req.people, req.seconds, req.hero_name, progress, film_title=req.film_title)
        S.lock_cast(cfg, story)
        S.save(story, story_path)
        save("written")
    else:
        about = req.topic.strip()
        about = (about[:90] + "...") if len(about) > 90 else about
        progress(f"Claude is writing the {'fiction ' if fiction else ''}{'Short' if short else 'film'} "
                 f"({f'{seconds} s' if short else f'{minutes:g} min'}{', about ' + about if about else ''})")
        story = S.write(cfg, req.topic.strip(), short=short, seconds=seconds, minutes=minutes, progress=progress, kind=req.kind,
                        save_to=work / "story-parts.json")
        S.lock_cast(cfg, story)
        S.save(story, story_path)
        S.remember(cfg, story)
        save("written")
    restaging = state.get("restage")
    if restaging and not restaging.get("done"):  # 🎬 New angles: the same words, new pictures (prepare_restage)
        if restaging.get("mode") == "storyboard":
            progress("Claude is writing the new storyboard: new camera angles and staging for the same words")
            story = S.restage(cfg, story, progress)
        elif restaging.get("mode") == "same":
            progress("The same shots and cameras, made again with the newest editor")
        else:
            progress("A new camera angle for every shot (the same staging, words, voices and music)")
            story = S.new_angles(story, int(restaging.get("seed", 1)))
        S.save(story, story_path)
        restaging["done"] = True
        save("restaged")
    notes = S.repair(story)
    pause_point()
    audio = {int(k): v for k, v in state.get("audio", {}).items()}
    # a re-make keeps the first version's seed: the same composed music and walk rhythm
    seed = int(state.get("seed") or uuid.uuid5(uuid.NAMESPACE_DNS, story.title + stamp).int % 100000)
    look = dict(vertical=vertical, watermark="" if req.watermark.strip().lower() == OLD_MARK else req.watermark.strip(), seed=seed, words=req.words if req.words in WORDS else "on")
    if (not audio and any(x.line.strip() for x in story.shots)) or not all(Path(v["path"]).exists() for v in audio.values()):
        pace = int(req.pace)
        audio = _record(cfg, story, req, work, progress, pace)
        if short:  # a Short keeps to its length: breaths tightened first, then spoken a little faster once
            full = build(story, audio, **look)[0]["duration"]
            tight = build(story, audio, tail=TIGHT_TAIL, pauses=0.5, **look)[0]["duration"]
            if tight > seconds * OVER:
                speech = sum(spoken(a) for a in audio.values())
                faster = min(MAX_FASTER, int(round((speech / max(1.0, speech - (tight - seconds)) - 1) * 100)) + 2)
                progress(f"It runs {full:.0f} s for {seconds} s: recording it {faster}% faster")
                pace = int(req.pace) + faster
                audio = _record(cfg, story, req, work, progress, pace, "audio-fast")
            state["pace"] = pace
        state["audio"] = audio
        save("voiced")
    pause_point()
    tighten = {}
    if short and build(story, audio, **look)[0]["duration"] > seconds * OVER:
        tighten = {"tail": TIGHT_TAIL, "pauses": 0.5}
    props, clips, cues, sections = build(story, audio, **look, **tighten)
    props["dof"] = bool(req.dof)
    use_model(props, work, getattr(req, "hero_look", "classic"))
    progress(f"'{story.title}': {len(props['shots'])} shots, " + (f"{props['duration']:.0f} s" if props["duration"] < 90 else
             f"{props['duration'] / 60:.1f} min") + f", {'9:16' if vertical else '16:9'} · {story.problem}")
    soundtrack = work / "soundtrack.wav"
    mixed = state.get("mix") if soundtrack.exists() else None
    if not mixed:
        progress("Making the music and the sound")
        brief = (f"cinematic main-title theme for a movie's cast introduction, each character revealed in turn, building; {story.music_prompt}"
                 if story.intro else f"cinematic film score for an animated sci-fi short film: {story.problem}; {story.music_prompt}" if story.kind == "fiction"
                 else f"soft score for a narrated low-poly animated short about {story.problem}; {story.music_prompt}")
        mix_cfg = cfg
        if restaging and not str(restaging.get("music", "")).startswith("AI music"):
            import dataclasses  # a re-make keeps its first version's music: composed music stays composed

            mix_cfg = dataclasses.replace(cfg, ai_music=False)
        mixed = mix(mix_cfg, props, clips, cues, sections, work, soundtrack, seed, progress, brief, fiction=story.kind == "fiction")
        state["mix"] = mixed
        save("mixed")
    pause_point()
    out = work / "reel.mp4"
    if state.get("stage") != "rendered" or not out.exists():
        progress("Editing the Short" if short else "Editing the film")
        with _render_slot(cfg):
            render(props, soundtrack, work, out, progress, composition="LowPoly")
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", f"{_thumb_time(props):.2f}", "-i", str(out), "-frames:v", "1",
                        "-q:v", "3", str(work / "thumbnail.jpg")], check=False)
        save("rendered")
    progress("Checking the video")
    info = probe(out)
    issues = []  # (the storyboard fixes `repair` made are staging the editor did itself, not faults: report "staging_fixes")
    size = (1080, 1920) if vertical else (1920, 1080)
    if (info.get("width"), info.get("height")) != size:
        issues.append(f"Resolution is {info.get('width')}x{info.get('height')}, expected {size[0]}x{size[1]}.")
    if not info.get("has_audio"):
        issues.append("No audio track.")
    if abs(float(info.get("duration") or 0) - props["duration"]) > 2:
        issues.append(f"The video runs {info.get('duration')} s, the timeline {props['duration']:.1f} s.")
    if short and props["duration"] > 62:
        issues.append(f"The Short runs {props['duration']:.0f} s (over a minute).")
    # every line's take, so a later re-make (🎬 New angles) reuses the voices exactly
    (work / "audio.json").write_text(json.dumps({str(k): {**v, "path": str(Path(v["path"]).relative_to(work)) if Path(v["path"]).is_relative_to(work)
                                                         else v["path"]} for k, v in audio.items()}, ensure_ascii=False), encoding="utf-8")
    ck.unlink(missing_ok=True)
    final = cfg.output_dir / f"{stamp}-{slugify(story.title.strip('. '))}-lowpoly{'-short' if short else '-intro' if intro else ''}{('-again' if restaging.get('mode') == 'same' else '-angles') if restaging else ''}"
    move(work, final)
    narration = " ".join(s.line.strip() for s in story.shots if s.line.strip())
    report = {
        "id": final.name, "format": "short" if vertical else "long",  # (the page shapes its player by this: a 9:16 film was filed as long) "length": "short" if short else "lowpoly",
        "source": "lowpoly", "topic": story.problem, "topic_source": req.topic.strip() and "your topic" or "Claude's pick",
        "style": "story", "category": "Life & People", "title": story.title.strip(), "why_chosen": story.problem,
        "narration": narration, "created_at": stamp, "verified": not issues, "score": None, "issues": issues,
        "checks": {"probe": info}, "attempts": 1, "video": str(final / "reel.mp4"), "thumbnail": str(final / "thumbnail.jpg"),
        "duration_seconds": round(props["duration"], 1), "editor": "remotion (LowPoly)", "captions": look["words"] == "on", "words_on_screen": look["words"],
        "sound_levels": mixed.get("levels"), "mix_version": mixed.get("mix_version"),
        "voice": req.voice.strip() or DEFAULT_VOICE, "voice_rate": f"{int(state.get('pace', req.pace)):+d}%", "music": mixed.get("music", ""),
        "sound_cues": mixed.get("sound_cues"), "lowpoly_request": asdict(req), "thumbnail_text": story.thumbnail_text,
        "cast": [c.name for c in story.cast], "story_kind": "intro" if story.intro else story.kind, "storyboard": board, "hero_look": "3D model (ethan)" if props["cast"].get("hero", {}).get("model") else "classic", "staging_fixes": notes,
        "designed": [m.name for m in story.made],
        "cast_intro": [{"name": c.name, "role": c.role, "seconds": round(c.seconds * c.shots, 2)} for c in story.intro] or None,
        "voices": sorted({a.get("voice", "") for a in audio.values()} - {""}), "youtube_title": story.youtube_title[:100], "youtube_description": story.description.strip(),
        "youtube_tags": story.tags, "youtube_hashtags": story.hashtags[:3], "caption": story.description.strip(),
        "hashtags": story.hashtags,
    }
    if restaging:
        report.update({"restaged_from": restaging.get("from"), "restaged_from_title": restaging.get("title"),
                       "restage_mode": restaging.get("mode")})
    rel = [{**c, "path": str(Path(c["path"]).relative_to(work)) if Path(c["path"]).is_relative_to(work) else c["path"]} for c in clips]
    (final / "props.json").write_text(json.dumps({**props, "clips": rel, "cues": cues, "sections": sections}, ensure_ascii=False), encoding="utf-8")
    report["usage"] = summarize_usage(meter_records())
    (final / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    progress("Done" if not issues else "Done, but it did not pass every check: review before posting")
    return report


RESTAGE_MODES = ("storyboard", "angles", "same")  # same = the very same shots, made again with the newest editor
KEEP_FOR_RESTAGE = ("audio", "audio-fast", "music")  # the first version's voices and music tracks


def prepare_restage(cfg: Config, folder: Path, mode: str) -> str:
    """🎬 New angles: a new unfinished low-poly video made from a finished one, to be carried on by `run_lowpoly` like a
    resumed one (so Pause, Stop and Resume work). It gets the first version's story, its voices (audio.json; a video
    made before that is recorded again with the same voices and speed), its music tracks and its seed, and in its
    checkpoint the re-staging to do: 'storyboard' (Claude stages every shot again) or 'angles' (a new camera per shot,
    no Claude). The first version is never touched; the new one is its own video."""
    import shutil

    report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
    props = json.loads((folder / "props.json").read_text(encoding="utf-8"))
    if report.get("source") != "lowpoly" or not (folder / "story.json").exists():
        raise RuntimeError("Only low-poly videos with their saved story can be shot again")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    work = cfg.output_dir / f"{stamp}-{uuid.uuid4().hex[:4]}-lowpoly-working"
    work.mkdir(parents=True)
    shutil.copy2(folder / "story.json", work / "story.json")
    for name in KEEP_FOR_RESTAGE:
        if (folder / name).is_dir():
            shutil.copytree(folder / name, work / name)
    req = dict(report.get("lowpoly_request") or {})
    try:
        req["pace"] = int(str(report.get("voice_rate", req.get("pace", 0))).rstrip("%"))
    except ValueError:
        pass
    if str(req.get("watermark") or "").strip().lower() == OLD_MARK:
        req["watermark"] = ""  # the old default nobody typed (the user: "remove it")
    req = asdict(LowPolyRequest(**{k: v for k, v in req.items() if k in LowPolyRequest.__dataclass_fields__}))
    state = {"stage": "written", "stamp": stamp, "request": req, "seed": int(props.get("seed") or 0) or None,
             "pace": req.get("pace", 0),
             "restage": {"mode": mode if mode in RESTAGE_MODES else "storyboard", "from": folder.name,
                         "title": report.get("title", ""), "seed": uuid.uuid4().int % 100000, "music": report.get("music", "")}}
    saved = folder / "audio.json"
    if saved.exists():
        audio = json.loads(saved.read_text(encoding="utf-8"))
        audio = {k: {**v, "path": str(work / v["path"]) if not Path(v["path"]).is_absolute() else v["path"]} for k, v in audio.items()}
        if all(Path(v["path"]).exists() for v in audio.values()):
            state["audio"] = audio
            state["stage"] = "voiced"
    (work / CHECKPOINT).write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    return work.name


def remix_sound(cfg: Config, folder: Path, progress) -> dict:
    """A finished low-poly video's sound mixed again with the current levels (mix.py), under the same picture: the same
    voices, music tracks and sound cues from its props.json, nothing recorded, generated or rendered again, no Claude.
    The first version is kept as reel-original.mp4."""
    import os
    import shutil
    import time

    from ..audio import master
    from ..verify import probe

    data = json.loads((folder / "props.json").read_text(encoding="utf-8"))
    report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
    clips = [{**c, "path": c["path"] if Path(c["path"]).is_absolute() else str(folder / c["path"])} for c in data.get("clips", [])]
    missing = [c["path"] for c in clips if not Path(c["path"]).exists()]
    if missing:
        raise RuntimeError(f"{len(missing)} of its voice files are missing (e.g. {Path(missing[0]).name}), so its sound can't be mixed again")
    props = {k: v for k, v in data.items() if k not in ("clips", "cues", "sections")}
    fiction = report.get("story_kind") == "fiction"
    progress("Mixing the sound again: the voices first, the music and the world's sounds under them")
    brief = (f"cinematic film score for an animated sci-fi short film: {report.get('topic', '')}" if fiction
             else f"soft score for a narrated low-poly animated short about {report.get('topic', '')}")
    wav = folder / "soundtrack.wav"
    mixed = mix(cfg, props, clips, data.get("cues", []), data.get("sections", []), folder, wav, int(props.get("seed", 1)), progress,
                brief, fiction=fiction)
    video, original, tmp = folder / "reel.mp4", folder / "reel-original.mp4", folder / "reel-remix.mp4"
    if not original.exists():
        shutil.copy2(video, original)
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(original), "-i", str(wav), "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(tmp)], check=True)
    done = master(tmp)
    if done:
        progress(f"Sound mastered: {done['before']:.1f} -> {done['after']:.1f} LUFS")
    for tries in range(10):  # the page may be playing the old file (Windows holds it open)
        try:
            os.replace(tmp, video)
            break
        except OSError:
            if tries == 9:
                raise
            time.sleep(1.5)
    info = probe(video)
    if not info.get("has_audio") or abs(float(info.get("duration") or 0) - float(report.get("duration_seconds") or 0)) > 2:
        report.setdefault("issues", []).append("After the sound was mixed again the video's length or sound looks wrong: check it.")
    lv = mixed["levels"]
    progress(f"Voices {lv['voice']} LUFS; music {lv['voice'] - lv['music_between_lines']:.0f} LU under them between lines and "
             f"{lv['voice'] - lv['music_under_speech']:.0f} LU under while they speak; wind, rain and fire beds "
             f"{lv['voice'] - lv['beds']:.0f} LU under")
    report.update({"music": mixed["music"], "sound_levels": lv, "mix_version": mixed["mix_version"],
                   "sound_remixed": datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")})
    (folder / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    progress("Done: the new sound is under the same picture (the first version is kept as reel-original.mp4)")
    return report


def run_lowpoly_job(cfg: Config, req: LowPolyRequest, count: int, progress, resume: list[str] | None = None) -> list[dict]:
    """The app's job: `count` videos one after another in the shared video slot (or the saved ones resumed)."""
    from ..llm import set_limit_reporter, start_meter, usage_line
    from ..pipeline import Paused, _video_slot, done_line, set_pause_check

    reports = []
    should_pause = getattr(progress, "should_pause", None)
    todo = list(resume or []) or [None] * count
    for i, folder in enumerate(todo):
        vp = (lambda m, n=i + 1: progress(f"[V{n}] {m}")) if len(todo) > 1 else progress
        with _video_slot(cfg):
            if should_pause and should_pause():
                vp("§skip {}")
                continue
            set_pause_check(should_pause)
            set_limit_reporter(vp)
            start_meter(lambda r, vp=vp: vp(usage_line(r)))
            vp(f"=== Video {i + 1}/{len(todo)} ===")
            try:
                saved = folder and cfg.output_dir / folder / CHECKPOINT
                mine = LowPolyRequest(**json.loads(saved.read_text(encoding="utf-8")).get("request", {})) if saved and saved.exists() else req
                reports.append(run_lowpoly(cfg, mine, vp, folder))
                vp(done_line(reports[-1]))
            except Paused:
                vp("Paused: progress saved. Press Resume to carry on from here.")
            except Exception as exc:  # noqa: BLE001
                log.exception("Low-poly video %d failed", i + 1)
                vp(f"Video {i + 1} failed: {exc}")
    return reports


def unfinished(cfg: Config) -> list[str]:
    return sorted(p.parent.name for p in Path(cfg.output_dir).glob(f"*-lowpoly-working/{CHECKPOINT}"))
