"""The AI side of Animated videos: runs inside the AI engine's own Python (tools/ai-engine/.venv, made by
reelgen/anim_engine.py), never inside the app's. One stage per process, so each frees the graphics card
when it ends:

    python worker.py probe
    python worker.py keyframes job.json   # SDXL-Lightning pictures; IP-Adapter keeps each character's look
    python worker.py embed job.json       # LTX-Video's T5 text encoder on the CPU, once for every clip
    python worker.py clips job.json       # LTX-Video 2B distilled: each picture becomes a moving clip
    python worker.py music job.json       # ACE-Step 1.5: new instrumental tracks

Built for small graphics cards (the user's GTX 1650 has 4 GB): models stream in layer by layer from system
memory (sequential CPU offload) and the VAE decodes in tiles. GTX 16xx cards often turn half precision into
NaNs (black pictures), so the first item of each stage checks its output and the stage falls back to full
precision for good (written to the calibration file the job names).

Every finished item is written next to a `.ok` file and skipped next time, so a crash, a Pause or a closed
app costs only the item in progress. Progress goes to stdout as lines starting with `§` (JSON).
"""

from __future__ import annotations

import gc
import json
import math
import os
import sys
import time
import traceback
from pathlib import Path


def say(kind: str, **data) -> None:
    print("§" + json.dumps({"kind": kind, **data}), flush=True)


def done(path: str | Path) -> bool:
    p = Path(path)
    return p.exists() and Path(str(p) + ".ok").exists()


def mark(path: str | Path) -> None:
    Path(str(path) + ".ok").write_text("ok", encoding="utf-8")


def load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ---------- the graphics card ----------

def device_info() -> dict:
    import torch

    info = {"torch": torch.__version__, "cuda": torch.cuda.is_available(), "name": "", "vram_gb": 0.0}
    if info["cuda"]:
        p = torch.cuda.get_device_properties(0)
        info.update(name=p.name, vram_gb=round(p.total_memory / 2**30, 1), capability=f"{p.major}.{p.minor}")
    try:
        import diffusers
        info["diffusers"] = diffusers.__version__
    except Exception:  # noqa: BLE001
        pass
    return info


def calibration(job: dict) -> dict:
    try:
        return json.loads(Path(job["calibration"]).read_text(encoding="utf-8"))
    except (KeyError, OSError, ValueError):
        return {}


def remember(job: dict, key: str, value) -> None:
    if not job.get("calibration"):
        return
    cal = calibration(job)
    cal[key] = value
    Path(job["calibration"]).write_text(json.dumps(cal, indent=1), encoding="utf-8")


def pick_dtype(job: dict, stage: str):
    """fp16 unless this card already showed it can't (or the job forces a precision)."""
    import torch

    forced = job.get("dtype") or os.environ.get("REEL_ANIM_DTYPE", "")
    if not torch.cuda.is_available() and not forced:
        return torch.float32
    if forced in ("fp32", "float32"):
        return torch.float32
    if forced in ("bf16", "bfloat16"):
        return torch.bfloat16
    if forced in ("fp16", "float16"):
        return torch.float16
    return torch.float32 if calibration(job).get(f"{stage}_fp32") else torch.float16


def place(pipe, job: dict) -> None:
    """Fit the pipeline on the card: whole on a big one, model by model on a middling one, layer by layer
    on a small one (the 4 GB GTX 1650), or the CPU without a card."""
    import torch

    if not torch.cuda.is_available():
        pipe.to("cpu")
        return
    vram = torch.cuda.get_device_properties(0).total_memory / 2**30
    mode = job.get("offload") or ("none" if vram >= 20 else "model" if vram >= 10 else "sequential")
    if mode == "none":
        pipe.to("cuda")
    elif mode == "model":
        pipe.enable_model_cpu_offload()
    else:
        pipe.enable_sequential_cpu_offload()


def broken(image) -> bool:
    """A NaN run comes out black (or one flat colour)."""
    import numpy as np

    a = np.asarray(image.convert("RGB"), dtype=np.float32)
    return not np.isfinite(a).all() or a.std() < 2.0


# ---------- keyframes: SDXL-Lightning (4 steps) + IP-Adapter ----------

SDXL_BASE = "stabilityai/stable-diffusion-xl-base-1.0"
LIGHTNING = ("ByteDance/SDXL-Lightning", "sdxl_lightning_4step_unet.safetensors")
FP16_VAE = "madebyollin/sdxl-vae-fp16-fix"
IP_ADAPTER = ("h94/IP-Adapter", "sdxl_models", "ip-adapter-plus_sdxl_vit-h.safetensors", "models/image_encoder")


