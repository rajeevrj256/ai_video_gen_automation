"""The local AI engine behind Animated videos: its own Python with PyTorch for the graphics card, kept apart
from the app's (anim_worker/worker.py runs inside it, one stage per process).

The engine is ACE-Step 1.5's own environment (cloned into tools/ai-engine, set up by `uv sync` with the CUDA
build of PyTorch it pins), plus the few packages the picture and video stages need. All model files go to
tools/ai-models (Hugging Face cache and ACE-Step checkpoints), downloaded on first use:

    ACE-Step 1.5 turbo (music)           ~10 GB   MIT (its downloader also fetches its 1.7B LM, unused here)
    SDXL-Lightning 4-step + SDXL parts    ~7 GB   OpenRAIL++ (commercial use allowed)
    IP-Adapter Plus SDXL + image encoder  ~3 GB   Apache-2.0
    LTX-Video 2B 0.9.8 distilled          ~6 GB   LTX open weights licence (free under $10M revenue)
    T5-XXL text encoder (bf16)           ~10 GB   Apache-2.0
    plus PyTorch and the libraries        ~6 GB   -> about 45 GB in all

`install` runs in a background thread with its log in `state`; `run_stage` starts the worker, turns its
`§` lines into progress, and kills it when the job is stopped or paused (finished items are kept).
"""

from __future__ import annotations

import json
import logging
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable

from . import stopper
from .config import PROJECT_ROOT

log = logging.getLogger(__name__)
Progress = Callable[[str], None]

TOOLS = PROJECT_ROOT / "tools"
ENGINE = TOOLS / "ai-engine"
MODELS = TOOLS / "ai-models"
WORKER = PROJECT_ROOT / "anim_worker" / "worker.py"
CALIBRATION = MODELS / "calibration.json"
ACE_REPO = "https://github.com/ace-step/ACE-Step-1.5.git"
EXTRA = ["sentencepiece", "imageio", "imageio-ffmpeg", "protobuf"]
WINDOWS = os.name == "nt"

state: dict = {"installing": False, "log": [], "error": "", "done": False}
_lock = threading.Lock()


def python() -> Path:
    return ENGINE / ".venv" / ("Scripts/python.exe" if WINDOWS else "bin/python")


def installed() -> bool:
    return python().exists() and (ENGINE / ".reel-installed").exists()


def env() -> dict:
    e = dict(os.environ)
    MODELS.mkdir(parents=True, exist_ok=True)
    e.update(HF_HOME=str(MODELS / "hf"), ACESTEP_CHECKPOINTS_DIR=str(MODELS / "acestep"), PYTHONUNBUFFERED="1",
             PYTHONIOENCODING="utf-8")
    e.pop("PYTHONPATH", None)
    return e


def probe(refresh: bool = False) -> dict:
    """The graphics card as the engine sees it (cached; refreshed after an install)."""
    cache = MODELS / "probe.json"
    if not refresh and cache.exists():
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except ValueError:
            pass
    if not python().exists():
        return {"error": "not installed"}
    proc = subprocess.run([str(python()), "-I", str(WORKER), "probe"], capture_output=True, text=True, env=env(),
                          timeout=300, encoding="utf-8", errors="replace")
    info = next((json.loads(line[1:]) for line in proc.stdout.splitlines() if line.startswith("§")), None)
    info = info or {"error": (proc.stderr or proc.stdout)[-500:]}
    info.pop("kind", None)
    cache.write_text(json.dumps(info), encoding="utf-8")
    return info


def status() -> dict:
    free = shutil.disk_usage(PROJECT_ROOT).free / 2**30
    used = sum(f.stat().st_size for f in MODELS.rglob("*") if f.is_file()) / 2**30 if MODELS.exists() else 0.0
    return {"installed": installed(), "installing": state["installing"], "error": state["error"],
            "log": state["log"][-40:], "gpu": probe() if installed() else None,
            "disk_free_gb": round(free, 1), "models_gb": round(used, 1), "engine": str(ENGINE)}


