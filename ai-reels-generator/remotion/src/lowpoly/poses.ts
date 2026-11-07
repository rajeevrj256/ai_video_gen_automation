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
  shift?: [number, number]; // the whole body moved in his own frame (x right, z forward): a jump's drift, feet sliding back
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

// `steer`: the front wheels' turn of the vehicle he drives (his hands turn the wheel with it); `air`: off the ground
// after leaping from a vehicle (tucked, or spread in free fall once `fall` is set)
// `press`: how far his right foot is down on a pedal (0..1) and which (`pedal`): the cut-in to his foot before the car
// lurches or brakes
export type PoseIn = {action: Action; t: number; dur: number; seat: number | null; k: number; at?: number; moving?: boolean; steer?: number; air?: 'leap' | 'fall'; press?: number; pedal?: 'gas' | 'brake'};

// Walking speed in units a second (the editor moves the root along his path at this speed).
export const SPEED: Partial<Record<Action, number>> = {walk: 1.0, run: 2.6, jog: 1.7, dash: 16, flee: 2.8, carry: 0.8};

// A squat, 0 (standing) .. 1 (deep): thighs forward, knees back, the pelvis dropping by what the bend costs.
const squat = (p: Pose, d: number, wide = 0.25) => {
  const a = 1.0 * d;
  p.legL = L(-a, wide, 2 * a);
  p.legR = L(-a, wide, 2 * a);
  p.y = HIP - 0.52 * (1 - Math.cos(a));
  p.lean = 0.4 * d;
  return p;
};

const runLegs = (p: Pose, t: number, f: number, amp: number, k: number, knee = 1.4) => {
  const ph = t * f * PI + k;
  const sw = Math.sin(ph);
  p.legL = L(-amp * sw, 0.02, Math.max(0, Math.sin(ph + PI * 0.55)) * knee);
  p.legR = L(amp * sw, 0.02, Math.max(0, Math.sin(ph - PI * 0.45)) * knee);
  return sw;
};

