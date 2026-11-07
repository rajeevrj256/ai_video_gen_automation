// The places, built from flat-shaded boxes and faceted shapes like the man, and the light of each time of day.
// Rooms are open at the front (+z, where the camera usually is) and their walls face inward only, so a camera that
// ends up outside a wall still sees in. Every set lists its spots (where a person stands, sits or lies), the wide
// camera, the direction its main light comes from and the surface things are put on.
import React from 'react';
import * as THREE from 'three';
import {facetedBall, mat, rng} from './Man';
import type {Light, SetName, Spot} from './types';

// `stand`: where someone who isn't sitting stands at a seat spot (in front of a bench or bed, beside a chair at a
// table or desk); without it a man standing 'at the bench' stood inside it. Kept in step with timeline.set_spots.
export type SpotDef = {x: number; z: number; ry: number; seat?: number; bed?: number; stand?: [number, number]};
export type SetDef = {
  spots: Partial<Record<Spot, SpotDef>>;
  wide: {pos: [number, number, number]; look: [number, number, number]};
  sun: [number, number, number]; // where the key light comes from (a point the light shines from, toward the origin)
  outdoor: boolean;
  walk: 'x' | 'z'; // the way a walk goes when the shot gives no destination
  road?: number; // z of the traffic lane (walk 'x' sets with a road): cars and buses drive and stand there, never on the pavement
  surface: [number, number, number]; // where things are put
  lamp?: [number, number, number]; // where a lamp's light comes from when one is on
  reach?: number; // how far a vehicle under way can travel through it in one shot (metres)
  drive?: number; // the line across the walk a vehicle under way follows where there is no road (else the road, else its spot)
  jumpAt?: number; // where along it a vehicle's jump takes off (the rooftop's edge)
  gap?: [number, number]; // along the walk: no ground here (between two roofs, a bridge's fallen span); only a jump crosses it
  sky?: boolean; // high in the air: there is no ground, anything flying flies at the clouds' height
  Draw: React.FC<{look: Look; seed: number}>;
};

export type Look = {
  sky: [string, string]; // top, horizon
  hemi: [string, string, number];
  key: [string, number];
  fill: [string, number];
  window: [string, number]; // what a window shows, and how bright
  lamp: number; // indoor lamps' light
  fog: number; // outdoor haze (0 = none)
  exposure: number;
  shade: number; // walls and floors darkened at night
};

export const LOOKS: Record<Light, Look> = {
  night: {sky: ['#111a30', '#2a3756'], hemi: ['#6c7ca6', '#3a3646', 1.15], key: ['#a9bbee', 2.1], fill: ['#7080b4', 0.5], window: ['#2a3e6a', 1.0], lamp: 0, fog: 0.01, exposure: 1.1, shade: 0.7},
  lamp: {sky: ['#0b0f1c', '#1b2238'], hemi: ['#5a5f78', '#3e3238', 0.8], key: ['#8a9ad0', 0.7], fill: ['#ffb36b', 0.4], window: ['#17213c', 0.7], lamp: 2.2, fog: 0.012, exposure: 1.12, shade: 0.75},
  dawn: {sky: ['#a98a9c', '#e8ad98'], hemi: ['#f0c0b4', '#4e5a42', 1.0], key: ['#ffbf96', 2.3], fill: ['#a7a7d6', 0.35], window: ['#ffd2b8', 1.3], lamp: 0, fog: 0.008, exposure: 1.0, shade: 0.92},
  morning: {sky: ['#d9c4a8', '#f4dcb8'], hemi: ['#e2c2a0', '#5e4635', 0.85], key: ['#ffd29c', 3.2], fill: ['#a99c94', 0.25], window: ['#fff0d6', 2.2], lamp: 0, fog: 0.008, exposure: 1.0, shade: 1},
  day: {sky: ['#8fb6dd', '#dceaf2'], hemi: ['#e8eef5', '#8a8274', 1.15], key: ['#fff4e2', 2.6], fill: ['#c7d6ea', 0.4], window: ['#f2f8ff', 1.8], lamp: 0, fog: 0.006, exposure: 1.0, shade: 1},
  evening: {sky: ['#5b4a72', '#f2a66f'], hemi: ['#e8a98a', '#5a4440', 0.85], key: ['#ffad6b', 2.6], fill: ['#7d78b5', 0.35], window: ['#ffc58f', 1.5], lamp: 0.6, fog: 0.014, exposure: 1.0, shade: 0.9},
  dark: {sky: ['#07090f', '#11151f'], hemi: ['#3a4256', '#26232c', 0.5], key: ['#8090b8', 0.45], fill: ['#40466a', 0.15], window: ['#101a30', 0.5], lamp: 0, fog: 0.02, exposure: 1.1, shade: 0.55},
};

type V3 = [number, number, number];
const shadeOf = (c: string, k: number) => (k >= 0.999 ? c : new THREE.Color(c).multiplyScalar(k).getStyle());

// Boxes and shapes: cast and catch shadows, flat shaded.
export const B: React.FC<{p: V3; s: V3; c: string; r?: V3; glow?: number; noShadow?: boolean}> = ({p, s, c, r, glow, noShadow}) => (
  <mesh position={p} rotation={r} castShadow={!noShadow} receiveShadow>
    <boxGeometry args={s} />
    <primitive object={glow ? mat(c, {emissive: c, glow}) : mat(c)} attach="material" />
  </mesh>
);

const Cyl: React.FC<{p: V3; r1: number; r2: number; h: number; c: string; seg?: number; glow?: number; rot?: V3}> = ({p, r1, r2, h, c, seg = 8, glow, rot}) => (
  <mesh position={p} rotation={rot} castShadow receiveShadow>
    <cylinderGeometry args={[r1, r2, h, seg]} />
    <primitive object={glow ? mat(c, {emissive: c, glow}) : mat(c)} attach="material" />
  </mesh>
);

// A wall that faces into the room only (seen from behind it is not drawn).
const Wall: React.FC<{p: V3; w: number; h: number; ry: number; c: string}> = ({p, w, h, ry, c}) => (
  <mesh position={p} rotation={[0, ry, 0]} receiveShadow>
    <planeGeometry args={[w, h]} />
    <primitive object={mat(c)} attach="material" />
  </mesh>
);

// A window: a frame, its glass showing the light outside, a sill.
const Window: React.FC<{p: V3; w: number; h: number; ry: number; look: Look; frame?: string}> = ({p, w, h, ry, look, frame = '#5a3e2c'}) => (
  <group position={p} rotation={[0, ry, 0]}>
    <mesh position={[0, 0, 0.01]}>
      <planeGeometry args={[w, h]} />
      <meshBasicMaterial color={new THREE.Color(look.window[0]).multiplyScalar(Math.min(1.6, look.window[1]))} toneMapped />
    </mesh>
    <B p={[0, h / 2, 0.05]} s={[w + 0.12, 0.08, 0.1]} c={frame} />
    <B p={[0, -h / 2, 0.08]} s={[w + 0.2, 0.08, 0.18]} c={frame} />
    <B p={[-w / 2, 0, 0.05]} s={[0.08, h, 0.1]} c={frame} />
    <B p={[w / 2, 0, 0.05]} s={[0.08, h, 0.1]} c={frame} />
    <B p={[0, 0.05, 0.04]} s={[w, 0.05, 0.06]} c={frame} />
  </group>
);

// A room: floor, back and side walls (inward), skirting.
const Room: React.FC<{w?: number; d?: number; h?: number; floor: string; wall: string; side?: string; look: Look}> = ({w = 7, d = 6, h = 3.4, floor, wall, side, look}) => {
  const k = look.shade;
  return (
    <group>
      <B p={[0, -0.05, -d / 2 + 3]} s={[w + 6, 0.1, d + 8]} c={shadeOf(floor, k)} noShadow />
      <Wall p={[0, h / 2, -3]} w={w} h={h} ry={0} c={shadeOf(wall, k)} />
      <Wall p={[-w / 2, h / 2, 0]} w={6} h={h} ry={Math.PI / 2} c={shadeOf(side ?? wall, k * 0.94)} />
      <Wall p={[w / 2, h / 2, 0]} w={6} h={h} ry={-Math.PI / 2} c={shadeOf(side ?? wall, k * 0.94)} />
      <B p={[0, 0.06, -2.97]} s={[w, 0.12, 0.04]} c={shadeOf('#e9e1d4', k)} noShadow />
    </group>
  );
};

// Text on a little canvas, for a clock's digits, a note, a calendar page (kept per text).
const textures = new Map<string, THREE.CanvasTexture>();
export const labelTexture = (text: string, fg: string, bg: string, w = 256, h = 128, font = 'bold 80px Anton, Impact, sans-serif') => {
  const key = `${text}|${fg}|${bg}|${w}|${h}|${font}`;
  let t = textures.get(key);
  if (!t) {
    const c = document.createElement('canvas');
    c.width = w;
    c.height = h;
    const g = c.getContext('2d')!;
    g.fillStyle = bg;
    g.fillRect(0, 0, w, h);
    g.fillStyle = fg;
    g.font = font;
    g.textAlign = 'center';
    g.textBaseline = 'middle';
    g.fillText(text, w / 2, h / 2 + 4);
    t = new THREE.CanvasTexture(c);
    t.colorSpace = THREE.SRGBColorSpace;
    textures.set(key, t);
  }
  return t;
};

// A building face: rows of windows, some lit (seeded), drawn once on a canvas.
const facade = (seed: number, lit: number, base: string, glass: string, glow: string) =>
  `${seed}|${lit}|${base}|${glass}|${glow}`;
const facades = new Map<string, THREE.CanvasTexture>();
const facadeTexture = (seed: number, lit: number, base: string, glass: string, glow: string) => {
  const key = facade(seed, lit, base, glass, glow);
  let t = facades.get(key);
  if (!t) {
    const c = document.createElement('canvas');
    c.width = 256;
    c.height = 256;
    const g = c.getContext('2d')!;
    const rand = rng(seed);
    g.fillStyle = base;
    g.fillRect(0, 0, 256, 256);
    for (let y = 18; y < 240; y += 44) {
      for (let x = 16; x < 240; x += 40) {
        g.fillStyle = rand() < lit ? glow : glass;
        g.fillRect(x, y, 24, 28);
      }
    }
    t = new THREE.CanvasTexture(c);
    t.colorSpace = THREE.SRGBColorSpace;
    facades.set(key, t);
  }
  return t;
};

const Building: React.FC<{p: V3; s: V3; seed: number; look: Look; night: boolean}> = ({p, s, seed, look, night}) => {
  const tex = facadeTexture(seed, night ? 0.45 : 0.05, shadeOf(['#7d7f86', '#8c7f74', '#6f7887', '#958a7c'][seed % 4], look.shade), night ? '#232838' : '#9fb3c6', '#ffdca0');
  return (
    <mesh position={p} castShadow receiveShadow>
      <boxGeometry args={s} />
      <meshStandardMaterial map={tex} emissiveMap={night ? tex : null} emissive={night ? '#ffffff' : '#000000'} emissiveIntensity={night ? 0.55 : 0} roughness={0.95} flatShading />
    </mesh>
  );
};

