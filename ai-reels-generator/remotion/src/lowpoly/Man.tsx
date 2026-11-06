// The low-poly man: a faceted head (an icosphere with each corner nudged, flat shaded), curly hair as a cluster of
// small faceted lumps, square glasses of thin bars, black eyes on white, a little faceted nose, a bar of a mouth,
// a boxy sweater, box arms with faceted hands, box legs and white block shoes. Modelled on the user's own character
// (reference Short 'Life of a Man'); every film uses the same one (cast 'hero').
import React, {useMemo} from 'react';
import * as THREE from 'three';
import type {Design, Hold} from './types';
import {HIP, type Face, type Limb, type Pose} from './poses';

// Sizes in the man's units (he is about 2 tall to the top of his hair).
export const D = {
  shoe: [0.21, 0.12, 0.34] as const,
  shin: 0.25,
  thigh: 0.27,
  leg: [0.22, 0.24] as const, // width, depth
  legX: 0.15,
  torso: [0.64, 0.6, 0.4] as const,
  arm: [0.17, 0.19] as const,
  upper: 0.28,
  fore: 0.25,
  hand: 0.075,
  head: 0.35,
  neck: 0.06,
};
export const HEAD_Y = D.torso[1] + D.neck + D.head * 0.94; // head centre over the pelvis

const mats = new Map<string, THREE.Material>();
export const mat = (color: string, opts: {emissive?: string; rough?: number; glow?: number} = {}) => {
  const key = `${color}|${opts.emissive ?? ''}|${opts.rough ?? 0.92}|${opts.glow ?? 0}`;
  let m = mats.get(key);
  if (!m) {
    m = new THREE.MeshStandardMaterial({color, flatShading: true, roughness: opts.rough ?? 0.92, metalness: 0});
    if (opts.emissive) {
      (m as THREE.MeshStandardMaterial).emissive = new THREE.Color(opts.emissive);
      (m as THREE.MeshStandardMaterial).emissiveIntensity = opts.glow ?? 1;
    }
    mats.set(key, m);
  }
  return m;
};

// A seeded generator (mulberry32) so a face, a curl or a tree is the same in every frame and every render.
export const rng = (seed: number) => {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
};

// An icosphere whose corners are pushed in or out a little: the hand-made low-poly look. Shared corners move
// together (the geometry repeats them per face), so no cracks open.
export const facetedBall = (r: number, detail: number, wobble: number, seed: number) => {
  const g = new THREE.IcosahedronGeometry(r, detail);
  const pos = g.attributes.position as THREE.BufferAttribute;
  const rand = rng(seed);
  const moved = new Map<string, number>();
  for (let i = 0; i < pos.count; i++) {
    const key = `${pos.getX(i).toFixed(3)},${pos.getY(i).toFixed(3)},${pos.getZ(i).toFixed(3)}`;
    if (!moved.has(key)) moved.set(key, 1 + (rand() * 2 - 1) * wobble);
    const k = moved.get(key)!;
    pos.setXYZ(i, pos.getX(i) * k, pos.getY(i) * k, pos.getZ(i) * k);
  }
  g.computeVertexNormals();
  return g;
};

const geoCache = new Map<string, THREE.BufferGeometry>();
const cached = (key: string, make: () => THREE.BufferGeometry) => {
  let g = geoCache.get(key);
  if (!g) {
    g = make();
    geoCache.set(key, g);
  }
  return g;
};