def sdxl_pipeline(job: dict, dtype):
    import torch
    from diffusers import AutoencoderKL, EulerDiscreteScheduler, StableDiffusionXLPipeline, UNet2DConditionModel
    from huggingface_hub import hf_hub_download
    from safetensors.torch import load_file

    base = job.get("base_model") or SDXL_BASE
    if job.get("tiny"):  # tests: a tiny random SDXL, no Lightning weights
        pipe = StableDiffusionXLPipeline.from_pretrained(base, torch_dtype=dtype)
    else:
        from accelerate import init_empty_weights

        with init_empty_weights():  # no full-precision copy in memory first: the weights go straight in
            unet = UNet2DConditionModel.from_config(UNet2DConditionModel.load_config(base, subfolder="unet"))
        unet.load_state_dict(load_file(hf_hub_download(*LIGHTNING)), assign=True)
        unet.to(dtype)
        # The fp16 files are half the download; in full precision they are simply widened. The fp16-fix VAE
        # stops SDXL's VAE from overflowing in half precision.
        kw = {"vae": AutoencoderKL.from_pretrained(FP16_VAE, torch_dtype=dtype)} if dtype == torch.float16 else {}
        pipe = StableDiffusionXLPipeline.from_pretrained(base, unet=unet, torch_dtype=dtype, variant="fp16", **kw)
    # Lightning wants "trailing" timesteps and no guidance.
    pipe.scheduler = EulerDiscreteScheduler.from_config(pipe.scheduler.config, timestep_spacing="trailing")
    ip = False
    if job.get("ip_adapter", True) and not job.get("tiny"):
        try:
            repo, sub, weight, encoder = IP_ADAPTER
            pipe.load_ip_adapter(repo, subfolder=sub, weight_name=weight, image_encoder_folder=encoder)
            ip = True
        except Exception as exc:  # noqa: BLE001 - pictures still work, characters just drift more
            say("warn", msg=f"IP-Adapter didn't load ({exc}); characters are kept by description only")
    pipe.vae.enable_tiling()
    place(pipe, job)
    return pipe, ip


def keyframes(job: dict) -> None:
    import torch
    from diffusers import StableDiffusionXLImg2ImgPipeline
    from PIL import Image

    items = [*job.get("characters", []), *job.get("shots", [])]
    todo = [it for it in items if not done(it["out"])]
    say("start", stage="keyframes", total=len(items), todo=len(todo))
    if not todo:
        return
    dtype = pick_dtype(job, "sdxl")
    pipe, ip = sdxl_pipeline(job, dtype)
    i2i = StableDiffusionXLImg2ImgPipeline.from_pipe(pipe)
    W, H = job.get("width", 1024), job.get("height", 576)
    steps = job.get("steps", 4)
    blank = Image.new("RGB", (224, 224), (128, 128, 128))
    checked = bool(calibration(job).get("sdxl_ok")) or dtype == torch.float32
    n = 0
    for it in items:
        if done(it["out"]):
            continue
        t0 = time.time()
        g = torch.Generator("cpu").manual_seed(int(it.get("seed", 0)))
        common = dict(prompt=it["prompt"], negative_prompt=job.get("negative", ""), guidance_scale=0.0, generator=g)
        ref = it.get("ref")
        if ip:
            # Each shot takes the look of its main character from that character's sheet (scale 0 = no one).
            pipe.set_ip_adapter_scale(float(it.get("ref_scale", 0.6)) if ref and Path(ref).exists() else 0.0)
            common["ip_adapter_image"] = Image.open(ref).convert("RGB") if ref and Path(ref).exists() else blank
        init = it.get("init")
        if init and Path(init).exists():  # the same place as the shot before: start from its picture
            strength = float(it.get("strength", 0.6))
            image = i2i(image=Image.open(init).convert("RGB").resize((W, H)), strength=strength,
                        num_inference_steps=max(steps, math.ceil(steps / strength)), **common).images[0]
        else:
            image = pipe(width=W, height=H, num_inference_steps=steps, **common).images[0]
        if not checked:
            if broken(image):
                if dtype == torch.float32 or job.get("_retried") or job.get("dtype"):
                    raise RuntimeError("The pictures come out black even in full precision: check the graphics driver")
                say("warn", msg="Half precision gave a black picture on this card; switching to full precision")
                remember(job, "sdxl_fp32", True)
                del pipe, i2i
                gc.collect()
                torch.cuda.empty_cache()
                return keyframes({**job, "_retried": True, "dtype": "fp32"})  # again in fp32 (nothing saved yet)
            remember(job, "sdxl_ok", True)
            checked = True
        Path(it["out"]).parent.mkdir(parents=True, exist_ok=True)
        image.save(it["out"], quality=95)
        mark(it["out"])
        n += 1
        say("item", stage="keyframes", n=n, of=len(todo), id=it.get("id", ""), secs=round(time.time() - t0, 1))


