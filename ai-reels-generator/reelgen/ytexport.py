"""Everything about a channel in files another AI (or a person) can read (the user: "provide to download each data
including graph lines, diagram, video name, details and things, so i can give to AI to analyse my video").

- `markdown`: one file with every number: the channel, what each number means, views per day, and for every video its
  name, link, numbers, how many are still watching through it (every 5% of its length), where its viewers came from,
  how the app made it, its tags and description; then the latest audit with names instead of row numbers, and the
  earlier audits' verdicts.
- `zip_bytes`: that file plus the same data as CSV and JSON, every audit, and chart pictures drawn with Pillow (light
  background; categorical slots validated for a white surface; the two lighter ones always carry direct labels).
"""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from datetime import datetime, timedelta

from . import youtube as Y
from .config import Config

SHORT, LONG = "#2a78d6", "#eb6834"
LINES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
INK, MUTED, GRID, PAPER = "#1b1b1f", "#5c5c66", "#e6e6ea", "#ffffff"
FRESH = timedelta(hours=24)


# ---------- gathering ----------

def _made_by_app(cfg: Config) -> dict[str, dict]:
    out = {}
    for rep_path in cfg.output_dir.glob("*/report.json"):
        rep = Y._read(rep_path, {}) or {}
        yid = (rep.get("youtube") or {}).get("id")
        if yid:
            out[yid] = {k: rep[k] for k in ("source", "length", "style", "hook_template", "voice", "captions", "category",
                                            "visual_template", "music") if rep.get(k)}
    return out


def _details(cfg: Config, vid: str) -> dict | None:
    path = Y.home(cfg) / "details" / (re.sub(r"[^\w-]", "_", vid) + ".json")
    got = Y._read(path)
    if got and got.get("fetched_at", "") >= (datetime.now() - FRESH).isoformat(timespec="seconds"):
        return got
    try:
        return Y.details(cfg, vid)
    except Y.YouTubeError:
        return got  # an older copy beats nothing


def gather(cfg: Config) -> dict:
    """The active channel's numbers (as last refreshed), every public video's retention and traffic sources (read
    again when older than a day) and its audits."""
    data = Y.cached(cfg)
    if not data:
        data = Y.refresh(cfg)
    made = _made_by_app(cfg)
    videos = []
    for v in sorted(data.get("videos", []), key=lambda r: -(r.get("views") or 0)):
        row = {**v, "made_by_app": made.get(v["id"], {})}
        if v.get("privacy") == "public" and v.get("views"):
            d = _details(cfg, v["id"]) or {}
            row["retention"] = [{"at": r["at"], "second": round(r["at"] * (v.get("duration") or 0), 1),
                                 "watching": Y._num(r.get("watching")), "vs_similar": Y._num(r.get("vs_similar"))}
                                for r in d.get("retention") or []]
            row["sources"] = d.get("sources") or []
            summary = Y._retention(cfg, v)
            if summary:
                row["retention_summary"] = {k: summary.get(k) for k in ("at_3s", "half_gone_at", "at_end", "at_10s", "kept_5_to_10")}
        if v.get("short"):  # of all the times it started to play, how many stayed past the first seconds
            st = v.get("stats") or {}
            row["stayed"], row["stayed_estimated"] = Y.stayed(st.get("views"), st.get("engagedViews"),
                                                             st.get("estimatedMinutesWatched"), st.get("averageViewDuration"))
        videos.append(row)
    audits = []
    for item in Y.audits(cfg):
        a = Y.audit_at(cfg, item["key"])
        if a:
            audits.append(a)
    return {"exported_at": datetime.now().isoformat(timespec="seconds"), "fetched_at": data.get("fetched_at", ""),
            "channel": data.get("channel") or {}, "reach_note": data.get("reach_note", ""), "daily": data.get("daily") or [],
            "videos": videos, "audits": audits}


# ---------- one readable file ----------

def _fmt(x, digits: int = 1) -> str:
    if x is None or x == "":
        return "–"
    if isinstance(x, bool):
        return "yes" if x else "no"
    if isinstance(x, float):
        return f"{x:,.{digits}f}".rstrip("0").rstrip(".") if digits else f"{x:,.0f}"
    return f"{x:,}" if isinstance(x, int) else str(x)


