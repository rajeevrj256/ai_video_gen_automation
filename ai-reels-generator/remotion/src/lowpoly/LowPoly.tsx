// The "LowPoly" composition (reelgen/lowpoly/): one 3D canvas for the whole film. Each shot puts the cast on a set
// under a time-of-day light and frames them with a camera rule (face, top, medium, wide, side, front, back, low,
// detail) that follows the focus actor, with a slow push and a breath of sway. Depth of field (three's BokehPass)
// keeps the subject sharp; grain, a vignette and a soft grade finish the picture; the narrator's words come up two or
// three at a time in Anton capitals, time stamps take the caption's place, the last line can be red; the channel's
// name sits at the top. Picture only: reelgen/lowpoly/ mixes the sound.
import '@fontsource/anton/400.css';
import '@fontsource/inter/500.css';
import '@fontsource/inter/700.css';
import '@fontsource/special-elite/400.css';
import React, {useEffect, useLayoutEffect, useMemo, useState} from 'react';
import {AbsoluteFill, continueRender, delayRender, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import {ThreeCanvas} from '@remotion/three';
import {useFrame, useThree} from '@react-three/fiber';
import * as THREE from 'three';
import {EffectComposer} from 'three/examples/jsm/postprocessing/EffectComposer.js';
import {RenderPass} from 'three/examples/jsm/postprocessing/RenderPass.js';
import {BokehPass} from 'three/examples/jsm/postprocessing/BokehPass.js';
import {OutputPass} from 'three/examples/jsm/postprocessing/OutputPass.js';
import {D, HEAD_Y, HERO, Man, mat, PHONE_AT, PHONE_TILT} from './Man';
import {face, pose, SPEED, type Pose} from './poses';
import {LOOKS, Overgrowth, SETS, spotOf, ThingView, type SetDef} from './Sets';
import {
  bigState,
  BigView,
  GRAVITY,
  holderFor,
  insideBig,
  isVehicle,
  keyMoment,
  ridePath,
  RIDER_SCALE,
  ROAD_MOTIONS,
  seatsOf,
  setMade,
  sizeOf,
  standsOf,
  underway,
  VEHICLE,
  vehicleMatrix,
  type BigState,
  type Holder,
  type Pedals,
  CLUSTER,
  type RoadPlace,
  type Nudge,
  headOf,
  outlineOf,
  isCreature,
} from './Big';
import {flashAt, FxView, shakeAt, type FxCtx} from './Fx';
import type {Action, Actor, Big, Cam, Caption, Design, Fx, Hold, Insert, LowPolyProps, LPShot, NameCard} from './types';
import {PosterBusts, PosterScene, PosterWords} from './Poster';

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;
type V3 = [number, number, number];
const V = (a: V3) => new THREE.Vector3(...a);

const SEATED = new Set<Action>(['sit', 'type', 'eat', 'shoes', 'get-up', 'read', 'phone', 'head-in-hands', 'slump', 'think', 'drink', 'sigh', 'nod', 'shake-head', 'shrug', 'cry', 'stretch', 'reach']);
const LYING = new Set<Action>(['lie', 'lie-side', 'lie-phone', 'sit-up']);
const MOVING = new Set<Action>(['walk', 'run', 'jog', 'dash', 'flee']);
const moves = (a: Actor) => MOVING.has(a.action) || (a.action === 'carry' && !!a.to);
export const SLOW = 0.4; // slow motion: the action at this speed
// the shot's clock for the action (slow motion runs it at SLOW), from the shot's own seconds
export const actionTime = (shot: LPShot, t: number) => (shot.slowmo ? t * SLOW : t);

// When an actor's key moment is (the catch, the lift, the stop, the jump), in action seconds: his own `at`, else the
// moment of the big thing he handles, else the shot's first effect.
const ACT_BIG: Partial<Record<Action, string[]>> = {catch: ['caught', 'hang'], lift: ['lifted', 'held', 'thrown'], throw: ['thrown', 'held'], 'push-stop': ['stop']};
export const actorAt = (a: Actor, shot: LPShot): number | undefined => {
  const da = actionTime(shot, shot.duration);
  if (a.at !== undefined) return actionTime(shot, a.at);
  const b = (shot.big ?? []).find((x) => ACT_BIG[a.action]?.includes(x.motion));
  if (b) return keyMoment(scaledBig(b, shot), da);
  const f = (shot.fx ?? []).find((x) => x.at !== undefined && x.kind !== 'rain' && x.kind !== 'wind');
  return f ? actionTime(shot, f.at!) : undefined;
};
const scaledBig = (b: Big, shot: LPShot): Big => (b.at === undefined ? b : {...b, at: actionTime(shot, b.at)});
const FACE_CAMS = new Set<Cam>(['face', 'face-top', 'medium', 'detail', 'low', 'front']);
const AUTO_HOLD: Partial<Record<Action, Hold>> = {phone: 'phone', 'lie-phone': 'phone', drink: 'mug', read: 'book', eat: 'fork', crush: 'mug'};
// people who talk or react turn to the room even at a spot that faces into the set (the counter, the window)
const TO_ROOM = new Set<Action>(['talk', 'gasp', 'cheer', 'point', 'shrug', 'nod', 'shake-head', 'wave', 'look-hands', 'crush']);

export type Placed = {
  actor: Actor;
  design: Design;
  pose: Pose;
  root: V3;
  ry: number;
  head: THREE.Vector3; // world
  hand: THREE.Vector3; // his right hand (where a held thing is), world
  screen: THREE.Vector3; // which way a held phone's screen faces, world
  faceDir: THREE.Vector3; // where the face looks
  headUp: THREE.Vector3; // toward the top of the head
  body: THREE.Vector3; // middle of the body
  hold: Hold;
  seed: number;
  aim?: THREE.Vector3; // the head of the person he looks at (`look`), for the two-shot cameras
  // in or on a vehicle: where he is in its own frame (root, ry) and the vehicle's frame in the world (pos, quat); he
  // is drawn inside that frame, so he turns, pitches and rolls with it
  local?: {root: V3; ry: number; pos: THREE.Vector3; quat: THREE.Quaternion};
  ride?: number; // the index of the vehicle he is in or on (shot.big)
  inside?: boolean; // seated inside a closed car (under its roof)
  pedalAt?: {gas: V3; brake: V3}; // a driver: where the ball of his right foot rests on each pedal (the car's own frame)
};

// Where each person stands in a shot: an offset from their spot (sideways, so two people never share a spot and
// walkers go side by side or pass each other), and for a walk to someone's spot, where he stops in front of them.
export type Lane = {off: [number, number]; to?: [number, number]};
// Which way he turns: toward the person he looks at (`explicit`), else toward the nearest one, a little.
type Aim = {x: number; z: number; explicit: boolean};
export const STOP_SHORT = 1.2; // = timeline.STOP_SHORT: a walk to someone's spot ends this far in front of them
export const STOP_SEATED = 1.65; // = timeline.STOP_SEATED: ...or of someone on a seat (past their knees and the table)
const SEAT_SPOTS = new Set(['chair', 'couch', 'desk', 'bed']); // = timeline.SEAT_SPOTS
const GAP = 0.8; // two people's middles never closer than this (heads are 0.7 wide)
const WIDE_NEAR = 5; // outdoors the wide camera never closer than this to its subject
const wrap = (d: number) => Math.atan2(Math.sin(d), Math.cos(d));
const clampTo = (d: number, most: number) => Math.max(-most, Math.min(most, d));

// facing in the room's own terms: 'camera' keeps the spot's natural way (at the desk, toward the screen), 'away' turns
// his back to the open side (toward the counter, the window, the door), left/right face across the room
const FACING: Record<string, number> = {left: -Math.PI / 2, right: Math.PI / 2, away: Math.PI};

// Where an actor is at time t: his spot (and the seat or bed there), his walk, his pose, and the world positions the
// camera needs (computed with the same rotations the Man applies).
export const place = (a: Actor, k: number, set: SetDef, shot: LPShot, tReal: number, cast: Record<string, Design>, others: Placed[] = [], aim?: Aim, lane?: Lane): Placed => {
  const t = actionTime(shot, tReal);
  const dur = actionTime(shot, shot.duration);
  const design = cast[a.who] ?? (a.who === 'hero' ? HERO : HERO);
  const sp = spotOf(set, a.spot);
  let ry = sp.ry;
  let root: V3 = [sp.x, 0, sp.z];
  let action = a.action;
  const lying = LYING.has(action);
  let seat: number | null = sp.seat !== undefined && SEATED.has(action) ? sp.seat : null;
  if (a.spot === 'bed' && sp.bed !== undefined) {
    if (lying) {
      root = [sp.x, sp.bed + 0.2, sp.z];
      ry = 0;
    } else if (seat !== null || action === 'sit') {
      root = [sp.x, 0, -0.45];
      ry = 0;
      seat = sp.seat ?? 0.55;
    }
  } else if (lying) {
    root = [sp.x, 0.2, sp.z]; // on the floor
  }
  // not sitting at a seat spot (standing at the bench, lying on the floor by the couch, walking off from the chair): at
  // the spot's standing place, never inside the seat (the user's hero stood inside the bus stop's bench)
  const inBed = a.spot === 'bed' && sp.bed !== undefined && (lying || seat !== null || action === 'sit');
  if (sp.stand && seat === null && action !== 'sit' && !inBed && action !== 'carried') root = [sp.stand[0], root[1], sp.stand[1]];
  // stopping a vehicle with his bare hands happens on the road, where it drives (not on the pavement or in the shelter)
  if (action === 'push-stop' && set.road !== undefined && set.walk === 'x') root = [root[0], root[1], set.road];
  const turn = FACING[a.facing ?? 'camera'];
  if (turn !== undefined && seat === null && !lying) ry = turn;
  // stopping a vehicle with his hands: he faces up the road (it comes from there), the way away from the set's wide
  // camera, so the vehicle lies beyond him and never between that camera and him. 'camera' is every actor's default,
  // so it never counted as told otherwise: he faced the spot's way, the bus came from behind the camera and a wide shot
  // showed only its side. On a road it comes only along the road (another way would bring it over the pavement).
  if (action === 'push-stop') {
    const up = set.walk === 'z' ? (set.wide.pos[2] >= 0 ? Math.PI : 0) : set.wide.pos[0] >= 0 ? -Math.PI / 2 : Math.PI / 2;
    if ((set.road !== undefined && set.walk === 'x') || (a.facing ?? 'camera') === 'camera') ry = up;
  }
  // his lane in this shot (`lanesFor`): two people never on one spot, walkers side by side, never through anyone
  const off = lane?.off ?? [0, 0];
  if (action !== 'carried') root = [root[0] + off[0], root[1], root[2] + off[1]];
  if (action === 'sit' && seat === null) seat = 0.46; // a chair the set doesn't have: drawn under him
  // a spot that faces into the set (the counter, the mirror, a window) turns him round when the camera wants his face
  if ((a.facing ?? 'camera') === 'camera' && Math.cos(ry) < -0.5 && !lying && !moves(a) && action !== 'push-stop' && (FACE_CAMS.has(shot.camera) || TO_ROOM.has(action))) ry += Math.PI;
  // standing, he turns to the person he looks at (all the way round: the son points AT his dad on the chair); with
  // nobody named, toward the nearest one a little (fully to help them up), so the camera still sees his face.
  // Sitting, lying, walking or in a power move, his body keeps its way (his head turns, below).
  if (aim && seat === null && !lying && !moves(a) && !LONE.has(action) && (aim.explicit || (a.facing ?? 'camera') === 'camera')) {
    const diff = wrap(Math.atan2(aim.x - root[0], aim.z - root[2]) - ry);
    ry += clampTo(diff, aim.explicit || FULL_TURN.has(action) ? Math.PI : 0.6);
  }
  if (action === 'skydive') {
    // falling free at about 9 m/s (high over the clouds in the sky), drifting a little with the wind
    root = [root[0] + 0.8 * t, (set.sky ? 6 : 24) - 9 * t, root[2]];
  }
  const moving = moves(a);
  if (moving) {
    const speed = SPEED[action] ?? 1;
    const dist = speed * dur;
    let from = V([root[0], 0, root[2]]);
    let to: THREE.Vector3;
    if (lane?.to) {
      to = V([lane.to[0], 0, lane.to[1]]); // in front of the person standing or sitting where he goes
    } else if (a.to) {
      const b = spotOf(set, a.to);
      const [bx, bz] = b.stand ?? [b.x, b.z]; // to a free seat spot: he arrives at its standing place
      to = V([bx + off[0], 0, bz + off[1]]);
    } else {
      const dir = set.walk === 'x' ? new THREE.Vector3(a.facing === 'left' ? -1 : 1, 0, 0) : new THREE.Vector3(0, 0, a.facing === 'away' ? -1 : 1);
      from = from.clone().addScaledVector(dir, -dist * (set.walk === 'z' ? 0.6 : 0.5));
      to = from.clone().addScaledVector(dir, dist);
    }
    const len = Math.max(0.001, from.distanceTo(to));
    const along = Math.min(len, speed * t);
    const p = from.clone().lerp(to, along / len);
    root = [p.x, 0, p.z];
    ry = Math.atan2(to.x - from.x, to.z - from.z);
    if (along >= len - 0.01) action = action === 'carry' ? 'carry' : 'stand';
  }
  // carried: lying across the arms of the one who carries him (placed before him), his head to that man's right
  const carrier = action === 'carried' ? others.find((o) => o.actor.action === 'carry') : undefined;
  if (carrier) {
    const f = new THREE.Vector3(Math.sin(carrier.ry), 0, Math.cos(carrier.ry));
    const right = new THREE.Vector3(f.z, 0, -f.x);
    const at = new THREE.Vector3(...carrier.root).addScaledVector(f, 0.62).addScaledVector(right, -0.12);
    root = [at.x, carrier.pose.y + 0.3, at.z];
    ry = carrier.ry - Math.PI / 2;
  }
  const ps = pose({action, t, dur, seat, k: k * 1.7 + (shot.seed ?? 0), at: actorAt(a, shot), moving});
  if (lying) ps.y = 0;
  // the head turns to the one he looks at when his body can't (sitting, walking past, mid power move), at most ~65°
  if (aim?.explicit && !lying && action !== 'carried') {
    const diff = wrap(Math.atan2(aim.x - root[0], aim.z - root[2]) - ry - ps.twist);
    if (Math.abs(diff) > 0.08) ps.head = [ps.head[0], ps.head[1] + clampTo(diff, 1.15), ps.head[2]];
  }
  if (ps.shift) {
    // the pose moves the whole body in his own frame (a jump's drift, feet driven back)
    const f = new THREE.Vector3(Math.sin(ry), 0, Math.cos(ry));
    const right = new THREE.Vector3(f.z, 0, -f.x);
    root = [root[0] + right.x * ps.shift[0] + f.x * ps.shift[1], root[1], root[2] + right.z * ps.shift[0] + f.z * ps.shift[1]];
  }
  return kin(a, action, k, shot, design, ps, root, ry);
};

// Where the ball of his right foot is (the same chain the Man draws: pelvis -> thigh -> knee -> shin -> shoe), in the
// frame his root is in.
const footOf = (design: Design, ps: Pose, root: V3, ry: number): V3 => {
  const scale = design.height ?? 1;
  const one = new THREE.Vector3(1, 1, 1);
  const q = new THREE.Quaternion().setFromEuler(new THREE.Euler(0, ry, 0)).multiply(new THREE.Quaternion().setFromEuler(new THREE.Euler(ps.rx, 0, ps.rz)));
  const leg = new THREE.Matrix4().compose(new THREE.Vector3(D.legX, 0, 0), new THREE.Quaternion().setFromEuler(new THREE.Euler(ps.legR.x, 0, ps.legR.z)), one);
  const knee = new THREE.Matrix4().compose(new THREE.Vector3(0, -D.thigh, 0), new THREE.Quaternion().setFromEuler(new THREE.Euler(ps.legR.bend, 0, 0)), one);
  const ball = new THREE.Vector3(0, -D.shin - D.shoe[1] + 0.02, 0.05 + D.shoe[2] * 0.32).applyMatrix4(knee).applyMatrix4(leg);
  return V(root).add(new THREE.Vector3(0, ps.y * scale, 0)).add(ball.multiplyScalar(scale).applyQuaternion(q)).toArray() as V3;
};

// Forward kinematics: where his head, face, hands and body are in the world (or in a vehicle's own frame), with the
// rotations the Man applies.
const kin = (a: Actor, action: Action, k: number, shot: LPShot, design: Design, ps: Pose, root: V3, ry: number): Placed => {
  // forward kinematics for the head: root -> pelvis (rx, rz) -> torso (lean, twist, side) -> head (its own turn)
  const scale = design.height ?? 1;
  const qRoot = new THREE.Quaternion().setFromEuler(new THREE.Euler(0, ry, 0));
  const qPelvis = new THREE.Quaternion().setFromEuler(new THREE.Euler(ps.rx, 0, ps.rz));
  const qTorso = new THREE.Quaternion().setFromEuler(new THREE.Euler(ps.lean, ps.twist, ps.side));
  const qHead = new THREE.Quaternion().setFromEuler(new THREE.Euler(...ps.head));
  const q = qRoot.clone().multiply(qPelvis).multiply(qTorso);
  const pelvis = V(root).add(new THREE.Vector3(0, ps.y * scale, 0));
  const head = pelvis.clone().add(new THREE.Vector3(0, HEAD_Y * scale, 0).applyQuaternion(q));
  const qh = q.clone().multiply(qHead);
  const faceDir = new THREE.Vector3(0, 0, 1).applyQuaternion(qh);
  const headUp = new THREE.Vector3(0, 1, 0).applyQuaternion(qh);
  const body = pelvis.clone().lerp(head, 0.4);
  // the right hand, through the same chain the Man draws: shoulder -> upper arm -> elbow -> forearm -> hand
  const sx = D.torso[0] / 2 + D.arm[0] / 2 + 0.005;
  const arm = new THREE.Matrix4().compose(new THREE.Vector3(sx, D.torso[1] - 0.06, 0), new THREE.Quaternion().setFromEuler(new THREE.Euler(ps.armR.x, 0, ps.armR.z)), new THREE.Vector3(1, 1, 1));
  const fore = new THREE.Matrix4().compose(new THREE.Vector3(0, -D.upper, 0), new THREE.Quaternion().setFromEuler(new THREE.Euler(ps.armR.bend, 0, 0)), new THREE.Vector3(1, 1, 1));
  const handLocal = new THREE.Vector3(0, -D.fore - D.hand * 1.1, 0).applyMatrix4(fore).applyMatrix4(arm);
  const hand = pelvis.clone().add(handLocal.multiplyScalar(scale).applyQuaternion(q));
  const qArm = new THREE.Quaternion().setFromEuler(new THREE.Euler(ps.armR.x, 0, ps.armR.z))
    .multiply(new THREE.Quaternion().setFromEuler(new THREE.Euler(ps.armR.bend, 0, 0)))
    .multiply(new THREE.Quaternion().setFromEuler(new THREE.Euler(PHONE_TILT, 0, 0)));
  const screen = new THREE.Vector3(0, 0, 1).applyQuaternion(q.clone().multiply(qArm));
  const phone = hand.clone().add(new THREE.Vector3(...PHONE_AT).applyQuaternion(q.clone().multiply(qArm)));
  const hold = a.hold && a.hold !== 'none' ? a.hold : AUTO_HOLD[action] ?? (action === 'type' && !['desk', 'chair'].includes(a.spot) ? 'laptop' : 'none');
  return {actor: {...a, action}, design, pose: ps, root, ry, head, hand: hold === 'phone' ? phone : hand, screen, faceDir, headUp, body, hold, seed: (shot.seed ?? 1) * 31 + k * 7 + (a.who === 'hero' ? 0 : 101)};
};

// ---------------------------------------------------------------- people in and on vehicles
// The user's film 'Born to Fly' had a driver nobody ever saw drive: the editor had no way to put a man in a car. Now
// an actor `on` a vehicle sits in its seats (the driver's first) or stands on it (a roof, a wing), is drawn in its own
// frame (so he goes with it through a drift, a jump, a bank), and can leap off it at his moment.

// A vehicle someone is in or on, or one under way on its own, at this moment: its state, its frame in the world, and
// its state at any other moment (for a leap off it and for the cameras that follow it).
export type Ride = {b: Big; k: number; st: BigState; m: THREE.Matrix4; at: (tt: number) => BigState; under: boolean};

// Two vehicles never overlap (the user, of two cars at a race's start drawn inside each other: "make some runtime
// rules to analyse what needs to be done", not hand-placed): each vehicle someone is in or that is under way is
// placed in turn, and if at any of `RIDE_MOMENTS` moments of the shot it would touch one already placed it moves a
// lane over (its own width + `RIDE_GAP`, either side, then further) or a car length ahead or behind, the first place
// that touches nobody (else the one that touches least). Worked out once per shot.
const RIDE_MOMENTS = 9;
const RIDE_GAP = 1.0;
const vehicleOutline = (b: Big, st: BigState) => {
  const [w, h, l] = sizeOf(b);
  const m = vehicleMatrix(st);
  return [[-1, -1], [-1, 1], [1, -1], [1, 1], [0, 1], [0, -1], [1, 0], [-1, 0], [0, 0]].map(([sx, sz]) => new THREE.Vector3((sx * w) / 2, h / 2, (sz * l) / 2).applyMatrix4(m));
};
export const vehiclesTouch = (b1: Big, s1: BigState, b2: Big, s2: BigState) =>
  vehicleOutline(b1, s1).some((pt) => insideBig(b2, s2, pt, 0.3)) || vehicleOutline(b2, s2).some((pt) => insideBig(b1, s1, pt, 0.3));
type RideEntry = {b: Big; k: number; under: boolean; o: number; road?: RoadPlace};
const rideEntries = (shot: LPShot, set: SetDef): (RideEntry | undefined)[] => {
  const alone = !shot.actors.length; // a shot of only a vehicle: it travels, and the camera goes with it
  const pusher = shot.actors.some((a) => a.action === 'push-stop');
  let order = 0;
  return (shot.big ?? []).map((b0, k) => {
    const b = scaledBig(b0, shot);
    if (!isVehicle(b)) return undefined;
    const ridden = shot.actors.some((a) => a.on === k);
    const under = underway(b, ridden || alone) && !(b.motion === 'stop' && pusher);
    if (!under && !ridden) return undefined;
    const o = under ? order++ : 0;
    // standing with someone in it: on the road where the set has one
    const road: RoadPlace | undefined = !under && set.road !== undefined && set.walk === 'x' && !(b.motion === 'stop' && pusher) ? {lane: set.road, shift: 0} : undefined;
    return {b, k, under, o, road};
  });
};
const rideAt = (e: RideEntry, set: SetDef, tt: number, da: number, n: Nudge, people: Holder[] = [], trail = false): BigState => {
  if (e.under) return ridePath(e.b, set, tt, da, e.k, e.o, trail, n);
  if (!n.lat && !n.along) return bigState(e.b, set, people, tt, da, e.k, e.road);
  const sp = spotOf(set, e.b.spot);
  const base = e.road ?? {lane: set.walk === 'x' ? sp.z : sp.x, shift: 0};
  return bigState(e.b, set, people, tt, da, e.k, {lane: base.lane + n.lat, shift: base.shift + n.along});
};
const NUDGES = new WeakMap<LPShot, Nudge[]>();
export const rideNudges = (shot: LPShot, set: SetDef): Nudge[] => {
  const hit = NUDGES.get(shot);
  if (hit) return hit;
  const entries = rideEntries(shot, set);
  const da = actionTime(shot, shot.duration);
  const moments = Array.from({length: RIDE_MOMENTS}, (_, i) => (da * i) / (RIDE_MOMENTS - 1));
  const out: Nudge[] = entries.map(() => ({lat: 0, along: 0}));
  const placed: {e: RideEntry; n: Nudge}[] = [];
  for (const e of entries) {
    if (!e) continue;
    const [w, , l] = sizeOf(e.b);
    const across = w + RIDE_GAP;
    const tries: Nudge[] = [];
    for (const a of [0, 1, -1]) for (const s of [0, 1, -1, 2, -2, 3, -3]) tries.push({lat: s * across, along: a * (l + 2)});
    let best: {n: Nudge; hits: number} | undefined;
    for (const n of tries) {
      const hits = moments.filter((t) => {
        const st = rideAt(e, set, t, da, n);
        return placed.some((p) => vehiclesTouch(e.b, st, p.e.b, rideAt(p.e, set, t, da, p.n)));
      }).length;
      if (!best || hits < best.hits) best = {n, hits};
      if (!hits) break;
    }
    out[e.k] = best!.n;
    placed.push({e, n: best!.n});
  }
  NUDGES.set(shot, out);
  return out;
};

export const rideStates = (shot: LPShot, set: SetDef, tReal: number, people: Holder[] = []): (Ride | undefined)[] => {
  const da = actionTime(shot, shot.duration);
  const ta = actionTime(shot, tReal);
  const nudges = rideNudges(shot, set);
  return rideEntries(shot, set).map((e) => {
    if (!e) return undefined;
    const n = nudges[e.k];
    const at = (tt: number, trail = false) => rideAt(e, set, tt, da, n, people, trail);
    const st = at(ta, true);
    return {b: e.b, k: e.k, st, m: vehicleMatrix(st), at, under: e.under};
  });
};

// Which seat or standing place each person on a vehicle takes: the driver the first seat, passengers the next ones,
// everyone else a place to stand (in the order they are listed).
type Slot = {seat?: number; stand?: number};
const rideSlots = (shot: LPShot): (Slot | undefined)[] => {
  const used = new Map<number, {seats: Set<number>; stands: number}>();
  return shot.actors.map((a) => {
    if (a.on === undefined) return undefined;
    const u = used.get(a.on) ?? {seats: new Set<number>(), stands: 0};
    used.set(a.on, u);
    if (a.action === 'drive' || a.action === 'ride') {
      let s = a.action === 'drive' ? 0 : 1;
      while (u.seats.has(s)) s++;
      u.seats.add(s);
      return {seat: s};
    }
    return {stand: u.stands++};
  });
};
const slotPlace = (b: Big, slot: Slot): {root: V3; seat: number | null} => {
  const seats = seatsOf(b);
  if (slot.seat !== undefined && slot.seat < seats.length) {
    const s = seats[slot.seat];
    return {root: [s[0], 0, s[2]], seat: s[1]};
  }
  const stands = standsOf(b);
  const s = stands[(slot.stand ?? slot.seat ?? 0) % stands.length];
  return {root: [s[0], s[1], s[2]], seat: null};
};

// A placement worked out in a vehicle's frame, carried into the world (the Man is still drawn in that frame).
const toWorld = (pl: Placed, m: THREE.Matrix4, k: number): Placed => {
  const pos = new THREE.Vector3();
  const quat = new THREE.Quaternion();
  m.decompose(pos, quat, new THREE.Vector3());
  const P = (v: THREE.Vector3) => v.clone().applyMatrix4(m);
  const R = (v: THREE.Vector3) => v.clone().applyQuaternion(quat);
  const fwd = R(new THREE.Vector3(Math.sin(pl.ry), 0, Math.cos(pl.ry)));
  return {
    ...pl,
    root: V(pl.root).applyMatrix4(m).toArray() as V3,
    ry: Math.atan2(fwd.x, fwd.z),
    head: P(pl.head),
    hand: P(pl.hand),
    body: P(pl.body),
    screen: R(pl.screen),
    faceDir: R(pl.faceDir),
    headUp: R(pl.headUp),
    local: {root: pl.root, ry: pl.ry, pos, quat},
    ride: k,
  };
};

const ON_TOP_MOVING = new Set<Action>(['walk', 'run', 'jog', 'dash', 'flee', 'carry']);

// Someone in or on a vehicle at time t: in his seat or on his standing place, facing its front (or the way he is
// told, or the person on it he looks at); after a 'jump-off' at his moment, through the air from where he stood with
// the vehicle's speed and his own leap: in the sky falling free, else down beside it into a one-knee landing.
const placeOn = (a: Actor, k: number, set: SetDef, shot: LPShot, tReal: number, cast: Record<string, Design>, ride: Ride, slot: Slot, mate?: V3): Placed => {
  const t = actionTime(shot, tReal);
  const dur = actionTime(shot, shot.duration);
  const {root, seat} = slotPlace(ride.b, slot);
  // seated in a car he is drawn smaller, inside it under its roof (RIDER_SCALE)
  const base = cast[a.who] ?? HERO;
  const shrink = seat !== null ? RIDER_SCALE[ride.b.kind] ?? 1 : 1;
  const design = shrink === 1 ? base : {...base, height: (base.height ?? 1) * shrink};
  const sc = design.height ?? 1;
  let action: Action = a.action;
  if (ON_TOP_MOVING.has(action)) action = ride.under ? 'brace' : 'stand';
  if (seat === null && (action === 'drive' || action === 'ride')) action = 'brace'; // more people than seats
  const kk = k * 1.7 + (shot.seed ?? 0);
  const ev = actorAt(a, shot) ?? dur * 0.45;
  if (action === 'jump-off' && t > ev) {
    const m0 = vehicleMatrix(ride.at(ev));
    const p0 = V(root).applyMatrix4(m0);
    const v = V(root).applyMatrix4(vehicleMatrix(ride.at(ev + 0.05))).sub(p0).multiplyScalar(20);
    const q0 = new THREE.Quaternion();
    m0.decompose(new THREE.Vector3(), q0, new THREE.Vector3());
    const fwd = new THREE.Vector3(0, 0, 1).applyQuaternion(q0).setY(0).normalize();
    const side = new THREE.Vector3(fwd.z, 0, -fwd.x).multiplyScalar(a.facing === 'left' ? 1 : -1); // off to his right unless told left
    v.addScaledVector(side, 3.2).add(new THREE.Vector3(0, 3.6, 0));
    const tt = t - ev;
    const free = !!set.sky || !!ride.st.air || p0.y > 4;
    let pos: THREE.Vector3;
    let air: 'leap' | 'fall' | undefined = 'leap';
    let landed = 0;
    if (free) {
      // drag: his speed along falls away (the vehicle goes on without him), his fall reaches about 9 m/s
      const tau = 1.1;
      const vt = 9;
      pos = p0.clone().addScaledVector(v.clone().setY(0), tau * (1 - Math.exp(-tt / tau)));
      pos.y = p0.y + v.y * 0.5 * (1 - Math.exp(-tt / 0.5)) - ((vt * vt) / GRAVITY) * Math.log(Math.cosh((GRAVITY * tt) / vt));
      if (tt > 0.35) air = 'fall';
    } else {
      const T = (v.y + Math.sqrt(v.y * v.y + 2 * GRAVITY * Math.max(0, p0.y))) / GRAVITY;
      const flat = v.clone().setY(0);
      pos = p0.clone().addScaledVector(flat, Math.min(tt, T));
      if (tt < T) pos.y = p0.y + v.y * tt - 0.5 * GRAVITY * tt * tt;
      else {
        pos.addScaledVector(flat, 0.12 * (1 - Math.exp(-(tt - T) * 6))); // a skid as he lands
        pos.y = 0;
        air = undefined;
        landed = tt - T;
      }
    }
    const ps = air ? pose({action, t, dur, seat: null, k: kk, at: ev, air}) : pose({action: 'land', t: landed, dur, seat: null, k: kk, at: 0});
    return kin(a, air ? action : 'land', k, shot, design, ps, pos.toArray() as V3, Math.atan2(fwd.x, fwd.z));
  }
  let ry = 0;
  if (seat === null) {
    const turn = FACING[a.facing ?? 'camera'];
    if (turn !== undefined) ry = turn;
    if (mate) ry = Math.atan2(mate[0] - root[0], mate[2] - root[2]); // two on a wing face each other
  }
  // (the pose's seat is in his own units: his hips land just above the seat's top whatever his size)
  const pd = action === 'drive' ? pressAt(shot, tReal, ride.k) : {gas: 0, brake: 0};
  const pin = {action, t, dur, seat: seat === null ? null : seat / sc, k: kk, at: ev, steer: ride.st.steer ?? 0};
  const ps = pose({...pin, press: Math.max(pd.gas, pd.brake), pedal: pd.brake > 0 ? 'brake' : 'gas'});
  // a driver's pedals go where his foot rests (the user: "they press but where is its leg? why leg not touching the
  // pedal"): the accelerator under the foot at rest, the brake where the foot moves across to
  const pedalAt = action === 'drive' ? {gas: footOf(design, pose({...pin, press: 0}), root, ry), brake: footOf(design, pose({...pin, press: 1 / 3, pedal: 'brake'}), root, ry)} : undefined;
  return {...toWorld(kin(a, action, k, shot, design, ps, root, ry), ride.m, ride.k), inside: shrink < 1, pedalAt};
};

// ---------------------------------------------------------------- the cameras

export type CamPlan = {pos: THREE.Vector3; look: THREE.Vector3; up: THREE.Vector3; fov: number; focus: number; aperture: number; near?: number};

const distFor = (w: number, h: number, fov: number, aspect: number) => {
  const tan = Math.tan(((fov / 2) * Math.PI) / 180);
  return Math.max(h / 2 / tan, w / 2 / tan / aspect);
};

// The camera moved back along its line of sight (never closer) until every point is inside the frame with a margin:
// 86% of the half-width and 84% of the half-height.
const fitAll = (pos: THREE.Vector3, look: THREE.Vector3, pts: THREE.Vector3[], fov: number, aspect: number) => {
  const back = pos.clone().sub(look);
  const d0 = back.length();
  if (d0 < 1e-3) return pos;
  const fw = back.clone().negate().normalize();
  const rt = new THREE.Vector3().crossVectors(fw, new THREE.Vector3(0, 1, 0));
  if (rt.lengthSq() < 1e-6) rt.set(1, 0, 0);
  rt.normalize();
  const upv = new THREE.Vector3().crossVectors(rt, fw);
  const ty = Math.tan(((fov / 2) * Math.PI) / 180) * 0.84;
  const tx = Math.tan(((fov / 2) * Math.PI) / 180) * aspect * 0.86;
  // a point at offset r from the look point, seen from distance d along fw: fits when |r.rt| <= tx (d - r.fw), etc.
  let need = d0;
  for (const p of pts) {
    const r = p.clone().sub(look);
    const z = r.dot(fw);
    need = Math.max(need, Math.abs(r.dot(rt)) / tx + z, Math.abs(r.dot(upv)) / ty + z);
  }
  return look.clone().addScaledVector(back.normalize(), Math.min(need, d0 * 4));
};

const ease = (p: number) => (p <= 0 ? 0 : p >= 1 ? 1 : p * p * (3 - 2 * p));

// A horizontal direction in front of the face, nudged toward the open side of a room (+z) so walls stay behind.
const frontOf = (f: THREE.Vector3, outdoor: boolean) => {
  const d = new THREE.Vector3(f.x, 0, f.z);
  if (d.lengthSq() < 0.01) d.set(0, 0, 1);
  d.normalize();
  if (!outdoor && d.z < 0.5) d.add(new THREE.Vector3(0, 0, d.z < -0.3 ? 1.6 : 1.1)).normalize();
  return d;
};

// A two-shot of him and the one he looks at (the son pointing at his dad on the chair): square to the line between
// them, so both are the same size and who looks at whom reads at once, from the side where the other one's face shows
// (and indoors from the open side of the room), far enough back for both whole, seated or standing.
const twoShot = (who: Placed, all: Placed[], set: SetDef, aspect: number, push: number) => {
  const H = who.head;
  const A = who.aim ?? H;
  const other = all.find((p) => p !== who && p.head.distanceToSquared(A) < 1e-6);
  const line = A.clone().sub(H).setY(0);
  const spread = line.length();
  if (line.lengthSq() < 1e-4) line.set(1, 0, 0);
  line.normalize();
  const side = new THREE.Vector3(-line.z, 0, line.x);
  const flat = (v: THREE.Vector3) => new THREE.Vector3(v.x, 0, v.z).normalize();
  const score = (s: THREE.Vector3) =>
    (other ? s.dot(flat(other.faceDir)) : 0) * 0.6 + s.dot(flat(who.faceDir)) * 0.4 + s.z * (set.outdoor ? 0.2 : 1.2);
  if (score(side.clone().negate()) > score(side)) side.negate();
  const low = Math.min(H.y, A.y);
  const look = H.clone().lerp(A, 0.5).setY((Math.max(H.y, A.y) + 0.75 + low - 1.05) / 2);
  const d = distFor(1.5 + spread, 2.65 + Math.abs(H.y - A.y), 32, aspect) * push;
  // indoors square to them too (nudged toward the room's open side only when that side faces a back wall): nudged
  // always, the one nearer the open side came out twice the size of the other
  const dir = set.outdoor || side.z > -0.2 ? side : frontOf(side, false);
  const pos = look.clone().addScaledVector(dir, d).add(new THREE.Vector3(0, 0.25, 0));
  let fov = 32;
  if (!set.outdoor) {
    // inside the room; a camera the walls pull in widens its lens to keep both whole
    const want = pos.distanceTo(look);
    pos.x = Math.max(-3.1, Math.min(3.1, pos.x));
    pos.z = Math.max(-2.5, pos.z);
    const got = Math.max(0.5, pos.distanceTo(look));
    if (got < want - 0.01) fov = Math.min(70, (2 * Math.atan(Math.tan((16 * Math.PI) / 180) * (want / got)) * 180) / Math.PI);
  }
  return {pos, look, fov};
};

export const camFor = (cam: Cam, who: Placed, all: Placed[], set: SetDef, aspect: number, t: number, dur: number, seed: number): CamPlan => {
  const p = ease(t / Math.max(0.5, dur));
  const push = 1.05 - 0.08 * p; // a slow push in over the shot
  const sway = 0.012 * Math.sin(t * 0.7 + seed) + 0.006 * Math.sin(t * 1.9 + seed * 2);
  const lying = Math.abs(who.pose.rx) > 1.2 || Math.abs(who.pose.rz) > 1.2;
  const up = new THREE.Vector3(0, 1, 0);
  let fov = 34;
  let pos: THREE.Vector3;
  let look: THREE.Vector3;
  let camUp = up.clone();
  let aperture = 0.0;
  const H = who.head.clone();
  // falling free (a skydive, a leap from a plane): the camera falls with him like a skydiving cameraman
  // (and the whole shot of someone who leaps off a vehicle, before and after the leap, so the camera never jumps)
  const leaping = who.actor.action === 'jump-off';
  if ((leaping || (lying && who.pose.rx > 1.2 && (set.sky || who.root[1] > 1.5) && who.ride === undefined)) && !['face', 'face-top', 'medium', 'crash-zoom'].includes(cam)) {
    const fwd = new THREE.Vector3(Math.sin(who.ry), 0, Math.cos(who.ry));
    const right = new THREE.Vector3(fwd.z, 0, -fwd.x);
    const B = who.body.clone();
    const buffet = new THREE.Vector3(Math.sin(t * 7.1 + seed), Math.sin(t * 5.3 + seed * 2), Math.sin(t * 6.2 + seed * 3)).multiplyScalar(0.04);
    let fpos: THREE.Vector3;
    let flook = B.clone();
    if (cam === 'side' || cam === 'tracking') {
      fpos = B.clone().addScaledVector(right, 3.4).add(new THREE.Vector3(0, 0.5, 0));
    } else if (cam === 'front' || cam === 'lead' || cam === 'low' || cam === 'cockpit') {
      fpos = H.clone().addScaledVector(fwd, 2.6).add(new THREE.Vector3(0, -0.7, 0));
    } else if (cam === 'orbit') {
      const th = Math.atan2(fwd.x, fwd.z) + 1.2 - t * 0.6;
      fpos = B.clone().add(new THREE.Vector3(Math.sin(th) * 3.2, 1.0, Math.cos(th) * 3.2));
    } else {
      // above and behind him: his back, his spread arms, the clouds far below
      fpos = B.clone().addScaledVector(fwd, -2.4).addScaledVector(right, 0.6).add(new THREE.Vector3(0, 2.7, 0));
      flook = B.clone().addScaledVector(fwd, 1.2).add(new THREE.Vector3(0, -1.6, 0));
    }
    fpos.add(buffet);
    return {pos: fpos, look: flook, up: up.clone(), fov: aspect < 1 ? 62 : 48, focus: fpos.distanceTo(B), aperture: 0.2, near: 0.05};
  }
  // seated inside a closed car: close shots look in through the windscreen (from the side the doors and pillars fill
  // the picture), framing him alone ('face') or everyone in the car ('medium')
  if (who.inside && who.local && (cam === 'face' || cam === 'medium' || cam === 'crash-zoom')) {
    const fwd = new THREE.Vector3(0, 0, 1).applyQuaternion(who.local.quat);
    const flat = fwd.clone().setY(0).normalize();
    const mates = cam === 'medium' ? all.filter((p) => p.ride === who.ride && p.inside) : [who];
    const mid = mates.reduce((sum, p) => sum.add(p.head), new THREE.Vector3()).multiplyScalar(1 / mates.length);
    const spread = Math.max(...mates.map((p) => p.head.distanceTo(mid))) * 2;
    const ifov = aspect < 1 ? 50 : 36;
    const q = cam === 'crash-zoom' ? ease((t - 0.12) / 0.3) : 0;
    const d = distFor((cam === 'face' ? 0.75 : 1.1) + spread, 0.8, ifov, aspect) * (cam === 'crash-zoom' ? 2.2 - 1.2 * q : push);
    const ipos = mid.clone().addScaledVector(flat, Math.max(1.25, d)).add(new THREE.Vector3(0, 0.12, 0));
    const ilook = mid.clone().add(new THREE.Vector3(0, -0.06, 0));
    const toward = ilook.clone().sub(ipos);
    const side = new THREE.Vector3().crossVectors(toward, up).normalize();
    ilook.addScaledVector(side, sway * toward.length());
    return {pos: ipos, look: ilook, up: up.clone(), fov: ifov, focus: ipos.distanceTo(mid), aperture: 0.35, near: 0.05};
  }
  const kind = cam === 'face' && lying ? 'face-top' : cam === 'aerial' && !set.outdoor ? 'wide' : cam;
  switch (kind) {
    case 'face': {
      fov = 30;
      const d = distFor(1.05, 0.95, fov, aspect) * push;
      const dir = frontOf(who.faceDir, set.outdoor);
      look = H.clone().add(new THREE.Vector3(0, -0.03, 0));
      pos = look.clone().addScaledVector(dir, d).add(new THREE.Vector3(0, -0.06, 0));
      aperture = 0.9;
      break;
    }
    case 'face-top': {
      fov = 30;
      const d = distFor(1.1, 1.0, fov, aspect) * push;
      const out = lying ? who.faceDir.clone() : frontOf(who.faceDir, set.outdoor).add(new THREE.Vector3(0, 1.1, 0)).normalize();
      look = H.clone();
      pos = look.clone().addScaledVector(out, d);
      camUp = lying ? who.headUp.clone() : up.clone();
      aperture = 0.9;
      break;
    }
    case 'top': {
      fov = 36;
      const along = who.head.clone().sub(who.body).setY(0);
      const lenAxis = along.lengthSq() > 0.01 ? along.normalize() : new THREE.Vector3(0, 0, -1);
      look = who.body.clone().lerp(who.head, 0.15);
      const d = distFor(1.6, 2.6, fov, aspect) * push;
      pos = look.clone().add(new THREE.Vector3(0, d, 0)).addScaledVector(lenAxis, -0.05);
      camUp = lenAxis;
      aperture = 0.35;
      break;
    }
    case 'medium': {
      fov = 32;
      if (who.aim) {
        const two = twoShot(who, all, set, aspect, push);
        pos = two.pos;
        look = two.look;
        fov = two.fov;
        aperture = 0.3;
        break;
      }
      const pts = all.length > 1 ? all.map((a) => a.head) : [H];
      const mid = pts.reduce((s, v) => s.add(v), new THREE.Vector3()).multiplyScalar(1 / pts.length);
      const spread = all.length > 1 ? Math.max(...pts.map((v) => v.distanceTo(mid))) * 2 : 0;
      look = mid.clone().add(new THREE.Vector3(0, -0.32, 0));
      const d = distFor(1.6 + spread, 1.5, fov, aspect) * push;
      const dir = frontOf(all.length > 1 ? new THREE.Vector3(0, 0, 1) : who.faceDir, set.outdoor);
      pos = look.clone().addScaledVector(dir, d).add(new THREE.Vector3(0, 0.12, 0));
      aperture = 0.6;
      break;
    }
    case 'side': {
      fov = 38;
      look = who.body.clone().add(new THREE.Vector3(0, 0.25, 0));
      const fwd = new THREE.Vector3(Math.sin(who.ry), 0, Math.cos(who.ry));
      let side = new THREE.Vector3(fwd.z, 0, -fwd.x);
      if (side.z < 0) side.negate();
      const gap = who.aim ? who.aim.clone().sub(who.head).setY(0).length() : 0; // the one he looks at in the frame too
      if (who.aim) look.lerp(who.aim.clone().add(new THREE.Vector3(0, -0.5, 0)), 0.5);
      const d = distFor(1.8 + gap, 3.0, fov, aspect) * push;
      pos = look.clone().addScaledVector(side, d).add(new THREE.Vector3(0, 0.15, 0)).addScaledVector(fwd, 0.25);
      aperture = 0.5;
      break;
    }
    case 'front': {
      fov = 38;
      const fwd = new THREE.Vector3(Math.sin(who.ry), 0, Math.cos(who.ry));
      look = who.body.clone().add(new THREE.Vector3(0, 0.35, 0));
      const d = distFor(1.8, 3.0, fov, aspect) * push;
      pos = look.clone().addScaledVector(fwd, d).add(new THREE.Vector3(0, -0.05, 0));
      aperture = 0.55;
      break;
    }
    case 'back': {
      fov = 36;
      // over his shoulder at what he faces, or at the one he looks at (seated, his body may point elsewhere)
      const toAim = who.aim ? who.aim.clone().sub(H).setY(0) : undefined;
      const fwd = toAim && toAim.lengthSq() > 0.04 ? toAim.clone().normalize() : new THREE.Vector3(Math.sin(who.ry), 0, Math.cos(who.ry));
      const right = new THREE.Vector3(fwd.z, 0, -fwd.x);
      // high over the shoulder, so a chair or a table behind him stays under the shot
      pos = H.clone().addScaledVector(fwd, -2.3 * push).addScaledVector(right, 0.75).add(new THREE.Vector3(0, 0.65, 0));
      if (who.ride !== undefined && !who.aim) {
        // at the wheel: his point of view over his shoulder, the road (or the sky) far ahead, his head low in the frame
        // (in a closed car from the back of the cabin, under its roof)
        // (inside a car from behind his seat toward the car's middle, so his head sits at the side of the picture)
        const inward = who.local ? new THREE.Vector3(who.local.root[0] < 0 ? 1 : -1, 0, 0).applyQuaternion(who.local.quat).setY(0).normalize() : right;
        pos = who.inside
          ? H.clone().addScaledVector(fwd, -0.6).addScaledVector(inward, 0.42).add(new THREE.Vector3(0, 0.1, 0))
          : H.clone().addScaledVector(fwd, -1.5).addScaledVector(right, 0.55).add(new THREE.Vector3(0, 0.55, 0));
        look = H.clone().addScaledVector(fwd, 14).add(new THREE.Vector3(0, -0.6, 0));
        fov = who.inside ? (aspect < 1 ? 70 : 60) : aspect < 1 ? 58 : 44;
        aperture = 0.15;
        break;
      }
      look = who.aim
        ? who.aim.clone().add(new THREE.Vector3(0, -0.45, 0)).lerp(H, 0.3)
        : H.clone().addScaledVector(fwd, 2.0).add(new THREE.Vector3(0, -0.75, 0));
      aperture = 0.45;
      // his back to a wall (a chair against it): the room leaves no space behind him and the camera ended up in his
      // hair; a two-shot from the side instead
      if (who.aim && !set.outdoor && (pos.z < -2.6 || Math.abs(pos.x) > 3.2)) {
        const two = twoShot(who, all, set, aspect, push);
        pos = two.pos;
        look = two.look;
        fov = two.fov;
        aperture = 0.3;
      }
      break;
    }
    case 'low': {
      fov = 40;
      const dir = frontOf(who.faceDir, set.outdoor);
      const d = distFor(1.6, 2.8, fov, aspect) * push;
      pos = new THREE.Vector3(who.root[0], 0.28, who.root[2]).addScaledVector(dir, d * 0.8);
      look = H.clone().add(new THREE.Vector3(0, -0.25, 0));
      aperture = 0.4;
      break;
    }
    case 'detail': {
      fov = 30;
      const held = who.hold !== 'none';
      if (held && who.hold === 'phone') {
        // his point of view: close in front of the screen, between the phone and his eyes
        fov = 46;
        look = who.hand.clone();
        pos = look.clone().addScaledVector(who.screen, 0.44 * push).addScaledVector(who.headUp, 0.04);
        camUp = who.headUp.clone().addScaledVector(who.screen, -who.headUp.dot(who.screen)).normalize();
      } else if (held) {
        // in front of him and to the side of the hand
        look = who.hand.clone();
        const side = who.hand.clone().sub(who.body);
        side.addScaledVector(who.headUp, -side.dot(who.headUp)).addScaledVector(who.faceDir, -side.dot(who.faceDir));
        if (side.lengthSq() < 0.001) side.set(1, 0, 0);
        side.normalize();
        const out = who.faceDir.clone().multiplyScalar(0.8).addScaledVector(side, 0.6).addScaledVector(who.headUp, 0.3).normalize();
        const d = distFor(0.8, 0.75, fov, aspect) * push;
        pos = look.clone().addScaledVector(out, d);
        camUp = who.headUp.clone();
      } else {
        look = V(set.surface);
        const d = distFor(0.8, 0.7, fov, aspect) * push;
        pos = look.clone().addScaledVector(new THREE.Vector3(0.3, 0.6, 1).normalize(), d);
      }
      aperture = 1.2;
      break;
    }
    case 'aerial': {
      // high above, looking down on him and the place, circling slowly
      fov = aspect < 1 ? 44 : 38;
      look = who.body.clone();
      const th = seed * 1.3 + t * 0.12;
      const r = aspect < 1 ? 6 : 7.5;
      pos = look.clone().add(new THREE.Vector3(Math.cos(th) * r, 9.5 - 0.8 * p, Math.sin(th) * r));
      aperture = 0.08;
      break;
    }
    case 'orbit': {
      // circling round him at his height
      fov = 36;
      look = H.clone().add(new THREE.Vector3(0, -0.4, 0));
      const d = distFor(1.9, 2.5, fov, aspect);
      const f0 = frontOf(who.faceDir, set.outdoor);
      const th0 = Math.atan2(f0.x, f0.z);
      const th = set.outdoor ? th0 + 0.6 - t * 0.42 : th0 + 0.75 * Math.sin(t * 0.4 + 0.6);
      pos = look.clone().add(new THREE.Vector3(Math.sin(th) * d, 0.2, Math.cos(th) * d));
      aperture = 0.55;
      break;
    }
    case 'crash-zoom': {
      // from the room to his face in a third of a second, then held
      const q = ease((t - 0.12) / 0.3);
      fov = 34 - 4 * q;
      const dir = frontOf(who.faceDir, set.outdoor);
      const far = distFor(3.4, 4.6, 34, aspect);
      const near = distFor(1.05, 0.95, 30, aspect);
      look = who.body.clone().add(new THREE.Vector3(0, 0.3, 0)).lerp(H.clone().add(new THREE.Vector3(0, -0.03, 0)), q);
      pos = look.clone().addScaledVector(dir, far + (near - far) * q).add(new THREE.Vector3(0, 0.15 * (1 - q) - 0.05, 0));
      const jolt = t > 0.42 ? 0.04 * Math.exp(-(t - 0.42) * 7) * Math.sin(t * 60) : 0;
      pos.y += jolt;
      aperture = 0.25 + 0.65 * q;
      break;
    }
    case 'wide':
    default: {
      fov = aspect < 1 ? 46 : 38;
      pos = V(set.wide.pos);
      // toward the subject and everyone else in the shot (in a tall frame a second person fell outside it)
      const others = all.filter((p) => p !== who).map((p) => p.body);
      const group = others.length ? others.reduce((sum, v) => sum.add(v), who.body.clone().multiplyScalar(2)).multiplyScalar(1 / (others.length + 2)) : who.body;
      look = V(set.wide.look).lerp(who.aim ? who.body.clone().lerp(who.aim, 0.5) : group, others.length ? 0.6 : 0.45);
      if (who.aim) {
        // the room's own view, moved sideways when one of the two would stand in front of the other (the son who
        // walked up to his dad on the couch hid him)
        const right = new THREE.Vector3().crossVectors(look.clone().sub(pos), up).normalize();
        const apart = (at: THREE.Vector3) => {
          const a = who.head.clone().sub(at).normalize();
          const b = who.aim!.clone().sub(at).normalize();
          return a.angleTo(b) * Math.min(at.distanceTo(who.head), at.distanceTo(who.aim!));
        };
        let best = pos.clone();
        for (const s of [0.7, -0.7, 1.4, -1.4, 2.1, -2.1]) {
          if (apart(best) >= 0.85) break;
          const p2 = pos.clone().addScaledVector(right, s);
          if (!set.outdoor) p2.x = Math.max(-3.1, Math.min(3.1, p2.x));
          if (apart(p2) > apart(best) + 0.05) best = p2;
        }
        pos = best;
      }
      // outdoors someone can stand right by the room's camera (a man stopping a bus on the road was 3.5 m from it and
      // only his shoulder was in the picture): it steps back along its own line
      const gap = pos.distanceTo(who.body);
      if (set.outdoor && gap < WIDE_NEAR) pos = who.body.clone().add(pos.clone().sub(who.body).multiplyScalar(WIDE_NEAR / Math.max(0.3, gap)));
      pos.lerp(look, 0.06 * p);
      // everyone whole in the picture: the view turns toward them as far as it must, then the lens opens until the
      // widest person (side to side, head to feet) fits
      const need = (lk: THREE.Vector3) => {
        const fwd = lk.clone().sub(pos).normalize();
        const side = new THREE.Vector3().crossVectors(fwd, up).normalize();
        const upv = new THREE.Vector3().crossVectors(side, fwd).normalize();
        let needH = 0;
        let needV = 0;
        for (const pl of all) {
          for (const pt of [pl.head.clone().add(new THREE.Vector3(0, 0.45, 0)), new THREE.Vector3(pl.root[0], 0, pl.root[2])]) {
            const d = pt.clone().sub(pos);
            const depth = Math.max(0.5, d.dot(fwd));
            needH = Math.max(needH, (Math.abs(d.dot(side)) + 0.4) / depth);
            needV = Math.max(needV, (Math.abs(d.dot(upv)) + 0.15) / depth);
          }
        }
        return Math.max(needV, needH / aspect); // as tan of half the vertical angle
      };
      const have = Math.tan(((fov / 2) * Math.PI) / 180);
      const middle = all.reduce((sum, pl) => sum.add(pl.body), new THREE.Vector3()).multiplyScalar(1 / Math.max(1, all.length));
      const room = look.clone();
      for (let f = 0.2; f <= 1.001 && need(look) > have * 0.92; f += 0.2) look = room.clone().lerp(middle, f);
      const n = need(look);
      if (n > have) fov = Math.min(72, (2 * Math.atan(n) * 180) / Math.PI);
      aperture = 0.15;
      break;
    }
  }
  // indoors the camera stays inside the room (behind a wall it looked through the window frame and the counter)
  if (!set.outdoor && kind !== 'wide') {
    pos.x = Math.max(-3.2, Math.min(3.2, pos.x));
    pos.z = Math.max(-2.6, pos.z);
    pos.y = Math.max(0.25, Math.min(3.2, pos.y));
  }
  // a breath of handheld sway
  const toward = look.clone().sub(pos);
  const right = new THREE.Vector3().crossVectors(toward, camUp).normalize();
  look.addScaledVector(right, sway * toward.length()).addScaledVector(camUp, 0.5 * sway * toward.length());
  const focus = pos.distanceTo(kind === 'detail' || kind === 'top' ? look : H);
  // furniture right in front of the lens (a chair between the camera and him) is left out of the picture
  const near = kind === 'detail' ? 0.05 : Math.max(0.05, Math.min(1.5, focus * 0.45));
  return {pos, look, up: camUp, fov, focus, aperture, near};
};

// ---------------------------------------------------------------- cameras on vehicles: the car-chase and air-to-air shots
// The user: "this cars movement, angle movement must be hollywood style". A vehicle under way is filmed the way films
// do it: from a camera car behind it (chase), ahead of it looking back as it gains (lead), beside it at its speed
// (tracking), from the roadside as it whooshes past with a long lens panning (pass-by), from a helicopter (heli),
// straight down from a drone (drone), from the dashboard on the driver's face (cockpit), low at its front corner
// along its flank (bumper), circling it as it goes (orbit). They shake with its speed, punch in at its moment (the
// drift, the jump, the spin) and tilt a little when they are low and fast.
export const VEHICLE_CAMS = new Set<Cam>(['chase', 'lead', 'tracking', 'pass-by', 'heli', 'cockpit', 'bumper', 'drone', 'pedal', 'wheel', 'speedo']);
const INSIDE_CAMS = new Set<Cam>(['cockpit', 'pedal', 'wheel', 'speedo']);
const CUT_CAMS = new Set<Cam>(['pedal', 'wheel', 'speedo']); // the cut-ins
// a shot's cut-ins (older videos had one, `insert`)
export const insertsOf = (shot: LPShot): Insert[] => shot.inserts ?? (shot.insert ? [shot.insert] : []); // inside the car: they work parked too
// a person's camera on someone riding a vehicle under way, as the vehicle's own shot (face, medium, back, orbit and
// crash-zoom stay on him: they go with him)
const RIDER_CAM: Partial<Record<Cam, Cam>> = {wide: 'pass-by', side: 'tracking', front: 'lead', aerial: 'heli', low: 'bumper', detail: 'cockpit', top: 'drone'};
// a shot of only the vehicle: every camera is one of its own
const ALONE_CAM: Partial<Record<Cam, Cam>> = {
  ...RIDER_CAM,
  face: 'chase',
  medium: 'tracking',
  back: 'chase',
  'face-top': 'drone',
  'crash-zoom': 'lead',
  detail: 'bumper',
  cockpit: 'chase',
  pedal: 'bumper',
  wheel: 'chase',
  speedo: 'chase',
};
// a vehicle's camera with no vehicle to follow: the matching camera on the person
const ON_FOOT: Record<string, Cam> = {chase: 'back', lead: 'front', tracking: 'side', 'pass-by': 'wide', heli: 'aerial', cockpit: 'face', bumper: 'low', drone: 'top', pedal: 'low', wheel: 'detail', speedo: 'detail'};
const MOMENT_MOTIONS = new Set(['drift', 'spin', 'jump', 'roll', 'stop', 'dive', 'climb', 'bank']);

// The camera a shot really uses, given who it is on: a vehicle's own cameras when its subject is in a moving vehicle
// (or the shot is only the vehicle), a person's otherwise.
export const camOf = (cam: Cam, who: Placed | undefined, ride: Ride | undefined): Cam => {
  if (ride && !who) return ALONE_CAM[cam] ?? (VEHICLE_CAMS.has(cam) || cam === 'orbit' ? cam : 'chase');
  if (ride && ride.under) return VEHICLE_CAMS.has(cam) ? cam : RIDER_CAM[cam] ?? cam;
  if (ride) return VEHICLE_CAMS.has(cam) ? (INSIDE_CAMS.has(cam) ? cam : ON_FOOT[cam]) : cam;
  return VEHICLE_CAMS.has(cam) ? ON_FOOT[cam] : cam;
};

// The cut-ins of an action film's driving scene (the user: "pressing brake/acceleration by char legs for fraction of
// second just like action films and then move angle to car or road by what happened", "if sudden car movement like
// drifting first show car steering then actions"): down in the footwell on his foot as it hits the accelerator or the
// brake, or over the dashboard on his hands yanking the wheel. Placed in the car's own frame from his seat.
const insertPlan = (kind: 'pedal' | 'wheel' | 'speedo', r: Ride, who: Placed | undefined, aspect: number, t: number, seed: number): CamPlan => {
  const lr = who?.local?.root ?? ([-0.4, 0, -0.3] as V3);
  const at = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z).applyMatrix4(r.m);
  const q = new THREE.Quaternion();
  r.m.decompose(new THREE.Vector3(), q, new THREE.Vector3());
  const tall = aspect < 1;
  const pedal = kind === 'pedal';
  // the pedal: low by the door sill, looking forward and in across his shoe at the pedals (Big.tsx `Pedal`: x -0.5 and
  // -0.36, hinged at y 0.62, z 0.36), as the films do; in front of his feet the camera was inside the bonnet
  const pa = who?.pedalAt;
  const foot: V3 = pa ? [(pa.gas[0] + pa.brake[0]) / 2, (pa.gas[1] + pa.brake[1]) / 2, (pa.gas[2] + pa.brake[2]) / 2] : [-0.43, 0.44, 0.3];
  // from beside and behind the foot, by the door sill: his leg coming down, the shoe on the pedal, the wheel above
  // (the user picked this one: "this angle is ok")
  // the speedometer: square on the dial through the top of the wheel (Big.tsx `CLUSTER`), its needle climbing
  const speedo = kind === 'speedo';
  const dial = new THREE.Vector3(...CLUSTER.at).add(new THREE.Vector3(CLUSTER.speedo, 0, 0));
  const facing = new THREE.Vector3(0, Math.sin(CLUSTER.tilt), -Math.cos(CLUSTER.tilt));
  const pos = speedo ? at(...(dial.clone().addScaledVector(facing, 0.15).toArray() as V3)) : pedal ? at(foot[0] - 0.34, foot[1] + 0.2, foot[2] - 0.34) : at(lr[0] + 0.46, 0.98, lr[2] + 0.66);
  const look = speedo ? at(dial.x, dial.y, dial.z) : pedal ? at(foot[0] + 0.02, foot[1] + 0.02, foot[2] + 0.02) : at(lr[0], 0.8, lr[2] + 0.36);
  // the road through the car: a fine shake with its speed
  const jig = 0.004 * Math.min(1, (r.st.speed ?? 0) / 25);
  pos.add(new THREE.Vector3(Math.sin(t * 57 + seed), Math.sin(t * 49 + seed * 2), Math.sin(t * 61 + seed * 3)).multiplyScalar(jig));
  return {pos, look, up: new THREE.Vector3(0, 1, 0).applyQuaternion(q), fov: speedo ? (tall ? 48 : 40) : pedal ? (tall ? 66 : 54) : tall ? 60 : 50, focus: pos.distanceTo(look), aperture: 1.0, near: 0.02};
};