// Low-poly trees: a trunk and one or two faceted crowns.
const Tree: React.FC<{p: V3; seed: number; s?: number; tone?: string}> = ({p, seed, s = 1, tone}) => {
  const rand = rng(seed);
  const crown = tone ?? ['#3f6b38', '#c47a2c', '#2f5532', '#a35a27', '#56803f'][Math.floor(rand() * 5)];
  const g = React.useMemo(() => facetedBall(0.9, 0, 0.18, seed), [seed]);
  return (
    <group position={p} scale={s}>
      <Cyl p={[0, 0.8, 0]} r1={0.1} r2={0.15} h={1.6} c="#5b3b26" seg={5} />
      <mesh geometry={g} position={[0, 2.1, 0]} scale={[1, 1.15, 1]} castShadow receiveShadow>
        <primitive object={mat(crown)} attach="material" />
      </mesh>
    </group>
  );
};

const LampPost: React.FC<{p: V3; look: Look}> = ({p, look}) => (
  <group position={p}>
    <Cyl p={[0, 1.9, 0]} r1={0.05} r2={0.07} h={3.8} c="#2c2d31" seg={6} />
    <B p={[0.3, 3.8, 0]} s={[0.7, 0.06, 0.08]} c="#2c2d31" />
    <B p={[0.55, 3.72, 0]} s={[0.36, 0.1, 0.2]} c="#fff1d6" glow={look.lamp > 0 || look.shade < 0.8 ? 2 : 0.6} />
  </group>
);

// Grass tufts: small faceted cones scattered on a strip.
const Grass: React.FC<{x0: number; x1: number; z0: number; z1: number; seed: number; n: number; c: string}> = ({x0, x1, z0, z1, seed, n, c}) => {
  const ref = React.useRef<THREE.InstancedMesh>(null);
  React.useLayoutEffect(() => {
    const m = ref.current;
    if (!m) return;
    const rand = rng(seed);
    const o = new THREE.Object3D();
    for (let i = 0; i < n; i++) {
      o.position.set(x0 + rand() * (x1 - x0), 0.06, z0 + rand() * (z1 - z0));
      o.rotation.set(0, rand() * 6, 0);
      const k = 0.6 + rand() * 0.8;
      o.scale.set(k, k * (0.8 + rand()), k);
      o.updateMatrix();
      m.setMatrixAt(i, o.matrix);
    }
    m.instanceMatrix.needsUpdate = true;
  }, [x0, x1, z0, z1, seed, n]);
  return (
    <instancedMesh ref={ref} args={[undefined, undefined, n]} receiveShadow>
      <coneGeometry args={[0.06, 0.16, 4]} />
      <primitive object={mat(c)} attach="material" />
    </instancedMesh>
  );
};

const Bed: React.FC<{x: number; look: Look}> = ({x, look}) => {
  const k = look.shade;
  return (
    <group position={[x, 0, -1.55]}>
      <B p={[0, 0.16, 0]} s={[2.05, 0.3, 2.75]} c={shadeOf('#6b4632', k)} />
      <B p={[0, 0.42, 0.02]} s={[1.92, 0.24, 2.62]} c={shadeOf('#8d96a3', k)} />
      <B p={[0, 0.72, -1.36]} s={[2.1, 1.12, 0.12]} c={shadeOf('#6b4632', k)} />
      <B p={[0, 0.62, -1.0]} s={[0.85, 0.16, 0.45]} c={shadeOf('#eeebe6', k)} />
    </group>
  );
};

const Chair: React.FC<{p: V3; ry: number; c?: string}> = ({p, ry, c = '#7a5238'}) => (
  <group position={p} rotation={[0, ry, 0]}>
    <B p={[0, 0.44, 0]} s={[0.5, 0.07, 0.5]} c={c} />
    <B p={[0, 0.85, -0.23]} s={[0.5, 0.75, 0.06]} c={c} />
    {[-0.21, 0.21].map((a) => [-0.21, 0.21].map((b) => <B key={`${a}${b}`} p={[a, 0.2, b]} s={[0.05, 0.42, 0.05]} c={c} />))}
  </group>
);

const Table: React.FC<{p: V3; s: [number, number, number]; c?: string}> = ({p, s, c = '#8a5f40'}) => (
  <group position={p}>
    <B p={[0, s[1] - 0.04, 0]} s={[s[0], 0.08, s[2]]} c={c} />
    {[-1, 1].map((a) => [-1, 1].map((b) => <B key={`${a}${b}`} p={[a * (s[0] / 2 - 0.08), (s[1] - 0.08) / 2, b * (s[2] / 2 - 0.08)]} s={[0.07, s[1] - 0.08, 0.07]} c={c} />))}
  </group>
);

const Sky: React.FC<{look: Look; r?: number; deep?: number}> = ({look, r = 140, deep = 0.6}) => {
  const g = React.useMemo(() => {
    const geo = new THREE.SphereGeometry(r, 24, 12);
    const top = new THREE.Color(look.sky[0]);
    const hor = new THREE.Color(look.sky[1]);
    const cols: number[] = [];
    const pos = geo.attributes.position;
    for (let i = 0; i < pos.count; i++) {
      const y = Math.max(0, pos.getY(i) / r);
      const c = hor.clone().lerp(top, Math.pow(y, deep));
      cols.push(c.r, c.g, c.b);
    }
    geo.setAttribute('color', new THREE.Float32BufferAttribute(cols, 3));
    return geo;
  }, [look.sky, r, deep]);
  return (
    <mesh geometry={g}>
      <meshBasicMaterial vertexColors side={THREE.BackSide} toneMapped={false} fog={false} />
    </mesh>
  );
};

const Mountains: React.FC<{z: number; seed: number; c: string}> = ({z, seed, c}) => {
  const rand = rng(seed);
  const peaks = Array.from({length: 9}, (_, i) => ({x: -60 + i * 15 + rand() * 8, h: 10 + rand() * 12, r: 12 + rand() * 8}));
  return (
    <group>
      {peaks.map((m, i) => (
        <mesh key={i} position={[m.x, m.h / 2 - 1, z - rand() * 15]} receiveShadow>
          <coneGeometry args={[m.r, m.h, 5]} />
          <primitive object={mat(c)} attach="material" />
        </mesh>
      ))}
    </group>
  );
};

const night = (look: Look) => look.shade < 0.8;

// ---------------------------------------------------------------- the places

const bedroom: SetDef = {
  lamp: [0.95, 1.0, -2.55],
  spots: {
    bed: {x: -0.6, z: -1.45, ry: 0, bed: 0.55, seat: 0.55, stand: [-0.6, 0.15]},
    center: {x: 0.6, z: 0.5, ry: 0},
    left: {x: -1.6, z: 0.6, ry: 0},
    right: {x: 1.8, z: 0.2, ry: 0},
    window: {x: 2.5, z: -1.0, ry: Math.PI / 2},
    door: {x: -2.6, z: 1.0, ry: Math.PI / 2},
    chair: {x: -0.6, z: -0.35, ry: 0, seat: 0.55, stand: [-0.6, 0.3]},
  },
  wide: {pos: [2.9, 3.0, 3.4], look: [-0.5, 0.5, -1.3]},
  sun: [6, 4.5, -0.4],
  outdoor: false,
  walk: 'x',
  surface: [0.75, 0.58, -2.5],
  Draw: ({look}) => (
    <group>
      <Room floor="#8a6a52" wall="#cdb8a3" look={look} />
      <Bed x={-0.6} look={look} />
      <B p={[0.75, 0.27, -2.5]} s={[0.55, 0.54, 0.45]} c={shadeOf('#7c5439', look.shade)} />
      <Cyl p={[0.95, 0.66, -2.62]} r1={0.06} r2={0.08} h={0.16} c="#d9d2c4" seg={6} />
      <Cyl p={[0.95, 0.86, -2.62]} r1={0.12} r2={0.18} h={0.22} c="#f4e3c4" seg={6} glow={look.lamp > 0 ? 1.4 : 0} />
      <Window p={[3.48, 1.65, -1.0]} w={1.5} h={1.25} ry={-Math.PI / 2} look={look} />
      <B p={[-0.6, 0.012, 0.75]} s={[1.7, 0.02, 1.15]} c={shadeOf('#b0583f', look.shade)} noShadow />
      <B p={[-3.1, 1.15, -1.2]} s={[0.6, 2.3, 1.3]} c={shadeOf('#9c7556', look.shade)} />
      <B p={[-2.79, 1.15, -1.2]} s={[0.02, 2.1, 0.02]} c="#5a3e2c" />
      <B p={[1.9, 1.9, -2.95]} s={[0.9, 0.65, 0.04]} c={shadeOf('#7d8d94', look.shade)} />
    </group>
  ),
};

const hallway: SetDef = {
  spots: {
    door: {x: 0, z: -2.1, ry: Math.PI},
    center: {x: 0.3, z: 0.2, ry: 0},
    chair: {x: -2.2, z: -0.9, ry: Math.PI / 2, seat: 0.47, stand: [-1.55, -0.9]},
    left: {x: -1.2, z: 0.4, ry: 0},
    right: {x: 1.4, z: 0.3, ry: 0},
  },
  wide: {pos: [2.6, 2.8, 3.2], look: [-0.4, 0.8, -1.5]},
  sun: [-5, 4, 3],
  outdoor: false,
  walk: 'x',
  surface: [-2.4, 0.5, -0.4],
  Draw: ({look}) => (
    <group>
      <Room floor="#a07c5c" wall="#d6c7b4" look={look} />
      <B p={[0, 1.15, -2.96]} s={[1.15, 2.3, 0.08]} c={shadeOf('#6e4b35', look.shade)} />
      <B p={[0.42, 1.1, -2.9]} s={[0.07, 0.07, 0.06]} c="#c9a84a" />
      <B p={[0, 0.01, -2.4]} s={[1.2, 0.02, 0.6]} c={shadeOf('#5f6b54', look.shade)} noShadow />
      <B p={[-2.35, 0.25, -0.9]} s={[0.5, 0.45, 1.6]} c={shadeOf('#8d6a4f', look.shade)} />
      <B p={[-1.6, 0.28, -2.75]} s={[1.1, 0.55, 0.4]} c={shadeOf('#8d6a4f', look.shade)} />
      {[-1.95, -1.6, -1.25].map((x, i) => (
        <B key={x} p={[x, 0.62, -2.72]} s={[0.24, 0.12, 0.34]} c={['#eeece7', '#2c3e57', '#9a4b3a'][i]} />
      ))}
      <B p={[1.6, 1.95, -2.92]} s={[1.0, 0.06, 0.06]} c="#5a3e2c" />
      <B p={[1.35, 1.45, -2.82]} s={[0.42, 0.9, 0.16]} c={shadeOf('#41505e', look.shade)} />
      <B p={[1.85, 1.5, -2.82]} s={[0.38, 0.8, 0.16]} c={shadeOf('#8a6b3c', look.shade)} />
      <Window p={[-3.48, 1.7, 1.2]} w={1.0} h={1.1} ry={Math.PI / 2} look={look} />
    </group>
  ),
};

