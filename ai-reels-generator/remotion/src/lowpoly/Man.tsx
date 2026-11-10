// The low-poly man: a faceted head (an icosphere with each corner nudged, flat shaded), curly hair as a cluster of
// small faceted lumps, square glasses of thin bars, black eyes on white, a little faceted nose, a bar of a mouth,
// a boxy sweater, box arms with faceted hands, box legs and white block shoes. Modelled on the user's own character
// (reference Short 'Life of a Man'); every film uses the same one (cast 'hero').
import React, {useMemo} from 'react';
import * as THREE from 'three';
import type {Design, Hold, PhoneScreen} from './types';
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

// Skin glows a little from within (the reference's faces stay pale and readable in every light, its chins never
// go black): an emissive lift of the skin's own colour under the light.
export const SKIN_GLOW = 0.16;
const skinMat = (c: string) => mat(c, {emissive: c, glow: SKIN_GLOW});

const FaceView: React.FC<{f: Face; design: Design; detail?: boolean}> = ({f, design, detail}) => {
  const z = D.head * 0.935;
  const skin = skinMat(design.skin);
  const dark = mat('#141416', {rough: 0.5});
  const white = mat('#f4f2ee', {rough: 0.5, emissive: '#f4f2ee', glow: 0.12});
  const brow = mat(design.hairStyle === 'bald' ? '#5a4030' : design.hair);
  const er = 0.058 * f.eye;
  const eye = (sx: number) => (
    <group key={sx} position={[sx * 0.118, 0.015, z]} rotation={[0, sx * 0.3, 0]}>
      <mesh geometry={disc(er)} material={white} scale={[1, 0.82, 1]} position={[0, 0, 0.004]} />
      {detail ? (
        // the poster's close-up eye: a brown iris, a pupil, a catchlight and a lash line (a film still, not a sticker)
        <group position={[f.look[0] - sx * 0.004, f.look[1] - 0.004, 0.009]}>
          <mesh geometry={disc(er * 0.74)} material={mat('#5b3a22', {rough: 0.35})} scale={[1, 0.95, 1]} />
          <mesh geometry={disc(er * 0.4)} material={dark} position={[0, 0, 0.003]} />
          <mesh geometry={disc(er * 0.17)} material={mat('#ffffff', {emissive: '#ffffff', glow: 0.9})} position={[er * 0.28, er * 0.28, 0.006]} />
          <mesh geometry={box(er * 2.25, er * 0.28, 0.02)} material={dark} position={[sx * 0.004, er * 0.78, 0.004]} rotation={[0, 0, sx * 0.08]} />
        </group>
      ) : (
        <mesh geometry={disc(er * 0.86)} material={dark} scale={[1, 0.88, 1]} position={[f.look[0] - sx * 0.004, f.look[1] - 0.004, 0.009]} />
      )}
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
        geometry={box(detail ? 0.13 : 0.115, detail ? 0.034 : 0.026, 0.03)}
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
      case 'open':
        // talking: a wider, shorter opening than the 'o' of surprise
        return <mesh geometry={box(0.085, 0.05, 0.02)} material={dark} position={[0, mouthY - 0.005, z - 0.01]} />;
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

// A phone's lit screen. With no story screen: a generic chat, drawn once. With one (story.LPScreen): what the story
// needs there (a 'Mom' chat with 'Where are you?', a call from Dad, the 5:30 alarm...), drawn on a canvas per screen
// and per moment (before / after the last message arrives), cached.
const SW = 540;
const SH = 1056; // the screen plane is 0.088 x 0.172
const FONT = 'Inter, "Helvetica Neue", Arial, sans-serif';
const screens = new Map<string, THREE.CanvasTexture>();

const wrap = (g: CanvasRenderingContext2D, text: string, width: number) => {
  const lines: string[] = [];
  let cur = '';
  for (const w of text.split(/\s+/).filter(Boolean)) {
    const next = cur ? `${cur} ${w}` : w;
    if (g.measureText(next).width > width && cur) {
      lines.push(cur);
      cur = w;
    } else cur = next;
  }
  if (cur) lines.push(cur);
  return lines.slice(0, 4);
};
const round = (g: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number, col: string) => {
  g.fillStyle = col;
  g.beginPath();
  g.roundRect(x, y, w, h, r);
  g.fill();
};
const initial = (name: string) => (name.trim()[0] ?? '?').toUpperCase();
const avatar = (g: CanvasRenderingContext2D, x: number, y: number, r: number, name: string, col = '#7b8ba3') => {
  g.fillStyle = col;
  g.beginPath();
  g.arc(x, y, r, 0, Math.PI * 2);
  g.fill();
  g.fillStyle = '#fff';
  g.font = `700 ${Math.round(r * 1.05)}px ${FONT}`;
  g.textAlign = 'center';
  g.textBaseline = 'middle';
  g.fillText(initial(name), x, y + r * 0.04);
};
const statusBar = (g: CanvasRenderingContext2D, time: string, dark: boolean) => {
  g.fillStyle = dark ? '#fff' : '#111';
  g.font = `600 30px ${FONT}`;
  g.textAlign = 'left';
  g.textBaseline = 'middle';
  g.fillText(time, 40, 40);
  for (let i = 0; i < 4; i++) g.fillRect(410 + i * 13, 50 - (i + 1) * 6, 9, (i + 1) * 6); // signal
  round(g, 470, 26, 44, 24, 6, dark ? '#fff' : '#111'); // battery
  round(g, 473, 29, 30, 18, 4, dark ? '#2a2f38' : '#eef2f7');
  round(g, 473, 29, 22, 18, 4, dark ? '#fff' : '#111');
};
const clockText = (time: string, fallback = '11:47') => (/^\d{1,2}:\d{2}/.test(time.trim()) ? time.trim().split(/\s/)[0] : fallback);

const drawScreen = (g: CanvasRenderingContext2D, sc: PhoneScreen, shown: boolean) => {
  const time = clockText(sc.time);
  const msgs = sc.messages.filter((m) => m.text.trim());
  const visible = shown || sc.arrive === undefined ? msgs : msgs.slice(0, -1);
  g.textAlign = 'left';
  g.textBaseline = 'alphabetic';
  switch (sc.kind) {
    case 'chat': {
      g.fillStyle = '#eef1f5';
      g.fillRect(0, 0, SW, SH);
      g.fillStyle = '#f8f9fb';
      g.fillRect(0, 0, SW, 190);
      statusBar(g, time, false);
      g.fillStyle = '#2f7cf6';
      g.font = `400 54px ${FONT}`;
      g.fillText('‹', 26, 140);
      avatar(g, SW / 2, 118, 38, sc.name || '?');
      g.fillStyle = '#111';
      g.font = `600 28px ${FONT}`;
      g.textAlign = 'center';
      g.fillText(sc.name || 'Message', SW / 2, 182);
      g.textAlign = 'left';
      // bubbles from the bottom up, so the newest is always in view
      g.font = `400 34px ${FONT}`;
      let y = SH - 290; // the hand holding it covers the bottom fifth
      for (let i = visible.length - 1; i >= 0 && y > 220; i--) {
        const m = visible[i];
        const lines = wrap(g, m.text, 330);
        const w = Math.max(...lines.map((l) => g.measureText(l).width)) + 48;
        const h = lines.length * 44 + 30;
        y -= h;
        const x = m.me ? SW - 26 - w : 26;
        round(g, x, y, w, h, 30, m.me ? '#2f7cf6' : '#dfe3ea');
        g.fillStyle = m.me ? '#fff' : '#111';
        lines.forEach((l, k) => g.fillText(l, x + 24, y + 50 + k * 44));
        y -= 18;
      }
      if (!shown && sc.arrive !== undefined && msgs.length) {
        // they are typing: three dots where the last message will land
        round(g, 26, SH - 370, 120, 66, 33, '#dfe3ea');
        g.fillStyle = '#8b93a1';
        for (let k = 0; k < 3; k++) {
          g.beginPath();
          g.arc(60 + k * 26, SH - 337, 9, 0, Math.PI * 2);
          g.fill();
        }
      }
      g.fillStyle = '#f8f9fb';
      g.fillRect(0, SH - 100, SW, 100);
      round(g, 30, SH - 82, SW - 60, 60, 30, '#fff');
      g.fillStyle = '#a3aab6';
      g.font = `400 28px ${FONT}`;
      g.fillText('Message', 60, SH - 42);
      return;
    }
    case 'call': {
      const grd = g.createLinearGradient(0, 0, 0, SH);
      grd.addColorStop(0, '#2d3a4f');
      grd.addColorStop(1, '#0d1118');
      g.fillStyle = grd;
      g.fillRect(0, 0, SW, SH);
      statusBar(g, time, true);
      avatar(g, SW / 2, 330, 110, sc.name || '?', '#56657d');
      g.fillStyle = '#fff';
      g.textAlign = 'center';
      g.font = `600 56px ${FONT}`;
      g.fillText(sc.name || 'Unknown', SW / 2, 530);
      g.fillStyle = '#b8c2d3';
      g.font = `400 32px ${FONT}`;
      g.fillText(shown ? 'incoming call…' : 'mobile', SW / 2, 585);
      const btn = (x: number, col: string, label: string) => {
        g.fillStyle = col;
        g.beginPath();
        g.arc(x, SH - 330, 62, 0, Math.PI * 2);
        g.fill();
        g.fillStyle = '#d5dbe5';
        g.font = `400 26px ${FONT}`;
        g.fillText(label, x, SH - 232);
      };
      btn(140, '#e5483d', 'Decline');
      btn(SW - 140, '#34c759', 'Accept');
      g.fillStyle = '#fff';
      g.font = `700 54px ${FONT}`;
      g.fillText('✕', 140, SH - 312);
      g.fillText('✓', SW - 140, SH - 312);
      return;
    }
    case 'feed': {
      g.fillStyle = '#f2f3f5';
      g.fillRect(0, 0, SW, SH);
      statusBar(g, time, false);
      let y = 100;
      const posts = visible.length ? visible : [{me: false, text: ''}];
      posts.slice(-3).forEach((m, k) => {
        round(g, 20, y, SW - 40, 300, 20, '#fff');
        avatar(g, 66, y + 46, 24, sc.name || 'A', ['#c47a5a', '#5a8fc4', '#7ac45a'][k % 3]);
        g.fillStyle = '#111';
        g.font = `600 26px ${FONT}`;
        g.textAlign = 'left';
        g.fillText(sc.name || 'friend', 104, y + 56);
        const pic = g.createLinearGradient(0, y + 86, 0, y + 210);
        pic.addColorStop(0, ['#f4b183', '#9cc3e6', '#a9d18e'][k % 3]);
        pic.addColorStop(1, ['#c55a11', '#2e75b6', '#548235'][k % 3]);
        g.fillStyle = pic;
        g.fillRect(36, y + 86, SW - 72, 124);
        g.fillStyle = '#222';
        g.font = `400 28px ${FONT}`;
        wrap(g, m.text, SW - 90).slice(0, 2).forEach((l, i) => g.fillText(l, 40, y + 250 + i * 34));
        y += 320;
      });
      return;
    }
    case 'map': {
      g.fillStyle = '#e8ecdf';
      g.fillRect(0, 0, SW, SH);
      g.strokeStyle = '#ffffff';
      g.lineWidth = 26;
      for (const [x1, y1, x2, y2] of [[0, 300, SW, 260], [0, 640, SW, 700], [150, 0, 120, SH], [400, 0, 430, SH]]) {
        g.beginPath();
        g.moveTo(x1, y1);
        g.lineTo(x2, y2);
        g.stroke();
      }
      g.fillStyle = '#b9d9a5';
      g.fillRect(200, 360, 170, 220);
      g.strokeStyle = '#2f7cf6';
      g.lineWidth = 14;
      g.lineCap = 'round';
      g.beginPath();
      g.moveTo(130, 780);
      g.lineTo(130, 660);
      g.lineTo(415, 690);
      g.lineTo(415, 290);
      g.stroke();
      g.fillStyle = '#2f7cf6';
      g.beginPath();
      g.arc(130, 780, 20, 0, Math.PI * 2);
      g.fill();
      g.fillStyle = '#e5483d'; // the pin
      g.beginPath();
      g.arc(415, 250, 30, Math.PI, 0);
      g.lineTo(415, 310);
      g.closePath();
      g.fill();
      statusBar(g, time, false);
      round(g, 20, 80, SW - 40, 160, 24, '#fff'); // the destination at the top: the hand covers the bottom
      g.fillStyle = '#111';
      g.font = `600 34px ${FONT}`;
      g.fillText(sc.name || 'Destination', 50, 142);
      g.fillStyle = '#34a853';
      g.font = `400 28px ${FONT}`;
      g.fillText(visible[0]?.text || '12 min', 50, 192);
      return;
    }
    default: {
      // lock screen, a notification on it, or the alarm ringing
      const grd = g.createLinearGradient(0, 0, SW, SH);
      grd.addColorStop(0, sc.kind === 'alarm' ? '#3b2a1e' : '#1f3550');
      grd.addColorStop(1, '#0b0f17');
      g.fillStyle = grd;
      g.fillRect(0, 0, SW, SH);
      statusBar(g, time, true);
      g.fillStyle = '#fff';
      g.textAlign = 'center';
      if (sc.kind === 'alarm') {
        g.font = `300 150px ${FONT}`;
        g.fillText(clockText(sc.time, '5:30'), SW / 2, 380);
        g.font = `500 40px ${FONT}`;
        g.fillText(sc.name || 'Alarm', SW / 2, 470);
        round(g, 70, SH - 500, SW - 140, 100, 50, '#f29d38');
        round(g, 70, SH - 370, SW - 140, 100, 50, 'rgba(255,255,255,0.18)');
        g.fillStyle = '#fff';
        g.font = `600 40px ${FONT}`;
        g.fillText('Snooze', SW / 2, SH - 436);
        g.fillText('Stop', SW / 2, SH - 306);
        return;
      }
      g.font = `200 160px ${FONT}`;
      g.fillText(time, SW / 2, 270);
      g.font = `400 32px ${FONT}`;
      g.fillStyle = '#c8d0dc';
      g.fillText('Tuesday', SW / 2, 380);
      if (sc.kind === 'notification' && visible.length) {
        let y = 440;
        for (const m of visible.slice(-3)) {
          g.font = `400 32px ${FONT}`;
          const lines = wrap(g, m.text, SW - 170).slice(0, 3);
          const h = 100 + lines.length * 40;
          round(g, 24, y, SW - 48, h, 30, 'rgba(240,243,248,0.92)');
          avatar(g, 78, y + 56, 30, sc.name || '?');
          g.textAlign = 'left';
          g.fillStyle = '#111';
          g.font = `700 30px ${FONT}`;
          g.fillText(sc.name || 'Message', 124, y + 52);
          g.fillStyle = '#6b7380';
          g.font = `400 24px ${FONT}`;
          g.textAlign = 'right';
          g.fillText('now', SW - 50, y + 50);
          g.textAlign = 'left';
          g.fillStyle = '#222';
          g.font = `400 32px ${FONT}`;
          lines.forEach((l, k) => g.fillText(l, 124, y + 96 + k * 40));
          y += h + 16;
        }
      }
      return;
    }
  }
};

let screenTex: THREE.CanvasTexture | null = null;
const phoneScreen = (sc?: PhoneScreen, t = 0) => {
  if (sc) {
    const shown = sc.arrive === undefined || t >= sc.arrive;
    const key = `${JSON.stringify(sc)}|${shown}`;
    let tex = screens.get(key);
    if (!tex) {
      const c = document.createElement('canvas');
      c.width = SW;
      c.height = SH;
      drawScreen(c.getContext('2d')!, sc, shown);
      tex = new THREE.CanvasTexture(c);
      tex.colorSpace = THREE.SRGBColorSpace;
      tex.anisotropy = 8;
      screens.set(key, tex);
    }
    return tex;
  }
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
export const HeldThing: React.FC<{hold: Hold; glow?: boolean; screen?: PhoneScreen; screenT?: number}> = ({hold, screen, screenT}) => {
  switch (hold) {
    case 'phone':
      return (
        <group position={PHONE_AT} rotation={[PHONE_TILT, 0, 0]}>
          <M g={box(0.1, 0.19, 0.016)} m={mat('#1a1b1f', {rough: 0.4})} />
          <mesh position={[0, 0, 0.0085]} rotation={[0, 0, Math.PI]}>
            <planeGeometry args={[0.088, 0.172]} />
            <meshBasicMaterial map={phoneScreen(screen, screenT)} toneMapped={false} />
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

// A hard hat (a yellow faceted dome with a brim and a ridge) or a cap (a dome with a visor), over the hair.
const Hat: React.FC<{kind: 'hardhat' | 'cap'}> = ({kind}) => {
  const hard = kind === 'hardhat';
  const m = mat(hard ? '#e8b21f' : '#2e3f5c', {rough: hard ? 0.55 : 0.9});
  const dome = cached(`dome-${kind}`, () => new THREE.SphereGeometry(D.head * (hard ? 1.13 : 1.08), 10, 5, 0, Math.PI * 2, 0, Math.PI / 2));
  return (
    <group position={[0, hard ? 0.08 : 0.07, -0.01]}>
      <M g={dome} m={m} s={[1, hard ? 0.9 : 0.78, 1.04]} />
      {hard ? (
        <>
          <M g={cached('brim-hard', () => new THREE.CylinderGeometry(D.head * 1.32, D.head * 1.32, 0.03, 12))} m={m} p={[0, 0.005, 0.02]} />
          <M g={box(0.07, 0.07, D.head * 2.1)} m={m} p={[0, D.head * 1.0, 0]} />
        </>
      ) : (
        <M g={box(0.4, 0.025, 0.26)} m={m} p={[0, 0.0, D.head * 1.05]} r={[0.12, 0, 0]} />
      )}
    </group>
  );
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
  detail?: boolean; // the poster's close-ups: eyes with an iris, a catchlight and lashes (FaceView)
  screen?: PhoneScreen; // what a held phone shows (story.LPScreen)
  screenT?: number; // seconds into the shot (the last message arrives at screen.arrive)
}> = ({design, pose: p, face: f, root, ry, hold = 'none', seed, detail, screen, screenT}) => {
  const skin = skinMat(design.skin);
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
          <HeldThing hold={hold} screen={screen} screenT={screenT} />
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
            <FaceView f={f} design={design} detail={detail} />
            {design.glasses ? <Glasses color="#2f2d2c" /> : null}
            {design.beard ? <M g={box(0.42, 0.16, 0.2)} m={hair} p={[0, -0.24, 0.18]} /> : null}
            {design.hat && design.hat !== 'none' ? <Hat kind={design.hat} /> : null}
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