// Curly hair: lumps over the top and the back of the head, the hairline high on the forehead and over the ears.
const hairGeo = (style: Design['hairStyle'], seed: number) =>
  cached(`hair-${style}-${seed}`, () => {
    const rand = rng(seed * 7 + 3);
    const parts: THREE.BufferGeometry[] = [];
    const R = D.head;
    const lumps = style === 'curly' ? 190 : style === 'short' ? 150 : 130;
    for (let n = 0, tries = 0; n < lumps && tries < 4000; tries++) {
      const u = rand() * 2 - 1;
      const th = rand() * Math.PI * 2;
      const s = Math.sqrt(1 - u * u);
      const d = new THREE.Vector3(s * Math.cos(th), u, s * Math.sin(th));
      const front = d.z > 0.25;
      const side = Math.abs(d.x) > 0.55;
      // the face stays clear: a high fringe, above the ears at the sides, down to the nape at the back
      const ok = front ? d.y > 0.5 + 0.12 * Math.abs(d.x) : side ? d.y > 0.12 + (d.z > 0 ? 0.25 : 0) : d.y > -0.38;
      if (!ok) continue;
      const curl = style === 'curly' ? 0.048 + rand() * 0.03 : 0.045 + rand() * 0.02;
      const g = new THREE.IcosahedronGeometry(curl, 0);
      const lift = style === 'curly' ? (d.y > 0.6 ? 1.02 + rand() * 0.05 : 0.985 + rand() * 0.04) : 0.97 + rand() * 0.02;
      g.rotateX(rand() * 3);
      g.rotateY(rand() * 3);
      g.translate(d.x * R * lift, d.y * R * lift + (d.y > 0.5 ? 0.02 : 0), d.z * R * lift);
      parts.push(g.toNonIndexed());
      n++;
    }
    if (style === 'long' || style === 'ponytail' || style === 'bun') {
      const back = new THREE.BoxGeometry(0.62, style === 'long' ? 0.62 : 0.3, 0.16, 1, 2, 1);
      back.translate(0, style === 'long' ? -0.12 : 0.05, -0.27);
      parts.push(back.toNonIndexed());
      if (style === 'long') {
        for (const sx of [-1, 1]) {
          const lock = new THREE.BoxGeometry(0.11, 0.55, 0.22);
          lock.translate(sx * 0.31, -0.12, -0.02);
          parts.push(lock.toNonIndexed());
        }
      }
      if (style === 'bun') {
        const bun = new THREE.IcosahedronGeometry(0.14, 1);
        bun.translate(0, 0.33, -0.18);
        parts.push(bun.toNonIndexed());
      }
      if (style === 'ponytail') {
        const tail = new THREE.BoxGeometry(0.13, 0.4, 0.13);
        tail.translate(0, -0.12, -0.42);
        parts.push(tail.toNonIndexed());
      }
    }
    const merged = mergeAll(parts);
    merged.computeVertexNormals();
    return merged;
  });

// BufferGeometryUtils.mergeGeometries without the import (all parts are non-indexed with position + normal + uv).
const mergeAll = (parts: THREE.BufferGeometry[]) => {
  const names = ['position', 'normal'];
  const out = new THREE.BufferGeometry();
  for (const name of names) {
    const arrays = parts.map((p) => (p.getAttribute(name) as THREE.BufferAttribute).array as Float32Array);
    const total = arrays.reduce((t, a) => t + a.length, 0);
    const buf = new Float32Array(total);
    let o = 0;
    for (const a of arrays) {
      buf.set(a, o);
      o += a.length;
    }
    out.setAttribute(name, new THREE.BufferAttribute(buf, 3));
  }
  return out;
};

const box = (w: number, h: number, d: number) => cached(`box-${w}-${h}-${d}`, () => new THREE.BoxGeometry(w, h, d));
const ball = (r: number, detail = 0) => cached(`ball-${r}-${detail}`, () => new THREE.IcosahedronGeometry(r, detail));
const disc = (r: number) => cached(`disc-${r}`, () => new THREE.CircleGeometry(r, 18));

const M: React.FC<{g: THREE.BufferGeometry; m: THREE.Material; p?: [number, number, number]; r?: [number, number, number]; s?: [number, number, number]}> = ({
  g,
  m,
  p,
  r,
  s,
}) => <mesh geometry={g} material={m} position={p} rotation={r} scale={s} castShadow receiveShadow />;

// A limb: the joint at the group's origin, the box hanging down from it, the next joint at its end.
const Limb3: React.FC<{
  at: [number, number, number];
  limb: Limb;
  len1: number;
  len2: number;
  w: number;
  d: number;
  m1: THREE.Material;
  m2: THREE.Material;
  end: React.ReactNode;
}> = ({at, limb, len1, len2, w, d, m1, m2, end}) => (
  <group position={at} rotation={[limb.x, 0, (at[0] < 0 ? -1 : 1) * limb.z]}>
    <M g={box(w, len1 + 0.02, d)} m={m1} p={[0, -len1 / 2, 0]} />
    <group position={[0, -len1, 0]} rotation={[limb.bend, 0, 0]}>
      <M g={box(w * 0.96, len2 + 0.02, d * 0.96)} m={m2} p={[0, -len2 / 2, 0]} />
      <group position={[0, -len2, 0]}>{end}</group>
    </group>
  </group>
);

