// The "LowPoly" composition (reelgen/lowpoly/): one 3D canvas for the whole film. Each shot puts the cast on a set
// under a time-of-day light and frames them with a camera rule (face, top, medium, wide, side, front, back, low,
// detail) that follows the focus actor, with a slow push and a breath of sway. Depth of field (three's BokehPass)
// keeps the subject sharp; grain, a vignette and a soft grade finish the picture; the narrator's words come up two or
// three at a time in Anton capitals, time stamps take the caption's place, the last line can be red; the channel's
// name sits at the top. Picture only: reelgen/lowpoly/ mixes the sound.
import '@fontsource/anton/400.css';
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
import {LOOKS, SETS, spotOf, ThingView, type SetDef} from './Sets';
import {bigState, BigView, holderFor, insideBig, keyMoment, ROAD_MOTIONS, SIZE, VEHICLE, type BigState, type Holder, type RoadPlace} from './Big';
import {flashAt, FxView, shakeAt, type FxCtx} from './Fx';
import type {Action, Actor, Big, Cam, Caption, Design, Fx, Hold, LowPolyProps, LPShot} from './types';

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
  // stopping a vehicle with his hands: he faces up the road (it comes from there), unless told otherwise
  if (action === 'push-stop' && !a.facing) ry = set.walk === 'z' ? Math.PI : -Math.PI / 2;
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

// ---------------------------------------------------------------- the cameras

export type CamPlan = {pos: THREE.Vector3; look: THREE.Vector3; up: THREE.Vector3; fov: number; focus: number; aperture: number; near?: number};

