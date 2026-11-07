// Effects in a shot, worked out from the time alone (every frame the same in every render): a shockwave ring on the
// ground, the ground cracking, dust thrown out, debris and glass flying and landing, sparks, smoke rising, fire,
// speed streaks behind a man moving very fast, rain, wind, an emergency light. Shake and flash are the camera's and
// the screen's (LowPoly.tsx). Times are the shot's action time; each effect starts at its `at`.
import React from 'react';
import * as THREE from 'three';
import {facetedBall, rng} from './Man';
import type {FxKind} from './types';

type V3 = [number, number, number];

// Transparent materials, cached by colour, opacity (in steps of 0.05) and glow.
const fxMats = new Map<string, THREE.Material>();
const fxMat = (color: string, opacity: number, glow = 0) => {
  const o = Math.max(0, Math.min(1, Math.round(opacity * 20) / 20));
  const key = `${color}|${o}|${glow}`;
  let m = fxMats.get(key);
  if (!m) {
    m = new THREE.MeshStandardMaterial({
      color,
      flatShading: true,
      roughness: 0.9,
      transparent: o < 1,
      opacity: o,
      depthWrite: o >= 1,
      emissive: glow ? new THREE.Color(color) : new THREE.Color('#000000'),
      emissiveIntensity: glow,
    });
    fxMats.set(key, m);
  }
  return m;
};

const geos = new Map<string, THREE.BufferGeometry>();
const geo = (key: string, make: () => THREE.BufferGeometry) => {
  let g = geos.get(key);
  if (!g) {
    g = make();
    geos.set(key, g);
  }
  return g;
};
const puff = () => geo('puff', () => facetedBall(1, 0, 0.12, 5));
const chunk = () => geo('chunk', () => new THREE.IcosahedronGeometry(1, 0));
const cube = () => geo('cube', () => new THREE.BoxGeometry(1, 1, 1));
const ring = () => geo('ring', () => new THREE.RingGeometry(0.82, 1, 40));
const cone = () => geo('cone', () => new THREE.ConeGeometry(1, 1, 5));

const P: React.FC<{g: THREE.BufferGeometry; m: THREE.Material; p: V3 | THREE.Vector3; s: number | V3; r?: V3; shadow?: boolean}> = ({g, m, p, s, r, shadow}) => (
  <mesh geometry={g} material={m} position={p instanceof THREE.Vector3 ? p.toArray() : p} scale={typeof s === 'number' ? [s, s, s] : s} rotation={r} castShadow={shadow} />
);

export type FxCtx = {
  at: number; // when it starts
  t: number;
  dur: number;
  point: THREE.Vector3; // where (on the ground under it)
  mover?: {root: V3; ry: number}; // the man the speed streaks follow
  around: THREE.Vector3; // the middle of the shot (rain and wind fill the space around it)
  seed: number;
  dust: string; // the ground's dust colour
  indoor: boolean; // no rain inside a room (the window shows the weather)
};

const Shockwave: React.FC<{c: FxCtx}> = ({c}) => {
  const tau = c.t - c.at;
  if (tau < 0 || tau > 0.9) return null;
  const r = 0.4 + 7 * Math.pow(tau / 0.9, 0.55);
  const o = 0.75 * (1 - tau / 0.9);
  return (
    <group position={c.point.toArray()}>
      <mesh geometry={ring()} material={fxMat('#fff6e6', o, 1.2)} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.05, 0]} scale={[r, r, r]} />
      <mesh geometry={ring()} material={fxMat('#ffffff', o * 0.6, 1.2)} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.25, 0]} scale={[r * 0.7, r * 0.7, r * 0.7]} />
      {tau < 0.35 ? <P g={puff()} m={fxMat('#fff3dc', 0.35 * (1 - tau / 0.35), 1)} p={[0, 0.3, 0]} s={[r * 0.45, r * 0.22, r * 0.45]} /> : null}
    </group>
  );
};