const Glasses: React.FC<{color: string}> = ({color}) => {
  const m = mat(color, {rough: 0.6});
  const t = 0.026;
  const w = 0.22;
  const h = 0.155;
  const z = D.head * 0.99;
  const lens = (cx: number) => (
    <group position={[cx, 0.02, z]} key={cx}>
      <M g={box(w, t, t)} m={m} p={[0, h / 2, 0]} />
      <M g={box(w, t, t)} m={m} p={[0, -h / 2, 0]} />
      <M g={box(t, h, t)} m={m} p={[-w / 2, 0, 0]} />
      <M g={box(t, h, t)} m={m} p={[w / 2, 0, 0]} />
    </group>
  );
  return (
    <group>
      {lens(-0.125)}
      {lens(0.125)}
      <M g={box(0.05, t * 0.9, t)} m={m} p={[0, 0.06, z + 0.005]} />
      {[-1, 1].map((sx) => (
        <M key={sx} g={box(t * 0.8, t * 0.8, 0.4)} m={m} p={[sx * 0.24, 0.05, 0.15]} r={[0, sx * 0.22, 0]} />
      ))}
    </group>
  );
};

const FaceView: React.FC<{f: Face; design: Design}> = ({f, design}) => {
  const z = D.head * 0.935;
  const skin = mat(design.skin);
  const dark = mat('#141416', {rough: 0.5});
  const white = mat('#f4f2ee', {rough: 0.5});
  const brow = mat(design.hairStyle === 'bald' ? '#5a4030' : design.hair);
  const er = 0.058 * f.eye;
  const eye = (sx: number) => (
    <group key={sx} position={[sx * 0.118, 0.015, z]} rotation={[0, sx * 0.3, 0]}>
      <mesh geometry={disc(er)} material={white} scale={[1, 0.82, 1]} position={[0, 0, 0.004]} />
      <mesh geometry={disc(er * 0.86)} material={dark} scale={[1, 0.88, 1]} position={[f.look[0] - sx * 0.004, f.look[1] - 0.004, 0.009]} />
      {f.lid > 0.02 ? (
        // the eyelid: a skin-coloured block coming down over the top of the eye
        <mesh
          geometry={box(er * 2.3, er * 1.9 * f.lid, 0.02)}
          material={skin}
          position={[0, er * 0.85 - (er * 1.9 * f.lid) / 2 + 0.002, 0.012]}
        />
      ) : null}
      {f.lid >= 1 ? <mesh geometry={box(er * 1.9, 0.012, 0.01)} material={dark} position={[0, -er * 0.3, 0.024]} /> : null}
      <mesh
        geometry={box(0.115, 0.026, 0.03)}
        material={brow}
        position={[0, 0.115 + f.brow, 0.03]}
        rotation={[0, 0, sx * -f.tilt]}
      />
    </group>
  );
  const mouthY = -0.155;
  const mouth = (() => {
    switch (f.mouth) {
      case 'o':
        return <mesh geometry={box(0.055, 0.075, 0.02)} material={dark} position={[0, mouthY - 0.01, z - 0.01]} />;
      case 'smile':
      case 'frown': {
        const up = f.mouth === 'smile' ? 1 : -1;
        return (
          <group position={[0, mouthY, z - 0.012]}>
            <mesh geometry={box(0.06, 0.022, 0.02)} material={dark} />
            <mesh geometry={box(0.04, 0.02, 0.02)} material={dark} position={[-0.045, up * 0.012, 0]} rotation={[0, 0, -up * 0.5]} />
            <mesh geometry={box(0.04, 0.02, 0.02)} material={dark} position={[0.045, up * 0.012, 0]} rotation={[0, 0, up * 0.5]} />
          </group>
        );
      }
      case 'flat':
        return <mesh geometry={box(0.12, 0.02, 0.02)} material={dark} position={[0.008, mouthY, z - 0.012]} rotation={[0, 0, 0.05]} />;
      default:
        return <mesh geometry={box(0.1, 0.022, 0.02)} material={dark} position={[0, mouthY, z - 0.012]} />;
    }
  })();
  return (
    <group>
      {eye(-1)}
      {eye(1)}
      <mesh geometry={ball(0.062, 0)} material={skin} position={[0, -0.05, D.head * 0.98]} scale={[0.95, 1, 1.25]} castShadow />
      {mouth}
    </group>
  );
};

