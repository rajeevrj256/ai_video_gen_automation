"""Runs inside Blender (reelgen/lowpoly/blend.py starts it: blender -b --factory-startup -P this -- args): every
frame the low-poly editor dumped (remotion/src/lowpoly/Dump.tsx) rebuilt and rendered with Blender's own light.

Each frame is the editor's scene exactly: the same meshes, colours, camera, lights, depth of field. What Blender adds
is the light itself: bounced light and soft contact shadows (Cycles path tracing), slightly rounded edges on every
faceted block (the Bevel shader, Cycles only), soft sun shadows, a real depth of field, a filmic view transform and
a gentle glow on bright things. Meshes and materials are built once and shared; objects are kept in a pool and only
moved from frame to frame, so a frame costs its render, not a rebuild.

Coordinates: three.js is y-up, Blender z-up; every world matrix is turned by C (x, y, z) -> (x, -z, y). Meshes keep
three's local coordinates (the object matrix carries C), and cameras and lights look down -Z in both.

Light levels follow three.js's physically based units (r180): a directional light of intensity I = a sun of
strength I; a point or spot light of I candela = 4*pi*I watts; a rectangle of I nits = pi*w*h*I watts; ambient and
hemisphere light of I = a world of radiance I/pi (three's indirect diffuse is irradiance * albedo/pi).
"""
from __future__ import annotations

import base64
import gzip
import json
import math
import os
import shutil
import sys
import time
import zlib
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector

C = Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
BEVEL = 0.02  # metres: the rounding Cycles puts on every edge (the reference's blocks catch the light on theirs)
# = GRADES in remotion/src/lowpoly/LowPoly.tsx (selfcheck keeps them equal): the editor's film grade per light, here a
# split tone (teal shadows through Lift, warm highlights through Gain) and a touch of contrast
GRADES = {
    "night": (0.5, 0.42, 0.22), "lamp": (0.5, 0.44, 0.22), "dark": (0.46, 0.3, 0.2), "evening": (0.34, 0.4, 0.18),
    "dawn": (0.3, 0.34, 0.16), "morning": (0.22, 0.3, 0.14), "day": (0.18, 0.2, 0.12),
}
SATURATION = 1.08  # the view transform greys colours a little; the reference's are rich
BEVEL_SAMPLES = 2  # rays the Bevel shader casts per point: 6 cost a quarter of the frame, 2 look the same once denoised
LIGHT_TREE_FROM = 16  # Cycles' light tree only above this many lights: with our handful it doubled the frame time
# (measured on a park frame: 8.0 s -> 3.8 s at the same samples; the picture differs only in its grain)
FSTOP = 0.6  # f-stop = FSTOP / the editor's aperture (0.15 wide -> f/4, 0.6 close -> f/1.4): a miniature's shallow focus
# grass tufts, pebbles and flowers scattered over every green ground the camera sees (the reference's ground is full)
TUFTS_PER_M2 = 45  # near the middle of the set, where the people are
TUFT_FALLOFF = 9.0  # metres: the density halves this far out, and keeps thinning
TUFT_REACH = 40.0  # metres from the middle: no grass further than this (fog and depth of field hide it anyway)
MOST_TUFTS = 30000


def say(**kw) -> None:
    print("@@BLEND@@ " + json.dumps(kw), flush=True)


def args() -> dict:
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = {}
    for k, v in zip(a[::2], a[1::2]):
        out[k.lstrip("-")] = v
    return out


def m4(e) -> Matrix:
    """three's column-major 16 numbers as a Blender matrix."""
    return Matrix(((e[0], e[4], e[8], e[12]), (e[1], e[5], e[9], e[13]), (e[2], e[6], e[10], e[14]), (e[3], e[7], e[11], e[15])))


def b3(v) -> Vector:
    """A three.js point in Blender's axes."""
    return Vector((v[0], -v[2], v[1]))


