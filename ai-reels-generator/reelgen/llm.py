"""One interface, two ways to reach Claude.

- "claude-code": runs the Claude Code CLI you're already logged in to
  (`claude -p ...`). No API key needed, and Claude can use web search to
  check facts about a trend before it writes.
- "api": the Anthropic API with ANTHROPIC_API_KEY (used on GitHub Actions).

"auto" (the default) picks claude-code when the `claude` command is installed.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from . import stopper

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


INSTALL_HELP = (
    "Claude Code was not found on this computer, and no ANTHROPIC_API_KEY is set. "
    "Install Claude Code (Windows PowerShell: irm https://claude.ai/install.ps1 | iex; "
    "Mac/Linux: curl -fsSL https://claude.ai/install.sh | bash), open a NEW terminal, run `claude` "
    "once to log in, then restart Reel Studio. (The Claude desktop chat app can't be used by other programs.)"
)


def find_claude() -> str | None:
    """The Claude Code CLI: on PATH, or in the installer's folder when PATH hasn't been
    refreshed yet (common right after installing on Windows)."""
    found = shutil.which("claude")
    if found:
        return found
    home = Path.home()
    for candidate in (home / ".local" / "bin" / "claude.exe", home / ".local" / "bin" / "claude",
                      home / "AppData" / "Roaming" / "npm" / "claude.cmd"):
        if candidate.exists():
            return str(candidate)
    return None


def describe_backend(backend: str) -> str:
    """Like resolve_backend, but "missing" instead of raising (for status displays)."""
    try:
        return resolve_backend(backend)
    except LLMError:
        return "missing"


def resolve_backend(backend: str) -> str:
    if backend in ("claude-code", "api"):
        return backend
    if find_claude():
        return "claude-code"
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return "api"
    raise LLMError(INSTALL_HELP)


# ---- Usage limits: pause until the limit resets, then retry the same step. ----
# Claude Code reports e.g. "You've hit your session limit · resets 10:30pm (UTC)". Every
# video thread waits for the same reset, so a batch picks up exactly where it stopped.
LIMIT_RE = re.compile(r"hit your .{0,20}limit|(usage|session|weekly) limit|limit reached|rate.limit", re.I)
LIMIT_BUFFER = 120  # seconds after the reset, so the first call isn't too early
_limit_until = 0.0
_limit_lock = threading.Lock()
_reporter = threading.local()


# ---- Token metering: every Claude call is recorded against the current video ----
# pipeline.py starts a meter per video thread; each call adds one record (the step, tokens
# in/out/cached and the API-equivalent cost that Claude Code reports).

STEP_NAMES = {"ReelScript": "Script", "LongScript": "Script", "FactCheck": "Fact-check", "ScriptFixes": "Fact fixes",
              "Review": "Review", "PostCopy": "Post text"}
_meter = threading.local()


def start_meter(on_record=None, earlier: list[dict] | None = None) -> list[dict]:
    """Start counting this thread's Claude usage (continuing `earlier` records on a resume)."""
    _meter.records = list(earlier or [])
    _meter.fn = on_record
    return _meter.records


def meter_add_earlier(records: list[dict] | None) -> None:
    """On a resume: put the usage recorded before the stop back in front."""
    if records and hasattr(_meter, "records"):
        _meter.records[:0] = records


def usage_line(rec: dict) -> str:
    """A progress-log line the app turns into live token counts (and hides from the log)."""
    return "§usage " + json.dumps(rec)


def meter_records() -> list[dict]:
    return list(getattr(_meter, "records", []))


def _record(schema, usage: dict) -> None:
    rec = {"step": STEP_NAMES.get(schema.__name__, schema.__name__), "at": round(time.time(), 1), **usage}
    rec["tokens"] = rec["input"] + rec["output"] + rec["cache_read"] + rec["cache_write"]
    if hasattr(_meter, "records"):
        _meter.records.append(rec)
    fn = getattr(_meter, "fn", None)
    if fn:
        fn(rec)
    log.info("Claude usage for %s: %s tokens", rec["step"], f"{rec['tokens']:,}")


def _cli_usage(out: dict) -> dict:
    """Totals for one Claude Code run across every model it used (web search and helpers included)."""
    models = out.get("modelUsage") or {}
    if models:
        total = lambda k: sum(int(m.get(k) or 0) for m in models.values())
        return {"input": total("inputTokens"), "output": total("outputTokens"), "cache_read": total("cacheReadInputTokens"),
                "cache_write": total("cacheCreationInputTokens"), "web_searches": total("webSearchRequests"),
                "cost_usd": round(sum(float(m.get("costUSD") or 0) for m in models.values()), 4)}
    u = out.get("usage") or {}
    return {"input": u.get("input_tokens", 0), "output": u.get("output_tokens", 0),
            "cache_read": u.get("cache_read_input_tokens", 0), "cache_write": u.get("cache_creation_input_tokens", 0),
            "web_searches": 0, "cost_usd": out.get("total_cost_usd")}