// How far the driver's foot is down on each pedal of car k: in the shot's cut-in to the pedal (the brake for a hard
// stop, else the accelerator), or through a whole 'pedal' shot.
export const pressAt = (shot: LPShot, t: number, k: number): Pedals => {
  const ins = insertsOf(shot).find((x) => x.cam === 'pedal' && x.on === k);
  let p = 0;
  let brake = false;
  if (ins) {
    p = ease((t - ins.from - 0.05) / 0.16);
    brake = ins.pedal === 'brake';
  } else if (shot.camera === 'pedal') {
    p = ease((t - 0.25) / 0.16);
    brake = shot.big?.[k]?.motion === 'stop';
  }
  return brake ? {gas: 0, brake: p} : {gas: p, brake: 0};
};

const rideCam = (cam: Cam, r: Ride, who: Placed | undefined, set: SetDef, shot: LPShot, aspect: number, t: number, seed: number): CamPlan => {
  if (CUT_CAMS.has(cam)) {
    if (who && who.inside) return insertPlan(cam as Insert['cam'], r, who, aspect, t, seed);
    return rideCam('chase', r, who, set, shot, aspect, t, seed);
  }
  const dur = shot.duration;
  const ta = actionTime(shot, t);
  const da = actionTime(shot, dur);
  const [w, h, l] = sizeOf(r.b);
  const st = r.st;
  const flying = !!st.air || !!set.sky;
  const yawOf = (s: BigState) => s.heading ?? s.ry;
  const fwdOf = (y: number) => new THREE.Vector3(Math.sin(y), 0, Math.cos(y));
  const f = fwdOf(yawOf(st));
  const c = st.pos.clone(); // its middle
  const up = new THREE.Vector3(0, 1, 0);
  // the open side of the place (where the set's own camera stands: the road's far side, away from the buildings)
  const sideOf = (fw: THREE.Vector3) => {
    const s = new THREE.Vector3(fw.z, 0, -fw.x);
    const toward = V(set.wide.pos).sub(c).setY(0);
    if (set.sky ? seed % 2 === 1 : toward.dot(s) < 0) s.negate();
    return s;
  };
  const open = sideOf(f);
  const tall = aspect < 1;
  const p = ease(t / Math.max(0.5, dur));
  let fov = tall ? 54 : 38;
  let pos: THREE.Vector3;
  let look: THREE.Vector3;
  let camUp = up.clone();
  let aperture = 0.2;
  let shake = 0.5; // how much its speed shakes this camera
  let roll = 0; // a dutch tilt
  const big = Math.max(w, l);
  switch (cam) {
    case 'lead': {
      // ahead of it, low, looking back: it comes on and gains on the camera
      const d0 = distFor(w * 1.7 + 1.2, h * 2.6 + 1, fov, aspect) + l * 0.5;
      const d = d0 * (1.35 - 0.5 * p);
      pos = c.clone().addScaledVector(f, d).addScaledVector(open, d0 * 0.12).add(new THREE.Vector3(0, h * 0.3 + 0.35, 0));
      look = c.clone().add(new THREE.Vector3(0, h * 0.12, 0));
      shake = 0.45;
      break;
    }
    case 'tracking': {
      // beside it at its speed, wheels spinning, the world streaming behind (a tall frame takes it from three-quarters
      // ahead, so its whole length fits)
      const dir = tall ? open.clone().multiplyScalar(0.78).addScaledVector(f, 0.62).normalize() : open.clone();
      const span = tall ? big * 0.8 + 1.4 : l + 1.6;
      const d = distFor(span, h * 2.6 + 0.8, fov, aspect) + w * 0.5;
      pos = c.clone().addScaledVector(dir, d).addScaledVector(f, l * 0.08).add(new THREE.Vector3(0, h * 0.2 + 0.25, 0));
      look = c.clone().addScaledVector(f, l * 0.06);
      shake = 0.6;
      roll = 0.03;
      break;
    }
    case 'pass-by': {
      // a fixed camera by the road where it passes at its moment, a long lens panning with it: small and far, then
      // filling the frame as it whooshes past, then gone
      const atM = r.b.at ?? da * 0.5;
      const m = r.at(atM);
      const fm = fwdOf(yawOf(m));
      const sm = sideOf(fm);
      pos = m.pos.clone().addScaledVector(sm, w / 2 + (flying ? 9 : 2.6)).addScaledVector(fm, l * 0.6 + (flying ? 6 : 2.2));
      pos.y = flying ? m.pos.y - 2.5 : 0.55;
      look = c.clone();
      const dist = Math.max(1, pos.distanceTo(c));
      const width = l * 1.25 + 1.6;
      fov = Math.max(14, Math.min(64, (2 * Math.atan(width / 2 / dist / Math.min(1, aspect)) * 180) / Math.PI));
      aperture = 0.08;
      shake = 0;
      break;
    }
    case 'heli': {
      // from a helicopter behind and to the side, high, looking down on it and the way ahead
      const d = distFor(big * 2.6 + 4, h * 3 + 4, 34, aspect) + l * 0.5;
      fov = 34;
      pos = c.clone().addScaledVector(f, -0.72 * d).addScaledVector(open, 0.55 * d).add(new THREE.Vector3(0, 0.62 * d, 0));
      look = c.clone().addScaledVector(f, Math.min(12, (st.speed ?? 0) * 0.35));
      aperture = 0.04;
      shake = 0.12;
      break;
    }
    case 'drone': {
      // straight down on it, its nose to the top of the frame
      const d = distFor(w * 2.6 + 2.5, l * 2.0 + 2.5, 40, aspect);
      fov = 40;
      pos = c.clone().add(new THREE.Vector3(0, d, 0)).addScaledVector(f, -0.01);
      look = c.clone();
      camUp = f.clone();
      aperture = 0.04;
      shake = 0.1;
      break;
    }
    case 'cockpit': {
      // on the dashboard, facing the driver: his face, the world rushing away behind him. Inside a closed car the
      // camera sits in the cabin over the middle of the dashboard, so his body, his hands on the wheel, the seats and
      // the gear lever are in the picture (through the windscreen only his head showed over the dashboard)
      if (who && who.inside && who.local) {
        fov = tall ? 70 : 60;
        const lr = who.local.root;
        pos = new THREE.Vector3(-lr[0] * (tall ? 0.3 : 0.15), tall ? 1.03 : 1.0, lr[2] + (tall ? 0.82 : 0.7)).applyMatrix4(r.m);
        look = who.head.clone().lerp(who.body, 0.35);
        aperture = 0.35;
        shake = 0.6;
        break;
      }
      if (who) {
        fov = tall ? 64 : 56;
        const fd = who.faceDir.clone().setY(0);
        const dir = (fd.lengthSq() > 0.01 ? fd : f.clone()).normalize();
        look = who.head.clone().add(new THREE.Vector3(0, -0.12, 0));
        pos = who.head.clone().addScaledVector(dir, 1.3).add(new THREE.Vector3(0, 0.08, 0)); // through the windscreen
        aperture = 0.5;
        shake = 0.8;
        break;
      }
      return rideCam('chase', r, who, set, shot, aspect, t, seed);
    }
    case 'bumper': {
      if (flying) {
        // past the wing tip and a little above, looking in along the wing at the cockpit
        fov = tall ? 60 : 50;
        pos = c.clone().addScaledVector(open, w / 2 + 1.6).addScaledVector(f, l * 0.12).add(new THREE.Vector3(0, h * 0.6, 0));
        look = c.clone().addScaledVector(f, l * 0.2).add(new THREE.Vector3(0, h * 0.2, 0));
      } else {
        // low at its front corner, looking back along its flank: the wheel, the road, the speed
        fov = tall ? 62 : 56;
        pos = c.clone().addScaledVector(f, l / 2 + 0.35).addScaledVector(open, w / 2 + 0.3).add(new THREE.Vector3(0, -h / 2 + 0.28, 0));
        look = c.clone().addScaledVector(f, -l * 0.35).add(new THREE.Vector3(0, h * 0.1, 0));
      }
      shake = 0.9;
      roll = 0.045;
      aperture = 0.3;
      break;
    }
    case 'orbit': {
      // circling it as it goes: the hero shot
      const d = distFor(big * 1.2 + 1, h * 2.5 + 1, 38, aspect);
      fov = 38;
      const th0 = Math.atan2(open.x, open.z);
      const th = th0 + 0.9 - t * 0.55;
      pos = c.clone().add(new THREE.Vector3(Math.sin(th) * d, h * 0.4 + 0.5, Math.cos(th) * d));
      look = c.clone();
      shake = 0.25;
      break;
    }
    case 'chase':
    default: {
      // from a camera car behind it and a little above: in a drift it stays on its line and the car slides across
      // the frame; under hard acceleration it pulls away
      const lag = r.at(Math.max(0, ta - 0.06));
      const fl = fwdOf(yawOf(lag));
      const d = distFor(w * 1.2 + 1.0, h * 2.2 + 0.8, fov, aspect) + l * 0.5;
      pos = lag.pos.clone().addScaledVector(fl, -d).addScaledVector(open, 0.25 * Math.sin(t * 0.5 + seed)).add(new THREE.Vector3(0, h * 0.55 + 0.55, 0));
      look = c.clone().addScaledVector(f, l * 0.35).add(new THREE.Vector3(0, h * 0.15, 0));
      shake = 0.5;
      break;
    }
  }
  // its moment (the drift, the jump, the spin, the roll): the lens punches in for a beat
  const atM = r.b.at;
  if (atM !== undefined && MOMENT_MOTIONS.has(r.b.motion)) fov *= 1 - 0.12 * Math.exp(-(((ta - atM) / 0.35) ** 2));
  // never under the ground
  if (!set.sky) pos.y = Math.max(0.22, pos.y);
  const toward = look.clone().sub(pos);
  const dist = toward.length();
  // the road through the lens: a fine shake that grows with its speed
  const fast = Math.min(1, (st.speed ?? 0) / 26);
  if (shake > 0 && fast > 0) {
    const a = 0.0045 * shake * fast * Math.max(1, dist);
    pos.add(new THREE.Vector3(Math.sin(t * 53.1 + seed), Math.sin(t * 61.7 + seed * 2) * 0.7, Math.sin(t * 47.3 + seed * 3)).multiplyScalar(a));
  }
  if (roll) {
    const axis = toward.clone().normalize();
    camUp.applyAxisAngle(axis, roll * (0.5 + 0.5 * fast) * (seed % 2 ? 1 : -1));
  }
  const focus = who && (cam === 'cockpit' || cam === 'tracking') ? pos.distanceTo(who.head) : pos.distanceTo(c);
  return {pos, look, up: camUp, fov, focus, aperture, near: cam === 'cockpit' || cam === 'bumper' ? 0.05 : Math.max(0.05, Math.min(1.2, focus * 0.25))};
};