export function pose({action, t, dur, seat, k, at, moving, steer = 0, air, press = 0, pedal = 'gas'}: PoseIn): Pose {
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
    // ---------------------------------------------------------------- action and fiction
    case 'lift':
    case 'catch':
    case 'throw': {
      // lift: a squat (to `at`), then the arms carry it overhead; catch: arms up, a dip as it lands at `at`;
      // throw: overhead, the arms snap forward at `at`
      const ev = at ?? (action === 'lift' ? 0.5 : 0.8);
      let up = 1;
      let dip = 0;
      if (action === 'lift') {
        up = ease((t - ev) / 0.9);
        dip = t < ev ? ease(t / Math.max(0.2, ev)) : 1 - up;
      } else if (action === 'catch') {
        const since = t - ev;
        dip = since > 0 ? Math.exp(-since * 3) * Math.min(1, since * 10) * 0.7 : 0.15;
      } else {
        up = t < ev ? 1 : 1 - ease((t - ev) / 0.25);
      }
      squat(p, 0.25 + 0.6 * dip, 0.3);
      p.lean = action === 'throw' && t > ev ? 0.35 : 0.08 * (1 - up) + 0.25 * dip;
      const arm = mix(-0.75, -2.95, up);
      p.armL = L(arm, 0.18 * up, mix(-0.3, -0.25, up));
      p.armR = L(arm, 0.18 * up, mix(-0.3, -0.25, up));
      if (action === 'throw' && t > ev) {
        p.armL = L(-1.35, 0.1, -0.1);
        p.armR = L(-1.35, 0.1, -0.1);
      }
      p.side = up > 0.9 && action !== 'throw' ? 0.012 * Math.sin(t * 31) : 0; // the strain
      p.head = [-0.35 * up, 0, 0];
      return p;
    }
    case 'push-stop': {
      const ev = at ?? 1.0;
      const hit = t > ev;
      p.legL = L(-0.75, 0.05, 1.0);
      p.legR = L(0.55, 0.05, 0.2);
      p.y = HIP - 0.1;
      p.lean = hit ? 0.42 + 0.04 * Math.exp(-(t - ev) * 4) : 0.3;
      const reach = hit ? -1.38 : -1.2;
      p.armL = L(reach, 0.14, hit ? -0.2 : -0.6);
      p.armR = L(reach, 0.14, hit ? -0.2 : -0.6);
      p.head = [-0.15, 0, 0];
      // driven back by the blow, the feet sliding, then held
      p.shift = [0, hit ? -1.1 * (1 - Math.exp(-(t - ev) * 3.5)) : 0];
      p.side = hit ? 0.015 * Math.sin(t * 29) : 0;
      return p;
    }
    case 'super-jump': {
      const go = at ?? 0.45;
      if (t < go) {
        squat(p, ease(t / go), 0.22);
        p.armL = L(0.7 * ease(t / go), 0.15, -0.2);
        p.armR = L(0.7 * ease(t / go), 0.15, -0.2);
        return p;
      }
      const tt = t - go;
      p.y = HIP + 11 * tt - 2.4 * tt * tt;
      p.legL = L(-0.9, 0.06, 1.5);
      p.legR = L(-0.6, 0.06, 1.2);
      p.armL = L(-2.7, 0.3, -0.2);
      p.armR = L(-2.7, 0.3, -0.2);
      p.lean = -0.1;
      p.head = [-0.4, 0, 0];
      p.shift = [0, 2.2 * tt];
      return p;
    }
    case 'land': {
      const hit = at ?? 0.45;
      if (t < hit) {
        const q = 1 - t / hit;
        p.y = HIP + 9 * q * q;
        p.legL = L(-0.5, 0.15, 0.7);
        p.legR = L(-0.3, 0.15, 0.5);
        p.armL = L(-0.2, 1.1, -0.2);
        p.armR = L(-0.2, 1.1, -0.2);
        p.head = [0.35, 0, 0];
        return p;
      }
      // the three-point landing: left foot forward, right knee down, right fist on the ground; the head comes up
      const after = t - hit;
      p.y = 0.4 + 0.05 * Math.exp(-after * 6);
      p.legL = L(-1.5, 0.12, 1.55);
      p.legR = L(0.35, 0.1, 1.55);
      p.lean = 0.6 - 0.25 * ease((after - 0.8) / 0.8);
      p.armR = L(-0.15, 0.05, 0);
      p.armL = L(0.5, 0.55, -0.3);
      p.head = [mix(0.3, -0.35, ease((after - 0.6) / 0.7)), 0, 0];
      return p;
    }
    case 'dash': {
      const sw = runLegs(p, t, 5.5, 0.95, k, 1.6);
      p.armL = L(0.9 * sw, 0.05, -1.4);
      p.armR = L(-0.9 * sw, 0.05, -1.4);
      p.y = HIP - 0.06;
      p.lean = 0.5;
      p.head = [-0.3, 0, 0];
      return p;
    }
    case 'punch': {
      const ev = at ?? 0.4;
      const q = t < ev ? 0 : t < ev + 0.12 ? ease((t - ev) / 0.12) : 1 - ease((t - ev - 0.35) / 0.3);
      p.legL = L(-0.4, 0.08, 0.35);
      p.legR = L(0.3, 0.08, 0.15);
      p.armL = L(-1.25, -0.15, -2.0);
      p.armR = L(mix(-1.2, -1.58, q), mix(-0.2, -0.05, q), mix(-2.1, 0, q));
      p.twist = -0.35 * q;
      p.lean = 0.12 + 0.15 * q;
      return p;
    }
    case 'crush':
      p.armR = L(-0.75, -0.28, -1.45);
      p.armL = L(-0.2, 0.05, -0.2);
      p.head = [0.38, 0, 0];
      p.side = 0.006 * Math.sin(t * 40);
      return p;
    case 'look-hands':
      if (seat !== null) sitting(p, s);
      p.armL = L(-0.55, -0.3, -1.35);
      p.armR = L(-0.55, -0.3, -1.35 + 0.08 * Math.sin(t * 2));
      p.head = [0.42, 0.05 * Math.sin(t * 0.8), 0];
      return p;
    case 'crouch':
      squat(p, 1, 0.22);
      p.lean = 0.5;
      p.armL = L(-0.6, 0.1, -0.4);
      p.armR = L(-0.6, 0.1, -0.4);
      p.head = [-0.15, 0, 0];
      return idle(p, t, k);
    case 'kneel':
      p.y = 0.42;
      p.legL = L(-1.5, 0.1, 1.5);
      p.legR = L(0.2, 0.1, 1.6);
      p.lean = 0.12;
      p.armL = L(-0.6, 0.05, -0.6);
      p.armR = L(-0.3, 0.1, -0.2);
      return idle(p, t, k);
    case 'carry': {
      if (moving) runLegs(p, t, 1.75, 0.4, k, 0.7);
      p.armL = L(-1.15, -0.05, -0.75);
      p.armR = L(-1.15, -0.05, -0.75);
      p.lean = -0.06;
      p.head = [0.15, 0, 0];
      return p;
    }
    case 'carried':
      p.rx = -PI / 2;
      p.y = 0;
      p.legL = L(-1.0, 0.05, 1.3);
      p.legR = L(-0.9, 0.05, 1.2);
      p.armL = L(-2.4, 0.2, -1.2);
      p.armR = L(-0.4, 0.1, -0.3);
      p.head = [-0.2, 0, 0];
      return p;
    case 'fall': {
      const q = ease(t / 0.45);
      p.rx = -PI / 2 * q;
      p.y = mix(HIP, 0.2, q);
      p.armL = L(-0.6 * (1 - q), 0.3 + 0.9 * q, -0.2);
      p.armR = L(-0.6 * (1 - q), 0.3 + 0.9 * q, -0.2);
      p.head = [q > 0.9 ? 0.05 : -0.2, 0.25 * q, 0];
      return p;
    }
    case 'flee': {
      runLegs(p, t, 2.7, 0.8, k, 1.3);
      const w = 0.35 * Math.sin(t * 9 + k);
      p.armL = L(-2.4 + w, 0.35, -0.4);
      p.armR = L(-2.4 - w, 0.35, -0.4);
      p.y = HIP - 0.03;
      p.lean = 0.2;
      p.head = [-0.1, 0.5 * Math.sin(t * 1.7 + k), 0];
      return p;
    }
    case 'cower':
      squat(p, 1, 0.2);
      p.lean = 0.65;
      p.armL = L(-2.45, -0.2, -1.9);
      p.armR = L(-2.45, -0.2, -1.9);
      p.head = [0.6, 0, 0];
      p.side = 0.008 * Math.sin(t * 25);
      return p;
    case 'help-up':
      p.legL = L(-0.6, 0.06, 0.8);
      p.legR = L(0.2, 0.06, 0.3);
      p.y = HIP - 0.08;
      p.lean = 0.55;
      p.armR = L(-1.0, 0, -0.1);
      p.armL = L(-0.45, 0.1, -0.7);
      p.head = [0.25, 0, 0];
      return p;
    case 'talk':
      if (seat !== null) sitting(p, s);
      p.armR = L(-0.55 + 0.2 * Math.sin(t * 2.6 + k), -0.05, -1.25);
      p.armL = L(-0.15, 0.08, -0.25);
      p.head = [0.04 * Math.sin(t * 3.1), 0.08 * Math.sin(t * 0.9 + k), 0];
      return idle(p, t, k);
    case 'gasp':
      p.armL = L(-1.25, -0.38, -2.15);
      p.armR = L(-1.25, -0.38, -2.15);
      p.lean = -0.1;
      p.head = [-0.1, 0, 0];
      return p;
    // ---------------------------------------------------------------- in and on vehicles
    case 'drive': {
      // at the wheel or the controls: seated low, both hands on the wheel, turning it as the wheels turn (one hand
      // rises as the other drops), leaning into the turns, eyes on the road
      sitting(p, s);
      const w = Math.max(-0.6, Math.min(0.6, steer * 1.6));
      p.legL = L(-1.45, 0.05, 0.3); // legs out long, as in a low sports car (feet inside its body)
      // the right foot over the accelerator, or moved across onto the brake, and pushed down
      const over = pedal === 'brake' ? ease(Math.min(1, press * 3)) : 0;
      p.legR = L(-1.45 + 0.09 * press, 0.05 - 0.37 * over, 0.3 - 0.22 * press);
      p.armL = L(-1.08 - 0.3 * w, 0.12, -0.62 + 0.15 * w);
      p.armR = L(-1.08 + 0.3 * w, 0.12, -0.62 - 0.15 * w);
      p.lean = 0.04;
      p.side = -0.08 * w;
      p.head = [0.03, -0.22 * w, -0.05 * w];
      return p;
    }
    case 'ride':
      // a passenger: seated, an arm along the door, the other hand on his knee, looking about
      sitting(p, s);
      p.legL = L(-1.45, 0.05, 0.3);
      p.legR = L(-1.45, 0.05, 0.3);
      p.armL = L(-0.45, 0.12, -0.9);
      p.armR = L(-0.2, 0.42, -0.5);
      p.head = [0.02, 0.25 * Math.sin(t * 0.45 + k), 0];
      return p;
    case 'brace': {
      // on top of something moving: feet wide, knees bent, leaning into the wind, arms out for balance, swaying
      squat(p, 0.42, 0.38);
      const sw = Math.sin(t * 2.3 + k);
      p.lean = 0.3 + 0.05 * Math.sin(t * 3.1 + k);
      p.side = 0.07 * sw;
      p.armL = L(-0.35, 1.25 + 0.15 * sw, -0.35);
      p.armR = L(-0.35, 1.25 - 0.15 * sw, -0.35);
      p.head = [-0.2, 0, -0.05 * sw];
      return p;
    }
    case 'jump-off': {
      // on the vehicle: braced, crouching deeper as the moment comes; then the leap (tucked) and, falling free, the
      // skydiver's spread (LowPoly moves him through the air)
      if (air === 'fall') return pose({action: 'skydive', t, dur, seat: null, k});
      if (air === 'leap') {
        p.legL = L(-1.1, 0.12, 1.5);
        p.legR = L(-0.7, 0.12, 1.2);
        p.armL = L(-2.4, 0.5, -0.3);
        p.armR = L(-2.4, 0.5, -0.3);
        p.lean = 0.25;
        p.head = [-0.25, 0, 0];
        return p;
      }
      const ev = at ?? dur * 0.4;
      const q = ease(1 - (ev - t) / 0.6);
      squat(p, 0.42 + 0.4 * q, 0.34);
      p.armL = L(mix(-0.35, 0.6, q), mix(1.2, 0.2, q), -0.3);
      p.armR = L(mix(-0.35, 0.6, q), mix(1.2, 0.2, q), -0.3);
      p.head = [-0.2, 0, 0];
      return p;
    }
    case 'skydive': {
      // falling free, face down, back arched: arms out and bent up, legs apart with the knees a little bent, the
      // wind shaking the limbs
      const fl = 0.06 * Math.sin(t * 13 + k);
      p.rx = PI / 2 - 0.12;
      p.y = HIP;
      p.armL = L(0.15 + fl, 1.45, -1.2);
      p.armR = L(0.15 - fl, 1.45, -1.2);
      p.legL = L(0.32 - fl, 0.32, 0.75);
      p.legR = L(0.32 + fl, 0.32, 0.75);
      p.lean = -0.18;
      p.head = [-0.55, 0.1 * Math.sin(t * 0.7 + k), 0];
      return p;
    }
    case 'stand':
    default:
      if (seat !== null && action !== 'stand') sitting(p, s);
      return idle(p, t, k);
  }
}

