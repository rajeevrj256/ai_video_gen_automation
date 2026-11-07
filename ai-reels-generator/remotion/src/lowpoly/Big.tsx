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
import type {Big, BigKind, Made, MadePart} from './types';

type V3 = [number, number, number];

// width (x), height (y), length (z) of the model as built
const BUILT: Record<BigKind, V3> = {
  car: [2.0, 1.44, 4.7], // a full-size luxury sports coupe (the user: "car must be luxury sports versions", "full car. not toy")
  bus: [2.6, 3.1, 10],
  truck: [2.5, 3.4, 8],
  beam: [6, 0.3, 0.3],
  crate: [1.2, 1.2, 1.2],
  boulder: [2.0, 1.8, 2.0],
  barbell: [2.2, 0.46, 0.46],
  pipe: [4, 0.7, 0.7],
  door: [1.0, 2.1, 0.08],
  ball: [0.6, 0.6, 0.6],
  made: [1, 1, 1], // its own size comes with its design (sizeOf)
};
// Vehicles drawn smaller than real, to the man's own scale: his body is small under his big head (shoulders at 1.24 m),
// and a real-size bus (3.1 m, windows over his head) stood beside him like a yellow wall (the user: "bus size are big
// than humans"). A car's roof now comes to his shoulders and a bus's windows start at his chest, as they would for a
// grown man.
export const MODEL_SCALE: Partial<Record<BigKind, number>> = {bus: 0.8, truck: 0.8};
// People seated in a car are drawn smaller than when they stand: his head is as big as a car is high, and seated at
// full size he sat on top of a car that looked like a toy (the user: "full car. not toy"). In a car he sits inside it,
// his head under the roof, seen through the windows.
export const RIDER_SCALE: Partial<Record<BigKind, number>> = {car: 0.64, made: 0.78}; // (in a plane's seat a little smaller too)
// what every placement, lane, collision and camera rule works with: the size as drawn
export const SIZE = Object.fromEntries(
  (Object.keys(BUILT) as BigKind[]).map((k) => [k, BUILT[k].map((v) => v * (MODEL_SCALE[k] ?? 1)) as V3]),
) as Record<BigKind, V3>;

const PAINT = ['#c7473b', '#3d6fa8', '#e2b21f', '#e9e4da', '#3a3d44', '#4f8a5b'];
const SPORT_PAINT = ['#c1121f', '#16171b', '#e8b000', '#e9e6df', '#1f4fa3', '#e2571d', '#8a8f98']; // rosso, black, giallo, white, blue, orange, silver
const G = 14.7; // gravity, a little more than real so falls read heavy at this scale
export const GRAVITY = G;
export const VEHICLE = new Set<BigKind>(['car', 'bus', 'truck']);
// motions a car, bus or truck does on its own (not in someone's hands): on the road, in a lane clear of everyone
export const ROAD_MOTIONS = new Set(['drive', 'still', 'crushed', 'shake', 'fall', 'stop']);

// What the editor needs of a person to hold or stop a thing (LowPoly's Placed, minimally).
export type Holder = {action: string; root: V3; ry: number; head: THREE.Vector3; hand: THREE.Vector3; body: THREE.Vector3; at?: number; on?: number};

// ---------------------------------------------------------------- vehicles under way, and things the writer designed
// The user's film 'Born to Fly' (a driver nobody can catch): every car shot had nobody in it, so the hero was stood on
// the road while a car crossed the frame in under a second. Now a vehicle has seats and people `on` it (at the wheel,
// riding, standing on its roof or wing), it moves like a stunt car (accelerating, drifting, spinning, jumping, taking
// off) or an aircraft (flying, climbing, diving, banking, rolling), and anything the writer needs that isn't built in
// (a plane, a jet, a helicopter, a motorbike, a boat) is designed for the film as low-poly parts (`made`) and built here.
export const UNDERWAY = new Set(['race', 'drift', 'spin', 'reverse', 'jump', 'fly', 'climb', 'dive', 'bank', 'roll']);
const AIRBORNE = new Set(['fly', 'climb', 'dive', 'bank', 'roll']);
export type Travel = 'ground' | 'air' | 'water' | 'none';
let MADE: Record<string, Made> = {};
export const setMade = (m?: Record<string, Made>) => {
  MADE = m ?? {};
};
export const madeOf = (b: Big): Made | undefined => (b.kind === 'made' && b.made ? MADE[b.made] : undefined);
export const sizeOf = (b: Big): V3 => madeOf(b)?.dims ?? SIZE[b.kind] ?? [1, 1, 1];
export const travelOf = (b: Big): Travel => (b.kind === 'made' ? madeOf(b)?.travel ?? 'none' : VEHICLE.has(b.kind) ? 'ground' : 'none');
export const isVehicle = (b: Big) => travelOf(b) !== 'none';
// under way: it travels on its own path and anyone on it travels with it (the camera too); a vehicle with someone at
// the wheel drives that way even when it only 'drive's
export const underway = (b: Big, ridden: boolean) => isVehicle(b) && (UNDERWAY.has(b.motion) || (ridden && (b.motion === 'drive' || b.motion === 'stop')));