// A shot with nobody in it, of an animal, a creature or a big thing (the user's dinosaur script: a T-Rex roaring, a
// Brachiosaurus between skyscrapers, an egg hatching in a cave): the camera is on that thing, the way the story asked.
export const bigCam = (cam: Cam, b: Big, st: BigState, set: SetDef, aspect: number, t: number, dur: number, seed: number): CamPlan => {
  const [w, h, l] = sizeOf(b);
  const f = new THREE.Vector3(Math.sin(st.ry), 0, Math.cos(st.ry));
  // the side the camera stands on: the open side of the place (+z, where every set's own camera is: the street's
  // buildings stood behind a camera put on the far side), else either by the shot's seed
  const sd0 = new THREE.Vector3(f.z, 0, -f.x);
  const sd = sd0.multiplyScalar(Math.abs(sd0.z) > 0.3 ? Math.sign(sd0.z) : seed % 2 ? 1 : -1);
  const c = st.pos.clone().setY(Math.max(0, st.pos.y) + h / 2);
  const head = headOf(b, st);
  const up = new THREE.Vector3(0, 1, 0);
  const fov = 40;
  // all of it, head included: the camera looks at the middle of its outline (a long neck puts the head far from the
  // body's centre) and steps back until every point is inside the frame
  const outline = outlineOf(b, st);
  const lo = outline.reduce((a, p) => a.min(p), outline[0].clone());
  const hi = outline.reduce((a, p) => a.max(p), outline[0].clone());
  const mid3 = lo.clone().add(hi).multiplyScalar(0.5);
  const whole = (k: number, dir: THREE.Vector3, high = 0) => {
    // in a tall frame a long animal is seen three-quarters on: its length needn't fit across the narrow width
    const D = distFor(Math.max(w, l) * (aspect < 1 ? 0.55 : 1.05), h * 1.25, fov, aspect) * k;
    const pos = mid3.clone().addScaledVector(dir.clone().normalize(), D);
    pos.y = Math.max(0.6, c.y * 0.55 + h * 0.15 + high * D);
    return {pos, look: mid3.clone()};
  };
  const close = (k: number) => {
    const D = distFor(head.size * 2.4 * k, head.size * 2.4 * k, 34, aspect);
    const dir = f.clone().multiplyScalar(0.85).addScaledVector(sd, 0.5).normalize();
    return {pos: head.p.clone().addScaledVector(dir, D).add(new THREE.Vector3(0, head.size * 0.25, 0)), look: head.p.clone()};
  };
  let pv: {pos: THREE.Vector3; look: THREE.Vector3};
  let lens = fov;
  switch (cam) {
    case 'face':
      pv = close(1);
      lens = 34;
      break;
    case 'detail':
      pv = close(0.55);
      lens = 34;
      break;
    case 'crash-zoom': {
      const a = whole(1, f.clone().addScaledVector(sd, 0.6));
      const z = close(0.9);
      const p = ease(Math.min(1, t / Math.max(0.4, dur * 0.4)));
      pv = {pos: a.pos.clone().lerp(z.pos, p), look: a.look.clone().lerp(z.look, p)};
      break;
    }
    case 'low': {
      pv = whole(0.75, f.clone().addScaledVector(sd, 0.5));
      pv.pos.y = 0.35;
      pv.look = c.clone().add(new THREE.Vector3(0, h * 0.3, 0));
      lens = 50;
      break;
    }
    case 'wide':
      // the place with it: wider for a small creature, and a huge one already fills a wide frame
      pv = whole(Math.max(1.35, Math.min(2.3, 2.3 - 0.06 * Math.max(0, Math.max(w, l) - 6))), f.clone().multiplyScalar(0.6).addScaledVector(sd, 0.8), 0.12);
      break;
    case 'side':
    case 'tracking':
      pv = whole(1.15, sd);
      break;
    case 'front':
    case 'lead':
      pv = whole(1.2, f.clone().addScaledVector(sd, 0.15));
      break;
    case 'back':
    case 'chase':
      pv = whole(1.3, f.clone().negate().addScaledVector(sd, 0.35), 0.1);
      pv.look = c.clone().addScaledVector(f, l * 0.8);
      break;
    case 'aerial':
    case 'top':
    case 'heli':
    case 'drone':
      pv = whole(1.6, f.clone().multiplyScalar(0.5).addScaledVector(sd, 0.5), 0.75);
      break;
    case 'orbit': {
      const a = seed * 0.9 + t * 0.3;
      pv = whole(1.25, f.clone().applyAxisAngle(up, a));
      break;
    }
    default: // medium: all of it, from three-quarters in front
      pv = whole(1.05, f.clone().multiplyScalar(0.75).addScaledVector(sd, 0.65));
  }
  // a slow push, so a held shot still breathes
  const push = 1 - 0.05 * ease(t / Math.max(1, dur));
  pv.pos = pv.look.clone().add(pv.pos.clone().sub(pv.look).multiplyScalar(push));
  if (cam !== 'face' && cam !== 'detail' && !(cam === 'crash-zoom' && t > dur * 0.2)) pv.pos = fitAll(pv.pos, pv.look, outline, lens, aspect);
  pv.pos.y = Math.max(0.3, pv.pos.y);
  const focus = pv.pos.distanceTo(cam === 'face' || cam === 'detail' ? head.p : c);
  void set;
  return {pos: pv.pos, look: pv.look, up: up.clone(), fov: lens, focus, aperture: 0.06, near: Math.max(0.05, Math.min(1.2, focus * 0.2))};
};