const street: SetDef = {
  spots: {center: {x: 0, z: -0.7, ry: Math.PI / 2}, left: {x: -1.5, z: -0.7, ry: Math.PI / 2}, right: {x: 1.5, z: -0.7, ry: Math.PI / 2}, door: {x: 0, z: -1.6, ry: Math.PI}},
  wide: {pos: [3, 2.6, 5.5], look: [0, 1.2, -1.5]},
  sun: [3, 6, 6],
  outdoor: true,
  walk: 'x',
  road: 2.8,
  reach: 120,
  surface: [0, 0, -0.4],
  Draw: ({look, seed}) => {
    const n = night(look);
    const k = look.shade;
    const xs = Array.from({length: 40}, (_, i) => -64 + i * 3.2);
    return (
      <group>
        <Sky look={look} />
        <B p={[0, -0.05, -0.6]} s={[140, 0.1, 3.2]} c={shadeOf('#6e7179', k)} noShadow />
        <B p={[0, 0.04, 1.05]} s={[140, 0.12, 0.2]} c={shadeOf('#9a9ca2', k)} />
        <B p={[0, -0.1, 5]} s={[140, 0.1, 8]} c={shadeOf('#2f3238', k)} noShadow />
        <Wall p={[0, 3.5, -2.2]} w={140} h={7} ry={0} c={shadeOf('#5d6068', k)} />
        {xs.map((x, i) => (
          <group key={x}>
            <mesh position={[x, 1.75, -2.18]}>
              <planeGeometry args={[2.5, 2.3]} />
              <meshBasicMaterial color={n ? new THREE.Color('#fff4e0').multiplyScalar(1.15) : new THREE.Color('#e9eef3').multiplyScalar(0.9)} />
            </mesh>
            <B p={[x + 1.6, 3.5, -2.1]} s={[0.22, 7, 0.16]} c={shadeOf('#4c4f57', k)} />
            {i % 3 === 0 ? <B p={[x, 4.6, -2.16]} s={[2.0, 1.2, 0.04]} c={n ? '#ffe9c4' : '#b9c4cf'} glow={n ? 1.2 : 0} /> : null}
          </group>
        ))}
        {[-24, 0, 24].map((x) => (
          <LampPost key={x} p={[x + 4, 0, 0.8]} look={look} />
        ))}
        {[-40, -20, 20, 40].map((x, i) => (
          <Building key={x} p={[x, 6, -14]} s={[12, 12 + (i % 2) * 6, 6]} seed={seed + i} look={look} night={n} />
        ))}
      </group>
    );
  },
};

const park: SetDef = {
  spots: {center: {x: 0, z: 0, ry: 0}, left: {x: -0.5, z: 0, ry: 0}, right: {x: 0.5, z: 0, ry: 0}, chair: {x: 2.0, z: -1.0, ry: -Math.PI / 2, seat: 0.45, stand: [1.35, -1.0]}, far: {x: 0, z: -12, ry: 0}},
  wide: {pos: [3.5, 3.2, 6], look: [0, 0.8, -3]},
  sun: [-3, 5, -20],
  outdoor: true,
  walk: 'z',
  reach: 70,
  surface: [2.3, 0.45, -1],
  Draw: ({look, seed}) => {
    const rand = rng(seed + 11);
    const trees = Array.from({length: 26}, (_, i) => ({
      x: (i % 2 ? 1 : -1) * (2.4 + rand() * 6),
      z: -70 + i * 3.3 + rand() * 2,
      s: 0.9 + rand() * 0.6,
    }));
    return (
      <group>
        <Sky look={look} />
        <B p={[0, -0.05, -20]} s={[120, 0.1, 140]} c={shadeOf('#4f7a3e', look.shade)} noShadow />
        <B p={[0, 0.005, -20]} s={[1.9, 0.02, 140]} c={shadeOf('#b46d5c', look.shade)} noShadow />
        <B p={[-1.0, 0.02, -20]} s={[0.1, 0.04, 140]} c={shadeOf('#c9c3b6', look.shade)} noShadow />
        <B p={[1.0, 0.02, -20]} s={[0.1, 0.04, 140]} c={shadeOf('#c9c3b6', look.shade)} noShadow />
        <Grass x0={-8} x1={-1.1} z0={-30} z1={8} seed={seed} n={900} c={shadeOf('#3e6a32', look.shade)} />
        <Grass x0={1.1} x1={8} z0={-30} z1={8} seed={seed + 1} n={900} c={shadeOf('#3e6a32', look.shade)} />
        {trees.map((t, i) => (
          <Tree key={i} p={[t.x, 0, t.z]} seed={seed + i * 3} s={t.s} />
        ))}
        {[-36, -18, 0].map((z) => (
          <LampPost key={z} p={[-1.5, 0, z + 2]} look={look} />
        ))}
        <group position={[2.0, 0, -1.0]} rotation={[0, -Math.PI / 2, 0]}>
          <B p={[0, 0.42, 0]} s={[1.5, 0.08, 0.45]} c="#7a5238" />
          <B p={[0, 0.75, -0.2]} s={[1.5, 0.35, 0.06]} c="#7a5238" />
          <B p={[-0.6, 0.2, 0]} s={[0.08, 0.4, 0.4]} c="#2c2d31" />
          <B p={[0.6, 0.2, 0]} s={[0.08, 0.4, 0.4]} c="#2c2d31" />
        </group>
        <Mountains z={-85} seed={seed} c={shadeOf('#2f4a33', look.shade * 0.9)} />
      </group>
    );
  },
};

const kitchen: SetDef = {
  lamp: [0, 2.1, -1.8],
  spots: {
    counter: {x: 0.2, z: -1.95, ry: Math.PI},
    chair: {x: -1.45, z: -0.2, ry: Math.PI / 2, seat: 0.48, stand: [-1.45, 0.5]},
    center: {x: 0.9, z: 0.6, ry: 0},
    left: {x: -1.5, z: 0.9, ry: 0},
    right: {x: 1.9, z: 0.4, ry: 0},
    window: {x: 0.2, z: -1.95, ry: Math.PI},
    desk: {x: -1.45, z: -0.2, ry: Math.PI / 2, seat: 0.48, stand: [-1.45, 0.5]},
  },
  wide: {pos: [2.9, 2.9, 3.4], look: [-0.4, 0.6, -1.2]},
  sun: [-1, 5, -6],
  outdoor: false,
  walk: 'x',
  surface: [-0.55, 0.79, -0.2],
  Draw: ({look}) => (
    <group>
      <Room floor="#9b8a74" wall="#d9cdb9" look={look} />
      <B p={[0, 0.45, -2.65]} s={[4.2, 0.9, 0.65]} c={shadeOf('#e6dfd2', look.shade)} />
      <B p={[0, 0.93, -2.65]} s={[4.3, 0.06, 0.7]} c={shadeOf('#7f7a73', look.shade)} />
      <B p={[-1.4, 2.35, -2.8]} s={[1.3, 0.7, 0.35]} c={shadeOf('#e6dfd2', look.shade)} />
      <B p={[1.4, 2.35, -2.8]} s={[1.3, 0.7, 0.35]} c={shadeOf('#e6dfd2', look.shade)} />
      <Window p={[0, 1.85, -2.98]} w={1.2} h={0.9} ry={0} look={look} />
      <B p={[2.75, 1.05, -2.45]} s={[0.85, 2.1, 0.8]} c={shadeOf('#cfd3d6', look.shade)} />
      <B p={[2.4, 1.3, -2.04]} s={[0.04, 0.5, 0.04]} c="#8d9196" />
      <Table p={[-0.55, 0, -0.2]} s={[1.3, 0.78, 0.85]} />
      <Chair p={[-1.45, 0, -0.2]} ry={Math.PI / 2} />
      <Chair p={[0.35, 0, -0.2]} ry={-Math.PI / 2} />
    </group>
  ),
};

const living: SetDef = {
  lamp: [2.6, 1.75, -2.5],
  spots: {
    couch: {x: -2.35, z: -0.8, ry: Math.PI / 2, seat: 0.47, stand: [-1.7, -0.8]},
    chair: {x: -0.1, z: -2.1, ry: 0.3, seat: 0.47, stand: [0.09, -1.48]},
    center: {x: 0.5, z: 0.4, ry: 0},
    window: {x: 0.3, z: -2.0, ry: Math.PI},
    left: {x: -1.0, z: 0.8, ry: 0},
    right: {x: 1.8, z: 0.4, ry: 0},
  },
  wide: {pos: [2.8, 2.9, 3.4], look: [-0.8, 0.5, -1.0]},
  sun: [1, 5, -6],
  outdoor: false,
  walk: 'x',
  surface: [-1.25, 0.46, -0.8],
  Draw: ({look}) => {
    const tv = look.lamp > 0 || look.shade < 0.8;
    return (
      <group>
        <Room floor="#8d7059" wall="#c9c2b6" look={look} />
        <group position={[-2.85, 0, -0.8]}>
          <B p={[0.1, 0.24, 0]} s={[0.95, 0.45, 2.4]} c={shadeOf('#4f6170', look.shade)} />
          <B p={[-0.35, 0.65, 0]} s={[0.28, 0.85, 2.4]} c={shadeOf('#4f6170', look.shade)} />
          <B p={[0.1, 0.4, -1.15]} s={[0.95, 0.55, 0.2]} c={shadeOf('#475866', look.shade)} />
          <B p={[0.1, 0.4, 1.15]} s={[0.95, 0.55, 0.2]} c={shadeOf('#475866', look.shade)} />
          <B p={[-0.1, 0.62, 0.6]} s={[0.25, 0.35, 0.45]} c={shadeOf('#c46a63', look.shade)} r={[0, 0, 0.2]} />
        </group>
        <Table p={[-1.25, 0, -0.8]} s={[0.7, 0.42, 1.2]} c="#6b4a33" />
        <group position={[-0.1, 0, -2.1]} rotation={[0, 0.3, 0]}>
          <B p={[0, 0.24, 0.05]} s={[0.95, 0.45, 0.85]} c={shadeOf('#b08a4a', look.shade)} />
          <B p={[0, 0.7, -0.38]} s={[0.95, 0.75, 0.2]} c={shadeOf('#b08a4a', look.shade)} />
          <B p={[-0.43, 0.45, 0.05]} s={[0.16, 0.45, 0.85]} c={shadeOf('#9c7a40', look.shade)} />
          <B p={[0.43, 0.45, 0.05]} s={[0.16, 0.45, 0.85]} c={shadeOf('#9c7a40', look.shade)} />
        </group>
        <B p={[3.2, 0.3, -0.8]} s={[0.5, 0.6, 1.8]} c={shadeOf('#3d3a37', look.shade)} />
        <B p={[3.15, 1.25, -0.8]} s={[0.08, 0.85, 1.5]} c="#16171a" />
        <B p={[3.1, 1.25, -0.8]} s={[0.02, 0.75, 1.4]} c="#9cc6ff" glow={tv ? 1.3 : 0.15} r={[0, 0, 0]} />
        <Window p={[0.3, 1.7, -2.98]} w={1.6} h={1.2} ry={0} look={look} />
        <B p={[-1.25, 0.012, -0.8]} s={[1.6, 0.02, 2.2]} c={shadeOf('#a4835f', look.shade)} noShadow />
        <Cyl p={[2.6, 0.8, -2.6]} r1={0.03} r2={0.05} h={1.6} c="#2c2d31" />
        <Cyl p={[2.6, 1.7, -2.6]} r1={0.15} r2={0.24} h={0.3} c="#f4e3c4" glow={look.lamp > 0 ? 1.4 : 0} />
      </group>
    );
  },
};

