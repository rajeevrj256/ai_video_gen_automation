// Every action as joint angles at time t (seconds into the shot). Angles in radians, the man's own axes:
// he faces +z; a limb's z > 0 swings it outward, away from the body (each side mirrored);
// a thigh/arm at x = -PI/2 points forward; a knee at +x bends back; a head at +x looks down;
// a torso lean at +x bends forward. The root sits at the pelvis.
import type {Action, Expr} from './types';

export type Limb = {x: number; z: number; bend: number}; // swing forward/back, out to the side, elbow/knee
export type Pose = {
  rx: number; // the whole body: lying on the back = -PI/2, face down = +PI/2
  rz: number; // on his side = PI/2
  y: number; // pelvis height over his spot's floor or seat
  lean: number;
  twist: number;
  side: number;
  head: [number, number, number];
  legL: Limb;
  legR: Limb;
  armL: Limb;
  armR: Limb;
  hand: 'none' | 'right' | 'both'; // which hand holds the thing
};

export const HIP = 0.64; // pelvis over the floor when standing
const PI = Math.PI;
const L = (x = 0, z = 0, bend = 0): Limb => ({x, z, bend});

const base = (): Pose => ({
  rx: 0,
  rz: 0,
  y: HIP,
  lean: 0,
  twist: 0,
  side: 0,
  head: [0, 0, 0],
  legL: L(),
  legR: L(),
  armL: L(0, 0.06, -0.08),
  armR: L(0, 0.06, -0.08),
  hand: 'none',
});

const ease = (p: number) => (p <= 0 ? 0 : p >= 1 ? 1 : p * p * (3 - 2 * p));
const mix = (a: number, b: number, p: number) => a + (b - a) * p;

// Sitting on a seat whose top is `seat` high (the pelvis then sits just above it).
const sitting = (p: Pose, seat: number) => {
  p.y = seat + 0.1;
  p.legL = L(-1.5, 0.04, 1.5);
  p.legR = L(-1.5, 0.04, 1.5);
  p.lean = 0.05;
  p.armL = L(-0.55, 0.1, -0.75);
  p.armR = L(-0.55, 0.1, -0.75);
  return p;
};

const idle = (p: Pose, t: number, k: number) => {
  p.lean += 0.012 * Math.sin(t * 1.6 + k); // breathing
  p.head = [p.head[0] + 0.02 * Math.sin(t * 0.7 + k), p.head[1] + 0.05 * Math.sin(t * 0.4 + k * 2), p.head[2]];
  return p;
};

export type PoseIn = {action: Action; t: number; dur: number; seat: number | null; k: number};

// Walking speed in units a second (the editor moves the root along his path at this speed).
export const SPEED: Partial<Record<Action, number>> = {walk: 1.0, run: 2.6, jog: 1.7};