// Cracks: jagged dark lines out from a dent, grown in the first 0.15 s, then staying.
const Crack: React.FC<{c: FxCtx}> = ({c}) => {
  const tau = c.t - c.at;
  if (tau < 0) return null;
  const grow = Math.min(1, tau / 0.15);
  const rand = rng(c.seed * 13 + 7);
  const lines: React.ReactNode[] = [];
  for (let i = 0; i < 10; i++) {
    let a = (i / 10) * Math.PI * 2 + rand() * 0.5;
    let x = 0;
    let z = 0;
    const segs = 4;
    for (let j = 0; j < segs; j++) {
      const len = (0.35 + rand() * 0.45) * grow;
      a += (rand() - 0.5) * 0.9;
      const nx = x + Math.cos(a) * len;
      const nz = z + Math.sin(a) * len;
      lines.push(
        <mesh key={`${i}-${j}`} geometry={cube()} material={fxMat('#1c1a18', 1)} position={[(x + nx) / 2, 0.012, (z + nz) / 2]} rotation={[0, -a, 0]} scale={[len, 0.01, 0.05 * (1 - j / segs) + 0.015]} />,
      );
      x = nx;
      z = nz;
    }
  }
  return (
    <group position={c.point.toArray()}>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.008, 0]} scale={[grow, grow, grow]}>
        <circleGeometry args={[0.9, 9]} />
        <primitive object={fxMat('#2a2622', 0.85)} attach="material" />
      </mesh>
      {lines}
    </group>
  );
};

const Dust: React.FC<{c: FxCtx}> = ({c}) => {
  const tau = c.t - c.at;
  if (tau < 0 || tau > 5) return null;
  const rand = rng(c.seed * 7 + 1);
  return (
    <group position={c.point.toArray()}>
      {Array.from({length: 22}, (_, i) => {
        const a = rand() * Math.PI * 2;
        const v = 1.5 + rand() * 3.5;
        const d = (v * (1 - Math.exp(-2 * tau))) / 2 + 0.3;
        const y = 0.15 + (0.3 + rand() * 0.6) * (1 - Math.exp(-1.5 * tau));
        const s = 0.18 + (0.38 + rand() * 0.32) * (1 - Math.exp(-1.2 * tau));
        const o = 0.32 * Math.exp(-0.9 * tau) * Math.min(1, tau * 12);
        return <P key={i} g={puff()} m={fxMat(c.dust, o)} p={[Math.cos(a) * d, y, Math.sin(a) * d]} s={s} />;
      })}
    </group>
  );
};

// Pieces thrown up that fall and lie where they land: debris (chunks) and glass (thin bright shards).
const Flying: React.FC<{c: FxCtx; glass?: boolean}> = ({c, glass}) => {
  const tau = c.t - c.at;
  if (tau < 0) return null;
  const rand = rng(c.seed * 17 + (glass ? 3 : 9));
  const n = glass ? 34 : 26;
  const from = glass ? 1.2 : 0.2;
  return (
    <group position={c.point.toArray()}>
      {Array.from({length: n}, (_, i) => {
        const a = rand() * Math.PI * 2;
        const out = glass ? 2 + rand() * 4 : 1.5 + rand() * 3.5;
        const up = glass ? 1 + rand() * 3 : 3 + rand() * 5;
        const size = glass ? 0.04 + rand() * 0.05 : 0.035 + rand() * 0.075;
        const spin = 4 + rand() * 8;
        // the time it reaches the ground: from + up*T - 6*T^2 = size
        const T = (up + Math.sqrt(up * up + 24 * Math.max(0, from - size))) / 12;
        const tt = Math.min(tau, T);
        const y = Math.max(size, from + up * tt - 6 * tt * tt);
        const x = Math.cos(a) * out * tt;
        const z = Math.sin(a) * out * tt;
        const r: V3 = [spin * tt, spin * 0.7 * tt + i, spin * 0.4 * tt];
        if (glass) {
          return <P key={i} g={cube()} m={fxMat('#cfeeff', 0.75, 0.6)} p={[x, y, z]} s={[size * 1.6, size, 0.01]} r={r} />;
        }
        return <P key={i} g={chunk()} m={fxMat(['#5c5852', '#6e665c', '#3e3b38'][i % 3], 1)} p={[x, y, z]} s={size} r={r} shadow />;
      })}
    </group>
  );
};

