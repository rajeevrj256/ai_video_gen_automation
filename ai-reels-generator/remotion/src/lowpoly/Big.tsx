// Big things in a shot and what they do: a car, a bus, a truck, a steel beam, a crate, a boulder, a barbell, a pipe,
// a door, a ball. Each is drawn with its bottom at y = 0, centred, its front toward +z, from the same flat-shaded
// boxes as the sets. Its place at time t comes from its motion: still, falling onto its spot, falling into the hands
// of the man who catches it, lifted overhead by the man who lifts it, held, thrown, driving at the man who stops it
// with his hands (and stopping against them, the back rising), driving across, crushed, swinging from the crane.
// Times are the shot's action time (slow motion already applied by the caller).
import React from 'react';
import * as THREE from 'three';
import {facetedBall, mat} from './Man';
import {Girder, spotOf, type SetDef} from './Sets';
import type {Big, BigKind} from './types';

type V3 = [number, number, number];

// width (x), height (y), length (z) of the model as built
const BUILT: Record<BigKind, V3> = {
  car: [1.9, 1.45, 4.2],
  bus: [2.6, 3.1, 10],
  truck: [2.5, 3.4, 8],
  beam: [6, 0.3, 0.3],
  crate: [1.2, 1.2, 1.2],
  boulder: [2.0, 1.8, 2.0],
  barbell: [2.2, 0.46, 0.46],
  pipe: [4, 0.7, 0.7],
  door: [1.0, 2.1, 0.08],
  ball: [0.6, 0.6, 0.6],
};
// Vehicles drawn smaller than real, to the man's own scale: his body is small under his big head (shoulders at 1.24 m),
// and a real-size bus (3.1 m, windows over his head) stood beside him like a yellow wall (the user: "bus size are big
// than humans"). A car's roof now comes to his shoulders and a bus's windows start at his chest, as they would for a
// grown man.
export const MODEL_SCALE: Partial<Record<BigKind, number>> = {car: 0.85, bus: 0.8, truck: 0.8};
// what every placement, lane, collision and camera rule works with: the size as drawn
export const SIZE = Object.fromEntries(
  (Object.keys(BUILT) as BigKind[]).map((k) => [k, BUILT[k].map((v) => v * (MODEL_SCALE[k] ?? 1)) as V3]),
) as Record<BigKind, V3>;

const PAINT = ['#c7473b', '#3d6fa8', '#e2b21f', '#e9e4da', '#3a3d44', '#4f8a5b'];
const G = 14.7; // gravity, a little more than real so falls read heavy at this scale
export const VEHICLE = new Set<BigKind>(['car', 'bus', 'truck']);
// motions a car, bus or truck does on its own (not in someone's hands): on the road, in a lane clear of everyone
export const ROAD_MOTIONS = new Set(['drive', 'still', 'crushed', 'shake', 'fall', 'stop']);

// What the editor needs of a person to hold or stop a thing (LowPoly's Placed, minimally).
export type Holder = {action: string; root: V3; ry: number; head: THREE.Vector3; hand: THREE.Vector3; body: THREE.Vector3; at?: number};

export type BigState = {
  pos: THREE.Vector3; // the pivot, in the world
  ry: number;
  rx: number;
  rz: number;
  pivot: V3; // where the pivot is on the thing (its own frame, bottom-centre = 0)
  squash: [number, number, number];
  contact: THREE.Vector3; // where it touches ground, hands or a man (sparks and dust go here)
  landed: boolean; // it has hit the ground (or the hands) by now
  cable?: number; // a crane cable above it, up to this height
};

const fwdOf = (ry: number) => new THREE.Vector3(Math.sin(ry), 0, Math.cos(ry));

// Who handles a thing with this motion, and when his key moment is.
export const holderFor = (b: Big, people: Holder[]) => {
  const want: Record<string, string[]> = {
    caught: ['catch'],
    hang: ['catch'],
    lifted: ['lift'],
    held: ['lift', 'throw', 'carry'],
    thrown: ['throw', 'lift'],
    stop: ['push-stop'],
  };
  const acts = want[b.motion];
  return acts ? people.find((p) => acts.includes(p.action)) : undefined;
};

// The key moment a thing gives the man handling it (his pose's `at`), in action seconds.
export const keyMoment = (b: Big, dur: number) => {
  const at = b.at ?? dur * 0.4;
  if (b.motion === 'hang') return b.at === undefined ? 99 : b.at + 0.8; // the cable snaps at `at`, it lands in his hands 0.8 s later
  if (b.motion === 'held') return -5;
  return at;
};