export function pose({action, t, dur, seat, k}: PoseIn): Pose {
  const p = base();
  const s = seat ?? 0.48; // a chair when nothing else is there
  switch (action) {
    case 'walk':
    case 'run':
    case 'jog': {
      const f = action === 'run' ? 2.7 : action === 'jog' ? 2.2 : 1.75;
      const amp = action === 'run' ? 0.8 : action === 'jog' ? 0.6 : 0.45;
      const ph = t * f * PI + k;
      const sw = Math.sin(ph);
      p.legL = L(-amp * sw, 0.02, Math.max(0, Math.sin(ph + PI * 0.55)) * (action === 'walk' ? 0.7 : 1.4));
      p.legR = L(amp * sw, 0.02, Math.max(0, Math.sin(ph - PI * 0.45)) * (action === 'walk' ? 0.7 : 1.4));
      const arm = action === 'walk' ? 0.38 : 0.75;
      const elbow = action === 'walk' ? -0.25 : -1.25;
      p.armL = L(arm * sw, 0.08, elbow);
      p.armR = L(-arm * sw, 0.08, elbow);
      p.y = HIP + (action === 'walk' ? 0.025 : 0.06) * Math.abs(Math.cos(ph)) - (action === 'walk' ? 0.01 : 0.04);
      p.lean = action === 'walk' ? 0.04 : 0.16;
      p.twist = 0.06 * sw;
      p.head = [0.04, 0, 0];
      return p;
    }
    case 'sit':
      sitting(p, s);
      return idle(p, t, k);
    case 'sit-floor':
      p.y = 0.13;
      p.legL = L(-0.75, 0.12, 1.9);
      p.legR = L(-0.75, 0.12, 1.9);
      p.armL = L(-0.9, -0.05, -0.5);
      p.armR = L(-0.9, -0.05, -0.5);
      p.lean = 0.12;
      return idle(p, t, k);
    case 'lie':
      p.rx = -PI / 2;
      p.armL = L(0, 0.12, 0);
      p.armR = L(0, 0.12, 0);
      p.head = [0, 0.08 * Math.sin(t * 0.35 + k), 0];
      p.lean = 0.008 * Math.sin(t * 1.4);
      return p;
    case 'lie-side':
      p.rz = PI / 2;
      p.legL = L(-0.35, 0, 0.5);
      p.legR = L(-0.5, 0, 0.7);
      p.armL = L(-1.4, 0, -1.2); // under the pillow
      p.armR = L(-0.6, 0, -0.4);
      p.head = [0.05, 0, -0.15];
      return p;
    case 'lie-phone':
      p.rx = -PI / 2;
      p.armL = L(-1.25, -0.1, -0.75);
      p.armR = L(-1.25, -0.1, -0.75);
      p.head = [0.12, 0, 0];
      p.hand = 'right';
      return p;
    case 'phone':
      if (seat !== null) sitting(p, s);
      p.armR = L(-0.5, -0.25, -1.55);
      p.armL = L(-0.35, -0.2, -1.35);
      p.head = [0.38, 0, 0];
      p.hand = 'right';
      return idle(p, t, k);
    case 'type': {
      sitting(p, s);
      const tap = 0.05 * Math.sin(t * 14 + k);
      p.armL = L(-0.95 + tap, 0.0, -0.75);
      p.armR = L(-0.95 - tap, 0.0, -0.75);
      p.head = [0.18, 0, 0];
      p.lean = 0.12;
      return p;
    }
    case 'read':
      if (seat !== null) sitting(p, s);
      p.armL = L(-0.75, -0.18, -1.0);
      p.armR = L(-0.75, -0.18, -1.0);
      p.head = [0.32, 0, 0];
      p.hand = 'both';
      return idle(p, t, k);
    case 'reach': {
      const q = ease(Math.min(1, t / 0.9)) * (1 - ease((t - dur + 0.8) / 0.8));
      if (seat !== null) sitting(p, s);
      p.armR = L(-1.1 * q, 0.9 * q, -0.15);
      p.side = -0.12 * q;
      p.head = [0.05, -0.4 * q, 0];
      return p;
    }
    case 'sit-up': {
      const q = ease(Math.min(1, t / Math.max(1, dur * 0.6)));
      p.rx = -PI / 2 * (1 - q);
      p.legL = L(-PI / 2 * q, 0.02, 0);
      p.legR = L(-PI / 2 * q, 0.02, 0);
      p.lean = 0.1 * q;
      p.armL = L(-0.3 * q, 0.15, -0.3);
      p.armR = L(-0.3 * q, 0.15, -0.3);
      p.head = [0.1 * q, 0, 0];
      return p;
    }
    case 'get-up': {
      const q = ease(Math.min(1, t / Math.max(0.8, Math.min(1.6, dur * 0.6))));
      sitting(p, s);
      p.y = mix(s + 0.1, HIP, q);
      p.legL = L(mix(-1.5, 0, q), 0.03, mix(1.5, 0, q));
      p.legR = L(mix(-1.5, 0, q), 0.03, mix(1.5, 0, q));
      p.lean = 0.05 + 0.45 * Math.sin(PI * q);
      p.armL = L(mix(-0.55, 0, q), 0.08, mix(-0.75, -0.08, q));
      p.armR = L(mix(-0.55, 0, q), 0.08, mix(-0.75, -0.08, q));
      return p;
    }
    case 'shoes': {
      sitting(p, s);
      const tug = 0.06 * Math.sin(t * 6 + k);
      p.lean = 0.7;
      p.legL = L(-1.5, 0.04, 1.75);
      p.armL = L(-0.35 + tug, 0.12, -0.2);
      p.armR = L(-0.35 - tug, 0.12, -0.2);
      p.head = [0.35, 0, 0];
      return p;
    }
    case 'head-in-hands':
    case 'cry': {
      if (seat !== null) sitting(p, s);
      const shake = action === 'cry' ? 0.03 * Math.sin(t * 11) : 0;
      p.lean = (seat !== null ? 0.45 : 0.2) + shake;
      p.head = [0.45, 0, 0];
      p.armL = L(-1.25, -0.22, -1.55);
      p.armR = L(-1.25, -0.22, -1.55);
      return p;
    }
    case 'slump':
      if (seat !== null) sitting(p, s);
      p.lean = 0.28;
      p.head = [0.45, 0, 0.05];
      p.armL = L(seat !== null ? -0.25 : 0, 0.02, -0.1);
      p.armR = L(seat !== null ? -0.25 : 0, 0.02, -0.1);
      return idle(p, t * 0.5, k);
    case 'stretch': {
      const q = Math.sin(PI * Math.min(1, t / Math.max(1.2, dur * 0.8)));
      if (seat !== null) sitting(p, s);
      p.armL = L(-2.9 * q, 0.35 * q, -0.2);
      p.armR = L(-2.9 * q, 0.35 * q, -0.2);
      p.lean = -0.12 * q;
      p.head = [-0.3 * q, 0, 0];
      return p;
    }
    case 'sigh': {
      if (seat !== null) sitting(p, s);
      const q = Math.sin(PI * Math.min(1, t / 1.8));
      p.lean = 0.05 + 0.12 * Math.max(0, Math.min(1, (t - 0.9) / 0.8));
      p.y += 0.03 * q;
      p.head = [0.32 * Math.min(1, t / 1.6), 0, 0];
      return p;
    }
    case 'nod':
      if (seat !== null) sitting(p, s);
      p.head = [0.18 * Math.max(0, Math.sin(t * 7)) * Math.max(0, 1 - t / 1.6), 0, 0];
      return idle(p, t, k);
    case 'shake-head':
      if (seat !== null) sitting(p, s);
      p.head = [0.1, 0.35 * Math.sin(t * 8) * Math.max(0, 1 - t / 1.4), 0];
      return idle(p, t, k);
    case 'shrug': {
      if (seat !== null) sitting(p, s);
      const q = Math.sin(PI * Math.min(1, t / 1.3));
      p.armL = L(-0.4 * q, 0.35 * q, -1.3 * q);
      p.armR = L(-0.4 * q, 0.35 * q, -1.3 * q);
      p.head = [0, 0, 0.18 * q];
      p.y += 0.02 * q;
      return p;
    }
    case 'think':
      if (seat !== null) sitting(p, s);
      p.armR = L(-1.1, -0.25, -2.15);
      p.armL = L(-0.5, -0.4, -1.4);
      p.head = [-0.06, 0.1, 0.1];
      return idle(p, t, k);
    case 'drink': {
      if (seat !== null) sitting(p, s);
      const q = ease(Math.min(1, ((t + k) % 3.4) / 0.8)) * (1 - ease((((t + k) % 3.4) - 2.0) / 0.8));
      p.armR = L(mix(-0.55, -0.9, q), -0.2 * q, mix(-1.3, -2.05, q));
      p.head = [mix(0.1, -0.2, q), 0, 0];
      p.hand = 'right';
      return p;
    }
    case 'eat': {
      sitting(p, s);
      const q = Math.max(0, Math.sin(t * 2.4 + k));
      p.armR = L(mix(-0.8, -1.0, q), -0.2 * q, mix(-0.9, -2.0, q));
      p.armL = L(-0.7, -0.1, -0.9);
      p.head = [0.2 - 0.12 * q, 0, 0];
      p.lean = 0.15;
      p.hand = 'right';
      return p;
    }
    case 'look-out':
      p.head = [-0.1, 0, 0];
      return idle(p, t, k);
    case 'wave': {
      const w = 0.35 * Math.sin(t * 7);
      p.armR = L(-0.3, 2.5 - w * 0.3, -0.5 + w);
      return idle(p, t, k);
    }
    case 'point':
      p.armR = L(-1.5, 0, 0);
      p.head = [0.05, 0, 0];
      return idle(p, t, k);
    case 'cheer': {
      const b = Math.abs(Math.sin(t * 5));
      p.armL = L(-2.85, 0.45, -0.25);
      p.armR = L(-2.85, 0.45, -0.25);
      p.y += 0.06 * b;
      p.head = [-0.25, 0, 0];
      return p;
    }
    case 'pushup': {
      const d = 0.5 + 0.5 * Math.cos(t * 2.6 + k);
      p.rx = PI / 2 - 0.22;
      p.y = 0.34 + 0.12 * d;
      p.armL = L(-PI / 2 + 0.22, 0.25, -0.9 * (1 - d));
      p.armR = L(-PI / 2 + 0.22, 0.25, -0.9 * (1 - d));
      p.head = [-0.35, 0, 0];
      return p;
    }
    case 'stand':
    default:
      if (seat !== null && action !== 'stand') sitting(p, s);
      return idle(p, t, k);
  }
}