// Sparks: a stream of tiny glowing bits for 1.6 s, each living 0.45 s.
const Sparks: React.FC<{c: FxCtx}> = ({c}) => {
  const rand = rng(c.seed * 23 + 5);
  const out: React.ReactNode[] = [];
  for (let i = 0; i < 60; i++) {
    const born = c.at + i * 0.027;
    const a = rand() * Math.PI * 2;
    const v = 2.5 + rand() * 4;
    const up = 1 + rand() * 3;
    const tt = c.t - born;
    if (tt < 0 || tt > 0.45) continue;
    out.push(
      <P key={i} g={cube()} m={fxMat(rand() < 0.5 ? '#ffd27a' : '#fff3c4', 1 - tt / 0.45, 3)} p={[Math.cos(a) * v * tt, up * tt - 4.9 * tt * tt, Math.sin(a) * v * tt]} s={0.035} />,
    );
  }
  return <group position={c.point.toArray()}>{out}</group>;
};

const Smoke: React.FC<{c: FxCtx}> = ({c}) => {
  const tau = c.t - c.at;
  if (tau < 0) return null;
  const rand = rng(c.seed * 29 + 2);
  return (
    <group position={c.point.toArray()}>
      {Array.from({length: 16}, (_, i) => {
        const phase = rand() * 4;
        const life = ((tau + phase) % 4) / 4; // 0..1
        if (tau + phase < phase + (i * 0.25)) return null;
        const drift = rand() - 0.5;
        const s = 0.35 + 1.1 * life;
        const o = 0.5 * (1 - life) * Math.min(1, tau * 2);
        return <P key={i} g={puff()} m={fxMat(i % 3 ? '#3c3d42' : '#55565c', o)} p={[drift * 1.6 * life, 0.4 + 4.2 * life, drift * 0.8 * life]} s={s} />;
      })}
    </group>
  );
};

const Fire: React.FC<{c: FxCtx}> = ({c}) => {
  const tau = c.t - c.at;
  if (tau < 0) return null;
  const grow = Math.min(1, tau / 0.6);
  const rand = rng(c.seed * 31 + 4);
  const flick = 0.75 + 0.25 * Math.sin(c.t * 19) * Math.sin(c.t * 7.3);
  return (
    <group position={c.point.toArray()} scale={grow}>
      {Array.from({length: 11}, (_, i) => {
        const x = (rand() - 0.5) * 1.2;
        const z = (rand() - 0.5) * 1.0;
        const h = (0.6 + rand() * 0.9) * (0.75 + 0.3 * Math.sin(c.t * (9 + i) + i));
        const w = 0.18 + rand() * 0.2;
        return <P key={i} g={cone()} m={fxMat(i % 3 === 0 ? '#ffd35a' : '#ff7a2a', 0.85, 2.2)} p={[x, h / 2, z]} s={[w, h, w]} />;
      })}
      <pointLight position={[0, 1.0, 0]} color="#ff8a3a" intensity={6 * flick} distance={8} decay={1.6} />
    </group>
  );
};

// Speed: white streaks trailing the man who moves very fast, at his height, flickering.
const Speed: React.FC<{c: FxCtx}> = ({c}) => {
  if (!c.mover || c.t < c.at) return null;
  const rand = rng(c.seed * 37 + 1);
  const f = new THREE.Vector3(Math.sin(c.mover.ry), 0, Math.cos(c.mover.ry));
  const side = new THREE.Vector3(f.z, 0, -f.x);
  const root = new THREE.Vector3(...c.mover.root);
  return (
    <group>
      {Array.from({length: 16}, (_, i) => {
        const len = 2.2 + rand() * 2.6;
        const y = 0.2 + rand() * 1.8;
        const off = (rand() - 0.5) * 1.6;
        const back = 0.6 + rand() * 1.2 + len / 2;
        const on = Math.sin(c.t * 30 + i * 2.1) > -0.3;
        if (!on) return null;
        const p = root.clone().addScaledVector(f, -back).addScaledVector(side, off).setY(root.y + y); // (a plane's are up with it)
        return <P key={i} g={cube()} m={fxMat('#ffffff', 0.55, 1.5)} p={p} s={[0.025, 0.025, len]} r={[0, c.mover!.ry, 0]} />;
      })}
    </group>
  );
};

