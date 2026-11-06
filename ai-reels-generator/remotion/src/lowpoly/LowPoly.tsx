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
import type {Action, Actor, Cam, Caption, Design, Hold, LowPolyProps, LPShot} from './types';

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;
type V3 = [number, number, number];
const V = (a: V3) => new THREE.Vector3(...a);

const SEATED = new Set<Action>(['sit', 'type', 'eat', 'shoes', 'get-up', 'read', 'phone', 'head-in-hands', 'slump', 'think', 'drink', 'sigh', 'nod', 'shake-head', 'shrug', 'cry', 'stretch', 'reach']);
const LYING = new Set<Action>(['lie', 'lie-side', 'lie-phone', 'sit-up']);
const MOVING = new Set<Action>(['walk', 'run', 'jog']);
const FACE_CAMS = new Set<Cam>(['face', 'face-top', 'medium', 'detail', 'low', 'front']);
const AUTO_HOLD: Partial<Record<Action, Hold>> = {phone: 'phone', 'lie-phone': 'phone', drink: 'mug', read: 'book', eat: 'fork'};

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
};

// facing in the room's own terms: 'camera' keeps the spot's natural way (at the desk, toward the screen), 'away' turns
// his back to the open side (toward the counter, the window, the door), left/right face across the room
const FACING: Record<string, number> = {left: -Math.PI / 2, right: Math.PI / 2, away: Math.PI};

// Where an actor is at time t: his spot (and the seat or bed there), his walk, his pose, and the world positions the
// camera needs (computed with the same rotations the Man applies).
export const place = (a: Actor, k: number, set: SetDef, shot: LPShot, t: number, cast: Record<string, Design>, others: Placed[] = []): Placed => {
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
  const turn = FACING[a.facing ?? 'camera'];
  if (turn !== undefined && seat === null && !lying) ry = turn;
  // two people never on the same spot: the later one moves along the spot (along the couch, beside him)
  if (!MOVING.has(action) && others.some((o) => Math.hypot(o.root[0] - root[0], o.root[2] - root[2]) < 0.7)) {
    const side = others.length % 2 ? 1 : -1;
    root = [root[0] + Math.cos(ry) * 0.85 * side, root[1], root[2] - Math.sin(ry) * 0.85 * side];
  }
  if (action === 'sit' && seat === null) seat = 0.46; // a chair the set doesn't have: drawn under him
  // a spot that faces into the set (the counter, the mirror, a window) turns him round when the camera wants his face
  if ((a.facing ?? 'camera') === 'camera' && Math.cos(ry) < -0.5 && !lying && !MOVING.has(action) && FACE_CAMS.has(shot.camera)) ry += Math.PI;
  if (MOVING.has(action)) {
    const speed = SPEED[action] ?? 1;
    const dist = speed * shot.duration;
    let from = V([root[0], 0, root[2]]);
    let to: THREE.Vector3;
    if (a.to) {
      const b = spotOf(set, a.to);
      to = V([b.x, 0, b.z]);
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
    if (along >= len - 0.01) action = 'stand';
  }
  const ps = pose({action, t, dur: shot.duration, seat, k: k * 1.7 + (shot.seed ?? 0)});
  if (lying) ps.y = 0;
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
  const kind = cam === 'face' && lying ? 'face-top' : cam === 'top' && !lying && who.pose.y > 0.5 ? 'top' : cam;
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
      const d = distFor(1.8, 3.0, fov, aspect) * push;
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
      const fwd = new THREE.Vector3(Math.sin(who.ry), 0, Math.cos(who.ry));
      const right = new THREE.Vector3(fwd.z, 0, -fwd.x);
      // high over the shoulder, so a chair or a table behind him stays under the shot
      pos = H.clone().addScaledVector(fwd, -2.3 * push).addScaledVector(right, 0.75).add(new THREE.Vector3(0, 0.65, 0));
      look = H.clone().addScaledVector(fwd, 2.0).add(new THREE.Vector3(0, -0.75, 0));
      aperture = 0.45;
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
    case 'wide':
    default: {
      fov = aspect < 1 ? 46 : 38;
      pos = V(set.wide.pos);
      look = V(set.wide.look).lerp(who.body, 0.45);
      pos.lerp(look, 0.06 * p);
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
      <directionalLight position={eye.clone().add(new THREE.Vector3(0, 0.6, 0)).toArray()} target={tgt} color="#fff1e2" intensity={look.shade < 0.8 ? 0.55 : 0.25} />
      {look.lamp > 0 && set.lamp ? (
        <pointLight position={set.lamp} color="#ffb46b" intensity={look.lamp * 3.2} distance={9} decay={1.6} castShadow={false} />
      ) : null}
    </>
  );
};

const ShotScene: React.FC<{shot: LPShot; t: number; props: LowPolyProps; aspect: number}> = ({shot, t, props, aspect}) => {
  const set = SETS[shot.set] ?? SETS.void;
  const look = LOOKS[shot.light] ?? LOOKS.day;
  const placed: Placed[] = [];
  shot.actors.forEach((a, k) => placed.push(place(a, k, set, shot, t, props.cast, placed)));
  const who = placed[Math.min(placed.length - 1, Math.max(0, shot.focus ?? 0))];
  const plan = who
    ? camFor(shot.camera, who, placed, set, aspect, t, shot.duration, shot.seed ?? 1)
    : {pos: V(set.wide.pos), look: V(set.wide.look), up: new THREE.Vector3(0, 1, 0), fov: 40, focus: 5, aperture: 0.1};
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
      {placed.map((pl, i) => (
        <group key={i}>
          <Man design={pl.design} pose={pl.pose} face={face(pl.actor.expression, t, i + (shot.seed ?? 0))} root={pl.root} ry={pl.ry} hold={pl.hold} seed={pl.actor.who === 'hero' ? 7 : pl.seed} />
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
  return (
    <AbsoluteFill style={{background: '#000'}}>
      <ThreeCanvas width={width} height={height} shadows gl={{antialias: true}} camera={{fov: 34, near: 0.05, far: 400, position: [0, 1.5, 5]}}>
        <ShotScene shot={shot} t={local} props={props} aspect={width / height} />
      </ThreeCanvas>
      <AbsoluteFill style={{background: 'radial-gradient(ellipse at 50% 48%, rgba(0,0,0,0) 52%, rgba(0,0,0,0.42) 100%)'}} />
      <Grain frame={frame} />
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