// The face for each feeling: eyelids (0 open .. 1 shut), brows (lift, tilt: + = inner ends up), eye size, the mouth.
export type Face = {lid: number; brow: number; tilt: number; eye: number; mouth: 'line' | 'o' | 'smile' | 'frown' | 'flat'; look: [number, number]};

export function face(e: Expr, t: number, k: number): Face {
  const blinkAt = (t + k * 1.7) % 3.7;
  const blink = blinkAt < 0.12 ? 1 : 0;
  const lookX = 0.012 * Math.sin(t * 0.5 + k);
  const f: Face = {lid: 0, brow: 0, tilt: 0, eye: 1, mouth: 'line', look: [lookX, 0]};
  switch (e) {
    case 'tired':
      Object.assign(f, {lid: 0.45, brow: -0.01, tilt: 0.1});
      break;
    case 'sad':
      Object.assign(f, {lid: 0.25, brow: 0.0, tilt: 0.35, mouth: 'frown', look: [lookX, -0.012]});
      break;
    case 'worried':
      Object.assign(f, {brow: 0.015, tilt: 0.3, mouth: 'flat', look: [0.02 * Math.sin(t * 1.3), 0]});
      break;
    case 'surprised':
      Object.assign(f, {brow: 0.035, eye: 1.25, mouth: 'o'});
      break;
    case 'happy':
      Object.assign(f, {lid: 0.12, brow: 0.01, mouth: 'smile'});
      break;
    case 'determined':
      Object.assign(f, {lid: 0.15, brow: -0.015, tilt: -0.3, mouth: 'flat'});
      break;
    case 'annoyed':
      Object.assign(f, {lid: 0.38, brow: -0.02, tilt: -0.15, mouth: 'flat'});
      break;
    case 'asleep':
      Object.assign(f, {lid: 1, mouth: 'line'});
      return f;
    case 'blank':
      Object.assign(f, {lid: 0.08, look: [0, 0]});
      break;
    default:
      break;
  }
  if (blink) f.lid = 1;
  return f;
}
