"""Real pictures as proof, from Wikimedia Commons: a logo, a building, a document, the real place.

The user, after the 'How YouTube started' documentary: "if any proof need to show on images, if logo want to show,
like google buy youtube use some images if needed". The stick editor draws everything, which can never show the
real Google or YouTube logo; Commons has them (most logos are public domain as simple text marks) and states every
file's licence. `find` searches Commons for the words Claude gives (a thing's `photo`), keeps only freely licensed
files (public domain, CC0, CC BY, CC BY-SA) whose name has the search's main name, fewest other names first, downloads a 960 px copy into
the video's folder and returns what the description must credit. Nothing found = the drawn object stays.
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

API = "https://commons.wikimedia.org/w/api.php"
AGENT = {"User-Agent": "ReelStudio/1.0 (https://github.com/rajeevrj256/ai_video_gen_automation; local video tool)"}  # Wikimedia asks for a contact URL
FREE = re.compile(r"^(public domain|pd\b|cc0|cc[ -]by(-sa)?\b|cc by(-sa)? \d)", re.I)
GENERIC = {"wordmark", "official", "old", "new", "icon", "symbol", "emblem", "original", "version", "color", "colour",
           "black", "white", "transparent", "vector", "full", "text"}  # words a file name adds without naming anything else
STOP = {"logo", "the", "of", "a", "an", "and", "in", "on", "photo", "picture", "image", "file", "svg", "png", "jpg"}


@dataclass
class Picture:
    path: Path  # the local copy
    width: int
    height: int
    title: str  # the Commons file name
    page: str  # its Commons page
    licence: str
    author: str

    def credit(self) -> str:
        who = f" by {self.author}" if self.author and self.licence.lower() not in ("public domain", "cc0") else ""
        return f"{self.title.removeprefix('File:')}{who}, {self.licence}, Wikimedia Commons ({self.page})"


def _words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", s.lower()) if w not in STOP and len(w) > 1}


def _get(url: str, timeout: int = 30, tries: int = 4) -> bytes:
    """GET with Wikimedia's rate limit respected: a 429 waits its Retry-After (at most 20 s) and tries again."""
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=AGENT), timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or k == tries - 1:
                raise
            wait = exc.headers.get("Retry-After", "")
            time.sleep(min(20.0, float(wait) if wait.replace(".", "", 1).isdigit() else 5.0) + k * 2)
    raise RuntimeError("unreachable")


def search(words: str, limit: int = 10) -> list[dict]:
    query = urllib.parse.urlencode({
        "action": "query", "generator": "search", "gsrsearch": f"{words} filetype:bitmap|drawing", "gsrnamespace": 6,
        "gsrlimit": limit, "prop": "imageinfo", "iiprop": "url|extmetadata|mime|size", "iiurlwidth": 960,  # a standard thumbnail width: Wikimedia refuses other sizes
        "format": "json"})
    data = json.loads(_get(f"{API}?{query}"))
    pages = sorted((data.get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
    out = []
    for p in pages:
        ii = (p.get("imageinfo") or [{}])[0]
        meta = ii.get("extmetadata") or {}
        val = lambda k: re.sub(r"<[^>]+>", "", (meta.get(k) or {}).get("value", "")).strip()  # noqa: E731
        # A bitmap smaller than 960 px has no 960 thumbnail: its thumb link is at its own, non-standard width,
        # which Wikimedia refuses (429 "use thumbnail sizes"), so the original file is taken. SVGs always render.
        if "svg" not in ii.get("mime", "") and (ii.get("width") or 0) < 400:
            continue  # too small for a card (a 176 px Google logo would show blurred)
        small = "svg" not in ii.get("mime", "") and 0 < (ii.get("width") or 0) <= 960
        out.append({"title": p.get("title", ""), "url": (ii.get("url") if small else ii.get("thumburl")) or ii.get("url", ""),
                    "page": ii.get("descriptionurl", ""), "licence": val("LicenseShortName"),
                    "author": val("Artist")[:80], "width": (ii.get("width") if small else ii.get("thumbwidth")) or ii.get("width", 0),
                    "height": (ii.get("height") if small else ii.get("thumbheight")) or ii.get("height", 0), "mime": ii.get("mime", "")})
    return out


def find(words: str, out_dir: Path, name: str) -> Picture | None:
    """The first free, relevant Commons picture for `words`, saved as out_dir/name.<ext>; None if there's none."""
    words = (words or "").strip()[:120]
    if not words:
        return None
    try:
        hits = search(words)
    except Exception as exc:  # noqa: BLE001 - no network or Commons down: the drawing stays
        log.warning("Commons search failed for %r: %s", words, exc)
        return None
    names = [w for w in re.findall(r"[a-z0-9]+", words.lower()) if w in _words(words) and not w.isdigit()]
    years = {w for w in _words(words) if w.isdigit()}

    def fit(h: dict) -> tuple:
        # The search's main name (its first word) must be in the file's name; then the fewest other names win, and
        # the year: 'Google logo 2010' prefers 'Google logo (2010-2013)' to 'Google Buzz logo (2010-2011)'.
        title = _words(h["title"])
        extra = {w for w in title if not w.isdigit()} - set(names) - GENERIC
        return (len(extra), -len(set(names) & title), -any(y in h["title"] for y in years))

    def era_ok(title: str) -> bool:
        # A year asked for must fall in the file's years: 'YouTube logo 2005' never gives 'Logo of YouTube (2015-2017)'.
        spans = [(int(a), int(b or a)) for a, b in re.findall(r"\b((?:19|20)\d\d)(?:\s*[-–]\s*((?:19|20)\d\d))?\b", title)]
        return not years or not spans or any(lo <= int(y) <= hi for y in years for lo, hi in spans)

    ok = sorted((h for h in hits if h["url"] and FREE.match(h["licence"] or "") and era_ok(h["title"])
                 and (not names or names[0] in _words(h["title"]))), key=fit)  # stable: Commons' ranking breaks ties
    # Only the best-fitting kind: when the right file can't be downloaded, no picture beats a wrong one
    # (a failed 'Google logo' download once fell back to the Google Scholar logo).
    ok = [h for h in ok if fit(h)[0] == fit(ok[0])[0]] if ok else []
    if "logo" in words.lower():  # a logo is the company's own: no other name in the file (Google Scholar, Google Buzz)
        ok = [h for h in ok if fit(h)[0] == 0]
    for h in ok:
        ext = ".png" if h["url"].lower().endswith((".png", ".svg.png")) or "svg" in h["mime"] else ".jpg"
        path = out_dir / f"{name}{ext}"
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            data = _get(h["url"], 60)
            if len(data) < 500:
                continue
            path.write_bytes(data)
        except Exception as exc:  # noqa: BLE001 - try the next hit
            log.warning("Couldn't download %s: %s", h["title"], exc)
            continue
        return Picture(path, int(h["width"] or 960), int(h["height"] or 960), h["title"], h["page"], h["licence"], h["author"])
    return None