// The camera of a shot at time t: on its subject (the focus actor, or the vehicle when nobody is in the shot), by the
// camera the story asked for (as camOf turns it), and the wide view of the place when there is nothing to film.
// the big thing a shot with nobody in it is about: its first creature, else its first design, else its first big thing
export const subjectBig = (shot: LPShot, set: SetDef, t: number): {b: Big; st: BigState} | undefined => {
  if (shot.actors.length) return undefined;
  const all = (shot.big ?? []).map((b0, k) => ({b: scaledBig(b0, shot), k}));
  // a creature before an egg it hatches from, before anything else
  const pick = all.find(({b}) => isCreature(b) && !/egg|shell/i.test(b.made ?? '')) ?? all.find(({b}) => isCreature(b)) ?? all.find(({b}) => b.kind === 'made' && !isVehicle(b)) ?? all[0]; // (a vehicle under way has its own cameras: rides, before this)
  if (!pick) return undefined;
  return {b: pick.b, st: bigState(pick.b, set, [], actionTime(shot, t), actionTime(shot, shot.duration), pick.k)};
};

export const planFor = (shot: LPShot, set: SetDef, placed: Placed[], rides: (Ride | undefined)[], aspect: number, t: number) => {
  const who = placed[Math.min(placed.length - 1, Math.max(0, shot.focus ?? 0))];
  // (someone who leaps off a vehicle in this shot is filmed as himself the whole shot, not as the vehicle)
  const ride = who ? (who.ride !== undefined && who.actor.action !== 'jump-off' ? rides[who.ride] : undefined) : rides.find((r) => r?.under) ?? rides.find(Boolean);
  const seed = shot.seed ?? 1;
  // the cut-in: for its fraction of a second the camera is on his foot or his hands, then back
  const ins = insertsOf(shot).find((x) => t >= x.from && t < x.to && rides[x.on]);
  if (ins) {
    const driver = placed.find((p) => p.ride === ins.on && p.actor.action === 'drive' && p.inside);
    if (driver) return {plan: insertPlan(ins.cam, rides[ins.on]!, driver, aspect, t, seed), who: driver, ride: rides[ins.on], cam: ins.cam as Cam, insert: true};
  }
  const cam = camOf(shot.camera, who, ride);
  const plan: CamPlan =
    ride && (VEHICLE_CAMS.has(cam) || (!who && cam === 'orbit'))
      ? rideCam(cam, ride, who, set, shot, aspect, t, seed)
      : who
        ? camFor(cam, who, placed, set, aspect, t, shot.duration, seed)
        : subjectBig(shot, set, t)
          ? bigCam(shot.camera, subjectBig(shot, set, t)!.b, subjectBig(shot, set, t)!.st, set, aspect, t, shot.duration, seed)
          : {pos: V(set.wide.pos), look: V(set.wide.look), up: new THREE.Vector3(0, 1, 0), fov: 40, focus: 5, aperture: 0.1};
  return {plan, who, ride, cam, insert: CUT_CAMS.has(cam)};
};

