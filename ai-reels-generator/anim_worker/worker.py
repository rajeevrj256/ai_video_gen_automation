"""The AI side of Animated videos: runs inside the AI engine's own Python (tools/ai-engine/.venv, made by
reelgen/anim_engine.py), never inside the app's. One stage per process, so each frees the graphics card
when it ends:

    python worker.py probe
    python worker.py keyframes job.json   # SDXL-Lightning pictures; IP-Adapter keeps each character's look
    python worker.py embed job.json       # LTX-Video's T5 text encoder on the CPU, once for every clip
    python worker.py clips job.json       # LTX-Video 2B distilled: each picture becomes a moving clip
    python worker.py upscale job.json     # Real-ESRGAN compact: clips and pictures sharpened to full HD
    python worker.py music job.json       # ACE-Step 1.5: new instrumental tracks

Built for small graphics cards (the user's GTX 1650 has 4 GB): models stream in layer by layer from system
memory (sequential CPU offload) and the VAE decodes in tiles. GTX 16xx cards often turn half precision into
NaNs (black pictures), so the first item of each stage checks its output (keyframes: every picture) and the
stage falls back to full precision for good (written to the calibration file the job names).

Every finished item is written next to a `.ok` file and skipped next time, so a crash, a Pause or a closed
app costs only the item in progress. Progress goes to stdout as lines starting with `@@REEL@@` (JSON). Plain
ASCII on purpose: run with -I, Python ignores PYTHONIOENCODING, and on Windows a '§' marker came out in the
console code page and was never recognised ("The engine installed but didn't start").
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


MARK = "@@REEL@@"


def say(kind: str, **data) -> None:
    print(MARK + json.dumps({"kind": kind, **data}), flush=True)  # json.dumps escapes non-ASCII


def loading(what: str, gb: float, repo: str, filename: str) -> None:
    """Say which model is loading. The first time it is a big one-off download (minutes to an hour on home
    Wi-Fi) during which nothing else moves, so say so instead of looking stuck."""
    try:
        from huggingface_hub import try_to_load_from_cache
        cached = isinstance(try_to_load_from_cache(repo, filename), str)
    except Exception:  # noqa: BLE001
        cached = False
    say("note", msg=f"Loading {what}" if cached else f"Downloading {what} ({gb:g} GB, only before the first video)...")


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


def broken_file(path: str | Path) -> bool:
    """A saved picture that is black or one flat colour (a run before every picture was checked kept them)."""
    try:
        from PIL import Image

        with Image.open(path) as im:
            im.thumbnail((256, 256))
            return broken(im)
    except Exception:  # noqa: BLE001 - unreadable: draw it again
        return True


def gtx16() -> bool:
    """A GeForce GTX 16xx (Turing without tensor cores): half precision often comes out as NaN there."""
    import torch

    if not torch.cuda.is_available():
        return False
    return torch.cuda.get_device_capability(0) == (7, 5) and "GTX 16" in torch.cuda.get_device_name(0)



# SDXL's text encoders read 77 tokens (75 words-pieces between start and end). Our prompts run 150-170 (the
# scene, then the character, then the art style), so the style and most of the character were cut off: the
# user's what-if pictures came out as ordinary cartoon people, never the round black heads the style asks for.
CHUNK = 75


def _chunks(tok, text: str, size: int = CHUNK) -> list[str]:
    """The prompt in pieces of at most `size` tokens, cut between phrases (or words, for a very long phrase)."""
    import re

    def count(t: str) -> int:
        return len(tok(t, add_special_tokens=False).input_ids)

    parts: list[str] = []
    for phrase in (x.strip() for x in re.split(r"(?<=[,.;:])\s+", text or "") if x.strip()):
        if count(phrase) <= size:
            parts.append(phrase)
            continue
        cur: list[str] = []
        for word in phrase.split():
            if cur and count(" ".join([*cur, word])) > size:
                parts.append(" ".join(cur))
                cur = []
            cur.append(word)
        if cur:
            parts.append(" ".join(cur))
    out, cur = [], []
    for part in parts:
        if cur and count(" ".join([*cur, part])) > size:
            out.append(" ".join(cur))
            cur = []
        cur.append(part)
    if cur:
        out.append(" ".join(cur))
    return out or [""]


def long_embeds(pipe, prompt: str, negative: str, guidance: float) -> dict:
    """The whole prompt as SDXL embeddings: each piece encoded on its own (with its own start and end tokens) and
    the pieces joined, as AUTOMATIC1111 does; the pooled embedding from the first piece. The negative gets as many
    pieces (blank ones added) because guidance stacks the two."""
    import torch

    cfg = guidance > 1.0
    pos = _chunks(pipe.tokenizer, prompt)
    neg = _chunks(pipe.tokenizer, negative) if cfg else []
    n = max(len(pos), len(neg))
    pos += [""] * (n - len(pos))
    neg += [""] * (n - len(neg)) if cfg else []
    device = pipe._execution_device
    pe, ne, pooled, npooled = [], [], None, None
    for i in range(n):
        e, en, p, pn = pipe.encode_prompt(prompt=pos[i], prompt_2=pos[i], device=device, num_images_per_prompt=1,
                                          do_classifier_free_guidance=cfg, negative_prompt=neg[i] if cfg else None,
                                          negative_prompt_2=neg[i] if cfg else None)
        pe.append(e)
        if cfg:
            ne.append(en)
        if i == 0:
            pooled, npooled = p, pn
    out = {"prompt_embeds": torch.cat(pe, 1), "pooled_prompt_embeds": pooled}
    if cfg:
        out.update(negative_prompt_embeds=torch.cat(ne, 1), negative_pooled_prompt_embeds=npooled)
    return out


# The character sheet goes in through IP-Adapter's style blocks only (InstantStyle: up_blocks.0.attentions.1):
# the character's look (head, colours, clothes, materials) without the sheet's pose, framing and plain grey
# background. At one scale for every block, 7 of the user's 8 what-if shots came out as the sheet again: the same
# standing figure on grey, no starting blocks, no stadium.
def ref_scale(scale: float):
    return {"up": {"block_0": [0.0, scale, 0.0]}} if scale > 0 else 0.0


def roomy() -> bool:
    """Room for the photoreal model in full precision (10.3 GB of weights in system memory, streamed through the
    card): on the user's 16 GB laptop with a 4 GB GTX 1650 it ran the card out of memory (Windows let PyTorch take
    10.4 GB of shared memory before failing) after 15 minutes."""
    import torch

    if not torch.cuda.is_available():
        return True  # the CPU computes in full precision anyway (or REEL_ANIM_DTYPE)
    vram = torch.cuda.get_device_properties(0).total_memory / 2**30
    return ram_gb() >= FP32_RAM_GB and vram >= 8


def oom(exc: BaseException) -> bool:
    import torch

    return isinstance(exc, torch.cuda.OutOfMemoryError) or "out of memory" in str(exc).lower()


def fit_vae(vae, job: dict) -> None:
    """Decode in small tiles on small cards: SDXL's decoder tiles at 1024 px by default, so a 768x1344 picture was
    decoded almost whole (gigabytes in full precision). 512 px on cards under 6 GB, 256 in the low-memory mode."""
    import torch

    vae.enable_tiling()
    small = torch.cuda.is_available() and torch.cuda.get_device_properties(0).total_memory / 2**30 < 6
    size = 256 if job.get("lowmem") else 512 if small else 0
    if size and hasattr(vae, "tile_sample_min_size"):
        vae.tile_sample_min_size, vae.tile_latent_min_size = size, size // 8


class NaNLatents(RuntimeError):
    """The picture went NaN during its steps: it would come out black."""


def nan_guard(pipe, step, timestep, kw):
    """Stop a picture at the first step whose latents aren't finite (minutes sooner than a black picture)."""
    import torch

    if not torch.isfinite(kw["latents"]).all():
        raise NaNLatents(f"step {step + 1}")
    return kw


