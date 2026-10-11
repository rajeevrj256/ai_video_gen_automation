"""Update and restart from the app (Settings > App updates, or the orange bar).

The running app can't replace itself, so it hands over to a small helper process and quits:

1. the app stops every running video at once (their checkpoints stay, so they resume later),
2. starts `python -m reelgen.updater` detached, then ends itself at once (`hard_exit`),
3. the helper waits for the old app to be gone (ending it, and its window, if it hangs), ends anything
   it left running, waits until the port is free, runs `git pull --ff-only` on the current branch,
4. and starts the app again with start.bat / start.sh, which install anything new the pull added
   (Python packages, the editor's npm packages) before the app opens.

On Windows `os._exit` still runs every loaded library's exit code, and one of them (OpenMP, ONNX, BLAS
thread pools) can hang there with the port still open: the old window stayed, and the new app stopped with
"address already in use" after the helper had waited 90 s. TerminateProcess skips that code.

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
    dirty = [l[3:] for l in _git("status", "--porcelain", "--untracked-files=no").stdout.splitlines()][:30]
    # Windows checkouts often show files as changed when only their line endings differ: not edits of yours
    real = [f for f in dirty if _git("diff", "--quiet", "--ignore-cr-at-eol", "--", f).returncode != 0]
    return {"ok": True, "branch": b, "head": head(), "behind": len(new), "commits": new[:15], "local_changes": real[:10]}


def start(output_dir: Path, port: int, serve_args: list[str]) -> None:
    """Start the helper, detached so it outlives this app."""
    cmd = [sys.executable, "-m", "reelgen.updater", "--port", str(port), "--output", str(output_dir),
           "--pid", str(os.getpid()), "--parent", str(os.getppid()), "--", *serve_args]
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


def hard_exit(code: int) -> None:
    """End this process now, skipping the libraries' exit code (see the module's notes)."""
    if WINDOWS:
        import ctypes

        k = ctypes.windll.kernel32  # type: ignore[attr-defined]
        k.GetCurrentProcess.restype = ctypes.c_void_p
        k.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        k.TerminateProcess(k.GetCurrentProcess(), code)
    os._exit(code)


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def port_bindable(port: int, wait: float = 0) -> bool:
    """Whether the app could listen on `port`, waiting up to `wait` s for it to free up."""
    end = time.time() + wait
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if not WINDOWS:  # like uvicorn: a closed connection still waiting (TIME_WAIT) doesn't block it
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("0.0.0.0", port))
                return True
            except OSError:
                pass
        if time.time() >= end:
            return False
        time.sleep(1)


def _run(cmd: list[str], timeout: int = 30) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=timeout).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def _alive(pid: int) -> bool:
    if WINDOWS:
        import ctypes

        k = ctypes.windll.kernel32  # type: ignore[attr-defined]
        k.OpenProcess.restype = ctypes.c_void_p
        k.OpenProcess.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.c_uint]
        k.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        k.CloseHandle.argtypes = [ctypes.c_void_p]
        h = k.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
        if not h:
            return False
        try:
            return k.WaitForSingleObject(h, 0) == 0x102  # WAIT_TIMEOUT: still running
        finally:
            k.CloseHandle(h)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:  # ended but not yet collected by its parent (a zombie) counts as gone
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] != "Z"
    except (OSError, IndexError):
        return True


def _image(pid: int) -> str:
    """The program a process runs (Windows), e.g. 'cmd.exe'; '' if unknown."""
    if not WINDOWS:
        return ""
    line = _run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"]).strip()
    return line.split('","')[0].strip('"') if line.startswith('"') else ""


def _children(pid: int) -> list[int]:
    """Processes the old app started (a render, an AI worker, cloudflared...), still running after it ended."""
    if WINDOWS:
        out = _run(["powershell", "-NoProfile", "-Command",
                    f"(Get-CimInstance Win32_Process -Filter 'ParentProcessId={pid}').ProcessId"])
    else:
        out = _run(["pgrep", "-P", str(pid)])
    return [int(x) for x in out.split() if x.isdigit() and int(x) != os.getpid()]


def _kill(pid: int, tree: bool = True) -> None:
    """End a process (and what it started, if `tree`). Never with `tree` on the old app or its window:
    this helper is the old app's child and would end itself."""
    if WINDOWS:
        _run(["taskkill", "/F", *(["/T"] if tree else []), "/PID", str(pid)])
        return
    import signal

    kills = [lambda: os.killpg(pid, signal.SIGKILL)] if tree else []
    for kill in kills + [lambda: os.kill(pid, signal.SIGKILL)]:
        try:
            kill()
        except OSError:
            pass