const CamRig: React.FC<{plan: CamPlan; exposure: number}> = ({plan, exposure}) => {
  const camera = useThree((s) => s.camera) as THREE.PerspectiveCamera;
  const gl = useThree((s) => s.gl);
  useLayoutEffect(() => {
    camera.position.copy(plan.pos);
    camera.up.copy(plan.up);
    camera.fov = plan.fov;
    camera.near = plan.near ?? 0.05;
    camera.far = 400;
    camera.lookAt(plan.look);
    camera.updateProjectionMatrix();
    camera.updateMatrixWorld();
    gl.toneMappingExposure = exposure;
  });
  return null;
};

// Depth of field: the scene rendered, blurred by depth around the focus distance, then tone mapped.
const Post: React.FC<{focus: number; aperture: number}> = ({focus, aperture}) => {
  const gl = useThree((s) => s.gl);
  const scene = useThree((s) => s.scene);
  const camera = useThree((s) => s.camera);
  const size = useThree((s) => s.size);
  const parts = useMemo(() => {
    const composer = new EffectComposer(gl);
    composer.addPass(new RenderPass(scene, camera));
    const bokeh = new BokehPass(scene, camera, {focus: 3, aperture: 0.002, maxblur: 0.008});
    composer.addPass(bokeh);
    composer.addPass(new OutputPass());
    return {composer, bokeh};
  }, [gl, scene, camera]);
  useLayoutEffect(() => {
    parts.composer.setPixelRatio(gl.getPixelRatio());
    parts.composer.setSize(size.width, size.height);
  }, [parts, size, gl]);
  useEffect(() => () => parts.composer.dispose(), [parts]);
  useFrame(() => {
    const u = (parts.bokeh as unknown as {uniforms: Record<string, {value: number}>}).uniforms;
    u.focus.value = focus;
    u.aperture.value = aperture * 0.006;
    u.maxblur.value = 0.009;
    parts.composer.render();
  }, 1);
  return null;
};