def _names(a: dict) -> dict[str, str]:
    """Row number → title in an audit (each audit numbered the videos it saw)."""
    snap = a.get("snapshot") or {}
    return {str(v["n"]): v["title"] for v in snap.get("videos", [])}


def _resolved(text: str, names: dict[str, str]) -> str:
    return Y.REF.sub(lambda m: f"“{names.get(m[1], 'video ' + m[1])}”", text or "")


def _table(head: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(str(c).replace("|", "/").replace("\n", " ") for c in r) + " |" for r in rows]
    return "\n".join(out)


def markdown(b: dict) -> str:
    ch = b["channel"]
    out = [f"# YouTube channel data: {ch.get('title', '')}",
           f"Exported {b['exported_at'][:16].replace('T', ' ')} from Reel Studio. Numbers from YouTube's Data and Analytics "
           f"APIs as of {b['fetched_at'][:16].replace('T', ' ')} (YouTube's analytics lag 2-3 days).", "",
           "## What the numbers mean",
           "- **Views**: times the video was watched; for a Short, every time it started to play in the feed, swiped "
           "away or not. **Average viewed %**: how much of the video a typical view lasted (Shorts can pass 100% when "
           "people rewatch).",
           "- **Stayed past the first seconds** (Shorts): of all those starts, how many kept watching instead of "
           "swiping away. Marked (estimate) when worked out from the watch time (minutes watched x 60 / average view "
           "seconds / views), exact when YouTube's own engaged views are in.",
           "- **Still watching**: the share of viewers still watching at that moment of the video. For a Short it is "
           "among the viewers who stayed past the first seconds, so it starts near or above 100% (over 100% = some "
           "watched that part again). **Kept from second 5 to second 10**: of the viewers still there at second 5, how "
           "many are still there at second 10. **vs similar videos**: YouTube's own comparison with videos of the "
           "same length (0.5 = typical, higher = better).",
           "- **Impressions**: how often YouTube showed the thumbnail. **Click rate (CTR)**: how many of those clicked.",
           f"- {b['reach_note'] or ''}", "",
           "## Channel",
           _table(["Channel", "Handle", "Subscribers", "Views", "Videos", "Started", "Channel ID"],
                  [[ch.get("title", ""), ch.get("handle", ""), _fmt(ch.get("subscribers")), _fmt(ch.get("views")),
                    _fmt(ch.get("videos")), (ch.get("published") or "")[:10], ch.get("id", "")]]), ""]
    latest = b["audits"][0] if b["audits"] else None
    if latest and latest.get("facts"):
        out += ["## Channel facts (worked out by the app from the videos)"]
        names = _names(latest)
        for k, v in latest["facts"].items():
            if k == "same_title_uploaded_more_than_once":  # lists of [[n]] (privacy): the titles instead
                v = [", ".join(_resolved(x, names) for x in group) for group in v]
            text = json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else _fmt(v, 2)
            out.append(f"- {k.replace('_', ' ')}: {_resolved(text, names)}")
        out.append("")
    if b["daily"]:
        out += [f"## Views per day (last {len(b['daily'])} days)",
                _table(["Date", "Views", "New subscribers", "Minutes watched"],
                       [[d["day"], d["views"], d["subs"], _fmt(d.get("minutes"))] for d in b["daily"]]), ""]
    out += [f"## Videos ({len(b['videos'])}, most viewed first)", ""]
    for i, v in enumerate(b["videos"], 1):
        st, rc, rs = v.get("stats") or {}, v.get("reach") or {}, v.get("retention_summary") or {}
        out += [f"### {i}. {v['title']}",
                f"- Link: https://youtu.be/{v['id']} · published {v.get('published', '')[:10]} · "
                f"{'Short' if v.get('short') else 'long video'} · {_fmt(v.get('duration'), 0)} s · {v.get('privacy', '')}"
                + (f" · scheduled for {v['publish_at']}" if v.get("publish_at") else ""),
                f"- Views {_fmt(v.get('views'))} · likes {_fmt(v.get('likes'))} · comments {_fmt(v.get('comments'))} · "
                f"shares {_fmt(Y._num(st.get('shares')), 0)} · subscribers gained {_fmt(Y._num(st.get('subscribersGained')), 0)} · "
                f"minutes watched {_fmt(Y._num(st.get('estimatedMinutesWatched')))}",
                f"- Average viewed: {_fmt(Y._num(st.get('averageViewPercentage')), 2)}% "
                f"({_fmt(Y._num(st.get('averageViewDuration')), 0)} s of {_fmt(v.get('duration'), 0)} s)",
                f"- Impressions {_fmt(rc.get('impressions'))} · click rate "
                f"{'–' if rc.get('ctr') is None else _fmt(rc['ctr'] * 100, 2) + '%'}"]
        if rs:
            half = (f"half the viewers gone by {_fmt(rs['half_gone_at'], 0)} s" if rs.get("half_gone_at") is not None
                    else "more than half still watching at the end")
            out.append(f"- Still watching at 3 s: {_fmt(rs.get('at_3s'))}% · {half} · still watching at the end: {_fmt(rs.get('at_end'))}%")
            if rs.get("at_10s") is not None:
                out.append(f"- Still watching at 10 s: {_fmt(rs['at_10s'])}% · kept from second 5 to second 10: {_fmt(rs.get('kept_5_to_10'))}%")
        if v.get("stayed") is not None:
            out.append(f"- Stayed past the first seconds (did not swipe away): {_fmt(v['stayed'])}%"
                       + (" (estimate)" if v.get("stayed_estimated") else ""))
        ret = v.get("retention") or []
        if ret:
            picks = [r for r in ret if round(r["at"] * 100) % 5 == 0] or ret
            out += ["", "Still watching through the video (every 5% of its length):",
                    _table(["% of video", "Second", "Still watching", "vs similar videos"],
                           [[f"{round(r['at'] * 100)}%", _fmt(r["second"], 1), f"{_fmt(r['watching'] * 100 if r['watching'] is not None else None)}%",
                             _fmt(r["vs_similar"], 2)] for r in picks])]
        if v.get("sources"):
            out += ["", "Where viewers came from: " + ", ".join(
                f"{str(s['source']).replace('_', ' ').lower()} {_fmt(Y._num(s.get('views')), 0)} views" for s in v["sources"])]
        if v.get("made_by_app"):
            out.append("- Made by Reel Studio: " + ", ".join(f"{k} = {val}" for k, val in v["made_by_app"].items()))
        if v.get("tags"):
            out.append("- Tags: " + ", ".join(v["tags"]))
        if v.get("description"):
            out += ["- Description:", "", "> " + v["description"][:1500].replace("\n", "\n> ")]
        out.append("")
    if latest:
        names = _names(latest)
        out += [f"## Latest audit by Claude ({latest.get('made', '')[:16].replace('T', ' ')})", "",
                f"**{_resolved(latest.get('headline', ''), names)}**", "", _resolved(latest.get("diagnosis", ""), names), ""]
        for k, label in (("shown", "Shown"), ("clicked", "Clicked"), ("watched", "Watched"), ("followed", "Followed")):
            s = (latest.get("stages") or {}).get(k)
            if s:
                out.append(f"- {label}: {s.get('status')} – {_resolved(s.get('note', ''), names)}")
        out += ["", "### What the numbers show"]
        for f in latest.get("findings", []):
            out.append(f"- **{_resolved(f.get('title') or '', names)}** {_resolved(f.get('text', ''), names)}")
        out += ["", "### What to change"]
        for i, x in enumerate(latest.get("actions", []), 1):
            out.append(f"{i}. {_resolved(x.get('do', ''), names)}" + (f" (why: {_resolved(x['why'], names)})" if x.get("why") else ""))
        if latest.get("videos"):
            out += ["", "### Every video"]
            for x in latest["videos"]:
                title = names.get(str(x.get("n")), x.get("id", ""))
                out.append(f"- {title}: {x.get('grade', '')} – {_resolved(x.get('verdict', ''), names)} Fix: {_resolved(x.get('fix', ''), names)}")
        if len(b["audits"]) > 1:
            out += ["", "## Earlier audits"]
            for a in b["audits"][1:]:
                out.append(f"- {a.get('made', '')[:16].replace('T', ' ')}: {_resolved(a.get('headline') or a.get('diagnosis', '')[:200], _names(a))}")
    return "\n".join(out).rstrip() + "\n"


