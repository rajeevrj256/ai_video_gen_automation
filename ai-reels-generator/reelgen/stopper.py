"""Stop a job right away (the app's "Stop and remove"), not at the next step boundary.

Pause waits for the step a video is on (a fact-check, a render) and saves it for Resume. Stop kills
whatever the video is running now (a Claude Code call, a Remotion render, the stills preview) and the
video's thread ends with `Stopped`. Every long-running program goes through `run`, which polls the
job's stop flag once a second while the program works and kills its whole process tree when set.
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time

_local = threading.local()


class Paused(Exception):
    """Raised at a step boundary when the user pressed Pause; the checkpoint is already saved."""


class Stopped(Paused):
    """The user stopped the job: whatever was running was killed. A Paused, so every video loop
    that ends cleanly on a pause ends on this too."""


def set_checks(pause_fn) -> None:
    """For this video's thread: the job's pause check; its `.stop` attribute (if any) is the stop check."""
    _local.pause = pause_fn
    _local.stop = getattr(pause_fn, "stop", None)


def pause_requested() -> bool:
    fn = getattr(_local, "pause", None)
    return bool(fn and fn())


def stop_requested() -> bool:
    fn = getattr(_local, "stop", None)
    return bool(fn and fn())


def check() -> None:
    if stop_requested():
        raise Stopped()


def sleep(seconds: float) -> None:
    """time.sleep that ends early (with Stopped) when the job is stopped."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        check()
        time.sleep(min(1.0, max(0.0, end - time.monotonic())))


def _kill(proc: subprocess.Popen) -> None:
    try:
        if os.name == "nt":  # claude and remotion start child processes (node, Chrome): take the tree
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        pass
    try:
        proc.kill()
    except OSError:
        pass


def run(cmd, *, input=None, capture_output: bool = False, timeout: float | None = None, check: bool = False,
        **kw) -> subprocess.CompletedProcess:
    """subprocess.run, but killed (process tree included) as soon as the job is stopped."""
    stop = getattr(_local, "stop", None)
    if stop is None:
        return subprocess.run(cmd, input=input, capture_output=capture_output, timeout=timeout, check=check, **kw)
    if capture_output:
        kw.setdefault("stdout", subprocess.PIPE)
        kw.setdefault("stderr", subprocess.PIPE)
    if input is not None:
        kw.setdefault("stdin", subprocess.PIPE)
    if os.name == "nt":
        kw["creationflags"] = kw.get("creationflags", 0) | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    proc = subprocess.Popen(cmd, **kw)
    out: dict = {}
    talker = threading.Thread(target=lambda: out.update(r=proc.communicate(input)), daemon=True)
    talker.start()
    started = time.monotonic()
    while talker.is_alive():
        talker.join(1)
        if not talker.is_alive():
            break
        if stop():
            _kill(proc)
            talker.join(10)
            raise Stopped()
        if timeout and time.monotonic() - started > timeout:
            _kill(proc)
            talker.join(10)
            raise subprocess.TimeoutExpired(cmd, timeout)
    stdout, stderr = out.get("r", (None, None))
    done = subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)
    if check:
        done.check_returncode()
    return done