// Where people go on a vehicle, in its own frame (metres as drawn): seats (the driver's / pilot's first; the height is
// the seat's top) and places to stand (a roof, a bonnet, a wing).
const SEATS: Record<string, V3[]> = {car: [[-0.4, 0.4, -0.3], [0.4, 0.4, -0.3]], bus: [[-0.75, 0.62, 3.1], [0.6, 0.62, 1.5]], truck: [[-0.55, 0.72, 2.25], [0.55, 0.72, 2.25]]};
const STANDS: Record<string, V3[]> = {car: [[0, 1.44, -0.42], [0, 0.8, 1.45]], bus: [[0, 2.5, -2], [0, 2.5, 2]], truck: [[0, 2.32, -2.2], [0, 2.32, 0.3]]};
export const seatsOf = (b: Big): V3[] => madeOf(b)?.seats ?? SEATS[b.kind] ?? [[0, sizeOf(b)[1], 0]];
export const standsOf = (b: Big): V3[] => {
  const m = madeOf(b);
  if (m) {
    // on the wings when it has them (standing on top of a plane's body is inside it), else along its top
    const [w, , l] = m.dims;
    if (w > 3) return [[w * 0.27, m.top, 0], [-w * 0.27, m.top, 0], [w * 0.4, m.top, 0], [-w * 0.4, m.top, 0]];
    return [[0, m.top, 0], [0, m.top, -l * 0.25], [0, m.top, l * 0.2], [0, m.top, -l * 0.4]];
  }
  return STANDS[b.kind] ?? [[0, sizeOf(b)[1], 0]];
};

// The vehicle's transform (its pivot to the world), for the people riding it.
export const vehicleMatrix = (st: BigState) =>
  new THREE.Matrix4()
    .makeTranslation(st.pos.x, st.pos.y, st.pos.z)
    .multiply(new THREE.Matrix4().makeRotationFromEuler(new THREE.Euler(st.rx, st.ry, st.rz, 'YXZ')))
    .multiply(new THREE.Matrix4().makeTranslation(-st.pivot[0], -st.pivot[1], -st.pivot[2]));

const E = (x: number) => (x <= 0 ? 0 : x >= 1 ? 1 : x * x * (3 - 2 * x)); // eased 0..1
// distance after t s for a speed going linearly between keys [time, m/s] (held before the first and after the last)
const travelled = (keys: [number, number][], t: number) => {
  if (t <= keys[0][0]) return keys[0][1] * (t - keys[0][0]);
  let s = 0;
  for (let i = 1; i < keys.length; i++) {
    const [t0, v0] = keys[i - 1];
    const [t1, v1] = keys[i];
    if (t1 <= t0) continue;
    const end = Math.min(t, t1);
    const ve = v0 + ((v1 - v0) * (end - t0)) / (t1 - t0);
    s += ((v0 + ve) / 2) * (end - t0);
    if (t <= t1) return s;
  }
  const [tl, vl] = keys[keys.length - 1];
  return s + vl * (t - Math.max(tl, keys[0][0]));
};
const speedOf = (keys: [number, number][], t: number) => (travelled(keys, t + 0.05) - travelled(keys, t - 0.05)) / 0.1;

// How a vehicle moves: its speed over time, and around its moment its sideways slide, nose turn, height, pitch, roll.
type Profile = {keys: [number, number][]; lat: number; yaw: number; y: number; pitch: number; roll: number; air: boolean; bank?: number};
const profile = (b: Big, travel: Travel, t: number, at: number, dur: number, alt: number, lift: boolean, k: number): Profile => {
  const tau = t - at;
  const p: Profile = {keys: [[0, 13]], lat: 0, yaw: 0, y: 0, pitch: 0, roll: 0, air: false};
  if (travel === 'air' || AIRBORNE.has(b.motion)) {
    p.keys = travel === 'air' ? [[0, 30]] : [[0, 22]];
    // on the ground it runs, then lifts off at its moment; else it is already up
    const up = lift ? E(tau / 2.6) ** 1.2 : 1;
    p.y = alt * up + 0.25 * Math.sin(t * 0.9 + k) * up;
    p.air = up > 0.02;
    if (lift) p.pitch = tau > 0 ? -0.24 * Math.sin(Math.PI * E(tau / 1.8)) : 0;
    p.roll = 0.04 * Math.sin(t * 0.7 + k) * up;
    if (b.motion === 'climb') {
      p.pitch = -0.32;
      p.y = alt + 8.5 * tau;
    } else if (b.motion === 'dive') {
      p.pitch = 0.38;
      p.y = alt - 9.5 * tau;
    } else if (b.motion === 'bank') {
      p.bank = (k % 2 ? -1 : 1) * 0.42;
      p.roll = -Math.sign(p.bank) * 0.55;
    } else if (b.motion === 'roll') {
      p.roll = 2 * Math.PI * E(tau / 1.3);
    }
    if (!lift) p.y = Math.max(1.5, p.y);
    return p;
  }
  switch (b.motion) {
    case 'race':
      // the foot goes down (the cut-in to the pedal) and it surges
      p.keys = [[0, 15], [0.75, 16], [Math.max(1, dur), 36]];
      p.lat = 0.18 * Math.sin(t * 0.7 + k);
      break;
    case 'drift':
      p.keys = [[0, 23], [at, 23], [at + 0.6, 17]];
      p.yaw = 0.62 * E(tau / 0.35) - 0.62 * E((tau - 1.5) / 0.6);
      p.lat = -1.5 * E(tau / 1.6);
      break;
    case 'spin':
      p.keys = [[0, 21], [at, 21], [at + 1.1, 8], [at + 2.2, 14]];
      p.yaw = 2 * Math.PI * E(tau / 1.1);
      p.lat = -0.9 * E(tau / 1.1);
      break;
    case 'reverse':
      p.keys = [[0, -9]];
      break;
    case 'jump': {
      p.keys = [[0, 24]];
      const T = 1.25;
      if (tau > 0 && tau < T) {
        p.y = 4 * 2.3 * (tau / T) * (1 - tau / T);
        p.pitch = -0.17 * Math.cos((Math.PI * tau) / T);
        p.air = true;
      } else if (tau >= T) {
        p.y = -0.06 * Math.exp(-7 * (tau - T)) * Math.abs(Math.sin(16 * (tau - T)));
        p.pitch = 0.05 * Math.exp(-6 * (tau - T));
      }
      break;
    }
    case 'stop':
      p.keys = [[0, 22], [at, 22], [at + 1.0, 0]];
      p.pitch = tau > 0 && tau < 1.2 ? 0.07 * Math.sin((Math.PI * tau) / 1.2) : 0;
      break;
    default: // drive
      p.keys = [[0, travel === 'water' ? 10 : 13]];
      p.lat = 0.12 * Math.sin(t * 0.8 + k);
  }
  if (travel === 'water') {
    p.y = 0.06 * Math.sin(t * 1.7 + k);
    p.pitch += -0.05 - 0.002 * speedOf(p.keys, t);
    p.roll += 0.04 * Math.sin(t * 1.3 + k);
  }
  return p;
};

