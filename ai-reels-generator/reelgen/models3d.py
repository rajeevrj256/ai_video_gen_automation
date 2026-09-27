"""3D models for 'model3d' beats, decided per video.

Claude names the object a beat needs ("a red oil barrel", "a vintage propeller plane"),
gives search words and a recipe to build it from simple shapes. `find_model` then looks,
in order, for:

1. a model in the user's library (assets/models3d, e.g. from Pixabay),
2. a free CC0 model on Poly Haven (polyhaven.com, about 500 real-world objects: furniture,
   tools, food, plants, rocks, props), downloaded once into assets/models3d/polyhaven/,
3. nothing: the Remotion editor then builds the object from Claude's recipe of parts.

A match needs the object's main noun (the last search word) in the model's name or tags,
so "oil barrel" never becomes an armchair.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import time
from pathlib import Path
from typing import Literal

import requests
from pydantic import BaseModel, Field

from .config import Config

log = logging.getLogger(__name__)

POLYHAVEN_API = "https://api.polyhaven.com"
INDEX_DAYS = 7


class Part(BaseModel):
    shape: Literal["box", "sphere", "cylinder", "cone", "torus", "capsule"]
    size: list[float] = Field(description="Width, height, depth in metres (sphere: diameter; cylinder/cone: diameter, height; torus: diameter, tube thickness).")
    position: list[float] = Field(description="x, y, z centre in metres; +Y is up and the object's front faces +Z.")
    rotation: list[float] = Field(default_factory=lambda: [0, 0, 0], description="x, y, z rotation in degrees.")
    color: str = Field(description="Hex colour, e.g. '#c0392b'.")
    material: Literal["matte", "glossy", "metal", "glass", "glow"] = "matte"


def _words(text: str) -> list[str]:
    out = []
    for w in re.findall(r"[a-z]+", text.lower()):
        if len(w) > 3 and w.endswith("ies"):
            w = w[:-3] + "y"
        elif len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.append(w)
    return out


def _score(search: str, names: str) -> int:
    """0 unless the main noun matches; then how many search words match."""
    want = _words(search)
    have = set(_words(names))
    if not want or want[-1] not in have:
        return 0
    return sum(w in have for w in want)


def cache_dir(cfg: Config) -> Path:
    from .media import MODELS_DIR
    return MODELS_DIR / "polyhaven"


def _index(cfg: Config) -> dict:
    path = cache_dir(cfg) / "index.json"
    if path.exists() and time.time() - path.stat().st_mtime < INDEX_DAYS * 86400:
        return json.loads(path.read_text(encoding="utf-8"))
    try:
        resp = requests.get(f"{POLYHAVEN_API}/assets", params={"t": "models"}, timeout=30)
        resp.raise_for_status()
        index = {k: {"name": v.get("name", k), "tags": v.get("tags", []), "categories": v.get("categories", [])}
                 for k, v in resp.json().items()}
    except requests.RequestException as exc:
        log.warning("Poly Haven unavailable: %s", exc)
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index), encoding="utf-8")
    return index


def _download(cfg: Config, asset: str) -> Path | None:
    """The asset's 1k glTF with its .bin and textures, cached; returns the .gltf."""
    folder = cache_dir(cfg) / asset
    done = folder / ".complete"
    if done.exists():
        return next(folder.glob("*.gltf"), None)
    try:
        files = requests.get(f"{POLYHAVEN_API}/files/{asset}", timeout=30)
        files.raise_for_status()
        entry = files.json()["gltf"]["1k"]["gltf"]
        shutil.rmtree(folder, ignore_errors=True)
        wanted = {Path(entry["url"]).name: entry["url"], **{rel: f["url"] for rel, f in entry.get("include", {}).items()}}
        for rel, url in wanted.items():
            dest = folder / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            with requests.get(url, stream=True, timeout=120) as dl:
                dl.raise_for_status()
                with open(dest, "wb") as fh:
                    for block in dl.iter_content(1 << 20):
                        fh.write(block)
        done.write_text("ok")
        return folder / Path(entry["url"]).name
    except (requests.RequestException, KeyError, ValueError) as exc:
        log.warning("Couldn't download Poly Haven model %s: %s", asset, exc)
        return None


def find_model(cfg: Config, obj: str, search: str, out_dir: Path) -> Path | None:
    """Copy the best matching model into out_dir (the render's public folder); None = build it."""
    from .media import models

    search = search or obj
    library = sorted(((_score(search, m.about), m) for m in models(cfg)), key=lambda x: -x[0])
    if library and library[0][0] > 0:
        src = library[0][1].path
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / src.name
        if not dest.exists():
            shutil.copy(src, dest)
        log.info("3D %r: library model %s", obj, src.name)
        return dest
    index = _index(cfg)
    # The main noun must be in the model's own name ("Arm Chair"), not only a tag: tags are loose
    # ("rocket" on a spacecraft instrument). Tags then rank the matches.
    def score(k: str, v: dict) -> int:
        name = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", f"{v['name']} {k}").replace("_", " ")
        return _score(search, name) and _score(search, " ".join([name, *v["tags"], *v["categories"]]))
    ranked = sorted(((score(k, v), k) for k, v in index.items()), key=lambda x: -x[0])
    if ranked and ranked[0][0] > 0:
        asset = ranked[0][1]
        gltf = _download(cfg, asset)
        if gltf is not None:
            dest = out_dir / "polyhaven" / asset
            if not dest.exists():
                shutil.copytree(gltf.parent, dest, ignore=shutil.ignore_patterns(".complete"))
            log.info("3D %r: Poly Haven %s", obj, asset)
            return dest / gltf.name
    log.info("3D %r: built from shapes", obj)
    return None