# ---------- clips: LTX-Video 2B distilled, image to video ----------

LTX_FILE = ("Lightricks/LTX-Video", "ltxv-2b-0.9.8-distilled.safetensors")
LTX_TEXT = "Lightricks/LTX-Video-0.9.5"  # the tokenizer (its T5 encoder is stored in fp32: 19 GB)
T5_BF16 = "city96/t5-v1_1-xxl-encoder-bf16"  # the same google/t5-v1_1-xxl encoder in bf16: 9.5 GB
LTX_PIPE = "Lightricks/LTX-Video-0.9.7-distilled"  # the condition pipeline's scheduler
DISTILLED_STEPS = [1000, 993, 987, 981, 975, 909, 725, 0.03]


def embed(job: dict) -> None:
    """T5-XXL for every clip's prompt, on the CPU (it needs ~10 GB, far over a small card), saved to disk."""
    import torch
    from transformers import T5EncoderModel, T5TokenizerFast

    todo = [s for s in job["shots"] if not done(s["emb"])]
    say("start", stage="embed", total=len(job["shots"]), todo=len(todo))
    if not todo:
        return
    if job.get("text_model"):  # tests: a tiny T5 laid out like the LTX repos
        tok = T5TokenizerFast.from_pretrained(job["text_model"], subfolder="tokenizer")
        enc = T5EncoderModel.from_pretrained(job["text_model"], subfolder="text_encoder")
    else:
        tok = T5TokenizerFast.from_pretrained(LTX_TEXT, subfolder="tokenizer")
        enc = T5EncoderModel.from_pretrained(T5_BF16, torch_dtype=torch.bfloat16)
    enc.eval()
    n = 0
    with torch.no_grad():
        for s in todo:
            t0 = time.time()
            ids = tok(s["prompt"], padding="max_length", max_length=job.get("max_tokens", 128), truncation=True,
                      return_tensors="pt")
            out = enc(ids.input_ids, attention_mask=ids.attention_mask)[0]
            torch.save({"embeds": out.float(), "mask": ids.attention_mask}, s["emb"])
            mark(s["emb"])
            n += 1
            say("item", stage="embed", n=n, of=len(todo), id=s.get("id", ""), secs=round(time.time() - t0, 1))


def ltx_pipeline(job: dict, dtype):
    from diffusers import AutoencoderKLLTXVideo, LTXConditionPipeline, LTXVideoTransformer3DModel
    from huggingface_hub import hf_hub_download

    if job.get("tiny"):  # tests: components built in code
        tr, vae = job["_tiny_parts"]
    else:
        path = hf_hub_download(*LTX_FILE)
        tr = LTXVideoTransformer3DModel.from_single_file(path, torch_dtype=dtype)
        vae = AutoencoderKLLTXVideo.from_single_file(path, torch_dtype=dtype)
    from diffusers import FlowMatchEulerDiscreteScheduler

    sched = FlowMatchEulerDiscreteScheduler.from_pretrained(job.get("scheduler_repo") or LTX_PIPE, subfolder="scheduler")
    pipe = LTXConditionPipeline(scheduler=sched, vae=vae, text_encoder=None, tokenizer=None, transformer=tr)
    pipe.vae.enable_tiling()
    place(pipe, job)
    return pipe