def _say(line: str) -> None:
    state["log"].append(line.rstrip()[:400])
    del state["log"][:-300]
    log.info("[ai engine] %s", line.rstrip())


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    _say("$ " + " ".join(str(c) for c in cmd))
    proc = subprocess.Popen([str(c) for c in cmd], cwd=cwd, env=env(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace")
    for line in proc.stdout:
        if line.strip():
            _say(line)
    if proc.wait() != 0:
        raise RuntimeError(f"{Path(str(cmd[0])).name} {cmd[1] if len(cmd) > 1 else ''} failed (exit {proc.returncode})")


def _uv() -> str:
    found = shutil.which("uv")
    if found:
        return found
    _run([sys.executable, "-m", "pip", "install", "-q", "uv"])
    exe = Path(sys.executable).parent / ("uv.exe" if WINDOWS else "uv")
    return str(exe) if exe.exists() else "uv"


def install() -> bool:
    """Start setting up the engine in the background; False if it is already running."""
    with _lock:
        if state["installing"]:
            return False
        state.update(installing=True, error="", done=False, log=[])
    threading.Thread(target=_install, daemon=True).start()
    return True


def _install() -> None:
    try:
        if not shutil.which("git"):
            raise RuntimeError("Git isn't installed: get it from https://git-scm.com and try again")
        TOOLS.mkdir(parents=True, exist_ok=True)
        if not (ENGINE / ".git").exists():
            _say("Downloading ACE-Step 1.5 (the music model's code)...")
            _run(["git", "clone", "--depth", "1", ACE_REPO, str(ENGINE)])
        else:
            _run(["git", "-C", str(ENGINE), "pull", "--ff-only"])
        uv = _uv()
        _say("Installing PyTorch for your graphics card and the AI libraries (several GB, 10-30 minutes)...")
        _run([uv, "sync"], cwd=ENGINE)
        _run([uv, "pip", "install", "--python", str(python()), *EXTRA], cwd=ENGINE)
        info = probe(refresh=True)
        if info.get("error"):
            raise RuntimeError(f"The engine installed but didn't start: {info['error']}")
        _say(f"Graphics card: {info.get('name') or 'none found (the CPU would be far too slow)'}"
             + (f", {info.get('vram_gb')} GB" if info.get("cuda") else ""))
        (ENGINE / ".reel-installed").write_text(time.strftime("%Y-%m-%d %H:%M"), encoding="utf-8")
        state["done"] = True
        _say("Done. The models download the first time a video uses them.")
    except Exception as exc:  # noqa: BLE001 - shown in the app
        state["error"] = str(exc)
        _say(f"ERROR: {exc}")
    finally:
        state["installing"] = False


# ---------- running a worker stage ----------

def run_stage(stage: str, job: dict, work: Path, progress: Progress, label: str) -> None:
    """Run one worker stage to the end. Stop or Pause kills it at once; finished items stay on disk."""
    if not installed():
        raise RuntimeError("The AI engine isn't installed yet: open the Anim tab and press 'Install the AI engine'")
    job = {**job, "hf_home": str(MODELS / "hf"), "calibration": str(CALIBRATION)}
    jobfile = work / f"ai-{stage}.json"
    jobfile.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
    kw: dict = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if WINDOWS else {"start_new_session": True}  # type: ignore[attr-defined]
    proc = subprocess.Popen([str(python()), "-I", str(WORKER), stage, str(jobfile)], env=env(), cwd=work,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                            errors="replace", **kw)
    lines: queue.Queue = queue.Queue()
    eof = object()

    def read() -> None:
        for x in proc.stdout:
            lines.put(x)
        lines.put(eof)

    threading.Thread(target=read, daemon=True).start()
    error, tail, started, times = "", [], time.time(), []
    while True:
        try:
            line = lines.get(timeout=1)
        except queue.Empty:
            line = None
        if line is eof:
            break
        if line is None:
            if stopper.stop_requested() or stopper.pause_requested():
                stopper._kill(proc)
                raise stopper.Stopped() if stopper.stop_requested() else stopper.Paused()
            continue
        if not line.startswith("§"):
            if line.strip():
                tail = (tail + [line.rstrip()])[-25:]
            continue
        try:
            msg = json.loads(line[1:])
        except ValueError:
            continue
        kind = msg.get("kind")
        if kind == "item":
            times.append(float(msg.get("secs") or 0))
            n, of = int(msg["n"]), int(msg["of"])
            each = sum(times[-8:]) / len(times[-8:])
            left = (of - n) * each
            progress(f"{label}: {n} of {of} done · {each:.0f} s each · about "
                     + (f"{left / 3600:.1f} h left" if left > 5400 else f"{left / 60:.0f} min left"))
        elif kind == "start" and msg.get("todo"):
            progress(f"{label}: {msg['todo']} to make" + (f" ({msg['total'] - msg['todo']} already done)" if msg["total"] > msg["todo"] else ""))
        elif kind == "warn":
            progress(f"{label}: {msg.get('msg')}")
        elif kind == "error":
            error = msg.get("msg", "")
            log.error("AI worker %s failed: %s\n%s", stage, error, msg.get("trace", ""))
    if proc.wait() != 0:
        raise RuntimeError(f"{label} failed: {error or ' / '.join(tail[-3:]) or f'exit {proc.returncode}'}")
    log.info("AI stage %s finished in %.1f min", stage, (time.time() - started) / 60)
