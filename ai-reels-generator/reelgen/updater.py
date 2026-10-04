"""Update and restart from the app (Settings > App updates, or the orange bar).

The running app can't replace itself, so it hands over to a small helper process and quits:

1. the app stops every running video at once (their checkpoints stay, so they resume later),
2. starts `python -m reelgen.updater` detached, then exits,
3. the helper waits until the app's port is free, runs `git pull --ff-only` on the current branch,
4. and starts the app again with start.bat / start.sh, which install anything new the pull added
   (Python packages, the editor's npm packages) before the app opens.

The outcome is written to `<output>/update.json`; the restarted app shows it and sends it on Telegram.
A pull that fails (local edits in the way, no network) still restarts the old code and says why.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent  # ai-reels-generator/
RESULT = "update.json"
WINDOWS = os.name == "nt"


def _git(*args: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=APP_DIR, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)


def branch() -> str:
    return _git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()


def head() -> str:
    return _git("rev-parse", "--short", "HEAD").stdout.strip()


def check() -> dict:
    """What an update would bring: fetches the current branch and counts the new commits."""
    b = branch()
    if not b or b == "HEAD":
        return {"ok": False, "error": "This folder isn't on a git branch, so it can't update itself."}
    got = _git("fetch", "origin", b)
    if got.returncode != 0:
        return {"ok": False, "branch": b, "error": "Couldn't reach GitHub: " + (got.stderr.strip().splitlines() or ["?"])[-1]}
    new = _git("log", "--format=%h %s", f"HEAD..origin/{b}").stdout.strip().splitlines()
    dirty = [l[3:] for l in _git("status", "--porcelain", "--untracked-files=no").stdout.splitlines()]
    return {"ok": True, "branch": b, "head": head(), "behind": len(new), "commits": new[:15], "local_changes": dirty[:10]}


def start(output_dir: Path, port: int, serve_args: list[str]) -> None:
    """Start the helper, detached so it outlives this app."""
    cmd = [sys.executable, "-m", "reelgen.updater", "--port", str(port), "--output", str(output_dir), "--", *serve_args]
    log = open(output_dir / "update.log", "w", encoding="utf-8")
    if WINDOWS:
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        subprocess.Popen(cmd, cwd=APP_DIR, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, creationflags=flags)
    else:
        subprocess.Popen(cmd, cwd=APP_DIR, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)


def last_result(output_dir: Path) -> dict | None:
    try:
        return json.loads((output_dir / RESULT).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def _relaunch(serve_args: list[str], output_dir: Path) -> None:
    if WINDOWS:  # its own console window, like double-clicking start.bat
        subprocess.Popen(["cmd.exe", "/c", str(APP_DIR / "start.bat"), *serve_args], cwd=APP_DIR,
                         creationflags=subprocess.CREATE_NEW_CONSOLE)  # type: ignore[attr-defined]
    else:
        logs = APP_DIR.parent / "logs"
        logs.mkdir(exist_ok=True)
        out = open(logs / "reel-studio.log", "a", encoding="utf-8")
        subprocess.Popen(["bash", str(APP_DIR / "start.sh"), *serve_args], cwd=APP_DIR, stdout=out, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, start_new_session=True)


def _helper(port: int, output_dir: Path, serve_args: list[str]) -> None:
    result = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "branch": branch(), "from": head(), "ok": False}
    deadline = time.time() + 90
    while not _port_free(port) and time.time() < deadline:  # the app is shutting down
        time.sleep(0.5)
    time.sleep(1.5)  # let Windows let go of its files
    try:
        b = result["branch"]
        pulled = _git("pull", "--ff-only", "origin", b, timeout=300)
        print(pulled.stdout, pulled.stderr, flush=True)
        result["to"] = head()
        if pulled.returncode == 0:
            result["ok"] = True
            result["message"] = (f"Updated {result['from']} → {result['to']}" if result["to"] != result["from"]
                                 else "Already up to date")
        else:
            err = (pulled.stderr.strip() or pulled.stdout.strip()).splitlines()
            result["message"] = "The update didn't apply, so the app restarted unchanged: " + " ".join(err[-3:])[:400]
    except Exception as exc:  # noqa: BLE001 - the app must come back whatever happened
        result["message"] = f"The update didn't apply, so the app restarted unchanged: {exc}"
    result["notified"] = False
    (output_dir / RESULT).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    print(result["message"], flush=True)
    _relaunch(serve_args, output_dir)


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, required=True)
    p.add_argument("--output", required=True)
    p.add_argument("rest", nargs="*")
    a = p.parse_args()
    _helper(a.port, Path(a.output), a.rest)