// Where the thing is overhead in a man's raised hands: its bottom just above his hands, centred over his head.
const overhead = (h: Holder) => {
  const top = Math.max(h.hand.y + 0.04, h.head.y + 0.42); // on top of his hair (his arms are short for his head)
  return new THREE.Vector3(h.head.x, top, h.head.z);
};

// A thing lying where someone stands is moved behind him (deeper into the place), so it never passes through him.
const aside = (st: BigState, people: Holder[], size: V3) => {
  const near = people.some((p) => Math.hypot(p.root[0] - st.pos.x, p.root[2] - st.pos.z) < Math.max(size[0], size[2]) / 2 + 0.4);
  if (near) {
    const d = Math.min(size[0], size[2]) / 2 + 0.8;
    st.pos.z -= d;
    st.contact.z -= d;
  }
  return st;
};

// `road`: for a vehicle that drives, stands, brakes or falls on its own, its place on the road: `lane` across the way
// it drives (z on a set where walks go along x, else x) and `shift` along it from its spot, chosen once per shot by
// LowPoly's `vehiclePlans` so it never touches anyone, never has the camera inside it and, standing, hides nobody.
export type RoadPlace = {lane: number; shift: number};
export const bigState = (b: Big, set: SetDef, people: Holder[], t: number, dur: number, k: number, road?: RoadPlace): BigState => {
  const size = SIZE[b.kind];
  const sp = spotOf(set, b.spot);
  const onLane = road !== undefined;
  const ground = !road ? new THREE.Vector3(sp.x, 0, sp.z)
    : set.walk === 'x' ? new THREE.Vector3(sp.x + road.shift, 0, road.lane) : new THREE.Vector3(road.lane, 0, sp.z + road.shift);
  const st: BigState = {pos: ground.clone(), ry: onLane ? (set.walk === 'x' ? Math.PI / 2 : 0) : sp.ry, rx: 0, rz: 0, pivot: [0, 0, 0], squash: [1, 1, 1],
    contact: ground.clone(), landed: true};
  const who = holderFor(b, people);
  const ev = b.at ?? dur * 0.4;
  // a beam or a pipe that shakes on a building site hangs from the crane, trembling
  if (b.motion === 'shake' && (b.kind === 'beam' || b.kind === 'pipe') && set.outdoor) {
    const hung = bigState({...b, motion: 'hang', at: undefined}, set, people, t, dur, k);
    hung.rz += 0.05 * Math.sin(t * 31);
    hung.pos.x += 0.03 * Math.sin(t * 23);
    return hung;
  }
  const across = (h: Holder) => h.ry + (size[2] > size[0] ? Math.PI / 2 : 0); // its long side across his shoulders
  switch (b.motion) {
    case 'fall': {
      const dt = ev - t;
      const lift = dt > 0 ? Math.min(30, 0.5 * G * dt * dt) : 0;
      st.pos.y = lift;
      st.landed = dt <= 0;
      if (st.landed) {
        const after = -dt;
        st.pos.y = 0.25 * Math.abs(Math.sin(after * 9)) * Math.exp(-after * 5) * Math.min(1, size[1]);
        st.rz = 0.06 * (1 - Math.exp(-after * 6));
      } else {
        st.rz = 0.15 * Math.sin(t * 2);
      }
      st.contact = ground.clone();
      return st;
    }
    case 'caught':
    case 'hang': {
      const hangY = 4.2; // high over them, still inside a wide shot
      const snap = b.motion === 'hang' ? b.at ?? Infinity : -Infinity;
      const land = b.motion === 'hang' ? snap + 0.8 : ev;
      const target = who ? overhead(who) : ground.clone();
      if (who) st.ry = across(who);
      if (b.motion === 'hang' && t < snap) {
        // swinging on the crane's cable over its spot (or over the man who will catch it)
        const sw = Math.sin(t * 1.25 + (b.at ?? 0));
        st.pos = new THREE.Vector3(target.x + 0.35 * sw, hangY + target.y * 0.3, target.z);
        st.rz = 0.07 * sw;
        st.cable = 30;
        st.landed = false;
        st.contact = st.pos.clone().add(new THREE.Vector3(0, size[1], 0)); // where the cable holds it
        return st;
      }
      if (t < land) {
        // falling: from the snapped cable, or from far above, landing exactly at its moment
        const start = b.motion === 'hang' ? hangY + target.y * 0.3 : target.y + 14;
        const g = b.motion === 'hang' ? (2 * Math.max(0.5, start - target.y)) / 0.64 : G;
        const y = target.y + Math.min(start - target.y, 0.5 * g * (land - t) * (land - t));
        st.pos = new THREE.Vector3(target.x, y, target.z);
        st.rz = 0.1 * Math.sin(t * 3);
        st.landed = false;
        return st;
      }
      st.pos = target;
      st.contact = target.clone();
      return st;
    }
    case 'lifted':
    case 'held':
    case 'thrown': {
      if (!who) return st;
      const f = fwdOf(who.ry);
      st.ry = across(who);
      const depth = Math.min(size[0], size[2]) / 2;
      const low = new THREE.Vector3(who.root[0], 0, who.root[2]).addScaledVector(f, depth + 0.35);
      const high = overhead(who);
      if (who.action === 'carry') {
        st.pos = who.body.clone().addScaledVector(f, 0.42 + depth).setY(who.hand.y - size[1] * 0.3);
        st.contact = who.hand.clone();
        return st;
      }
      if (b.motion === 'thrown' && t > ev) {
        // flung forward and up, turning over as it goes
        const tt = t - ev;
        st.pos = high.clone().addScaledVector(f, 17 * tt).add(new THREE.Vector3(0, 4.5 * tt - 0.5 * 9.8 * tt * tt, 0));
        st.rx = 2.2 * tt;
        st.pivot = [0, size[1] / 2, 0];
        st.pos.y += size[1] / 2;
        st.landed = false;
        return st;
      }
      const up = b.motion === 'held' || b.motion === 'thrown' ? 1 : t < ev ? 0 : Math.min(1, (t - ev) / 0.9);
      const q = up * up * (3 - 2 * up);
      st.pos = low.clone().lerp(high, q);
      st.pos.y += Math.sin(Math.PI * q) * 0.25; // a slight arc up past his face
      st.rx = -0.15 * Math.sin(Math.PI * q);
      st.contact = q > 0.95 ? high.clone() : low.clone();
      return st;
    }
    case 'stop': {
      const speed = 15;
      if (who && VEHICLE.has(b.kind)) {
        const f = fwdOf(who.ry);
        // its front at his hands: he is driven back with it (his root carries the slide), the back rises and settles
        const front = new THREE.Vector3(who.root[0], 0, who.root[2]).addScaledVector(f, 0.9);
        const far = t < ev ? speed * (ev - t) : 0;
        st.pos = front.addScaledVector(f, far);
        st.ry = who.ry + Math.PI;
        st.pivot = [0, 0, size[2] / 2];
        const after = t - ev;
        st.rx = after > 0 ? 0.05 * Math.sin(Math.min(1, after / 0.5) * Math.PI) * Math.exp(-after * 0.8) : 0;
        st.contact = new THREE.Vector3(who.root[0], 1.1, who.root[2]).addScaledVector(f, 0.72);
        return st;
      }
      // no one to stop it: it brakes hard and stops on its spot (along the road)
      const dir = set.walk === 'z' ? new THREE.Vector3(0, 0, 1) : new THREE.Vector3(1, 0, 0);
      const a = 7;
      const dt = ev - t;
      const back = dt <= 0 ? 0 : dt < 2 ? 0.5 * a * dt * dt : 14 + 14 * (dt - 2);
      st.pos = ground.clone().addScaledVector(dir, -back);
      st.ry = set.walk === 'z' ? 0 : Math.PI / 2;
      st.rx = dt <= 0 ? 0.05 * Math.exp(dt * 4) : 0.05;
      return st;
    }
    case 'drive': {
      const dir = set.walk === 'z' ? new THREE.Vector3(0, 0, 1) : new THREE.Vector3(1, 0, 0);
      st.pos = ground.clone().addScaledVector(dir, 14 * (t - ev));
      st.ry = set.walk === 'z' ? 0 : Math.PI / 2;
      return st;
    }
    case 'crushed':
      st.squash = [1.08, 0.55, 0.92];
      st.rz = 0.05;
      return onLane ? st : aside(st, people, size);
    case 'shake':
      st.rz = 0.02 * Math.sin(t * 37);
      st.pos.x += 0.02 * Math.sin(t * 29);
      return st;
    case 'still':
    default:
      void k;
      return onLane ? st : aside(st, people, size);
  }
};