def summarize_usage(records: list[dict]) -> dict:
    """Per-step and total token counts for a report or a job."""
    steps: dict[str, dict] = {}
    for r in records:
        s = steps.setdefault(r["step"], {"calls": 0, "tokens": 0, "input": 0, "output": 0, "cache_read": 0,
                                          "cache_write": 0, "cost_usd": 0.0})
        s["calls"] += 1
        for k in ("tokens", "input", "output", "cache_read", "cache_write"):
            s[k] += int(r.get(k) or 0)
        s["cost_usd"] = round(s["cost_usd"] + float(r.get("cost_usd") or 0), 4)
    total = {k: sum(s[k] for s in steps.values()) for k in ("calls", "tokens", "input", "output", "cache_read", "cache_write")}
    total["cost_usd"] = round(sum(s["cost_usd"] for s in steps.values()), 4)
    return {"steps": steps, "total": total}


def set_limit_reporter(report) -> None:
    """Where this thread's "paused"/"resumed" messages go (the video's progress log)."""
    _reporter.fn = report


def _report(msg: str) -> None:
    getattr(_reporter, "fn", None) and _reporter.fn(msg)
    log.warning(msg)


def _zone(name: str | None):
    if not name or name.upper() in ("UTC", "GMT"):
        return timezone.utc if name else None
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo({"Asia/Calcutta": "Asia/Kolkata"}.get(name, name))
    except Exception:  # unknown name, or no tz database (Windows without tzdata)
        return None


def reset_time(message: str, now: datetime | None = None) -> float | None:
    """The reset moment in a limit message ("resets 10:30pm (UTC)", "resets Oct 3, 9am
    (Asia/Calcutta)") as a timestamp, or None if there isn't one."""
    m = re.search(r"resets?\s+(?:at\s+)?(?:([A-Za-z]{3})[a-z]*\s+(\d{1,2}),?\s+(?:at\s+)?)?"
                  r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*(?:\(([^)]+)\))?", message, re.I)
    if not m:
        return None
    mon, day, hour, minute, ampm, zone = m.groups()
    hour, minute = int(hour) % 24, int(minute or 0)
    if ampm:
        hour = hour % 12 + (12 if ampm.lower() == "pm" else 0)
    tz = _zone(zone)
    now = (now or datetime.now(timezone.utc)).astimezone(tz)  # tz None = this computer's zone
    try:
        when = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if mon:
            when = when.replace(month=datetime.strptime(mon[:3].title(), "%b").month, day=int(day))
            if when <= now:
                when = when.replace(year=when.year + 1)
        elif when <= now:
            when += timedelta(days=1)
    except ValueError:
        return None
    return when.timestamp()


def _wait_for_limit() -> None:
    until = _limit_until
    if time.time() >= until:
        return
    clock = datetime.fromtimestamp(until).strftime("%H:%M")
    _report(f"Paused: Claude usage limit reached. Waiting until {clock}, then continuing from this step")
    while time.time() < _limit_until:
        stopper.sleep(min(60, max(1, _limit_until - time.time())))
    _report("Resumed after the Claude usage limit reset")


def ask(backend: str, model: str, system: str, prompt: str, schema: type[T],
        images: list[Path] | None = None, allow_web: bool = False, cwd: Path | None = None,
        effort: str = "", timeout: int = 900) -> T:
    """`timeout`: seconds one Claude Code run may take (long-video scripts need more)."""
    global _limit_until
    while True:
        stopper.check()
        _wait_for_limit()
        try:
            return _ask_once(backend, model, system, prompt, schema, images, allow_web, cwd, effort, timeout)
        except LLMError as exc:
            if not LIMIT_RE.search(str(exc)):
                raise
            until = (reset_time(str(exc)) or time.time() + 30 * 60) + LIMIT_BUFFER
            with _limit_lock:
                _limit_until = max(_limit_until, until)


def _ask_once(backend: str, model: str, system: str, prompt: str, schema: type[T],
              images: list[Path] | None, allow_web: bool, cwd: Path | None, effort: str, timeout: int = 900) -> T:
    backend = resolve_backend(backend)
    if backend == "claude-code":
        return _ask_claude_code(model, system, prompt, schema, images or [], allow_web, cwd, effort, timeout)
    return _ask_api(model, system, prompt, schema, images or [], effort)


