"""History of generation runs (manual, automation and resume), with Claude token usage.

Each finished job is appended to <output>/run_history.json: when it ran, what started it,
how many videos it made, and the tokens every video and every step used.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from .config import Config
from .llm import summarize_usage

KEEP = 1000
_lock = threading.Lock()


def _path(cfg: Config) -> Path:
    return cfg.output_dir / "run_history.json"


def load(cfg: Config) -> list[dict]:
    path = _path(cfg)
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def record_job(cfg: Config, job: dict) -> dict:
    """Save a finished job. Tokens are grouped per video and per step."""
    usage = job.get("usage", [])
    per_video: dict[int, list] = {}
    for rec in usage:
        per_video.setdefault(rec.get("video", 1), []).append(rec)
    done = {v["video"]: v for v in job.get("videos", [])}
    videos = []
    for n in sorted(set(per_video) | set(done)):
        summary = summarize_usage(per_video.get(n, []))
        videos.append({"n": n, "id": done.get(n, {}).get("id"), "title": done.get(n, {}).get("title", ""),
                       "made": n in done, "verified": done.get(n, {}).get("verified"),
                       "tokens": summary["total"]["tokens"], "cost_usd": summary["total"]["cost_usd"],
                       "steps": {k: v["tokens"] for k, v in summary["steps"].items()}})
    entry = {
        "id": job["id"], "trigger": job.get("trigger", "manual"), "style": job.get("style"), "length": job.get("length", "short"),
        "topic": job.get("topic"), "count": job.get("count"), "status": job.get("status"),
        "made": len(job.get("results", [])), "created": job.get("created"), "finished": job.get("finished"),
        "usage": summarize_usage(usage), "videos": videos,
    }
    with _lock:
        runs = [r for r in load(cfg) if r.get("id") != job["id"]] + [entry]
        path = _path(cfg)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(runs[-KEEP:], ensure_ascii=False), encoding="utf-8")
    return entry


def history(cfg: Config) -> dict:
    """Runs newest first, plus totals for each automation."""
    runs = sorted(load(cfg), key=lambda r: r.get("created") or 0, reverse=True)
    autos: dict[str, dict] = {}
    for r in runs:
        trigger = r.get("trigger") or "manual"
        if not trigger.startswith("automation: "):
            continue
        a = autos.setdefault(trigger[len("automation: "):], {"runs": 0, "videos": 0, "tokens": 0, "cost_usd": 0.0,
                                                             "last_run": r.get("created")})
        a["runs"] += 1
        a["videos"] += r.get("made", 0)
        a["tokens"] += r["usage"]["total"]["tokens"]
        a["cost_usd"] = round(a["cost_usd"] + (r["usage"]["total"]["cost_usd"] or 0), 4)
    total_tokens = sum(r["usage"]["total"]["tokens"] for r in runs)
    return {"runs": runs, "automations": [{"name": k, **v} for k, v in autos.items()],
            "total": {"runs": len(runs), "videos": sum(r.get("made", 0) for r in runs), "tokens": total_tokens,
                      "cost_usd": round(sum(r["usage"]["total"]["cost_usd"] or 0 for r in runs), 4)}}