# ---------- keyframes: SDXL-Lightning (4 steps) + IP-Adapter ----------

SDXL_BASE = "stabilityai/stable-diffusion-xl-base-1.0"
LIGHTNING = ("ByteDance/SDXL-Lightning", "sdxl_lightning_4step_unet.safetensors")
FP16_VAE = "madebyollin/sdxl-vae-fp16-fix"
# Photoreal pictures (the Divine look): a whole SDXL fine-tune distilled to 4-6 steps, openrail++. Its own advice:
# 5 steps, DPM++ SDE Karras, CFG 1-2 (so the negative prompt works).
PHOTOREAL = "SG161222/RealVisXL_V5.0_Lightning"
IP_ADAPTER = ("h94/IP-Adapter", "sdxl_models", "ip-adapter-plus_sdxl_vit-h.safetensors", "models/image_encoder")


def sdxl_pipeline(job: dict, dtype):
    import torch
    from diffusers import AutoencoderKL, EulerDiscreteScheduler, StableDiffusionXLPipeline, UNet2DConditionModel
    from huggingface_hub import hf_hub_download
    from safetensors.torch import load_file

    base = job.get("base_model") or SDXL_BASE
    if job.get("model") == "photoreal" and not job.get("tiny"):
        from diffusers import DPMSolverMultistepScheduler

        loading("the photoreal picture model (RealVisXL Lightning)", 6.9, PHOTOREAL, "unet/diffusion_pytorch_model.fp16.safetensors")
        kw = {"vae": AutoencoderKL.from_pretrained(FP16_VAE, torch_dtype=dtype)} if dtype == torch.float16 else {}
        pipe = StableDiffusionXLPipeline.from_pretrained(PHOTOREAL, torch_dtype=dtype, variant="fp16", **kw)
        pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config, algorithm_type="sde-dpmsolver++",
                                                                 use_karras_sigmas=True)
        fit_vae(pipe.vae, job)
        place(pipe, job)
        return pipe, False
    if job.get("tiny"):  # tests: a tiny random SDXL, no Lightning weights
        pipe = StableDiffusionXLPipeline.from_pretrained(base, torch_dtype=dtype)
    else:
        from accelerate import init_empty_weights

        loading("the picture model (SDXL-Lightning)", 5.1, *LIGHTNING)
        loading("SDXL's text encoders", 1.8, base, "text_encoder_2/model.fp16.safetensors")
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
            loading("IP-Adapter (keeps the characters the same)", 3.4, repo, f"{encoder}/model.safetensors")
            pipe.load_ip_adapter(repo, subfolder=sub, weight_name=weight, image_encoder_folder=encoder)
            ip = True
        except Exception as exc:  # noqa: BLE001 - pictures still work, characters just drift more
            say("warn", msg=f"IP-Adapter didn't load ({exc}); characters are kept by description only")
    fit_vae(pipe.vae, job)
    place(pipe, job)
    return pipe, ip


REF_SCALE = 0.75  # the style blocks only (ref_scale); the whole-model 0.6 copied the sheet's layout
PLAIN = {"model": None, "guidance": 0.0, "steps": 4, "ip_adapter": False}  # SDXL-Lightning's own settings


