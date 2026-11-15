"""Language models on this computer, free (the user: "find local llms for script generation or camera move like what
claude used while generating video ... fallback llms if claude token usage completed or blocked, also option to use
another llms at the time of building video, by default use claude").

Claude stays the default. A local model answers a step only when the job picked it (the 🤖 picker's 'on this
computer' models) or when Claude can't (its usage limit, a block, no network) and Settings says to fall back
(`llm.ask`).

- The program: llama.cpp's own server (llama-server, MIT), the official release from GitHub unpacked into
  tools/llm/ (git-ignored): on Windows with an NVIDIA card the CUDA 12.4 build and NVIDIA's runtime DLLs next to it
  (`cudart-llama-bin-win-cuda-12.4-x64.zip`), else the Vulkan or CPU build; on Linux the CUDA 12.8 or CPU build;
  `REEL_LLAMA_SERVER` can point at one already on the computer. It serves the OpenAI chat API on 127.0.0.1.
- The models (`MODELS`): Qwen 3.5 (Apache-2.0, Feb 2026, text and pictures) as GGUF files from Hugging Face in
  tools/ai-models/llm/<key>/, each checked against its SHA-256 from the Hub. 9B writes best (5.3 GB + its 0.9 GB
  picture reader; on a 4 GB card part of it runs in RAM), 4B is faster (2.6 + 0.6 GB).
- `REEL_LOCAL_URL` (e.g. LM Studio's http://127.0.0.1:1234) uses a server that is already running instead.

The server starts on the first request (loading takes a minute), answers one request at a time (`-np 1`), and
stops after `IDLE` seconds unused. llama.cpp fits as many layers on the card as its free memory allows (`--fit`,
on by default). The AI engine's stages (pictures, clips, music) need the whole card: `free_card` (called before
every one of them) waits for the request in progress and stops a server that is on the card, and a server
started while an AI stage holds the card runs on the processor (`-ngl 0`).
"""
from __future__ import annotations

import atexit
import hashlib
import json
import logging
import os
import platform
import shutil
import socket
import subprocess
import tarfile
import threading
import time
import zipfile
from pathlib import Path

import requests

from . import stopper
from .config import PROJECT_ROOT

log = logging.getLogger(__name__)

ROOT = PROJECT_ROOT / "tools" / "llm"
MODEL_DIR = PROJECT_ROOT / "tools" / "ai-models" / "llm"
RELEASES = "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest"
HF = "https://huggingface.co"

MODELS = {  # key -> the Hub files; the app's model id is 'local:<key>' (config.MODELS)
    "qwen3.5-9b": {"name": "Qwen 3.5 9B", "repo": "unsloth/Qwen3.5-9B-GGUF", "file": "Qwen3.5-9B-Q4_K_M.gguf",
                   "mmproj": "mmproj-F16.gguf", "gb": 6.2, "about": "writes best; on a 4 GB card part of it runs in RAM"},
    "qwen3.5-4b": {"name": "Qwen 3.5 4B", "repo": "unsloth/Qwen3.5-4B-GGUF", "file": "Qwen3.5-4B-Q4_K_M.gguf",
                   "mmproj": "mmproj-F16.gguf", "gb": 3.2, "about": "faster, fits a 4 GB card; simpler writing"},
}
PREFER = ["qwen3.5-9b", "qwen3.5-4b"]  # the fallback uses the first one installed
CTX = int(os.environ.get("REEL_LOCAL_CTX", "32768") or 32768)  # tokens the server holds (prompt + answer)
CTX_MAX = int(os.environ.get("REEL_LOCAL_CTX_MAX", "131072") or 131072)  # a longer prompt restarts it this big at most
IDLE = 600  # seconds unused before the server is stopped (it holds GBs of memory)
LOAD_WAIT = 600  # seconds a model may take to load

state: dict = {"installing": False, "log": [], "error": "", "progress": ""}
_install_lock = threading.Lock()


# ---------------------------------------------------------------- what is on this computer
def binary() -> Path | None:
    own = os.environ.get("REEL_LLAMA_SERVER", "").strip()
    if own and Path(own).exists():
        return Path(own)
    if not ROOT.exists():
        return None
    for name in ("llama-server.exe", "llama-server"):
        found = sorted(ROOT.rglob(name))
        if found:
            return found[0]
    return None


