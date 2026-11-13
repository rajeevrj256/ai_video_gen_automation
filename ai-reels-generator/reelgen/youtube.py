"""Your YouTube channel from the app: connect with your own Google sign-in, upload a finished video (title, description,
tags, thumbnail, privacy or a scheduled time), edit any of your channel's videos, and read their analytics (views,
watch time, how much of each video people watch, impressions and click-through rate, where viewers leave and where
they came from), with an audit by Claude.

How it connects: you make an OAuth client of type "Desktop app" in your own Google Cloud project (the steps are in
Settings > YouTube) and give the app its JSON file. Connecting opens Google's sign-in in this computer's browser;
Google sends the browser back to a one-time listener on 127.0.0.1 (a random port, the way Google asks desktop apps
to do it, with PKCE), the app swaps the code for a refresh token and keeps it in <output>/youtube/token.json. The
client id and secret go in .env. Nothing here is ever sent anywhere but Google.

Google's rules this follows (YouTube Data API revision history, checked Nov 2026): an upload costs ~1 unit of its
own daily bucket (100 uploads a day); uploads from unverified API projects are no longer locked to private (since
2 Nov 2026); custom thumbnails work for Shorts after processing (since 3 Nov 2026), up to 50 MB; a scheduled video
is private with `status.publishAt`; `status.containsSyntheticMedia` is the altered/synthetic content disclosure.
Impressions and click-through rate: tried as `videoThumbnailImpressions` / `videoThumbnailImpressionsClickRate` in
the Analytics API first, else read from the Reporting API's daily `channel_reach_basic_a1` reports (a job the app
creates; the first reports arrive within 48 hours, then cover the 30 days before it).
"""

from __future__ import annotations

import base64
import contextvars
import csv
import shutil
import hashlib
import html
import io
import json
import os
import re
import secrets
import threading
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import requests

from . import stopper
from .config import PROJECT_ROOT, Config

# Every Google address in one place (a test points them at a stand-in server).
URLS = {
    "auth": "https://accounts.google.com/o/oauth2/v2/auth",
    "token": "https://oauth2.googleapis.com/token",
    "revoke": "https://oauth2.googleapis.com/revoke",
    "api": "https://www.googleapis.com/youtube/v3",
    "upload": "https://www.googleapis.com/upload/youtube/v3",
    "analytics": "https://youtubeanalytics.googleapis.com/v2/reports",
    "reporting": "https://youtubereporting.googleapis.com/v1",
}
# manage the channel's videos (upload, edit, thumbnails) + read its analytics and reports
SCOPES = ["https://www.googleapis.com/auth/youtube", "https://www.googleapis.com/auth/yt-analytics.readonly"]
CHUNK = 8 * 1024 * 1024  # upload piece, a multiple of 256 KB as Google asks
CONNECT_WAIT = 600  # seconds the one-time sign-in listener waits for Google to send the browser back
REACH_REPORT = "channel_reach_basic_a1"
TITLE_MAX = 100
DESCRIPTION_MAX = 5000  # Google counts bytes
TAGS_MAX = 500
THUMB_MAX = 50 * 1024 * 1024
STATS = ["views", "estimatedMinutesWatched", "averageViewDuration", "averageViewPercentage", "subscribersGained",
         "likes", "comments", "shares"]
# The app's categories (categories.CATEGORIES) as YouTube's category ids.
CATEGORY_IDS = {"Sports": "17", "Money": "27", "Science & Space": "28", "Tech": "28", "History": "27",
                "Nature & Animals": "15", "Weather": "25", "Entertainment": "24", "India": "22", "Life & People": "22",
                "Stories": "1", "Comedy": "23"}
YT_CATEGORIES = {"1": "Film & Animation", "2": "Autos & Vehicles", "10": "Music", "15": "Pets & Animals", "17": "Sports",
                 "19": "Travel & Events", "20": "Gaming", "22": "People & Blogs", "23": "Comedy", "24": "Entertainment",
                 "25": "News & Politics", "26": "Howto & Style", "27": "Education", "28": "Science & Technology"}
# Videos whose pictures look like real photographs or footage: the altered/synthetic disclosure starts ticked.
REALISTIC_SOURCES = ("journey", "divine")
VIDEO_FILES = ("reel.mp4", "reel-myvoice.mp4")


class YouTubeError(Exception):
    """Something to tell the user in plain words."""