// The lights: sky and ground fill, the key (casting the soft shadows) from the set's window or sun, a cool or warm
// fill from the other side, and a lamp when the light calls for one.
const Lights: React.FC<{set: SetDef; light: string; target: THREE.Vector3; eye: THREE.Vector3}> = ({set, light, target, eye}) => {
  const look = LOOKS[light as keyof typeof LOOKS] ?? LOOKS.day;
  const tgt = useMemo(() => new THREE.Object3D(), []);
  const sun = V(set.sun).normalize();
  const keyPos = target.clone().addScaledVector(sun, 14);
  const fillPos = target.clone().add(new THREE.Vector3(-sun.x * 8, 5, Math.abs(sun.z) * 4 + 6));
  return (
    <>
      <primitive object={tgt} position={target.toArray()} />
      <hemisphereLight args={[look.hemi[0], look.hemi[1], look.hemi[2]]} />
      <directionalLight
        position={keyPos.toArray()}
        target={tgt}
        color={look.key[0]}
        intensity={look.key[1]}
        castShadow
        shadow-mapSize={[2048, 2048]}
        shadow-bias={-0.0004}
        shadow-normalBias={0.025}
        shadow-radius={6}
        shadow-camera-left={-5}
        shadow-camera-right={5}
        shadow-camera-top={5}
        shadow-camera-bottom={-5}
        shadow-camera-near={0.5}
        shadow-camera-far={40}
      />
      <directionalLight position={fillPos.toArray()} target={tgt} color={look.fill[0]} intensity={look.fill[1]} />
      {/* a soft light from the camera's side, so his face reads in the dark looks too (lamp-lit rooms lost it) */}
      <directionalLight position={eye.clone().add(new THREE.Vector3(0, 0.6, 0)).toArray()} target={tgt} color="#fff1e2" intensity={look.shade < 0.8 ? 0.8 : 0.35} />
      {look.lamp > 0 && set.lamp ? (
        <pointLight position={set.lamp} color="#ffb46b" intensity={look.lamp * 3.2} distance={9} decay={1.6} castShadow={false} />
      ) : null}
    </>
  );
};

const DUST: Partial<Record<string, string>> = {construction: '#b8a58c', highway: '#9d968c', bridge: '#9d968c', alley: '#77746f', street: '#8f8c88', park: '#a99a7c'};

// Actions that keep their own way (they act on the place, not on the other person) and those that turn right round.
const LONE = new Set<Action>(['push-stop', 'catch', 'lift', 'throw', 'super-jump', 'land', 'dash', 'punch', 'look-out', 'pushup', 'cower', 'flee', 'carried', 'fall', 'skydive', 'jump-off', 'brace', 'drive', 'ride']);
const FULL_TURN = new Set<Action>(['help-up', 'carry']);

// ---------------------------------------------------------------- who stands where in a shot
// The user's films had people inside each other: two walkers on one spot walked the same line, a walk to someone's
// spot ended inside them, and spots only 0.5 apart (the park's left/center/right) put heads through heads. Each shot
// is laid out once: people who stay put first (a second one on a spot moves along it, as along a couch), then the
// walkers, each on the first lane (sideways from his line, 0, ±0.85, ±1.7) where he is never within GAP of anyone at
// any moment of the shot; a walk to the spot of someone standing or sitting there stops in front of them.
const SAMPLES = 16;
const VEHICLE_GAP = 0.7; // a person's middle never closer than this to a moving or ridden vehicle's side
const TOUCHES_VEHICLE = new Set(['push-stop', 'lift', 'catch', 'throw', 'crush', 'punch']);
type Layout = {lanes: Lane[]; paths: ([number, number][] | undefined)[]};
const LAYOUTS = new WeakMap<LPShot, Layout>();

export const layoutFor = (shot: LPShot, set: SetDef, cast: Record<string, Design>): Layout => {
  const hit = LAYOUTS.get(shot);
  if (hit) return hit;
  const actors = shot.actors;
  const lanes: Lane[] = actors.map(() => ({off: [0, 0]}));
  const paths: ([number, number][] | undefined)[] = actors.map(() => undefined);
  const times = Array.from({length: SAMPLES + 1}, (_, i) => (shot.duration * i) / SAMPLES);
  const track = (k: number, lane: Lane) =>
    times.map((t) => {
      const p = place(actors[k], k, set, shot, t, cast, [], undefined, lane);
      return [p.root[0], p.root[2]] as [number, number];
    });
  const pair = (i: number, j: number) => {
    const carry = (x: number, y: number) => actors[x].action === 'carry' && actors[y].action === 'carried';
    return carry(i, j) || carry(j, i);
  };
  // the vehicles that move or have someone in them, where they are at each moment: nobody stands or walks in their
  // way (the user, again and again: a car driven through a man standing on the roof, on the bridge)
  const rides = times.map((t) => rideStates(shot, set, t));
  const vehicleGap = (k: number, path: [number, number][]) => {
    if (TOUCHES_VEHICLE.has(actors[k].action)) return Infinity; // he stops it, lifts it, is meant to meet it
    let worst = Infinity;
    rides.forEach((rs, s) =>
      rs.forEach((r) => {
        if (!r) return;
        const [w, , l] = sizeOf(r.b);
        const dx = path[s][0] - r.st.pos.x;
        const dz = path[s][1] - r.st.pos.z;
        const c = Math.cos(r.st.ry);
        const sn = Math.sin(r.st.ry);
        const lx = dx * c - dz * sn; // across the vehicle
        const lz = dx * sn + dz * c; // along it
        worst = Math.min(worst, Math.hypot(Math.max(0, Math.abs(lx) - w / 2), Math.max(0, Math.abs(lz) - l / 2)));
      }),
    );
    return worst;
  };
  const clearance = (k: number, path: [number, number][]) => {
    let worst = Infinity;
    paths.forEach((other, j) => {
      if (!other || j === k || pair(j, k)) return;
      path.forEach((p, s) => (worst = Math.min(worst, Math.hypot(p[0] - other[s][0], p[1] - other[s][1]))));
    });
    // a vehicle's side within VEHICLE_GAP counts like a person within GAP
    return Math.min(worst, vehicleGap(k, path) - VEHICLE_GAP + GAP);
  };
  // the one carried goes with his carrier, people in or on a vehicle with it: neither walks a lane of his own
  const order = actors.map((_, k) => k).filter((k) => actors[k].action !== 'carried' && !onVehicle(shot, k));
  order.sort((i, j) => Number(moves(actors[i])) - Number(moves(actors[j])));
  for (const k of order) {
    const a = actors[k];
    const sp = spotOf(set, a.spot);
    let to: [number, number] | undefined;
    let axis: [number, number] = [Math.cos(sp.ry), -Math.sin(sp.ry)]; // along the spot (the couch, the counter)
    let along: [number, number] = [0, 0]; // a walker's own direction
    if (moves(a)) {
      const straight = track(k, {off: [0, 0]});
      const start = straight[0];
      if (a.to) {
        // someone standing or sitting where he goes: he stops in front of them, facing them
        const b = spotOf(set, a.to);
        // (sitting there, or standing at the seat's standing place)
        const near = (q: [number, number]) => Math.min(Math.hypot(q[0] - b.x, q[1] - b.z), b.stand ? Math.hypot(q[0] - b.stand[0], q[1] - b.stand[1]) : Infinity);
        const there = paths.find((p, j) => p && j !== k && !moves(actors[j]) && near(p[SAMPLES]) < GAP);
        if (there) {
          const occ = there[SAMPLES];
          const d = Math.hypot(occ[0] - start[0], occ[1] - start[1]);
          const ux = d > 1e-3 ? (occ[0] - start[0]) / d : 0;
          const uz = d > 1e-3 ? (occ[1] - start[1]) / d : 1;
          const stop = Math.max(0.02, d - (SEAT_SPOTS.has(a.to) ? STOP_SEATED : STOP_SHORT));
          to = [start[0] + ux * stop, start[1] + uz * stop];
        }
      }
      const end = to ?? straight[SAMPLES];
      const dx = end[0] - start[0];
      const dz = end[1] - start[1];
      const len = Math.hypot(dx, dz);
      if (len > 0.05) {
        axis = [dz / len, -dx / len]; // sideways from his line
        along = [dx / len, dz / len];
      }
    }
    let best: Lane = {off: [0, 0], to};
    let bestPath: [number, number][] | undefined;
    let bestGap = -1;
    // sideways lanes; walkers side by side are also a little ahead or behind each other, so a camera from the side
    // sees a group, not one man hiding the others
    for (const [s, b] of [[0, 0], [0.9, -0.85], [-0.9, 0.85], [1.8, -1.7], [-1.8, 1.7], [2.7, 0], [-2.7, 0], [3.6, 0], [-3.6, 0], [4.6, 0], [-4.6, 0]]) {
      const lane: Lane = {off: [axis[0] * s + along[0] * b, axis[1] * s + along[1] * b], to};
      const path = track(k, lane);
      const gap = clearance(k, path);
      if (gap > bestGap + 0.05) {
        best = lane;
        bestPath = path;
        bestGap = gap;
      }
      if (gap >= GAP) break;
    }
    lanes[k] = best;
    paths[k] = bestPath;
  }
  const out = {lanes, paths};
  LAYOUTS.set(shot, out);
  return out;
};

// Everyone in the shot, in order (the one carried is placed after the one who carries him); each turns to the one he
// looks at (`look`), else toward the nearest other person (within 4 m).
export const placeAll = (shot: LPShot, set: SetDef, t: number, cast: Record<string, Design>) => {
  const {lanes, paths} = layoutFor(shot, set, cast);
  const placed: (Placed | undefined)[] = shot.actors.map(() => undefined);
  const done: Placed[] = [];
  const where = (j: number, at: number): [number, number] | undefined => {
    const p = paths[j];
    if (!p) return undefined;
    const f = Math.max(0, Math.min(SAMPLES, (at / Math.max(0.01, shot.duration)) * SAMPLES));
    const i = Math.min(SAMPLES - 1, Math.floor(f));
    const u = f - i;
    return [p[i][0] + (p[i + 1][0] - p[i][0]) * u, p[i][1] + (p[i + 1][1] - p[i][1]) * u];
  };
  const target = (k: number) => {
    const name = shot.actors[k].look;
    return name ? shot.actors.findIndex((o, j) => j !== k && o.who === name) : -1;
  };
  const aimOf = (k: number): Aim | undefined => {
    const j = target(k);
    const me = where(k, t);
    const them = j >= 0 ? where(j, t) : undefined;
    if (them) return {x: them[0], z: them[1], explicit: true};
    if (!me) return undefined;
    let best: Aim | undefined;
    let dist = 4;
    paths.forEach((_, o) => {
      const p = o !== k ? where(o, shot.duration / 2) : undefined;
      const d = p ? Math.hypot(p[0] - me[0], p[1] - me[1]) : Infinity;
      if (p && d < dist && d > 0.05) {
        dist = d;
        best = {x: p[0], z: p[1], explicit: false};
      }
    });
    return best;
  };
  // the people on the ground first, the one carried after his carrier, then those in or on vehicles (a car stopped by
  // a man's hands needs him placed before its driver)
  const slots = rideSlots(shot);
  let rides: (Ride | undefined)[] | undefined;
  for (const pass of [0, 1, 2]) {
    shot.actors.forEach((a, k) => {
      const rider = onVehicle(shot, k);
      if ((rider ? 2 : a.action === 'carried' ? 1 : 0) !== pass) return;
      let pl: Placed;
      if (rider) {
        rides ??= rideStates(shot, set, t, holders(done));
        const r = rides[a.on!];
        const j = target(k);
        const mate = r && j >= 0 && shot.actors[j].on === a.on && slots[j] ? slotPlace(r.b, slots[j]!).root : undefined;
        pl = r ? placeOn(a, k, set, shot, t, cast, r, slots[k]!, mate) : place(a, k, set, shot, t, cast, done, aimOf(k), lanes[k]);
      } else {
        pl = place(a, k, set, shot, t, cast, done, aimOf(k), lanes[k]);
      }
      placed[k] = pl;
      done.push(pl);
    });
  }
  placed.forEach((pl, k) => {
    const j = target(k);
    if (pl && j >= 0 && placed[j]) pl.aim = placed[j]!.head.clone();
  });
  return placed as Placed[];
};

const holders = (placed: Placed[]): Holder[] => placed.map((p) => ({action: p.actor.action, root: p.root, ry: p.ry, head: p.head, hand: p.hand, body: p.body, on: p.ride}));

// The shot's vehicles that someone is in or on, or that travel, at time t (with the people on the ground placed).
const ridesAt = (shot: LPShot, set: SetDef, placed: Placed[], t: number) => rideStates(shot, set, t, holders(placed.filter((p) => p.ride === undefined)));

// Is this actor in or on one of the shot's vehicles?
const onVehicle = (shot: LPShot, k: number) => {
  const on = shot.actors[k].on;
  const b = on !== undefined ? shot.big?.[on] : undefined;
  return !!b && isVehicle(b);
};