def model_files(key: str) -> tuple[Path, Path] | None:
    m = MODELS.get(key)
    if not m:
        return None
    folder = MODEL_DIR / key
    gguf, mmproj = folder / m["file"], folder / m["mmproj"]
    return (gguf, mmproj) if gguf.exists() and mmproj.exists() else None


def external() -> str:
    """A server the user runs themselves (LM Studio, Ollama's OpenAI API, their own llama-server)."""
    return os.environ.get("REEL_LOCAL_URL", "").strip().rstrip("/").removesuffix("/v1")


def installed(key: str) -> bool:
    return bool(external()) or (binary() is not None and model_files(key) is not None)


def installed_models() -> list[str]:
    return [k for k in PREFER if installed(k)]


def model_id(key: str) -> str:
    return f"local:{key}"


def key_of(model: str) -> str:
    return model.split(":", 1)[1] if model.startswith("local:") else model


def name_of(model: str) -> str:
    m = MODELS.get(key_of(model))
    return f"{m['name']} on this computer" if m else model


def fallback_model() -> str | None:
    """The model a step goes to when Claude can't answer: Settings 'When Claude can't answer' (REEL_LLM_FALLBACK:
    local = the chosen or best installed local model, wait = wait for Claude as before)."""
    if os.environ.get("REEL_LLM_FALLBACK", "local").strip().lower() != "local":
        return None
    want = key_of(os.environ.get("REEL_LOCAL_MODEL", "").strip())
    if want in MODELS and installed(want):
        return model_id(want)
    have = installed_models()
    return model_id(have[0]) if have else None


def status() -> dict:
    exe = binary()
    run = _server
    return {
        "server": bool(exe) or bool(external()), "external": external(), "binary": str(exe) if exe else "",
        "models": {k: {**{x: m[x] for x in ("name", "gb", "about")}, "installed": installed(k)} for k, m in MODELS.items()},
        "installing": state["installing"], "log": state["log"][-10:], "error": state["error"], "progress": state["progress"],
        "running": (run.key if run and run.alive() else ""), "on_card": bool(run and run.alive() and run.gpu),
        "fallback": fallback_model() or "", "supported": bool(_package_patterns()),
    }


# ---------------------------------------------------------------- installing
def _say(line: str) -> None:
    log.info("Local model: %s", line)
    state["log"].append(line)
    del state["log"][:-40]


def _nvidia() -> bool:
    try:
        return subprocess.run(["nvidia-smi", "-L"], capture_output=True, timeout=20).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _package_patterns() -> list[tuple[str, str | None]]:
    """The release files to fetch, best first: (the build, NVIDIA's runtime files to put next to it or None)."""
    system, machine = platform.system(), platform.machine().lower()
    x64 = machine in ("amd64", "x86_64")
    if system == "Windows" and x64:
        cuda = [("-bin-win-cuda-12.4-x64.zip", "cudart-llama-bin-win-cuda-12.4-x64.zip")] if _nvidia() else []
        return cuda + [("-bin-win-vulkan-x64.zip", None), ("-bin-win-cpu-x64.zip", None)]
    if system == "Linux" and x64:
        cuda = [("-bin-ubuntu-cuda-12.8-x64.tar.gz", "cudart-llama-{tag}-bin-ubuntu-cuda-12.8-x64.tar.gz")] if _nvidia() else []
        return cuda + [("-bin-ubuntu-x64.tar.gz", None)]
    if system == "Darwin":
        return [("-bin-macos-arm64.tar.gz" if machine == "arm64" else "-bin-macos-x64.tar.gz", None)]
    return []


def install(keys: list[str]) -> bool:
    """Start installing the program (if missing) and these models in the background; False if already running."""
    keys = [k for k in keys if k in MODELS]
    with _install_lock:
        if state["installing"]:
            return False
        state.update(installing=True, error="", log=[], progress="")
    threading.Thread(target=_install, args=(keys,), daemon=True).start()
    return True