// The wheel yanked just before a drift or a spin (action seconds from its moment), held through it, let go after.
const yankOf = (motion: string, tau: number) =>
  motion === 'drift' || motion === 'spin' ? (motion === 'spin' ? -0.75 : -0.55) * (tau < 0 ? E((tau + 0.5) / 0.4) : 1 - E((tau - 0.5) / 0.7)) : 0;

// A vehicle under way at time t: along the set's road (or its walk), at its spot at its moment (a jump at the roof's
// edge), never further than the set reaches; a second one in a shot follows behind in the next lane.
export const ridePath = (b: Big, set: SetDef, t: number, dur: number, k: number, order: number, trail = true): BigState => {
  const size = sizeOf(b);
  const travel = travelOf(b);
  const sp = spotOf(set, b.spot);
  const at = b.at ?? dur * 0.5;
  const sky = !!set.sky;
  const air = travel === 'air' || AIRBORNE.has(b.motion);
  const alt = sky ? 6 : set.outdoor ? 14 : 2.5;
  const lift = air && !sky && b.at !== undefined && b.motion === 'fly'; // a take-off run, then up at its moment
  const shape = (tt: number) => profile(b, travel, tt, at, dur, alt, lift, k + order);
  const pr = shape(t);
  const dir = set.walk === 'z' ? new THREE.Vector3(0, 0, 1) : new THREE.Vector3(1, 0, 0);
  const side = new THREE.Vector3(dir.z, 0, -dir.x);
  const lane = (set.drive ?? set.road ?? (set.walk === 'z' ? sp.x : sp.z)) + (order % 2 ? 3.2 : 0);
  let along0 = b.motion === 'jump' && set.jumpAt !== undefined ? set.jumpAt : set.walk === 'z' ? sp.z : sp.x;
  // the whole run fits the place (a 240 m highway, a row of roofs); in the air and the sky there is no end
  const reach = air || sky ? Infinity : set.reach ?? 30;
  const span = Math.abs(travelled(pr.keys, dur) - travelled(pr.keys, 0));
  const fit = span > reach ? reach / span : 1;
  // where the ground has a gap (between two roofs, a bridge's fallen span) only a jump crosses it: any other run
  // stays on the near side and ends before it (a race on the roofs used to drive across thin air)
  if (set.gap && b.motion !== 'jump' && !air) {
    const ss = Array.from({length: 25}, (_, i) => (travelled(pr.keys, (dur * i) / 24) - travelled(pr.keys, at)) * fit - order * 11);
    const lo = along0 + Math.min(...ss) - size[2] / 2;
    const hi = along0 + Math.max(...ss) + size[2] / 2;
    if (hi > set.gap[0] - 0.8 && lo < set.gap[1] + 0.8) along0 -= hi - (set.gap[0] - 0.8);
  }
  const s = (travelled(pr.keys, t) - travelled(pr.keys, at)) * fit - order * 11;
  const ry0 = Math.atan2(dir.x, dir.z);
  const base = set.walk === 'z' ? new THREE.Vector3(lane, 0, along0) : new THREE.Vector3(along0, 0, lane);
  let pos: THREE.Vector3;
  let heading = ry0;
  if (pr.bank) {
    // a turn: round a circle through its moment
    const R = Math.abs(speedOf(pr.keys, t) / pr.bank);
    const th = pr.bank * (t - at);
    pos = base.clone().addScaledVector(dir, Math.sin(Math.abs(th)) * R * Math.sign(t - at)).addScaledVector(side, (1 - Math.cos(th)) * R * Math.sign(pr.bank));
    heading = ry0 - th;
  } else {
    pos = base.clone().addScaledVector(dir, s).addScaledVector(side, pr.lat);
  }
  const v = speedOf(pr.keys, t) * fit;
  const accel = (speedOf(pr.keys, t + 0.15) - speedOf(pr.keys, t - 0.15)) / 0.3;
  const yawRate = (shape(t + 0.05).yaw - shape(t - 0.05).yaw) / 0.1;
  const h = size[1] / 2;
  const st: BigState = {
    pos: pos.clone().setY(pr.y + h),
    ry: heading + pr.yaw,
    rx: pr.pitch - (pr.air ? 0 : 0.004 * accel),
    rz: pr.roll + Math.max(-0.12, Math.min(0.12, -0.05 * yawRate)),
    pivot: [0, h, 0],
    squash: [1, 1, 1],
    contact: pos.clone().setY(Math.max(0, pr.y)),
    landed: !pr.air,
    speed: Math.abs(v),
    heading,
    wheel: (travelled(pr.keys, t) * fit) / 0.31,
    // before a drift or a spin he yanks the wheel (the cut-in to his hands comes first, then the slide)
    steer: Math.max(-0.75, Math.min(0.75, -0.4 * pr.yaw + yankOf(b.motion, t - at) + (b.motion === 'drive' ? 0.25 * Math.sin(t * 0.8 + k) : 0))),
    air: pr.air,
    yawOff: pr.yaw,
  };
  // tyre smoke behind a drift or a spin, a puff of dust where a jump lands
  if (trail && travel === 'ground') {
    const puffs: {p: THREE.Vector3; age: number}[] = [];
    const smoky = b.motion === 'drift' || b.motion === 'spin' ? [at, at + 2.2] : b.motion === 'jump' ? [at + 1.2, at + 1.6] : null;
    if (smoky) {
      for (let i = 1; i <= 18; i++) {
        const tp = t - i * 0.07;
        if (tp < smoky[0] || tp > smoky[1]) continue;
        const m = vehicleMatrix(ridePath(b, set, tp, dur, k, order, false));
        for (const x of [-0.8, 0.8]) puffs.push({p: new THREE.Vector3(x, 0.25, -1.3).applyMatrix4(m), age: i * 0.07});
      }
    }
    st.trail = puffs;
  }
  return st;
};

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
  // under way (ridePath): how fast (m/s), which way it travels (its nose can point elsewhere in a drift), how far its
  // wheels have turned, the front wheels' steer, whether it is off the ground, smoke left behind
  speed?: number;
  heading?: number;
  wheel?: number;
  steer?: number;
  air?: boolean;
  yawOff?: number;
  trail?: {p: THREE.Vector3; age: number}[];
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
export const bigState = (b: Big, set: SetDef, people: Holder[], t: number, dur: number, k: number, road?: RoadPlace, order = 0): BigState => {
  if (underway(b, people.some((p) => p.on === k))) return ridePath(b, set, t, dur, k, order);
  const size = sizeOf(b);
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
  const [w, h, l] = sizeOf(b);
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
const Wheel: React.FC<{p: V3; r: number; turn?: number; steer?: number; w?: number}> = ({p, r, turn = 0, steer = 0, w = 0.3}) => (
  <group position={p} rotation={[0, steer, 0]}>
    <group rotation={[turn, 0, 0]}>
      <mesh rotation={[0, 0, Math.PI / 2]} castShadow receiveShadow>
        <cylinderGeometry args={[r, r, w, 10]} />
        <primitive object={mat('#1d1e22')} attach="material" />
      </mesh>
      <mesh position={[p[0] > 0 ? w / 2 + 0.005 : -w / 2 - 0.005, 0, 0]} rotation={[0, 0, Math.PI / 2]}>
        <cylinderGeometry args={[r * 0.62, r * 0.62, 0.02, 5]} />
        <primitive object={mat('#a9adb3', {rough: 0.4})} attach="material" />
      </mesh>
    </group>
  </group>
);
// glass you can see the driver through
const glassMats = new Map<string, THREE.Material>();
const glassMat = (c: string, opacity = 0.32) => {
  const key = `${c}|${opacity}`;
  let m = glassMats.get(key);
  if (!m) {
    m = new THREE.MeshStandardMaterial({color: c, roughness: 0.5, metalness: 0, transparent: true, opacity, flatShading: true, depthWrite: false});
    glassMats.set(key, m);
  }
  return m;
};
const Glass: React.FC<{p: V3; s: V3; r?: V3; c?: string; opacity?: number}> = ({p, s: size, r, c = '#9fb6c8', opacity}) => (
  <mesh position={p} rotation={r}>
    <boxGeometry args={size} />
    <primitive object={glassMat(c, opacity)} attach="material" />
  </mesh>
);
const GLASS = '#26323f';

// A full-size luxury sports coupe (the user: "car must be luxury sports versions", then "full car. not toy": the
// first one was an open box on wheels with the man sitting on top, his head taller than the car). Its body is a real
// car's side silhouette (a long bonnet, a raked windscreen, a fastback roof, wheel arches) extruded across its width
// with rounded edges; a glass cabin with pillars and a roof, so whoever drives is seen inside through the windows;
// shiny paint, slim lights, a light bar across the tail, five-spoke wheels with brake callipers. Built 2.0 x 1.44 x 4.7.
const CAR_L = 4.7;
const CAR_W = 2.0;
const WHEEL_Z = 1.45;
const WHEEL_R = 0.36;
const paintMats = new Map<string, THREE.Material>();
// (both sides for the roof and the doors: a camera inside the car sees their inside, the ceiling over his head)
const paintMat = (c: string, both = false) => {
  const key = `${c}|${both}`;
  let m = paintMats.get(key);
  if (!m) {
    m = new THREE.MeshStandardMaterial({color: c, flatShading: true, roughness: 0.3, metalness: 0.1, side: both ? THREE.DoubleSide : THREE.FrontSide});
    paintMats.set(key, m);
  }
  return m;
};
// an outline in the car's side view (z along, y up), extruded across its width with rounded edges
const extruded = (pts: [number, number][], width: number, bevel: number) => {
  const shape = new THREE.Shape(pts.map(([z, y]) => new THREE.Vector2(z, y)));
  const g = new THREE.ExtrudeGeometry(shape, {depth: width - 2 * bevel, bevelEnabled: true, bevelThickness: bevel, bevelSize: bevel, bevelSegments: 2, curveSegments: 4});
  g.rotateY(-Math.PI / 2); // the outline's x becomes the car's z, the extrusion its width
  g.translate(width / 2 - bevel, 0, 0);
  return g;
};
const arch = (zc: number, rear: boolean): [number, number][] => {
  // over a wheel, from its back to its front (the outline runs along the bottom from the tail to the nose)
  const r = 0.45;
  const a0 = Math.atan2(0.18 - 0.36, -Math.sqrt(r * r - 0.18 * 0.18));
  const a1 = Math.atan2(0.18 - 0.36, Math.sqrt(r * r - 0.18 * 0.18));
  const from = a0 < 0 ? a0 + 2 * Math.PI : a0;
  void rear;
  return Array.from({length: 11}, (_, k) => {
    const a = from + ((a1 - from) * k) / 10;
    return [zc + r * Math.cos(a), 0.36 + r * Math.sin(a)];
  });
};
const CAR_BODY = (() => {
  const L = CAR_L / 2;
  const pts: [number, number][] = [
    [-L + 0.12, 0.18],
    ...arch(-WHEEL_Z, true),
    ...arch(WHEEL_Z, false),
    [L - 0.1, 0.2],
    [L + 0.02, 0.31],
    [L, 0.5],
    [L - 0.2, 0.63],
    [1.2, 0.79],
    [0.66, 0.86],
    // the cabin is open inside (the user: "inside the car, char body and car interior must be visible like seat,
    // gear"): the body dips to the floor between the dashboard and the rear bulkhead, the doors are their own panels
    [0.6, 0.86],
    [0.58, 0.3],
    [-0.84, 0.3],
    [-0.86, 0.92],
    [-1.6, 0.92],
    [-L + 0.22, 0.92],
    [-L + 0.02, 0.9],
    [-L - 0.02, 0.6],
    [-L + 0.04, 0.3],
  ];
  return extruded(pts, CAR_W, 0.07);
})();
const KNOB = facetedBall(0.04, 1, 0.05, 11);
const CABIN = extruded([[0.66, 0.84], [-0.08, 1.39], [-0.78, 1.42], [-1.62, 1.04], [-1.85, 0.9], [0.66, 0.86]], 1.66, 0.05);
// a solid roof over the cabin, in the paint, a little wider than the glass (the user: "not half car. add ceiling"):
// the glass cabin with a thin strip on top read from above and in front as an open frame
const ROOF = extruded([[0.04, 1.36], [-0.1, 1.455], [-0.8, 1.485], [-1.5, 1.16], [-1.62, 1.07], [-1.5, 1.08], [-0.8, 1.4], [-0.1, 1.37]], 1.74, 0.04);
// the rear quarters behind the doors: solid, with a fastback window let into the top
const QUARTER = extruded([[-0.8, 0.9], [-0.8, 1.41], [-1.5, 1.09], [-1.84, 0.9]], 1.7, 0.04);
// the doors: the body's sides along the cabin, from the floor to the window line
const DOOR = extruded([[0.6, 0.3], [0.6, 0.87], [-0.86, 0.915], [-0.86, 0.3]], 0.1, 0.02);
const UNDER = '#0d0e10';
const LEATHER = '#2b1d1a';
const TRIM = '#1b1c20';
// a straight piece between two points of the side view, at the car's side or across it
const Strut: React.FC<{a: [number, number]; b: [number, number]; x: number; w: number; t: number; m: THREE.Material}> = ({a, b, x, w, t, m}) => {
  const dz = b[0] - a[0];
  const dy = b[1] - a[1];
  const len = Math.hypot(dz, dy);
  return (
    <mesh position={[x, (a[1] + b[1]) / 2, (a[0] + b[0]) / 2]} rotation={[-Math.atan2(dy, dz), 0, 0]} castShadow material={m}>
      <boxGeometry args={[w, t, len]} />
    </mesh>
  );
};
const CarWheel: React.FC<{p: V3; turn: number; steer: number; caliper: string}> = ({p, turn, steer, caliper}) => {
  const out = p[0] > 0 ? 1 : -1;
  return (
    <group position={p} rotation={[0, steer, 0]}>
      <group rotation={[turn, 0, 0]}>
        <mesh rotation={[0, 0, Math.PI / 2]} castShadow receiveShadow>
          <cylinderGeometry args={[WHEEL_R, WHEEL_R, 0.3, 18]} />
          <primitive object={mat('#16171a')} attach="material" />
        </mesh>
        <mesh position={[out * 0.152, 0, 0]} rotation={[0, 0, Math.PI / 2]}>
          <cylinderGeometry args={[0.255, 0.255, 0.01, 18]} />
          <primitive object={mat('#2b2d31')} attach="material" />
        </mesh>
        {[0, 1, 2, 3, 4].map((k) => (
          <mesh key={k} position={[out * 0.158, 0, 0]} rotation={[(k * 2 * Math.PI) / 5, 0, 0]}>
            <boxGeometry args={[0.02, 0.48, 0.07]} />
            <primitive object={mat('#c3c7cd', {rough: 0.3})} attach="material" />
          </mesh>
        ))}
        <mesh position={[out * 0.16, 0, 0]} rotation={[0, 0, Math.PI / 2]}>
          <cylinderGeometry args={[0.06, 0.06, 0.02, 8]} />
          <primitive object={mat('#c3c7cd', {rough: 0.3})} attach="material" />
        </mesh>
      </group>
      {/* the brake calliper stays put while the wheel turns */}
      <mesh position={[out * 0.12, 0.13, 0.12]} rotation={[0.8, 0, 0]}>
        <boxGeometry args={[0.04, 0.16, 0.08]} />
        <primitive object={mat(caliper)} attach="material" />
      </mesh>
    </group>
  );
};
// the pedals at the driver's feet: the accelerator under his right foot, the brake inboard of it, hinged at the top
const Pedal: React.FC<{x: number; w: number; h: number; press: number}> = ({x, w, h, press}) => (
  <group position={[x, 0.62, 0.36]} rotation={[0.55 - 0.42 * press, 0, 0]}>
    <Box p={[0, -0.06, 0]} s={[0.025, 0.12, 0.025]} c="#2a2b30" />
    <Box p={[0, -0.12 - h / 2, 0.01]} s={[w, h, 0.025]} c="#9aa0a8" />
    {[0, 1, 2].map((r) => <Box key={r} p={[0, -0.12 - h * 0.2 - r * h * 0.3, 0.025]} s={[w * 0.85, 0.008, 0.008]} c="#1d1e22" />)}
  </group>
);
export type Pedals = {gas: number; brake: number};
const SportsCar: React.FC<{c: string; turn?: number; steer?: number; pedals?: Pedals}> = ({c, turn = 0, steer = 0, pedals}) => {
  const paint = paintMat(c);
  const dark = mat('#141518');
  const L = CAR_L / 2;
  const caliper = c === '#e8b000' || c === '#c1121f' ? '#16171b' : '#c8102e';
  return (
    <group>
      <mesh geometry={CAR_BODY} material={paint} castShadow receiveShadow />
      {/* dark wheel wells, so the arches read as holes (nothing seen through) */}
      {[-WHEEL_Z, WHEEL_Z].map((z) => (
        <mesh key={`w${z}`} position={[0, 0.5, z]}>
          <boxGeometry args={[1.4, 0.62, 0.95]} />
          <primitive object={mat(UNDER)} attach="material" />
        </mesh>
      ))}
      {/* the cabin: tinted glass all round, pillars and a roof in the paint */}
      <mesh geometry={CABIN} material={glassMat('#1e2a36', 0.42)} />
      <mesh geometry={ROOF} material={paintMat(c, true)} castShadow receiveShadow />
      <mesh geometry={QUARTER} material={paintMat(c, true)} castShadow receiveShadow />
      {[-1, 1].map((sd) => (
        <group key={`door${sd}`}>
          <mesh geometry={DOOR} position={[sd * (CAR_W / 2 - 0.05), 0, 0]} material={paint} castShadow receiveShadow />
          {/* its inside: trim, an armrest */}
          <Box p={[sd * (CAR_W / 2 - 0.11), 0.6, -0.13]} s={[0.02, 0.5, 1.36]} c={TRIM} />
          <Box p={[sd * (CAR_W / 2 - 0.15), 0.62, -0.25]} s={[0.07, 0.05, 0.5]} c={LEATHER} />
        </group>
      ))}
      <Strut a={[-0.84, 1.42]} b={[-1.46, 1.13]} x={0} w={1.3} t={0.02} m={glassMat('#141c24', 0.85)} />
      <Strut a={[0.66, 0.86]} b={[-0.06, 1.39]} x={0.81} w={0.09} t={0.07} m={paint} />
      <Strut a={[0.66, 0.86]} b={[-0.06, 1.39]} x={-0.81} w={0.09} t={0.07} m={paint} />
      {/* the window line along the doors */}
      {[-0.86, 0.86].map((x) => (
        <Strut key={`l${x}`} a={[0.62, 0.885]} b={[-0.8, 0.915]} x={x} w={0.03} t={0.03} m={mat('#101114', {rough: 0.4})} />
      ))}
      {[-0.82, 0.82].map((x) => (
        <group key={`b${x}`}>
          <Strut a={[-0.78, 0.92]} b={[-0.8, 1.42]} x={x} w={0.05} t={0.09} m={paint} />
          {/* door shut lines and a side intake behind the door */}
          <Box p={[x * 1.22, 0.6, 0.6]} s={[0.012, 0.42, 0.02]} c="#0e0f12" />
          <Box p={[x * 1.22, 0.62, -0.95]} s={[0.012, 0.44, 0.02]} c="#0e0f12" />
          <Box p={[x * 1.225, 0.55, -1.12]} s={[0.012, 0.16, 0.36]} c="#0e0f12" />
          {/* the mirror */}
          <Box p={[x * 1.3, 0.96, 0.42]} s={[0.16, 0.09, 0.14]} c={c} />
        </group>
      ))}
      {/* the nose: slim lights, a dark grille and splitter */}
      {[-0.66, 0.66].map((x) => (
        <Box key={`h${x}`} p={[x, 0.6, L - 0.12]} s={[0.46, 0.06, 0.16]} c="#fff6d8" glow={1.8} r={[0.25, x > 0 ? -0.28 : 0.28, 0]} />
      ))}
      <Box p={[0, 0.36, L + 0.02]} s={[1.1, 0.16, 0.04]} c="#0e0f12" />
      <Box p={[0, 0.2, L - 0.05]} s={[1.9, 0.05, 0.22]} c="#0e0f12" />
      {/* the tail: a light bar across, a dark diffuser, twin exhausts */}
      <Box p={[0, 0.78, -L - 0.03]} s={[1.76, 0.06, 0.04]} c="#e0262b" glow={1.3} />
      <Box p={[0, 0.27, -L + 0.02]} s={[1.6, 0.14, 0.12]} c="#0e0f12" />
      {[-0.45, 0.45].map((x) => (
        <mesh key={`x${x}`} position={[x, 0.28, -L - 0.03]} rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[0.065, 0.065, 0.08, 10]} />
          <primitive object={mat('#9a9ea6', {rough: 0.3})} attach="material" />
        </mesh>
      ))}
      {/* inside: carpet, two leather bucket seats, the centre tunnel with the gear lever, a dashboard with its lit
          dials and screen, the steering wheel where his hands are */}
      {/* (the body's rounded edges grow its outline by 0.07: the cabin's floor is at 0.37, its front wall at z 0.51;
          carpet on both, so the footwell is dark round his feet and the pedals) */}
      <Box p={[0, 0.38, -0.13]} s={[CAR_W - 0.2, 0.025, 1.28]} c="#141417" />
      <Box p={[0, 0.6, 0.5]} s={[CAR_W - 0.2, 0.46, 0.02]} c="#141417" />
      {[-0.4, 0.4].map((x) => (
        <group key={`s${x}`}>
          <Box p={[x, 0.35, -0.32]} s={[0.48, 0.1, 0.5]} c={LEATHER} />
          <Box p={[x, 0.68, -0.62]} s={[0.48, 0.62, 0.1]} c={LEATHER} r={[-0.16, 0, 0]} />
          <Box p={[x, 1.06, -0.69]} s={[0.3, 0.16, 0.08]} c={LEATHER} r={[-0.16, 0, 0]} />
          {[-0.21, 0.21].map((sx) => <Box key={sx} p={[x + sx, 0.47, -0.32]} s={[0.07, 0.12, 0.5]} c={LEATHER} />)}
        </group>
      ))}
      <Box p={[0, 0.46, -0.12]} s={[0.26, 0.3, 1.25]} c={TRIM} />
      <mesh position={[0, 0.69, 0.16]} rotation={[0.25, 0, 0]}>
        <cylinderGeometry args={[0.014, 0.014, 0.16, 6]} />
        <primitive object={mat('#9a9ea6', {rough: 0.3})} attach="material" />
      </mesh>
      <mesh geometry={KNOB} position={[0, 0.77, 0.18]}>
        <primitive object={mat('#2a2b2f', {rough: 0.35})} attach="material" />
      </mesh>
      <Box p={[0, 0.79, 0.45]} s={[CAR_W - 0.2, 0.15, 0.34]} c="#17181b" />
      <Pedal x={-0.5} w={0.06} h={0.16} press={pedals?.gas ?? 0} />
      <Pedal x={-0.36} w={0.1} h={0.09} press={pedals?.brake ?? 0} />
      <Box p={[-0.4, 0.87, 0.33]} s={[0.36, 0.1, 0.02]} c="#6fc6ff" glow={0.7} r={[-0.3, 0, 0]} />
      <Box p={[0.04, 0.88, 0.4]} s={[0.26, 0.15, 0.02]} c="#4f86c6" glow={0.6} r={[-0.3, 0, 0]} />
      {/* the steering wheel on its column, which runs forward and down into the dashboard (the user: "why steering
          move toward the character, it must be attached to car": it hung in the air, its top leaning at him) */}
      <group position={[-0.4, 0.78, 0.08]} rotation={[0.5, 0, steer * 2.2]}>
        <mesh>
          <torusGeometry args={[0.19, 0.026, 6, 18]} />
          <primitive object={dark} attach="material" />
        </mesh>
        <Box p={[0, -0.04, 0]} s={[0.3, 0.04, 0.03]} c="#141518" />
        <Box p={[0, 0, -0.03]} s={[0.08, 0.08, 0.06]} c="#202125" />
      </group>
      <group position={[-0.4, 0.78, 0.08]} rotation={[0.5, 0, 0]}>
        <mesh position={[0, 0, 0.19]} rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[0.035, 0.05, 0.38, 8]} />
          <primitive object={dark} attach="material" />
        </mesh>
        <Box p={[0, 0, 0.27]} s={[0.12, 0.11, 0.22]} c="#17181b" />
      </group>
      <Box p={[-0.4, 0.7, 0.5]} s={[0.56, 0.12, 0.2]} c="#17181b" />
      {[-0.86, 0.86].map((x) =>
        [-WHEEL_Z, WHEEL_Z].map((z) => <CarWheel key={`${x}${z}`} p={[x, WHEEL_R, z]} turn={turn} steer={z > 0 ? steer : 0} caliper={caliper} />),
      )}
    </group>
  );
};

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