// The effects with their start in action seconds, and where each one happens.
const fxPlan = (shot: LPShot, set: SetDef, placed: Placed[], who: Placed | undefined, bigs: {b: Big; st: BigState}[], ta: number, da: number, ride?: Ride) =>
  (shot.fx ?? []).map((f: Fx, i) => {
    const at = f.at !== undefined ? actionTime(shot, f.at) : ['rain', 'wind'].includes(f.kind) ? 0 : f.kind === 'meteor' ? da * 0.1 : da * 0.4;
    const fallen = bigs.find((x) => x.b.motion === 'fall' || x.b.motion === 'crushed');
    let point: THREE.Vector3;
    if (f.spot) {
      const sp = spotOf(set, f.spot);
      point = new THREE.Vector3(sp.x, 0, sp.z);
    } else if ((f.kind === 'sparks' || f.kind === 'glass') && bigs.length) {
      point = bigs[0].st.contact.clone();
    } else if (['fire', 'smoke'].includes(f.kind) && bigs.length) {
      point = bigs[0].st.pos.clone().setY(bigs[0].st.pos.y + 0.6);
    } else if (fallen && ['dust', 'debris', 'crack', 'shockwave'].includes(f.kind)) {
      point = fallen.st.contact.clone().setY(0);
    } else if (who) {
      point = new THREE.Vector3(who.root[0], 0, who.root[2]);
    } else {
      point = new THREE.Vector3();
    }
    const fast = placed.find((p) => ['dash', 'run', 'flee', 'super-jump'].includes(p.actor.action));
    const runner = who && ['dash', 'run', 'flee', 'super-jump'].includes(who.actor.action) ? who : fast;
    // speed streaks follow a vehicle under way (from its bottom, along the way it travels), else the fastest runner
    const vh = ride?.under ? sizeOf(ride.b)[1] : 0;
    const mover = ride?.under
      ? {root: [ride.st.pos.x, ride.st.pos.y - vh / 2, ride.st.pos.z] as V3, ry: ride.st.heading ?? ride.st.ry}
      : runner
        ? {root: runner.root, ry: runner.ry}
        : undefined;
    const ctx: FxCtx = {
      at,
      t: ta,
      dur: da,
      point,
      mover,
      around: who ? new THREE.Vector3(who.root[0], 0, who.root[2]) : new THREE.Vector3(),
      seed: (shot.seed ?? 1) * 5 + i,
      dust: DUST[shot.set] ?? '#b8ab98',
      indoor: !set.outdoor,
    };
    return {kind: f.kind, ctx};
  });

// Where each car, bus or truck that acts on its own goes in a shot, worked out once (the user's bus drove along the
// bus stop's pavement, through the shelter and the people, and a camera standing in its way showed its inside): on the
// road where the set has one; then the first lane (a metre at a time across the road) and, for one standing still, the
// first place along it where at no moment of the shot it comes within reach of anyone, has the camera inside it or,
// standing, hides a person from the camera. A car someone stops with his hands is his and comes at him.
const VPLANS = new WeakMap<LPShot, (RoadPlace | undefined)[]>();
const vehiclePlans = (shot: LPShot, set: SetDef, cast: Record<string, Design>, aspect: number) => {
  const got = VPLANS.get(shot);
  if (got) return got;
  const bigs = shot.big ?? [];
  const stopper = shot.actors.some((a) => a.action === 'push-stop');
  // (a vehicle someone is in or on, or one under way, has its own path: rideStates)
  const ridden = rideStates(shot, set, 0);
  const want = bigs.map((b, k) => VEHICLE.has(b.kind) && ROAD_MOTIONS.has(b.motion) && !(b.motion === 'stop' && stopper) && !ridden[k]);
  let out: (RoadPlace | undefined)[] = bigs.map(() => undefined);
  if (want.some(Boolean)) {
    const {paths} = layoutFor(shot, set, cast);
    const views: {t: number; cam: THREE.Vector3; heads: THREE.Vector3[]}[] = [];
    for (let i = 0; i <= 8; i++) {
      const t = (shot.duration * i) / 8;
      const placed = placeAll(shot, set, t, cast);
      if (placed.length) views.push({t, cam: planFor(shot, set, placed, ridesAt(shot, set, placed, t), aspect, t).plan.pos, heads: placed.map((p) => p.head)});
    }
    const xRoad = set.walk === 'x'; // the road runs along x (else along z)
    // every other vehicle at each moment of the shot: those under way or with someone in them (their own paths) and
    // the road vehicles placed before this one; a place where it would touch one of them is refused (the user's truck
    // drove straight through the hero's car: lanes were chosen against people and the camera only)
    const moments = Array.from({length: 13}, (_, i) => (shot.duration * i) / 12);
    const da = actionTime(shot, shot.duration);
    const movingAt = moments.map((t) => rideStates(shot, set, t));
    const settled: {b: Big; k: number; place: RoadPlace}[] = [];
    const touch = vehiclesTouch;
    const clash = (b0: Big, k: number, place: RoadPlace) =>
      moments.some((t, i) => {
        const ta = actionTime(shot, t);
        const b = scaledBig(b0, shot);
        const st = bigState(b, set, [], ta, da, k, place);
        if (movingAt[i].some((r, j) => r && j !== k && touch(b, st, r.b, r.st))) return true;
        return settled.some((o) => {
          const ob = scaledBig(o.b, shot);
          return touch(b, st, ob, bigState(ob, set, [], ta, da, o.k, o.place));
        });
      });
    out = bigs.map((b, k) => {
      const place = roadPlace(b, k);
      if (place) settled.push({b, k, place});
      return place;
    });
    function roadPlace(b: Big, k: number): RoadPlace | undefined {
      if (!want[k]) return undefined;
      const sp = spotOf(set, b.spot);
      const road = set.road !== undefined && xRoad;
      const base = road ? set.road! : xRoad ? sp.z : sp.x;
      const at = xRoad ? sp.x : sp.z;
      const [w, h, l] = sizeOf(b);
      const passes = b.motion === 'drive' || b.motion === 'stop'; // it comes along the whole road
      const lanes = (road ? [0, 1, 2, 3, 4, 5, 6] : [0, -1, 1, -2, 2, -3, 3, -4, 4]).map((d) => base + d);
      const shifts = passes ? [0] : [0, -1, 1, -2, 2].map((m) => m * (l / 2 + 1.4));
      const across = (v: {x: number; z: number}) => (xRoad ? v.z : v.x);
      const along = (v: {x: number; z: number}) => (xRoad ? v.x : v.z);
      // at how many moments it stands or drives between the camera and someone (a truck passing between the lens and
      // the hero's car hid him for most of a tracking shot)
      const hidesAt = (place: RoadPlace) =>
        views.filter((v) => {
          const st = bigState(scaledBig(b, shot), set, [], actionTime(shot, v.t), da, k, place);
          return v.heads.some((hd) => [0.25, 0.4, 0.55, 0.7, 0.85].some((f) => insideBig(b, st, v.cam.clone().lerp(hd, f), 0.05)));
        }).length;
      let best: {place: RoadPlace; hides: number} | undefined;
      let clear: RoadPlace | undefined; // touches no other vehicle, whatever else
      for (const lane of [...lanes, ...lanes.map((x) => x + (road ? 7 : 5) * Math.sign(lanes[lanes.length - 1] - base || 1))]) {
        for (const shift of shifts) {
          const c = at + shift;
          const near = (v: {x: number; z: number}, m: number) => Math.abs(across(v) - lane) < w / 2 + m && (passes || Math.abs(along(v) - c) < l / 2 + m);
          const place: RoadPlace = {lane, shift};
          if (set.gap && !passes && c + l / 2 > set.gap[0] - 0.5 && c - l / 2 < set.gap[1] + 0.5) continue; // over the broken span
          if (clash(b, k, place)) continue; // through another car, bus or truck
          clear ??= place;
          if (paths.some((pp) => pp && pp.some((q) => near({x: q[0], z: q[1]}, 0.5)))) continue; // through someone
          if (views.some((v) => v.cam.y < h + 0.35 && near(v.cam, 0.35))) continue; // the camera inside it
          // driving past the lens for a moment is fine; the lane that hides the least, none at best
          const hides = hidesAt(place);
          if (hides === 0) return place;
          if (!best || hides < best.hides) best = {place, hides};
        }
      }
      return best?.place ?? clear ?? {lane: base, shift: 0};
    }
  }
  VPLANS.set(shot, out);
  return out;
};

// How far the camera must move toward what it looks at so that at no moment of the shot is it inside a vehicle or a
// boulder (0 almost always), worked out once per shot from 13 moments.
const PULLS = new WeakMap<LPShot, number>();
// the camera swung round its subject to the other side, for the whole shot, when moving it in can't clear a vehicle
// in the way (a whole car between the lens and the driver beside it at the start line)
const SWINGS = new WeakMap<LPShot, boolean>();
const swung = (plan: CamPlan): THREE.Vector3 => {
  const c = plan.look;
  const d = plan.pos.clone().sub(c);
  return new THREE.Vector3(c.x - d.x, plan.pos.y, c.z - d.z);
};
const pullOf = (shot: LPShot, set: SetDef, cast: Record<string, Design>, aspect: number) => {
  const got = PULLS.get(shot);
  if (got !== undefined) return got;
  let pull = 0;
  const solid = (shot.big ?? []).map((b) => isVehicle(b) || b.kind === 'boulder');
  if (solid.some(Boolean)) {
    const lanes = vehiclePlans(shot, set, cast, aspect);
    const da = actionTime(shot, shot.duration);
    for (let i = 0; i <= 12; i++) {
      const t = (shot.duration * i) / 12;
      const placed = placeAll(shot, set, t, cast);
      const rides = ridesAt(shot, set, placed, t);
      const {plan, who, ride, cam, insert} = planFor(shot, set, placed, rides, aspect, t);
      // the cameras inside his own car are there on purpose; any other camera, his car's own ones included, never
      // sits inside another vehicle (the side camera on a driver at the start line ended up in the car beside his)
      if (!who || insert || INSIDE_CAMS.has(cam)) continue;
      const people = holders(placed);
      const states = (shot.big ?? []).map((b0, k) => {
        const b = scaledBig(b0, shot);
        return {b, k, st: rides[k]?.st ?? bigState(b, set, people, actionTime(shot, t), da, k, lanes[k])};
      }).filter(({k}) => solid[k] && k !== ride?.k);
      const toLook = plan.look.clone().sub(plan.pos);
      const D = toLook.length();
      toLook.normalize();
      const blocked = (d: number) => states.some(({b, st}) => insideBig(b, st, plan.pos.clone().addScaledVector(toLook, d)));
      if (!blocked(pull)) continue;
      const most = Math.min(D - 0.6, plan.pos.distanceTo(who.head) - 1.1); // never into the face it films
      let cleared = false;
      for (let d = pull + 0.15; d < most; d += 0.15) {
        if (!blocked(d)) {
          pull = d;
          cleared = true;
          break;
        }
      }
      if (!cleared) {
        const other = swung(plan);
        const inWay = (p: THREE.Vector3) => states.some(({b, st}) => [0, 0.25, 0.5, 0.75].some((f) => insideBig(b, st, p.clone().lerp(plan.look, f), 0.1)));
        if (!inWay(other)) SWINGS.set(shot, true);
      }
    }
  }
  PULLS.set(shot, pull);
  return pull;
};

const ShotScene: React.FC<{shot: LPShot; t: number; props: LowPolyProps; aspect: number}> = ({shot, t, props, aspect}) => {
  const set = SETS[shot.set] ?? SETS.void;
  const look = LOOKS[shot.light] ?? LOOKS.day;
  const ta = actionTime(shot, t);
  const da = actionTime(shot, shot.duration);
  const placed = placeAll(shot, set, t, props.cast);
  const people = holders(placed);
  const lanes = vehiclePlans(shot, set, props.cast, aspect);
  const rides = ridesAt(shot, set, placed, t);
  const bigs = (shot.big ?? []).map((b0, i) => {
    const b = scaledBig(b0, shot);
    return {b, st: rides[i]?.st ?? bigState(b, set, people, ta, da, i, lanes[i]), i};
  });
  void holderFor;
  const {plan, who, ride, insert, cam} = planFor(shot, set, placed, rides, aspect, t);
  const fx = fxPlan(shot, set, placed, who, bigs, ta, da, ride ?? rides.find((r) => r?.under));
  for (const f of fx) {
    f.ctx.eye = plan.pos.clone();
    f.ctx.look = plan.look.clone();
  }
  // someone seated in it: an open roadster (the driver seen at the wheel), else a coupe
  const seated = new Set(placed.filter((p) => p.ride !== undefined && p.pose.y < 0.75 && ['drive', 'ride'].includes(p.actor.action)).map((p) => p.ride!));
  // never inside a bus driving by: the camera moves toward what it looks at, for the whole shot, with a wider lens
  const pull = who ? pullOf(shot, set, props.cast, aspect) : 0;
  if (who && SWINGS.get(shot) && !insert && !INSIDE_CAMS.has(cam)) plan.pos = swung(plan);
  else if (pull > 0) {
    const toLook = plan.look.clone().sub(plan.pos);
    const D = toLook.length();
    plan.pos.addScaledVector(toLook.normalize(), pull);
    plan.fov = Math.min(75, (2 * Math.atan(Math.tan(((plan.fov / 2) * Math.PI) / 180) * (D / Math.max(0.5, D - pull))) * 180) / Math.PI);
    plan.focus = Math.max(0.3, plan.focus - pull);
  }
  // the camera shakes with the hits: a quick decaying jitter on where it is and where it looks
  const shake = shakeAt(fx.map((f) => ({kind: f.kind, at: f.ctx.at})), ta);
  if (shake > 0.001) {
    const j = new THREE.Vector3(Math.sin(t * 47.3), Math.sin(t * 39.1 + 1.3), Math.sin(t * 31.7 + 2.1)).multiplyScalar(shake);
    plan.pos.add(j);
    plan.look.add(j.multiplyScalar(0.6));
  }
  // the city taken back by nature: all the way, or growing over the shot from the modern city to the jungle
  const wild = shot.overgrown === 'ruined' ? 1 : shot.overgrown === 'growing' ? Math.min(1, Math.max(0, (ta / Math.max(0.5, da)) * 1.15)) : 0;
  const things = shot.things ?? [];
  const s = V(set.surface);
  return (
    <>
      <color attach="background" args={[look.sky[1]]} />
      {set.outdoor ? <fogExp2 attach="fog" args={[look.sky[1], look.fog * (set.sky ? 0.3 : 1)]} /> : null}
      <CamRig plan={plan} exposure={look.exposure} />
      <Lights set={set} light={shot.light} target={who ? who.head.clone().lerp(who.body, 0.5) : ride ? ride.st.pos.clone() : subjectBig(shot, set, t)?.st.pos.clone() ?? V(set.wide.look)} eye={plan.pos} />
      <set.Draw look={look} seed={(shot.seed ?? 1) % 997} />
      {wild > 0 ? <Overgrowth set={shot.set} g={wild} look={look} seed={(shot.seed ?? 1) % 997} /> : null}
      {things.map((th, i) => (
        <ThingView key={i} kind={th.kind} glow={th.glow} label={th.label} p={[s.x + (i - (things.length - 1) / 2) * 0.32, s.y, s.z]} />
      ))}
      {bigs.map(({b, st, i}) => (
        <BigView key={`big${i}`} b={b} st={st} seed={(shot.seed ?? 1) + i * 3} open={seated.has(i)} t={ta} night={look.shade < 0.8} pedals={{...pressAt(shot, t, i), at: placed.find((p) => p.ride === i && p.pedalAt)?.pedalAt}} wild={wild} />
      ))}
      {fx.map((f, i) => (
        <FxView key={`fx${i}`} kind={f.kind} c={f.ctx} />
      ))}
      {placed.map((pl, i) => {
        const man = (
          <Man
            design={pl.design}
            pose={pl.pose}
            face={face(pl.actor.expression, ta, i + (shot.seed ?? 0), (pl.actor.talk ?? []).some(([a, b]) => t >= a && t < b))}
            root={pl.local ? pl.local.root : pl.root}
            ry={pl.local ? pl.local.ry : pl.ry}
            hold={pl.hold}
            seed={pl.actor.who === 'hero' ? 7 : pl.seed}
            screen={pl.actor.screen}
            screenT={t}
          />
        );
        // in or on a vehicle: drawn in its frame, so he turns, pitches and rolls with it
        if (pl.local) {
          return (
            <group key={i} position={pl.local.pos} quaternion={pl.local.quat}>
              {man}
            </group>
          );
        }
        return (
          <group key={i}>
            {man}
            {pl.actor.covered && LYING.has(pl.actor.action) ? <Blanket pl={pl} /> : null}
            {pl.actor.action === 'sit' && spotOf(set, pl.actor.spot).seat === undefined ? <StoolUnder pl={pl} /> : null}
          </group>
        );
      })}
      {/* down in the footwell or close on the wheel: a soft light from beside the lens, or it is all shadow */}
      {insert && cam !== 'speedo' ? <pointLight position={plan.pos.toArray()} color="#fff0dc" intensity={1.6} distance={1.6} decay={1.2} /> : null}
      {props.dof !== false ? <Post focus={plan.focus} aperture={plan.aperture} /> : null}
    </>
  );
};