def keyframes(job: dict) -> None:
    """Every picture is checked as it is drawn. Black (NaN) output on this card goes down a ladder, each step
    remembered in the calibration file: half precision -> full precision -> (the photoreal model only) the
    SDXL-Lightning model that this card already drew with. A black picture is never saved: a run that kept
    the first check's 'ok' for a new model saved 7 black pictures on the user's GTX 1650 and Claude's picture
    check then spent 420k tokens and an hour redrawing them black."""
    import torch
    from diffusers import StableDiffusionXLImg2ImgPipeline
    from PIL import Image

    cal = calibration(job)
    if job.get("model") == "photoreal" and not job.get("tiny") and (
            cal.get("photoreal_broken") or (cal.get("photoreal_fp32") and not roomy() and not job.get("dtype"))):
        say("note", msg="The photoreal model can't draw on this card (black pictures in half precision, too big in "
                        "full): drawing with SDXL-Lightning")
        job = {**job, **PLAIN}
    if cal.get("keyframes_lowmem"):
        job = {**job, "lowmem": True}
    stage = "photoreal" if job.get("model") == "photoreal" else "sdxl"
    items = [*job.get("characters", []), *job.get("shots", [])]
    todo = [it for it in items if not done(it["out"]) or broken_file(it["out"])]
    say("start", stage="keyframes", total=len(items), todo=len(todo))
    if not todo:
        return
    # Lets GTX 16xx cards run half precision they otherwise turn into NaNs (AUTOMATIC1111 #4407); not in the
    # low-memory mode (its trial runs can take large work buffers)
    torch.backends.cudnn.benchmark = gtx16() and not job.get("lowmem")
    dtype = pick_dtype(job, stage)
    pipe, ip = sdxl_pipeline(job, dtype)
    i2i = StableDiffusionXLImg2ImgPipeline.from_pipe(pipe, torch_dtype=dtype)  # else diffusers casts the shared model to fp32: twice the memory
    W, H = job.get("width", 1024), job.get("height", 576)
    steps = job.get("steps", 4)
    blank = Image.new("RGB", (224, 224), (128, 128, 128))
    inpaint = None  # made the first time an item has a mask (Journey)
    black, short = "", False
    n = 0
    for it in todo:
        t0 = time.time()
        g = torch.Generator("cpu").manual_seed(int(it.get("seed", 0)))
        guidance = float(job.get("guidance", 0.0))
        ref = it.get("ref")
        init = it.get("init")
        try:
            common = dict(**long_embeds(pipe, it["prompt"], job.get("negative", ""), guidance),
                          guidance_scale=guidance, generator=g, callback_on_step_end=nan_guard)
            if ip:
                # Each shot takes the look of its main character from that character's sheet (scale 0 = no one).
                pipe.set_ip_adapter_scale(ref_scale(float(it.get("ref_scale", REF_SCALE)) if ref and Path(ref).exists() else 0.0))
                common["ip_adapter_image"] = Image.open(ref).convert("RGB") if ref and Path(ref).exists() else blank
            if init and Path(init).exists() and not broken_file(init):  # the same place as the shot before
                strength = float(it.get("strength", 0.6))
                image = i2i(image=Image.open(init).convert("RGB").resize((W, H)), strength=strength,
                            num_inference_steps=max(steps, math.ceil(steps / strength)), **common).images[0]
                # 🌱 Journey: the light changed over the whole frame (above, gently), then each part drawn anew inside
                # its mask while the rest stays as it is: the weather (a storm sky, wet sand) and the subject (a
                # sprout, a young palm), each with its own words
                passes = list(it.get("passes") or [])
                if it.get("mask"):
                    passes.append({"mask": it["mask"], "strength": it.get("mask_strength", 0.95)})
                for ps in passes:
                    if not Path(ps["mask"]).exists():
                        continue
                    if inpaint is None:
                        from diffusers import StableDiffusionXLInpaintPipeline
                        inpaint = StableDiffusionXLInpaintPipeline.from_pipe(pipe, torch_dtype=dtype)
                    ms = float(ps.get("strength", 0.95))
                    words = common if not ps.get("prompt") else {
                        **common, **long_embeds(pipe, ps["prompt"], job.get("negative", ""), guidance)}
                    image = inpaint(image=image, mask_image=Image.open(ps["mask"]).convert("L").resize((W, H)), width=W,
                                    height=H, strength=ms, num_inference_steps=max(steps, math.ceil(steps / ms)),
                                    **words).images[0]
            else:
                image = pipe(width=W, height=H, num_inference_steps=steps, **common).images[0]
        except NaNLatents as exc:
            black = f"went NaN at {exc}"
            break
        except (RuntimeError, MemoryError) as exc:
            if not oom(exc):
                raise
            short = True
            break
        if broken(image):
            black = "came out black"
            break
        if n == 0:
            remember(job, f"{stage}_ok", True)
        Path(it["out"]).parent.mkdir(parents=True, exist_ok=True)
        image.save(it["out"], quality=95)
        mark(it["out"])
        n += 1
        say("item", stage="keyframes", n=n, of=len(todo), id=it.get("id", ""), secs=round(time.time() - t0, 1))
    if not black and not short:
        return
    del pipe, i2i, inpaint
    common = None
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return keyframes(after_oom(job, stage) if short else after_black(job, stage, dtype, black))


def after_oom(job: dict, stage: str) -> dict:
    """The next rung for a card that ran out of memory drawing a picture: the low-memory mode (small decoder tiles,
    no cuDNN trial runs), then (the photoreal model) SDXL-Lightning, then a clear error."""
    tried = set(job.get("_tried", []))
    if not job.get("lowmem") and "lowmem" not in tried:
        say("warn", msg="The graphics card ran out of memory drawing a picture: drawing again with less memory")
        remember(job, "keyframes_lowmem", True)
        return {**job, "lowmem": True, "_tried": [*tried, "lowmem"]}
    if stage == "photoreal":
        say("warn", msg="The photoreal model doesn't fit this graphics card's memory: drawing with SDXL-Lightning instead")
        remember(job, "photoreal_broken", "memory")
        rest = {k: v for k, v in job.items() if k != "dtype"}
        return {**rest, **PLAIN, "_tried": [*tried, "photoreal-off"]}
    raise RuntimeError("The graphics card runs out of memory drawing pictures even with the least memory: close other "
                       "programs that use it (games, video editors, a browser with many tabs) and press Resume")


def after_black(job: dict, stage: str, dtype, why: str) -> dict:
    """The next rung of the ladder for a card that drew a black picture (or an error when none is left)."""
    import torch

    name = "the photoreal model" if stage == "photoreal" else "SDXL-Lightning"
    tried = set(job.get("_tried", []))
    # full precision for the photoreal model only on a machine with room for its 10 GB of weights (roomy)
    if dtype != torch.float32 and f"{stage}-fp32" not in tried and (stage != "photoreal" or roomy()):
        say("warn", msg=f"A picture {why} in half precision with {name} on this card: drawing in full precision")
        remember(job, f"{stage}_fp32", True)
        return {**job, "dtype": "fp32", "_tried": [*tried, f"{stage}-fp32"]}
    if stage == "photoreal":
        say("warn", msg=f"A picture {why} with the photoreal model on this card"
                        + (" even in full precision" if dtype == torch.float32 else "") + ": drawing with SDXL-Lightning instead")
        remember(job, "photoreal_broken", True)
        rest = {k: v for k, v in job.items() if k != "dtype"}
        return {**rest, **PLAIN, "_tried": [*tried, "photoreal-off"]}
    raise RuntimeError("The pictures come out black even in full precision on this graphics card: update the "
                       "NVIDIA driver and try again")


# ---------- clips: LTX-Video 2B distilled, image to video ----------

LTX_FILE = ("Lightricks/LTX-Video", "ltxv-2b-0.9.8-distilled.safetensors")
LTX_TEXT = "Lightricks/LTX-Video-0.9.5"  # the tokenizer (its T5 encoder is stored in fp32: 19 GB)
T5_BF16 = "city96/t5-v1_1-xxl-encoder-bf16"  # the same google/t5-v1_1-xxl encoder in bf16: 9.5 GB
LTX_PIPE = "Lightricks/LTX-Video-0.9.7-distilled"  # the condition pipeline's scheduler
DISTILLED_STEPS = [1000, 993, 987, 981, 975, 909, 725, 0.03]


def _t5(job: dict, on_card: bool):
    """The T5-XXL encoder. On a graphics card: fp16, streamed through it layer by layer (accelerate's
    cpu_offload), so a 4 GB card runs a 9.5 GB model. Without one, or if fp16 failed on this card: bf16 on the
    CPU, which is very slow on CPUs without bf16 instructions (97 s per prompt on the user's i5-10300H, with
    RAM at 95%)."""
    import torch
    from transformers import T5EncoderModel

    if job.get("text_model"):  # tests: a tiny T5 laid out like the LTX repos
        enc = T5EncoderModel.from_pretrained(job["text_model"], subfolder="text_encoder",
                                             torch_dtype=torch.float16 if on_card else torch.float32)
    elif on_card:
        keep = T5EncoderModel._keep_in_fp32_modules
        T5EncoderModel._keep_in_fp32_modules = None  # all fp16: fp32 'wo' layers would add 2 GB of system RAM;
        try:                                         # T5 clamps fp16 overflow itself and the output is checked
            enc = T5EncoderModel.from_pretrained(T5_BF16, torch_dtype=torch.float16)
        finally:
            T5EncoderModel._keep_in_fp32_modules = keep
    else:
        enc = T5EncoderModel.from_pretrained(T5_BF16, torch_dtype=torch.bfloat16)
    enc.eval()
    if on_card:
        from accelerate import cpu_offload
        cpu_offload(enc, execution_device=torch.device(job.get("_t5_device") or "cuda:0"))  # outputs come back to the CPU
    return enc