const office: SetDef = {
  lamp: [1.3, 1.5, -1.2],
  spots: {
    desk: {x: 0.3, z: -1.2, ry: Math.PI / 2, seat: 0.5, stand: [0.3, -0.5]},
    chair: {x: 0.3, z: -1.2, ry: Math.PI / 2, seat: 0.5, stand: [0.3, -0.5]},
    center: {x: -0.6, z: 0.5, ry: 0},
    window: {x: -1.5, z: -2.0, ry: Math.PI},
    left: {x: -1.8, z: 0.6, ry: 0},
    right: {x: 1.0, z: 0.8, ry: 0},
    door: {x: -2.6, z: 0.8, ry: Math.PI / 2},
  },
  wide: {pos: [-2.6, 2.8, 3.2], look: [0.6, 0.6, -1.3]},
  sun: [-6, 5, -1],
  outdoor: false,
  walk: 'x',
  surface: [1.35, 0.78, -1.55],
  Draw: ({look}) => {
    const on = true;
    return (
      <group>
        <Room floor="#6f7378" wall="#c7c9c6" look={look} />
        <Table p={[1.35, 0, -1.2]} s={[0.85, 0.76, 1.8]} c="#a98c6c" />
        <B p={[1.5, 1.08, -1.2]} s={[0.06, 0.52, 0.85]} c="#1b1c20" />
        <B p={[1.465, 1.08, -1.2]} s={[0.01, 0.46, 0.79]} c="#a9cdfa" glow={on ? 1.2 : 0} />
        <B p={[1.55, 0.84, -1.2]} s={[0.18, 0.06, 0.25]} c="#1b1c20" />
        <B p={[1.1, 0.79, -1.2]} s={[0.22, 0.02, 0.6]} c="#2a2b30" />
        <group position={[0.3, 0, -1.2]}>
          <Cyl p={[0, 0.25, 0]} r1={0.05} r2={0.05} h={0.45} c="#2a2b30" />
          <B p={[0, 0.5, 0]} s={[0.55, 0.08, 0.55]} c="#2f3a48" />
          <B p={[-0.28, 0.9, 0]} s={[0.07, 0.75, 0.52]} c="#2f3a48" />
          <B p={[0, 0.04, 0]} s={[0.6, 0.06, 0.08]} c="#2a2b30" />
          <B p={[0, 0.04, 0]} s={[0.08, 0.06, 0.6]} c="#2a2b30" />
        </group>
        <Window p={[-1.5, 1.75, -2.98]} w={1.8} h={1.3} ry={0} look={look} />
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <B key={i} p={[-1.5, 1.2 + i * 0.22, -2.92]} s={[1.8, 0.03, 0.03]} c="#d9d6cf" noShadow />
        ))}
        <B p={[2.9, 1.0, -2.6]} s={[0.9, 2.0, 0.5]} c={shadeOf('#8a7056', look.shade)} />
        <Cyl p={[-3.0, 0.25, -2.5]} r1={0.22} r2={0.17} h={0.5} c="#b6603f" seg={7} />
        <mesh position={[-3.0, 0.9, -2.5]} castShadow>
          <icosahedronGeometry args={[0.42, 0]} />
          <primitive object={mat('#3f6b38')} attach="material" />
        </mesh>
      </group>
    );
  },
};

const bathroom: SetDef = {
  spots: {mirror: {x: 0, z: -2.0, ry: Math.PI}, center: {x: 0.4, z: 0.3, ry: 0}, left: {x: -1.4, z: 0.4, ry: 0}, right: {x: 1.5, z: 0.4, ry: 0}, door: {x: -2.6, z: 0.8, ry: Math.PI / 2}},
  wide: {pos: [2.5, 2.8, 3.0], look: [-0.2, 0.9, -1.6]},
  sun: [-5, 5, -1],
  outdoor: false,
  walk: 'x',
  surface: [0, 0.92, -2.65],
  Draw: ({look}) => (
    <group>
      <Room floor="#c9c6bf" wall="#b8cacc" look={look} />
      <B p={[0, 0.45, -2.68]} s={[1.3, 0.9, 0.6]} c={shadeOf('#e9e5dc', look.shade)} />
      <B p={[0, 0.92, -2.65]} s={[0.7, 0.06, 0.45]} c="#f4f3ef" />
      <B p={[0, 1.75, -2.96]} s={[1.1, 1.0, 0.04]} c={shadeOf('#9fb2bb', look.shade * 1.05)} />
      <B p={[0, 1.75, -2.97]} s={[1.2, 1.1, 0.02]} c="#6c6a66" />
      <B p={[2.6, 0.3, -2.0]} s={[1.6, 0.6, 1.8]} c={shadeOf('#eeece6', look.shade)} />
      <Window p={[-3.48, 1.9, -1.2]} w={0.9} h={0.7} ry={Math.PI / 2} look={look} />
    </group>
  ),
};

const gym: SetDef = {
  spots: {center: {x: 0, z: -0.4, ry: 0}, chair: {x: -1.6, z: -1.4, ry: 0, seat: 0.45, stand: [-1.6, -0.75]}, left: {x: -1.4, z: 0.4, ry: 0}, right: {x: 1.4, z: 0.4, ry: 0}, mirror: {x: 0.6, z: -1.9, ry: Math.PI}},
  wide: {pos: [2.9, 2.8, 3.6], look: [-0.3, 0.7, -1.3]},
  sun: [5, 6, 2],
  outdoor: false,
  walk: 'x',
  surface: [2.4, 0.5, -2.4],
  Draw: ({look}) => (
    <group>
      <Room floor="#3d4046" wall="#b9b4ab" look={look} />
      <B p={[0, 1.4, -2.95]} s={[5.5, 1.8, 0.04]} c={shadeOf('#a9bac2', look.shade)} />
      <B p={[-1.6, 0.4, -1.4]} s={[0.45, 0.1, 1.4]} c="#20232a" />
      <B p={[-1.6, 0.2, -1.4]} s={[0.12, 0.35, 1.0]} c="#555" />
      <B p={[2.4, 0.45, -2.4]} s={[1.6, 0.06, 0.5]} c="#505257" />
      {[1.8, 2.15, 2.5, 2.85].map((x) => (
        <group key={x}>
          <B p={[x, 0.55, -2.4]} s={[0.12, 0.12, 0.3]} c="#22252a" />
        </group>
      ))}
      <B p={[0.5, 0.01, 0.2]} s={[1.0, 0.03, 2.0]} c={shadeOf('#4f6d8c', look.shade)} noShadow />
      <B p={[-2.9, 2.1, -1.0]} s={[0.04, 0.9, 0.7]} c="#d1793d" />
    </group>
  ),
};

const cafe: SetDef = {
  lamp: [0, 2.0, -1.2],
  spots: {
    chair: {x: -1.35, z: -0.6, ry: Math.PI / 2, seat: 0.48, stand: [-1.35, 0.1]},
    counter: {x: 0.8, z: -1.6, ry: Math.PI},
    center: {x: 0.4, z: 0.6, ry: 0},
    left: {x: -1.6, z: 0.7, ry: 0},
    right: {x: 1.6, z: 0.6, ry: 0},
    window: {x: -2.6, z: 0.6, ry: -Math.PI / 2},
  },
  wide: {pos: [2.8, 2.8, 3.4], look: [-0.5, 0.6, -1.2]},
  sun: [-6, 4, 1],
  outdoor: false,
  walk: 'x',
  surface: [-0.55, 0.75, -0.6],
  Draw: ({look}) => (
    <group>
      <Room floor="#7d5a40" wall="#c8a98a" side="#b98f6c" look={look} />
      <B p={[1.0, 0.55, -2.55]} s={[3.4, 1.1, 0.7]} c={shadeOf('#5b3b26', look.shade)} />
      <B p={[1.0, 1.12, -2.55]} s={[3.5, 0.05, 0.75]} c="#d8d2c6" />
      <B p={[2.1, 1.4, -2.6]} s={[0.5, 0.55, 0.4]} c="#9aa0a8" />
      {[-1.4, 0, 1.4].map((x) => (
        <group key={x}>
          <Cyl p={[x, 2.7, -1.2]} r1={0.01} r2={0.01} h={1.2} c="#222" seg={4} />
          <Cyl p={[x, 2.05, -1.2]} r1={0.08} r2={0.25} h={0.22} c="#e8b04d" glow={0.8 + look.lamp * 0.4} />
        </group>
      ))}
      <Cyl p={[-0.55, 0.37, -0.6]} r1={0.45} r2={0.45} h={0.05} c="#e3dbcd" seg={10} />
      <Cyl p={[-0.55, 0.0, -0.6]} r1={0.04} r2={0.04} h={0.74} c="#2a2b30" seg={6} />
      <B p={[-0.55, 0.74, -0.6]} s={[0.9, 0.04, 0.9]} c="#e3dbcd" noShadow />
      <Chair p={[-1.35, 0, -0.6]} ry={Math.PI / 2} c="#3b3d42" />
      <Chair p={[0.3, 0, -0.6]} ry={-Math.PI / 2} c="#3b3d42" />
      <Window p={[-3.48, 1.6, 0.4]} w={2.4} h={1.6} ry={Math.PI / 2} look={look} />
    </group>
  ),
};

const busstop: SetDef = {
  spots: {chair: {x: 0, z: -1.5, ry: 0, seat: 0.46, stand: [0, -0.85]}, center: {x: 1.4, z: -0.5, ry: 0}, left: {x: -1.6, z: -0.5, ry: 0}, right: {x: 2.4, z: -0.4, ry: -Math.PI / 2}},
  wide: {pos: [3.2, 2.6, 5.0], look: [0, 1.0, -1.5]},
  sun: [5, 6, -3],
  outdoor: true,
  walk: 'x',
  road: 2.8,
  reach: 120,
  surface: [0.7, 0.47, -1.5],
  Draw: ({look, seed}) => {
    const n = night(look);
    return (
      <group>
        <Sky look={look} />
        <B p={[0, -0.05, -2]} s={[140, 0.1, 6]} c={shadeOf('#74777e', look.shade)} noShadow />
        <B p={[0, 0.04, 1.0]} s={[140, 0.12, 0.2]} c={shadeOf('#9a9ca2', look.shade)} />
        <B p={[0, -0.1, 6]} s={[140, 0.1, 10]} c={shadeOf('#30333a', look.shade)} noShadow />
        <B p={[0, 1.2, -2.05]} s={[3.4, 2.4, 0.04]} c="#a8c3cf" />
        <B p={[0, 2.45, -1.6]} s={[3.6, 0.1, 1.2]} c="#3a3d44" />
        <B p={[-1.75, 1.2, -1.6]} s={[0.08, 2.4, 0.08]} c="#3a3d44" />
        <B p={[1.75, 1.2, -1.6]} s={[0.08, 2.4, 0.08]} c="#3a3d44" />
        <B p={[0, 0.44, -1.55]} s={[2.2, 0.07, 0.4]} c="#7a5238" />
        <Cyl p={[2.4, 1.3, -0.8]} r1={0.04} r2={0.04} h={2.6} c="#2c2d31" seg={6} />
        <B p={[2.4, 2.5, -0.8]} s={[0.5, 0.5, 0.04]} c="#2f6db5" />
        <LampPost p={[-3.5, 0, 0.6]} look={look} />
        {[-30, -15, 0, 15, 30].map((x, i) => (
          <Building key={x} p={[x, 7, -12]} s={[12, 14 + (i % 3) * 4, 6]} seed={seed + i} look={look} night={n} />
        ))}
      </group>
    );
  },
};