def _install(keys: list[str]) -> None:
    try:
        if not binary() and not external():
            _install_server()
        for key in keys:
            if model_files(key):
                _say(f"{MODELS[key]['name']} is already here")
                continue
            _install_model(key)
        _say("Ready" + (f": {', '.join(MODELS[k]['name'] for k in keys)}" if keys else ""))
    except Exception as exc:  # noqa: BLE001 - shown in Settings
        state["error"] = str(exc)
        _say(f"Failed: {exc}")
    finally:
        state.update(installing=False, progress="")


def _download(url: str, dest: Path, want_sha: str = "", size: int = 0, label: str = "") -> None:
    """A large file with resume (a '.part' file grows until done) and an optional SHA-256 check."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    have = part.stat().st_size if part.exists() else 0
    free = shutil.disk_usage(dest.parent).free
    if size and free < (size - have) * 1.05:
        raise RuntimeError(f"Not enough disk space for {label or dest.name}: {size / 2**30:.1f} GB needed, "
                           f"{free / 2**30:.1f} GB free")
    headers = {"Range": f"bytes={have}-"} if have else {}
    with requests.get(url, stream=True, timeout=60, headers=headers) as r:
        if r.status_code == 416:  # already whole
            pass
        else:
            r.raise_for_status()
            if have and r.status_code != 206:
                have = 0  # the server sent the whole file again
            total = have + int(r.headers.get("content-length") or 0)
            shown = time.time()
            with open(part, "ab" if have else "wb") as fh:
                for chunk in r.iter_content(1 << 20):
                    stopper.check()
                    fh.write(chunk)
                    have += len(chunk)
                    if time.time() - shown > 3:
                        shown = time.time()
                        state["progress"] = f"{label or dest.name}: {have / 2**30:.2f} of {total / 2**30:.2f} GB" if total else ""
    if want_sha:
        _say(f"Checking {label or dest.name}")
        h = hashlib.sha256()
        with open(part, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 22), b""):
                h.update(chunk)
        if h.hexdigest() != want_sha.lower():
            part.unlink(missing_ok=True)
            raise RuntimeError(f"{label or dest.name} didn't match its checksum on Hugging Face; try again")
    os.replace(part, dest)


def _install_server() -> None:
    patterns = _package_patterns()
    if not patterns:
        raise RuntimeError("No llama.cpp build for this computer; install llama-server yourself and set REEL_LLAMA_SERVER")
    _say("Finding the latest llama.cpp release (MIT) on GitHub")
    rel = requests.get(RELEASES, timeout=60, headers={"Accept": "application/vnd.github+json"})
    rel.raise_for_status()
    rel = rel.json()
    tag, assets = rel["tag_name"], {a["name"]: a for a in rel.get("assets", [])}
    for suffix, runtime in patterns:
        main = next((a for n, a in assets.items() if n.startswith("llama-") and n.endswith(suffix)), None)
        extra = assets.get((runtime or "").format(tag=tag)) if runtime else None
        if main and (extra or not runtime):
            break
    else:
        raise RuntimeError(f"llama.cpp {tag} has no build for this computer ({', '.join(p for p, _ in patterns)})")
    tmp = ROOT.parent / "llm-unpack"
    shutil.rmtree(tmp, ignore_errors=True)
    for asset in [main] + ([extra] if extra else []):
        _say(f"Downloading {asset['name']} ({asset['size'] / 2**20:.0f} MB)")
        file = ROOT.parent / asset["name"]
        _download(asset["browser_download_url"], file, (asset.get("digest") or "").removeprefix("sha256:"), asset["size"], asset["name"])
        _say(f"Unpacking {asset['name']}")
        tmp.mkdir(parents=True, exist_ok=True)
        if asset["name"].endswith(".zip"):
            with zipfile.ZipFile(file) as z:
                z.extractall(tmp)
        else:
            with tarfile.open(file) as t:
                t.extractall(tmp, filter="data")
        file.unlink(missing_ok=True)
    # every file next to llama-server (the runtime DLLs/libraries have to sit beside it)
    found = sorted(tmp.rglob("llama-server.exe")) or sorted(tmp.rglob("llama-server"))
    if not found:
        raise RuntimeError("llama-server wasn't in the release download")
    home = found[0].parent
    for f in list(tmp.rglob("*")):
        if f.is_file() and f.parent != home and (f.suffix.lower() in (".dll", ".so") or ".so." in f.name):
            shutil.copy2(f, home / f.name)
    shutil.rmtree(ROOT, ignore_errors=True)
    if home == tmp:
        tmp.rename(ROOT)
    else:
        home.rename(ROOT)
        shutil.rmtree(tmp, ignore_errors=True)
    exe = binary()
    if not exe:
        raise RuntimeError("llama-server unpacked but wasn't found")
    exe.chmod(exe.stat().st_mode | 0o111)
    (ROOT / "release.txt").write_text(f"{tag} {main['name']}\n", encoding="utf-8")
    _say(f"llama.cpp {tag} is ready ({'CUDA' if 'cuda' in main['name'] else 'Vulkan' if 'vulkan' in main['name'] else 'CPU'})")


def _hub_files(repo: str) -> dict:
    r = requests.get(f"{HF}/api/models/{repo}/tree/main", timeout=60)
    r.raise_for_status()
    return {e["path"]: e for e in r.json() if e.get("type") == "file"}


def _install_model(key: str) -> None:
    m = MODELS[key]
    files = _hub_files(m["repo"])
    for name in (m["mmproj"], m["file"]):
        e = files.get(name)
        if not e:
            raise RuntimeError(f"{name} isn't in {m['repo']} any more")
        lfs = e.get("lfs") or {}
        _say(f"Downloading {m['name']}: {name} ({(lfs.get('size') or e.get('size') or 0) / 2**30:.1f} GB, Apache-2.0)")
        _download(f"{HF}/{m['repo']}/resolve/main/{name}", MODEL_DIR / key / name, lfs.get("oid", ""),
                  int(lfs.get("size") or e.get("size") or 0), f"{m['name']} {name}")
    (MODEL_DIR / key / "source.txt").write_text(f"https://huggingface.co/{m['repo']}\nApache-2.0\n", encoding="utf-8")


# ---------------------------------------------------------------- the server
class _Server:
    def __init__(self, key: str, ctx: int, gpu: bool):
        self.key, self.ctx, self.gpu = key, ctx, gpu
        self.port = _port()
        self.url = f"http://127.0.0.1:{self.port}"
        self.proc: subprocess.Popen | None = None
        self.last = time.time()

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self, progress=None) -> None:
        gguf, mmproj = model_files(self.key) or (None, None)
        exe = binary()
        if not (gguf and exe):
            raise RuntimeError(f"{MODELS[self.key]['name']} isn't installed: Settings > Local AI")
        cmd = [str(exe), "-m", str(gguf), "--mmproj", str(mmproj), "--host", "127.0.0.1", "--port", str(self.port),
               "-c", str(self.ctx), "-np", "1", "--jinja", "-fa", "auto", "--no-webui"]
        if not self.gpu:
            cmd += ["-ngl", "0", "--no-mmproj-offload"]
        logfile = ROOT / "server.log"
        logfile.parent.mkdir(parents=True, exist_ok=True)
        self.log = open(logfile, "w", encoding="utf-8", errors="replace")  # noqa: SIM115 - closed in stop()
        kw = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
        self.proc = subprocess.Popen(cmd, stdout=self.log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, **kw)
        say = progress or (lambda m: None)
        say(f"Starting {MODELS[self.key]['name']} on this computer ({'graphics card and RAM' if self.gpu else 'processor'}, "
            f"{self.ctx // 1024}k tokens of room); loading takes a minute")
        began = time.time()
        while time.time() - began < LOAD_WAIT:
            if not self.alive():
                raise RuntimeError("The local model stopped while loading: " + _tail(logfile))
            try:
                if requests.get(self.url + "/health", timeout=5).status_code == 200:
                    say(f"{MODELS[self.key]['name']} is ready ({time.time() - began:.0f} s to load)")
                    return
            except requests.RequestException:
                pass
            stopper.sleep(1)
        self.stop()
        raise RuntimeError(f"The local model didn't load in {LOAD_WAIT // 60} minutes: " + _tail(logfile))

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            stopper._kill(self.proc)
            try:
                self.proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                pass
        if getattr(self, "log", None):
            self.log.close()


def _port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _tail(path: Path, n: int = 6) -> str:
    try:
        lines = [ln for ln in path.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
    except OSError:
        return ""
    return " | ".join(lines[-n:])[-600:]


_server: _Server | None = None
_lock = threading.RLock()  # one request at a time; held while a server starts or stops
_busy = threading.Lock()  # held while a request runs (free_card waits on it)


def _card_busy() -> bool:
    try:
        from . import anim_engine
        return anim_engine._gpu.locked()
    except Exception:  # noqa: BLE001
        return False


def _ensure(key: str, need_ctx: int, progress=None) -> str:
    """The server's address for this model with room for `need_ctx` tokens, starting or restarting it."""
    global _server
    if external():
        return external()
    ctx = CTX
    while ctx < need_ctx and ctx < CTX_MAX:
        ctx *= 2
    if need_ctx > CTX_MAX:
        raise RuntimeError(f"This step needs {need_ctx:,} tokens, more than the local model is set to hold ({CTX_MAX:,}; "
                           "REEL_LOCAL_CTX_MAX)")
    with _lock:
        s = _server
        if s and s.alive() and s.key == key and s.ctx >= ctx:
            s.last = time.time()
            return s.url
        if s:
            s.stop()
        _server = _Server(key, max(ctx, s.ctx if s and s.key == key else 0), gpu=not _card_busy())
        _server.start(progress)
        _watch()
        return _server.url