def embed(job: dict) -> None:
    """T5-XXL for every clip's prompt, saved to disk, in batches (the weights pass through the card once per
    batch, not once per prompt)."""
    import torch
    from transformers import T5TokenizerFast

    todo = [s for s in job["shots"] if not done(s["emb"])]
    say("start", stage="embed", total=len(job["shots"]), todo=len(todo))
    if not todo:
        return
    on_card = (torch.cuda.is_available() or bool(job.get("_t5_device"))) and not calibration(job).get("t5_cpu")
    if job.get("text_model"):
        tok = T5TokenizerFast.from_pretrained(job["text_model"], subfolder="tokenizer")
    else:
        loading("the text model for animation (T5-XXL" + (", streamed through the graphics card)" if on_card else
                ", on the CPU)"), 9.5, T5_BF16, "model.safetensors")
        tok = T5TokenizerFast.from_pretrained(LTX_TEXT, subfolder="tokenizer")
    enc = _t5(job, on_card)
    checked = not on_card or bool(calibration(job).get("t5_ok"))
    batch = int(job.get("batch", 8))
    n = 0
    with torch.no_grad():
        i = 0
        while i < len(todo):
            part = todo[i:i + batch]
            t0 = time.time()
            ids = tok([s["prompt"] for s in part], padding="max_length", max_length=job.get("max_tokens", 128),
                      truncation=True, return_tensors="pt")
            # The inputs go where the model computes: T5 builds its attention mask from them, and a mask left on
            # the CPU met the card's numbers ("Expected all tensors to be on the same device ... cuda:0 and cpu").
            dev = torch.device(job.get("_t5_device") or "cuda:0") if on_card else torch.device("cpu")
            try:
                out = enc(ids.input_ids.to(dev), attention_mask=ids.attention_mask.to(dev))[0].float().cpu()
            except RuntimeError as exc:  # out of memory, or anything else the card can't do: the CPU, slower
                if not on_card:
                    raise
                say("warn", msg=f"The text model failed on the graphics card ({str(exc)[:120]}); using the CPU (slower)")
                del enc
                gc.collect()
                torch.cuda.empty_cache()
                on_card, checked = False, True
                enc = _t5(job, False)
                continue  # this batch again, on the CPU
            if not checked:
                if not torch.isfinite(out).all() or float(out.std()) == 0.0:
                    say("warn", msg="The text model gave broken numbers in half precision on this card; using the CPU (slower)")
                    remember(job, "t5_cpu", True)
                    del enc
                    gc.collect()
                    torch.cuda.empty_cache()
                    on_card, checked = False, True
                    enc = _t5(job, False)
                    continue  # this batch again, on the CPU
                remember(job, "t5_ok", True)
                checked = True
            for k, s in enumerate(part):
                Path(s["emb"]).parent.mkdir(parents=True, exist_ok=True)  # clips/ doesn't exist before the first clip
                torch.save({"embeds": out[k:k + 1].clone(), "mask": ids.attention_mask[k:k + 1].clone()}, s["emb"])
                mark(s["emb"])
                n += 1
                say("item", stage="embed", n=n, of=len(todo), id=s.get("id", ""), secs=round((time.time() - t0) / len(part), 1))
            i += batch


def ltx_pipeline(job: dict, dtype, compute=None):
    import torch
    from diffusers import AutoencoderKLLTXVideo, LTXConditionPipeline, LTXVideoTransformer3DModel
    from huggingface_hub import hf_hub_download

    if job.get("tiny"):  # tests: components built in code (a function when a fallback loads them again)
        parts = job["_tiny_parts"]
        tr, vae = parts() if callable(parts) else parts
    else:
        loading("the animation model (LTX-Video 2B)", 6.3, *LTX_FILE)
        path = hf_hub_download(*LTX_FILE)
        tr = LTXVideoTransformer3DModel.from_single_file(path, torch_dtype=dtype)
        vae = AutoencoderKLLTXVideo.from_single_file(path, torch_dtype=dtype)
    from diffusers import FlowMatchEulerDiscreteScheduler

    sched = FlowMatchEulerDiscreteScheduler.from_pretrained(job.get("scheduler_repo") or LTX_PIPE, subfolder="scheduler")
    pipe = LTXConditionPipeline(scheduler=sched, vae=vae, text_encoder=None, tokenizer=None, transformer=tr)
    pipe.vae.enable_tiling()
    mode = ltx_mode(job)
    if mode == "fp8":
        # The 2B model is 3.8 GB in half precision: on a 4 GB card it was streamed in layer by layer for every one
        # of the 8 steps of every clip (288 s a clip on the user's GTX 1650). Stored in 8 bits it is 1.9 GB and
        # stays on the card; each layer is widened to `dtype` only while it computes (diffusers' layerwise
        # casting; norms stay full width). The VAE comes onto the card after it, for the decode.
        compute = compute or dtype
        tr.enable_layerwise_casting(storage_dtype=torch.float8_e4m3fn, compute_dtype=compute)
        if compute != dtype:  # what the casting leaves out (norms, embeddings, the blocks' tables) computes so too
            for t in [*tr.parameters(), *tr.buffers()]:
                if t.is_floating_point() and t.dtype != torch.float8_e4m3fn:
                    t.data = t.data.to(compute)
        if torch.cuda.is_available():
            pipe.enable_model_cpu_offload()
        else:
            pipe.to("cpu")
        lean_vae(pipe)
    else:
        place(pipe, job)
    return pipe, mode


def lean_vae(pipe) -> None:
    """Keep the VAE (encoder 1.29 GB + decoder 1.03 GB in half precision) off the card while the model computes.
    Model offload loads it to encode the picture a clip starts from and leaves it there (the chain only sends the
    model before it away): the 8 steps ran with 1.9 + 2.3 GB of weights and up to 1.4 GB of activations on the
    user's 4 GB GTX 1650, Windows lent the rest from system RAM (Task Manager: 3.7 GB dedicated + 1.6 GB shared)
    and a step took 28 s. It now leaves right after encoding, and the encoder stays off during the decode (whole
    VAE + a Fast clip's 1.2 GB of decode activations = 3.5 GB; decoder alone 2.3 GB). Measured on meta tensors."""
    import torch

    vae = pipe.vae
    encode = vae.encode  # through the offload hook, which brings the whole VAE onto the card

    def free() -> None:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def encode_and_leave(*args, **kwargs):
        out = encode(*args, **kwargs)
        vae.to("cpu")
        free()
        return out

    def decoder_alone(module, args):
        vae.encoder.to("cpu")
        free()
        dt = next(module.parameters()).dtype  # latents come in the model's precision (32 bits on some cards)
        return tuple(a.to(dt) if torch.is_tensor(a) and a.is_floating_point() else a for a in args)

    vae.encode = encode_and_leave
    vae.decoder.register_forward_pre_hook(decoder_alone)


