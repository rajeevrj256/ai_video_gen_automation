"""Real meme templates from the internet (the user: "CAN WE ADD REAL MEMES ON INTERNET???", then "Imgflip's ... can
also generate memes, either video or images"), from imgflip.com: picture templates (Drake, Two Buttons, Distracted
Boyfriend, Gru's Plan, Monkey Puppet...) and animated ones, short video clips (Shrek running, Confused Monkey...), and,
by search, Indian film and TV templates of both kinds (Hera Pheri, Jethalal, CID, 'Paisa hi paisa hoga'...), like the
18-minute Hinglish explainer the user sent.

Setting `meme_source`: 'drawn' (default: memes.py's formats drawn by the editor, nothing copied) or 'web'. With 'web'
the writer sees Imgflip's 100 most used templates (the free API, no key: api.imgflip.com/get_memes) and may ask for
any other with 'search: words'; the drawn format it also gives is the fallback. At props time (`prepare`) the template
is resolved (name in the list, or Imgflip's search page), its generator page read for where its text goes (the page
embeds each template's text boxes: position, size, rotation, colours, alignment, and for a clip when each box shows),
the picture or clip downloaded (i.imgflip.com/<id in base 36>.<type>, the page's IMAGE_DOMAIN) and copied into the
video's folder; the editor (Meme.tsx `OwnMeme`) writes each label into its box, a clip looping under its beat,
muted (a film's audio is what Content ID matches). No box data: top and bottom text. Anything that fails (offline,
no match, not a picture or a clip) draws the format.

Imgflip's robots.txt allows these pages; results are cached under <output>/meme-web (the list for a week, searches
and templates for good). The pictures are other people's (film and TV stills, photos of real people): they can bring
copyright claims, which is why this is off unless chosen. Never used: templates Imgflip marks not safe for work, and
any whose name or alternative names mention a politician or politics (the user's standing rule), or a tragedy.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import time
import urllib.parse
from pathlib import Path

from .config import Config

log = logging.getLogger(__name__)

API = "https://api.imgflip.com/get_memes"
PAGE = "https://imgflip.com/memegenerator/{}"
GIF_PAGE = "https://imgflip.com/gif-maker/{}"
GIF_LIST = "https://imgflip.com/gif-templates"
SEARCH = "https://imgflip.com/memesearch?q={}"
IMAGE = "https://i.imgflip.com/{}.{}"
UA = {"User-Agent": "Mozilla/5.0 (Reel Studio meme templates)"}
LIST_DAYS = 7
SOURCES = ("drawn", "web")

# Whole words in a template's name or alternative names that keep it out (politics: the user's standing rule).
BLOCKED = {"bernie", "sanders", "trump", "biden", "obama", "hillary", "clinton", "bush", "putin", "zelensky", "modi",
           "gandhi", "rahul", "kejriwal", "yogi", "bjp", "congress", "election", "elections", "president", "minister",
           "senator", "politics", "political", "politician", "democrat", "republican", "kim", "jong", "xi", "jinping",
           "hitler", "nazi", "9/11", "911", "drowning", "funeral", "war", "terrorist", "isis"}


def enabled(cfg: Config) -> bool:
    return (getattr(cfg, "meme_source", "drawn") or "drawn") == "web"


def _dir(cfg: Config) -> Path:
    d = cfg.output_dir / "meme-web"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache(cfg: Config) -> dict:
    try:
        return json.loads((_dir(cfg) / "cache.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(cfg: Config, data: dict) -> None:
    (_dir(cfg) / "cache.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _get(url: str, binary: bool = False):
    import requests

    r = requests.get(url, headers=UA, timeout=25)
    r.raise_for_status()
    return r.content if binary else r.text


def blocked(name: str, alt: str = "") -> bool:
    words = set(re.findall(r"[a-z0-9/]+", f"{name} {alt}".lower()))
    return bool(words & BLOCKED)


def base36(n: int) -> str:
    out = ""
    while n:
        n, r = divmod(n, 36)
        out = "0123456789abcdefghijklmnopqrstuvwxyz"[r] + out
    return out or "0"


def popular(cfg: Config) -> list[dict]:
    """Imgflip's 100 most used templates (id, name, url, width, height, box_count), politics and the like left out."""
    data = _cache(cfg)
    got = data.get("popular") or {}
    if not got.get("memes") or time.time() - got.get("at", 0) > LIST_DAYS * 86400:
        try:
            memes = json.loads(_get(API))["data"]["memes"]
            got = data["popular"] = {"at": time.time(), "memes": memes}
            _save(cfg, data)
        except Exception as exc:  # noqa: BLE001 - offline: the last list, or none
            log.warning("Couldn't load Imgflip's meme list: %s", exc)
    return [m for m in got.get("memes") or [] if not blocked(m.get("name", ""))]


