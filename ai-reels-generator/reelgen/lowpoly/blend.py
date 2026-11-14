"""The Blender look for a low-poly film (the user: a Blender low-poly diorama, "i need this level ... with free").

Three passes, each resumable (a stopped or crashed run carries on where it was):

1. Dump: the editor runs every frame without drawing an image (remotion/scripts/dump.mjs, imageFormat 'none'), and
   its Dump component posts that frame's 3D scene to a receiver here: the camera, lights, background and fog, and
   every mesh as geometry + material + world matrix. Geometries, materials and pictures are stored once each under
   blender/assets/, every frame as blender/scene/fNNNNN.json.gz.
2. Blender: blender_worker/lowpoly.py rebuilds each frame and renders it (Cycles: bounced light, soft contact
   shadows, rounded edges, depth of field; on a graphics card when there is one) to blender/frames/fNNNNN.jpg.
3. The film: the editor's usual part-by-part render with props `blend`, which draws Blender's frame in place of its
   own 3D picture and puts the words, fades, grain and vignette on top, with the soundtrack (sticky.render).

Staging, poses, cameras, vehicles and everything else stay the editor's own: Blender only renders what it built.
"""
from __future__ import annotations

import base64
import gzip
import json
import logging
import math
import os
import queue
import re
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .. import blender, stopper
from ..video import REMOTION_DIR, _concurrency

log = logging.getLogger(__name__)

DIR = "blender"
QUALITY = {  # Cycles samples per pixel (denoised) and the size Blender draws at (percent of the film's)
    "draft": (16, 50), "good": (48, 100), "best": (128, 100),
}
ENGINES = ("cycles", "eevee")  # cycles: path traced, on the graphics card or the processor; eevee: fast, needs a graphics card
DUMP_TIMEOUT = 6 * 3600  # seconds for the whole dump pass
FRAME_TIMEOUT = 1800  # seconds Blender may spend on one frame before the run is stopped


class _Receiver(BaseHTTPRequestHandler):
    root: Path

    def log_message(self, *a) -> None:  # quiet
        return

    def _cors(self) -> None:
        # the editor's page is served from another port: a plain-text POST needs no preflight, but answer one anyway
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802 - http.server's name
        m = re.match(r"^/frame/(\d+)$", self.path)
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n)
        if not m:
            self.send_response(404)
            self.end_headers()
            return
        try:
            store(self.root, int(m.group(1)), json.loads(body))
            self.send_response(200)
            self._cors()
            self.end_headers()
            self.wfile.write(b"ok")
        except Exception as exc:  # noqa: BLE001 - the page logs it and the frame is dumped again
            log.warning("Blender bridge: frame %s not stored: %s", m.group(1), exc)
            self.send_response(500)
            self._cors()
            self.end_headers()
            self.wfile.write(str(exc).encode())


def store(root: Path, frame: int, data: dict) -> None:
    """One frame's scene: its new geometries, materials and pictures kept once each, the frame itself gzipped."""
    if data.get("error"):
        raise RuntimeError(data["error"])
    for kind in ("geos", "mats", "texs"):
        folder = root / "assets" / kind[:3]
        folder.mkdir(parents=True, exist_ok=True)
        for key, rec in (data.pop(kind, None) or {}).items():
            path = folder / f"{key}.json"
            if path.exists():
                continue
            if kind == "texs":
                url = rec.pop("url", "")
                head, _, b64 = url.partition(",")
                (folder / f"{key}.png").write_bytes(base64.b64decode(b64))
            tmp = path.with_suffix(".part")
            tmp.write_text(json.dumps(rec), encoding="utf-8")
            os.replace(tmp, path)
    scene = root / "scene"
    scene.mkdir(parents=True, exist_ok=True)
    tmp = scene / f"f{frame:05d}.part"
    tmp.write_bytes(gzip.compress(json.dumps(data, separators=(",", ":")).encode(), 5))
    os.replace(tmp, scene / f"f{frame:05d}.json.gz")


def _port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def frames_of(props: dict) -> int:
    return max(1, math.ceil(float(props["duration"]) * int(props["fps"])))


def frames_needed(props: dict) -> list[int]:
    """The frames Blender draws: every frame but the closing poster's (the editor draws that one itself)."""
    fps, shots = int(props["fps"]), props.get("shots") or []
    out = []
    for f in range(frames_of(props)):
        t = f / fps
        shot = next((s for s in shots if s["start"] <= t < s["start"] + s["duration"]), shots[-1] if shots and t >= shots[0]["start"] else (shots[0] if shots else {}))
        if not shot.get("poster"):
            out.append(f)
    return out


def _missing(folder: Path, frames: list[int], ext: str) -> list[int]:
    return [f for f in frames if not (folder / f"f{f:05d}.{ext}").exists()]