def card_speed() -> dict:
    """How fast this card multiplies in 16 and 32 bits, at the video model's layer shape (2200 tokens x 2048 ->
    8192), and whether the memory-efficient attention kernel runs in 32 bits. GTX 16xx cards have no tensor
    cores: on the user's GTX 1650 a step of the 2B model took ~25 s in 16 bits, which is ~0.3 TFLOPS, a tenth of
    the card's 32-bit rating. A few seconds, measured at the start of every clips stage."""
    import torch
    import torch.nn.functional as F

    out = {}
    for name, dt in (("fp16", torch.float16), ("fp32", torch.float32)):
        a = torch.randn(2200, 2048, device="cuda", dtype=dt)
        b = torch.randn(2048, 8192, device="cuda", dtype=dt)
        a @ b
        torch.cuda.synchronize()
        t, n = time.time(), 0
        while n < 3 or (n < 20 and time.time() - t < 1.5):
            a @ b
            torch.cuda.synchronize()
            n += 1
        out[name] = round(2 * 2200 * 2048 * 8192 * n / (time.time() - t) / 1e12, 2)
        del a, b
    try:
        from torch.nn.attention import SDPBackend, sdpa_kernel

        q = torch.randn(1, 32, 2200, 64, device="cuda", dtype=torch.float32)
        with sdpa_kernel(SDPBackend.EFFICIENT_ATTENTION):
            F.scaled_dot_product_attention(q, q, q)
        torch.cuda.synchronize()
        out["attn32"] = True
        del q
    except Exception:  # noqa: BLE001 - no such kernel for 32 bits here: attention would take far more memory
        out["attn32"] = False
    torch.cuda.empty_cache()
    return out


def ltx_mode(job: dict) -> str:
    """fp8: weights kept on the card in 8 bits; stream: the usual offload (place). fp8 on cards too small to hold
    the model in half precision, unless this card already failed with it."""
    import torch

    forced = job.get("ltx_mode") or calibration(job).get("ltx_mode")
    if forced in ("fp8", "stream"):
        return forced
    if not torch.cuda.is_available():
        return "stream"
    vram = torch.cuda.get_device_properties(0).total_memory / 2**30
    return "fp8" if vram < 10 else "stream"