def popular_clips(cfg: Config) -> list[dict]:
    """Imgflip's popular animated templates (short clips): id, slug and a readable name."""
    data = _cache(cfg)
    got = data.get("clips") or {}
    if not got.get("items") or time.time() - got.get("at", 0) > LIST_DAYS * 86400:
        try:
            page, items = _get(GIF_LIST), []
            for m in re.finditer(r'href="/gif-maker/(\d+)/([^"/?#]+)"', page):
                if all(i["id"] != int(m.group(1)) for i in items):
                    items.append({"id": int(m.group(1)), "slug": m.group(2), "name": _readable(m.group(2))})
            if items:
                got = data["clips"] = {"at": time.time(), "items": items}
                _save(cfg, data)
        except Exception as exc:  # noqa: BLE001
            log.warning("Couldn't load Imgflip's animated templates: %s", exc)
    return [i for i in got.get("items") or [] if not blocked(i["name"])]


def _readable(slug: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[-_]+", " ", urllib.parse.unquote(slug))).strip()


def prompt_block(cfg: Config) -> str:
    """For the writer: the real templates it may pick (with how many text boxes each has)."""
    if not enabled(cfg):
        return ""
    names = [f"{m['name']} ({m.get('box_count', 2)})" for m in popular(cfg)]
    clips = [f"{c['name']} (video)" for c in popular_clips(cfg)]
    if not names and not clips:
        return ""
    return ("\n- Real memes (the user chose real memes from the internet): set 'web_meme' to a template's exact name as "
            "listed, its 'labels' one per text box in the template's own order (the number after a picture template's "
            "name; a clip takes 1-2: its caption, then a second line), and still set 'meme' to the closest drawn format as "
            "the fallback. Or write 'search: words' for any other well-known template, picture or clip, e.g. Indian film "
            "and TV memes for an Indian audience ('search: hera pheri', 'search: jethalal thinking', 'search: paisa hi "
            "paisa'); add 'video' to the words to prefer a clip. Its labels are then its own boxes, else top and bottom "
            "text. A clip (video) plays muted and loops under the line: use one where the motion is the joke. Use a "
            "template only where viewers know it and it fits the line exactly, each template at most once per video (the "
            "hook included); never one about a real politician, a tragedy or anything cruel."
            + (" Picture templates: " + "; ".join(names) + "." if names else "")
            + (" Clip templates: " + "; ".join(clips) + "." if clips else ""))


def _templates_on(page: str) -> dict[int, dict]:
    """Every template object a generator page embeds ({"id":..,"name":..,"w":..,"default_settings":"[...]"...})."""
    out, dec = {}, json.JSONDecoder()
    for m in re.finditer(r'\{"id":(\d+),"uid":', page):
        try:
            obj, _ = dec.raw_decode(page, m.start())
        except ValueError:
            continue
        if isinstance(obj, dict) and obj.get("name") and obj.get("w"):
            out[int(obj["id"])] = obj
    return out


def template(cfg: Config, tid: int, url_name: str = "", clip: bool = False) -> dict | None:
    """One template's name, size, file type, alternative names and text boxes (a clip: its length too), from its
    generator page (pictures: /memegenerator, clips: /gif-maker)."""
    data = _cache(cfg)
    known = data.setdefault("clip_templates" if clip else "templates", {})
    if str(tid) in known:
        return known[str(tid)]
    try:
        path = f"{tid}/{url_name}" if url_name else str(tid)
        page = _get((GIF_PAGE if clip else PAGE).format(path))
    except Exception as exc:  # noqa: BLE001
        log.warning("Couldn't open Imgflip template %s: %s", tid, exc)
        return None
    if clip:
        i = page.find("gif_template=")
        try:
            obj = json.JSONDecoder().raw_decode(page, i + len("gif_template="))[0] if i >= 0 else None
        except ValueError:
            obj = None
        if isinstance(obj, dict) and obj.get("w"):
            obj.setdefault("url_name", url_name)
            known[str(tid)] = obj
    else:
        for k, v in _templates_on(page).items():  # the page lists the popular ones too: keep them all
            known.setdefault(str(k), v)
    _save(cfg, data)
    return known.get(str(tid))


def search(cfg: Config, words: str) -> list[tuple[str, int, str]]:
    """Imgflip's template search: (kind 'picture' or 'clip', id, url name) of the matches, best first."""
    q = " ".join(words.split())[:80].lower()
    data = _cache(cfg)
    hits = data.setdefault("searches", {})
    if q not in hits:
        try:
            page = _get(SEARCH.format(urllib.parse.quote(q)))
        except Exception as exc:  # noqa: BLE001
            log.warning("Imgflip search failed for %r: %s", q, exc)
            return []
        found = []
        for m in re.finditer(r'href="/(memegenerator|gif-maker)/(\d+)/([^"/?#]+)"', page):
            item = ("clip" if m.group(1) == "gif-maker" else "picture", int(m.group(2)), m.group(3))
            if item not in found:
                found.append(item)
        hits[q] = found[:16]
        _save(cfg, data)
    return [(k, int(i), n) for k, i, n in hits[q]]


def boxes(tpl: dict) -> list[dict]:
    """The template's text boxes as fractions of the picture, with how their text looks."""
    try:
        raw = json.loads(tpl.get("default_settings") or "[]")
    except ValueError:
        return []
    w, h = float(tpl["w"]), float(tpl["h"])
    out = []
    for b in raw:
        if b.get("type", "text") != "text" or not b.get("w"):
            continue
        out.append({"x": round(b["x"] / w, 4), "y": round(b["y"] / h, 4), "w": round(b["w"] / w, 4), "h": round(b["h"] / h, 4),
                    "rot": float(b.get("rotation") or 0), "color": b.get("font_color") or "#ffffff",
                    "outline": b.get("outline_color") or "#000000", "caps": bool(b.get("force_caps", True)),
                    "align": b.get("text_align") or "center", "valign": b.get("vertical_align") or "top",
                    "font": (b.get("font") or "impact").lower(),
                    "start": float(b.get("start", 0) or 0), "end": float(b.get("end", 100) or 100)})  # clips: % of its length
    return out


def _ok(tpl: dict | None) -> bool:
    return bool(tpl) and tpl.get("safe_for_work", "yes") == "yes" and str(tpl.get("approved", "1")) != "0" \
        and not blocked(tpl.get("name", ""), tpl.get("altNames", ""))


def _pick(cfg: Config, want: str) -> tuple[str, int, str] | None:
    """(kind, id, url name) of the template `want` names: a listed picture or clip, or the first safe search hit."""
    want = want.strip()
    if want.lower().startswith("search:"):
        words = want.split(":", 1)[1]
        video = bool(re.search(r"\b(video|clip|gif)\b", words, re.I))
        hits = search(cfg, re.sub(r"\b(video|clip|gif)\b", " ", words, flags=re.I))
        for kind, tid, url_name in sorted(hits, key=lambda h: 0 if (h[0] == "clip") == video else 1):
            if _ok(template(cfg, tid, url_name, clip=kind == "clip")):
                return kind, tid, url_name
        return None
    key = re.sub(r"\s*\((\d+|video)\)\s*$", "", want).lower()  # 'Drake Hotline Bling (2)', 'Shrek running (video)'
    if not want.lower().endswith("(video)"):
        listed = popular(cfg)
        hit = next((m for m in listed if m["name"].lower() == key), None) or next(
            (m for m in listed if key and (key in m["name"].lower() or m["name"].lower() in key)), None)
        if hit:
            return "picture", int(hit["id"]), ""
    clips = popular_clips(cfg)
    hit = next((c for c in clips if c["name"].lower() == key), None) or next(
        (c for c in clips if key and (key in c["name"].lower() or c["name"].lower() in key)), None)
    return ("clip", int(hit["id"]), hit["slug"]) if hit else None


def prepare(cfg: Config, want: str, out_dir: Path, index: int) -> dict | None:
    """The template `want` (a listed name or 'search: words') ready for the editor: its picture copied to
    out_dir/webNNN.ext and its boxes; None when it can't be had (the drawn format is used then)."""
    if not enabled(cfg) or not want.strip():
        return None
    try:
        picked = _pick(cfg, want)
        if picked is None:
            log.info("No safe meme template found for %r: drawing the format instead", want)
            return None
        kind, tid, url_name = picked
        clip = kind == "clip"
        tpl = template(cfg, tid, url_name, clip=clip)
        listed = None if clip else next((m for m in popular(cfg) if int(m["id"]) == tid), None)
        if tpl is None and listed is None:
            return None
        tpl = tpl or {"name": listed["name"], "w": listed["width"], "h": listed["height"],
                      "file_type": listed["url"].rsplit(".", 1)[-1], "default_settings": ""}
        if not _ok(tpl):
            return None
        ext = (tpl.get("file_type") or ("mp4" if clip else "jpg")).lower()
        if ext not in (("mp4", "webm") if clip else ("jpg", "jpeg", "png", "webp")):
            return None
        url = listed["url"] if listed else IMAGE.format(base36(tid), ext)
        store = _dir(cfg) / "img" / f"{tid}.{ext}"
        if not store.exists():
            data = _get(url, binary=True)
            if len(data) < 1000 or (clip and b"ftyp" not in data[:64] and not data[:4] == b"\x1aE\xdf\xa3"):
                raise ValueError(f"{url} isn't a {'video' if clip else 'picture'}")
            store.parent.mkdir(parents=True, exist_ok=True)
            store.write_bytes(data)
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / f"web{index:03d}.{ext}"
        shutil.copy(store, dest)
        page = (GIF_PAGE if clip else PAGE).format(f"{tid}/{tpl.get('url_name') or url_name}".rstrip("/"))
        return {"path": dest, "name": tpl["name"], "w": int(tpl["w"]), "h": int(tpl["h"]), "boxes": boxes(tpl),
                "page": page, "clip": clip, "seconds": float(tpl.get("duration") or 0) if clip else 0.0}
    except Exception as exc:  # noqa: BLE001 - a meme never stops a video
        log.warning("Meme template %r unavailable: %s", want, exc)
        return None
