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

On Windows `.venv/Scripts/python.exe` is a launcher that starts the real Python as its child, so the app runs as
window cmd.exe → launcher → app, and the helper as app → launcher → helper. The helper used to end every child of
the old app, its own launcher among them, and with it itself: the app closed and nothing pulled or started again
(the user: "just close but it not restart"). The window's cmd.exe also sat one launcher further up than the helper
looked. `_table` lists every process, the helper's own chain is never ended, and the window is found above the
launchers.

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


def _say(msg: str) -> None:
    print(time.strftime("%H:%M:%S ") + msg, flush=True)  # <output>/update.log


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
           "--pid", str(os.getpid()), "--born", str(_born(os.getpid())), "--", *serve_args]
    log = open(output_dir / "update.log", "w", encoding="utf-8")
    if WINDOWS:
        # A hidden console of its own: with DETACHED_PROCESS the venv launcher's child got a new visible window.
        flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        _spawn(cmd, flags, cwd=APP_DIR, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    else:
        subprocess.Popen(cmd, cwd=APP_DIR, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)


def _spawn(cmd: list[str], flags: int, **kw) -> subprocess.Popen:
    """Windows: start `cmd` outside any job the caller is in (a job can end its processes together), if allowed."""
    try:
        return subprocess.Popen(cmd, creationflags=flags | subprocess.CREATE_BREAKAWAY_FROM_JOB, **kw)  # type: ignore[attr-defined]
    except OSError:  # the job doesn't allow it: started inside it (the venv launcher's job lets children go anyway)
        return subprocess.Popen(cmd, creationflags=flags, **kw)


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


LAUNCHERS = ("python.exe", "pythonw.exe", "py.exe")  # .venv/Scripts/python.exe starts the real Python as its child


def _table() -> dict[int, tuple[int, str]]:
    """Every running process: PID -> (parent PID, program name in lower case, e.g. 'cmd.exe'). Empty if unreadable."""
    if not WINDOWS:
        return _parse(_run(["ps", "-Ao", "pid=,ppid=,comm="]))
    try:
        return _toolhelp()
    except Exception as exc:  # noqa: BLE001 - PowerShell below
        _say(f"Process list via Toolhelp failed ({exc}); asking PowerShell")
    return _parse(_run(["powershell", "-NoProfile", "-Command",
                        'Get-CimInstance Win32_Process | ForEach-Object { "$($_.ProcessId) $($_.ParentProcessId) $($_.Name)" }'], 60))


def _parse(out: str) -> dict[int, tuple[int, str]]:
    """Lines of 'PID PARENT NAME'."""
    table = {}
    for line in out.splitlines():
        parts = line.split(None, 2)
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            table[int(parts[0])] = (int(parts[1]), (parts[2] if len(parts) > 2 else "").strip().lower())
    return table


def _toolhelp() -> dict[int, tuple[int, str]]:
    """Windows' own process snapshot (CreateToolhelp32Snapshot): instant, no PowerShell."""
    import ctypes
    from ctypes import wintypes

    class Entry(ctypes.Structure):  # PROCESSENTRY32W
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]

    k = ctypes.WinDLL("kernel32", use_last_error=True)  # its own copy: argtypes set here touch nobody else's
    k.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    k.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    for f in (k.Process32FirstW, k.Process32NextW):
        f.restype = wintypes.BOOL
        f.argtypes = [ctypes.c_void_p, ctypes.POINTER(Entry)]
    k.CloseHandle.argtypes = [ctypes.c_void_p]
    snap = k.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if not snap or snap == ctypes.c_void_p(-1).value:
        raise OSError(ctypes.get_last_error(), "CreateToolhelp32Snapshot failed")
    table = {}
    try:
        e = Entry()
        e.dwSize = ctypes.sizeof(Entry)
        ok = k.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            table[int(e.th32ProcessID)] = (int(e.th32ParentProcessID), e.szExeFile.lower())
            ok = k.Process32NextW(snap, ctypes.byref(e))
    finally:
        k.CloseHandle(snap)
    if not table:
        raise OSError("no processes listed")
    return table


def _chain(pid: int, table: dict[int, tuple[int, str]]) -> list[int]:
    """`pid`'s parent, grandparent... nearest first."""
    out, seen = [], {pid}
    while pid in table:
        pid = table[pid][0]
        if pid <= 0 or pid in seen:
            break
        seen.add(pid)
        out.append(pid)
    return out


def _name(pid: int, table: dict[int, tuple[int, str]]) -> str:
    return table.get(pid, (0, ""))[1]


def _window(pid: int, table: dict[int, tuple[int, str]]) -> tuple[list[int], int]:
    """The launchers between the old app and its start.bat window, and that window's cmd.exe (0 if none):
    window cmd.exe → .venv launcher (python.exe) → the app."""
    launchers = []
    for up in _chain(pid, table):
        if _name(up, table) in LAUNCHERS:
            launchers.append(up)
            continue
        return launchers, (up if _name(up, table) == "cmd.exe" else 0)
    return launchers, 0