// A part of something the writer designed: a box, a cylinder or cone (along its own y), a squashed sphere, or a wedge
// (a box narrowing to its front, for noses, tails and fins), turned, coloured, lit or see-through; propellers, rotors and
// wheels spin while it moves.
const geoms = new Map<string, THREE.BufferGeometry>();
const geomOf = (shape: string, size: [number, number, number]) => {
  const key = `${shape}|${size.map((v) => v.toFixed(3)).join(',')}`;
  let g = geoms.get(key);
  if (!g) {
    const [a, b, c] = size.map((v) => Math.max(0.01, v));
    if (shape === 'cylinder') g = new THREE.CylinderGeometry(c / 2 || a / 2, a / 2, b, 10);
    else if (shape === 'cone') g = new THREE.CylinderGeometry(Math.min(c, a) * 0.02, a / 2, b, 10);
    else if (shape === 'sphere') {
      g = new THREE.SphereGeometry(0.5, 9, 6);
      g.scale(a, b, c);
    } else if (shape === 'wedge') {
      g = new THREE.BoxGeometry(a, b, c, 1, 1, 1);
      const pos = g.attributes.position as THREE.BufferAttribute;
      for (let i = 0; i < pos.count; i++) {
        if (pos.getZ(i) > 0) {
          pos.setX(i, pos.getX(i) * 0.3);
          pos.setY(i, pos.getY(i) * 0.3 - b * 0.12);
        }
      }
      g.computeVertexNormals();
    } else g = new THREE.BoxGeometry(a, b, c);
    geoms.set(key, g);
  }
  return g;
};
const D2R = Math.PI / 180;
const MadePartView: React.FC<{p: MadePart; spin: number}> = ({p, spin}) => {
  const material = p.glass ? glassMat(p.color, 0.35) : p.glow ? mat(p.color, {emissive: p.color, glow: 1.5}) : mat(p.color);
  const t = p.turn ?? [0, 0, 0];
  const sp: V3 = p.spin === 'x' ? [spin, 0, 0] : p.spin === 'y' ? [0, spin, 0] : p.spin === 'z' ? [0, 0, spin] : [0, 0, 0];
  return (
    <group position={p.at} rotation={[t[0] * D2R, t[1] * D2R, t[2] * D2R]}>
      <group rotation={sp}>
        <mesh geometry={geomOf(p.shape, p.size)} castShadow={!p.glass} receiveShadow>
          <primitive object={material} attach="material" />
        </mesh>
      </group>
    </group>
  );
};
export const MadeModel: React.FC<{m: Made; spin: number}> = ({m, spin}) => (
  <group>
    {m.parts.map((p, i) => (
      <MadePartView key={i} p={p} spin={spin} />
    ))}
  </group>
);