const Rain: React.FC<{c: FxCtx}> = ({c}) => {
  const rand = rng(c.seed * 41 + 3);
  const m = fxMat('#c9d8ea', 0.45, 0.4);
  return (
    <group position={c.around.toArray()}>
      {Array.from({length: 170}, (_, i) => {
        const x = (rand() - 0.5) * 12;
        const z = (rand() - 0.5) * 12;
        const y0 = rand() * 9;
        const y = ((((y0 - 15 * c.t) % 9) + 9) % 9) - 0.5;
        return <P key={i} g={cube()} m={m} p={[x + 0.12 * y, y, z]} s={[0.012, 0.42, 0.012]} r={[0, 0, 0.12]} />;
      })}
    </group>
  );
};

const Wind: React.FC<{c: FxCtx}> = ({c}) => {
  const rand = rng(c.seed * 43 + 8);
  return (
    <group position={c.around.toArray()}>
      {Array.from({length: 36}, (_, i) => {
        const x0 = rand() * 16;
        const x = ((((x0 + 5 * c.t) % 16) + 16) % 16) - 8;
        const z = (rand() - 0.5) * 8;
        const y = 0.1 + rand() * 2.2 + 0.25 * Math.sin(c.t * 3 + i);
        const col = ['#b88a3c', '#8a6a3a', '#d9d2c4'][i % 3];
        return <P key={i} g={cube()} m={fxMat(col, 0.9)} p={[x, y, z]} s={[0.12, 0.01, 0.08]} r={[c.t * 4 + i, c.t * 3, i]} />;
      })}
    </group>
  );
};

// An emergency light: red and blue turning (a police car or an alarm somewhere close).
const Alarm: React.FC<{c: FxCtx}> = ({c}) => {
  if (c.t < c.at) return null;
  const red = Math.sin(c.t * 9) > 0;
  return <pointLight position={c.point.clone().add(new THREE.Vector3(1.5, 2.6, 2)).toArray()} color={red ? '#ff2a2a' : '#2a6bff'} intensity={5} distance={12} decay={1.4} />;
};

export const FxView: React.FC<{kind: FxKind; c: FxCtx}> = ({kind, c}) => {
  switch (kind) {
    case 'shockwave':
      return <Shockwave c={c} />;
    case 'crack':
      return <Crack c={c} />;
    case 'dust':
      return <Dust c={c} />;
    case 'debris':
      return <Flying c={c} />;
    case 'glass':
      return <Flying c={c} glass />;
    case 'sparks':
      return <Sparks c={c} />;
    case 'smoke':
      return <Smoke c={c} />;
    case 'fire':
      return <Fire c={c} />;
    case 'speed':
      return <Speed c={c} />;
    case 'rain':
      return c.indoor ? null : <Rain c={c} />;
    case 'wind':
      return <Wind c={c} />;
    case 'alarm':
      return <Alarm c={c} />;
    default:
      return null; // shake and flash: the camera and the screen
  }
};

// How hard the camera shakes at t from the shot's shake effects (and the hits that always shake it a little).
export const shakeAt = (fx: {kind: FxKind; at: number}[], t: number) =>
  fx.reduce((s, f) => {
    const tau = t - f.at;
    if (tau < 0) return s;
    const amp = f.kind === 'shake' ? 0.11 : f.kind === 'shockwave' ? 0.05 : 0;
    return s + amp * Math.exp(-tau * 3.5);
  }, 0);

export const flashAt = (fx: {kind: FxKind; at: number}[], t: number) =>
  Math.max(0, ...fx.filter((f) => f.kind === 'flash').map((f) => (t >= f.at ? 0.9 * Math.exp(-(t - f.at) * 9) : 0)));