def _children(pid: int, table: dict[int, tuple[int, str]], mine: set[int], born: int = 0) -> list[int]:
    """Processes the old app started (a render, an AI worker, cloudflared...), never this helper or its launcher."""
    kids = [p for p, (parent, _) in table.items() if parent == pid and p not in mine]
    if WINDOWS:  # a process keeps the PID of a parent long gone (explorer.exe: userinit's), and PIDs are reused
        kids = [p for p in kids if born and _born(p) >= born]
    return kids


def _born(pid: int) -> int:
    """When a process started (Windows FILETIME), 0 if unknown or not Windows."""
    if not WINDOWS:
        return 0
    import ctypes
    from ctypes import wintypes

    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenProcess.restype = ctypes.c_void_p
    k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k.GetProcessTimes.restype = wintypes.BOOL
    k.GetProcessTimes.argtypes = [ctypes.c_void_p] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    k.CloseHandle.argtypes = [ctypes.c_void_p]
    h = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return 0
    try:
        t = [wintypes.FILETIME() for _ in range(4)]
        if not k.GetProcessTimes(h, *(ctypes.byref(x) for x in t)):
            return 0
        return (t[0].dwHighDateTime << 32) | t[0].dwLowDateTime
    finally:
        k.CloseHandle(h)


def _still(pid: int, born: int) -> bool:
    """The old app is still running (not another program that got its PID since)."""
    return _alive(pid) and (not WINDOWS or not born or _born(pid) == born)


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
            return f"{_name(pid, _table()) or 'a program'} (PID {pid})"
    return ""


def _end_old_app(pid: int, born: int) -> str:
    """Wait for the old app to be gone; end it (and its window) if it hangs, then whatever it left running."""
    note = ""
    table = _table()
    mine = {os.getpid(), *_chain(os.getpid(), table)}  # this helper and the launcher that started it: never ended
    launchers, window = _window(pid, table)
    kids = _children(pid, table, mine, born)  # now: once it ends, Linux hands its children to another parent
    _say(f"Old app PID {pid}" + (f", launcher {launchers}" if launchers else "") + (f", window cmd.exe {window}" if window else "")
         + f"; this helper PID {os.getpid()}; left running by the app: {kids or 'nothing'}")
    end = time.time() + 20
    while _still(pid, born) and time.time() < end:
        time.sleep(0.5)
    if _still(pid, born):
        _say("The old app didn't close in 20 s: ending it")
        _kill(pid, tree=False)
        for p in launchers:  # they end once the app is gone; not waited on
            _kill(p, tree=False)
        if window:  # its start.bat window would wait for a key
            _kill(window, tree=False)
        time.sleep(1)
        note = "The old app hung while closing, so it was ended. "
    later = _children(pid, _table(), mine, born)  # Windows keeps the old parent PID on processes started since
    for child in dict.fromkeys(kids + later):
        _kill(child)
    return note


def _relaunch(serve_args: list[str], output_dir: Path) -> None:
    env = {**os.environ, "REEL_WAIT_PORT": "60"}  # the new app waits for the port instead of failing at once
    if WINDOWS:  # its own console window, like double-clicking start.bat
        _spawn(["cmd.exe", "/c", str(APP_DIR / "start.bat"), *serve_args], subprocess.CREATE_NEW_CONSOLE,  # type: ignore[attr-defined]
               cwd=APP_DIR, env=env)
    else:
        logs = APP_DIR.parent / "logs"
        logs.mkdir(exist_ok=True)
        out = open(logs / "reel-studio.log", "a", encoding="utf-8")
        subprocess.Popen(["bash", str(APP_DIR / "start.sh"), *serve_args], cwd=APP_DIR, stdout=out, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, start_new_session=True, env=env)


def _helper(port: int, output_dir: Path, serve_args: list[str], pid: int = 0, born: int = 0) -> None:
    _say(f"Update helper started (PID {os.getpid()})")
    result = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "branch": "", "from": "", "ok": False}
    try:
        note = _end_old_app(pid, born) if pid else ""
    except Exception as exc:  # noqa: BLE001 - the app must come back whatever happened
        note = ""
        _say(f"Couldn't check the old app's processes: {exc}")
    deadline = time.time() + 30
    while not _port_free(port) and time.time() < deadline:  # the app is shutting down
        time.sleep(0.5)
    if not _port_free(port):
        owner = port_owner(port)
        note += f"Port {port} is still in use" + (f" by {owner}" if owner else "") + ". "
    _say(note or "The old app closed.")
    time.sleep(1.5)  # let Windows let go of its files
    try:
        b = result["branch"] = branch()
        result["from"] = head()
        _say(f"git pull --ff-only origin {b}")
        pulled = _git("pull", "--ff-only", "origin", b, timeout=300)
        _say((pulled.stdout + pulled.stderr).strip())
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
    try:
        (output_dir / RESULT).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        _say(f"Couldn't write {RESULT}: {exc}")
    _say(result["message"])
    _relaunch(serve_args, output_dir)
    _say("Started the app again")


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--pid", type=int, default=0)
    p.add_argument("--born", type=int, default=0)  # the old app's start time (Windows), so a reused PID isn't it
    p.add_argument("rest", nargs="*")
    a = p.parse_args()
    _helper(a.port, Path(a.output), a.rest, a.pid, a.born)
