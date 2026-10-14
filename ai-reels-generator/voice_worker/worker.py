"""The voice side of Shoot videos: runs inside the voice engine's own Python (tools/voice-engine/.venv, made by
reelgen/voice_engine.py), never inside the app's. One stage per process, so each frees the graphics card when it
ends:

    python worker.py probe
    python worker.py clean job.json    # ClearerVoice MossFormer2 (48 kHz): noise, hum and room taken out, timing kept
    python worker.py speak job.json    # Chatterbox Multilingual: lines spoken in your voice, cloned from your takes
    python worker.py convert job.json  # Chatterbox VC: a recording turned into your voice

Every finished item is written next to a `.ok` file and skipped next time. Progress goes to stdout as lines
starting with `@@REEL@@` (JSON, plain ASCII: see anim_worker/worker.py), read by reelgen/anim_engine.py `_run_stage`.
On a graphics card that runs out of memory (the user's GTX 1650 has 4 GB) a stage starts again on the processor.
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from pathlib import Path

MARK = "@@REEL@@"


def say(kind: str, **data) -> None:
    print(MARK + json.dumps({"kind": kind, **data}), flush=True)


def done(path: str | Path) -> bool:
    p = Path(path)
    return p.exists() and Path(str(p) + ".ok").exists()


def mark(path: str | Path) -> None:
    Path(str(path) + ".ok").write_text("ok", encoding="utf-8")


def device(job: dict) -> str:
    import torch

    want = job.get("device") or "auto"
    return "cuda" if want in ("auto", "cuda") and torch.cuda.is_available() else "cpu"


def device_info() -> dict:
    import torch

    info = {"torch": torch.__version__, "cuda": torch.cuda.is_available(), "name": "", "vram_gb": 0.0}
    if info["cuda"]:
        p = torch.cuda.get_device_properties(0)
        info.update(name=p.name, vram_gb=round(p.total_memory / 2**30, 1))
    return info


def _items(job: dict) -> list[dict]:
    items = job.get("items") or []
    todo = [it for it in items if not done(it["out"])]
    say("start", total=len(items), todo=len(todo))
    return todo


def _on_card_or_cpu(job: dict, run) -> None:
    """Run `run(device)` on the card; out of memory there, once more on the processor (slower, always fits)."""
    import torch

    dev = device(job)
    try:
        run(dev)
    except (torch.cuda.OutOfMemoryError, RuntimeError) as exc:  # noqa: PERF203
        if dev != "cuda" or "out of memory" not in str(exc).lower():
            raise
        say("note", msg="the graphics card ran out of memory: going on with the processor (slower)")
        torch.cuda.empty_cache()
        run("cpu")


# ---------- clean: noise, hum and room taken out ----------

def clean(job: dict) -> None:
    todo = _items(job)
    if not todo:
        return
    models = Path(job["models"])
    models.mkdir(parents=True, exist_ok=True)
    os.chdir(models)  # ClearerVoice keeps its checkpoints in ./checkpoints

    def run(dev: str) -> None:
        import torch
        from clearvoice import ClearVoice

        if dev == "cpu":
            torch.cuda.is_available = lambda: False  # ClearerVoice picks the card by itself otherwise
        say("note", msg="Loading the voice cleaner (ClearerVoice MossFormer2, 48 kHz)")
        cv = ClearVoice(task="speech_enhancement", model_names=["MossFormer2_SE_48K"])
        for n, it in enumerate(todo, 1):
            if done(it["out"]):
                continue
            t = time.time()
            out = cv(input_path=it["src"], online_write=False)
            Path(it["out"]).parent.mkdir(parents=True, exist_ok=True)
            cv.write(out, output_path=it["out"])
            mark(it["out"])
            say("item", n=n, of=len(todo), secs=round(time.time() - t, 1))

    _on_card_or_cpu(job, run)


# ---------- speak: your voice, cloned ----------

def speak(job: dict) -> None:
    todo = _items(job)
    if not todo:
        return

    def run(dev: str) -> None:
        import torch
        import torchaudio
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS

        say("note", msg="Loading the voice model (Chatterbox Multilingual, 3 GB the first time)")
        tts = ChatterboxMultilingualTTS.from_pretrained(device=dev)
        tts.prepare_conditionals(job["ref"], exaggeration=float(job.get("exaggeration", 0.5)))
        for n, it in enumerate(todo, 1):
            if done(it["out"]):
                continue
            t = time.time()
            torch.manual_seed(int(it.get("seed", 1)))
            wav = tts.generate(it["text"], language_id=it.get("lang") or job.get("lang") or "en",
                               exaggeration=float(job.get("exaggeration", 0.5)), cfg_weight=float(it.get("cfg", job.get("cfg", 0.5))),
                               temperature=float(job.get("temperature", 0.7)))
            Path(it["out"]).parent.mkdir(parents=True, exist_ok=True)
            torchaudio.save(it["out"], wav.cpu(), tts.sr, encoding="PCM_S", bits_per_sample=16)
            mark(it["out"])
            say("item", n=n, of=len(todo), secs=round(time.time() - t, 1))

    _on_card_or_cpu(job, run)


# ---------- convert: a recording turned into your voice ----------

def convert(job: dict) -> None:
    todo = _items(job)
    if not todo:
        return

    def run(dev: str) -> None:
        import torchaudio
        from chatterbox.vc import ChatterboxVC

        say("note", msg="Loading the voice converter (Chatterbox VC)")
        vc = ChatterboxVC.from_pretrained(dev)
        for n, it in enumerate(todo, 1):
            if done(it["out"]):
                continue
            t = time.time()
            wav = vc.generate(it["src"], target_voice_path=job["ref"])
            Path(it["out"]).parent.mkdir(parents=True, exist_ok=True)
            torchaudio.save(it["out"], wav.cpu(), vc.sr, encoding="PCM_S", bits_per_sample=16)
            mark(it["out"])
            say("item", n=n, of=len(todo), secs=round(time.time() - t, 1))

    _on_card_or_cpu(job, run)


STAGES = {"clean": clean, "speak": speak, "convert": convert}


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    if len(sys.argv) >= 2 and sys.argv[1] == "probe":
        try:
            say("probe", **device_info())
            return 0
        except Exception as exc:  # noqa: BLE001
            say("probe", error=str(exc))
            return 1
    if len(sys.argv) < 3 or sys.argv[1] not in STAGES:
        print(__doc__)
        return 2
    job = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    if job.get("hf_home"):
        os.environ.setdefault("HF_HOME", job["hf_home"])
    try:
        STAGES[sys.argv[1]](job)
        say("end", stage=sys.argv[1])
        return 0
    except Exception as exc:  # noqa: BLE001
        say("error", stage=sys.argv[1], msg=f"{type(exc).__name__}: {exc}", trace=traceback.format_exc()[-3000:])
        return 1


if __name__ == "__main__":
    sys.exit(main())
