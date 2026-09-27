"""Background footage for each scene: Pexels stock video, or a generated fallback."""

from __future__ import annotations

import logging
import re
from pathlib import Path

import requests
from PIL import Image, ImageDraw

log = logging.getLogger(__name__)

PALETTES = [
    ((20, 20, 60), (120, 40, 160)),
    ((10, 40, 70), (0, 150, 170)),
    ((60, 10, 30), (220, 90, 60)),
    ((15, 50, 30), (40, 170, 110)),
    ((30, 30, 30), (90, 90, 140)),
]


def pexels_video(query: str, api_key: str, out_path: Path, used_ids: set[int],
                 min_height: int = 1280, landscape: bool = False) -> Path | None:
    """Download a stock clip matching `query` not used yet in this video, or None. Portrait
    for Shorts; landscape (and its first word must be in the clip's title) for long videos."""
    resp = requests.get(
        "https://api.pexels.com/videos/search",
        params={"query": query, "orientation": "landscape" if landscape else "portrait", "size": "medium",
                "per_page": 8},
        headers={"Authorization": api_key},
        timeout=20,
    )
    resp.raise_for_status()
    videos = _relevant(query, resp.json().get("videos", []))
    if landscape:  # "stockholm old town" must show Stockholm, not any old town
        first = _words(query.split()[0]) if query.split() else set()
        videos = [v for v in videos if first <= _words(v.get("url", ""))]
    for video in videos:
        if video.get("id") in used_ids:
            continue
        files = [f for f in video.get("video_files", [])
                 if f.get("file_type") == "video/mp4" and (f.get("height") or 0) >= min_height
                 and ((f.get("width") or 0) > (f.get("height") or 0)) == landscape]
        if not files:
            continue
        # Smallest file that is still tall enough keeps downloads fast.
        best = min(files, key=lambda f: f["height"])
        with requests.get(best["link"], stream=True, timeout=60) as dl:
            dl.raise_for_status()
            with open(out_path, "wb") as fh:
                for block in dl.iter_content(1 << 20):
                    fh.write(block)
        used_ids.add(video.get("id"))
        out_path.with_suffix(".url").write_text(best["link"], encoding="utf-8")  # lets a re-render fetch the same clip
        return out_path
    return None


STOPWORDS = {"a", "an", "the", "of", "in", "on", "at", "and", "with", "to", "for", "from", "by", "up", "close", "closeup", "shot", "view"}


def _words(text: str) -> set[str]:
    return {w.rstrip("s") for w in re.findall(r"[a-z]+", text.lower()) if w not in STOPWORDS and len(w) > 2}


# A query naming one of these must get a clip named after it: Pexels has almost no real
# footage of other planets, so "saturn planet" otherwise returns Earth on the word "planet".
NAMED_BODIES = {"mercury", "venus", "earth", "mars", "jupiter", "saturn", "uranus", "neptune", "pluto", "moon", "sun"}


def _relevant(query: str, videos: list[dict]) -> list[dict]:
    """Keep results whose Pexels page slug (e.g. /video/a-boy-pitching-a-baseball-123/)
    shares a word with the query, best match first; Pexels' own ranking breaks ties.
    Its search is loose ("football stadium" can return baseball), and a clip that
    visibly doesn't match the narration is the fastest way to look fake."""
    wanted = _words(query)
    must = wanted & _words(" ".join(NAMED_BODIES))
    scored = [(len(wanted & _words(v.get("url", ""))), i, v) for i, v in enumerate(videos)
              if must <= _words(v.get("url", ""))]
    return [v for score, _, v in sorted(scored, key=lambda x: (-x[0], x[1])) if score > 0]


def gradient_image(width: int, height: int, out_path: Path, seed: int) -> Path:
    """A vertical two-colour gradient, used when no stock footage is available."""
    top, bottom = PALETTES[seed % len(PALETTES)]
    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)
    for y in range(height):
        t = y / (height - 1)
        draw.line([(0, y), (width, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    img.save(out_path)
    return out_path


def fetch_backgrounds(scene_queries: list[list[str]], api_key: str, width: int, height: int,
                      out_dir: Path) -> list[list[Path]]:
    """Several clips per scene for quick cuts. Each entry is .mp4 (stock) or .png (fallback)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    used_ids: set[int] = set()
    result = []
    for i, queries in enumerate(scene_queries):
        clips = []
        for j, query in enumerate(queries[:3]):
            if not api_key:
                break
            try:
                path = pexels_video(query, api_key, out_dir / f"bg_{i:02d}_{j}.mp4", used_ids)
                if path:
                    clips.append(path)
            except Exception as exc:
                log.warning("Pexels failed for %r: %s", query, exc)
        if not clips:
            # The Remotion edit swaps "gradient_*" stills for an animated placeholder.
            clips.append(gradient_image(width, height, out_dir / f"gradient_{i:02d}.png", seed=i))
        result.append(clips)
    return result