class Builder:
    def __init__(self, root: Path, engine: str):
        self.root = root
        self.cycles = engine == "CYCLES"
        self.meshes: dict[str, bpy.types.Mesh] = {}
        self.planes: dict[str, bool] = {}
        self.mats: dict[str, bpy.types.Material] = {}
        self.images: dict[str, bpy.types.Image] = {}
        self.recs: dict[str, dict] = {}
        self.pool: dict[str, list[bpy.types.Object]] = {}
        self.lights: dict[str, list[bpy.types.Object]] = {}
        self.coll = bpy.data.collections.new("film")
        bpy.context.scene.collection.children.link(self.coll)

    # ---------------------------------------------------------------- assets
    def _asset(self, kind: str, key: str) -> dict:
        got = self.recs.get(kind + key)
        if got is None:
            got = self.recs[kind + key] = json.loads((self.root / "assets" / kind / f"{key}.json").read_text(encoding="utf-8"))
        return got

    def mesh(self, key: str, smooth: bool) -> bpy.types.Mesh:
        name = f"{key}{'s' if smooth else ''}"
        if name in self.meshes:
            return self.meshes[name]
        g = self._asset("geo", key)
        pos = np.frombuffer(base64.b64decode(g["pos"]), np.float32).reshape(-1, 3)
        if g.get("idx"):
            idx = np.frombuffer(base64.b64decode(g["idx"]), np.uint32 if g.get("idxBits") == 32 else np.uint16).astype(np.int32)
        else:
            idx = np.arange(len(pos) - len(pos) % 3, dtype=np.int32)
        idx = idx[: len(idx) - len(idx) % 3]
        me = bpy.data.meshes.new(name)
        me.vertices.add(len(pos))
        me.vertices.foreach_set("co", pos.ravel())
        me.loops.add(len(idx))
        me.loops.foreach_set("vertex_index", idx)
        me.polygons.add(len(idx) // 3)
        me.polygons.foreach_set("loop_start", np.arange(0, len(idx), 3, dtype=np.int32))
        if g.get("uv"):
            uv = np.frombuffer(base64.b64decode(g["uv"]), np.float32).reshape(-1, 2)
            layer = me.uv_layers.new(name="UV")
            layer.data.foreach_set("uv", uv[idx].ravel())
        me.update(calc_edges=True)
        if smooth:
            me.shade_smooth()
        else:
            me.shade_flat()
        me.materials.append(None)  # one slot, filled per object (the same mesh in many colours)
        self.meshes[name] = me
        self.planes[key] = bool(g.get("plane"))
        return me

    def merged(self, key: str, smooth: bool, inst_b64: str) -> bpy.types.Mesh:
        """An InstancedMesh (grass, rows of things): its instances baked into one mesh, kept by its matrices."""
        name = f"{key}i{hash(inst_b64) & 0xFFFFFFF:x}"
        if name in self.meshes:
            return self.meshes[name]
        base = self.mesh(key, smooth)
        mats = np.frombuffer(base64.b64decode(inst_b64), np.float32).reshape(-1, 4, 4)
        n = len(base.vertices)
        co = np.empty(n * 3, np.float32)
        base.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        loops = np.empty(len(base.loops), np.int32)
        base.loops.foreach_get("vertex_index", loops)
        out_co, out_idx = [], []
        for k, m in enumerate(mats):
            mt = m.T  # three stores column-major: rows of the transpose are its rows
            out_co.append(co @ mt[:3, :3].T + mt[:3, 3])
            out_idx.append(loops + k * n)
        co_all = np.concatenate(out_co).astype(np.float32)
        idx_all = np.concatenate(out_idx).astype(np.int32)
        me = bpy.data.meshes.new(name)
        me.vertices.add(len(co_all))
        me.vertices.foreach_set("co", co_all.ravel())
        me.loops.add(len(idx_all))
        me.loops.foreach_set("vertex_index", idx_all)
        me.polygons.add(len(idx_all) // 3)
        me.polygons.foreach_set("loop_start", np.arange(0, len(idx_all), 3, dtype=np.int32))
        me.update(calc_edges=True)
        me.shade_smooth() if smooth else me.shade_flat()
        me.materials.append(None)
        self.meshes[name] = me
        return me

    def image(self, key: str) -> tuple[bpy.types.Image, dict]:
        t = self._asset("tex", key)
        if key not in self.images:
            img = bpy.data.images.load(str(self.root / "assets" / "tex" / f"{key}.png"))
            img.colorspace_settings.name = "sRGB" if t.get("srgb", True) else "Non-Color"
            self.images[key] = img
        return self.images[key], t

    def material(self, key: str, plane: bool) -> bpy.types.Material:
        name = f"{key}{'p' if plane else ''}"
        if name in self.mats:
            return self.mats[name]
        r = self._asset("mat", key)
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        nt = m.node_tree
        nodes, links = nt.nodes, nt.links
        nodes.clear()
        out = nodes.new("ShaderNodeOutputMaterial")
        col = (*(r.get("color") or [1, 1, 1]), 1.0)

        def tex(tkey: str):
            img, t = self.image(tkey)
            node = nodes.new("ShaderNodeTexImage")
            node.image = img
            node.interpolation = "Linear"
            rep, off = t.get("repeat", [1, 1]), t.get("offset", [0, 0])
            if rep != [1, 1] or off != [0, 0]:
                uvn = nodes.new("ShaderNodeUVMap")
                uvn.uv_map = "UV"
                mp = nodes.new("ShaderNodeMapping")
                mp.inputs["Location"].default_value = (off[0], off[1], 0)
                mp.inputs["Scale"].default_value = (rep[0], rep[1], 1)
                links.new(uvn.outputs["UV"], mp.inputs["Vector"])
                links.new(mp.outputs["Vector"], node.inputs["Vector"])
                node.extension = "REPEAT"
            return node

        def times(color, tkey):
            """the material's colour times its picture (three multiplies them)"""
            if not tkey:
                return None
            node = tex(tkey)
            if tuple(color[:3]) == (1, 1, 1):
                return node.outputs["Color"]
            mix = nodes.new("ShaderNodeMix")
            mix.data_type = "RGBA"
            mix.blend_type = "MULTIPLY"
            mix.inputs["Factor"].default_value = 1.0
            mix.inputs[6].default_value = color
            links.new(node.outputs["Color"], mix.inputs[7])
            return mix.outputs[2]

        unlit = r.get("type") == "MeshBasicMaterial"
        if unlit:
            shader = nodes.new("ShaderNodeEmission")
            shader.inputs["Strength"].default_value = 1.0
            shader.inputs["Color"].default_value = col
            src = times(col, r.get("map"))
            if src is not None:
                links.new(src, shader.inputs["Color"])
            surf = shader.outputs[0]
        else:
            b = nodes.new("ShaderNodeBsdfPrincipled")
            b.inputs["Base Color"].default_value = col
            b.inputs["Roughness"].default_value = float(r.get("rough", 1))
            b.inputs["Metallic"].default_value = float(r.get("metal", 0))
            src = times(col, r.get("map"))
            if src is not None:
                links.new(src, b.inputs["Base Color"])
            em, ei = r.get("emissive") or [0, 0, 0], float(r.get("ei") or 0)
            if ei > 0 and (max(em) > 0 or r.get("emap")):
                b.inputs["Emission Color"].default_value = (*em, 1.0)
                b.inputs["Emission Strength"].default_value = ei
                esrc = times((*em, 1.0), r.get("emap"))
                if esrc is not None:
                    links.new(esrc, b.inputs["Emission Color"])
            if r.get("transmission"):
                b.inputs["Transmission Weight"].default_value = float(r["transmission"])
                b.inputs["IOR"].default_value = float(r.get("ior", 1.5))
            if r.get("transparent") and float(r.get("opacity", 1)) < 1:
                b.inputs["Alpha"].default_value = float(r["opacity"])
            if self.cycles and BEVEL > 0 and not r.get("transparent"):
                bev = nodes.new("ShaderNodeBevel")
                bev.samples = BEVEL_SAMPLES
                bev.inputs["Radius"].default_value = BEVEL
                links.new(bev.outputs["Normal"], b.inputs["Normal"])
            surf = b.outputs[0]
        if r.get("transparent") and float(r.get("opacity", 1)) < 1 and unlit:
            tr = nodes.new("ShaderNodeBsdfTransparent")
            mix = nodes.new("ShaderNodeMixShader")
            mix.inputs["Fac"].default_value = float(r["opacity"])
            links.new(tr.outputs[0], mix.inputs[1])
            links.new(surf, mix.inputs[2])
            surf = mix.outputs[0]
        if plane and r.get("side", 0) == 0:
            # a wall or ceiling three draws from one side only (a camera outside the room sees in through it)
            geo = nodes.new("ShaderNodeNewGeometry")
            tr = nodes.new("ShaderNodeBsdfTransparent")
            mix = nodes.new("ShaderNodeMixShader")
            links.new(geo.outputs["Backfacing"], mix.inputs["Fac"])
            links.new(surf, mix.inputs[1])
            links.new(tr.outputs[0], mix.inputs[2])
            surf = mix.outputs[0]
        links.new(surf, out.inputs["Surface"])
        if r.get("transparent") or plane:
            try:
                m.surface_render_method = "BLENDED" if r.get("transparent") else "DITHERED"
            except AttributeError:
                pass
        self.mats[name] = m
        return m

    # ---------------------------------------------------------------- a frame
    def objects(self, frame: dict) -> None:
        used: dict[str, int] = {}
        for rec in frame.get("items", []):
            g, mk, e, cast = rec
            self._place(g, mk, e, cast, used, None)
        for rec in frame.get("insts", []):
            g, mk, e, inst, cast = rec
            self._place(g, mk, e, cast, used, inst)
        for key, objs in self.pool.items():
            for k, ob in enumerate(objs):
                hide = k >= used.get(key, 0)
                if ob.hide_render != hide:
                    ob.hide_render = hide
                    ob.hide_viewport = hide

    def _place(self, g: str, mk: str, e: list, cast: int, used: dict, inst: str | None) -> None:
        r = self._asset("mat", mk)
        smooth = not r.get("flat", True) and r.get("type") != "MeshBasicMaterial"
        me = self.merged(g, smooth, inst) if inst else self.mesh(g, smooth)
        plane = self.planes.get(g, False)
        key = f"{me.name}|{mk}{'p' if plane else ''}"
        objs = self.pool.setdefault(key, [])
        k = used.get(key, 0)
        used[key] = k + 1
        if k >= len(objs):
            ob = bpy.data.objects.new(key[:60], me)
            ob.material_slots[0].link = "OBJECT"
            ob.material_slots[0].material = self.material(mk, plane)
            self.coll.objects.link(ob)
            objs.append(ob)
        ob = objs[k]
        ob.matrix_world = C @ m4(e)
        ob.visible_shadow = bool(cast)

    # ---------------------------------------------------------------- the ground's own life
    def _tuft_meshes(self) -> dict:
        """A few shapes to scatter, built once: grass tufts (3-5 bent blades), a pebble, a flower on its stem."""
        if hasattr(self, "_tufts"):
            return self._tufts
        rng = np.random.default_rng(11)
        out = {}
        for k in range(4):
            verts, faces = [], []
            for b in range(int(rng.integers(3, 6))):
                a = rng.uniform(0, 2 * math.pi)
                lean = rng.uniform(0.05, 0.35)
                h = rng.uniform(0.07, 0.17)
                w = rng.uniform(0.012, 0.022)
                dx, dy = math.cos(a), math.sin(a)
                px, py = -dy * w, dx * w
                base = len(verts)
                verts += [(px, py, 0), (-px, -py, 0), (dx * lean * h, dy * lean * h, h)]
                faces.append((base, base + 1, base + 2))
            me = bpy.data.meshes.new(f"tuft{k}")
            me.from_pydata(verts, [], faces)
            me.update()
            out[f"tuft{k}"] = me
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.045)
        peb = bpy.context.object
        peb.scale = (1.0, 0.8, 0.5)
        bpy.ops.object.transform_apply(scale=True)
        out["pebble"] = peb.data
        bpy.data.objects.remove(peb)
        verts = [(0, 0, 0), (0.004, 0, 0), (0, 0, 0.12)]
        faces = [(0, 1, 2)]
        for i in range(5):
            a = i * 2 * math.pi / 5
            verts += [(0.02 * math.cos(a), 0.02 * math.sin(a), 0.125)]
        verts.append((0, 0, 0.13))
        c = len(verts) - 1
        for i in range(5):
            faces.append((3 + i, 3 + (i + 1) % 5, c))
        me = bpy.data.meshes.new("flower")
        me.from_pydata(verts, [], faces)
        me.update()
        out["flower"] = me
        self._tufts = out
        return out

    def _flat(self, name: str, color, rough: float = 0.9) -> bpy.types.Material:
        if name in self.mats:
            return self.mats[name]
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        b = m.node_tree.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (*color, 1)
        b.inputs["Roughness"].default_value = rough
        self.mats[name] = m
        return m

    def dress(self) -> None:
        """Grass tufts, pebbles and flowers over every green ground in the frame (worked out once per ground and
        place, so a shot's frames all get the same ones): what makes the reference's world feel full."""
        cache = getattr(self, "_dressed", None)
        if cache is None:
            cache = self._dressed = {}
        live = set()
        for key, objs in self.pool.items():
            for ob in objs:
                if ob.hide_render or not ob.material_slots or not ob.material_slots[0].material:
                    continue
                mat = ob.material_slots[0].material
                b = mat.node_tree.nodes.get("Principled BSDF") if mat.node_tree else None
                if b is None:
                    continue
                col = b.inputs["Base Color"].default_value
                if not (col[1] > col[0] * 1.1 and col[1] > col[2] * 1.05 and col[1] > 0.04):
                    continue  # grass is green
                corners = [ob.matrix_world @ Vector(v) for v in ob.bound_box]
                xs, ys, zs = [p.x for p in corners], [p.y for p in corners], [p.z for p in corners]
                area = (max(xs) - min(xs)) * (max(ys) - min(ys))
                if max(zs) - min(zs) > 0.25 or max(zs) > 0.4 or area < 3:
                    continue  # a ground: wide, flat and low
                sig = f"{ob.data.name}|{tuple(round(v, 2) for v in ob.matrix_world.translation)}"
                live.add(sig)
                if sig not in cache:
                    cache[sig] = self._scatter(ob, col, sig)
                for d in cache[sig]:
                    d.hide_render = False
        for sig, objs in cache.items():
            if sig not in live:
                for d in objs:
                    d.hide_render = True

    def _scatter(self, ground: bpy.types.Object, col, sig: str) -> list:
        """Points dropped on this ground from above, thick near the middle of the set and thinning out: a point only
        counts where the ground is the first thing hit (not under a path, a road, a bench or a tree trunk)."""
        rng = np.random.default_rng(zlib.crc32(sig.encode()))
        corners = [ground.matrix_world @ Vector(v) for v in ground.bound_box]
        x0, x1 = max(-TUFT_REACH, min(p.x for p in corners)), min(TUFT_REACH, max(p.x for p in corners))
        y0, y1 = max(-TUFT_REACH, min(p.y for p in corners)), min(TUFT_REACH, max(p.y for p in corners))
        top = max(p.z for p in corners) + 2.0
        if x1 - x0 < 1 or y1 - y0 < 1:
            return []
        n = int((x1 - x0) * (y1 - y0) * TUFTS_PER_M2)
        xs, ys = rng.uniform(x0, x1, n), rng.uniform(y0, y1, n)
        keep = rng.random(n) < 1 / (1 + (np.hypot(xs, ys) / TUFT_FALLOFF) ** 2)
        xs, ys = xs[keep][:MOST_TUFTS], ys[keep][:MOST_TUFTS]
        bpy.context.view_layer.update()  # this frame's places, for the rays
        scene = bpy.context.scene
        deps = bpy.context.evaluated_depsgraph_get()
        shapes = self._tuft_meshes()
        groups: dict[str, list] = {}
        down = Vector((0, 0, -1))
        for x, y in zip(xs, ys):
            hit, loc, nrm, _i, obj, _m = scene.ray_cast(deps, Vector((x, y, top)), down)
            if not hit or obj is None or obj.name != ground.name or nrm.z < 0.7:
                continue
            r = rng.random()
            kind = "pebble" if r < 0.06 else "flower" if r < 0.09 else f"tuft{int(rng.integers(0, 4))}"
            groups.setdefault(kind, []).append((loc, rng.uniform(0, 2 * math.pi), rng.uniform(0.7, 1.35)))
        made = []
        dark = tuple(max(0.0, x * 0.62) for x in col[:3])
        light = tuple(min(1.0, x * 1.25) for x in col[:3])
        for kind, items in groups.items():
            src = shapes[kind]
            co = np.empty(len(src.vertices) * 3, np.float32)
            src.vertices.foreach_get("co", co)
            co = co.reshape(-1, 3)
            loops = np.empty(len(src.loops), np.int32)
            src.loops.foreach_get("vertex_index", loops)
            vs, ls = [], []
            for j, (p, rot, sc) in enumerate(items):
                cr, sr = math.cos(rot), math.sin(rot)
                r = np.array([[cr, -sr, 0], [sr, cr, 0], [0, 0, 1]], np.float32) * sc
                vs.append(co @ r.T + np.array(p, np.float32))
                ls.append(loops + j * len(co))
            allv, alll = np.concatenate(vs), np.concatenate(ls)
            me2 = bpy.data.meshes.new(f"dress-{kind}")
            me2.vertices.add(len(allv))
            me2.vertices.foreach_set("co", allv.ravel())
            me2.loops.add(len(alll))
            me2.loops.foreach_set("vertex_index", alll)
            starts = np.empty(len(src.polygons), np.int32)
            src.polygons.foreach_get("loop_start", starts)
            me2.polygons.add(len(items) * len(starts))
            me2.polygons.foreach_set("loop_start", (starts[None, :] + np.arange(len(items))[:, None] * len(src.loops)).ravel().astype(np.int32))
            me2.update(calc_edges=True)
            me2.shade_flat()
            ob = bpy.data.objects.new(f"dress-{kind}", me2)
            shade = {"pebble": ("pebble", (0.32, 0.3, 0.27), 0.8), "flower": ("flower", (0.95, 0.85, 0.35), 0.6)}.get(
                kind, ("grass" + kind[-1], dark if kind[-1] in "02" else light, 0.85))
            ob.data.materials.append(self._flat(shade[0] + sig[-6:], shade[1], shade[2]))
            self.coll.objects.link(ob)
            made.append(ob)
        return made

    def _light(self, kind: str, k: int) -> bpy.types.Object:
        objs = self.lights.setdefault(kind, [])
        if k >= len(objs):
            data = bpy.data.lights.new(f"{kind}{k}", kind)
            ob = bpy.data.objects.new(f"{kind}{k}", data)
            self.coll.objects.link(ob)
            objs.append(ob)
        return objs[k]

    def lighting(self, frame: dict, world_tree) -> None:
        count: dict[str, int] = {}
        sky, ground, amb = Vector((0, 0, 0)), Vector((0, 0, 0)), Vector((0, 0, 0))
        for li in frame.get("lights", []):
            t, col, inten = li["type"], Vector(li.get("color") or (1, 1, 1)), float(li.get("intensity", 1))
            if t == "AmbientLight":
                amb += col * inten
                continue
            if t == "HemisphereLight":
                sky += col * inten
                ground += Vector(li.get("ground") or (0, 0, 0)) * inten
                continue
            kind = {"DirectionalLight": "SUN", "PointLight": "POINT", "SpotLight": "SPOT", "RectAreaLight": "AREA"}.get(t)
            if not kind:
                continue
            k = count.get(kind, 0)
            count[kind] = k + 1
            ob = self._light(kind, k)
            ob.hide_render = False
            d = ob.data
            d.color = col
            mw = C @ m4(li["m"])
            pos = mw.to_translation()
            if kind in ("SUN", "SPOT") and li.get("target"):
                direction = b3(li["target"]) - pos
                rot = direction.to_track_quat("-Z", "Y")
                ob.matrix_world = Matrix.Translation(pos) @ rot.to_matrix().to_4x4()
            else:
                ob.matrix_world = mw
            if kind == "SUN":
                d.energy = inten
                d.angle = math.radians(3.0)  # soft-edged sun shadows
            elif kind == "AREA":
                w, h = li.get("size") or (1, 1)
                d.shape = "RECTANGLE"
                d.size, d.size_y = w, h
                d.energy = math.pi * w * h * inten
            else:
                d.energy = 4 * math.pi * inten
                d.shadow_soft_size = 0.06
                if kind == "SPOT":
                    d.spot_size = min(math.pi, 2 * float(li.get("angle", 0.6)))
                    d.spot_blend = float(li.get("penumbra", 0.2))
            if hasattr(d, "use_shadow"):
                d.use_shadow = bool(li.get("shadow", 1)) or kind != "SUN"
        for kind, objs in self.lights.items():
            for k, ob in enumerate(objs):
                ob.hide_render = k >= count.get(kind, 0)
        # the world: the editor's background colour to the camera, its ambient and hemisphere light everywhere else
        n = world_tree.nodes
        n["sky"].inputs["Color"].default_value = (*(sky + amb) / math.pi, 1)
        n["ground"].inputs["Color"].default_value = (*(ground + amb) / math.pi, 1)
        bg = frame.get("background") or [0.05, 0.05, 0.06]
        n["back"].inputs["Color"].default_value = (*bg, 1)

    def camera(self, frame: dict, cam: bpy.types.Object, scene) -> None:
        c = frame["camera"]
        cam.matrix_world = C @ m4(c["m"])
        d = cam.data
        d.sensor_fit = "VERTICAL"
        d.angle_y = math.radians(float(c["fov"]))
        d.clip_start = max(0.01, float(c.get("near") or 0.05))
        d.clip_end = float(c.get("far") or 400)
        focus, ap = c.get("focus"), c.get("aperture")
        d.dof.use_dof = bool(focus) and bool(ap)
        if d.dof.use_dof:
            d.dof.focus_distance = float(focus)
            d.dof.aperture_fstop = max(1.4, min(11.0, FSTOP / float(ap)))
        if focus is not None and float(focus) < 0.3:
            d.dof.use_dof = False  # a cut-in on a dial or a pedal: all of it sharp
        scene.view_settings.exposure = math.log2(max(0.05, float(c.get("exposure") or 1)))
        teal, warm, contrast = GRADES.get(c.get("light") or "day", GRADES["day"])
        g = scene.node_tree.nodes["grade"]
        g.lift = (1 - 0.07 * teal, 1 + 0.01 * teal, 1 + 0.06 * teal)
        g.gain = (1 + 0.09 * warm, 1 + 0.02 * warm, 1 - 0.08 * warm)
        con = scene.node_tree.nodes["contrast"]
        if "Contrast" in con.inputs:
            con.inputs["Contrast"].default_value = 40 * contrast
        fog = frame.get("fog")
        if fog and fog.get("density"):
            scene.world.mist_settings.start = 0.0
            scene.world.mist_settings.depth = 1.6 / float(fog["density"])
            scene.node_tree.nodes["fogcol"].inputs[2].default_value = (*fog["color"], 1)
            scene.node_tree.nodes["fogamt"].outputs[0].default_value = 0.85
        else:
            scene.node_tree.nodes["fogamt"].outputs[0].default_value = 0.0


def setup(scene, w: int, h: int, engine: str, samples: int, device: str) -> tuple:
    scene.render.resolution_x, scene.render.resolution_y = w, h
    scene.render.resolution_percentage = 100
    engines = {i.identifier for i in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items}
    if engine == "EEVEE":
        scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines else "BLENDER_EEVEE"
        ee = scene.eevee
        for k, v in (("taa_render_samples", max(16, samples)), ("use_raytracing", True), ("use_shadows", True), ("use_gtao", True)):
            if hasattr(ee, k):
                setattr(ee, k, v)
    else:
        scene.render.engine = "CYCLES"
        cy = scene.cycles
        cy.samples = samples
        cy.use_adaptive_sampling = True
        cy.use_denoising = True
        try:
            cy.denoiser = "OPENIMAGEDENOISE"
        except TypeError:
            pass
        cy.max_bounces = 6
        cy.diffuse_bounces = 3
        cy.glossy_bounces = 2
        cy.transparent_max_bounces = 8
        cy.caustics_reflective = cy.caustics_refractive = False
        cy.device = "CPU"
        if device != "CPU":
            prefs = bpy.context.preferences.addons["cycles"].preferences
            kinds = ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI")
            for kind in ((device,) if device in kinds else kinds):  # REEL_BLENDER_DEVICE=CUDA tries CUDA alone
                try:
                    prefs.compute_device_type = kind
                    prefs.get_devices()
                    gpus = [d for d in prefs.devices if d.type == kind]
                    if gpus:
                        for d in prefs.devices:
                            d.use = d.type == kind
                        cy.device = "GPU"
                        if hasattr(cy, "denoising_use_gpu"):
                            cy.denoising_use_gpu = True  # off in factory settings: a 1080x1920 frame denoised on the CPU took ~9 s
                        say(device=kind, names=[d.name for d in gpus])
                        break
                except Exception:  # noqa: BLE001 - try the next kind
                    continue
            if cy.device == "CPU":
                say(cpu=True)
        scene.render.use_persistent_data = True
    scene.view_settings.view_transform = "AgX"
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 94
    # the world: background to the camera, sky and ground light to everything else
    world = bpy.data.worlds.new("world")
    scene.world = world
    world.use_nodes = True
    wt = world.node_tree
    wt.nodes.clear()
    out = wt.nodes.new("ShaderNodeOutputWorld")
    path = wt.nodes.new("ShaderNodeLightPath")
    tc = wt.nodes.new("ShaderNodeTexCoord")
    sep = wt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = wt.nodes.new("ShaderNodeMapRange")
    sky = wt.nodes.new("ShaderNodeBackground")
    sky.name = "sky"
    ground = wt.nodes.new("ShaderNodeBackground")
    ground.name = "ground"
    back = wt.nodes.new("ShaderNodeBackground")
    back.name = "back"
    updown = wt.nodes.new("ShaderNodeMixShader")
    final = wt.nodes.new("ShaderNodeMixShader")
    wt.links.new(tc.outputs["Generated"], sep.inputs[0])
    wt.links.new(sep.outputs["Z"], ramp.inputs["Value"])
    ramp.inputs["From Min"].default_value = -1.0
    wt.links.new(ramp.outputs[0], updown.inputs["Fac"])
    wt.links.new(ground.outputs[0], updown.inputs[1])
    wt.links.new(sky.outputs[0], updown.inputs[2])
    wt.links.new(path.outputs["Is Camera Ray"], final.inputs["Fac"])
    wt.links.new(updown.outputs[0], final.inputs[1])
    wt.links.new(back.outputs[0], final.inputs[2])
    wt.links.new(final.outputs[0], out.inputs["Surface"])
    # the compositor: haze by depth (the editor's fog), then a soft glow on the brightest things (lamps, screens)
    scene.view_layers[0].use_pass_mist = True
    scene.world.mist_settings.falloff = "QUADRATIC"
    scene.use_nodes = True
    ct = scene.node_tree
    ct.nodes.clear()
    rl = ct.nodes.new("CompositorNodeRLayers")
    amt = ct.nodes.new("CompositorNodeValue")
    amt.name = "fogamt"
    mul = ct.nodes.new("CompositorNodeMath")
    mul.operation = "MULTIPLY"
    ct.links.new(rl.outputs["Mist"], mul.inputs[0])
    ct.links.new(amt.outputs[0], mul.inputs[1])
    mix = ct.nodes.new("CompositorNodeMixRGB")
    mix.name = "fogcol"
    ct.links.new(mul.outputs[0], mix.inputs[0])
    ct.links.new(rl.outputs["Image"], mix.inputs[1])
    glare = ct.nodes.new("CompositorNodeGlare")
    for k, v in (("glare_type", "BLOOM"), ("quality", "MEDIUM"), ("threshold", 1.2), ("mix", -0.75), ("size", 7)):
        try:
            setattr(glare, k, v)
        except (AttributeError, TypeError):
            pass
    for k, v in (("Threshold", 1.2), ("Strength", 0.3), ("Size", 0.5)):
        if k in glare.inputs:
            glare.inputs[k].default_value = v
    ct.links.new(mix.outputs[0], glare.inputs[0])
    bal = ct.nodes.new("CompositorNodeColorBalance")
    bal.name = "grade"
    bal.correction_method = "LIFT_GAMMA_GAIN"
    con = ct.nodes.new("CompositorNodeBrightContrast")
    con.name = "contrast"
    sat = ct.nodes.new("CompositorNodeHueSat")
    if "Saturation" in sat.inputs:
        sat.inputs["Saturation"].default_value = SATURATION
    ct.links.new(glare.outputs[0], bal.inputs[1])
    ct.links.new(bal.outputs[0], con.inputs[0])
    ct.links.new(con.outputs[0], sat.inputs[1] if len(sat.inputs) > 1 and sat.inputs[0].name == "Fac" else sat.inputs[0])
    comp = ct.nodes.new("CompositorNodeComposite")
    ct.links.new(sat.outputs[0], comp.inputs[0])
    cam_data = bpy.data.cameras.new("cam")
    cam = bpy.data.objects.new("cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    return cam, wt


marks: dict[str, float] = {}  # when the scene was built (the app shows where a frame's time goes)


def _parts(t0: float, m: dict) -> dict:
    """Seconds building the scene in Python and inside Blender's render (sync, path tracing, denoising, compositing,
    saving). Blender's render_post/composite handlers don't fire in a background render, so those aren't split."""
    prep = m.get("prep", t0)
    return {"build": round(prep - t0, 2), "render": round(time.time() - prep, 2)}


def main() -> None:
    a = args()
    root = Path(a["root"])
    out_dir = Path(a["out"])
    out_dir.mkdir(parents=True, exist_ok=True)
    first, last = int(a.get("first", 0)), int(a.get("last", 0))
    w, h = int(a.get("width", 1080)), int(a.get("height", 1920))
    engine = a.get("engine", "CYCLES").upper()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    cam, wt = setup(scene, w, h, engine, int(a.get("samples", 48)), a.get("device", "CPU").upper())
    b = Builder(root, engine)
    threads = int(a.get("threads", 0) or 0)
    if threads > 0:  # several Blender processes on the processor share its cores
        scene.render.threads_mode = "FIXED"
        scene.render.threads = threads
    frames = list(range(first, last + 1))
    claims = Path(a["claims"]) if a.get("claims") else None
    block = max(1, int(a.get("block", 12) or 12))

    def mine():
        """This process's frames: blocks of consecutive ones (persistent data and held-frame copies work within a
        block); with several processes, each block goes to the first one that claims it."""
        for i in range(0, len(frames), block):
            part = [f for f in frames[i:i + block] if not (out_dir / f"f{f:05d}.jpg").exists()]
            if not part:
                continue
            if claims is not None:
                try:
                    os.close(os.open(claims / f"b{i // block:05d}", os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                except FileExistsError:
                    continue
            yield from part

    todo = sum(1 for f in frames if not (out_dir / f"f{f:05d}.jpg").exists())
    say(start=True, todo=todo, total=last - first + 1, engine=scene.render.engine, device=scene.cycles.device if engine == "CYCLES" else "GPU")
    done = 0
    last_sig, last_out = None, None
    for f in mine():
        src = root / "scene" / f"f{f:05d}.json.gz"
        if not src.exists():
            say(missing=f)
            continue
        t0 = time.time()
        frame = json.loads(gzip.decompress(src.read_bytes()))
        # a held frame (a freeze, a still moment) is the same scene again: the same picture, not drawn twice
        sig = zlib.crc32(json.dumps({k: v for k, v in frame.items() if k != "frame"}, sort_keys=True).encode())
        if sig == last_sig and last_out and last_out.exists():
            shutil.copyfile(last_out, out_dir / f"f{f:05d}.jpg")
            done += 1
            say(done=done, todo=todo, frame=f, sec=round(time.time() - t0, 2), same=True)
            continue
        b.objects(frame)
        b.dress()
        b.lighting(frame, wt)
        b.camera(frame, cam, scene)
        lights = sum(1 for o in b.coll.objects if o.type == "LIGHT" and not o.hide_render)
        scene.cycles.use_light_tree = lights > LIGHT_TREE_FROM
        marks.clear()
        marks["prep"] = time.time()
        tmp = out_dir / f"f{f:05d}.part.jpg"
        scene.render.filepath = str(tmp)
        bpy.ops.render.render(write_still=True)
        if not tmp.exists():  # a render Blender gave up on (out of card memory...) writes nothing: never a blank frame
            raise RuntimeError(f"frame {f} wasn't written (out of graphics card memory?)")
        os.replace(tmp, out_dir / f"f{f:05d}.jpg")
        last_sig, last_out = sig, out_dir / f"f{f:05d}.jpg"
        done += 1
        say(done=done, todo=todo, frame=f, sec=round(time.time() - t0, 2), parts=_parts(t0, marks))
    say(finished=True, done=done)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - the app shows this line
        import traceback

        traceback.print_exc()
        say(error=f"{type(exc).__name__}: {exc}")
        sys.exit(1)