const rooftop: SetDef = {
  spots: {center: {x: 0, z: -1.6, ry: Math.PI}, left: {x: -1.4, z: -0.5, ry: 0}, right: {x: 1.4, z: -0.5, ry: 0}, chair: {x: 0, z: -2.05, ry: 0, seat: 0.9, stand: [0, -1.4]}},
  wide: {pos: [3, 2.6, 4.2], look: [0, 1.0, -2.5]},
  sun: [-4, 4, -12],
  outdoor: true,
  walk: 'x',
  reach: 64,
  drive: 2.6, // a vehicle under way runs along the roofs' open side, clear of the parapet and of where people stand
  jumpAt: 6.0, // the roof's edge before the gap
  gap: [7, 10],
  surface: [1.2, 0.9, -2.3],
  Draw: ({look, seed}) => {
    const n = night(look);
    const rand = rng(seed + 5);
    return (
      <group>
        <Sky look={look} />
        <B p={[0, -0.05, 0.6]} s={[14, 0.1, 9.2]} c={shadeOf('#8d8a84', look.shade)} noShadow />
        {/* the next roofs along, across a gap to the street far below (a car can jump it) */}
        {/* the roof goes on to the left; to the right, past a gap over the street far below, the next roof (a car
            can jump it at jumpAt) */}
        {[[-29.5, 45], [31, 42]].map(([x, len]) => (
          <group key={x}>
            <B p={[x, -0.05, 0.6]} s={[len, 0.1, 9.2]} c={shadeOf('#86837d', look.shade)} noShadow />
            <B p={[x, -6, 0.6]} s={[len, 11.9, 9.1]} c={shadeOf('#5f6168', look.shade)} />
            <B p={[x, 0.45, -2.4]} s={[len, 0.9, 0.3]} c={shadeOf('#a29d94', look.shade)} />
          </group>
        ))}
        <B p={[0, -6, 0.6]} s={[14, 11.9, 9.1]} c={shadeOf('#666870', look.shade)} />
        <B p={[0, 0.45, -2.4]} s={[14, 0.9, 0.3]} c={shadeOf('#a29d94', look.shade)} />
        {/* a vent housing, by the parapet and out of the cars' way (it stood in their lane) */}
        <B p={[-4.6, 0.6, -1.7]} s={[1.2, 1.2, 1.0]} c={shadeOf('#9a968e', look.shade)} />
        {Array.from({length: 18}, (_, i) => {
          const x = -60 + i * 7 + rand() * 3;
          const h = 10 + rand() * 30;
          return <Building key={i} p={[x, h / 2 - 20, -40 - rand() * 30]} s={[6, h, 6]} seed={seed + i} look={look} night={n} />;
        })}
      </group>
    );
  },
};

const voidSet: SetDef = {
  spots: {center: {x: 0, z: 0, ry: 0}, left: {x: -1.2, z: 0, ry: 0}, right: {x: 1.2, z: 0, ry: 0}, chair: {x: 0, z: 0, ry: 0, seat: 0.46, stand: [0, 0.65]}},
  wide: {pos: [2.6, 2.6, 4.2], look: [0, 0.9, 0]},
  sun: [4, 6, 3],
  outdoor: false,
  walk: 'x',
  surface: [0.8, 0, 0.3],
  Draw: ({look}) => (
    <group>
      <B p={[0, -0.05, 0]} s={[60, 0.1, 60]} c={shadeOf('#c8b6a2', look.shade)} noShadow />
      <Wall p={[0, 8, -6]} w={60} h={16} ry={0} c={shadeOf('#d2c2ae', look.shade)} />
    </group>
  ),
};

// ---------------------------------------------------------------- places for action and fiction

// Bricks on a canvas (rows offset by half a brick, a seeded shade per brick), repeated along a wall.
const bricks = new Map<string, THREE.CanvasTexture>();
const brickTexture = (base: string, seed: number, rx: number, ry: number) => {
  const key = `${base}|${seed}|${rx}|${ry}`;
  let t = bricks.get(key);
  if (!t) {
    const c = document.createElement('canvas');
    c.width = 256;
    c.height = 256;
    const g = c.getContext('2d')!;
    const rand = rng(seed);
    g.fillStyle = '#3a2f2a';
    g.fillRect(0, 0, 256, 256);
    const col = new THREE.Color(base);
    for (let row = 0; row < 16; row++) {
      for (let b = -1; b < 5; b++) {
        const x = b * 64 + (row % 2 ? 32 : 0);
        const k = 0.8 + rand() * 0.35;
        g.fillStyle = col.clone().multiplyScalar(k).getStyle();
        g.fillRect(x + 2, row * 16 + 2, 60, 12);
      }
    }
    t = new THREE.CanvasTexture(c);
    t.wrapS = t.wrapT = THREE.RepeatWrapping;
    t.repeat.set(rx, ry);
    t.colorSpace = THREE.SRGBColorSpace;
    bricks.set(key, t);
  }
  return t;
};

const BrickWall: React.FC<{p: V3; w: number; h: number; ry: number; look: Look; seed: number}> = ({p, w, h, ry, look, seed}) => (
  <mesh position={p} rotation={[0, ry, 0]} receiveShadow>
    <planeGeometry args={[w, h]} />
    <meshStandardMaterial map={brickTexture(shadeOf('#8a4a36', look.shade), seed, w / 3, h / 3)} roughness={0.95} />
  </mesh>
);

// A steel girder: an I-beam along x (flanges and a web), in a primer red or steel grey.
export const Girder: React.FC<{p: V3; len: number; r?: V3; c?: string}> = ({p, len, r, c = '#b5532f'}) => (
  <group position={p} rotation={r}>
    <B p={[0, 0.11, 0]} s={[len, 0.04, 0.26]} c={c} />
    <B p={[0, -0.11, 0]} s={[len, 0.04, 0.26]} c={c} />
    <B p={[0, 0, 0]} s={[len, 0.22, 0.05]} c={c} />
  </group>
);

const Barrier: React.FC<{p: V3; ry?: number}> = ({p, ry = 0}) => (
  <group position={p} rotation={[0, ry, 0]}>
    {[-0.9, -0.3, 0.3, 0.9].map((x, i) => (
      <B key={x} p={[x, 0.85, 0]} s={[0.6, 0.22, 0.06]} c={i % 2 ? '#f2f0ea' : '#e2632a'} />
    ))}
    <B p={[-1.1, 0.5, 0]} s={[0.07, 1.0, 0.07]} c="#3a3d44" />
    <B p={[1.1, 0.5, 0]} s={[0.07, 1.0, 0.07]} c="#3a3d44" />
    <B p={[-1.1, 0.04, 0]} s={[0.12, 0.08, 0.6]} c="#3a3d44" />
    <B p={[1.1, 0.04, 0]} s={[0.12, 0.08, 0.6]} c="#3a3d44" />
  </group>
);

const construction: SetDef = {
  spots: {
    center: {x: 0, z: 0, ry: 0},
    left: {x: -2.0, z: 0.3, ry: 0},
    right: {x: 2.0, z: 0.3, ry: 0},
    far: {x: 0, z: -7, ry: 0},
    chair: {x: 3.4, z: -1.4, ry: -Math.PI / 2, seat: 0.6, stand: [2.75, -1.4]},
    door: {x: -4.2, z: -2.6, ry: Math.PI},
  },
  wide: {pos: [4.8, 3.6, 7.5], look: [0, 1.5, -2.5]},
  sun: [5, 7, 4],
  outdoor: true,
  walk: 'x',
  reach: 46,
  surface: [3.4, 0.62, -0.7],
  Draw: ({look, seed}) => {
    const k = look.shade;
    const n = night(look);
    const cols = [-6, -3, 0, 3, 6];
    const floors = [3.2, 6.4, 9.6, 12.8];
    return (
      <group>
        <Sky look={look} />
        <B p={[0, -0.05, -10]} s={[140, 0.1, 60]} c={shadeOf('#8a7158', k)} noShadow />
        <B p={[0, 0.02, -8]} s={[14, 0.12, 6]} c={shadeOf('#a9a59c', k)} />
        {/* the steel frame of the building going up */}
        {cols.map((x) => (
          <B key={x} p={[x, 7, -8]} s={[0.3, 14, 0.3]} c={shadeOf('#b5532f', k)} />
        ))}
        {cols.map((x) => (
          <B key={`b${x}`} p={[x, 7, -10.5]} s={[0.3, 14, 0.3]} c={shadeOf('#9c4527', k)} />
        ))}
        {floors.map((y) => (
          <group key={y}>
            <Girder p={[0, y, -8]} len={12.4} c={shadeOf('#b5532f', k)} />
            <Girder p={[0, y, -10.5]} len={12.4} c={shadeOf('#9c4527', k)} />
            {cols.map((x) => (
              <Girder key={x} p={[x, y, -9.25]} len={2.5} r={[0, Math.PI / 2, 0]} c={shadeOf('#a84c2b', k)} />
            ))}
          </group>
        ))}
        <B p={[0, 3.25, -9.25]} s={[12.4, 0.1, 2.5]} c={shadeOf('#8f8b84', k)} />
        {/* the tower crane: mast, jib over the site, counterweight, the cable down */}
        <group position={[8, 0, -12]}>
          <B p={[0, 13, 0]} s={[1.0, 26, 1.0]} c={shadeOf('#e2b21f', k)} />
          {Array.from({length: 13}, (_, i) => (
            <B key={i} p={[0, 1 + i * 2, 0.51]} s={[1.0, 0.08, 0.02]} c="#3a3d44" r={[0, 0, 0.9]} />
          ))}
          <B p={[-8, 26.3, 0]} s={[22, 0.7, 0.7]} c={shadeOf('#e2b21f', k)} />
          <B p={[4.5, 25.4, 0]} s={[2.2, 1.6, 1.4]} c="#5a5c62" />
          <B p={[0.9, 25.0, 0]} s={[1.2, 1.2, 1.2]} c="#e9e4da" />
          <B p={[-14, 25.95, 0]} s={[0.5, 0.3, 0.5]} c="#3a3d44" />
        </group>
        {/* the site office, barriers, a pile of pipes, a stack of crates to sit on */}
        <group position={[-4.2, 0, -3.4]}>
          <B p={[0, 1.25, 0]} s={[3.2, 2.5, 1.6]} c={shadeOf('#d8d2c2', k)} />
          <B p={[0, 1.05, 0.81]} s={[0.8, 2.0, 0.02]} c={shadeOf('#5a6b7a', k)} />
          <B p={[1.0, 1.6, 0.81]} s={[0.8, 0.6, 0.02]} c={n ? '#ffe2a8' : '#a8c3cf'} glow={n ? 1.2 : 0} />
        </group>
        <Barrier p={[-1.5, 0, 2.6]} />
        <Barrier p={[2.4, 0, 2.6]} />
        {[0, 1, 2].map((i) => (
          <Cyl key={i} p={[-6.5 + i * 0.42, 0.21, -1.2]} r1={0.2} r2={0.2} h={2.6} c={shadeOf('#5f6670', k)} rot={[Math.PI / 2, 0, 0]} />
        ))}
        <Cyl p={[-6.29, 0.56, -1.2]} r1={0.2} r2={0.2} h={2.6} c={shadeOf('#5f6670', k)} rot={[Math.PI / 2, 0, 0]} />
        <B p={[3.4, 0.27, -1.4]} s={[0.9, 0.54, 0.9]} c={shadeOf('#a07a4c', k)} />
        <B p={[3.4, 0.27, -0.6]} s={[0.7, 0.54, 0.7]} c={shadeOf('#8d6a40', k)} />
        <B p={[5.2, 0.3, 0.6]} s={[1.2, 0.6, 0.8]} c={shadeOf('#8d6a40', k)} />
        {[-20, -36, 22, 38].map((x, i) => (
          <Building key={x} p={[x, 8, -30]} s={[12, 16 + (i % 2) * 8, 8]} seed={seed + i} look={look} night={n} />
        ))}
      </group>
    );
  },
};