def clips(job: dict) -> None:
    import torch
    from diffusers.pipelines.ltx.pipeline_ltx_condition import LTXVideoCondition
    from diffusers.utils import export_to_video
    from PIL import Image

    todo = [s for s in job["shots"] if not done(s["out"])]
    say("start", stage="clips", total=len(job["shots"]), todo=len(todo))
    if not todo:
        return
    dtype = pick_dtype(job, "ltx")
    pipe = ltx_pipeline(job, dtype)
    W, H, fps = job.get("width", 832), job.get("height", 480), job.get("fps", 24)
    checked = bool(calibration(job).get("ltx_ok")) or dtype == torch.float32
    n = 0
    for s in todo:
        t0 = time.time()
        emb = torch.load(s["emb"])
        image = Image.open(s["image"]).convert("RGB").resize((W, H))
        frames = int(s.get("frames", 97))
        frames = max(9, (frames - 1) // 8 * 8 + 1)  # LTX takes 8k+1 frames
        g = torch.Generator("cpu").manual_seed(int(s.get("seed", 0)))
        result = pipe(
            conditions=[LTXVideoCondition(image=image, frame_index=0)],
            prompt_embeds=emb["embeds"].to(dtype), prompt_attention_mask=emb["mask"],
            width=W, height=H, num_frames=frames, frame_rate=fps,
            timesteps=job.get("timesteps") or DISTILLED_STEPS, guidance_scale=1.0,
            decode_timestep=0.05, decode_noise_scale=0.025, image_cond_noise_scale=0.0,
            generator=g, output_type="pil",
        ).frames[0]
        if not checked:
            if broken(result[len(result) // 2]):
                if dtype == torch.float32 or job.get("_retried") or job.get("dtype"):
                    raise RuntimeError("The clips come out black even in full precision: check the graphics driver")
                say("warn", msg="Half precision gave black frames on this card; switching to full precision")
                remember(job, "ltx_fp32", True)
                del pipe
                gc.collect()
                torch.cuda.empty_cache()
                return clips({**job, "_retried": True, "dtype": "fp32"})  # again in fp32 (nothing saved yet)
            remember(job, "ltx_ok", True)
            checked = True
        Path(s["out"]).parent.mkdir(parents=True, exist_ok=True)
        export_to_video(result, s["out"], fps=fps)
        result[-1].save(str(Path(s["out"]).with_suffix(".last.jpg")), quality=92)
        mark(s["out"])
        n += 1
        del result
        say("item", stage="clips", n=n, of=len(todo), id=s.get("id", ""), secs=round(time.time() - t0, 1),
            frames=frames)


# ---------- music: ACE-Step 1.5 (turbo, no language model: fits a 4 GB card) ----------

def music(job: dict) -> None:
    import shutil

    import torch

    todo = [m for m in job["tracks"] if not done(m["out"])]
    say("start", stage="music", total=len(job["tracks"]), todo=len(todo))
    if not todo:
        return
    root = job["ace_root"]
    sys.path.insert(0, root)
    os.chdir(root)
    from acestep.handler import AceStepHandler
    from acestep.inference import GenerationConfig, GenerationParams, generate_music
    from acestep.llm_inference import LLMHandler

    vram = torch.cuda.get_device_properties(0).total_memory / 2**30 if torch.cuda.is_available() else 0
    dit = AceStepHandler()
    status, ok = dit.initialize_service(
        project_root=root, config_path="acestep-v15-turbo", device="auto",
        offload_to_cpu=vram < 16, offload_dit_to_cpu=vram < 12,
        quantization="int8_weight_only" if 0 < vram < 12 else None)
    if not ok:
        raise RuntimeError(f"ACE-Step didn't start: {status}")
    lm = LLMHandler()  # not initialised: the DiT alone writes instrumentals
    n = 0
    for m in todo:
        t0 = time.time()
        params = GenerationParams(caption=m["caption"][:500], lyrics="[Instrumental]", instrumental=True,
                                  duration=float(m["duration"]), bpm=m.get("bpm"), thinking=False,
                                  use_cot_caption=False, use_cot_language=False, use_cot_metas=False,
                                  inference_steps=8, shift=3.0, seed=int(m.get("seed", -1)))
        config = GenerationConfig(batch_size=1, audio_format="wav", use_random_seed=False, seeds=[int(m.get("seed", 0))])
        tmp = Path(m["out"]).parent / "ace-tmp"
        tmp.mkdir(parents=True, exist_ok=True)
        result = generate_music(dit, lm, params, config, save_dir=str(tmp))
        if not result.success or not result.audios:
            raise RuntimeError(f"ACE-Step failed on {m.get('id')}: {result.error}")
        shutil.move(result.audios[0]["path"], m["out"])
        shutil.rmtree(tmp, ignore_errors=True)
        mark(m["out"])
        n += 1
        say("item", stage="music", n=n, of=len(todo), id=m.get("id", ""), secs=round(time.time() - t0, 1))


STAGES = {"keyframes": keyframes, "embed": embed, "clips": clips, "music": music}


def main() -> int:
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
    job = load_json(sys.argv[2])
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
