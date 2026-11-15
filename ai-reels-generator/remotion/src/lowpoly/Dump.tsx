// The Blender bridge (reelgen/lowpoly/blend.py): every frame's 3D scene, exactly as the editor built it, sent to a
// local receiver so Blender can rebuild and render it with real light (the user: a Blender low-poly diorama "i need
// this level ... with free"). Nothing here draws: the render that runs this uses imageFormat 'none'.
//
// Per frame: the camera (its matrix, field of view, focus distance and aperture), the background and fog, every
// light, and every visible mesh as [geometry, material, world matrix]. A geometry, material or picture is sent once
// per browser tab, by a hash of its contents (tabs render frames in parallel and don't share memory); the receiver
// keeps one copy of each.
import React, {useLayoutEffect} from 'react';
import {continueRender, delayRender} from 'remotion';
import {useThree} from '@react-three/fiber';
import * as THREE from 'three';

const sent = new Set<string>();
const geoKey = new WeakMap<THREE.BufferGeometry, string>();
const texKey = new WeakMap<THREE.Texture, {version: number; key: string}>();

// FNV-1a over bytes, twice with different seeds: a 64-bit-ish name for a geometry or a picture
const hashBytes = (b: Uint8Array, seed = 2166136261) => {
  let h = seed >>> 0;
  for (let i = 0; i < b.length; i++) {
    h ^= b[i];
    h = Math.imul(h, 16777619) >>> 0;
  }
  return h.toString(36);
};
const bytesOf = (a: ArrayLike<number> & {buffer: ArrayBufferLike; byteOffset: number; byteLength: number}) =>
  new Uint8Array(a.buffer, a.byteOffset, a.byteLength);
const hashOf = (parts: Uint8Array[]) => parts.map((p) => hashBytes(p) + hashBytes(p, 0x811c9dc5 ^ 0x5bd1e995)).join('').slice(0, 24) + parts.reduce((n, p) => n + p.length, 0).toString(36);
const hashText = (s: string) => hashOf([new TextEncoder().encode(s)]);

const b64 = (b: Uint8Array) => {
  let s = '';
  for (let i = 0; i < b.length; i += 0x8000) s += String.fromCharCode(...b.subarray(i, i + 0x8000));
  return btoa(s);
};
const r5 = (x: number) => Math.round(x * 1e5) / 1e5;
const lin = (c?: THREE.Color) => (c ? [r5(c.r), r5(c.g), r5(c.b)] : null);

type Out = {geos: Record<string, unknown>; mats: Record<string, unknown>; texs: Record<string, unknown>};

const geometry = (g: THREE.BufferGeometry, out: Out) => {
  let key = geoKey.get(g);
  const pos = g.getAttribute('position') as THREE.BufferAttribute | undefined;
  if (!pos || !(pos.array instanceof Float32Array)) return null;
  if (!key) {
    const idx = g.getIndex();
    const uv = g.getAttribute('uv') as THREE.BufferAttribute | undefined;
    const parts = [bytesOf(pos.array as Float32Array)];
    if (idx) parts.push(bytesOf(idx.array as Uint16Array | Uint32Array));
    if (uv && uv.array instanceof Float32Array) parts.push(bytesOf(uv.array));
    key = 'g' + hashOf(parts);
    geoKey.set(g, key);
  }
  if (!sent.has(key)) {
    const idx = g.getIndex();
    const uv = g.getAttribute('uv') as THREE.BufferAttribute | undefined;
    out.geos[key] = {
      pos: b64(bytesOf(pos.array as Float32Array)),
      idx: idx ? b64(bytesOf(idx.array as Uint16Array | Uint32Array)) : null,
      idxBits: idx ? (idx.array instanceof Uint32Array ? 32 : 16) : 0,
      uv: uv && uv.array instanceof Float32Array && uv.itemSize === 2 ? b64(bytesOf(uv.array)) : null,
      plane: g.type === 'PlaneGeometry', // a wall or a ceiling: seen from one side only (three culls the back)
    };
    sent.add(key);
  }
  return key;
};

const texture = (t: THREE.Texture | null | undefined, out: Out): string | null => {
  if (!t) return null;
  const img = t.image as {width?: number; height?: number} | undefined;
  if (!img || !img.width || !img.height) return null;
  const known = texKey.get(t);
  if (known && known.version === t.version) return known.key;
  let url = '';
  try {
    if (typeof HTMLCanvasElement !== 'undefined' && img instanceof HTMLCanvasElement) url = img.toDataURL('image/png');
    else {
      const c = document.createElement('canvas');
      c.width = img.width;
      c.height = img.height;
      c.getContext('2d')!.drawImage(img as CanvasImageSource, 0, 0);
      url = c.toDataURL('image/png');
    }
  } catch {
    return null;
  }
  const key = 't' + hashText(url + `|${t.repeat.x},${t.repeat.y},${t.offset.x},${t.offset.y},${t.wrapS},${t.wrapT}`);
  texKey.set(t, {version: t.version, key});
  if (!sent.has(key)) {
    out.texs[key] = {url, repeat: [t.repeat.x, t.repeat.y], offset: [t.offset.x, t.offset.y], srgb: t.colorSpace === THREE.SRGBColorSpace};
    sent.add(key);
  }
  return key;
};

