"""Blender, free (GPL) and portable, for the low-poly films' best look (reelgen/lowpoly/blend.py; the user, after a
Blender low-poly diorama: "this use blender to build this, you use this also. i need this level with free").

The official LTS build from download.blender.org is unpacked into tools/blender (git-ignored, ~1.1 GB on disk,
~400 MB to download), checked against Blender's own SHA-256 list. Nothing is installed system-wide; deleting the
folder removes it. `REEL_BLENDER` can point at a Blender already on the computer instead.

`install` runs in a background thread with its log in `state`; `binary` is the program to run.
"""
from __future__ import annotations

import hashlib
import logging
import os
import platform
import shutil
import subprocess
import tarfile
import threading
import zipfile
from pathlib import Path

import requests

from .config import PROJECT_ROOT

log = logging.getLogger(__name__)

VERSION = "4.5.16"  # the LTS line (supported until 2027); its Python API is what blender_worker/ is written for
SERIES = "4.5"
SITE = f"https://download.blender.org/release/Blender{SERIES}/"
ROOT = PROJECT_ROOT / "tools" / "blender"
WORKER = PROJECT_ROOT / "blender_worker"
state: dict = {"installing": False, "log": [], "error": ""}
_lock = threading.Lock()


def _package() -> str:
    system = platform.system()
    if system == "Windows":
        return f"blender-{VERSION}-windows-x64.zip"
    if system == "Linux":
        return f"blender-{VERSION}-linux-x64.tar.xz"
    if system == "Darwin":
        return f"blender-{VERSION}-macos-{'arm64' if platform.machine() == 'arm64' else 'x64'}.dmg"
    return ""


def binary() -> Path | None:
    """The Blender program to run, or None."""
    own = os.environ.get("REEL_BLENDER", "").strip()
    if own and Path(own).exists():
        return Path(own)
    for name in ("blender.exe", "blender"):
        p = ROOT / name
        if p.exists():
            return p
    return None


def version() -> str:
    exe = binary()
    if not exe:
        return ""
    try:
        out = subprocess.run([str(exe), "--version"], capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""
    first = out.strip().splitlines()[0] if out.strip() else ""
    return first.replace("Blender", "").strip()


def status() -> dict:
    exe = binary()
    return {"installed": bool(exe), "version": version() if exe else "", "installing": state["installing"],
            "log": state["log"][-8:], "error": state["error"], "size": "about 400 MB to download, 1.1 GB on disk",
            "supported": bool(_package()) and not _package().endswith(".dmg")}


def _say(line: str) -> None:
    log.info("Blender: %s", line)
    state["log"].append(line)
    del state["log"][:-40]


def install() -> bool:
    """Start installing in the background; False when it is already running or already there."""
    with _lock:
        if state["installing"] or binary():
            return False
        state.update(installing=True, error="", log=[])
    threading.Thread(target=_install, daemon=True).start()
    return True


def _install() -> None:
    try:
        pkg = _package()
        if not pkg or pkg.endswith(".dmg"):
            raise RuntimeError("Blender can be set up here on Windows and Linux; on a Mac, install it and set REEL_BLENDER")
        ROOT.parent.mkdir(parents=True, exist_ok=True)
        part = ROOT.parent / (pkg + ".part")
        _say(f"Downloading Blender {VERSION} (free, GPL) from blender.org")
        with requests.get(SITE + pkg, stream=True, timeout=60) as r:
            r.raise_for_status()
            size = int(r.headers.get("content-length") or 0)
            got, shown = 0, 0
            digest = hashlib.sha256()
            with open(part, "wb") as fh:
                for chunk in r.iter_content(1 << 20):
                    fh.write(chunk)
                    digest.update(chunk)
                    got += len(chunk)
                    if size and got - shown > size / 10:
                        shown = got
                        _say(f"Downloading: {got * 100 // size}%")
        sums = requests.get(SITE + f"blender-{VERSION}.sha256", timeout=60).text
        want = next((line.split()[0] for line in sums.splitlines() if line.strip().endswith(pkg)), "")
        if want and want.lower() != digest.hexdigest():
            part.unlink(missing_ok=True)
            raise RuntimeError("The download didn't match Blender's own checksum; try again")
        _say("Unpacking")
        tmp = ROOT.parent / "blender-unpack"
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir()
        if pkg.endswith(".zip"):
            with zipfile.ZipFile(part) as z:
                z.extractall(tmp)
        else:
            with tarfile.open(part) as t:
                t.extractall(tmp, filter="data")
        inner = next(tmp.iterdir())
        shutil.rmtree(ROOT, ignore_errors=True)
        inner.rename(ROOT)
        shutil.rmtree(tmp, ignore_errors=True)
        part.unlink(missing_ok=True)
        if not binary():
            raise RuntimeError("Blender unpacked but its program wasn't found")
        _say(f"Blender {version() or VERSION} is ready")
    except Exception as exc:  # noqa: BLE001 - shown in the tab
        state["error"] = str(exc)
        _say(f"Failed: {exc}")
    finally:
        state["installing"] = False