def folder(cfg: Config) -> Path:
    d = cfg.output_dir / "youtube"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _read(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write(path: Path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


# ---------- your OAuth client (Settings > YouTube) ----------

def client() -> tuple[str, str]:
    return os.environ.get("YOUTUBE_CLIENT_ID", "").strip(), os.environ.get("YOUTUBE_CLIENT_SECRET", "").strip()


def set_env(values: dict[str, str]) -> None:
    """Write keys into .env on this computer and the running app ('' removes one)."""
    env = PROJECT_ROOT / ".env"
    lines = env.read_text(encoding="utf-8").splitlines() if env.exists() else []
    lines = [x for x in lines if not any(re.match(rf"\s*{k}\s*=", x) for k in values)]
    for k, v in values.items():
        if v:
            lines.append(f"{k}={v}")
            os.environ[k] = v
        else:
            os.environ.pop(k, None)
    env.write_text("\n".join(lines) + "\n", encoding="utf-8")


NO_SECRET = ("This file has no client secret in it: Google shows a client's secret only once, right after you make it. "
             "In Google Cloud > Google Auth Platform > Clients, open your Desktop client and press '+ Add secret', then "
             "paste it into 'Client secret' (the client ID is filled in from your file) and save. Or make a new Desktop client "
             "and press Download JSON in the dialog that opens.")


def save_client(text: str = "", client_id: str = "", client_secret: str = "") -> str:
    """The OAuth client from Google Cloud: its downloaded JSON file, or the id and secret typed in."""
    if text.strip():
        try:
            data = json.loads(text)
        except ValueError:
            raise YouTubeError("That isn't the JSON file Google Cloud gives you for an OAuth client") from None
        kind = "installed" if "installed" in data else "web" if "web" in data else ""
        if not kind:
            raise YouTubeError("That JSON file isn't an OAuth client (it should have 'installed' in it: "
                               "choose 'Desktop app' when you create the client)")
        if kind == "web":
            raise YouTubeError("This is a 'Web application' client. Create one of type 'Desktop app' instead "
                               "(Google Cloud > Clients > Create client > Desktop app)")
        client_id = data[kind].get("client_id", "") or client_id
        client_secret = str(data[kind].get("client_secret") or "").strip() or client_secret
        if not re.fullmatch(r"[\w\-]{10,100}", client_secret.strip()):
            # Google shows a client's secret only once, in the dialog right after it is made; a JSON downloaded
            # later from the client's page has no usable secret in it.
            raise YouTubeError(NO_SECRET)
    client_id, client_secret = client_id.strip(), client_secret.strip()
    if not re.fullmatch(r"[\w.\-]+\.apps\.googleusercontent\.com", client_id):
        raise YouTubeError("That client ID doesn't look right (it ends in .apps.googleusercontent.com)")
    if not client_secret:
        raise YouTubeError(NO_SECRET)
    if not re.fullmatch(r"[\w\-]{10,100}", client_secret):
        raise YouTubeError("That client secret doesn't look right (it looks like GOCSPX-... with no spaces)")
    set_env({"YOUTUBE_CLIENT_ID": client_id, "YOUTUBE_CLIENT_SECRET": client_secret})
    return client_id


# ---------- connecting (Google sign-in in this computer's browser) ----------

_pending: dict[str, dict] = {}
_lock = threading.Lock()


# ---------- several channels: each its own folder (sign-in, numbers, audits, picture) ----------
# youtube/channels/<channel id>/token.json, videos.json, audits/, details/, reach/, avatar.jpg; youtube/active.json
# says which one the YouTube tab shows. A job or a request picks another with `use(channel id)`.

_CHANNEL: contextvars.ContextVar[str] = contextvars.ContextVar("youtube_channel", default="")


@contextmanager
def use(cid: str | None):
    """Everything inside works on that channel ('' = the active one)."""
    token = _CHANNEL.set(cid or "")
    try:
        yield
    finally:
        _CHANNEL.reset(token)


def _channels_dir(cfg: Config) -> Path:
    d = folder(cfg) / "channels"
    if not d.exists():
        d.mkdir(parents=True, exist_ok=True)
        _migrate(cfg, d)
    return d


def _migrate(cfg: Config, d: Path) -> None:
    """The first version kept one channel straight in youtube/: moved into its own folder."""
    root = folder(cfg)
    tok = _read(root / "token.json")
    if not tok:
        return
    cid = re.sub(r"[^\w-]", "_", ((tok.get("channel") or {}).get("id") or "channel"))
    home = d / cid
    home.mkdir(exist_ok=True)
    for name in ("token.json", "videos.json", "audit.json", "details", "reach"):
        if (root / name).exists():
            shutil.move(str(root / name), str(home / name))
    _write(root / "active.json", {"id": cid})


def _ok_id(cid: str) -> str:
    if not re.fullmatch(r"[\w-]{1,64}", cid or ""):
        raise YouTubeError("That isn't one of your connected channels")
    return cid


def channels(cfg: Config) -> list[dict]:
    """Every connected channel, the active one marked."""
    act = active(cfg)
    out = []
    for home in sorted(_channels_dir(cfg).iterdir()):
        tok = _read(home / "token.json") or {}
        if not tok.get("refresh_token"):
            continue
        ch = tok.get("channel") or {"id": home.name, "title": home.name}
        out.append({**{k: ch.get(k) for k in ("id", "title", "handle", "subscribers", "views", "videos")},
                    "avatar": (home / "avatar.jpg").exists(), "connected_at": tok.get("connected_at", ""),
                    "active": home.name == act})
    return out


def active(cfg: Config) -> str:
    """The channel this request or job works on: `use(...)`, else the one picked in the tab, else the first."""
    d = _channels_dir(cfg)
    for cid in (_CHANNEL.get(), (_read(folder(cfg) / "active.json") or {}).get("id", "")):
        if cid and re.fullmatch(r"[\w-]{1,64}", cid) and (_read(d / cid / "token.json") or {}).get("refresh_token"):
            return cid
    for home in sorted(d.iterdir()):
        if (_read(home / "token.json") or {}).get("refresh_token"):
            return home.name
    return ""


def set_active(cfg: Config, cid: str) -> None:
    if not (_read(_channels_dir(cfg) / _ok_id(cid) / "token.json") or {}).get("refresh_token"):
        raise YouTubeError("That channel isn't connected")
    _write(folder(cfg) / "active.json", {"id": cid})


def home(cfg: Config, cid: str = "") -> Path:
    """The folder of a channel (the active one by default)."""
    cid = cid or active(cfg)
    if not cid:
        raise YouTubeError("YouTube isn't connected yet (YouTube tab)")
    d = _channels_dir(cfg) / _ok_id(cid)
    d.mkdir(exist_ok=True)
    return d


def _token_path(cfg: Config, tok: dict | None = None) -> Path:
    cid = ((tok or {}).get("channel") or {}).get("id", "")
    return home(cfg, re.sub(r"[^\w-]", "_", cid) if cid else "") / "token.json"


def connected(cfg: Config) -> dict | None:
    cid = active(cfg)
    if not cid:
        return None
    tok = _read(_channels_dir(cfg) / cid / "token.json")
    return tok if tok and tok.get("refresh_token") else None


def avatar_path(cfg: Config, cid: str) -> Path | None:
    path = _channels_dir(cfg) / _ok_id(cid) / "avatar.jpg"
    return path if path.exists() else None


def _save_avatar(cfg: Config, ch: dict, url: str) -> None:
    """The channel picture kept on this computer: Google's picture host (yt3.ggpht.com) refuses requests that come
    from another site's page, so the tab showed a broken picture."""
    if not url:
        return
    try:
        r = requests.get(url, timeout=20)
        if r.status_code == 200 and r.content[:3] in (b"\xff\xd8\xff", b"\x89PN", b"RIF", b"GIF"):
            (home(cfg, ch["id"]) / "avatar.jpg").write_bytes(r.content)
    except requests.RequestException:
        pass


def start_connect(cfg: Config, back: str) -> str:
    """The Google sign-in address to open; a one-time listener on 127.0.0.1 waits for Google to send the browser back."""
    cid, secret = client()
    if not cid:
        raise YouTubeError("Save your OAuth client first: choose its JSON file in step 1 above, or paste its ID and secret")
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    box: dict = {"state": state, "verifier": verifier, "back": back, "done": None}

    class Back(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            q = parse_qs(urlparse(self.path).query)
            if q.get("state", [""])[0] != state:
                self._page("This sign-in link is old or not from Reel Studio. Press Connect again in the app.", 400)
                return
            if q.get("error"):
                box["done"] = {"error": q["error"][0]}
                self._page("Google says: " + q["error"][0] + ". Nothing was connected; you can press Connect again.", 400)
            else:
                try:
                    tok = _exchange(cfg, q.get("code", [""])[0], box["redirect"], verifier)
                    ch = channel(cfg, tok=tok)
                    set_active(cfg, ch["id"])
                    box["done"] = {"channel": ch}
                    self._page(f"Connected to {ch['title']}. You can close this tab and go back to Reel Studio.")
                except Exception as exc:  # shown to the user, never raised in the server thread
                    box["done"] = {"error": str(exc)}
                    self._page("Couldn't finish connecting: " + str(exc), 500)
            threading.Thread(target=server.shutdown, daemon=True).start()

        def _page(self, text: str, code: int = 200):
            body = (f"<!doctype html><meta charset=utf-8><title>Reel Studio · YouTube</title>"
                    f"<body style='font:16px system-ui;padding:40px;max-width:640px'><h2>Reel Studio · YouTube</h2>"
                    f"<p>{html.escape(text)}</p><p><a href='{html.escape(box['back'])}'>Back to Reel Studio</a></p>").encode()
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = HTTPServer(("127.0.0.1", 0), Back)
    box["redirect"] = f"http://127.0.0.1:{server.server_address[1]}/"
    with _lock:
        for old in list(_pending.values()):  # one sign-in at a time
            threading.Thread(target=old["server"].shutdown, daemon=True).start()
        _pending.clear()
        _pending[state] = {**box, "server": server}

    def serve():
        timer = threading.Timer(CONNECT_WAIT, server.shutdown)
        timer.start()
        try:
            server.serve_forever(poll_interval=0.5)
        finally:
            timer.cancel()
            server.server_close()
            with _lock:
                _pending.pop(state, None)

    threading.Thread(target=serve, daemon=True).start()
    return URLS["auth"] + "?" + urlencode({
        "client_id": cid, "redirect_uri": box["redirect"], "response_type": "code", "scope": " ".join(SCOPES),
        # select_account: Google asks which account (and which of its channels) every time, so 'Add another channel'
        # can pick a different one
        "access_type": "offline", "prompt": "consent select_account", "include_granted_scopes": "true", "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256"})


def _exchange(cfg: Config, code: str, redirect: str, verifier: str) -> dict:
    cid, secret = client()
    r = requests.post(URLS["token"], data={"code": code, "client_id": cid, "client_secret": secret, "redirect_uri": redirect,
                                           "grant_type": "authorization_code", "code_verifier": verifier}, timeout=30)
    data = _json(r)
    if r.status_code != 200 or not data.get("refresh_token"):
        raise YouTubeError("Google didn't give a sign-in that lasts: " + (data.get("error_description") or data.get("error")
                                                                          or f"HTTP {r.status_code}"))
    tok = {"refresh_token": data["refresh_token"], "access_token": data.get("access_token", ""),
           "expires_at": time.time() + int(data.get("expires_in", 3600)), "scope": data.get("scope", ""),
           "connected_at": datetime.now().isoformat(timespec="seconds")}
    return tok  # saved by channel() into that channel's own folder


def disconnect(cfg: Config) -> None:
    """The active channel's sign-in is revoked and forgotten; its numbers and audits stay (they come back if you
    connect it again)."""
    tok = connected(cfg)
    if tok:
        try:
            requests.post(URLS["revoke"], data={"token": tok["refresh_token"]}, timeout=15)
        except requests.RequestException:
            pass
        _token_path(cfg, tok).unlink(missing_ok=True)
        if (_read(folder(cfg) / "active.json") or {}).get("id") == ((tok.get("channel") or {}).get("id")):
            (folder(cfg) / "active.json").unlink(missing_ok=True)


def _access(cfg: Config, tok: dict | None = None) -> str:
    tok = tok or connected(cfg)
    if not tok:
        raise YouTubeError("YouTube isn't connected yet (Settings > YouTube)")
    if tok.get("access_token") and tok.get("expires_at", 0) - 60 > time.time():
        return tok["access_token"]
    cid, secret = client()
    try:
        r = requests.post(URLS["token"], data={"client_id": cid, "client_secret": secret, "refresh_token": tok["refresh_token"],
                                               "grant_type": "refresh_token"}, timeout=30)
    except requests.RequestException as exc:
        raise YouTubeError(f"Couldn't reach Google to sign in: {exc}") from None
    data = _json(r)
    if r.status_code != 200:
        if data.get("error") == "invalid_grant":
            if tok.get("channel"):
                _token_path(cfg, tok).unlink(missing_ok=True)
            raise YouTubeError("Google ended the app's sign-in, so connect again in the YouTube tab. An OAuth app left in "
                               "'Testing' gets sign-ins that last 7 days: in Google Cloud > OAuth consent screen, press "
                               "'Publish app' to keep it connected.")
        raise YouTubeError("Google refused the sign-in: " + (data.get("error_description") or data.get("error") or str(r.status_code)))
    tok.update(access_token=data["access_token"], expires_at=time.time() + int(data.get("expires_in", 3600)))
    if tok.get("channel"):
        _write(_token_path(cfg, tok), tok)
    return tok["access_token"]


# ---------- calling Google ----------

def _json(r: requests.Response) -> dict:
    try:
        data = r.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


REASONS = {
    "quotaExceeded": "Your Google project used up today's YouTube quota. It resets at midnight Pacific time.",
    "uploadLimitExceeded": "YouTube's daily upload limit for this channel is reached. Try again tomorrow.",
    "youtubeSignupRequired": "This Google account has no YouTube channel yet. Create one on youtube.com first.",
    "invalidPublishAt": "That scheduled time doesn't work: it must be in the future, and only a private video that was "
                        "never public can be scheduled.",
    "accessNotConfigured": "An API isn't turned on in your Google Cloud project: enable 'YouTube Data API v3', "
                           "'YouTube Analytics API' and 'YouTube Reporting API' (APIs & Services > Library).",
    "SERVICE_DISABLED": "An API isn't turned on in your Google Cloud project: enable 'YouTube Data API v3', "
                        "'YouTube Analytics API' and 'YouTube Reporting API' (APIs & Services > Library).",
    "invalidTitle": "YouTube refused the title (empty, over 100 characters, or with < or >).",
    "invalidDescription": "YouTube refused the description (over 5,000 bytes, or with < or >).",
    "invalidTags": "YouTube refused the tags (over 500 characters in all).",
    "insufficientPermissions": "The sign-in doesn't allow this. Disconnect and connect again in Settings > YouTube.",
}


def _problem(r: requests.Response, what: str) -> YouTubeError:
    data = _json(r)
    err = data.get("error") if isinstance(data.get("error"), dict) else {}
    reasons = [e.get("reason", "") for e in err.get("errors", []) if isinstance(e, dict)]
    reasons += [d.get("reason", "") for d in err.get("details", []) if isinstance(d, dict)]
    for reason in reasons:
        if reason in REASONS:
            return YouTubeError(f"{what}: {REASONS[reason]}")
    if what.startswith("Thumbnail") and r.status_code == 403:
        return YouTubeError("Thumbnail: YouTube allows custom thumbnails only on a verified channel. Verify it with a phone "
                            "number at youtube.com/verify, then try again.")
    msg = err.get("message") or data.get("error_description") or r.text[:300] or f"HTTP {r.status_code}"
    return YouTubeError(f"{what}: {msg}")


def _call(cfg: Config, method: str, url: str, what: str, ok=(200,), **kw) -> requests.Response:
    """One Google call with the sign-in, retried on 5xx/429 and dropped connections."""
    for attempt in range(4):
        stopper.check()
        headers = {"Authorization": "Bearer " + _access(cfg), **kw.pop("headers", {})}
        try:
            r = requests.request(method, url, headers=headers, timeout=kw.pop("timeout", 60), **kw)
        except requests.RequestException as exc:
            if attempt == 3:
                raise YouTubeError(f"{what}: couldn't reach Google ({exc})") from None
            stopper.sleep(2 ** attempt * 2)
            continue
        if r.status_code in ok:
            return r
        if r.status_code == 401 and attempt == 0:  # the access token ran out early: refresh once
            tok = connected(cfg) or {}
            if tok:
                tok["expires_at"] = 0
                _write(_token_path(cfg, tok), tok)
            continue
        if r.status_code in (429, 500, 502, 503, 504) and attempt < 3:
            stopper.sleep(2 ** attempt * 3)
            continue
        raise _problem(r, what)
    raise YouTubeError(f"{what}: Google didn't answer")


def _get(cfg: Config, path: str, what: str, **params) -> dict:
    return _call(cfg, "GET", URLS["api"] + path, what, params=params).json()


# ---------- the channel and its videos ----------

def channel(cfg: Config, tok: dict | None = None) -> dict:
    """The connected channel (saved in token.json so Settings shows it without a call)."""
    headers = {"Authorization": "Bearer " + _access(cfg, tok)}
    r = requests.get(URLS["api"] + "/channels", params={"part": "snippet,statistics,contentDetails", "mine": "true"},
                     headers=headers, timeout=30)
    if r.status_code != 200:
        raise _problem(r, "Your channel")
    items = r.json().get("items") or []
    if not items:
        raise YouTubeError(REASONS["youtubeSignupRequired"])
    c = items[0]
    sn, st = c.get("snippet", {}), c.get("statistics", {})
    thumbs = sn.get("thumbnails") or {}
    ch = {"id": c["id"], "title": sn.get("title", ""), "handle": sn.get("customUrl", ""),
          "thumb": (thumbs.get("default") or {}).get("url", ""),
          "published": sn.get("publishedAt", ""), "subscribers": int(st.get("subscriberCount", 0) or 0),
          "views": int(st.get("viewCount", 0) or 0), "videos": int(st.get("videoCount", 0) or 0),
          "uploads": ((c.get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads", "")}
    tok = tok or connected(cfg) or {}
    if tok:
        tok["channel"] = ch
        _write(_token_path(cfg, tok), tok)
        _save_avatar(cfg, ch, (thumbs.get("medium") or thumbs.get("default") or {}).get("url", ""))
    return ch


def _duration(iso: str) -> float:
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0.0
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return float(((d * 24 + h) * 60 + mi) * 60 + s)


def _video_row(v: dict) -> dict:
    sn, st, cd, status = v.get("snippet", {}), v.get("statistics", {}), v.get("contentDetails", {}), v.get("status", {})
    thumbs = sn.get("thumbnails") or {}
    return {"id": v["id"], "title": sn.get("title", ""), "description": sn.get("description", ""), "tags": sn.get("tags", []),
            "category": sn.get("categoryId", ""), "published": sn.get("publishedAt", ""),
            "thumb": (thumbs.get("medium") or thumbs.get("default") or {}).get("url", ""),
            "duration": _duration(cd.get("duration", "")), "privacy": status.get("privacyStatus", ""),
            "publish_at": status.get("publishAt", ""), "made_for_kids": bool(status.get("selfDeclaredMadeForKids")),
            "synthetic": bool(status.get("containsSyntheticMedia")), "upload_status": status.get("uploadStatus", ""),
            "views": int(st.get("viewCount", 0) or 0), "likes": int(st.get("likeCount", 0) or 0),
            "comments": int(st.get("commentCount", 0) or 0)}


def video(cfg: Config, vid: str) -> dict:
    items = _get(cfg, "/videos", "Reading the video", part="snippet,status,statistics,contentDetails,processingDetails",
                 id=vid).get("items") or []
    if not items:
        raise YouTubeError("That video isn't on your channel (or it was deleted)")
    row = _video_row(items[0])
    row["processing"] = (items[0].get("processingDetails") or {}).get("processingStatus", "")
    return row


def _all_videos(cfg: Config, uploads: str) -> list[dict]:
    ids, token = [], None
    while True:
        page = _get(cfg, "/playlistItems", "Listing your videos", part="contentDetails", playlistId=uploads,
                    maxResults=50, **({"pageToken": token} if token else {}))
        ids += [i["contentDetails"]["videoId"] for i in page.get("items", [])]
        token = page.get("nextPageToken")
        if not token:
            break
    rows = []
    for k in range(0, len(ids), 50):
        got = _get(cfg, "/videos", "Reading your videos", part="snippet,status,statistics,contentDetails",
                   id=",".join(ids[k:k + 50]), maxResults=50)
        rows += [_video_row(v) for v in got.get("items", [])]
    return rows


# ---------- analytics ----------

def _report(cfg: Config, what: str, **params) -> list[dict]:
    r = _call(cfg, "GET", URLS["analytics"], what, params={"ids": "channel==MINE", **params})
    data = r.json()
    names = [h["name"] for h in data.get("columnHeaders", [])]
    return [dict(zip(names, row)) for row in data.get("rows") or []]


def _lifetime(ch: dict) -> dict:
    start = (ch.get("published") or "2005-04-23")[:10]
    return {"startDate": start, "endDate": date.today().isoformat()}


def _num(x) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _ctr_scale(values: list[float | None]) -> float:
    """Google calls the click-through rate a 'percentage' but defines it as clicks / impressions, and the unit wasn't
    confirmed on a real channel: decided once for a whole set (any value over 1 means the set is in percent; a real
    CTR over 100% can't happen), so a low CTR like 0.8% is never read as 80%."""
    return 100.0 if any(v is not None and v > 1 for v in values) else 1.0


def _reach_targeted(cfg: Config, ch: dict) -> dict[str, dict]:
    rows, start = [], 1
    while True:
        got = _report(cfg, "Impressions", dimensions="video", metrics="videoThumbnailImpressions,videoThumbnailImpressionsClickRate",
                      sort="-videoThumbnailImpressions", maxResults=200, startIndex=start, **_lifetime(ch))
        rows += got
        if len(got) < 200:
            break
        start += 200
    scale = _ctr_scale([_num(r.get("videoThumbnailImpressionsClickRate")) for r in rows])
    return {r["video"]: {"impressions": int(_num(r.get("videoThumbnailImpressions")) or 0),
                         "ctr": None if _num(r.get("videoThumbnailImpressionsClickRate")) is None
                         else _num(r["videoThumbnailImpressionsClickRate"]) / scale} for r in rows}


def _reach_reports(cfg: Config) -> tuple[dict[str, dict], str]:
    """Impressions and click-through rate from the Reporting API's daily reach reports (cached in youtube/reach/)."""
    base = URLS["reporting"]
    jobs = _call(cfg, "GET", base + "/jobs", "Impressions report").json().get("jobs", [])
    job = next((j for j in jobs if j.get("reportTypeId") == REACH_REPORT), None)
    if job is None:
        job = _call(cfg, "POST", base + "/jobs", "Impressions report",
                    json={"reportTypeId": REACH_REPORT, "name": "Reel Studio reach"}).json()
        return {}, ("YouTube is preparing your impressions and click-through report: the first one comes within 48 hours, "
                    "then it covers the 30 days before. Refresh again then.")
    reports, token = [], None
    while True:
        page = _call(cfg, "GET", f"{base}/jobs/{job['id']}/reports", "Impressions report",
                     params={"pageToken": token} if token else None).json()
        reports += page.get("reports", [])
        token = page.get("nextPageToken")
        if not token:
            break
    if not reports:
        return {}, "YouTube hasn't written the first impressions report yet (it takes up to 48 hours). Refresh again later."
    # a day's report written again (backfill) replaces the earlier one
    latest: dict[str, dict] = {}
    for rep in reports:
        key = rep.get("startTime", "")
        if key not in latest or rep.get("createTime", "") > latest[key].get("createTime", ""):
            latest[key] = rep
    cache = home(cfg) / "reach"
    cache.mkdir(exist_ok=True)
    raw: list[tuple[str, int, float]] = []
    for rep in latest.values():
        path = cache / (re.sub(r"[^\w-]", "_", rep["id"]) + ".csv")
        if not path.exists():
            r = _call(cfg, "GET", rep["downloadUrl"], "Impressions report", timeout=120)
            path.write_bytes(r.content)
        for row in csv.DictReader(io.StringIO(path.read_text(encoding="utf-8", errors="replace"))):
            if row.get("video_id"):
                raw.append((row["video_id"], int(_num(row.get("video_thumbnail_impressions")) or 0),
                            _num(row.get("video_thumbnail_impressions_ctr")) or 0.0))
    scale = _ctr_scale([c for _v, _n, c in raw])
    shown, clicks = {}, {}
    for vid, n, ctr in raw:
        shown[vid] = shown.get(vid, 0) + n
        clicks[vid] = clicks.get(vid, 0) + n * ctr / scale
    days = sorted(latest)
    span = f"{days[0][:10]} to {days[-1][:10]}" if days else ""
    return ({v: {"impressions": n, "ctr": (clicks[v] / n) if n else None} for v, n in shown.items()},
            f"Impressions and click-through rate from YouTube's daily reports, {span} (not lifetime).")


def refresh(cfg: Config, progress=None) -> dict:
    """Every video on the channel with its lifetime numbers, saved in youtube/videos.json."""
    say = progress or (lambda _m: None)
    ch = channel(cfg)
    say(f"Reading the {ch['videos']} videos of {ch['title']}")
    rows = _all_videos(cfg, ch["uploads"]) if ch["uploads"] else []
    by_id = {r["id"]: r for r in rows}
    say("Reading their analytics")
    start = 1
    while True:
        got = _report(cfg, "Analytics", dimensions="video", metrics=",".join(STATS), sort="-views", maxResults=200,
                      startIndex=start, **_lifetime(ch))
        for r in got:
            if r["video"] in by_id:
                by_id[r["video"]]["stats"] = {k: r.get(k) for k in STATS}
        if len(got) < 200:
            break
        start += 200
    reach_note = ""
    try:
        reach = _reach_targeted(cfg, ch)
        reach_note = "Impressions and click-through rate over each video's lifetime."
    except YouTubeError:
        try:
            reach, reach_note = _reach_reports(cfg)
        except YouTubeError as exc:
            reach, reach_note = {}, f"Impressions and click-through rate aren't available: {exc}"
    for vid, r in reach.items():
        if vid in by_id:
            by_id[vid]["reach"] = r
    for r in rows:
        r["short"] = r["duration"] <= 180  # YouTube treats vertical videos up to 3 minutes as Shorts
    try:
        daily = _daily(cfg, ch)
    except YouTubeError:
        daily = []
    data = {"fetched_at": datetime.now().isoformat(timespec="seconds"), "channel": ch, "reach_note": reach_note,
            "daily": daily, "videos": sorted(rows, key=lambda r: r.get("published", ""), reverse=True)}
    _write(home(cfg) / "videos.json", data)
    return data


DAILY_DAYS = 90


def _daily(cfg: Config, ch: dict) -> list[dict]:
    """The channel's views and new subscribers per day over the last 90 days (for the audit's line chart)."""
    start = max(date.fromisoformat((ch.get("published") or "2005-04-23")[:10]), date.today() - timedelta(days=DAILY_DAYS))
    rows = _report(cfg, "Daily views", dimensions="day", metrics="views,subscribersGained,estimatedMinutesWatched",
                   sort="day", startDate=start.isoformat(), endDate=date.today().isoformat())
    return [{"day": r["day"], "views": int(_num(r.get("views")) or 0), "subs": int(_num(r.get("subscribersGained")) or 0),
             "minutes": round(_num(r.get("estimatedMinutesWatched")) or 0, 1)} for r in rows]


def cached(cfg: Config) -> dict | None:
    return _read(home(cfg) / "videos.json") if active(cfg) else None


def details(cfg: Config, vid: str) -> dict:
    """One video: where viewers leave (audience retention) and where they came from (traffic sources)."""
    ch = (connected(cfg) or {}).get("channel") or channel(cfg)
    when = _lifetime(ch)
    retention = _report(cfg, "Audience retention", dimensions="elapsedVideoTimeRatio",
                        metrics="audienceWatchRatio,relativeRetentionPerformance", filters=f"video=={vid}", **when)
    sources = _report(cfg, "Traffic sources", dimensions="insightTrafficSourceType", metrics="views,estimatedMinutesWatched",
                      filters=f"video=={vid}", sort="-views", **when)
    out = {"id": vid, "fetched_at": datetime.now().isoformat(timespec="seconds"),
           "retention": [{"at": float(r["elapsedVideoTimeRatio"]), "watching": r.get("audienceWatchRatio"),
                          "vs_similar": r.get("relativeRetentionPerformance")} for r in retention],
           "sources": [{"source": r["insightTrafficSourceType"], "views": r.get("views"),
                        "minutes": r.get("estimatedMinutesWatched")} for r in sources]}
    path = home(cfg) / "details"
    path.mkdir(exist_ok=True)
    safe = re.sub(r"[^\w-]", "_", vid)
    _write(path / f"{safe}.json", out)
    return out


def table_csv(data: dict) -> str:
    """The videos table as CSV (Settings-free: what you'd export from YouTube Studio's Advanced mode)."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["video_id", "title", "published", "format", "duration_s", "privacy", "views", "likes", "comments",
                "impressions", "ctr_percent", "avg_view_duration_s", "avg_percent_viewed", "watch_minutes", "subscribers_gained",
                "shares", "url"])
    for v in data.get("videos", []):
        st, rc = v.get("stats") or {}, v.get("reach") or {}
        w.writerow([v["id"], v["title"], v["published"][:10], "short" if v.get("short") else "long", round(v["duration"]),
                    v["privacy"], v["views"], v["likes"], v["comments"], rc.get("impressions", ""),
                    "" if rc.get("ctr") is None else round(rc["ctr"] * 100, 2), st.get("averageViewDuration", ""),
                    st.get("averageViewPercentage", ""), st.get("estimatedMinutesWatched", ""), st.get("subscribersGained", ""),
                    st.get("shares", ""), "https://youtu.be/" + v["id"]])
    return buf.getvalue()


# ---------- what goes up: the details of a library video ----------

def clean_text(text: str, limit: int) -> str:
    """YouTube refuses '<' and '>' in titles and descriptions and counts the description in bytes."""
    text = (text or "").replace("<", "‹").replace(">", "›").strip()
    while len(text.encode("utf-8")) > limit:
        text = text[:-1]
    return text


def fit_tags(tags: list[str]) -> list[str]:
    out, total = [], 0
    for t in tags:
        t = clean_text(str(t).lstrip("#"), 100)
        cost = len(t) + (2 if " " in t else 0) + (1 if out else 0)  # YouTube counts quotes round a tag with spaces
        if t and t.lower() not in {x.lower() for x in out} and total + cost <= TAGS_MAX:
            out.append(t)
            total += cost
    return out


def plan_for(report: dict, folder_path: Path) -> dict:
    """What the app would upload for a finished video: its own title, description, hashtags and tags, its category,
    its thumbnail, made-for-kids No, and the synthetic-content box ticked for photoreal pipelines."""
    title = report.get("youtube_title") or report.get("title") or report.get("topic") or folder_path.name
    desc = report.get("youtube_description") or report.get("caption") or ""
    tags = [h for h in report.get("youtube_hashtags") or report.get("hashtags") or [] if h]
    if tags and not any(f"#{t}".lower() in desc.lower() for t in tags):
        desc = (desc + "\n\n" + " ".join(f"#{t}" for t in tags)).strip()
    short = report.get("format") == "short" or report.get("length") in ("short", "storyshorts", "stick-short", "journey")
    lang = "hi" if re.search(r"[ऀ-ॿ]", title + desc) or "hi-IN" in str(report.get("voice", "")) else "en"
    files = [f for f in VIDEO_FILES if (folder_path / f).exists()]
    thumb = "thumbnail-youtube.jpg" if (folder_path / "thumbnail-youtube.jpg").exists() else ""
    source = report.get("source", "")
    realistic = source in REALISTIC_SOURCES or report.get("style") == "divine-epic" or report.get("kind") == "divine"
    return {"title": clean_text(title, 400)[:TITLE_MAX], "description": clean_text(desc, DESCRIPTION_MAX),
            "tags": fit_tags(report.get("youtube_tags") or []), "category": CATEGORY_IDS.get(report.get("category", ""), "22"),
            "privacy": "private", "publish_at": "", "made_for_kids": False, "synthetic": bool(realistic),
            "language": lang, "file": files[0] if files else "", "files": files, "thumbnail": thumb, "short": short}


def _meta(p: dict) -> dict:
    snippet = {"title": clean_text(p["title"], 400)[:TITLE_MAX], "description": clean_text(p.get("description", ""), DESCRIPTION_MAX),
               "tags": fit_tags(p.get("tags") or []), "categoryId": str(p.get("category") or "22")}
    if p.get("language"):
        snippet["defaultLanguage"] = snippet["defaultAudioLanguage"] = p["language"]
    status = {"privacyStatus": p.get("privacy") or "private", "selfDeclaredMadeForKids": bool(p.get("made_for_kids")),
              "containsSyntheticMedia": bool(p.get("synthetic"))}
    if p.get("publish_at"):
        status.update(privacyStatus="private", publishAt=publish_time(p["publish_at"]))
    if not snippet["title"]:
        raise YouTubeError("The title is empty")
    return {"snippet": snippet, "status": status}


def publish_time(value: str) -> str:
    """A scheduled time from the page (its own time zone offset included) as UTC, at least 15 minutes ahead."""
    try:
        when = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise YouTubeError(f"'{value}' isn't a date and time") from None
    if when.tzinfo is None:
        when = when.astimezone()  # this computer's time zone
    when = when.astimezone(timezone.utc)
    if when.timestamp() < time.time() + 15 * 60:
        raise YouTubeError("Pick a time at least 15 minutes from now to schedule it")
    return when.strftime("%Y-%m-%dT%H:%M:%S.000Z")


# ---------- upload (a job) ----------

def upload(cfg: Config, folder_path: Path, opts: dict, progress) -> dict:
    """A finished video up to the channel, resumable: a stopped or failed upload carries on from where it got to
    (Google keeps an upload session about a week; youtube-upload.json remembers it)."""
    stopper.set_checks(getattr(progress, "should_pause", None))
    report_path = folder_path / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if (report.get("youtube") or {}).get("id"):
        raise YouTubeError(f"This video is already on YouTube: https://youtu.be/{report['youtube']['id']}")
    name = opts.get("file") or "reel.mp4"
    if name not in VIDEO_FILES or not (folder_path / name).exists():
        raise YouTubeError(f"{name} isn't in this video's folder")
    path = folder_path / name
    size = path.stat().st_size
    meta = _meta(opts)
    sig = hashlib.sha1(json.dumps([name, size, int(path.stat().st_mtime), meta, active(cfg)], sort_keys=True).encode()).hexdigest()
    state_path = folder_path / "youtube-upload.json"
    state = _read(state_path, {}) or {}
    session = state.get("session") if state.get("sig") == sig else None
    offset = 0
    if session:
        offset = _offset(cfg, session, size)
        if offset is None:
            session = None
    if not session:
        progress(f"Starting the upload of {name} ({size / 1e6:.0f} MB) to YouTube")
        r = _call(cfg, "POST", URLS["upload"] + "/videos", "Upload", ok=(200,),
                  params={"uploadType": "resumable", "part": "snippet,status", "notifySubscribers": "true"},
                  json=meta, headers={"X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)})
        session = r.headers.get("Location")
        if not session:
            raise YouTubeError("Upload: Google gave no upload address")
        _write(state_path, {"sig": sig, "session": session, "started": datetime.now().isoformat(timespec="seconds")})
        offset = 0
    else:
        progress(f"Carrying on the upload from {offset / 1e6:.0f} of {size / 1e6:.0f} MB")
    done = None if offset < size else _offset(cfg, session, size, finished=True)
    fails = 0
    with path.open("rb") as fh:
        while done is None:
            stopper.check()
            fh.seek(offset)
            piece = fh.read(CHUNK)
            end = offset + len(piece) - 1
            try:
                r = requests.put(session, data=piece, timeout=300, headers={
                    "Authorization": "Bearer " + _access(cfg), "Content-Type": "video/mp4",
                    "Content-Range": f"bytes {offset}-{end}/{size}"})
            except requests.RequestException:
                r = None
            if r is not None and r.status_code in (200, 201):
                done = r.json()
                break
            if r is not None and r.status_code == 308:
                got = re.search(r"bytes=0-(\d+)", r.headers.get("Range", ""))
                offset = int(got[1]) + 1 if got else 0
                fails = 0
                progress(f"§live Uploading to YouTube: {offset * 100 // size}% ({offset / 1e6:.0f} of {size / 1e6:.0f} MB)")
                continue
            if r is not None and r.status_code not in (408, 429, 500, 502, 503, 504):
                state_path.unlink(missing_ok=True)
                raise _problem(r, "Upload")
            fails += 1
            if fails > 8:
                raise YouTubeError("Upload: the connection keeps dropping. Press Upload again later: it carries on from "
                                   f"{offset / 1e6:.0f} MB.")
            stopper.sleep(min(60, 2 ** fails))
            got = _offset(cfg, session, size)
            if got is None:
                state_path.unlink(missing_ok=True)
                raise YouTubeError("Upload: Google dropped the upload session. Press Upload again to start over.")
            offset = got
    vid = done["id"]
    state_path.unlink(missing_ok=True)
    progress(f"Uploaded: https://youtu.be/{vid}")
    info = {"id": vid, "url": f"https://youtu.be/{vid}", "studio": f"https://studio.youtube.com/video/{vid}/edit",
            "uploaded_at": datetime.now().isoformat(timespec="seconds"), "file": name,
            "privacy": meta["status"]["privacyStatus"], "publish_at": meta["status"].get("publishAt", ""),
            "title": meta["snippet"]["title"], "channel": active(cfg)}
    thumb = opts.get("thumbnail") or ""
    if thumb:
        info["thumbnail"] = _thumb_after_upload(cfg, vid, folder_path / Path(thumb).name, progress)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["youtube"] = info
    now = datetime.now().isoformat(timespec="seconds")
    old = report.get("posted") or {}
    report["posted"] = {"at": old.get("at", now), "last": now, "file": name, "times": int(old.get("times", 0)) + 1,
                        "youtube": vid}
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def _offset(cfg: Config, session: str, size: int, finished: bool = False):
    """How much of an upload Google has: the next byte to send, or the finished video resource (finished=True)."""
    try:
        r = requests.put(session, timeout=60, headers={"Authorization": "Bearer " + _access(cfg),
                                                       "Content-Range": f"bytes */{size}"})
    except requests.RequestException:
        return 0 if not finished else None
    if r.status_code in (200, 201):
        return r.json() if finished else size
    if r.status_code == 308:
        got = re.search(r"bytes=0-(\d+)", r.headers.get("Range", ""))
        return int(got[1]) + 1 if got else 0
    return None


def _thumb_after_upload(cfg: Config, vid: str, path: Path, progress) -> str:
    """Set the thumbnail; a Short takes it only after processing, so wait for that (up to 15 min) and try again."""
    if not path.exists():
        return "missing"
    try:
        set_thumbnail(cfg, vid, path)
        return "set"
    except YouTubeError as exc:
        if "verified channel" in str(exc):
            progress(str(exc))
            return "needs a verified channel"
        progress("Waiting for YouTube to finish processing before setting the thumbnail")
    for _ in range(60):
        stopper.sleep(15)
        try:
            state = video(cfg, vid).get("processing")
        except YouTubeError:
            continue
        if state in ("succeeded", "failed", "terminated"):
            break
    try:
        set_thumbnail(cfg, vid, path)
        return "set"
    except YouTubeError as exc:
        progress(f"The video is up, but the thumbnail wasn't set: {exc}")
        return "failed: " + str(exc)[:200]


# ---------- editing a video on the channel ----------

def set_thumbnail(cfg: Config, vid: str, path: Path) -> None:
    data = path.read_bytes()
    if len(data) > THUMB_MAX:
        raise YouTubeError("Thumbnail: over 50 MB")
    kind = "image/png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg" if data[:2] == b"\xff\xd8" else ""
    if not kind:
        raise YouTubeError("Thumbnail: use a JPG or PNG picture")
    _call(cfg, "POST", URLS["upload"] + "/thumbnails/set", "Thumbnail", params={"videoId": vid}, data=data,
          headers={"Content-Type": kind}, timeout=120)


def update(cfg: Config, vid: str, changes: dict) -> dict:
    """Title, description, tags, category, privacy, schedule, made-for-kids and synthetic disclosure of one video.
    Google's update replaces the whole snippet and status, so everything not changed is sent back as it is."""
    items = _get(cfg, "/videos", "Reading the video", part="snippet,status", id=vid).get("items") or []
    if not items:
        raise YouTubeError("That video isn't on your channel (or it was deleted)")
    sn, st = items[0]["snippet"], items[0]["status"]
    snippet = {"title": sn.get("title", ""), "description": sn.get("description", ""), "tags": sn.get("tags", []),
               "categoryId": sn.get("categoryId", "22")}
    for key in ("defaultLanguage", "defaultAudioLanguage"):
        if sn.get(key):
            snippet[key] = sn[key]
    if "title" in changes:
        snippet["title"] = clean_text(changes["title"], 400)[:TITLE_MAX]
        if not snippet["title"]:
            raise YouTubeError("The title is empty")
    if "description" in changes:
        snippet["description"] = clean_text(changes["description"], DESCRIPTION_MAX)
    if "tags" in changes:
        snippet["tags"] = fit_tags(changes["tags"] or [])
    if changes.get("category"):
        snippet["categoryId"] = str(changes["category"])
    status = {k: st[k] for k in ("privacyStatus", "embeddable", "license", "publicStatsViewable", "publishAt",
                                 "selfDeclaredMadeForKids", "containsSyntheticMedia") if k in st}
    if "made_for_kids" in changes:
        status["selfDeclaredMadeForKids"] = bool(changes["made_for_kids"])
    if "synthetic" in changes:
        status["containsSyntheticMedia"] = bool(changes["synthetic"])
    if changes.get("privacy"):
        status["privacyStatus"] = changes["privacy"]
        status.pop("publishAt", None)
    if "publish_at" in changes:
        if changes["publish_at"]:
            if st.get("privacyStatus") == "public" and not st.get("publishAt"):
                raise YouTubeError("This video is already public, so it can't be scheduled")
            status.update(privacyStatus="private", publishAt=publish_time(changes["publish_at"]))
        else:
            status.pop("publishAt", None)
    body = {"id": vid, "snippet": snippet, "status": status}
    r = _call(cfg, "PUT", URLS["api"] + "/videos", "Saving the changes", params={"part": "snippet,status"}, json=body)
    return _video_row(r.json())


def youtube_id(text: str) -> str:
    """A video id from an id, a youtu.be / watch / shorts / Studio link."""
    text = (text or "").strip()
    for pat in (r"youtu\.be/([\w-]{11})", r"[?&]v=([\w-]{11})", r"/shorts/([\w-]{11})", r"/video/([\w-]{11})",
                r"/live/([\w-]{11})", r"^([\w-]{11})$"):
        m = re.search(pat, text)
        if m:
            return m[1]
    raise YouTubeError("That isn't a YouTube video link")


# ---------- the audit (Claude reads the numbers) ----------
# What makes it accurate: every count, sum, median and bucket is worked out here in code and handed over as facts;
# each video is cited as [[n]] (its row number), so the page shows its thumbnail and title instead of an id; every
# figure Claude writes in its evidence is looked up in the data afterwards, a figure not found is sent back once to
# be corrected, and one still not found is marked on the page. Each audit is kept (audits/) with a snapshot of the
# numbers it saw, so the tab shows the history, its charts, and what changed since.

CHARTS = ("none", "length_vs_viewed", "views", "retention", "daily", "ctr_vs_views", "subs", "comments")
REF = re.compile(r"\[\[(\d+)\]\]")
RETENTION_FOR = 30  # videos whose audience retention is read for the audit (public ones, most viewed first)
RETENTION_POINTS = 24


def _audits_dir(cfg: Config) -> Path:
    d = home(cfg) / "audits"
    if not d.exists():
        d.mkdir(parents=True, exist_ok=True)
        old = _read(home(cfg) / "audit.json")  # the first version kept only the latest audit
        if old and old.get("made"):
            _write(d / (re.sub(r"[^\w-]", "-", old["made"]) + ".json"), old)
    return d


def _retention(cfg: Config, v: dict) -> dict | None:
    """Where viewers leave, read from YouTube (cached a day per video) and summed up in seconds."""
    path = home(cfg) / "details" / (re.sub(r"[^\w-]", "_", v["id"]) + ".json")
    got = _read(path)
    fresh = got and got.get("fetched_at", "") >= (datetime.now() - timedelta(hours=24)).isoformat(timespec="seconds")
    if not fresh:
        try:
            got = details(cfg, v["id"])
        except YouTubeError:
            return None
    pts = [(float(r["at"]), _num(r.get("watching"))) for r in got.get("retention") or [] if _num(r.get("watching")) is not None]
    dur = v.get("duration") or 0
    if len(pts) < 3 or not dur:
        return None
    pts.sort()

    def at(frac: float) -> float:
        for (a, wa), (b, wb) in zip(pts, pts[1:]):
            if a <= frac <= b:
                return wa + (wb - wa) * ((frac - a) / (b - a) if b > a else 0)
        return pts[0][1] if frac < pts[0][0] else pts[-1][1]

    half = next((a for a, w in pts if w < 0.5), None)
    step = max(1, len(pts) // RETENTION_POINTS)
    return {"at_3s": round(at(min(1.0, 3 / dur)) * 100, 1), "half_gone_at": None if half is None else round(half * dur),
            "at_end": round(at(0.95) * 100, 1),
            "curve": [[round(a * dur, 1), round(w * 100, 1)] for a, w in pts[::step]]}


def _median(xs: list[float]) -> float | None:
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    m = len(xs) // 2
    return round(xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2, 2)


def _norm_title(t: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"#\w+|[^\w\s]", " ", t.lower())).strip()


def snapshot(cfg: Config, data: dict, retention: dict[str, dict]) -> dict:
    """The numbers an audit saw, kept with it (charts and 'since this audit' are drawn from these)."""
    vids = []
    for n, v in enumerate(data.get("videos", []), 1):
        st, rc = v.get("stats") or {}, v.get("reach") or {}
        vids.append({"n": n, "id": v["id"], "title": v["title"], "thumb": v.get("thumb", ""), "short": bool(v.get("short")),
                     "duration": round(v.get("duration") or 0), "privacy": v.get("privacy", ""), "published": v.get("published", "")[:10],
                     "views": v.get("views", 0), "likes": v.get("likes", 0), "comments": v.get("comments", 0),
                     "viewed": _num(st.get("averageViewPercentage")), "avg_seconds": _num(st.get("averageViewDuration")),
                     "subs": _num(st.get("subscribersGained")), "shares": _num(st.get("shares")),
                     "impressions": rc.get("impressions"), "ctr": None if rc.get("ctr") is None else round(rc["ctr"] * 100, 2),
                     "retention": retention.get(v["id"])})
    ch = data.get("channel") or {}
    return {"fetched_at": data.get("fetched_at", ""), "channel": {k: ch.get(k) for k in ("id", "title", "subscribers", "views", "videos")},
            "reach_note": data.get("reach_note", ""), "daily": data.get("daily") or [], "videos": vids}


def facts(snap: dict) -> dict:
    """Counts, sums, medians and buckets worked out here, so Claude never has to count."""
    vids = snap["videos"]
    pub = [v for v in vids if v["privacy"] == "public"]
    shorts, longs = [v for v in pub if v["short"]], [v for v in pub if not v["short"]]
    views = sum(v["views"] for v in pub)
    subs = sum(v["subs"] or 0 for v in vids)
    buckets = []
    for name, lo, hi in (("up to 45 s", 0, 45), ("46 to 60 s", 46, 60), ("61 to 90 s", 61, 90), ("over 90 s", 91, 10 ** 6)):
        b = [v for v in shorts if lo <= v["duration"] <= hi]
        if b:
            buckets.append({"length": name, "shorts": len(b), "median_viewed_percent": _median([v["viewed"] for v in b]),
                            "median_views": _median([v["views"] for v in b])})
    groups: dict[str, list[dict]] = {}
    for v in vids:
        groups.setdefault(_norm_title(v["title"]), []).append(v)
    dupes = [[f"[[{v['n']}]] ({v['privacy']})" for v in g] for g in groups.values() if len(g) > 1]
    daily = snap.get("daily") or []
    last28 = daily[-28:]
    return {
        "public_shorts": len(shorts), "public_long_videos": len(longs), "private_or_unlisted": len(vids) - len(pub),
        "views_public_shorts": sum(v["views"] for v in shorts), "views_public_long_videos": sum(v["views"] for v in longs),
        "median_views_public_shorts": _median([v["views"] for v in shorts]),
        "median_viewed_percent_public_shorts": _median([v["viewed"] for v in shorts]),
        "median_viewed_percent_public_long_videos": _median([v["viewed"] for v in longs]),
        "public_shorts_with_comments": sum(1 for v in shorts if v["comments"]),
        "subscribers_gained_all_videos": subs, "subscribers_per_1000_views": round(subs / views * 1000, 2) if views else None,
        "subscribers_as_percent_of_views": round(subs / views * 100, 2) if views else None,
        "shorts_by_length": buckets, "same_title_uploaded_more_than_once": dupes,
        "views_last_28_days": sum(d["views"] for d in last28) if last28 else None,
        "subscribers_last_28_days": sum(d["subs"] for d in last28) if last28 else None,
        "impressions_available": any(v["impressions"] for v in vids),
    }


def audit_table(snap: dict, made: dict[str, dict]) -> str:
    """Every video in one line Claude can read: its row number, its numbers, and how the app made it."""
    lines = []
    for v in snap["videos"]:
        rep, r = made.get(v["id"], {}), v.get("retention") or {}
        how = ""
        if rep:
            how = " | made by the app: " + ", ".join(f"{k}={rep[k]}" for k in ("source", "length", "style", "hook_template",
                                                                               "voice", "captions", "category") if rep.get(k))
        hold = (f" | still watching at 3 s: {r['at_3s']}% | half gone by {r['half_gone_at']} s | still watching at the end: "
                f"{r['at_end']}%") if r else ""
        lines.append(
            f"[[{v['n']}]] {v['title']!r} | {'Short' if v['short'] else 'long'} {v['duration']} s | {v['privacy']} | "
            f"published {v['published']} | views {v['views']} | impressions {v['impressions'] if v['impressions'] is not None else '?'} | "
            f"CTR {str(v['ctr']) + '%' if v['ctr'] is not None else '?'} | average viewed {v['viewed'] if v['viewed'] is not None else '?'}% "
            f"({v['avg_seconds'] if v['avg_seconds'] is not None else '?'} s) | likes {v['likes']} | comments {v['comments']} | "
            f"subscribers +{v['subs'] if v['subs'] is not None else '?'}{hold}{how}")
    return "\n".join(lines)


NUMBER = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?(\s*%|\s*s\b|\s*sec)?")


def _values(snap: dict, fx: dict, previous: dict | None) -> list[float]:
    """Every figure an audit may state: the table's, the facts', sums of a row's parts, the titles' own numbers."""
    out: list[float] = []

    def add(x):
        x = _num(x)
        if x is not None:
            out.append(x)

    def walk(o):
        if isinstance(o, dict):
            for k, val in o.items():
                if k not in ("curve", "published", "fetched_at", "day"):
                    walk(val)
        elif isinstance(o, (list, tuple)):
            for val in o:
                walk(val)
        elif isinstance(o, str):
            for m in NUMBER.finditer(o):
                add(m[1].replace(",", "") + ("." + m[2] if m[2] else ""))
        else:
            add(o)

    out += [3.0, 100.0]  # 'still watching at 3 s' and 100% are the audit's own words
    walk(snap["channel"])
    walk(fx)
    for v in snap["videos"]:
        walk({k: v[k] for k in v if k not in ("id", "thumb", "published")})
        if v["duration"] and v["duration"] >= 60:
            add(v["duration"] / 60)
        if v["avg_seconds"]:
            add(v["avg_seconds"] / 60)
    for d in snap.get("daily") or []:
        add(d["views"])
    if previous:
        walk(previous)
    return out


def check_figures(text: str, values: list[float]) -> list[str]:
    """The figures in a sentence that aren't in the data (small counts and years are left alone)."""
    bad = []
    for m in NUMBER.finditer(REF.sub("", text)):
        whole, dec, unit = m[1].replace(",", ""), m[2] or "", (m[3] or "").strip()
        x = float(whole + ("." + dec if dec else ""))
        if not dec and not unit and (x <= 10 or 1990 <= x <= 2100):
            continue
        places = len(dec)
        if any(round(a, places) == x or (not places and int(a) == x) for a in values):
            continue
        bad.append(m[0].strip())
    return bad


def _since(prev: dict | None, snap: dict) -> dict | None:
    """What changed between the last audit's snapshot and now (computed, handed to Claude)."""
    if not prev or not prev.get("snapshot"):
        return None
    old = {v["id"]: v for v in prev["snapshot"].get("videos", [])}
    moved = []
    for v in snap["videos"]:
        o = old.get(v["id"])
        if o:
            moved.append({"n": v["n"], "views_gained": v["views"] - (o.get("views") or 0),
                          "subscribers_gained": (v["subs"] or 0) - (o.get("subs") or 0)})
    new = [f"[[{v['n']}]]" for v in snap["videos"] if v["id"] not in old]
    ch, och = snap["channel"], prev["snapshot"].get("channel") or {}
    return {"last_audit": prev.get("made", ""), "channel_views_gained": (ch.get("views") or 0) - (och.get("views") or 0),
            "channel_subscribers_gained": (ch.get("subscribers") or 0) - (och.get("subscribers") or 0),
            "new_videos_since": new, "videos": sorted(moved, key=lambda m: -m["views_gained"])[:12],
            "last_actions": [a.get("do", a) if isinstance(a, dict) else a for a in prev.get("actions", [])][:8]}


def audits(cfg: Config) -> list[dict]:
    """The active channel's audits, newest first (a line each for the history)."""
    if not active(cfg):
        return []
    out = []
    for path in sorted(_audits_dir(cfg).glob("*.json"), reverse=True):
        a = _read(path) or {}
        out.append({"key": path.stem, "made": a.get("made", ""), "videos_seen": a.get("videos_seen"),
                    "headline": a.get("headline") or (a.get("diagnosis") or "")[:160], "model": a.get("model", ""),
                    "unverified": len(a.get("unverified") or [])})
    return out


def audit_at(cfg: Config, key: str = "") -> dict | None:
    """One audit (the newest when no key), older ones brought to today's shape."""
    d = _audits_dir(cfg)
    if key:
        if not re.fullmatch(r"[\w-]{1,64}", key):
            raise YouTubeError("No such audit")
        a = _read(d / f"{key}.json")
    else:
        paths = sorted(d.glob("*.json"))
        a = _read(paths[-1]) if paths else None
        key = paths[-1].stem if paths else ""
    if not a:
        return None
    a["key"] = key
    a["findings"] = [f if isinstance(f, dict) else {"text": f, "chart": "none", "videos": []} for f in a.get("findings", [])]
    a["actions"] = [x if isinstance(x, dict) else {"do": x, "why": "", "videos": []} for x in a.get("actions", [])]
    return a


def audit(cfg: Config, progress) -> dict:
    from typing import Literal

    from pydantic import BaseModel, Field

    from .llm import ask

    class Stage(BaseModel):
        status: Literal["good", "ok", "weak", "unknown"] = Field(description="How this step is going, from the numbers.")
        note: str = Field(description="One short plain sentence (at most 14 words, at most one figure) saying why.")

    class Stages(BaseModel):
        shown: Stage = Field(description="Is YouTube showing the videos (impressions)? 'unknown' while impressions aren't in.")
        clicked: Stage = Field(description="Do people click when shown (click rate)? 'unknown' while impressions aren't in.")
        watched: Stage = Field(description="Do viewers keep watching (% watched, still watching at 3 s and at the end)?")
        followed: Stage = Field(description="Do viewers subscribe, like and comment?")

    class Finding(BaseModel):
        title: str = Field(description="The finding in plain words, at most 10 words, no figures, e.g. 'Shorts under a "
                                       "minute keep viewers longer'.")
        level: Literal["good", "problem", "info"] = Field(description="good = keep doing it, problem = costing views, info = context.")
        text: str = Field(description="At most 2 short sentences with the figures that show it, at most 3 figures in all. "
                                      "Cite videos as [[n]]; name at most 3 videos (list the rest in `videos`).")
        chart: Literal[CHARTS] = Field(description="The chart that shows it best: length_vs_viewed (video length against % viewed), "
                                                   "views (views per video), retention (where viewers leave, for the videos you cite), "
                                                   "daily (channel views per day), ctr_vs_views (only when impressions are in), "
                                                   "subs (subscribers per video), comments (comments per video), or none. "
                                                   "Use each chart for one finding only.")
        videos: list[int] = Field(description="The row numbers of the videos this finding is about, at most 6 (listed under it "
                                              "with their numbers and highlighted in its chart).")

    class Action(BaseModel):
        do: str = Field(description="The change to make, concrete, at most 16 words. Cite videos as [[n]]. Targets are fine "
                                    "here (e.g. 'keep Shorts near 50 s'); no figures read from the data.")
        why: str = Field(description="One short sentence with the evidence, at most 2 figures. Cite videos as [[n]].")
        videos: list[int] = Field(description="Row numbers of the videos it is about.")

    class VideoNote(BaseModel):
        n: int = Field(description="The video's row number.")
        grade: Literal["good", "ok", "weak"] = Field(description="How this video did against the channel's others.")
        verdict: str = Field(description="At most 12 words: what its numbers say.")
        fix: str = Field(description="At most 14 words: the one change most likely to help it or the next one like it.")

    class Audit(BaseModel):
        headline: str = Field(description="One sentence, at most 22 words, no figures: the channel's bottleneck right now.")
        stages: Stages
        diagnosis: str = Field(description="3-5 short sentences: why the channel isn't getting more views, from these numbers only.")
        since_last: str = Field(description="When a last audit is given: 1-2 short sentences on what changed since and whether "
                                            "its actions show in the numbers. Else empty.")
        findings: list[Finding] = Field(description="4-6 patterns, most important first.")
        actions: list[Action] = Field(description="4-7 actions, most important first.")
        videos: list[VideoNote] = Field(description="Every video in the table, by row number.")

    stopper.set_checks(getattr(progress, "should_pause", None))
    data = refresh(cfg, progress)
    if not data["videos"]:
        raise YouTubeError("Your channel has no videos to audit yet")
    progress("Reading where viewers leave in each video")
    retention: dict[str, dict] = {}
    for v in sorted([v for v in data["videos"] if v.get("privacy") == "public" and v.get("views")],
                    key=lambda v: -v["views"])[:RETENTION_FOR]:
        r = _retention(cfg, v)
        if r:
            retention[v["id"]] = r
    snap = snapshot(cfg, data, retention)
    fx = facts(snap)
    prev = audit_at(cfg)
    since = _since(prev, snap)
    made = {}
    for rep_path in cfg.output_dir.glob("*/report.json"):
        rep = _read(rep_path, {}) or {}
        yt = rep.get("youtube") or {}
        if yt.get("id"):
            made[yt["id"]] = rep
    ch = snap["channel"]
    progress(f"Claude is reading the numbers of {len(snap['videos'])} videos")
    system = (
        "You audit a small YouTube channel from its own analytics, like an honest growth consultant writing for the "
        "channel's owner, who is not an analyst. How YouTube works: impressions = how often YouTube showed the thumbnail; "
        "CTR = how many of those clicked (title and thumbnail); average percentage viewed = how well a video holds (the "
        "hook and pacing); for Shorts, 'still watching at 3 s' shows how many swiped away at the start; a video that "
        "gets few impressions isn't being recommended yet, usually because early viewers didn't watch long or click.\n"
        "Rules:\n- Cite every video as [[n]], its row number in the table, never by its id or full title (the page shows "
        "the title and thumbnail for you).\n- Use only figures that are in the table, the facts or the changes given, "
        "written as given (rounding to whole numbers is fine). Never count, add up, average or compare rows yourself: "
        "the facts already did the counting. Never state a benchmark or a figure about YouTube in general.\n- When "
        "impressions and CTR aren't in yet, say so once and judge from what is there.\n- Say plainly which part is the "
        "bottleneck (being shown, being clicked, being watched, being followed), then what to change.\n- Write for "
        "someone who reads it on a phone: short, simple sentences, everyday words ('click rate', not 'CTR'; 'how much "
        "of the video people watch', not 'retention'), at most 2-3 figures in a sentence, no lists of figures. Each "
        "finding names one pattern in its title and picks the chart that shows it.")
    prompt = (f"Channel: {ch.get('title')} · {ch.get('subscribers')} subscribers · {ch.get('views')} views · {ch.get('videos')} videos\n"
              f"{snap.get('reach_note', '')}\n\nFacts worked out from the table (use these, don't recount):\n"
              f"{json.dumps(fx, ensure_ascii=False, indent=1)}\n\n"
              + (f"Since the last audit (worked out from its numbers):\n{json.dumps(since, ensure_ascii=False, indent=1)}\n\n" if since else "")
              + f"Videos (row number, newest first):\n{audit_table(snap, made)}")
    result = ask(cfg.ai_backend, cfg.claude_model, system, prompt, Audit, effort=cfg.claude_effort)
    values = _values(snap, fx, since)

    def problems(a) -> list[dict]:
        found = []
        texts = [("headline", a.headline), ("diagnosis", a.diagnosis), ("since the last audit", a.since_last)]
        texts += [(f"step '{k}'", getattr(a.stages, k).note) for k in ("shown", "clicked", "watched", "followed")]
        texts += [(f"finding {i}", f.text) for i, f in enumerate(a.findings, 1)]
        texts += [(f"finding {i} (title)", f.title) for i, f in enumerate(a.findings, 1)]
        texts += [(f"action {i} (why)", x.why) for i, x in enumerate(a.actions, 1)]
        texts += [(f"video [[{x.n}]]", x.verdict) for x in a.videos]
        for where, text in texts:
            for fig in check_figures(text, values):
                found.append({"where": where, "figure": fig, "text": text})
        return found

    found = problems(result)
    if found:
        progress(f"Checking {len(found)} figure{'s' if len(found) > 1 else ''} Claude wrote that aren't in the data")
        fix = ("Your audit states figures that are not in the table, the facts or the changes:\n"
               + "\n".join(f"- {p['where']}: {p['figure']} in \"{p['text']}\"" for p in found)
               + "\nCorrect each from the data, or say it without the figure. Keep everything else as it was.\n\n"
               + f"Your audit:\n{result.model_dump_json(indent=1)}")
        result = ask(cfg.ai_backend, cfg.claude_model, system, prompt + "\n\n" + fix, Audit, effort=cfg.claude_effort)
        found = problems(result)
    rows = len(snap["videos"])
    out = result.model_dump()
    if not fx["impressions_available"]:  # nobody can judge being shown or clicked before the impressions report
        for k in ("shown", "clicked"):
            out["stages"][k] = {"status": "unknown", "note": "YouTube's impressions report isn't in yet."}
    for f in out["findings"]:
        f["videos"] = [n for n in f["videos"] if 1 <= n <= rows]
    for x in out["actions"]:
        x["videos"] = [n for n in x["videos"] if 1 <= n <= rows]
    out["videos"] = [x for x in out["videos"] if 1 <= x["n"] <= rows]
    out = {"made": datetime.now().isoformat(timespec="seconds"), "videos_seen": rows,
           "model": f"{cfg.claude_model} {cfg.claude_effort}".strip(), **out, "facts": fx, "since": since,
           "unverified": found, "refs": {str(v["n"]): v["id"] for v in snap["videos"]}, "snapshot": snap}
    stem, k = re.sub(r"[^\w-]", "-", out["made"]), 2
    path = _audits_dir(cfg) / f"{stem}.json"
    while path.exists():  # two audits in the same second keep both; '_02' sorts after the first ('-2' sorted before it)
        path, k = _audits_dir(cfg) / f"{stem}_{k:02d}.json", k + 1
    _write(path, out)
    _write(home(cfg) / "audit.json", out)
    progress("The audit is ready (YouTube tab)" + (f": {len(found)} figure{'s' if len(found) > 1 else ''} couldn't be "
                                                   "found in the data and are marked" if found else ""))
    return out