// A phone's lit screen: a chat (a name bar, grey and blue bubbles), drawn once.
let screenTex: THREE.CanvasTexture | null = null;
const phoneScreen = () => {
  if (!screenTex) {
    const c = document.createElement('canvas');
    c.width = 180;
    c.height = 340;
    const g = c.getContext('2d')!;
    g.fillStyle = '#eef2f7';
    g.fillRect(0, 0, 180, 340);
    g.fillStyle = '#d5dce6';
    g.fillRect(0, 0, 180, 46);
    g.fillStyle = '#8a96a8';
    g.beginPath();
    g.arc(26, 23, 13, 0, Math.PI * 2);
    g.fill();
    g.fillRect(48, 17, 70, 12);
    const bubble = (x: number, y: number, w: number, h: number, col: string) => {
      g.fillStyle = col;
      g.beginPath();
      g.roundRect(x, y, w, h, 12);
      g.fill();
    };
    bubble(12, 66, 112, 34, '#d9dee6');
    bubble(12, 110, 84, 34, '#d9dee6');
    bubble(64, 160, 104, 34, '#4f8ff7');
    bubble(12, 210, 120, 34, '#d9dee6');
    bubble(84, 258, 84, 34, '#4f8ff7');
    g.fillStyle = '#d5dce6';
    g.fillRect(0, 306, 180, 34);
    screenTex = new THREE.CanvasTexture(c);
    screenTex.colorSpace = THREE.SRGBColorSpace;
  }
  return screenTex;
};
// where the phone sits in the hand and which way its screen faces (the editor's camera aims at it)
export const PHONE_AT: [number, number, number] = [0, -0.085, 0.045];
export const PHONE_TILT = -0.4;

// Things held in the hand, drawn at the hand.
export const HeldThing: React.FC<{hold: Hold; glow?: boolean}> = ({hold}) => {
  switch (hold) {
    case 'phone':
      return (
        <group position={PHONE_AT} rotation={[PHONE_TILT, 0, 0]}>
          <M g={box(0.1, 0.19, 0.016)} m={mat('#1a1b1f', {rough: 0.4})} />
          <mesh position={[0, 0, 0.0085]}>
            <planeGeometry args={[0.088, 0.172]} />
            <meshBasicMaterial map={phoneScreen()} toneMapped={false} />
          </mesh>
        </group>
      );
    case 'mug':
      return (
        <group position={[0, -0.02, 0.06]}>
          <M g={cached('mug', () => new THREE.CylinderGeometry(0.06, 0.055, 0.13, 8))} m={mat('#e9e4da')} />
        </group>
      );
    case 'book':
      return <M g={box(0.24, 0.32, 0.04)} m={mat('#3d5a80')} p={[0.1, -0.05, 0.08]} r={[-0.6, 0, 0]} />;
    case 'laptop':
      return <M g={box(0.42, 0.03, 0.3)} m={mat('#9aa0a8', {rough: 0.5})} p={[0.15, -0.05, 0.1]} />;
    case 'shoes':
      return <M g={box(0.2, 0.11, 0.32)} m={mat('#ecebe6')} p={[0, -0.06, 0.04]} />;
    case 'bag':
      return <M g={box(0.32, 0.36, 0.14)} m={mat('#4a5a48')} p={[0, -0.22, 0]} />;
    case 'keys':
      return <M g={box(0.05, 0.08, 0.01)} m={mat('#c9a84a', {rough: 0.4})} p={[0, -0.05, 0.03]} />;
    case 'fork':
      return <M g={box(0.02, 0.18, 0.015)} m={mat('#c8c8c8', {rough: 0.4})} p={[0, -0.02, 0.06]} r={[-1, 0, 0]} />;
    default:
      return null;
  }
};

