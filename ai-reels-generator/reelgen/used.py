"""Everything a finished video uses, for the "Effects & media used" list on its page.

Read from the video's props.json (what the editor actually rendered) and script.json:
music (composed, built-in bed or a library file), ambience beds, every sound effect with its
file and the times it plays, 3D models (Poly Haven or the user's library), footage clips, and the
visual effects (look, transitions, camera moves, impacts, scene actions, the hook trailer).
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from .config import Config
from .media import BEDS, CUE_SOUNDS, folder as library_folder, slug



def _library_file(cfg: Config, kind: str, name: str) -> str | None:
    """The user's original file name for a library item (copies in the video are renamed)."""
    base = library_folder(cfg, kind)
    if base.exists():
        for f in base.iterdir():
            if f.is_file() and slug(f.name) == name:
                return f.name
    return None


def _times(ts: list[float]) -> list[float]:
    return sorted(round(t, 2) for t in ts)


def media_used(cfg: Config, video: Path) -> dict:
    props_path = video / "props.json"
    if not props_path.exists():
        return {"available": False}
    props = json.loads(props_path.read_text(encoding="utf-8"))
    script = {}
    if (video / "script.json").exists():
        script = json.loads((video / "script.json").read_text(encoding="utf-8"))
        script = script.get("script", script)
    long = "beats" in props

    # ---- music ----
    music = []
    hook = props.get("hook") or {}
    if hook.get("music"):
        own = hook.get("own")
        music.append({"name": "Hook music" if own else f"Trailer track: {hook.get('style') or 'trailer'}",
                      "file": hook["music"], "times": [0.0], "play": hook["music"],
                      "source": f"Your library: {_library_file(cfg, 'music', own) or own}" if own
                      else "Composed for this video's hook"})
    if props.get("music"):
        picked = script.get("music") or ""
        original = _library_file(cfg, "music", picked) if picked else None
        if original:
            source = f"Your library: {original}"
        elif picked in BEDS:
            source = f"Built-in bed: {picked}"
        else:
            source = f"Composed for this video (mood: {script.get('mood', 'auto')})"
        music.append({"name": "Main music", "file": props["music"], "source": source,
                      "times": [round(props.get("musicFrom", 0.0), 2)], "play": props["music"]})
    for m in props.get("musicParts") or []:  # the user's tracks on the chapters they fit
        music.append({"name": f"Chapter music ({m['from'] // 60:.0f}:{m['from'] % 60:02.0f}–{m['to'] // 60:.0f}:{m['to'] % 60:02.0f})",
                      "file": m["src"], "source": f"Your library: {_library_file(cfg, 'music', m['name']) or m['name']}",
                      "times": [round(m["from"], 2)], "play": m["src"]})
    for a in props.get("ambience") or []:
        music.append({"name": f"Ambience: {Path(a['src']).stem}", "file": a["src"], "source": "Composed ambience bed",
                      "times": [round(a["from"], 2)], "play": a["src"]})

    # ---- sound effects (word cues + the automatic sound design) ----
    by_name: dict[str, dict] = {}
    times = defaultdict(list)
    for c in props.get("cues") or []:
        name = c.get("name") or Path(c["src"]).stem
        times[name].append(c["at"])
        if name not in by_name:
            user = Path(c["src"]).name.startswith("u-")
            original = (_library_file(cfg, "sfx", name) or _library_file(cfg, "sfx", Path(c["src"]).stem[2:])) if user else None
            by_name[name] = {"name": name, "file": c["src"],
                             "source": f"Your library: {original or Path(c['src']).name}" if user else
                             f"Built-in (synthesised): {CUE_SOUNDS[name][3]}" if name in CUE_SOUNDS else "Built-in (synthesised)",
                             "play": c["src"]}
    sounds = [{**v, "times": _times(times[k]), "count": len(times[k])} for k, v in by_name.items()]
    # Transition sounds play on every cut between scenes.
    cuts = [b["start"] for b in props.get("beats") or []] if long else [s["start"] for s in props.get("scenes") or []][1:]
    look = props.get("look") or {}
    transition = look.get("transition") or ""
    for name, src in (props.get("sfx") or {}).items():
        if name not in by_name:
            sounds.append({"name": name, "file": src, "source": "Built-in transition sound", "play": src,
                           "times": [], "count": 0, "note": f"on scene cuts ({transition or 'per scene'})"})
    sounds.sort(key=lambda s: -s["count"])

    # ---- 3D models and footage ----
    visuals = []
    if long:
        visuals = [(s["start"], s["visual"]) for s in hook.get("shots", [])] + [(b["start"], b["visual"]) for b in props["beats"]]
    models: dict[str, dict] = {}
    footage = []
    for at, v in visuals:
        if v.get("type") == "model3d" and v.get("src"):
            src = v["src"]
            key = src
            if key not in models:
                poly = "polyhaven/" in src
                models[key] = {"name": v.get("model") or Path(src).stem, "file": Path(src).name,
                               "source": f"Poly Haven (CC0): {src.split('polyhaven/')[1].split('/')[0]}" if poly else
                               f"Your library: {Path(src).name}", "times": []}
            models[key]["times"].append(round(at, 2))
        elif v.get("type") == "footage" and v.get("src"):
            footage.append({"name": v.get("query") or Path(v["src"]).stem, "file": v["src"], "source": "Pexels",
                            "times": [round(at, 2)]})
    for c in props.get("cuts") or []:  # Shorts: stock clips
        if c.get("src"):
            footage.append({"name": Path(c["src"]).stem, "file": c["src"], "source": "Pexels", "times": [round(c["start"], 2)]})
    for key, src in ({"hook": hook_plate} if (hook_plate := (props.get("look") or {}).get("hookPlate")) else {}).items() | \
            ((props.get("look") or {}).get("plates") or {}).items():
        ch = next((c for c in props.get("chapters") or [] if str(c.get("index")) == key), None)
        footage.append({"name": "Background photo: " + ("hook" if key == "hook" else (ch or {}).get("title", f"chapter {key}")),
                        "file": src, "source": "Pexels photo (" + ((props.get("look") or {}).get("plateUrls") or {}).get(key, "") + ")",
                        "times": [0.0 if key == "hook" else round((ch or {}).get("start", 0.0), 2)]})
    for m in models.values():
        m["count"] = len(m["times"])

    # ---- visual effects ----
    effects = []
    if look:
        effects.append({"name": "Look", "detail": f"palette {look.get('palette', '?')}, backdrop {look.get('backdrop', '?')}, "
                                                 f"transitions {look.get('transition', '?')}", "times": []})
    if hook.get("shots"):
        slams = [s for s in hook["shots"] if s.get("text")]
        effects.append({"name": "Trailer hook", "detail": f"{len(hook['shots'])} shots, letterbox, light rays, glitch cut; "
                        f"slammed words: {', '.join(s['text'] for s in slams) or 'none'}",
                        "times": _times([s["start"] for s in hook["shots"]])})
    group = defaultdict(list)
    for at, v in visuals:
        group[f"Visual: {v.get('type', '?')}"].append(at)
        if v.get("camera"):
            group[f"Camera: {v['camera']}"].append(at)
        if v.get("impact"):
            group["Impact (punch-in, flash, shake, boom)"].append(at)
        for a in v.get("actors") or []:
            group[f"Scene action: {a.get('action', '?')}"].append(at + float(a.get("at", 0)))
    for s in props.get("scenes") or []:  # Shorts
        if s.get("transition"):
            group[f"Transition: {s['transition']}"].append(s["start"])
        g = (s.get("graphic") or {}).get("type")
        if g and g != "none":
            group[f"Graphic: {g}"].append(s["start"])
    effects += [{"name": k, "detail": "", "times": _times(ts), "count": len(ts)}
                for k, ts in sorted(group.items(), key=lambda kv: -len(kv[1]))]

    return {"available": True, "music": music, "sounds": sounds, "models": list(models.values()),
            "footage": footage, "effects": effects}


def library_files(cfg: Config, video: Path) -> list[tuple[str, str]]:
    """(kind, file name) of every file from the user's library this video uses (for licence credits)."""
    try:
        used = media_used(cfg, video)
    except (OSError, ValueError, KeyError):
        return []
    out = []
    for kind, key in (("music", "music"), ("sfx", "sounds"), ("models3d", "models")):
        for item in used.get(key) or []:
            source = item.get("source", "")
            if source.startswith("Your library: "):
                out.append((kind, source[len("Your library: "):]))
    return out