const highway: SetDef = {
  road: -2.0, // the far lane: a car under way drives there, the camera cars beside it on the road
  reach: 200,
  spots: {
    center: {x: 0, z: 0.4, ry: 0},
    left: {x: -2.5, z: 2.1, ry: 0},
    right: {x: 2.5, z: 2.1, ry: 0},
    far: {x: 0, z: -2.1, ry: 0},
    door: {x: 0, z: 5.6, ry: Math.PI},
  },
  wide: {pos: [7, 3.4, 10], look: [0, 1.0, 0]},
  sun: [-6, 7, 5],
  outdoor: true,
  walk: 'x',
  surface: [0, 0, 0],
  Draw: ({look, seed}) => {
    const k = look.shade;
    const n = night(look);
    const dashes = Array.from({length: 46}, (_, i) => -90 + i * 4);
    return (
      <group>
        <Sky look={look} />
        <B p={[0, -0.1, 0]} s={[240, 0.1, 80]} c={shadeOf('#5d7a44', k)} noShadow />
        <B p={[0, -0.04, 0]} s={[240, 0.1, 8.6]} c={shadeOf('#3d3f44', k)} noShadow />
        {dashes.map((x) => (
          <group key={x}>
            <B p={[x, 0.012, 0]} s={[2, 0.02, 0.14]} c={shadeOf('#e9e4c8', k)} noShadow />
          </group>
        ))}
        <B p={[0, 0.012, -4.0]} s={[240, 0.02, 0.12]} c={shadeOf('#e9e4da', k)} noShadow />
        <B p={[0, 0.012, 4.0]} s={[240, 0.02, 0.12]} c={shadeOf('#e9e4da', k)} noShadow />
        {/* guard rails on both sides */}
        {[-4.7, 4.7].map((z) => (
          <group key={z}>
            <B p={[0, 0.62, z]} s={[240, 0.24, 0.06]} c={shadeOf('#b9bcc2', k)} />
            {Array.from({length: 60}, (_, i) => (
              <B key={i} p={[-118 + i * 4, 0.32, z + (z > 0 ? 0.06 : -0.06)]} s={[0.1, 0.64, 0.1]} c={shadeOf('#8e9198', k)} />
            ))}
          </group>
        ))}
        {Array.from({length: 12}, (_, i) => -110 + i * 20).map((x) => (
          <group key={x} position={[x, 0, -5.4]}>
            <Cyl p={[0, 4, 0]} r1={0.08} r2={0.12} h={8} c="#6c6f76" seg={6} />
            <B p={[0, 8, 1.2]} s={[0.15, 0.12, 2.6]} c="#6c6f76" />
            <B p={[0, 7.9, 2.4]} s={[0.4, 0.12, 0.6]} c="#fff1d6" glow={n ? 2 : 0.4} />
          </group>
        ))}
        {Array.from({length: 14}, (_, i) => (
          <Building key={i} p={[-90 + i * 14, 9 + (i % 3) * 4, -60 - (i % 2) * 10]} s={[10, 18 + (i % 3) * 8, 8]} seed={seed + i} look={look} night={n} />
        ))}
        <Mountains z={-110} seed={seed} c={shadeOf('#5d6f7a', look.shade * 0.9)} />
      </group>
    );
  },
};

// ---------------------------------------------------------------- the broken bridge

// An elevated highway over a river whose middle span has collapsed (the user, of a car jumping between two plain
// grey roofs: "this not look real broken highway"): the deck on concrete piers 26 m up, its broken ends jagged with
// rebar sticking out and bent down, a slab hanging into the gap from the near side, a barrier and a lamp post torn
// with it, cracks and rubble on the road before it, cones knocked over, and the fallen span lying in the river below.
// The road runs along x; the gap is BRIDGE_GAP.
const BRIDGE_GAP: [number, number] = [5.2, 19.6];
const DECK_W = 11; // z -5.5..5.5
const DROP = 26; // the river's surface below the road
const CONCRETE = '#8f8b84';
const ASPHALT = '#3c3e43';
const REBAR = '#6e4430';

// A bar from a point in a direction (the reinforcing steel left sticking out of broken concrete).
const Bar: React.FC<{from: V3; dir: V3; len: number; r?: number; c?: string}> = ({from, dir, len, r = 0.025, c = REBAR}) => {
  const d = new THREE.Vector3(...dir).normalize();
  const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), d);
  const mid = new THREE.Vector3(...from).addScaledVector(d, len / 2);
  return (
    <mesh position={mid} quaternion={q} castShadow>
      <cylinderGeometry args={[r, r, len, 5]} />
      <primitive object={mat(c)} attach="material" />
    </mesh>
  );
};

// One side of the deck from `far` to its broken end at `edge` (`dir` +1: the deck runs toward -x and breaks at its +x
// end; -1 the other way): the slab and its asphalt in strips across that end at staggered lengths, the girders under
// it, the barriers along both sides, rebar out of every strip, cracks across the road before it.
const Deck: React.FC<{far: number; edge: number; dir: 1 | -1; seed: number; k: number}> = ({far, edge, dir, seed, k}) => {
  const rand = rng(seed);
  const solid = edge - dir * 1.6; // where the whole slab ends and the broken strips begin
  const len = Math.abs(solid - far);
  const mid = (solid + far) / 2;
  const strips = Array.from({length: 7}, (_, i) => {
    const z0 = -DECK_W / 2 + (i * DECK_W) / 7;
    return {z: z0 + DECK_W / 14, w: DECK_W / 7 + 0.02, end: edge + dir * (rand() * 1.4 - 0.9), y: -rand() * 0.12};
  });
  const conc = shadeOf(CONCRETE, k);
  const asph = shadeOf(ASPHALT, k);
  return (
    <group>
      <B p={[mid, -0.5, 0]} s={[len, 1.0, DECK_W]} c={conc} />
      <B p={[mid, -0.015, 0]} s={[len, 0.04, DECK_W - 0.9]} c={asph} noShadow />
      {strips.map((st, i) => {
        const l = Math.abs(st.end - solid);
        const x = (st.end + solid) / 2;
        return (
          <group key={i}>
            <B p={[x, -0.5 + st.y, st.z]} s={[l, 1.0, st.w]} c={conc} />
            {Math.abs(st.z) < DECK_W / 2 - 0.45 ? <B p={[x, -0.015 + st.y, st.z]} s={[l, 0.04, st.w]} c={asph} noShadow /> : null}
            {[0, 1, 2].map((j) => (
              <Bar key={j} from={[st.end, -0.25 - j * 0.28 + st.y, st.z - st.w / 3 + (j * st.w) / 3]}
                dir={[dir, -0.25 - rand() * 1.6, (rand() - 0.5) * 0.5]} len={0.5 + rand() * 1.3} />
            ))}
          </group>
        );
      })}
      {/* two box girders under the slab, broken off short of the slab's end */}
      {[-2.8, 2.8].map((z) => (
        <group key={z}>
          <B p={[(solid - dir * 0.8 + far) / 2, -1.8, z]} s={[Math.abs(solid - dir * 0.8 - far), 1.6, 2.6]} c={shadeOf('#7b7872', k)} />
          {[0, 1, 2, 3].map((j) => (
            <Bar key={j} from={[solid - dir * 0.8, -1.2 - j * 0.35, z - 0.9 + j * 0.6]} dir={[dir, -0.6 - rand(), (rand() - 0.5) * 0.4]} len={0.6 + rand() * 0.9} r={0.03} />
          ))}
        </group>
      ))}
      {/* concrete barriers along both sides (the far side's ends with the slab) */}
      {[-1, 1].map((sd) => {
        const end = strips[sd < 0 ? 0 : 6].end - dir * 0.3;
        const bl = Math.abs(end - far);
        return (
          <group key={sd}>
            <B p={[(end + far) / 2, 0.45, sd * (DECK_W / 2 - 0.25)]} s={[bl, 0.9, 0.45]} c={shadeOf('#a7a39b', k)} />
            <B p={[(end + far) / 2, 0.93, sd * (DECK_W / 2 - 0.25)]} s={[bl, 0.08, 0.3]} c={shadeOf('#b9bcc2', k)} />
          </group>
        );
      })}
      {/* lane lines: two dashed, the edges solid, stopping before the break */}
      {[-0.4, 2.8].map((z) =>
        Array.from({length: Math.floor((len - 2) / 6)}, (_, i) => solid - dir * (3 + i * 6)).map((x) => (
          <B key={`${z}${x}`} p={[x, 0.012, z]} s={[2.6, 0.02, 0.13]} c={shadeOf('#e9e4c8', k)} noShadow />
        )),
      )}
      {[-4.6, 4.6].map((z) => (
        <B key={z} p={[mid - dir * 0.6, 0.012, z]} s={[len - 1.2, 0.02, 0.12]} c={shadeOf('#e9e4da', k)} noShadow />
      ))}
      {/* cracks running back from the break across the asphalt */}
      {Array.from({length: 6}, (_, i) => {
        let x = edge - dir * (0.6 + rand() * 1.0);
        let z = -4 + i * 1.6 + rand() * 0.8;
        return Array.from({length: 4}, (_, j) => {
          const l = 0.6 + rand() * 1.1;
          const a = (rand() - 0.5) * 1.4;
          const cx = x - dir * Math.cos(a) * l * 0.5;
          const cz = z + Math.sin(a) * l * 0.5;
          x -= dir * Math.cos(a) * l;
          z += Math.sin(a) * l;
          return <B key={`${i}${j}`} p={[cx, 0.01, cz]} s={[l, 0.012, 0.05 - j * 0.008]} r={[0, a, 0]} c="#16171a" noShadow />;
        });
      })}
    </group>
  );
};

const LAMP_EVERY = 30;
const BridgeLamp: React.FC<{x: number; z: number; look: Look; tilt?: number}> = ({x, z, look, tilt = 0}) => {
  const sd = z > 0 ? -1 : 1;
  return (
    <group position={[x, 0.95, z]} rotation={[tilt * sd, 0, 0]}>
      <Cyl p={[0, 3.8, 0]} r1={0.07} r2={0.1} h={7.6} c="#6c6f76" seg={6} />
      <B p={[0, 7.6, sd * 1.1]} s={[0.12, 0.1, 2.3]} c="#6c6f76" />
      <B p={[0, 7.5, sd * 2.1]} s={[0.36, 0.1, 0.55]} c="#fff1d6" glow={night(look) ? 2 : 0.4} />
    </group>
  );
};

const Cone: React.FC<{p: V3; down?: number; ry?: number}> = ({p, down = 0, ry = 0}) => (
  <group position={p} rotation={[0, ry, down]}>
    <B p={[0, 0.02, 0]} s={[0.42, 0.04, 0.42]} c="#2a2b2f" />
    <Cyl p={[0, 0.34, 0]} r1={0.03} r2={0.17} h={0.62} c="#e2622a" seg={8} />
    <Cyl p={[0, 0.4, 0]} r1={0.11} r2={0.13} h={0.1} c="#f1efe8" seg={8} />
  </group>
);