def clips(job: dict) -> None:
    import torch
    from diffusers.pipelines.ltx.pipeline_ltx_condition import LTXVideoCondition
    from diffusers.utils import export_to_video
    from PIL import Image, ImageOps

    todo = [s for s in job["shots"] if not done(s["out"])]
    say("start", stage="clips", total=len(job["shots"]), todo=len(todo))
    if not todo:
        return
    dtype = pick_dtype(job, "ltx")
    cal = calibration(job)
    W, H, fps = job.get("width", 832), job.get("height", 480), job.get("fps", 24)
    compute, speed = dtype, {}
    if torch.cuda.is_available():
        speed = card_speed()
        # 32-bit maths where this card does them clearly faster (no tensor cores): the weights stay 8 bits on the
        # card, and the efficient attention kernel keeps the activations small (without it ~2.8 GB more)
        wanted = job.get("ltx_compute") or cal.get("ltx_compute")
        if ltx_mode(job) == "fp8" and dtype == torch.float16 and wanted != "fp16" and speed["attn32"] and (
                wanted == "fp32" or speed["fp32"] > 1.3 * speed["fp16"]):
            compute = torch.float32
        frames = max(int(s.get("frames", 97)) for s in todo)
        tokens = (W // 32) * (H // 32) * ((frames - 1) // 8 + 1)
        flops = 2 * 1.92e9 * tokens + 4 * tokens ** 2 * 2048 * 28  # one step of the 2B model
        rate = speed["fp32" if compute == torch.float32 else "fp16"]
        say("note", msg=f"Card speed: {speed['fp16']} TFLOPS in 16 bits, {speed['fp32']} in 32 bits; about "
                        f"{flops / max(rate, 0.01) / 1e12:.0f} s a step expected")
    free0 = torch.cuda.mem_get_info()[0] if torch.cuda.is_available() else 0  # the card's own memory left for us
    pipe, mode = ltx_pipeline(job, dtype, compute)
    # the first clip is checked until this card has shown the setup works (black frames = broken numbers)
    fp8_ok = "ltx_fp8_ok" if compute == dtype else "ltx_fp8_32_ok"
    checked = bool(cal.get(fp8_ok)) if mode == "fp8" else bool(cal.get("ltx_ok")) or dtype == torch.float32
    if not torch.cuda.is_available():
        how = "on the CPU (very slow)"
    elif dtype == torch.float32:
        how = "full precision" + (", since half gave black frames on this card (about twice as slow)"
                                  if cal.get("ltx_fp32") else "")
    elif compute == torch.float32:
        how = "32-bit maths (faster on this card)"
    else:
        how = "half precision"
    if torch.cuda.is_available():
        how += ", model kept on the card in 8 bits" if mode == "fp8" else ", model streamed through the card"
    say("note", msg=f"{W}x{H} clips, {how}")

    def without_fp8(why: str):
        """8-bit weights failed on this card: the same stage the usual way (nothing of this run is saved yet)."""
        say("warn", msg=f"Keeping the model on the card in 8 bits didn't work ({why[:100]}); streaming it instead (slower)")
        remember(job, "ltx_mode", "stream")
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        return clips({**job, "ltx_mode": "stream"})

    def without_32(why: str):
        """32-bit maths failed (memory, a cast): 16 bits again, still 8-bit weights on the card."""
        say("warn", msg=f"32-bit maths didn't work on this card ({why[:100]}); back to 16 bits")
        remember(job, "ltx_compute", "fp16")
        gc.collect()
        torch.cuda.empty_cache()
        return clips({**job, "ltx_compute": "fp16"})

    # The first clip of a run says where the card's memory went: past what was free, Windows lends system RAM
    # without a word and every step gets several times slower (the VAE left beside the model did that).
    watch = {"on": torch.cuda.is_available(), "steps": 0, "t": 0.0}

    def at_step(p, i, t, kw):
        if watch["on"]:
            torch.cuda.synchronize()
            watch["steps"] = max(watch["steps"], torch.cuda.memory_reserved())
            watch["t"] = time.time()
        return {}
    n = 0
    for s in todo:
        t0 = time.time()
        emb = torch.load(s["emb"])
        image = ImageOps.fit(Image.open(s["image"]).convert("RGB"), (W, H), Image.LANCZOS)  # cropped, never stretched
        frames = int(s.get("frames", 97))
        frames = max(9, (frames - 1) // 8 * 8 + 1)  # LTX takes 8k+1 frames
        g = torch.Generator("cpu").manual_seed(int(s.get("seed", 0)))
        conditions = [LTXVideoCondition(image=image, frame_index=0)]
        if s.get("end") and Path(s["end"]).exists():  # 🌱 Journey: the clip ends on the next stage's picture
            end = ImageOps.fit(Image.open(s["end"]).convert("RGB"), (W, H), Image.LANCZOS)
            conditions.append(LTXVideoCondition(image=end, frame_index=frames - 1))
        if watch["on"]:
            torch.cuda.reset_peak_memory_stats()
        try:
            result = pipe(
                conditions=conditions,
                # precomputed embeddings aren't moved by the pipeline: put them where its own would be
                prompt_embeds=emb["embeds"].to(device=pipe._execution_device, dtype=compute),
                prompt_attention_mask=emb["mask"].bool().to(pipe._execution_device),
                width=W, height=H, num_frames=frames, frame_rate=fps,
                timesteps=job.get("timesteps") or DISTILLED_STEPS, guidance_scale=1.0,
                decode_timestep=0.05, decode_noise_scale=0.025, image_cond_noise_scale=0.0,
                generator=g, output_type="pil", callback_on_step_end=at_step,
            ).frames[0]
        except RuntimeError as exc:  # out of memory, or an 8-bit cast this card can't do (clips done so far stay)
            if mode != "fp8":
                raise
            del pipe
            return without_32(str(exc)) if compute != dtype else without_fp8(str(exc))
        if watch["on"]:
            watch["on"] = False
            torch.cuda.synchronize()
            gb = 2 ** 30
            top, dec = torch.cuda.max_memory_reserved(), time.time() - watch["t"]
            say("note", msg=f"Card memory: {watch['steps'] / gb:.1f} GB while animating, {top / gb:.1f} GB at the "
                            f"most, {free0 / gb:.1f} GB free; decoding the frames took {dec:.0f} s")
            if watch["steps"] > free0:
                say("warn", msg=f"The graphics card ran out of its own memory ({watch['steps'] / gb:.1f} GB needed, "
                                f"{free0 / gb:.1f} GB free), so Windows lends it system RAM and every step gets several "
                                "times slower. Close other programs that use the card"
                                + (", or choose Fast clips" if W > 640 else ""))
            elif top > free0:  # a moment over, while encoding or decoding: only that part is slower
                say("note", msg=f"Decoding went over the card's own memory for a moment ({top / gb:.1f} of {free0 / gb:.1f} GB); "
                                "the animation steps fit")
        if not checked and mode == "fp8":
            if broken(result[len(result) // 2]):
                del pipe, result
                return without_32("black frames") if compute != dtype else without_fp8("black frames")
            remember(job, fp8_ok, True)
            checked = True
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


# ---------- upscale: Real-ESRGAN compact video models, 4x, then fitted to full HD ----------

# The clips come out 640x352 / 832x480 and the pictures 1344x768; stretched to 1920x1080 by the editor they
# looked soft. These small models (BSD-3-Clause, 2.5 / 4.9 MB) restore the edges: anime for flat and inked
# styles, general for painted and 3D ones. Checksums pinned: the file is loaded as model weights.
SR_URL = "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/"
SR_MODELS = {
    "anime": ("realesr-animevideov3.pth", 16, "b8a8376811077954d82ca3fcf476f1ac3da3e8a68a4f4d71363008000a18b75d"),
    "general": ("realesr-general-x4v3.pth", 32, "8dc7edb9ac80ccdc30c3a5dca6616509367f05fbc184ad95b731f05bece96292"),
}


def _sr_net(num_conv: int):
    """SRVGGNetCompact (Real-ESRGAN): convolutions at the input size, then a 4x pixel shuffle."""
    import torch
    from torch import nn

    class Net(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            layers = [nn.Conv2d(3, 64, 3, 1, 1), nn.PReLU(64)]
            for _ in range(num_conv):
                layers += [nn.Conv2d(64, 64, 3, 1, 1), nn.PReLU(64)]
            layers.append(nn.Conv2d(64, 48, 3, 1, 1))
            self.body = nn.ModuleList(layers)
            self.up = nn.PixelShuffle(4)

        def forward(self, x):
            out = x
            for layer in self.body:
                out = layer(out)
            return self.up(out) + torch.nn.functional.interpolate(x, scale_factor=4, mode="nearest")

    return Net()


def sr_model(job: dict, name: str, device, dtype):
    import hashlib
    import urllib.request

    import torch

    file, num_conv, sha = SR_MODELS[name]
    path = Path(job.get("sr_dir") or ".") / file
    if not path.exists():
        say("note", msg=f"Downloading the upscaler ({file}, a few MB, only once)...")
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        urllib.request.urlretrieve(SR_URL + file, tmp)
        if hashlib.sha256(tmp.read_bytes()).hexdigest() != sha:
            tmp.unlink(missing_ok=True)
            raise RuntimeError(f"The upscaler download ({file}) didn't match its checksum")
        tmp.replace(path)
    net = _sr_net(num_conv)
    state = torch.load(path, map_location="cpu", weights_only=True)
    net.load_state_dict({k.replace("upsampler", "up"): v for k, v in (state.get("params") or state["params_ema"]).items()})
    return net.eval().to(device=device, dtype=dtype)


def _fit(img, W: int, H: int):
    """A (1,3,h,w) picture scaled to cover WxH and centre-cropped: the clips aren't exactly 16:9."""
    import torch.nn.functional as F

    h, w = img.shape[-2:]
    k = max(W / w, H / h)
    nh, nw = max(H, round(h * k)), max(W, round(w * k))
    img = F.interpolate(img, size=(nh, nw), mode="bicubic", antialias=True, align_corners=False)
    y, x = (nh - H) // 2, (nw - W) // 2
    return img[..., y:y + H, x:x + W]


def upscale(job: dict) -> None:
    import imageio
    import numpy as np
    import torch

    todo = [it for it in job["items"] if not done(it["out"])]
    say("start", stage="upscale", total=len(job["items"]), todo=len(todo))
    if not todo:
        return
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = pick_dtype(job, "sr")
    net = sr_model(job, job.get("model") or "general", device, dtype)
    checked = bool(calibration(job).get("sr_ok")) or dtype == torch.float32

    def sharpen(frame, W: int, H: int):
        """One RGB uint8 frame -> W x H uint8, through the model."""
        x = torch.from_numpy(np.array(frame)).to(device).permute(2, 0, 1)[None].to(dtype) / 255
        with torch.no_grad():
            y = _fit(net(x).float(), W, H).clamp_(0, 1)  # after the resize: bicubic overshoots, and a byte wraps
        return (y[0].permute(1, 2, 0) * 255).round().byte().cpu().numpy()

    n = 0
    for it in todo:
        t0 = time.time()
        W, H = int(it["w"]), int(it["h"])
        out = Path(it["out"])
        tmp = out.with_name(out.stem + ".part" + out.suffix)
        if it.get("kind") == "image":
            from PIL import Image

            first = sharpen(np.asarray(Image.open(it["src"]).convert("RGB")), W, H)
            frames = [first]
            Image.fromarray(first).save(tmp, quality=93)
        else:
            reader = imageio.get_reader(it["src"])
            fps = reader.get_meta_data().get("fps", 24)
            writer = imageio.get_writer(str(tmp), format="FFMPEG", fps=fps, codec="libx264", quality=None,
                                        pixelformat="yuv420p", macro_block_size=8,
                                        ffmpeg_params=["-crf", "17", "-preset", "medium"])
            frames = []
            try:
                for i, frame in enumerate(reader):
                    up = sharpen(frame, W, H)
                    if i == 0:
                        frames.append(up)
                    last = up
                    writer.append_data(up)
            finally:
                writer.close()
                reader.close()
            frames.append(last)
        if not checked:
            from PIL import Image

            if broken(Image.fromarray(frames[0])):
                tmp.unlink(missing_ok=True)
                if dtype == torch.float32 or job.get("_retried") or job.get("dtype"):
                    raise RuntimeError("The upscaler gives black frames even in full precision: check the graphics driver")
                say("warn", msg="Half precision gave black frames on this card; upscaling in full precision")
                remember(job, "sr_fp32", True)
                return upscale({**job, "_retried": True, "dtype": "fp32"})
            remember(job, "sr_ok", True)
            checked = True
        tmp.replace(out)
        if it.get("kind") != "image":
            from PIL import Image

            Image.fromarray(frames[-1]).save(str(out.with_suffix(".last.jpg")), quality=93)
        mark(out)
        n += 1
        say("item", stage="upscale", n=n, of=len(todo), id=it.get("id", ""), secs=round(time.time() - t0, 1))


# ---------- music: ACE-Step 1.5 (turbo, no language model: fits a 4 GB card) ----------

# ACE-Step always picks fp16 before Ampere, and on the user's GTX 1650 that gave "Generation produced NaN or
# Inf latents" on the first track. bf16 has fp32's range at the same size and made 7 of 8 one-minute tracks
# there; fp32 is the last resort, and only with room for it: the model is loaded whole into system memory before
# int8 shrinks it (~8 GB in fp32), and on the user's 16 GB laptop fp32 crashed while loading (0xC0000005).
ACE_PRECISIONS = ["auto", "bfloat16", "float32"]
FP32_RAM_GB = 24  # less system memory than this: never fp32
# ACE-Step gives up on a track after ACESTEP_GENERATION_TIMEOUT (600 s by default, read when it is imported):
# a 3-minute Stick track in bf16 on the GTX 1650 ran out. Stop still ends the worker at once.
ACE_TIMEOUT = "2400"


def ram_gb() -> float:
    """This computer's system memory, 0 when unknown."""
    try:
        if os.name == "nt":
            import ctypes

            class Status(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            st = Status()
            st.dwLength = ctypes.sizeof(Status)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
            return st.ullTotalPhys / 2**30
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30
    except (AttributeError, ValueError, OSError):
        return 0.0


def ace_ladder(ram: float) -> list[str]:
    """The precisions worth trying on this computer, narrowest first."""
    if 0 < ram < FP32_RAM_GB:
        return ACE_PRECISIONS[:-1]
    return ACE_PRECISIONS


def _ace_precision(prec: str) -> None:
    """Make ACE-Step load in `prec`. Its only switch is the ROCm one (ACESTEP_ROCM_DTYPE, read when the card
    counts as ROCm), which sets the model's and the VAE's precision together; nothing else checks that flag
    on a 7.5 card."""
    if prec == "auto":
        return
    from acestep import gpu_config
    from acestep.core.generation.handler import memory_utils

    os.environ["ACESTEP_ROCM_DTYPE"] = prec
    gpu_config.is_rocm_available = memory_utils.is_rocm_available = lambda: True


def _precision_problem(err: str) -> bool:
    import re

    return bool(re.search(r"\bnan\b|\binf\b|bfloat16|not implemented for|timed out", err, re.I))

def music(job: dict) -> None:
    import shutil

    import torch

    todo = [m for m in job["tracks"] if not done(m["out"])]
    say("start", stage="music", total=len(job["tracks"]), todo=len(todo))
    if not todo:
        return
    root = job["ace_root"]
    os.environ.setdefault("ACESTEP_GENERATION_TIMEOUT", ACE_TIMEOUT)
    sys.path.insert(0, root)
    os.chdir(root)
    from acestep.handler import AceStepHandler
    from acestep.inference import GenerationConfig, GenerationParams, generate_music
    from acestep.llm_inference import LLMHandler

    vram = torch.cuda.get_device_properties(0).total_memory / 2**30 if torch.cuda.is_available() else 0
    ladder = ace_ladder(ram_gb())
    prec = job.get("ace_dtype") or calibration(job).get("ace_dtype") or "auto"
    if prec not in ladder:  # fp32 remembered, or tried, on a computer without the memory for it
        prec = ladder[-1]
    _ace_precision(prec)
    ckpt = Path(os.environ.get("ACESTEP_CHECKPOINTS_DIR") or Path(root) / "checkpoints") / "acestep-v15-turbo"
    say("note", msg=("Loading the music model (ACE-Step" + ("" if prec == "auto" else f", {prec}") + ")") if ckpt.exists()
        else "Downloading the music model (ACE-Step, 10 GB, only before the first video)...")

    def wider(err: str):
        """This card can't run the music model in `prec`: start the stage again one step wider (the tracks
        already made are kept), and remember it for the next video."""
        if not _precision_problem(err) or prec == ladder[-1]:
            return None
        nxt = ladder[ladder.index(prec) + 1]
        names = {"auto": "half precision", "bfloat16": "bf16", "float32": "full precision (more memory, slower)"}
        say("warn", msg=f"The music didn't work in {names[prec]} on this card; trying {names[nxt]}")
        remember(job, "ace_dtype", nxt)
        return {**job, "ace_dtype": nxt}

    def again(retry: dict) -> None:
        gc.collect()  # the model just dropped leaves the card and memory before the wider one loads
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        music(retry)

    dit = AceStepHandler()
    status, ok = dit.initialize_service(
        project_root=root, config_path="acestep-v15-turbo", device="auto",
        offload_to_cpu=vram < 16, offload_dit_to_cpu=vram < 12,
        quantization="int8_weight_only" if 0 < vram < 12 else None)
    if not ok:
        retry = wider(str(status))
        if retry:
            del dit
            return again(retry)
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
        try:
            result = generate_music(dit, lm, params, config, save_dir=str(tmp))
            error = "" if result.success and result.audios else str(result.error)
        except Exception as exc:  # noqa: BLE001 - a precision the card lacks can raise instead of returning NaN
            error = f"{type(exc).__name__}: {exc}"
        if error:
            retry = wider(error)
            if retry:
                del dit, lm
                return again(retry)
            raise RuntimeError(f"ACE-Step failed on {m.get('id')}: {error}")
        shutil.move(result.audios[0]["path"], m["out"])
        shutil.rmtree(tmp, ignore_errors=True)
        mark(m["out"])
        n += 1
        say("item", stage="music", n=n, of=len(todo), id=m.get("id", ""), secs=round(time.time() - t0, 1))


# ---------- 2.5D parallax: a still picture moved like a real camera through its depth (no video model) ----------
# The user couldn't buy GPU time, and the laptop's video model makes poor motion; this gives every picture a camera
# that moves *through* it (near things slide more than far ones), computed from a small depth model on any card.

DEPTH_REPO = "depth-anything/Depth-Anything-V2-Small-hf"


def _depth_model(device):
    from transformers import AutoImageProcessor, AutoModelForDepthEstimation

    loading("the depth model", 0.1, DEPTH_REPO, "config.json")
    proc = AutoImageProcessor.from_pretrained(DEPTH_REPO)
    model = AutoModelForDepthEstimation.from_pretrained(DEPTH_REPO).to(device).eval()
    return proc, model


def _depth(proc, model, image, device):
    """0 = far .. 1 = near, the picture's size, a little dilated so a near edge never tears."""
    import torch
    import torch.nn.functional as F

    with torch.no_grad():
        inputs = {k: v.to(device) for k, v in proc(images=image, return_tensors="pt").items()}
        d = model(**inputs).predicted_depth[None]  # 1x1xh'xw', bigger = nearer
        d = F.interpolate(d.float(), size=(image.height, image.width), mode="bicubic", align_corners=False)[0, 0]
    lo, hi = torch.quantile(d.flatten()[::97], 0.02), torch.quantile(d.flatten()[::97], 0.98)
    d = ((d - lo) / (hi - lo + 1e-6)).clamp(0, 1)
    d = F.max_pool2d(d[None, None], 9, stride=1, padding=4)
    return F.avg_pool2d(d, 15, stride=1, padding=7)[0, 0]


def _move(camera: str, t: float, seed: int) -> tuple[float, float, float]:
    """(zoom, shift x, shift y) at eased time t; the shift is how far the NEAREST things move (fractions of the
    frame); far things move a quarter of it."""
    import math

    e = 0.5 - 0.5 * math.cos(math.pi * t)
    side = 1 if seed % 2 else -1
    return {
        "push-in": (1 + 0.16 * e, 0.0, -0.01 * e), "pull-out": (1.16 - 0.16 * e, 0.0, 0.0),
        "pan-left": (1.04, 0.07 * e, 0.0), "pan-right": (1.04, -0.07 * e, 0.0),
        "tilt-up": (1.04, 0.0, 0.06 * e), "tilt-down": (1.04, 0.0, -0.06 * e),
        "orbit": (1 + 0.06 * e, side * 0.09 * e, -0.01 * e),
        "handheld": (1.03 + 0.03 * e, 0.012 * math.sin(6.3 * t + seed), 0.01 * math.sin(4.1 * t + seed * 2)),
    }.get(camera, (1 + 0.08 * e, side * 0.03 * e, 0.0))


def parallax(job: dict) -> None:
    import imageio
    import numpy as np
    import torch
    import torch.nn.functional as F
    from PIL import Image

    todo = [s for s in job["shots"] if not done(s["out"])]
    say("start", stage="parallax", total=len(job["shots"]), todo=len(todo))
    if not todo:
        return
    device = "cuda" if torch.cuda.is_available() else "cpu"
    proc, model = _depth_model(device)
    W, H, fps = int(job["width"]), int(job["height"]), int(job.get("fps", 24))
    over = 1.10  # the frame is drawn from a slightly bigger picture, so no edge ever shows
    n = 0
    for s in todo:
        t0 = time.time()
        src = Image.open(s["image"]).convert("RGB")
        depth = _depth(proc, model, src, device)
        img = torch.from_numpy(np.asarray(src)).to(device).permute(2, 0, 1)[None].float() / 255
        # cover-fit both to the output's shape (crop, never stretch)
        sw, sh = src.size
        scale = max(W / sw, H / sh)
        nw, nh = round(sw * scale), round(sh * scale)
        img = F.interpolate(img, size=(nh, nw), mode="bicubic", align_corners=False).clamp(0, 1)
        dep = F.interpolate(depth[None, None], size=(nh, nw), mode="bilinear", align_corners=False)
        top, left = (nh - H) // 2, (nw - W) // 2
        img, dep = img[..., top:top + H, left:left + W], dep[..., top:top + H, left:left + W]
        ys, xs = torch.meshgrid(torch.linspace(-1, 1, H, device=device), torch.linspace(-1, 1, W, device=device), indexing="ij")
        frames = max(2, int(s["frames"]))
        out = Path(s["out"])
        tmp = out.with_suffix(".tmp.mp4")
        writer = imageio.get_writer(str(tmp), format="FFMPEG", fps=fps, codec="libx264", quality=None,
                                    pixelformat="yuv420p", macro_block_size=8, ffmpeg_params=["-crf", "17", "-preset", "medium"])
        d = dep[0, 0]
        last = None
        try:
            for i in range(frames):
                z, dx, dy = _move(s.get("camera", ""), i / (frames - 1), int(s.get("seed", 0)))
                k = 0.25 + 0.75 * d  # far moves a quarter as much as near
                zoom = over * (1 + (z - 1) * k)
                gx = xs / zoom - 2 * dx * k
                gy = ys / zoom - 2 * dy * k
                grid = torch.stack([gx, gy], -1)[None]
                y = F.grid_sample(img, grid, mode="bilinear", padding_mode="border", align_corners=False)
                last = (y[0].permute(1, 2, 0).clamp(0, 1) * 255).round().byte().cpu().numpy()
                writer.append_data(last)
        finally:
            writer.close()
        tmp.replace(out)
        Image.fromarray(last).save(str(out.with_suffix(".last.jpg")), quality=93)
        mark(out)
        n += 1
        say("item", stage="parallax", n=n, of=len(todo), id=s.get("id", ""), secs=round(time.time() - t0, 1))


STAGES = {"keyframes": keyframes, "embed": embed, "clips": clips, "upscale": upscale, "music": music, "parallax": parallax}


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # library messages with non-ASCII must not crash a cp1252 pipe
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
