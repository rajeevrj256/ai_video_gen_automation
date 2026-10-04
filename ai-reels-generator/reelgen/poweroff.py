"""Shut the computer down once every job has finished (Create tab: "⏻ Shut down PC when done").

Armed from the app; a watcher thread checks every 15 s. When no job is queued or running it waits
GRACE seconds more (a batch can sit between two videos for a moment, and you can still cancel), tells
Telegram, then asks the system to shut down with a further minute's warning (Windows: `shutdown /s /t 60`,
which `shutdown /a` or the app's Cancel can still stop). Only the jobs in the app count; a scheduled
automation later that day won't run once the computer is off.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from typing import Callable

log = logging.getLogger(__name__)

GRACE = 60  # seconds with nothing running before the shutdown is issued
OS_DELAY = 60  # the system's own warning before it powers off

state = {"armed": False, "since": 0.0, "idle_since": 0.0, "issued": False, "error": ""}
_lock = threading.Lock()


def _shutdown_cmd() -> list[str]:
    if os.name == "nt":
        return ["shutdown", "/s", "/t", str(OS_DELAY), "/c", "Reel Studio: every video is finished, shutting down."]
    if sys.platform == "darwin":
        return ["osascript", "-e", 'tell app "System Events" to shut down']
    return ["shutdown", "-h", f"+{max(1, OS_DELAY // 60)}"]


def _abort_cmd() -> list[str] | None:
    if os.name == "nt":
        return ["shutdown", "/a"]
    if sys.platform == "darwin":
        return None
    return ["shutdown", "-c"]


def arm(on: bool) -> dict:
    with _lock:
        if on:
            state.update(armed=True, since=time.time(), idle_since=0.0, issued=False, error="")
        else:
            if state["issued"] and (cmd := _abort_cmd()):
                subprocess.run(cmd, capture_output=True, check=False)
            state.update(armed=False, idle_since=0.0, issued=False, error="")
    return view()


def view() -> dict:
    s = dict(state)
    if s["armed"] and s["idle_since"] and not s["issued"]:
        s["in"] = max(0, int(GRACE - (time.time() - s["idle_since"])))
    return s


def watch(busy: Callable[[], bool], tell: Callable[[str], None]) -> None:
    """Runs for the app's lifetime."""
    while True:
        time.sleep(5)
        with _lock:
            if not state["armed"] or state["issued"]:
                continue
            if busy():
                state["idle_since"] = 0.0
                continue
            if not state["idle_since"]:
                state["idle_since"] = time.time()
                continue
            if time.time() - state["idle_since"] < GRACE:
                continue
            state["issued"] = True
        tell("⏻ Reel Studio: every job is finished, shutting the computer down in about a minute.")
        try:
            proc = subprocess.run(_shutdown_cmd(), capture_output=True, text=True, timeout=30)
            if proc.returncode != 0:
                raise OSError((proc.stderr or proc.stdout).strip() or f"exit code {proc.returncode}")
            log.warning("Shutdown requested: every job finished")
        except (OSError, subprocess.SubprocessError) as exc:
            with _lock:
                state.update(armed=False, issued=False, error=f"Couldn't shut down: {exc}")
            tell(f"⚠️ Reel Studio couldn't shut the computer down: {exc}")