const bridge: SetDef = {
  road: -2.0, // the far lane, as on the highway
  reach: 160,
  jumpAt: 4.2, // its rear wheels leave the broken edge as it flies the fallen span
  gap: BRIDGE_GAP,
  spots: {
    center: {x: -2, z: 0.4, ry: 0},
    left: {x: -4.5, z: 2.1, ry: 0},
    right: {x: 0.5, z: 2.1, ry: 0},
    far: {x: -2, z: -2.1, ry: 0},
    door: {x: -2, z: 4.3, ry: Math.PI},
  },
  wide: {pos: [16, 3.2, 17], look: [8, -3, 0]},
  sun: [-6, 8, 6],
  outdoor: true,
  walk: 'x',
  surface: [0, 0, 0],
  Draw: ({look, seed}) => {
    const k = look.shade;
    const n = night(look);
    const rand = rng(seed + 31);
    const [g0, g1] = BRIDGE_GAP;
    const piers = [-6, -38, -70, -102, 31, 63, 95];
    return (
      <group>
        <Sky look={look} r={260} />
        <Deck far={-130} edge={g0} dir={1} seed={seed + 1} k={k} />
        <Deck far={130} edge={g1} dir={-1} seed={seed + 2} k={k} />
        {/* the slab that broke but didn't fall: hanging from the near edge into the gap on its rebar */}
        <group position={[g0 - 0.2, -0.15, -2.6]} rotation={[0.12, 0, -1.0]}>
          <B p={[1.7, -0.5, 0]} s={[3.4, 0.95, 5.2]} c={shadeOf(CONCRETE, k)} />
          <B p={[1.7, 0.0, 0.4]} s={[3.4, 0.04, 4.4]} c={shadeOf(ASPHALT, k)} noShadow />
          <B p={[1.6, 0.0, 0.9]} s={[2.4, 0.02, 0.13]} c={shadeOf('#e9e4c8', k)} noShadow />
          {/* its barrier, torn and hanging off it */}
          <B p={[1.4, 0.45, -2.4]} s={[2.8, 0.9, 0.45]} c={shadeOf('#a7a39b', k)} />
          {[0, 1, 2, 3, 4].map((j) => (
            <Bar key={j} from={[3.4, -0.3, -2.2 + j * 1.1]} dir={[1, -0.4 - 0.3 * j, 0.1]} len={0.6 + 0.2 * j} />
          ))}
          {[0, 1, 2, 3].map((j) => <Bar key={`h${j}`} from={[0.1, -0.4, -1.8 + j * 1.2]} dir={[-1, 0.9, 0]} len={0.9} />)}
        </group>
        {/* a lamp post bent over the edge, and the far edge's torn barrier sagging */}
        <BridgeLamp x={g0 - 2.4} z={-5.25} look={look} tilt={-0.5} />
        <group position={[g1 + 0.3, 0.2, 5.25]} rotation={[0, 0, -0.9]}>
          <B p={[-1.3, 0.3, 0]} s={[2.6, 0.9, 0.45]} c={shadeOf('#a7a39b', k)} />
        </group>
        {piers.map((x) => (
          <group key={x}>
            <B p={[x, -3.2, 0]} s={[2.8, 1.2, DECK_W - 0.6]} c={shadeOf('#827e77', k)} />
            <B p={[x, -3.8 - (DROP - 3.8) / 2, 0]} s={[2.4, DROP - 3.8, 3.4]} c={shadeOf('#8a867f', k)} />
          </group>
        ))}
        {Array.from({length: 9}, (_, i) => -126 + i * LAMP_EVERY)
          .filter((x) => x < g0 - 6 || x > g1 + 4)
          .map((x, i) => <BridgeLamp key={x} x={x} z={i % 2 ? 5.25 : -5.25} look={look} />)}
        {/* rubble and cones before the break */}
        {Array.from({length: 22}, (_, i) => {
          const s0 = 0.12 + rand() * 0.45;
          return (
            <B key={i} p={[g0 - 0.5 - rand() * 7, s0 * 0.4, (i % 2 ? -1 : 1) * (3.3 + rand() * 1.3)]} s={[s0, s0 * 0.8, s0 * (0.7 + rand() * 0.6)]}
              r={[rand() * 3, rand() * 3, rand() * 3]} c={shadeOf(i % 3 ? '#9b968e' : '#6f6b65', k)} />
          );
        })}
        {/* (rubble and cones by the barriers: the lanes the cars drive stay clear) */}
        <Cone p={[g0 - 9, 0, -4.4]} />
        <Cone p={[g0 - 7.5, 0.15, -3.9]} down={1.5} ry={0.7} />
        <Cone p={[g0 - 9.5, 0, 4.2]} />
        <Cone p={[g0 - 6.2, 0.15, 3.7]} down={1.5} ry={-1.1} />
        {/* the valley: the river under the gap, its banks, trees, the fallen span lying broken in the water */}
        <B p={[0, -DROP - 0.3, 0]} s={[420, 0.4, 320]} c={shadeOf('#5f6a48', k)} noShadow />
        <B p={[12, -DROP + 0.02, 0]} s={[44, 0.06, 320]} c={shadeOf('#35596c', k)} noShadow />
        {/* roads in the valley: one passing under the bridge beside the river, one along the far bank */}
        {[[-22, 'z'], [0, 'x']].map(([at, way]) => {
          const alongZ = way === 'z';
          const c0 = alongZ ? (at as number) : 46;
          return (
            <group key={String(way)}>
              <B p={alongZ ? [c0, -DROP + 0.03, 0] : [0, -DROP + 0.03, c0]} s={alongZ ? [9, 0.06, 320] : [420, 0.06, 9]} c={shadeOf(ASPHALT, k)} noShadow />
              {Array.from({length: 40}, (_, i) => -156 + i * 8).map((d) => (
                <B key={d} p={alongZ ? [c0, -DROP + 0.07, d] : [d, -DROP + 0.07, c0]} s={alongZ ? [0.14, 0.02, 3] : [3, 0.02, 0.14]} c={shadeOf('#e9e4c8', k)} noShadow />
              ))}
              {[-4.2, 4.2].map((e) => (
                <B key={e} p={alongZ ? [c0 + e, -DROP + 0.07, 0] : [0, -DROP + 0.07, c0 + e]} s={alongZ ? [0.12, 0.02, 320] : [420, 0.02, 0.12]} c={shadeOf('#e9e4da', k)} noShadow />
              ))}
            </group>
          );
        })}
        <group position={[8.6, -DROP + 0.6, 0.6]} rotation={[0.08, 0.22, 0.42]}>
          <B p={[0, 0, 0]} s={[7.5, 1.0, DECK_W]} c={shadeOf('#7d7973', k)} />
          <B p={[0, 0.5, 0]} s={[7.5, 0.04, DECK_W - 0.9]} c={shadeOf(ASPHALT, k)} noShadow />
        </group>
        <group position={[16.2, -DROP + 0.9, -1.2]} rotation={[-0.18, -0.3, -0.55]}>
          <B p={[0, 0, 0]} s={[6.5, 1.0, DECK_W - 1.5]} c={shadeOf('#7d7973', k)} />
          <B p={[0, 0.5, 0]} s={[6.5, 0.04, DECK_W - 2.2]} c={shadeOf(ASPHALT, k)} noShadow />
        </group>
        {Array.from({length: 16}, (_, i) => {
          const s0 = 0.6 + rand() * 1.6;
          return <B key={`r${i}`} p={[5 + rand() * 15, -DROP + s0 * 0.3, -9 + rand() * 18]} s={[s0, s0 * 0.7, s0]} r={[rand(), rand() * 3, rand()]} c={shadeOf('#78746e', k)} />;
        })}
        {Array.from({length: 26}, (_, i) => {
          const x = i % 2 ? (rand() < 0.5 ? -12 - rand() * 4 : -32 - rand() * 50) : 38 + rand() * 70;
          return <Tree key={`t${i}`} p={[x, -DROP, -60 + rand() * 100]} seed={seed + 90 + i} s={2.2 + rand() * 1.4} tone={rand() < 0.5 ? '#3f6b38' : '#2f5532'} />;
        })}
        {Array.from({length: 16}, (_, i) => {
          const h = 34 + ((i * 37) % 5) * 9;
          return <Building key={`b${i}`} p={[-110 + i * 15, -DROP + h / 2, -95 - (i % 3) * 12]} s={[11, h, 9]} seed={seed + i} look={look} night={n} />;
        })}
        <group position={[0, -DROP, 0]} scale={[1.6, 2.4, 1]}>
          <Mountains z={-150} seed={seed} c={shadeOf('#5d6f7a', k * 0.9)} />
        </group>
      </group>
    );
  },
};