// Is this point inside the thing (with a margin)? The camera must never be: it showed the inside of a bus driving by.
export const insideBig = (b: Big, st: BigState, point: THREE.Vector3, margin = 0.35) => {
  const [w, h, l] = SIZE[b.kind];
  const d = point.clone().sub(st.pos);
  const c = Math.cos(st.ry);
  const s = Math.sin(st.ry);
  const lx = d.x * c - d.z * s + st.pivot[0];
  const lz = d.x * s + d.z * c + st.pivot[2];
  const ly = d.y + st.pivot[1];
  return Math.abs(lx) < w / 2 + margin && Math.abs(lz) < l / 2 + margin && ly > -margin && ly < h * st.squash[1] + margin;
};

// ---------------------------------------------------------------- the models

const Box: React.FC<{p: V3; s: V3; c: string; r?: V3; glow?: number}> = ({p, s, c, r, glow}) => (
  <mesh position={p} rotation={r} castShadow receiveShadow>
    <boxGeometry args={s} />
    <primitive object={glow ? mat(c, {emissive: c, glow}) : mat(c)} attach="material" />
  </mesh>
);
const Wheel: React.FC<{p: V3; r: number}> = ({p, r}) => (
  <group position={p}>
    <mesh rotation={[0, 0, Math.PI / 2]} castShadow receiveShadow>
      <cylinderGeometry args={[r, r, 0.3, 10]} />
      <primitive object={mat('#1d1e22')} attach="material" />
    </mesh>
    <mesh position={[p[0] > 0 ? 0.155 : -0.155, 0, 0]} rotation={[0, 0, Math.PI / 2]}>
      <cylinderGeometry args={[r * 0.5, r * 0.5, 0.02, 8]} />
      <primitive object={mat('#a9adb3', {rough: 0.5})} attach="material" />
    </mesh>
  </group>
);
const GLASS = '#26323f';

