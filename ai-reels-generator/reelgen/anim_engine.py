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
`@@REEL@@` lines into progress, and kills it when the job is stopped or paused (finished items are kept).
"""

from __future__ import annotations

import json
import logging
import os
import queue
import re
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
MARK = "@@REEL@@"  # anim_worker/worker.py prefixes its JSON progress lines with this

state: dict = {"installing": False, "log": [], "error": "", "done": False}
_lock = threading.Lock()
_gpu = threading.Lock()  # one AI stage on the graphics card at a time (two would not fit in 4 GB)


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
            cached = json.loads(cache.read_text(encoding="utf-8"))
            if not cached.get("error"):
                return cached
        except ValueError:
            pass
    if not python().exists():
        return {"error": "not installed"}
    proc = subprocess.run([str(python()), "-I", str(WORKER), "probe"], capture_output=True, text=True, env=env(),
                          timeout=300, encoding="utf-8", errors="replace")
    info = next((json.loads(line.split(MARK, 1)[1]) for line in proc.stdout.splitlines() if MARK in line), None)
    if not info:
        return {"error": (proc.stderr or proc.stdout)[-500:]}
    info.pop("kind", None)
    if not info.get("error"):
        cache.write_text(json.dumps(info), encoding="utf-8")
    return info


def status() -> dict:
    if python().exists() and not installed() and not state["installing"]:
        # Everything installed but the last check failed (an older version misread the worker's answer on
        # Windows): if the engine answers now, it is installed; no need to download it all again.
        info = probe()
        if not info.get("error"):
            (ENGINE / ".reel-installed").write_text(time.strftime("%Y-%m-%d %H:%M"), encoding="utf-8")
            state["error"] = ""
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

class WorkerCrashed(RuntimeError):
    """The worker process ended without a Python error of its own: a crash inside the AI libraries or the
    graphics driver, or the system ending it (out of memory)."""

    def __init__(self, msg: str, why: str) -> None:
        super().__init__(msg)
        self.why = why


# Windows exit codes of a process that crashed (NTSTATUS); Python's own errors exit 1 after telling us.
CRASHES = {
    0xC0000005: "a crash inside the AI libraries (access violation)",
    0xC0000409: "a crash inside the AI libraries or the graphics driver",
    0xC00000FD: "a stack overflow",
    0xC0000017: "out of memory",
    0xC000012D: "out of memory (Windows ran out of RAM and page file)",
    0xC0000374: "memory corruption inside the AI libraries",
    0xC000001D: "an instruction this processor doesn't have",
}


def crash_reason(code: int) -> str:
    if code < 0 and not WINDOWS:  # a signal
        return "ended by the system, usually for lack of memory" if -code == 9 else f"signal {-code}"
    c = code & 0xFFFFFFFF
    if c in CRASHES:
        return f"{CRASHES[c]}, code 0x{c:08X}"
    return f"crashed, code 0x{c:08X}" if c >= 0xC0000000 else f"exit code {code}"


class EngineBusy(RuntimeError):
    """The graphics card is busy with another video's AI step for longer than the caller wants to wait."""


def run_stage(stage: str, job: dict, work: Path, progress: Progress, label: str, wait: float | None = None) -> None:
    """Run one worker stage to the end. Stop or Pause kills it at once; finished items stay on disk. A worker
    that crashes is started again for what's left while each run finishes something (the music model once died
    on the last of 8 tracks with no error of its own, and the 7 made were thrown away). `wait`: give up after that many seconds when another
    AI step holds the card (EngineBusy): a Short's music never waits hours behind an animated video's clips."""
    if not installed():
        raise RuntimeError("The AI engine isn't installed yet: open the Anim tab and press 'Install the AI engine'")
    run_on_card(stage, job, work, progress, label, wait, python(), WORKER)


def run_on_card(stage: str, job: dict, work: Path, progress: Progress, label: str, wait: float | None,
                py: Path, worker: Path) -> None:
    """`run_stage` for any engine's worker (the voice engine's too): one AI step on the graphics card at a time."""
    if not _gpu.acquire(blocking=False):
        progress(f"{label}: waiting for the graphics card (another AI step is using it)")
        waited = 0.0
        while not _gpu.acquire(timeout=1):
            waited += 1
            if stopper.stop_requested() or stopper.pause_requested():
                raise stopper.Stopped() if stopper.stop_requested() else stopper.Paused()
            if wait is not None and waited >= wait:
                raise EngineBusy("the graphics card is busy with another video's AI step")
    try:
        batch = FRESH_EVERY.get(stage)
        tracks = job.get("tracks") or []
        if batch and len(tracks) > batch:  # a fresh process every few tracks: they wear down (see FRESH_EVERY)
            todo = [t for t in tracks if not _finished({"tracks": [t]})]
            for i in range(0, len(todo), batch):
                whole = {"todo": todo, "done": len(tracks) - len(todo), "first": i == 0}
                _until_done(stage, {**job, "tracks": todo[i:i + batch]}, work, progress, label, py, worker, whole)
        else:
            _until_done(stage, job, work, progress, label, py, worker)
    finally:
        _gpu.release()