// The face for each feeling: eyelids (0 open .. 1 shut), brows (lift, tilt: + = inner ends up), eye size, the mouth.
export type Face = {lid: number; brow: number; tilt: number; eye: number; mouth: 'line' | 'o' | 'smile' | 'frown' | 'flat' | 'open'; look: [number, number]};

export function face(e: Expr, t: number, k: number, talking = false): Face {
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
    case 'scared':
      Object.assign(f, {brow: 0.04, tilt: 0.45, eye: 1.25, mouth: 'o', look: [0.02 * Math.sin(t * 2.3 + k), 0]});
      break;
    case 'angry':
      Object.assign(f, {lid: 0.22, brow: -0.025, tilt: -0.45, mouth: 'flat'});
      break;
    case 'amazed':
      Object.assign(f, {brow: 0.045, eye: 1.3, mouth: 'o', look: [0, 0.01]});
      break;
    case 'pained':
      Object.assign(f, {lid: 0.45, brow: 0.01, tilt: 0.4, mouth: 'flat'});
      break;
    default:
      break;
  }
  if (talking) f.mouth = Math.sin(t * 21 + k) > -0.2 ? 'open' : f.mouth === 'o' ? 'o' : 'line'; // the mouth moves with the words
  if (blink) f.lid = 1;
  return f;
}