const Car: React.FC<{c: string}> = ({c}) => (
  <group>
    <Box p={[0, 0.62, 0]} s={[1.9, 0.56, 4.2]} c={c} />
    <Box p={[0, 1.13, -0.3]} s={[1.68, 0.5, 2.1]} c={c} />
    <Box p={[0, 1.12, 0.78]} s={[1.6, 0.5, 0.05]} c={GLASS} r={[-0.55, 0, 0]} />
    <Box p={[0, 1.12, -1.38]} s={[1.6, 0.46, 0.05]} c={GLASS} r={[0.5, 0, 0]} />
    {[-0.85, 0.85].map((x) => (
      <Box key={x} p={[x, 1.13, -0.3]} s={[0.02, 0.38, 1.9]} c={GLASS} />
    ))}
    <Box p={[0, 0.42, 2.12]} s={[1.95, 0.22, 0.1]} c="#2a2b30" />
    <Box p={[0, 0.42, -2.12]} s={[1.95, 0.22, 0.1]} c="#2a2b30" />
    {[-0.62, 0.62].map((x) => (
      <group key={x}>
        <Box p={[x, 0.72, 2.11]} s={[0.36, 0.14, 0.04]} c="#fff6d8" glow={1.4} />
        <Box p={[x, 0.72, -2.11]} s={[0.36, 0.12, 0.04]} c="#d8352b" glow={0.9} />
      </group>
    ))}
    {[-0.86, 0.86].map((x) => [-1.35, 1.35].map((z) => <Wheel key={`${x}${z}`} p={[x, 0.36, z]} r={0.36} />))}
  </group>
);

const Bus: React.FC<{c: string}> = ({c}) => (
  <group>
    <Box p={[0, 1.75, 0]} s={[2.6, 2.7, 10]} c={c} />
    <Box p={[0, 3.12, 0]} s={[2.5, 0.05, 9.8]} c="#e9e4da" />
    {[-1.31, 1.31].map((x) => (
      <Box key={x} p={[x, 2.25, -0.4]} s={[0.02, 0.85, 8.6]} c={GLASS} />
    ))}
    <Box p={[0, 2.1, 5.01]} s={[2.3, 1.2, 0.03]} c={GLASS} />
    <Box p={[0, 2.95, 5.01]} s={[1.7, 0.25, 0.03]} c="#ffb84a" glow={1.3} />
    {[-0.95, 0.95].map((x) => (
      <Box key={x} p={[x, 0.9, 5.01]} s={[0.35, 0.18, 0.03]} c="#fff6d8" glow={1.4} />
    ))}
    {[-1.21, 1.21].map((x) => [-3.4, 3.4].map((z) => <Wheel key={`${x}${z}`} p={[x, 0.5, z]} r={0.5} />))}
  </group>
);