// The whole man. `root` = where his pelvis's spot is (floor, seat or bed surface) and which way he faces.
export const Man: React.FC<{
  design: Design;
  pose: Pose;
  face: Face;
  root: [number, number, number];
  ry: number;
  hold?: Hold;
  seed: number;
}> = ({design, pose: p, face: f, root, ry, hold = 'none', seed}) => {
  const skin = mat(design.skin);
  const top = mat(design.top);
  const topDark = mat(new THREE.Color(design.top).multiplyScalar(0.82).getStyle());
  const legs = mat(design.trousers);
  const shoe = mat(design.shoes);
  const hair = mat(design.hair);
  const head = useMemo(() => cached(`head-${seed}`, () => facetedBall(D.head, 1, 0.045, seed)), [seed]);
  const scale = design.height ?? 1;
  const dress = design.topKind === 'dress';
  const hand = (side: 'L' | 'R') => (
    <group>
      <mesh geometry={cached(`hand-${seed}`, () => facetedBall(D.hand, 0, 0.08, seed + 5))} material={skin} position={[0, -D.hand * 0.7, 0]} castShadow />
      {hold && hold !== 'none' && side === 'R' ? (
        <group position={[0, -D.hand * 1.2, 0]}>
          <HeldThing hold={hold} />
        </group>
      ) : null}
    </group>
  );
  const foot = <M g={box(...D.shoe)} m={shoe} p={[0, -D.shoe[1] / 2 + 0.01, 0.05]} />;
  const sx = D.torso[0] / 2 + D.arm[0] / 2 + 0.005;
  return (
    <group position={root} rotation={[0, ry, 0]} scale={scale}>
      <group position={[0, p.y, 0]} rotation={[p.rx, 0, p.rz]}>
        {/* legs */}
        <Limb3 at={[-D.legX, 0, 0]} limb={p.legL} len1={D.thigh} len2={D.shin} w={D.leg[0]} d={D.leg[1]} m1={dress ? skin : legs} m2={dress ? skin : legs} end={foot} />
        <Limb3 at={[D.legX, 0, 0]} limb={p.legR} len1={D.thigh} len2={D.shin} w={D.leg[0]} d={D.leg[1]} m1={dress ? skin : legs} m2={dress ? skin : legs} end={foot} />
        {dress ? <M g={box(0.62, 0.3, 0.42)} m={top} p={[0, -0.1, 0]} /> : null}
        {/* the body: the sweater, its hem a shade darker, then the shoulders, neck and head */}
        <group rotation={[p.lean, p.twist, p.side]}>
          <M g={box(...D.torso)} m={top} p={[0, D.torso[1] / 2 + 0.02, 0]} />
          <M g={box(D.torso[0] + 0.01, 0.06, D.torso[2] + 0.01)} m={topDark} p={[0, 0.05, 0]} />
          <M g={box(0.24, 0.05, 0.22)} m={topDark} p={[0, D.torso[1] + 0.03, 0]} />
          {design.topKind === 'suit' ? <M g={box(0.08, 0.32, 0.02)} m={mat('#7a1f25')} p={[0, D.torso[1] - 0.18, D.torso[2] / 2 + 0.01]} /> : null}
          <Limb3 at={[-sx, D.torso[1] - 0.06, 0]} limb={p.armL} len1={D.upper} len2={D.fore} w={D.arm[0]} d={D.arm[1]} m1={top} m2={top} end={hand('L')} />
          <Limb3 at={[sx, D.torso[1] - 0.06, 0]} limb={p.armR} len1={D.upper} len2={D.fore} w={D.arm[0]} d={D.arm[1]} m1={top} m2={top} end={hand('R')} />
          <M g={cached('neck', () => new THREE.CylinderGeometry(0.11, 0.12, 0.12, 7))} m={skin} p={[0, D.torso[1] + 0.06, 0]} />
          <group position={[0, HEAD_Y, 0]} rotation={p.head}>
            <mesh geometry={head} material={skin} castShadow receiveShadow scale={[1, 0.97, 0.98]} />
            {design.hairStyle !== 'bald' ? <mesh geometry={hairGeo(design.hairStyle, seed)} material={hair} castShadow /> : null}
            <FaceView f={f} design={design} />
            {design.glasses ? <Glasses color="#2f2d2c" /> : null}
            {design.beard ? <M g={box(0.42, 0.16, 0.2)} m={hair} p={[0, -0.24, 0.18]} /> : null}
          </group>
        </group>
      </group>
    </group>
  );
};

export const HERO: Design = {
  skin: '#e6d8cb',
  hair: '#94593a',
  hairStyle: 'curly',
  glasses: true,
  top: '#b2414e',
  topKind: 'sweater',
  trousers: '#6a4a33',
  shoes: '#eeece7',
};

export {HIP};
