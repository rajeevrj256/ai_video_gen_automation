"""History of generation runs (manual, automation and resume), with Claude token usage.

Each finished job is appended to <output>/run_history.json: when it ran, what started it,
how many videos it made, and the tokens every video and every step used.
"""

from __future__ import annotations

import json
import re
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


# Which step a progress line starts (lower-case keywords, first match wins). The names match the
# token steps (llm.STEP_NAMES), so time and tokens can be read side by side; None ends a step.
STEP_WORDS = [
    ("Paused", ("paused",)),
    ("Script", ("writing the script", "rewriting the script", "picking the topic")),
    ("Fact-check", ("fact-checking",)),
    ("Fact fixes", ("fixing", "revising", "removing what", "trimming")),
    ("Voice", ("recording", "voiceover runs")),
    ("Footage", ("footage",)),
    ("Music", ("composing the music",)),
    ("Editing", ("editing the video",)),
    ("Checks", ("verifying video quality",)),
    ("Preview", ("previewing the edit", "reviewing the preview")),
    ("Review", ("reviewing",)),
    ("Post text", ("title, description", "writing the title")),
    (None, ("passed verification", "failed verification", "done", "error", "script rejected", "still has")),
]


def _step_of(msg: str) -> str | None | bool:
    """The step a line starts, None if it ends one, False if it says nothing about steps."""
    low = msg.lower()
    for name, words in STEP_WORDS:
        if any(w in low for w in words):
            return name
    return False


def step_times(log_lines: list[dict], video: int, end: float | None) -> tuple[float, dict[str, float]]:
    """(total seconds, seconds per step) for one video, from the job's timestamped log.
    Batch lines are tagged [V<n>]; a one-video job has no tags."""
    tagged = any(re.match(r"\[V\d+\]", e["msg"]) for e in log_lines)
    mine = [e for e in log_lines if not tagged or e["msg"].startswith(f"[V{video}]")]
    if not mine:
        return 0.0, {}
    times: dict[str, float] = {}
    current, since = None, mine[0]["t"]
    for e in mine:
        step = _step_of(e["msg"])
        if step is False:
            continue
        if current:
            times[current] = times.get(current, 0.0) + (e["t"] - since)
        current, since = step, e["t"]
    last = end if end and (not tagged or current) else mine[-1]["t"]
    if current:
        times[current] = times.get(current, 0.0) + max(0.0, last - since)
    total = max(last, mine[-1]["t"]) - mine[0]["t"]
    return round(total, 1), {k: round(v, 1) for k, v in times.items() if v >= 0.5}


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
        seconds, times = step_times(job.get("log", []), n, job.get("finished"))
        videos.append({"n": n, "id": done.get(n, {}).get("id"), "title": done.get(n, {}).get("title", ""),
                       "made": n in done, "verified": done.get(n, {}).get("verified"),
                       "tokens": summary["total"]["tokens"], "cost_usd": summary["total"]["cost_usd"],
                       "steps": {k: v["tokens"] for k, v in summary["steps"].items()},
                       "seconds": seconds, "times": times})
    entry = {
        "id": job["id"], "trigger": job.get("trigger", "manual"), "style": job.get("style"), "length": job.get("length", "short"),
        "topic": job.get("topic"), "count": job.get("count"), "status": job.get("status"),
        "made": len(job.get("results", [])), "created": job.get("created"), "finished": job.get("finished"),
        "usage": summarize_usage(usage), "videos": videos,
        "times": {k: round(sum(v["times"].get(k, 0) for v in videos), 1) for k in {k for v in videos for k in v["times"]}},
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