const Truck: React.FC<{c: string}> = ({c}) => (
  <group>
    <Box p={[0, 1.55, 2.95]} s={[2.5, 2.3, 2.1]} c={c} />
    <Box p={[0, 2.1, 4.01]} s={[2.2, 0.85, 0.03]} c={GLASS} />
    <Box p={[0, 0.85, 4.02]} s={[2.0, 0.5, 0.05]} c="#3a3d44" />
    {[-0.95, 0.95].map((x) => (
      <Box key={x} p={[x, 0.75, 4.03]} s={[0.32, 0.16, 0.03]} c="#fff6d8" glow={1.4} />
    ))}
    <Box p={[0, 1.95, -1.0]} s={[2.5, 2.9, 5.6]} c="#e7e3da" />
    <Box p={[0, 0.45, -1.0]} s={[2.2, 0.25, 5.6]} c="#2a2b30" />
    {[-1.11, 1.11].map((x) => [3.0, -0.4, -2.9].map((z) => <Wheel key={`${x}${z}`} p={[x, 0.5, z]} r={0.5} />))}
  </group>
);

export const BigModel: React.FC<{kind: BigKind; color?: string; seed: number}> = ({kind, color, seed}) => {
  const c = color || PAINT[Math.abs(seed) % PAINT.length];
  switch (kind) {
    case 'car':
      return <Car c={c} />;
    case 'bus':
      return <Bus c={color || '#e2b21f'} />;
    case 'truck':
      return <Truck c={color || '#c7473b'} />;
    case 'beam':
      return <Girder p={[0, 0.15, 0]} len={6} c={color || '#b5532f'} />;
    case 'crate':
      return (
        <group>
          <Box p={[0, 0.6, 0]} s={[1.2, 1.2, 1.2]} c={color || '#a07a4c'} />
          {[0.25, 0.6, 0.95].map((y) => (
            <Box key={y} p={[0, y, 0]} s={[1.22, 0.05, 1.22]} c="#7a5a36" />
          ))}
        </group>
      );
    case 'boulder': {
      const g = facetedBall(1.0, 1, 0.16, seed + 3);
      return (
        <mesh geometry={g} position={[0, 0.9, 0]} scale={[1, 0.9, 1]} castShadow receiveShadow>
          <primitive object={mat(color || '#7d776e')} attach="material" />
        </mesh>
      );
    }
    case 'barbell':
      return (
        <group position={[0, 0.23, 0]}>
          <mesh rotation={[0, 0, Math.PI / 2]} castShadow>
            <cylinderGeometry args={[0.03, 0.03, 2.2, 8]} />
            <primitive object={mat('#b9bcc2', {rough: 0.4})} attach="material" />
          </mesh>
          {[-0.85, -0.72, 0.72, 0.85].map((x) => (
            <mesh key={x} position={[x, 0, 0]} rotation={[0, 0, Math.PI / 2]} castShadow>
              <cylinderGeometry args={[0.23, 0.23, 0.1, 12]} />
              <primitive object={mat('#22252a')} attach="material" />
            </mesh>
          ))}
        </group>
      );
    case 'pipe':
      return (
        <mesh position={[0, 0.35, 0]} rotation={[0, 0, Math.PI / 2]} castShadow receiveShadow>
          <cylinderGeometry args={[0.35, 0.35, 4, 10]} />
          <primitive object={mat(color || '#7f8790')} attach="material" />
        </mesh>
      );
    case 'door':
      return (
        <group>
          <Box p={[0, 1.05, 0]} s={[1.0, 2.1, 0.08]} c={color || '#8e949a'} />
          <Box p={[0.38, 1.0, 0.06]} s={[0.12, 0.04, 0.04]} c="#3a3d44" />
        </group>
      );
    case 'ball':
      return (
        <mesh geometry={facetedBall(0.3, 1, 0.05, seed)} position={[0, 0.3, 0]} castShadow receiveShadow>
          <primitive object={mat(color || '#d8352b')} attach="material" />
        </mesh>
      );
    default:
      return null;
  }
};

export const BigView: React.FC<{b: Big; st: BigState; seed: number}> = ({b, st, seed}) => (
  <group>
    <group position={st.pos} rotation={new THREE.Euler(st.rx, st.ry, st.rz, 'YXZ')}>
      <group position={[-st.pivot[0], -st.pivot[1], -st.pivot[2]]} scale={st.squash}>
        <group scale={MODEL_SCALE[b.kind] ?? 1}>
          <BigModel kind={b.kind} color={b.color} seed={seed} />
        </group>
      </group>
    </group>
    {st.cable ? (
      <mesh position={[st.pos.x, (st.pos.y + SIZE[b.kind][1] + st.cable) / 2, st.pos.z]}>
        <boxGeometry args={[0.04, st.cable - st.pos.y - SIZE[b.kind][1], 0.04]} />
        <primitive object={mat('#2a2b30')} attach="material" />
      </mesh>
    ) : null}
  </group>
);