export const BigModel: React.FC<{kind: BigKind; color?: string; seed: number; open?: boolean; turn?: number; steer?: number; made?: Made; pedals?: Pedals}> = ({kind, color, seed, open = false, turn = 0, steer = 0, made, pedals}) => {
  const c = color || PAINT[Math.abs(seed) % PAINT.length];
  void open; // (a car is always the closed coupe now; whoever drives is seen through its glass)
  switch (kind) {
    case 'made':
      return made ? <MadeModel m={made} spin={turn} /> : null;
    case 'car':
      return <SportsCar c={color || SPORT_PAINT[Math.abs(seed) % SPORT_PAINT.length]} turn={turn} steer={steer} pedals={pedals} />;
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

// Tyre smoke and dust left behind (world positions, growing and fading with age).
const puffMats = new Map<number, THREE.Material>();
const puffMat = (o: number) => {
  const q = Math.round(o * 10) / 10;
  let m = puffMats.get(q);
  if (!m) {
    m = new THREE.MeshStandardMaterial({color: '#d9d6d0', roughness: 1, transparent: true, opacity: q, flatShading: true, depthWrite: false});
    puffMats.set(q, m);
  }
  return m;
};
const PUFF = facetedBall(0.5, 1, 0.12, 5);
const Trail: React.FC<{puffs: {p: THREE.Vector3; age: number}[]}> = ({puffs}) => (
  <group>
    {puffs.map((u, i) => {
      const r = 0.35 + u.age * 1.4;
      return <mesh key={i} geometry={PUFF} position={u.p.toArray()} scale={[r, r * 0.7, r]} material={puffMat(Math.max(0, 0.55 * (1 - u.age / 1.3)))} />;
    })}
  </group>
);

export const BigView: React.FC<{b: Big; st: BigState; seed: number; open?: boolean; t?: number; night?: boolean; pedals?: Pedals; children?: React.ReactNode}> = ({b, st, seed, open = false, t = 0, night = false, pedals, children}) => {
  const size = sizeOf(b);
  const made = madeOf(b);
  // wheels turn with the distance; a designed thing's propellers and rotors spin fast whenever it is under way
  const turn = made && made.travel === 'air' ? (st.speed ? t * 46 : 0) : st.wheel ?? 0;
  return (
    <group>
      <group position={st.pos} rotation={new THREE.Euler(st.rx, st.ry, st.rz, 'YXZ')}>
        <group position={[-st.pivot[0], -st.pivot[1], -st.pivot[2]]} scale={st.squash}>
          <group scale={MODEL_SCALE[b.kind] ?? 1}>
            <BigModel kind={b.kind} color={b.color} seed={seed} open={open} turn={turn} steer={st.steer ?? 0} made={made} pedals={pedals} />
          </group>
          {night && b.kind === 'car' ? (
            <>
              {/* at night its headlights light the road ahead, and a soft light from above keeps a dark car's shape */}
              <pointLight position={[0, 0.7, size[2] / 2 + 3.5]} color="#ffe7b8" intensity={4.5} distance={14} decay={1.4} />
              <pointLight position={[0, 1.8, -size[2] / 2 - 2.2]} color="#ffd2b0" intensity={3} distance={6} decay={1.3} />
            </>
          ) : null}
          {children}
        </group>
      </group>
      {st.cable ? (
        <mesh position={[st.pos.x, (st.pos.y + size[1] + st.cable) / 2, st.pos.z]}>
          <boxGeometry args={[0.04, st.cable - st.pos.y - size[1], 0.04]} />
          <primitive object={mat('#2a2b30')} attach="material" />
        </mesh>
      ) : null}
      {st.trail && st.trail.length ? <Trail puffs={st.trail} /> : null}
    </group>
  );
};
