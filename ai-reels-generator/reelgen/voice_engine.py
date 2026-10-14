"""The voice engine behind Shoot videos: your voice cleaned and, where you skipped or said a word wrong, spoken again
in your own voice. Its own Python with PyTorch (tools/voice-engine/.venv), kept apart from the app's and from the
AI engine's (anim_engine.py): the cloning model pins library versions the music model can't share.
voice_worker/worker.py runs inside it, one stage per process, through the AI engine's runner (one AI step on the
graphics card at a time, Stop/Pause kill it, a crashed worker is started once more).

    ClearerVoice MossFormer2_SE_48K (noise, hum, room)   ~0.1 GB   Apache-2.0
    Chatterbox Multilingual + VC (your voice, 23 languages incl. Hindi)   ~3 GB   MIT (adds an inaudible watermark)
    plus PyTorch and the libraries                        ~3-5 GB

Tested on the user's own take (a Hinglish hook filmed with a phone across a room): the cleaner kept every word
(the speech checker heard 100%) and took the background 49 dB under the voice (26 before). Generative 'studio'
enhancers (Resemble Enhance, ClearerVoice's super-resolution) were tried and rejected: trained mostly on English,
they bent the Hindi words ('अव भी ने भी ने वील...'). Chatterbox speaks a short phrase badly (one word came out
as 3.6 s of other words), so missing words are cut from a whole line spoken in your voice (`wordfix`).
"""

from __future__ import annotations

import logging
import shutil
import threading
import time
from pathlib import Path
from typing import Callable

from . import anim_engine
from .anim_engine import MODELS, TOOLS, WINDOWS
from .config import PROJECT_ROOT

log = logging.getLogger(__name__)
Progress = Callable[[str], None]

ENGINE = TOOLS / "voice-engine"
WORKER = PROJECT_ROOT / "voice_worker" / "worker.py"
VOICE_MODELS = MODELS / "voice"
TORCH = ["torch==2.6.0", "torchaudio==2.6.0"]
CLONER = ["chatterbox-tts==0.1.7"]
CLEANER = "clearvoice==0.1.2"  # installed without its pins (librosa, soundfile, opencv...), which clash with the cloner's
CLEANER_NEEDS = ["yamlargparse", "rotary_embedding_torch==0.8.3", "torchinfo", "einops", "joblib", "scipy", "pydub"]

state: dict = {"installing": False, "log": [], "error": "", "done": False}
_lock = threading.Lock()


def python() -> Path:
    return ENGINE / ".venv" / ("Scripts/python.exe" if WINDOWS else "bin/python")


def installed() -> bool:
    return python().exists() and (ENGINE / ".reel-installed").exists()


def status() -> dict:
    return {"installed": installed(), "installing": state["installing"], "error": state["error"],
            "log": state["log"][-40:], "engine": str(ENGINE)}


def _say(line: str) -> None:
    state["log"].append(line.rstrip()[:400])
    del state["log"][:-300]
    log.info("[voice engine] %s", line.rstrip())


def _run(cmd: list) -> None:
    import subprocess

    _say("$ " + " ".join(str(c) for c in cmd))
    proc = subprocess.Popen([str(c) for c in cmd], env=anim_engine.env(), stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    for line in proc.stdout:
        if line.strip():
            _say(line)
    if proc.wait() != 0:
        raise RuntimeError(f"{Path(str(cmd[0])).name} {cmd[1] if len(cmd) > 1 else ''} failed (exit {proc.returncode})")


def install() -> bool:
    """Start setting up the voice engine in the background; False if it is already running."""
    with _lock:
        if state["installing"]:
            return False
        state.update(installing=True, error="", done=False, log=[])
    threading.Thread(target=_install, daemon=True).start()
    return True


def _install() -> None:
    try:
        uv = anim_engine._uv()
        ENGINE.mkdir(parents=True, exist_ok=True)
        if not python().exists():
            _run([uv, "venv", "--python", "3.11", str(ENGINE / ".venv")])
        nvidia = shutil.which("nvidia-smi") is not None
        index = "https://download.pytorch.org/whl/" + ("cu124" if nvidia else "cpu")
        _say("Installing PyTorch" + (" for your NVIDIA graphics card" if nvidia else " (no NVIDIA card found: the processor)")
             + " and the voice models' libraries (a few GB, 5-15 minutes)...")
        _run([uv, "pip", "install", "--python", str(python()), *TORCH, "--index-url", index])
        _run([uv, "pip", "install", "--python", str(python()), *CLONER])
        _run([uv, "pip", "install", "--python", str(python()), "--no-deps", CLEANER])
        _run([uv, "pip", "install", "--python", str(python()), *CLEANER_NEEDS])
        info = probe()
        if info.get("error"):
            raise RuntimeError(f"The voice engine installed but didn't start: {info['error']}")
        _say(f"Graphics card: {info.get('name') or 'none (the processor will do it, about a minute per line)'}")
        (ENGINE / ".reel-installed").write_text(time.strftime("%Y-%m-%d %H:%M"), encoding="utf-8")
        state["done"] = True
        _say("Done. The voice models (about 3 GB) download the first time a video uses them.")
    except Exception as exc:  # noqa: BLE001 - shown in the app
        state["error"] = str(exc)
        _say(f"ERROR: {exc}")
    finally:
        state["installing"] = False


def probe() -> dict:
    import json
    import subprocess

    if not python().exists():
        return {"error": "not installed"}
    proc = subprocess.run([str(python()), "-I", str(WORKER), "probe"], capture_output=True, text=True,
                          env=anim_engine.env(), timeout=300, encoding="utf-8", errors="replace")
    line = next((x for x in proc.stdout.splitlines() if anim_engine.MARK in x), "")
    return json.loads(line.split(anim_engine.MARK, 1)[1]) if line else {"error": (proc.stderr or proc.stdout)[-500:]}


def run(stage: str, job: dict, work: Path, progress: Progress, label: str, wait: float | None = None) -> None:
    """One voice stage on the graphics card (waits for another video's AI step; gives up after `wait` seconds)."""
    if not installed():
        raise RuntimeError("The voice engine isn't installed: open the Shoot tab and press 'Install the voice engine'")
    job = {**job, "models": str(VOICE_MODELS), "hf_home": str(MODELS / "hf")}
    anim_engine.run_on_card(stage, job, work, progress, label, wait, python(), WORKER)