const distFor = (w: number, h: number, fov: number, aspect: number) => {
  const tan = Math.tan(((fov / 2) * Math.PI) / 180);
  return Math.max(h / 2 / tan, w / 2 / tan / aspect);
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
      pos.lerp(look, 0.06 * p);
      if (others.length) {
        // everyone whole in the picture: the lens opens until the widest person (side to side, head to feet) fits
        const fwd = look.clone().sub(pos).normalize();
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
        const need = Math.max(needV, needH / aspect); // as tan of half the vertical angle
        const have = Math.tan(((fov / 2) * Math.PI) / 180);
        if (need > have) fov = Math.min(72, (2 * Math.atan(need) * 180) / Math.PI);
      }
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

const DUST: Partial<Record<string, string>> = {construction: '#b8a58c', highway: '#9d968c', alley: '#77746f', street: '#8f8c88', park: '#a99a7c'};

// Actions that keep their own way (they act on the place, not on the other person) and those that turn right round.
const LONE = new Set<Action>(['push-stop', 'catch', 'lift', 'throw', 'super-jump', 'land', 'dash', 'punch', 'look-out', 'pushup', 'cower', 'flee', 'carried', 'fall']);
const FULL_TURN = new Set<Action>(['help-up', 'carry']);

// ---------------------------------------------------------------- who stands where in a shot
// The user's films had people inside each other: two walkers on one spot walked the same line, a walk to someone's
// spot ended inside them, and spots only 0.5 apart (the park's left/center/right) put heads through heads. Each shot
// is laid out once: people who stay put first (a second one on a spot moves along it, as along a couch), then the
// walkers, each on the first lane (sideways from his line, 0, ±0.85, ±1.7) where he is never within GAP of anyone at
// any moment of the shot; a walk to the spot of someone standing or sitting there stops in front of them.
const SAMPLES = 16;
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
  const clearance = (k: number, path: [number, number][]) => {
    let worst = Infinity;
    paths.forEach((other, j) => {
      if (!other || j === k || pair(j, k)) return;
      path.forEach((p, s) => (worst = Math.min(worst, Math.hypot(p[0] - other[s][0], p[1] - other[s][1]))));
    });
    return worst;
  };
  const order = actors.map((_, k) => k).filter((k) => actors[k].action !== 'carried');
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
    for (const [s, b] of [[0, 0], [0.9, -0.85], [-0.9, 0.85], [1.8, -1.7], [-1.8, 1.7]]) {
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
  for (const late of [false, true]) {
    shot.actors.forEach((a, k) => {
      if ((a.action === 'carried') !== late) return;
      const pl = place(a, k, set, shot, t, cast, done, aimOf(k), lanes[k]);
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

const holders = (placed: Placed[]): Holder[] => placed.map((p) => ({action: p.actor.action, root: p.root, ry: p.ry, head: p.head, hand: p.hand, body: p.body}));

// The effects with their start in action seconds, and where each one happens.
const fxPlan = (shot: LPShot, set: SetDef, placed: Placed[], who: Placed | undefined, bigs: {b: Big; st: BigState}[], ta: number, da: number) =>
  (shot.fx ?? []).map((f: Fx, i) => {
    const at = f.at !== undefined ? actionTime(shot, f.at) : ['rain', 'wind'].includes(f.kind) ? 0 : da * 0.4;
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
    const mover = who && ['dash', 'run', 'flee', 'super-jump'].includes(who.actor.action) ? who : fast;
    const ctx: FxCtx = {
      at,
      t: ta,
      dur: da,
      point,
      mover: mover ? {root: mover.root, ry: mover.ry} : undefined,
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
  const want = bigs.map((b) => VEHICLE.has(b.kind) && ROAD_MOTIONS.has(b.motion) && !(b.motion === 'stop' && stopper));
  let out: (RoadPlace | undefined)[] = bigs.map(() => undefined);
  if (want.some(Boolean)) {
    const {paths} = layoutFor(shot, set, cast);
    const views: {cam: THREE.Vector3; heads: THREE.Vector3[]}[] = [];
    for (let i = 0; i <= 8; i++) {
      const t = (shot.duration * i) / 8;
      const placed = placeAll(shot, set, t, cast);
      const who = placed[Math.min(placed.length - 1, Math.max(0, shot.focus ?? 0))];
      if (who) views.push({cam: camFor(shot.camera, who, placed, set, aspect, t, shot.duration, shot.seed ?? 1).pos, heads: placed.map((p) => p.head)});
    }
    const xRoad = set.walk === 'x'; // the road runs along x (else along z)
    out = bigs.map((b, k) => {
      if (!want[k]) return undefined;
      const sp = spotOf(set, b.spot);
      const road = set.road !== undefined && xRoad;
      const base = road ? set.road! : xRoad ? sp.z : sp.x;
      const at = xRoad ? sp.x : sp.z;
      const [w, h, l] = SIZE[b.kind];
      const passes = b.motion === 'drive' || b.motion === 'stop'; // it comes along the whole road
      const lanes = (road ? [0, 1, 2, 3, 4, 5, 6] : [0, -1, 1, -2, 2, -3, 3, -4, 4]).map((d) => base + d);
      const shifts = passes ? [0] : [0, -1, 1, -2, 2].map((m) => m * (l / 2 + 1.4));
      const across = (v: {x: number; z: number}) => (xRoad ? v.z : v.x);
      const along = (v: {x: number; z: number}) => (xRoad ? v.x : v.z);
      let fallback: RoadPlace | undefined;
      for (const lane of lanes) {
        for (const shift of shifts) {
          const c = at + shift;
          const near = (v: {x: number; z: number}, m: number) => Math.abs(across(v) - lane) < w / 2 + m && (passes || Math.abs(along(v) - c) < l / 2 + m);
          if (paths.some((pp) => pp && pp.some((q) => near({x: q[0], z: q[1]}, 0.5)))) continue; // through someone
          if (views.some((v) => v.cam.y < h + 0.35 && near(v.cam, 0.35))) continue; // the camera inside it
          const place: RoadPlace = {lane, shift};
          if (passes) return place; // driving past the lens or in front of people for a moment is fine
          fallback ??= place;
          const st = bigState(b, set, [], 0, shot.duration, k, place);
          const hides = views.some((v) => v.heads.some((hd) => [0.25, 0.4, 0.55, 0.7, 0.85].some((f) => insideBig(b, st, v.cam.clone().lerp(hd, f), 0.05))));
          if (!hides) return place;
        }
      }
      return fallback ?? {lane: base, shift: 0};
    });
  }
  VPLANS.set(shot, out);
  return out;
};

// How far the camera must move toward what it looks at so that at no moment of the shot is it inside a vehicle or a
// boulder (0 almost always), worked out once per shot from 13 moments.
const PULLS = new WeakMap<LPShot, number>();
const pullOf = (shot: LPShot, set: SetDef, cast: Record<string, Design>, aspect: number) => {
  const got = PULLS.get(shot);
  if (got !== undefined) return got;
  let pull = 0;
  const solid = (shot.big ?? []).map((b) => VEHICLE.has(b.kind) || b.kind === 'boulder');
  if (solid.some(Boolean)) {
    const lanes = vehiclePlans(shot, set, cast, aspect);
    const da = actionTime(shot, shot.duration);
    for (let i = 0; i <= 12; i++) {
      const t = (shot.duration * i) / 12;
      const placed = placeAll(shot, set, t, cast);
      const who = placed[Math.min(placed.length - 1, Math.max(0, shot.focus ?? 0))];
      if (!who) continue;
      const plan = camFor(shot.camera, who, placed, set, aspect, t, shot.duration, shot.seed ?? 1);
      const people = holders(placed);
      const states = (shot.big ?? []).map((b0, k) => {
        const b = scaledBig(b0, shot);
        return {b, st: bigState(b, set, people, actionTime(shot, t), da, k, lanes[k])};
      }).filter((_, k) => solid[k]);
      const toLook = plan.look.clone().sub(plan.pos);
      const D = toLook.length();
      toLook.normalize();
      const blocked = (d: number) => states.some(({b, st}) => insideBig(b, st, plan.pos.clone().addScaledVector(toLook, d)));
      if (!blocked(pull)) continue;
      const most = Math.min(D - 0.6, plan.pos.distanceTo(who.head) - 1.1); // never into the face it films
      for (let d = pull + 0.15; d < most; d += 0.15) {
        if (!blocked(d)) {
          pull = d;
          break;
        }
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
  const who = placed[Math.min(placed.length - 1, Math.max(0, shot.focus ?? 0))];
  const people = holders(placed);
  const lanes = vehiclePlans(shot, set, props.cast, aspect);
  const bigs = (shot.big ?? []).map((b0, i) => {
    const b = scaledBig(b0, shot);
    return {b, st: bigState(b, set, people, ta, da, i, lanes[i]), i};
  });
  void holderFor;
  const fx = fxPlan(shot, set, placed, who, bigs, ta, da);
  const plan = who
    ? camFor(shot.camera, who, placed, set, aspect, t, shot.duration, shot.seed ?? 1)
    : {pos: V(set.wide.pos), look: V(set.wide.look), up: new THREE.Vector3(0, 1, 0), fov: 40, focus: 5, aperture: 0.1};
  // never inside a bus driving by: the camera moves toward what it looks at, for the whole shot, with a wider lens
  const pull = who ? pullOf(shot, set, props.cast, aspect) : 0;
  if (pull > 0) {
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
  const things = shot.things ?? [];
  const s = V(set.surface);
  return (
    <>
      <color attach="background" args={[look.sky[1]]} />
      {set.outdoor ? <fogExp2 attach="fog" args={[look.sky[1], look.fog]} /> : null}
      <CamRig plan={plan} exposure={look.exposure} />
      <Lights set={set} light={shot.light} target={who ? who.head.clone().lerp(who.body, 0.5) : V(set.wide.look)} eye={plan.pos} />
      <set.Draw look={look} seed={(shot.seed ?? 1) % 997} />
      {things.map((th, i) => (
        <ThingView key={i} kind={th.kind} glow={th.glow} label={th.label} p={[s.x + (i - (things.length - 1) / 2) * 0.32, s.y, s.z]} />
      ))}
      {bigs.map(({b, st, i}) => (
        <BigView key={`big${i}`} b={b} st={st} seed={(shot.seed ?? 1) + i * 3} />
      ))}
      {fx.map((f, i) => (
        <FxView key={`fx${i}`} kind={f.kind} c={f.ctx} />
      ))}
      {placed.map((pl, i) => (
        <group key={i}>
          <Man
            design={pl.design}
            pose={pl.pose}
            face={face(pl.actor.expression, ta, i + (shot.seed ?? 0), (pl.actor.talk ?? []).some(([a, b]) => t >= a && t < b))}
            root={pl.root}
            ry={pl.ry}
            hold={pl.hold}
            seed={pl.actor.who === 'hero' ? 7 : pl.seed}
          />
          {pl.actor.covered && LYING.has(pl.actor.action) ? <Blanket pl={pl} /> : null}
          {pl.actor.action === 'sit' && spotOf(set, pl.actor.spot).seat === undefined ? <StoolUnder pl={pl} /> : null}
        </group>
      ))}
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
    document.fonts.load('400 60px Anton').catch(() => undefined).finally(() => continueRender(handle));
  }, [handle]);
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
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const t = frame / fps;
  const shots = props.shots;
  let i = shots.findIndex((s) => t >= s.start && t < s.start + s.duration);
  if (i < 0) i = t < (shots[0]?.start ?? 0) ? 0 : shots.length - 1;
  const shot = shots[i];
  const local = t - shot.start;
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
      <ThreeCanvas width={width} height={height} shadows gl={{antialias: true}} camera={{fov: 34, near: 0.05, far: 400, position: [0, 1.5, 5]}}>
        <ShotScene shot={shot} t={local} props={props} aspect={width / height} />
      </ThreeCanvas>
      <AbsoluteFill style={{background: 'radial-gradient(ellipse at 50% 48%, rgba(0,0,0,0) 52%, rgba(0,0,0,0.42) 100%)'}} />
      <Grain frame={frame} />
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
    </AbsoluteFill>
  );
};