# ---------- tables ----------

def _csv(head: list[str], rows: list[list]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(head)
    w.writerows(rows)
    return buf.getvalue()


def tables(b: dict) -> dict[str, str]:
    vids = []
    for v in b["videos"]:
        st, rc, rs = v.get("stats") or {}, v.get("reach") or {}, v.get("retention_summary") or {}
        vids.append([v["id"], v["title"], v.get("published", "")[:10], "short" if v.get("short") else "long",
                     round(v.get("duration") or 0), v.get("privacy", ""), v.get("views", 0), v.get("likes", 0),
                     v.get("comments", 0), st.get("shares", ""), st.get("subscribersGained", ""), st.get("estimatedMinutesWatched", ""),
                     st.get("averageViewDuration", ""), st.get("averageViewPercentage", ""), rc.get("impressions", ""),
                     "" if rc.get("ctr") is None else round(rc["ctr"] * 100, 2), rs.get("at_3s", ""), rs.get("half_gone_at", ""),
                     rs.get("at_end", ""), "" if v.get("stayed") is None else v["stayed"],
                     "" if v.get("stayed") is None else ("yes" if v.get("stayed_estimated") else "no"),
                     "" if rs.get("at_10s") is None else rs["at_10s"], "" if rs.get("kept_5_to_10") is None else rs["kept_5_to_10"],
                     "; ".join(f"{k}={val}" for k, val in (v.get("made_by_app") or {}).items()),
                     ", ".join(v.get("tags") or []), "https://youtu.be/" + v["id"]])
    ret = [[v["id"], v["title"], r["second"], round(r["at"], 3), "" if r["watching"] is None else round(r["watching"] * 100, 2),
            "" if r["vs_similar"] is None else r["vs_similar"]] for v in b["videos"] for r in v.get("retention") or []]
    src = [[v["id"], v["title"], s.get("source", ""), s.get("views", ""), s.get("minutes", "")]
           for v in b["videos"] for s in v.get("sources") or []]
    return {
        "videos.csv": _csv(["video_id", "title", "published", "format", "duration_s", "privacy", "views", "likes", "comments",
                            "shares", "subscribers_gained", "watch_minutes", "avg_view_duration_s", "avg_percent_viewed",
                            "impressions", "ctr_percent", "still_watching_at_3s_percent", "half_gone_at_s",
                            "still_watching_at_end_percent", "stayed_past_first_seconds_percent", "stayed_is_estimate",
                            "still_watching_at_10s_percent", "kept_from_5s_to_10s_percent", "made_by_app", "tags", "url"], vids),
        "retention.csv": _csv(["video_id", "title", "second", "fraction_of_video", "percent_still_watching", "vs_similar_videos"], ret),
        "traffic_sources.csv": _csv(["video_id", "title", "source", "views", "minutes_watched"], src),
        "daily.csv": _csv(["date", "views", "new_subscribers", "minutes_watched"],
                          [[d["day"], d["views"], d["subs"], d.get("minutes", "")] for d in b["daily"]]),
    }


# ---------- chart pictures (Pillow) ----------

def _font(size: int, bold: bool = False):
    from PIL import ImageFont
    names = (["DejaVuSans-Bold.ttf", "arialbd.ttf", "segoeuib.ttf"] if bold else []) + \
            ["DejaVuSans.ttf", "Nirmala.ttc", "arial.ttf", "segoeui.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
             "C:/Windows/Fonts/Nirmala.ttc", "C:/Windows/Fonts/arial.ttf"]
    for n in names:
        try:
            return ImageFont.truetype(n, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _short(t: str, n: int = 34) -> str:
    t = re.sub(r"\s*#\w+", "", t or "").split(" | ")[0]
    t = re.sub(r"[^\w\s,.!?'’:;()&%+-]", "", t).strip()  # emoji the fonts can't draw
    return t if len(t) <= n else t[:n - 1].rstrip() + "…"


def _nice(v: float) -> float:
    import math
    if v <= 0:
        return 1
    p = 10 ** math.floor(math.log10(v))
    return next(m * p for m in (1, 2, 2.5, 5, 10) if m * p >= v)


class _Chart:
    def __init__(self, w: int, h: int, title: str, sub: str = ""):
        from PIL import Image, ImageDraw
        self.img = Image.new("RGB", (w, h), PAPER)
        self.d = ImageDraw.Draw(self.img)
        self.w, self.h = w, h
        self.d.text((24, 18), title, fill=INK, font=_font(22, True))
        if sub:
            self.d.text((24, 48), sub, fill=MUTED, font=_font(14))

    def legend(self, items: list[tuple[str, str, str]], y: int) -> None:
        x = 24
        for kind, color, name in items:
            if kind == "line":
                self.d.line((x, y + 8, x + 18, y + 8), fill=color, width=3)
                x += 24
            else:
                self.d.ellipse((x, y + 2, x + 12, y + 14), fill=color)
                x += 18
            self.d.text((x, y), name, fill=MUTED, font=_font(14))
            x += int(self.d.textlength(name, font=_font(14))) + 18

    def png(self) -> bytes:
        buf = io.BytesIO()
        self.img.save(buf, "PNG", optimize=True)
        return buf.getvalue()


def chart_length(b: dict) -> bytes | None:
    import math
    pts = [v for v in b["videos"] if v.get("views") and (v.get("stats") or {}).get("averageViewPercentage") is not None and v.get("duration")]
    if len(pts) < 2:
        return None
    c = _Chart(1400, 800, "How much of each video people watch, by its length", "Dot size = views. Labels: the most viewed.")
    c.legend([("dot", SHORT, "Shorts"), ("dot", LONG, "Long videos")], 74)
    L, R, T, B = 90, 40, 120, 70
    durs = [v["duration"] for v in pts]
    x0, x1 = math.log10(max(5, min(durs) * 0.8)), math.log10(max(durs) * 1.25)
    ys = [float(v["stats"]["averageViewPercentage"]) for v in pts]
    ymax = max(100.0, _nice(max(ys)))
    sx = lambda d: L + (math.log10(d) - x0) / (x1 - x0) * (c.w - L - R)
    sy = lambda p: T + (1 - p / ymax) * (c.h - T - B)
    f = _font(14)
    for k in range(5):
        p = ymax * k / 4
        c.d.line((L, sy(p), c.w - R, sy(p)), fill=GRID, width=1)
        c.d.text((L - 10, sy(p)), f"{p:.0f}%", fill=MUTED, font=f, anchor="rm")
    last = -1e9
    for t in (10, 15, 30, 45, 60, 90, 120, 180, 300, 600, 900, 1200, 1800):
        if x0 <= math.log10(t) <= x1 and sx(t) - last > 50:
            last = sx(t)
            c.d.text((sx(t), c.h - B + 18), f"{t // 60}m" if t >= 60 and t % 60 == 0 else (f"{t // 60}m{t % 60:02d}" if t > 60 else f"{t}s"),
                     fill=MUTED, font=f, anchor="mm")
    c.d.text((c.w / 2, c.h - 22), "video length", fill=MUTED, font=f, anchor="mm")
    top = max(v["views"] for v in pts)
    labelled = {v["id"] for v in sorted(pts, key=lambda v: -v["views"])[:6]}
    boxes: list[tuple] = []  # every dot, then every label drawn: a label never covers either
    for v in pts:
        r = 6 + 16 * math.sqrt(v["views"] / top)
        x, y = sx(v["duration"]), sy(float(v["stats"]["averageViewPercentage"]))
        boxes.append((x - r, y - r, x + r, y + r, v["id"]))
    for v in sorted(pts, key=lambda v: -v["views"]):
        r = 6 + 16 * math.sqrt(v["views"] / top)
        x, y = sx(v["duration"]), sy(float(v["stats"]["averageViewPercentage"]))
        c.d.ellipse((x - r, y - r, x + r, y + r), fill=SHORT if v.get("short") else LONG, outline=PAPER, width=2)
        if v["id"] in labelled:
            text = _short(v["title"], 30)
            w = c.d.textlength(text, font=f)
            for lx, anchor in ((x + r + 6, "lm"), (x - r - 6, "rm")):
                box = (lx if anchor == "lm" else lx - w, y - 9, lx + w if anchor == "lm" else lx, y + 9, v["id"])
                if box[0] > 0 and box[2] < c.w and not any(o[4] != v["id"] and not (box[2] < o[0] or box[0] > o[2] or box[3] < o[1] or box[1] > o[3])
                                                           for o in boxes):
                    boxes.append(box[:4] + ("",))
                    c.d.text((lx, y), text, fill=INK, font=f, anchor=anchor)
                    break
    return c.png()


def chart_views(b: dict) -> bytes | None:
    rows = [v for v in b["videos"] if v.get("privacy") == "public"][:20]
    if not rows:
        return None
    bar, gap, lab = 22, 12, 420
    c = _Chart(1400, 130 + len(rows) * (bar + gap) + 30, "Views per video", "Public videos, most viewed first")
    c.legend([("dot", SHORT, "Shorts"), ("dot", LONG, "Long videos")], 74)
    top = max(v["views"] for v in rows) or 1
    f = _font(14)
    for i, v in enumerate(rows):
        y = 120 + i * (bar + gap)
        w = max(3, (v["views"] / top) * (c.w - lab - 140))
        c.d.text((lab - 12, y + bar / 2), _short(v["title"], 44), fill=INK, font=f, anchor="rm")
        c.d.rounded_rectangle((lab, y, lab + w, y + bar), radius=4, fill=SHORT if v.get("short") else LONG)
        c.d.text((lab + w + 8, y + bar / 2), f"{v['views']:,}", fill=INK, font=f, anchor="lm")
    return c.png()


def chart_daily(b: dict) -> bytes | None:
    days = b["daily"]
    if len(days) < 3:
        return None
    c = _Chart(1400, 600, f"Views per day on the channel, last {len(days)} days", "▲ = a video was published that day")
    L, R, T, B = 80, 40, 100, 80
    top = _nice(max(d["views"] for d in days))
    sx = lambda i: L + i / (len(days) - 1) * (c.w - L - R)
    sy = lambda v: T + (1 - v / top) * (c.h - T - B)
    f = _font(14)
    for k in range(5):
        v = top * k / 4
        c.d.line((L, sy(v), c.w - R, sy(v)), fill=GRID, width=1)
        c.d.text((L - 10, sy(v)), f"{v:,.0f}", fill=MUTED, font=f, anchor="rm")
    pts = [(sx(i), sy(d["views"])) for i, d in enumerate(days)]
    c.d.polygon(pts + [(pts[-1][0], sy(0)), (pts[0][0], sy(0))], fill="#e3eefb")
    c.d.line(pts, fill=SHORT, width=3, joint="curve")
    for i in (0, len(days) // 3, 2 * len(days) // 3, len(days) - 1):
        c.d.text((sx(i), c.h - B + 18), days[i]["day"][5:], fill=MUTED, font=f, anchor="mm")
    index = {d["day"]: i for i, d in enumerate(days)}
    for v in b["videos"]:
        i = index.get((v.get("published") or "")[:10])
        if i is not None:
            x = sx(i)
            c.d.polygon([(x, c.h - B + 2), (x - 6, c.h - B + 12), (x + 6, c.h - B + 12)], fill=MUTED)
    return c.png()


def _retention_axes(c, box, curve_sets, dur, labels=True, small=False):
    L, T, W, H = box
    f = _font(12 if small else 14)
    top = max(100.0, max((p for _n, pts, _c in curve_sets for _s, p in pts), default=100))
    top = 25 * -(-top // 25)
    sx = lambda s: L + (s / dur) * W
    sy = lambda p: T + (1 - max(0.0, min(p, top)) / top) * H
    for k in range(0, int(top) + 1, 50 if small else 25):
        c.d.line((L, sy(k), L + W, sy(k)), fill=GRID, width=1)
        c.d.text((L - 6, sy(k)), f"{k}%", fill=MUTED, font=f, anchor="rm")
    for frac in (0, 0.5, 1):
        c.d.text((sx(dur * frac), T + H + 14), f"{dur * frac:.0f}s", fill=MUTED, font=f, anchor="mm")
    for name, pts, color in curve_sets:
        if len(pts) > 1:
            c.d.line([(sx(s), sy(p)) for s, p in pts], fill=color, width=2 if small else 3, joint="curve")
            if labels and not small:
                s, p = pts[-1]
                c.d.text((sx(s) + 8, sy(p)), name, fill=INK, font=f, anchor="lm")


def chart_retention_top(b: dict) -> bytes | None:
    vids = [v for v in b["videos"] if v.get("retention")][:4]
    if not vids:
        return None
    c = _Chart(1400, 700, "How many viewers are still watching, second by second",
               "The 4 most viewed videos. Over 100% = part of the audience watched that moment again.")
    c.legend([("line", LINES[i], _short(v["title"], 30)) for i, v in enumerate(vids)], 74)
    dur = max(v.get("duration") or 1 for v in vids)
    sets = [(_short(v["title"], 22), [(r["second"], (r["watching"] or 0) * 100) for r in v["retention"]], LINES[i]) for i, v in enumerate(vids)]
    _retention_axes(c, (90, 130, 1400 - 90 - 280, 700 - 130 - 70), sets, dur)
    return c.png()


def chart_retention_all(b: dict) -> bytes | None:
    vids = [v for v in b["videos"] if v.get("retention")]
    if not vids:
        return None
    cols, cw, chh = 3, 460, 260
    rows = -(-len(vids) // cols)
    c = _Chart(cols * cw + 20, 90 + rows * chh, "Still watching through every video",
               "One small chart per video, its own length on the axis")
    for i, v in enumerate(vids):
        x, y = 10 + (i % cols) * cw, 90 + (i // cols) * chh
        c.d.text((x + 50, y + 8), _short(v["title"], 40), fill=INK, font=_font(14, True))
        rs = v.get("retention_summary") or {}
        half = f"half gone by {rs['half_gone_at']}s" if rs.get("half_gone_at") is not None else "over half watch to the end"
        c.d.text((x + 50, y + 28), f"{v['views']:,} views · {v.get('duration', 0):.0f}s · {half}",
                 fill=MUTED, font=_font(12))
        _retention_axes(c, (x + 50, y + 52, cw - 80, chh - 90),
                        [("", [(r["second"], (r["watching"] or 0) * 100) for r in v["retention"]], SHORT if v.get("short") else LONG)],
                        max(v.get("duration") or 1, 1), labels=False, small=True)
    return c.png()


CHARTS = {"length_vs_watched.png": chart_length, "views_per_video.png": chart_views, "views_per_day.png": chart_daily,
          "still_watching_top4.png": chart_retention_top, "still_watching_every_video.png": chart_retention_all}


def zip_bytes(b: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("channel-for-ai.md", markdown(b))
        for name, text in tables(b).items():
            z.writestr(name, text)
        z.writestr("data.json", json.dumps({k: v for k, v in b.items() if k != "audits"}, indent=1, ensure_ascii=False))
        for a in b["audits"]:
            z.writestr(f"audits/{a.get('key', a.get('made', 'audit'))}.json", json.dumps(a, indent=1, ensure_ascii=False))
        drawn = []
        for name, draw in CHARTS.items():
            try:
                png = draw(b)
            except Exception:  # a chart that can't be drawn never stops the download
                png = None
            if png:
                z.writestr(f"charts/{name}", png)
                drawn.append(name)
        z.writestr("README.txt", "\n".join([
            f"YouTube channel data: {b['channel'].get('title', '')}, exported {b['exported_at'][:16]} from Reel Studio.",
            "", "channel-for-ai.md      everything in one readable file: give this to an AI first",
            "videos.csv             one row per video, every number", "retention.csv          still watching, second by second, every public video",
            "traffic_sources.csv    where each video's viewers came from", "daily.csv              channel views per day",
            "data.json              all of the above as raw data", "audits/                every audit Claude made, with the numbers it saw",
            *[f"charts/{n}" for n in drawn]]))
    return buf.getvalue()


def file_stem(b: dict) -> str:
    slug = re.sub(r"[^\w-]+", "-", (b["channel"].get("title") or "channel").lower()).strip("-") or "channel"
    return f"{slug}-youtube-{b['exported_at'][:10]}"