# The music model's process crashed with 0xC0000005 after a few tracks on the user's laptop, whatever the precision
# (the last of 8 tracks in bf16; after 3 and then 4 tracks of 11 in fp32, ~5 min each): every few tracks it starts
# fresh (a reload is ~1 min; a crash loses the track being made, then reloads anyway).
FRESH_EVERY = {"music": 3}


def _finished(job: dict) -> int:
    """How many of the job's outputs are finished (an output and its .ok marker)."""
    return sum(1 for key in ("characters", "shots", "tracks") for it in job.get(key) or []
               if it.get("out") and Path(it["out"]).exists() and Path(str(it["out"]) + ".ok").exists())


def _until_done(stage: str, job: dict, work: Path, progress: Progress, label: str, py: Path, worker: Path,
                whole: dict | None = None) -> None:
    """Run the stage; a worker that crashes is started again for what's left as long as each run finished
    something more. Two crashes in a row with nothing new finished: give up. `whole`: this job is one batch of
    a bigger set (its todo list, how many were done before it), so the progress lines count the whole set."""
    idle = 0
    while True:
        before = _finished(job)
        if whole:
            made = _finished({"tracks": whole["todo"]})
            job = {**job, "_shown": {"made": made, "more": len(whole["todo"]) - made - (len(job["tracks"]) - before),
                                     "first": whole["first"] and not made, "done": whole["done"]}}
        try:
            _run_stage(stage, job, work, progress, label, py, worker)
            return
        except WorkerCrashed as exc:
            idle = 0 if _finished(job) > before else idle + 1
            if idle >= 2:
                raise
            if whole:
                whole = {**whole, "first": False}
            progress(f"{label}: the AI worker stopped unexpectedly ({exc.why}); starting it again for what's left")