const alley: SetDef = {
  lamp: [-1.9, 2.7, -4],
  spots: {
    center: {x: 0, z: 0, ry: 0},
    left: {x: -1.1, z: 0.3, ry: 0},
    right: {x: 1.1, z: 0.3, ry: 0},
    far: {x: 0, z: -11, ry: 0},
    door: {x: -1.8, z: -4, ry: Math.PI / 2},
    chair: {x: 1.7, z: -1.6, ry: -Math.PI / 2, seat: 0.45, stand: [1.05, -1.6]},
  },
  wide: {pos: [1.5, 3.3, 6.5], look: [0, 1.0, -3.5]},
  sun: [2, 9, -10],
  outdoor: true,
  walk: 'z',
  reach: 40,
  surface: [-1.7, 1.25, -2.2],
  Draw: ({look, seed}) => {
    const k = look.shade;
    const n = night(look);
    return (
      <group>
        <Sky look={look} />
        <B p={[0, -0.05, -10]} s={[5, 0.1, 50]} c={shadeOf('#34363b', k)} noShadow />
        {/* wet ground: a few dark puddles that catch the light */}
        {[[0.5, 1.2, 1.1], [-0.6, -3.5, 1.5], [0.8, -8, 1.2]].map(([x, z, w], i) => (
          <mesh key={i} position={[x, 0.006, z]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
            <circleGeometry args={[w * 0.6, 9]} />
            <meshStandardMaterial color="#1c2230" roughness={0.12} metalness={0.4} />
          </mesh>
        ))}
        <BrickWall p={[-2.4, 4.5, -10]} w={50} h={9} ry={Math.PI / 2} look={look} seed={seed} />
        <BrickWall p={[2.4, 4.5, -10]} w={50} h={9} ry={-Math.PI / 2} look={look} seed={seed + 1} />
        {/* the street at the far end, brighter */}
        <mesh position={[0, 3, -34]}>
          <planeGeometry args={[5, 6]} />
          <meshBasicMaterial color={n ? '#f2c890' : '#dfe6ec'} />
        </mesh>
        {/* a door with a lamp over it, a dumpster, bags, crates, the fire escape further down */}
        <B p={[-2.37, 1.1, -4]} s={[0.06, 2.2, 1.1]} c={shadeOf('#4a3a2e', k)} />
        <B p={[-2.25, 2.7, -4]} s={[0.25, 0.12, 0.3]} c="#fff1d6" glow={n ? 2.2 : 0.4} />
        <group position={[-1.7, 0, -1.8]}>
          <B p={[0, 0.6, 0]} s={[1.1, 1.2, 1.8]} c={shadeOf('#3f6a4a', k)} />
          <B p={[0.05, 1.24, 0]} s={[1.18, 0.08, 1.86]} c={shadeOf('#2f5238', k)} r={[0, 0, 0.06]} />
        </group>
        {[[1.9, 0.0], [1.6, 0.6], [-1.9, 1.4]].map(([x, z], i) => (
          <mesh key={i} position={[x, 0.22, z]} castShadow receiveShadow>
            <icosahedronGeometry args={[0.28, 0]} />
            <primitive object={mat('#1d1f24')} attach="material" />
          </mesh>
        ))}
        <B p={[1.7, 0.22, -1.6]} s={[0.6, 0.44, 0.6]} c={shadeOf('#8d6a40', k)} />
        {[3.2, 5.6].map((y) => (
          <group key={y} position={[1.85, y, -9]}>
            <B p={[0, 0, 0]} s={[1.1, 0.06, 3]} c="#2a2c31" />
            <B p={[-0.52, 0.5, 0]} s={[0.04, 0.04, 3]} c="#2a2c31" />
            {[-1.4, -0.7, 0, 0.7, 1.4].map((z) => (
              <B key={z} p={[-0.52, 0.25, z]} s={[0.03, 0.5, 0.03]} c="#2a2c31" />
            ))}
          </group>
        ))}
        <B p={[1.85, 4.4, -10.2]} s={[0.5, 0.05, 2.6]} c="#2a2c31" r={[0.75, 0, 0]} />
      </group>
    );
  },
};

const lab: SetDef = {
  lamp: [0, 2.8, -0.8],
  spots: {
    center: {x: 0, z: 0.4, ry: 0},
    left: {x: -1.6, z: 0.6, ry: 0},
    right: {x: 1.6, z: 0.6, ry: 0},
    desk: {x: -1.5, z: -1.75, ry: Math.PI, seat: 0.5, stand: [-0.8, -1.75]},
    chair: {x: -1.5, z: -1.75, ry: Math.PI, seat: 0.5, stand: [-0.8, -1.75]},
    counter: {x: -1.5, z: -1.95, ry: Math.PI},
    far: {x: 1.7, z: -1.9, ry: 0},
    door: {x: -2.6, z: 0.9, ry: Math.PI / 2},
  },
  wide: {pos: [2.8, 2.9, 3.6], look: [0, 0.9, -1.3]},
  sun: [3, 6, 3],
  outdoor: false,
  walk: 'x',
  surface: [-1.5, 0.8, -2.55],
  Draw: ({look}) => {
    const k = look.shade;
    return (
      <group>
        <Room floor="#cfd4d8" wall="#e8ecee" side="#dde2e5" look={look} />
        {/* the glowing chamber: a glass tube on a ring, lit from below */}
        <group position={[1.7, 0, -1.9]}>
          <Cyl p={[0, 0.1, 0]} r1={0.85} r2={0.9} h={0.2} c="#9aa3ab" seg={12} />
          <Cyl p={[0, 0.21, 0]} r1={0.7} r2={0.7} h={0.02} c="#7fe7ff" seg={12} glow={1.8} />
          <mesh position={[0, 1.4, 0]}>
            <cylinderGeometry args={[0.72, 0.72, 2.4, 14, 1, true]} />
            <meshStandardMaterial color="#a8eeff" emissive="#5fd6ff" emissiveIntensity={0.35} transparent opacity={0.22} side={THREE.DoubleSide} depthWrite={false} />
          </mesh>
          <Cyl p={[0, 2.68, 0]} r1={0.85} r2={0.85} h={0.18} c="#9aa3ab" seg={12} />
          {[0.8, 1.6, 2.3].map((y) => (
            <Cyl key={y} p={[0, y, 0]} r1={0.74} r2={0.74} h={0.03} c="#7fe7ff" seg={14} glow={1.2} />
          ))}
        </group>
        {/* the console and its screens on the back wall */}
        <B p={[-1.5, 0.4, -2.55]} s={[1.9, 0.8, 0.7]} c={shadeOf('#b9c0c6', k)} />
        <B p={[-1.5, 0.82, -2.45]} s={[1.9, 0.04, 0.6]} c="#3a4048" />
        {[-2.2, -1.5, -0.8].map((x, i) => (
          <group key={x}>
            <B p={[x, 1.7, -2.96]} s={[0.62, 0.42, 0.04]} c="#1b1f26" />
            <B p={[x, 1.7, -2.935]} s={[0.56, 0.36, 0.01]} c={['#4fb8ff', '#62f0c0', '#4fb8ff'][i]} glow={1.1} />
          </group>
        ))}
        <B p={[2.95, 1.0, 0.4]} s={[0.5, 2.0, 1.4]} c={shadeOf('#c4cace', k)} />
        <B p={[0, 3.35, -0.8]} s={[2.4, 0.05, 0.5]} c="#f6fbff" glow={1.4} />
        <B p={[0, 0.015, 0.4]} s={[2.6, 0.02, 0.06]} c="#f2c94c" noShadow />
      </group>
    );
  },
};

// High above a sea of clouds (anything flying, a skydive, a fight on a plane's wing): faceted cloud lumps far below,
// banks of cloud on the horizon, the sky's own gradient; no ground.
const CLOUD = facetedBall(1, 1, 0.22, 11);
const skySet: SetDef = {
  spots: {center: {x: 0, z: 0, ry: Math.PI / 2}, left: {x: -2.5, z: 0, ry: Math.PI / 2}, right: {x: 2.5, z: 0, ry: Math.PI / 2}, far: {x: 0, z: -8, ry: Math.PI / 2}},
  wide: {pos: [10, 9, 16], look: [0, 5, 0]},
  sun: [-8, 9, -6],
  outdoor: true,
  walk: 'x',
  sky: true,
  surface: [0, 0, 0],
  Draw: ({look, seed}) => {
    const rand = rng(seed + 17);
    // a sea of clouds far below (a skydiver falls toward it for many seconds before reaching it)
    const lumps = React.useMemo(() => Array.from({length: 260}, () => [-420 + rand() * 840, -40 - rand() * 5, -180 + rand() * 300, 7 + rand() * 13] as const), [seed]);
    // and clouds at the height it flies, well off its line, that stream past whatever follows it
    const near = React.useMemo(() => Array.from({length: 70}, () => [-420 + rand() * 840, -12 + rand() * 34, (rand() < 0.5 ? -1 : 1) * (48 + rand() * 150), 6 + rand() * 10] as const), [seed]);
    const cloud = shadeOf('#f2efe9', Math.min(1, look.shade + 0.15));
    return (
      <group>
        <Sky look={look} r={380} deep={0.32} />
        {near.map(([x, y, z, r], i) => (
          <mesh key={`n${i}`} geometry={CLOUD} position={[x, y, z]} scale={[r * 1.7, r * 0.55, r]}>
            <primitive object={mat(cloud)} attach="material" />
          </mesh>
        ))}
        {lumps.map(([x, y, z, r], i) => (
          <mesh key={i} geometry={CLOUD} position={[x, y, z]} scale={[r * 1.6, r * 0.5, r]}>
            <primitive object={mat(cloud)} attach="material" />
          </mesh>
        ))}
      </group>
    );
  },
};

export const SETS: Record<SetName, SetDef> = {
  bedroom,
  hallway,
  street,
  park,
  kitchen,
  living,
  office,
  bathroom,
  gym,
  cafe,
  busstop,
  rooftop,
  construction,
  highway,
  bridge,
  alley,
  lab,
  sky: skySet,
  void: voidSet,
};

export const spotOf = (set: SetDef, spot: string): SpotDef => set.spots[spot as Spot] ?? set.spots.center ?? {x: 0, z: 0, ry: 0};

// Things put down in the scene: on the set's surface, side by side.
export const ThingView: React.FC<{kind: string; p: V3; glow?: boolean; label?: string}> = ({kind, p, glow, label}) => {
  switch (kind) {
    case 'alarm': {
      const tex = labelTexture(label || '5:30', '#ff4a3a', '#141414', 256, 128, 'bold 92px "Courier New", monospace');
      return (
        <group position={p} rotation={[0, -0.35, 0]}>
          <B p={[0, 0.09, 0]} s={[0.26, 0.18, 0.12]} c="#e9e4da" />
          <mesh position={[0, 0.09, 0.061]}>
            <planeGeometry args={[0.2, 0.1]} />
            <meshBasicMaterial map={tex} toneMapped={false} />
          </mesh>
        </group>
      );
    }
    case 'phone':
      return (
        <group position={p}>
          <B p={[0, 0.01, 0]} s={[0.1, 0.016, 0.19]} c="#1a1b1f" />
          <B p={[0, 0.02, 0]} s={[0.086, 0.004, 0.17]} c="#cfe3ff" glow={glow ? 1.5 : 0} />
        </group>
      );
    case 'mug':
      return <Cyl p={[p[0], p[1] + 0.065, p[2]]} r1={0.06} r2={0.055} h={0.13} c="#e9e4da" />;
    case 'laptop':
      return (
        <group position={p}>
          <B p={[0, 0.015, 0]} s={[0.42, 0.03, 0.3]} c="#9aa0a8" />
          <B p={[0, 0.16, -0.14]} s={[0.42, 0.28, 0.02]} c="#9aa0a8" r={[-0.2, 0, 0]} />
          <B p={[0, 0.16, -0.125]} s={[0.38, 0.24, 0.005]} c="#a9cdfa" glow={glow ? 1.2 : 0.2} r={[-0.2, 0, 0]} />
        </group>
      );
    case 'book':
      return <B p={[p[0], p[1] + 0.03, p[2]]} s={[0.24, 0.06, 0.32]} c="#3d5a80" />;
    case 'shoes':
      return (
        <group position={p}>
          <B p={[-0.13, 0.055, 0]} s={[0.2, 0.11, 0.32]} c="#eeece7" />
          <B p={[0.13, 0.055, 0.03]} s={[0.2, 0.11, 0.32]} c="#eeece7" />
        </group>
      );
    case 'plate':
      return <Cyl p={[p[0], p[1] + 0.015, p[2]]} r1={0.16} r2={0.13} h={0.03} c="#f2efe8" seg={10} />;
    case 'pizza':
      return (
        <group position={p}>
          <Cyl p={[0, 0.03, 0]} r1={0.32} r2={0.32} h={0.05} c="#c8954f" seg={8} />
          <Cyl p={[0, 0.06, 0]} r1={0.28} r2={0.28} h={0.02} c="#c4452e" seg={8} />
        </group>
      );
    case 'bag':
      return <B p={[p[0], p[1] + 0.2, p[2]]} s={[0.4, 0.4, 0.2]} c="#4a5a48" />;
    case 'plant':
      return (
        <group position={p}>
          <Cyl p={[0, 0.12, 0]} r1={0.12} r2={0.09} h={0.24} c="#b6603f" seg={7} />
          <mesh position={[0, 0.4, 0]} castShadow>
            <icosahedronGeometry args={[0.2, 0]} />
            <primitive object={mat('#3f6b38')} attach="material" />
          </mesh>
        </group>
      );
    case 'bottle':
      return <Cyl p={[p[0], p[1] + 0.13, p[2]]} r1={0.04} r2={0.05} h={0.26} c="#4b8fb5" seg={8} />;
    case 'calendar':
    case 'note': {
      const tex = labelTexture(label || (kind === 'calendar' ? 'MON' : 'TODO'), '#222', kind === 'calendar' ? '#f3efe6' : '#f2d65e', 256, 256, 'bold 64px Anton, Impact, sans-serif');
      return (
        <mesh position={[p[0], p[1] + 0.25, p[2]]} castShadow>
          <boxGeometry args={[0.4, 0.4, 0.01]} />
          <meshStandardMaterial map={tex} roughness={0.9} />
        </mesh>
      );
    }
    default:
      return null;
  }
};