def port_owner(port: int) -> str:
    """Who listens on `port`, e.g. 'python.exe (PID 1234)' (Windows; '' elsewhere or if nobody)."""
    if not WINDOWS:
        return ""
    for line in _run(["netstat", "-ano", "-p", "TCP"]).splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[3] == "LISTENING" and parts[1].endswith(f":{port}") and parts[4].isdigit():
            pid = int(parts[4])
            return f"{_image(pid) or 'a program'} (PID {pid})"
    return ""


def _end_old_app(pid: int, parent: int) -> str:
    """Wait for the old app to be gone; end it (and its window) if it hangs, then whatever it left running."""
    note = ""
    kids = _children(pid)  # now: once it ends, Linux hands its children to another parent
    end = time.time() + 20
    while _alive(pid) and time.time() < end:
        time.sleep(0.5)
    if _alive(pid):
        _kill(pid, tree=False)
        if parent and _image(parent).lower() == "cmd.exe":  # its start.bat window would wait for a key
            _kill(parent, tree=False)
        time.sleep(1)
        note = "The old app hung while closing, so it was ended. "
    for child in dict.fromkeys(kids + _children(pid)):  # never this helper (also the old app's child)
        _kill(child)
    return note


def _relaunch(serve_args: list[str], output_dir: Path) -> None:
    env = {**os.environ, "REEL_WAIT_PORT": "60"}  # the new app waits for the port instead of failing at once
    if WINDOWS:  # its own console window, like double-clicking start.bat
        subprocess.Popen(["cmd.exe", "/c", str(APP_DIR / "start.bat"), *serve_args], cwd=APP_DIR, env=env,
                         creationflags=subprocess.CREATE_NEW_CONSOLE)  # type: ignore[attr-defined]
    else:
        logs = APP_DIR.parent / "logs"
        logs.mkdir(exist_ok=True)
        out = open(logs / "reel-studio.log", "a", encoding="utf-8")
        subprocess.Popen(["bash", str(APP_DIR / "start.sh"), *serve_args], cwd=APP_DIR, stdout=out, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, start_new_session=True, env=env)


def _helper(port: int, output_dir: Path, serve_args: list[str], pid: int = 0, parent: int = 0) -> None:
    result = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "branch": branch(), "from": head(), "ok": False}
    note = _end_old_app(pid, parent) if pid else ""
    deadline = time.time() + 30
    while not _port_free(port) and time.time() < deadline:  # the app is shutting down
        time.sleep(0.5)
    if not _port_free(port):
        owner = port_owner(port)
        note += f"Port {port} is still in use" + (f" by {owner}" if owner else "") + ". "
    print(note or "The old app closed.", flush=True)
    time.sleep(1.5)  # let Windows let go of its files
    try:
        b = result["branch"]
        pulled = _git("pull", "--ff-only", "origin", b, timeout=300)
        print(pulled.stdout, pulled.stderr, flush=True)
        result["to"] = head()
        if pulled.returncode == 0:
            result["ok"] = True
            result["message"] = note + (f"Updated {result['from']} → {result['to']}" if result["to"] != result["from"]
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
    p.add_argument("--pid", type=int, default=0)
    p.add_argument("--parent", type=int, default=0)
    p.add_argument("rest", nargs="*")
    a = p.parse_args()
    _helper(a.port, Path(a.output), a.rest, a.pid, a.parent)