// The blanket over a man lying in bed: a soft block from the chest down (only the legs once he sits up).
const Blanket: React.FC<{pl: Placed}> = ({pl}) => {
  const up = pl.pose.rx > -1.2;
  const side = Math.abs(pl.pose.rz) > 1.2;
  const h = side ? 0.72 : up ? 0.3 : 0.46;
  const z0 = up ? -0.55 : -1.75;
  const len = (pl.root[2] + 0.95) - (pl.root[2] + 1.45 + z0);
  return (
    <mesh position={[pl.root[0], 0.54 + h / 2, pl.root[2] + 1.45 + z0 + len / 2]} castShadow receiveShadow>
      <boxGeometry args={[1.86, h, Math.max(0.6, len)]} />
      <primitive object={mat('#c25e5c')} attach="material" />
    </mesh>
  );
};

const StoolUnder: React.FC<{pl: Placed}> = ({pl}) => (
  <mesh position={[pl.root[0], 0.22, pl.root[2]]} castShadow receiveShadow>
    <cylinderGeometry args={[0.26, 0.22, 0.44, 7]} />
    <primitive object={mat('#7a5238')} attach="material" />
  </mesh>
);

// ---------------------------------------------------------------- the words and the finish

const useFonts = () => {
  const [handle] = useState(() => delayRender('Loading Anton'));
  useEffect(() => {
    Promise.all(['400 60px Anton', '500 30px Inter', '700 30px Inter', '400 30px "Special Elite"'].map((f) => document.fonts.load(f).catch(() => undefined))).finally(() => continueRender(handle));
  }, [handle]);
};

// 🎭 A movie's character intro: the number, a bar wiping in, the name in big capitals rising letter by letter, the role
// under it spaced wide in the colour they wear; it comes up just after their segment starts and leaves before it
// ends. Bottom left, or bottom right for every second person; centred low in a tall frame.
// 🎭 The crime-caper intro's card (the user: "mafia style intro", "make it cinematic"): on the freeze a slash of the
// colour they wear tears across the frame, the name SLAMS on huge and tilted with a hard shadow, and the role is typed
// under it on a paper tag; no counter (the user: "remove 9/20 char count").
const CaperCard: React.FC<{c: NameCard; t: number; vertical: boolean; width: number}> = ({c, t, vertical, width}) => {
  const a = t - c.start;
  const out = interpolate(t, [c.end - 0.12, c.end], [1, 0], clamp);
  const band = interpolate(a, [0, 0.12], [0, 1], {...clamp, easing: (x) => 1 - (1 - x) ** 3});
  const slam = interpolate(a, [0.04, 0.16], [0, 1], {...clamp, easing: (x) => 1 - (1 - x) ** 3});
  const scale = slam < 1 ? 2.4 - 1.4 * slam : 1 + 0.04 * Math.exp(-(a - 0.16) * 18) * Math.sin((a - 0.16) * 40);
  const name = c.name.toUpperCase();
  const size = Math.min(vertical ? 230 : 280, (width * (vertical ? 0.86 : 0.6)) / Math.max(3, name.length * 0.5));
  const role = c.role.toUpperCase();
  const typed = Math.floor(interpolate(a, [0.2, 0.2 + Math.min(0.55, role.length * 0.03)], [0, role.length], clamp));
  const bottom = vertical ? 470 : 200;
  return (
    <div style={{position: 'absolute', left: 0, right: 0, bottom, height: size * 1.9, opacity: out}}>
      <div style={{position: 'absolute', left: vertical ? -40 : -60, bottom: size * 0.42, height: size * 0.62, width: `${band * (vertical ? 118 : 70)}%`,
        background: c.color, transform: 'skewX(-14deg) rotate(-4deg)', transformOrigin: 'left center', boxShadow: '10px 10px 0 rgba(0,0,0,0.55)'}} />
      <div style={{position: 'absolute', left: vertical ? 0 : 110, right: vertical ? 0 : undefined, bottom: size * 0.5, textAlign: vertical ? 'center' : 'left',
        fontFamily: 'Anton, Impact, sans-serif', fontSize: size, lineHeight: 1, color: '#fff', whiteSpace: 'nowrap', letterSpacing: 2,
        opacity: slam > 0 ? 1 : 0, transform: `rotate(-4deg) scale(${scale})`, transformOrigin: vertical ? 'center' : 'left center',
        textShadow: '7px 7px 0 #000, 0 0 40px rgba(0,0,0,0.5)'}}>
        {name}
      </div>
      <div style={{position: 'absolute', left: vertical ? 0 : 130, right: vertical ? 0 : undefined, bottom: size * 0.1, textAlign: vertical ? 'center' : 'left'}}>
        <span style={{display: typed ? 'inline-block' : 'none', fontFamily: '"Special Elite", "Courier New", monospace', fontSize: vertical ? 50 : 46,
          color: '#16130f', background: '#efe6d2', padding: '6px 16px', transform: 'rotate(-4deg)', boxShadow: '5px 5px 0 rgba(0,0,0,0.6)',
          letterSpacing: 2, whiteSpace: 'nowrap'}}>
          {role.slice(0, typed)}
        </span>
      </div>
    </div>
  );
};

const NameCardView: React.FC<{c: NameCard | undefined; t: number; vertical: boolean}> = ({c, t, vertical}) => {
  if (!c) return null;
  const len = c.end - c.start;
  const a = t - c.start - Math.min(0.35, len * 0.08);
  const out = interpolate(t, [c.end - Math.min(0.45, len * 0.12), c.end - 0.05], [1, 0], clamp);
  const bar = interpolate(a, [0, 0.35], [0, 1], {...clamp, easing: (x) => 1 - (1 - x) ** 3});
  const right = !vertical && c.index % 2 === 0;
  const align = vertical ? 'center' : right ? 'right' : 'left';
  const size = Math.min(vertical ? 118 : 132, (vertical ? 980 : 1100) / Math.max(4, c.name.length * 0.62));
  const letters = [...c.name.toUpperCase()];
  const role = interpolate(a, [0.45, 0.8], [0, 1], clamp);
  return (
    <div
      style={{
        position: 'absolute',
        left: vertical ? 60 : right ? undefined : 110,
        right: vertical ? 60 : right ? 110 : undefined,
        bottom: vertical ? 380 : 120,
        textAlign: align,
        opacity: out,
        transform: `translateY(${(1 - out) * 18}px)`,
      }}
    >
      <div style={{height: 6, width: 150 * bar, background: c.color, margin: vertical ? '14px auto 10px' : right ? '14px 0 10px auto' : '14px 0 10px 0',
        boxShadow: '0 0 18px rgba(0,0,0,0.5)'}} />
      <div style={{fontFamily: 'Anton, Impact, sans-serif', fontSize: size, lineHeight: 1.02, color: '#fff', letterSpacing: 2,
        textShadow: '0 6px 28px rgba(0,0,0,0.7)', whiteSpace: 'nowrap'}}>
        {letters.map((ch, k) => {
          const p = interpolate(a, [0.12 + k * 0.035, 0.42 + k * 0.035], [0, 1], {...clamp, easing: (x) => 1 - (1 - x) ** 3});
          return (
            <span key={k} style={{display: 'inline-block', opacity: p, transform: `translateY(${(1 - p) * 40}px)`, whiteSpace: 'pre'}}>
              {ch}
            </span>
          );
        })}
      </div>
      <div style={{fontFamily: 'Inter, sans-serif', fontWeight: 500, fontSize: vertical ? 34 : 30, letterSpacing: 8, marginTop: 10,
        color: '#fff', opacity: role, transform: `translateX(${(right ? 1 : -1) * (1 - role) * 30}px)`, textShadow: '0 2px 12px rgba(0,0,0,0.8)'}}>
        <span style={{color: c.color, filter: 'brightness(1.35) saturate(1.2)'}}>▍</span>
        {c.role.toUpperCase()}
      </div>
    </div>
  );
};

const Words: React.FC<{c: Caption | undefined; vertical: boolean; t: number}> = ({c, vertical, t}) => {
  if (!c) return null;
  const k = interpolate(t, [c.start, c.start + 0.08], [0.6, 1], clamp);
  const out = c.red ? interpolate(t, [c.end - 0.5, c.end], [1, 0], clamp) : 1;
  return (
    <div
      style={{
        position: 'absolute',
        top: vertical ? '24.5%' : '16%',
        left: 0,
        right: 0,
        padding: vertical ? '0 70px' : '0 260px',
        textAlign: 'center',
        fontFamily: 'Anton, Impact, sans-serif',
        fontSize: vertical ? 96 : 84,
        lineHeight: 1.08,
        letterSpacing: 0.5,
        textTransform: 'uppercase',
        color: c.red ? '#e5342e' : '#ffffff',
        textShadow: '3px 5px 0 rgba(10,10,12,0.92), 0 0 22px rgba(0,0,0,0.45)',
        opacity: k * out,
        transform: `scale(${0.96 + 0.04 * k})`,
      }}
    >
      {c.text}
    </div>
  );
};

// 🎭 The cast intro's camera work on the picture itself: a whip pan in and out (a sideways smear), a push in during the
// sped-up action, and on the freeze a snap zoom with a dutch tilt, a shake as the name lands, and the colour drained.
const caperLook = (shot: LPShot, local: number, frozen: boolean, width: number): React.CSSProperties => {
  if (shot.freeze === undefined && !shot.whipIn && !shot.whipOut) return {};
  let x = 0, blur = 0, scale = 1, rot = 0, filter = '';
  const W = 0.14;
  if (shot.whipIn && local < W) {
    const k = 1 - local / W;
    x += k * k * 0.35 * width;
    blur += k * 14;
  }
  if (shot.whipOut && local > shot.duration - W) {
    const k = (local - (shot.duration - W)) / W;
    x -= k * k * 0.35 * width;
    blur += k * 14;
  }
  if (shot.freeze !== undefined) {
    if (!frozen) scale = 1 + 0.05 * (local / Math.max(0.3, shot.freeze));
    else {
      const a = local - shot.freeze;
      const snap = Math.min(1, a / 0.07);
      scale = 1.05 + 0.07 * snap;
      rot = -2.5 * snap;
      const shake = a < 0.3 ? (1 - a / 0.3) * 9 : 0;
      x += shake * Math.sin(a * 90);
      filter = `saturate(${0.75 + 0.25 * (1 - snap)}) contrast(1.32) brightness(1.08)`;
    }
  }
  if (!frozen && shot.grade === 'caper') filter = 'contrast(1.12) saturate(1.15)';
  return {transform: `translateX(${x}px) scale(${scale}) rotate(${rot}deg)`, filter: `${filter}${blur ? ` blur(${blur}px)` : ''}` || undefined};
};

// Black bars top and bottom: a 2.39:1 film frame in 16:9, a thinner pair in a tall Short.
const Letterbox: React.FC<{vertical: boolean}> = ({vertical}) => {
  const h = vertical ? 150 : Math.round((1080 - 1920 / 2.39) / 2);
  return (
    <>
      <div style={{position: 'absolute', left: 0, right: 0, top: 0, height: h, background: '#000'}} />
      <div style={{position: 'absolute', left: 0, right: 0, bottom: 0, height: h, background: '#000'}} />
    </>
  );
};

const Grain: React.FC<{frame: number}> = ({frame}) => (
  <svg width="100%" height="100%" style={{position: 'absolute', inset: 0, mixBlendMode: 'overlay', opacity: 0.32}}>
    <filter id={`lpg${frame % 8}`}>
      <feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves={2} seed={frame % 8} />
      <feColorMatrix type="saturate" values="0" />
    </filter>
    <rect width="100%" height="100%" filter={`url(#lpg${frame % 8})`} />
  </svg>
);

export const LowPoly: React.FC<LowPolyProps> = (props) => {
  useFonts();
  setMade(props.made); // the things the writer designed for this film (planes, bikes, boats...)
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const t = frame / fps;
  const shots = props.shots;
  let i = shots.findIndex((s) => t >= s.start && t < s.start + s.duration);
  if (i < 0) i = t < (shots[0]?.start ?? 0) ? 0 : shots.length - 1;
  const shot = shots[i];
  const local = t - shot.start;
  // 🎭 the cast intro: the action plays sped up, then the picture freezes on the beat (the name slams on)
  const frozen = shot.freeze !== undefined && local >= shot.freeze;
  const sceneT = shot.freeze !== undefined ? Math.min(local, shot.freeze) * (shot.ramp ?? 1) : local;
  const card = (props.cards ?? []).find((c) => t >= c.start && t < c.end);
  const cap = props.captions.find((c) => t >= c.start && t < c.end);
  const fadeIn = shot.fadeIn ? interpolate(local, [0, shot.fadeIn], [1, 0], clamp) : 0;
  const fadeOut = shot.fadeOut ? interpolate(local, [shot.duration - shot.fadeOut, shot.duration], [0, 1], clamp) : 0;
  const dip = shot.cut === 'dip' ? interpolate(local, [0, 0.25], [1, 0], clamp) : 0;
  const black = Math.max(fadeIn, fadeOut, dip);
  const fxAt = (shot.fx ?? []).map((f) => ({kind: f.kind, at: f.at !== undefined ? actionTime(shot, f.at) : actionTime(shot, shot.duration) * 0.4}));
  const flash = flashAt(fxAt, actionTime(shot, local));
  const alarm = fxAt.find((f) => f.kind === 'alarm' && actionTime(shot, local) >= f.at) ? (Math.sin(actionTime(shot, local) * 9) > 0 ? 'rgba(255,40,40,0.13)' : 'rgba(40,90,255,0.11)') : '';
  return (
    <AbsoluteFill style={{background: '#000'}}>
      <AbsoluteFill style={caperLook(shot, local, frozen, width)}>
        <ThreeCanvas width={width} height={height} shadows gl={{antialias: true}} camera={{fov: 34, near: 0.05, far: 400, position: [0, 1.5, 5]}}>
          {shot.poster ? (
            <PosterScene shot={shot} t={local} cast={props.cast} tall={props.vertical} CamRig={CamRig} />
          ) : (
            <ShotScene shot={shot} t={sceneT} props={props} aspect={width / height} />
          )}
        </ThreeCanvas>
      </AbsoluteFill>
      {shot.poster ? (
        <PosterBusts p={shot.poster} t={local} dur={shot.duration} cast={props.cast} tall={props.vertical} width={width} height={height} CamRig={CamRig} />
      ) : null}
      {shot.grade === 'caper' ? (
        <AbsoluteFill style={{background: 'linear-gradient(135deg, rgba(0,110,130,0.55), rgba(0,0,0,0) 45%, rgba(255,140,40,0.5))', mixBlendMode: 'soft-light',
          opacity: frozen ? 1 : 0.85}} />
      ) : null}
      {frozen && local - shot.freeze! < 0.2 ? <AbsoluteFill style={{background: '#fff', opacity: 0.85 * (1 - (local - shot.freeze!) / 0.2)}} /> : null}
      <AbsoluteFill style={{background: 'radial-gradient(ellipse at 50% 48%, rgba(0,0,0,0) 52%, rgba(0,0,0,0.42) 100%)'}} />
      <Grain frame={frame} />
      {props.cinematic && !shot.poster ? <Letterbox vertical={props.vertical} /> : null}
      {alarm ? <AbsoluteFill style={{background: alarm, mixBlendMode: 'screen'}} /> : null}
      {flash > 0.01 ? <AbsoluteFill style={{background: '#fffaf0', opacity: flash}} /> : null}
      <AbsoluteFill style={{background: '#000', opacity: black}} />
      {props.watermark ? (
        <div
          style={{
            position: 'absolute',
            top: props.vertical ? 62 : 40,
            width: '100%',
            textAlign: 'center',
            fontFamily: 'Anton, Impact, sans-serif',
            fontSize: props.vertical ? 30 : 26,
            letterSpacing: 1,
            color: 'rgba(214,214,214,0.72)',
            textTransform: 'uppercase',
          }}
        >
          {props.watermark}
        </div>
      ) : null}
      <Words c={cap} vertical={props.vertical} t={t} />
      {shot.poster ? <PosterWords p={shot.poster} t={local} tall={props.vertical} width={width} /> : null}
      {card?.style === 'caper' ? <CaperCard c={card} t={t} vertical={props.vertical} width={width} /> : <NameCardView c={card} t={t} vertical={props.vertical} />}
    </AbsoluteFill>
  );
};