def _ranges(frames: list[int]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for f in frames:
        if out and out[-1][1] == f - 1:
            out[-1] = (out[-1][0], f)
        else:
            out.append((f, f))
    return out


def dump(props: dict, work: Path, progress, composition: str = "LowPoly") -> None:
    """Pass 1: every frame's scene, from the editor. Frames already dumped are skipped."""
    root = work / DIR
    total = frames_of(props)
    need = frames_needed(props)
    todo = _missing(root / "scene", need, "json.gz")
    if not todo:
        return
    handler = type("Receiver", (_Receiver,), {"root": root})
    port = _port()
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        for attempt in range(2):
            for first, last in _ranges(todo):
                job = root / "dump-job.json"
                root.mkdir(parents=True, exist_ok=True)
                job.write_text(json.dumps({"composition": composition, "props": {**props, "silent": True, "dump": {"url": f"http://127.0.0.1:{port}"}},
                                           "publicDir": str(work), "frames": [first, last], "concurrency": max(1, _concurrency() // 2)}),
                               encoding="utf-8")
                progress(f"Blender: reading the 3D scene of frames {first + 1}-{last + 1} of {total}")
                _node(["node", "scripts/dump.mjs", str(job)], progress, "Blender: reading the scenes", DUMP_TIMEOUT)
            todo = _missing(root / "scene", need, "json.gz")
            if not todo:
                return
            progress(f"Blender: {len(todo)} frames' scenes didn't arrive; reading them again")
        raise RuntimeError(f"Blender: {len(todo)} frames' 3D scenes couldn't be read from the editor")
    finally:
        server.shutdown()


def _node(cmd: list[str], progress, label: str, timeout: float) -> None:
    proc = stopper.run(cmd, cwd=REMOTION_DIR, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                       stdin=subprocess.DEVNULL)
    if proc.returncode != 0:
        err = next((ln for ln in (proc.stderr or proc.stdout or "").splitlines() if "Error" in ln), (proc.stderr or proc.stdout or "")[-400:])
        raise RuntimeError(f"{label} failed: {err[:300]}")


def render_frames(props: dict, work: Path, progress, quality: str = "good", engine: str = "cycles") -> None:
    """Pass 2: Blender renders every dumped frame not rendered yet."""
    exe = blender.binary()
    if not exe:
        raise RuntimeError("Blender isn't installed: install it from the Low-poly tab (free, about 400 MB)")
    root = work / DIR
    need = frames_needed(props)
    total = len(need)
    out = root / "frames"
    if not _missing(out, need, "jpg"):
        return
    samples, scale = QUALITY.get(quality, QUALITY["good"])
    w, h = (1080, 1920) if props.get("vertical") else (1920, 1080)
    w, h = w * scale // 100, h * scale // 100
    engine = engine.lower() if engine.lower() in ENGINES else "cycles"
    device = os.environ.get("REEL_BLENDER_DEVICE", "GPU").upper()
    cmd = [str(exe), "-b", "--factory-startup", "-noaudio", "-P", str(blender.WORKER / "lowpoly.py"), "--",
           "--root", str(root), "--out", str(out), "--first", str(need[0]), "--last", str(need[-1]), "--width", str(w), "--height", str(h),
           "--samples", str(samples), "--engine", "EEVEE" if engine == "eevee" else "CYCLES", "--device", device]
    started, done_before = time.time(), total - len(_missing(out, need, "jpg"))
    progress(f"Blender: rendering {total - done_before} frames ({engine.title()}, {quality}, {w}x{h})")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                            stdin=subprocess.DEVNULL, **_group())
    lines: queue.Queue = queue.Queue()
    threading.Thread(target=lambda: [lines.put(ln) for ln in proc.stdout] and None or lines.put(None), daemon=True).start()  # type: ignore[union-attr]
    tail: list[str] = []
    last_say = 0.0
    try:
        while True:
            if stopper.stop_requested() or stopper.pause_requested():  # Stop or Pause: the frames done are kept
                stopper._kill(proc)
                raise stopper.Stopped() if stopper.stop_requested() else stopper.Paused()
            try:
                line = lines.get(timeout=1.0)
            except queue.Empty:
                continue
            if line is None:
                break
            line = line.rstrip()
            if not line.startswith("@@BLEND@@ "):
                tail = (tail + [line])[-30:]
                continue
            msg = json.loads(line[10:])
            if msg.get("error"):
                raise RuntimeError(f"Blender: {msg['error']}")
            if msg.get("device") and not msg.get("start"):
                progress(f"Blender: rendering on the graphics card ({msg['device']}: {', '.join(msg.get('names', []))})")
            if msg.get("cpu"):
                progress("Blender: no graphics card it can use; rendering on the processor (slower)")
            if msg.get("done") and time.time() - last_say > 15:
                last_say = time.time()
                n, todo = msg["done"], msg["todo"]
                per = (time.time() - started) / max(1, n)
                progress(f"Blender: {done_before + n} of {total} frames · {msg.get('sec', per):.0f} s a frame · about "
                         f"{max(1, round(per * (todo - n) / 60))} min left")
    finally:
        if proc.poll() is None:
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                stopper._kill(proc)
    left = _missing(out, need, "jpg")
    if left:
        raise RuntimeError(f"Blender stopped with {len(left)} frames left: " + " | ".join(tail[-4:])[-400:])


def _group() -> dict:
    """Blender in its own process group, so Stop can end it and everything it started."""
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def film_props(props: dict) -> dict:
    """The editor's props for pass 3: Blender's frames under the words, fades and grain."""
    return {**props, "blend": {"dir": f"{DIR}/frames", "ext": "jpg"}}


def run(props: dict, soundtrack: Path, work: Path, out: Path, progress, quality: str = "good", engine: str = "cycles") -> None:
    from ..sticky.render import render

    dump(props, work, progress)
    render_frames(props, work, progress, quality, engine)
    progress("Putting the words, fades and sound over Blender's frames")
    render(film_props(props), soundtrack, work, out, progress, composition="LowPoly")


def label(quality: str, engine: str) -> str:
    """How the report names it: 'Blender (Cycles, good)'."""
    return f"Blender {blender.VERSION} ({'Eevee' if engine == 'eevee' else 'Cycles'}, {quality if quality in QUALITY else 'good'})"