def _ask_claude_code(model: str, system: str, prompt: str, schema: type[T], images: list[Path],
                     allow_web: bool, cwd: Path | None, effort: str = "", timeout: int = 900) -> T:
    claude = find_claude()
    if claude is None:
        raise LLMError(INSTALL_HELP)
    tools = []
    if images:
        tools.append("Read")
        prompt += "\n\nLook at these image files with the Read tool before answering:\n" + \
                  "\n".join(str(p.resolve()) for p in images)
    if allow_web:
        tools += ["WebSearch", "WebFetch"]

    # How the prompt travels matters on Windows:
    # - Command-line arguments are Unicode-safe (Hindi, ₹, emoji arrive intact), but the
    #   whole command line is capped at about 32,000 characters.
    # - Piped stdin is NOT safe there: Claude Code decodes it with the legacy code page and
    #   Hindi turns into "à¤Ÿà¤¾…".
    # So short prompts go as an argument; a prompt too long for that goes into a UTF-8 file
    # that Claude reads with its Read tool. The system prompt always goes in a file.
    schema_json = json.dumps(schema.model_json_schema())
    temp_files = []

    def temp_file(text: str) -> str:
        with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=False) as fh:
            fh.write(text)
        temp_files.append(fh.name)
        return fh.name

    system_file = temp_file(system)
    if len(prompt) + len(schema_json) + 2000 > 30000:
        prompt_file = temp_file(prompt)
        prompt = (f"Your full task is in the UTF-8 text file {prompt_file}. Read the whole file with the "
                  "Read tool first, then do exactly what it asks.")
        if "Read" not in tools:
            tools.append("Read")
    cmd = [
        claude, "-p", prompt,
        "--output-format", "json",
        "--json-schema", schema_json,
        "--append-system-prompt-file", system_file,
    ]
    if model:
        cmd += ["--model", model]
    if effort:
        cmd += ["--effort", effort]
    # Only the tools this step needs are available, and they're pre-approved
    # so the non-interactive run never waits on a permission prompt.
    cmd += ["--tools", ",".join(tools)]
    if tools:
        cmd += ["--allowedTools", *tools]

    log.info("Asking Claude Code (%s)%s", model or "default model", " with web search" if allow_web else "")
    try:
        # Output is always read as UTF-8: Windows would otherwise decode it with its legacy
        # code page, fail on characters like ₹ or emoji, and hand back no output at all.
        # stopper.run: killed at once when the job is stopped (Stop and remove on the Create tab).
        proc = stopper.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, cwd=cwd, stdin=subprocess.DEVNULL)
    finally:
        for name in temp_files:
            Path(name).unlink(missing_ok=True)
    stdout, stderr = proc.stdout or "", proc.stderr or ""
    if proc.returncode != 0 and not stdout.strip():
        raise LLMError(f"claude CLI failed ({proc.returncode}): {stderr.strip()[:500]}")
    try:
        out = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise LLMError(f"claude CLI returned non-JSON output: {stdout[:300]}") from exc
    if out.get("is_error"):
        raise LLMError(f"Claude Code error: {out.get('result') or out.get('subtype')}")

    _record(schema, _cli_usage(out))
    data = out.get("structured_output")
    if data is None:  # older CLI versions: parse the text result
        data = _extract_json(out.get("result", ""))
    try:
        return schema.model_validate(data)
    except ValidationError as exc:
        raise LLMError(f"Claude Code output did not match the schema: {exc}") from exc


def _ask_api(model: str, system: str, prompt: str, schema: type[T], images: list[Path],
             effort: str = "") -> T:
    import anthropic

    content: list[dict] = []
    for img in images:
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg",
                       "data": base64.b64encode(img.read_bytes()).decode()},
        })
    content.append({"type": "text", "text": prompt})

    response = anthropic.Anthropic().messages.parse(
        model=model or "claude-opus-5-5",
        max_tokens=16000,
        system=system,
        messages=[{"role": "user", "content": content}],
        output_format=schema,  # the SDK merges this into output_config.format
        **({"output_config": {"effort": effort}} if effort else {}),
    )
    u = response.usage
    _record(schema, {"input": u.input_tokens or 0, "output": u.output_tokens or 0,
                     "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
                     "cache_write": getattr(u, "cache_creation_input_tokens", 0) or 0, "cost_usd": None, "web_searches": 0})
    if response.stop_reason == "refusal" or response.parsed_output is None:
        raise LLMError(f"Claude returned no usable answer (stop_reason={response.stop_reason})")
    return response.parsed_output


def _extract_json(text: str):
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise LLMError(f"no JSON object in Claude's reply: {text[:300]}")
    return json.loads(text[start:end + 1])