def tokens(url: str, text: str) -> int:
    try:
        r = requests.post(url + "/tokenize", json={"content": text}, timeout=120)
        r.raise_for_status()
        return len(r.json().get("tokens") or [])
    except (requests.RequestException, ValueError):
        return len(text) // 3  # a generous guess


def chat(key: str, body: dict, timeout: float, progress=None, text: str = "") -> dict:
    """One OpenAI-style chat request to the local model (`text`: the request's words, to size the server's room);
    one request at a time, the others wait their turn; Stop and Pause end it (the server cancels a request when its
    connection closes)."""
    want = int(body.get("max_tokens") or 8192)
    while not _busy.acquire(timeout=1):  # another video's request is running
        stopper.check()
    try:
        with _lock:
            guess = len(text) // 3 + want + 2048
            url = _ensure(key, max(CTX, guess) if guess > CTX else CTX, progress)
            if not external() and len(text) > CTX:  # a long prompt: count it exactly, restart with more room if needed
                url = _ensure(key, tokens(url, text) + want + 1024, progress)
        return _post(url + "/v1/chat/completions", {**body, "model": key}, timeout)
    finally:
        _busy.release()
        if _server:
            _server.last = time.time()


def _post(url: str, body: dict, timeout: float) -> dict:
    result: dict = {}

    def run() -> None:
        try:
            r = requests.post(url, json=body, timeout=(30, timeout))
            if r.status_code >= 400:
                result["error"] = f"{r.status_code}: {r.text[:500]}"
            else:
                result["json"] = r.json()
        except requests.RequestException as exc:
            result["error"] = str(exc)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    began = time.time()
    while t.is_alive():
        t.join(1)
        if stopper.stop_requested() or stopper.pause_requested():
            stop_server()  # the only way to end a request that is still writing
            raise stopper.Stopped() if stopper.stop_requested() else stopper.Paused()
        if time.time() - began > timeout + 60:
            stop_server()
            raise RuntimeError(f"The local model took longer than {timeout / 60:.0f} minutes")
    if "error" in result:
        raise RuntimeError(f"The local model failed: {result['error']}")
    return result["json"]


def stop_server() -> None:
    global _server
    with _lock:
        if _server:
            _server.stop()
            _server = None


def free_card() -> None:
    """Before an AI stage takes the graphics card: let the request in progress finish, then stop a server on it."""
    if not (_server and _server.alive() and _server.gpu):
        return
    with _busy:
        with _lock:
            if _server and _server.gpu:
                log.info("Stopping the local model to free the graphics card for an AI step")
                stop_server()


_watching = False


def _watch() -> None:
    """Stop the server after IDLE seconds unused."""
    global _watching
    if _watching:
        return
    _watching = True

    def loop() -> None:
        global _watching
        while True:
            time.sleep(15)
            s = _server
            if not (s and s.alive()):
                _watching = False
                return
            if time.time() - s.last > IDLE and not _busy.locked():
                stop_server()
                _watching = False
                return

    threading.Thread(target=loop, daemon=True).start()


atexit.register(stop_server)