def _run_stage(stage: str, job: dict, work: Path, progress: Progress, label: str, py: Path | None = None,
               worker: Path | None = None) -> None:
    job = {**job, "hf_home": str(MODELS / "hf"), "calibration": str(CALIBRATION)}
    for items in (job.get("characters", []), job.get("shots", []), job.get("tracks", [])):  # every output's folder
        for it in items:
            for key in ("out", "emb"):
                if it.get(key):
                    Path(it[key]).parent.mkdir(parents=True, exist_ok=True)
    jobfile = work / f"ai-{stage}.json"
    jobfile.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
    kw: dict = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if WINDOWS else {"start_new_session": True}  # type: ignore[attr-defined]
    proc = subprocess.Popen([str(py or python()), "-I", str(worker or WORKER), stage, str(jobfile)], env=env(), cwd=work,
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
    # A live line while an item is being made (the first clip takes minutes before any time per item is known):
    # sent as "§live", which the app shows in place of the last log line without adding to the log.
    live = {"n": 0, "of": 0, "since": time.time(), "step": "", "sent": 0.0}

    def tell_live(force: bool = False) -> None:
        if not live["of"] or (not force and time.time() - live["sent"] < 4):
            return
        secs = int(time.time() - live["since"])
        progress(f"§live {label}: making {live['n'] + 1} of {live['of']}" + (f" · {live['step']}" if live["step"] else "")
                 + f" · {secs // 60}:{secs % 60:02d} so far")
        live["sent"] = time.time()

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
            tell_live()
            continue
        if MARK not in line:
            bar = re.search(r"\|\s*(\d+)/(\d+) \[[\d:]+<[\d:?]+,\s*([\d.]+)(s/it|it/s)", line)  # a tqdm progress bar
            if bar:
                rate = float(bar[3])
                per = rate if bar[4] == "s/it" else (1 / rate if rate else 0)
                live["step"] = f"step {bar[1]} of {bar[2]}" + (f" ({per:.0f} s each)" if per >= 2 else "")
                tell_live()
            elif line.strip():
                tail = (tail + [line.rstrip()])[-25:]
            continue
        try:
            msg = json.loads(line.split(MARK, 1)[1])
        except ValueError:
            continue
        kind = msg.get("kind")
        shown = job.get("_shown") or {}  # this run is one batch of a bigger set: count the whole set
        if kind == "item":
            times.append(float(msg.get("secs") or 0))
            n, of = int(msg["n"]), int(msg["of"])
            n, of = n + shown.get("made", 0), of + shown.get("made", 0) + shown.get("more", 0)
            live.update(n=n, of=of, since=time.time(), step="")
            each = sum(times[-8:]) / len(times[-8:])
            left = (of - n) * each
            progress(f"{label}: {n} of {of} done · {each:.0f} s each · about "
                     + (f"{left / 3600:.1f} h left" if left > 5400 else f"{left / 60:.0f} min left"))
        elif kind == "start" and msg.get("todo") and shown and not shown.get("first"):
            live.update(n=shown.get("made", 0), of=int(msg["todo"]) + shown.get("made", 0) + shown.get("more", 0),
                        since=time.time(), step="")
        elif kind == "start" and msg.get("todo"):
            if shown:
                msg = {**msg, "todo": int(msg["todo"]) + shown.get("more", 0),
                       "total": int(msg["todo"]) + shown.get("more", 0) + shown.get("done", 0)}
            live.update(n=0, of=int(msg["todo"]), since=time.time(), step="")
            progress(f"{label}: {msg['todo']} to make" + (f" ({msg['total'] - msg['todo']} already done)" if msg["total"] > msg["todo"] else ""))
        elif kind in ("warn", "note"):
            progress(f"{label}: {msg.get('msg')}")
        elif kind == "error":
            error = msg.get("msg", "")
            log.error("AI worker %s failed: %s\n%s", stage, error, msg.get("trace", ""))
    if proc.wait() != 0:
        if error:
            raise RuntimeError(f"{label} failed: {error}")
        # no word from the worker: say how it ended and the lines that tell why (never a library's INFO line)
        why = crash_reason(proc.returncode)
        log.error("AI worker %s ended (%s); its last output:\n%s", stage, why, "\n".join(tail))
        telling = [x for x in tail if re.search(r"error|exception|traceback|out of memory|killed|abort|fatal|denied", x, re.I)
                   and not re.search(r"\|\s*(INFO|DEBUG)\s*\|", x)]
        raise WorkerCrashed(f"{label} stopped unexpectedly ({why})" + (f": {' / '.join(telling[-2:])[-240:]}" if telling else ""),
                            why)
    log.info("AI stage %s finished in %.1f min", stage, (time.time() - started) / 60)


# ---------- trying the music model on its own (Anim tab: "Try the music model") ----------

music_test: dict = {"running": False, "log": [], "error": "", "name": "", "stop": False, "started": 0.0}
TEST_DIR = "music-tests"


def music_tests(output_dir: Path) -> list[dict]:
    """The tracks made so far, newest first (<output>/music-tests/<stamp>/track.wav + info.json)."""
    out = []
    for info in sorted((output_dir / TEST_DIR).glob("*/info.json"), reverse=True)[:12]:
        try:
            data = json.loads(info.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (info.parent / "track.wav").exists():
            out.append({**data, "name": info.parent.name})
    return out


def start_music_test(output_dir: Path, caption: str, seconds: float, bpm: int | None) -> bool:
    """Make one track in the background; False if one is being made already."""
    with _lock:
        if music_test["running"]:
            return False
        name = time.strftime("%Y%m%d-%H%M%S")
        music_test.update(running=True, log=[], error="", name=name, stop=False, started=time.time())
    threading.Thread(target=_music_test, args=(output_dir / TEST_DIR / name, caption, seconds, bpm), daemon=True).start()
    return True


def _music_test(folder: Path, caption: str, seconds: float, bpm: int | None) -> None:
    import random

    from .animated import _loudnorm

    def progress(line: str) -> None:
        live = line.startswith("§live ")  # a live line replaces the one before it instead of piling up
        log_ = music_test["log"][:-1] if live and music_test.get("live") else music_test["log"]
        music_test["log"] = (log_ + [line.replace("§live ", "", 1)])[-30:]
        music_test["live"] = live

    stop = lambda: music_test["stop"]  # noqa: E731
    stop.stop = stop  # type: ignore[attr-defined]
    stopper.set_checks(stop)
    folder.mkdir(parents=True, exist_ok=True)
    track = folder / "track.wav"
    try:
        run_stage("music", {"tracks": [{"id": "test", "out": str(track), "caption": caption, "duration": seconds,
                                        "bpm": bpm, "seed": random.randrange(2**31)}], "ace_root": str(ENGINE)},
                  folder, progress, "Music")
        _loudnorm(track)
        took = round(time.time() - music_test["started"])
        (folder / "info.json").write_text(json.dumps({"caption": caption, "seconds": seconds, "bpm": bpm, "took": took},
                                                     ensure_ascii=False), encoding="utf-8")
        progress(f"Done in {took // 60} min {took % 60} s")
    except stopper.Paused:
        music_test["error"] = "Stopped"
        shutil.rmtree(folder, ignore_errors=True)
    except Exception as exc:  # noqa: BLE001 - shown in the app
        log.exception("Music test failed")
        music_test["error"] = str(exc)
        shutil.rmtree(folder, ignore_errors=True)
    finally:
        stopper.set_checks(None)
        music_test["running"] = False