const material = (m: THREE.Material, out: Out): string | null => {
  if (!m.visible) return null;
  const s = m as THREE.MeshStandardMaterial & THREE.MeshPhysicalMaterial & THREE.MeshBasicMaterial;
  if (m.transparent && (s.opacity ?? 1) < 0.01) return null;
  const rec = {
    type: m.type,
    color: lin(s.color),
    emissive: lin(s.emissive),
    ei: s.emissiveIntensity ?? 0,
    rough: s.roughness ?? 1,
    metal: s.metalness ?? 0,
    opacity: s.opacity ?? 1,
    transparent: !!m.transparent,
    flat: !!s.flatShading,
    side: m.side,
    map: texture(s.map, out),
    emap: texture(s.emissiveMap, out),
    transmission: s.transmission ?? 0,
    ior: s.ior ?? 1.5,
    toneMapped: m.toneMapped !== false,
  };
  const key = 'm' + hashText(JSON.stringify(rec));
  if (!sent.has(key)) {
    out.mats[key] = rec;
    sent.add(key);
  }
  return key;
};

const matrix = (m: THREE.Matrix4) => m.elements.map(r5);

export const dumpScene = (scene: THREE.Scene, camera: THREE.PerspectiveCamera, frame: number) => {
  scene.updateMatrixWorld(true);
  camera.updateMatrixWorld(true);
  const out: Out = {geos: {}, mats: {}, texs: {}};
  const items: unknown[] = [];
  const insts: unknown[] = [];
  const lights: unknown[] = [];
  scene.traverseVisible((o) => {
    const mesh = o as THREE.Mesh;
    if ((mesh as THREE.Mesh).isMesh) {
      const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
      if (!mats[0]) return;
      const g = geometry(mesh.geometry, out);
      const m = material(mats[0], out);
      if (!g || !m) return;
      const inst = o as THREE.InstancedMesh;
      if (inst.isInstancedMesh) {
        const arr = inst.instanceMatrix.array as Float32Array;
        insts.push([g, m, matrix(o.matrixWorld), b64(bytesOf(arr.subarray(0, inst.count * 16))), o.castShadow ? 1 : 0]);
      } else items.push([g, m, matrix(o.matrixWorld), o.castShadow ? 1 : 0]);
      return;
    }
    const l = o as THREE.Light;
    if (!l.isLight || l.intensity <= 0) return;
    const rec: Record<string, unknown> = {type: l.type, color: lin(l.color), intensity: r5(l.intensity), m: matrix(o.matrixWorld)};
    const withTarget = l as THREE.DirectionalLight | THREE.SpotLight;
    if (withTarget.target) {
      withTarget.target.updateMatrixWorld(true);
      rec.target = new THREE.Vector3().setFromMatrixPosition(withTarget.target.matrixWorld).toArray().map(r5);
    }
    const pl = l as THREE.PointLight & THREE.SpotLight;
    if (pl.distance !== undefined) rec.distance = pl.distance;
    if (pl.decay !== undefined) rec.decay = pl.decay;
    if (pl.angle !== undefined) rec.angle = pl.angle;
    if (pl.penumbra !== undefined) rec.penumbra = pl.penumbra;
    const area = l as THREE.RectAreaLight;
    if (area.width !== undefined) rec.size = [area.width, area.height];
    const hemi = l as THREE.HemisphereLight;
    if (hemi.groundColor) rec.ground = lin(hemi.groundColor);
    rec.shadow = l.castShadow ? 1 : 0;
    lights.push(rec);
  });
  const bg = scene.background as THREE.Color | null;
  const fog = scene.fog as THREE.FogExp2 | null;
  const ud = camera.userData as {focus?: number; aperture?: number; exposure?: number; light?: string};
  return {
    frame,
    camera: {m: matrix(camera.matrixWorld), fov: camera.fov, aspect: camera.aspect, near: camera.near, far: camera.far,
      focus: ud.focus ?? null, aperture: ud.aperture ?? null, exposure: ud.exposure ?? 1, light: ud.light ?? ''},
    background: bg && (bg as THREE.Color).isColor ? lin(bg) : null,
    fog: fog && (fog as THREE.FogExp2).isFogExp2 ? {color: lin(fog.color), density: fog.density} : null,
    lights,
    items,
    insts,
    ...out,
  };
};

// Sends this frame's scene and holds the frame until the receiver has it.
export const Dump: React.FC<{url: string; frame: number}> = ({url, frame}) => {
  const scene = useThree((s) => s.scene);
  const camera = useThree((s) => s.camera) as THREE.PerspectiveCamera;
  useLayoutEffect(() => {
    const handle = delayRender(`Sending frame ${frame}'s scene to Blender`);
    let body = '';
    try {
      body = JSON.stringify(dumpScene(scene, camera, frame));
    } catch (e) {
      body = JSON.stringify({frame, error: String(e)});
    }
    fetch(`${url}/frame/${frame}`, {method: 'POST', body, headers: {'Content-Type': 'text/plain'}})
      .then((r) => (r.ok ? continueRender(handle) : r.text().then((t) => { throw new Error(t); })))
      .catch((e) => {
        console.error('Blender bridge:', e);
        continueRender(handle);
      });
  });
  return null;
};
