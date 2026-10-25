import React from 'react';
import {random} from 'remotion';
import type {Actor, Cast, Face, Pose, Prop, Tone} from './types';

// The bean people of the reference films (reelgen/sticky/ANALYSIS.md): a round head on a soft bean body, rubber-hose
// limbs with rounded ends, no clothes but one identity item, a face of two eyes, eyebrows and a small mouth (the
// eyebrows carry the feeling). Drawn in a frame with the feet at (0, 0), facing right; facing left mirrors it.
// Poses are procedural: every pose is a set of joint positions as a function of the time into the shot.

export const TONES: Record<Tone, string> = {
  cream: '#EDE5D3', grey: '#8E949C', peach: '#F1D2BC', tan: '#D8B28C', brown: '#A77A55', pale: '#F5F2EA',
};
const INK = '#2A2A31';
const LINE = 3.2;
const LIMB = 17;

type P = [number, number];
type Rig = {
  rot: number; // body rotation about the hips, degrees
  dx: number; dy: number; // body offset
  head: number; // head tilt, degrees
  hl: P; hr: P; // hands (body frame)
  fl: P; fr: P; // feet (world frame, relative to the actor's spot)
  kl?: P; kr?: P; // knees (bent legs)
  el?: P; er?: P; // elbows (bent arms)
  squash: number;
  jitter: P;
};

const SHOULDER_L: P = [-34, -172];
const SHOULDER_R: P = [34, -172];
const HIP_L: P = [-17, -96];
const HIP_R: P = [17, -96];

const lerp = (a: number, b: number, k: number) => a + (b - a) * k;
const ease = (k: number) => (k < 0 ? 0 : k > 1 ? 1 : k * k * (3 - 2 * k));

// Seat heights by set furniture (the pipeline puts a sitting actor on the set's own chair, bed or couch).
export const SEAT = {chair: -118, bed: -150, couch: -122, floor: -40};

export const rigFor = (pose: Pose, t: number, dur: number, seed: number, seat: number): Rig => {
  const base: Rig = {rot: 0, dx: 0, dy: 0, head: 0, hl: [-44, -96], hr: [44, -96], fl: [-20, 0], fr: [20, 0], squash: 1, jitter: [0, 0]};
  const sitDy = seat - HIP_L[1]; // raise the hips to the seat
  const sitting = (r: Partial<Rig>): Rig => ({...base, dy: sitDy, kl: [40, seat + 4], kr: [52, seat + 4], fl: [44, 0], fr: [58, 0],
    hl: [30, -110], hr: [46, -112], ...r});
  switch (pose) {
    case 'walk':
    case 'climb':
    case 'run': {
      const run = pose === 'run';
      const period = run ? 0.42 : 0.62;
      const ph = ((t + seed * 0.37) / period) * Math.PI * 2;
      const s = Math.sin(ph);
      const swing = run ? 34 : 24;
      const lift = run ? 20 : 11;
      return {...base, rot: run ? 9 : 2, dy: -Math.abs(Math.cos(ph)) * (run ? 9 : 4),
        fl: [-6 + s * swing, -Math.max(0, Math.sin(ph)) * lift], fr: [6 - s * swing, -Math.max(0, -Math.sin(ph)) * lift],
        kl: run ? [-2 + s * swing * 0.7 + 12, -52] : undefined, kr: run ? [2 - s * swing * 0.7 + 12, -52] : undefined,
        hl: [-30 - s * (run ? 36 : 26), run ? -128 : -100], hr: [30 + s * (run ? 36 : 26), run ? -128 : -100],
        el: run ? [-26 - s * 10, -134] : undefined, er: run ? [26 + s * 10, -134] : undefined};
    }
    case 'sit':
      return sitting({});
    case 'sit_bed':
      return sitting({hl: [26, seat - 6], hr: [48, seat - 6]});
    case 'type':
      return sitting({rot: 6, hl: [92, -150 + Math.sin(t * 22) * 3], hr: [112, -150 + Math.cos(t * 19) * 3], head: 6});
    case 'write':
      return sitting({rot: 8, hl: [90, -150], hr: [112 + Math.sin(t * 9) * 6, -148 + Math.cos(t * 13) * 3], head: 10});
    case 'guitar':
      return sitting({hl: [70, -150], hr: [30 + Math.sin(t * 9) * 6, -128], head: 6});
    case 'slump':
      return sitting({rot: 18, head: 18, hl: [36, seat + 30], hr: [52, seat + 30]});
    case 'lie':
    case 'sleep':
      // on the mattress (its top at `seat`), head to the left, the face turned back up toward the camera
      return {...base, rot: -90, dx: 0, dy: seat - 44 + 96, head: 72, hl: [-24, -118], hr: [20, -112], squash: 1};
    case 'curl':
      return {...base, dy: SEAT.floor - HIP_L[1], kl: [36, -150], kr: [44, -146], fl: [40, 0], fr: [52, 0],
        hl: [44, -132], hr: [56, -128], head: 22, rot: 10};
    case 'kneel':
      return {...base, dy: 44, kl: [10, 0], kr: [34, 0], fl: [-30, 0], fr: [-10, 0], hl: [40, -110], hr: [56, -112]};
    case 'shake': {
      const j = (random(`sh${seed}-${Math.floor(t * 30)}`) - 0.5) * 7;
      return {...sitting({rot: 6, hl: [30, -150], hr: [40, -146], head: 10}), jitter: [j, 0]};
    }
    case 'pushup': {
      const k = (Math.sin(((t + seed) / 0.9) * Math.PI * 2) + 1) / 2;
      return {...base, rot: 72 + k * 8, dy: -34 + k * 26, dx: -60, hl: [60, -40 - k * 10], hr: [70, -38 - k * 10],
        fl: [-140, 0], fr: [-128, 0], head: -40};
    }
    case 'punch': {
      const k = (Math.sin(((t + seed) / 0.36) * Math.PI * 2) + 1) / 2;
      return {...base, rot: 6, fl: [-26, 0], fr: [30, 0], hl: [40 + (1 - k) * 70, -160], hr: [40 + k * 70, -150]};
    }
    case 'reach': {
      const k = ease(Math.min(1, t / Math.max(0.6, dur * 0.5)));
      return {...base, rot: 8 * k, hr: [lerp(44, 200, k), lerp(-96, -150, k)], hl: [-30, -100]};
    }
    case 'phone':
      return {...base, head: 16, hl: [26, -150], hr: [36, -152]};
    case 'cheer': {
      const hop = Math.max(0, Math.sin(((t + seed) / 0.5) * Math.PI)) * 16;
      return {...base, dy: -hop, hl: [-56, -262], hr: [56, -262]};
    }
    case 'hug':
      return {...base, rot: 4, hl: [70, -150], hr: [86, -140]};
    case 'hold_out':
      return {...base, hl: [56, -140], hr: [72, -140]};
    case 'wave':
      return {...base, hr: [70 + Math.sin(t * 7) * 18, -250], hl: [-44, -96]};
    case 'fall': {
      const k = ease(Math.min(1, t / 0.5));
      return {...base, rot: -80 * k, dy: 0, hl: [-60, -160], hr: [60, -180]};
    }
    case 'think':
      return {...base, head: -6, hr: [22, -206], hl: [-20, -120]};
    default:
      return base;
  }
};

const limb = (a: P, b: P, bend?: P, curl = 0.18): string => {
  // a rubber hose from a to b: through `bend` when given, else a soft curve
  if (bend) return `M${a[0]},${a[1]} Q${bend[0] * 2 - (a[0] + b[0]) / 2},${bend[1] * 2 - (a[1] + b[1]) / 2} ${b[0]},${b[1]}`;
  const mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2;
  const dx = b[0] - a[0], dy = b[1] - a[1];
  return `M${a[0]},${a[1]} Q${mx - dy * curl},${my + dx * curl} ${b[0]},${b[1]}`;
};

const Hose: React.FC<{d: string; fill: string; w?: number}> = ({d, fill, w = LIMB}) => (
  <>
    <path d={d} stroke={INK} strokeWidth={w + LINE * 2} fill="none" strokeLinecap="round" />
    <path d={d} stroke={fill} strokeWidth={w} fill="none" strokeLinecap="round" />
  </>
);

// The head, the body and the face are drawn in the body frame (hips at 0,-96; the head centre at 0,-236).
const HEAD: P = [0, -236];
const HEAD_R = 60;

const BODY = 'M-44,-176 C-50,-130 -48,-100 -36,-86 C-20,-74 20,-74 36,-86 C48,-100 50,-130 44,-176 Z';

export const Bean: React.FC<{cast: Cast; actor: Actor; t: number; dur: number; seat: number; scale?: number; grey?: boolean}> = (p) => {
  const {cast, actor, t, dur, seat} = p;
  const seed = Array.from(cast.id).reduce((s, c) => s + c.charCodeAt(0), 0) % 97;
  const rig = rigFor(actor.pose, t, dur, seed, seat);
  if ((actor.pose === 'lie') && (actor.prop === 'phone' || actor.glow)) rig.hr = [96, -226]; // the phone held up over the face
  const fill = p.grey ? TONES.grey : TONES[cast.tone] ?? TONES.cream;
  const face: Face = actor.face2 && actor.faceAt !== undefined && t >= actor.faceAt ? actor.face2 : actor.face;
  const flip = actor.facing === 'left' ? -1 : 1;
  const k = (cast.kid ? 0.66 : 1) * (p.scale ?? 1);
  const seated = ['sit', 'sit_bed', 'type', 'write', 'guitar', 'slump', 'shake'].includes(actor.pose);
  // legs: hips (body frame) to feet (world frame)
  const toWorld = (q: P): P => {
    const r = (rig.rot * Math.PI) / 180;
    const x = q[0], y = q[1] - -96; // about the hips
    return [x * Math.cos(r) - y * Math.sin(r) + rig.dx, x * Math.sin(r) + y * Math.cos(r) - 96 + rig.dy];
  };
  const hipL = toWorld(HIP_L), hipR = toWorld(HIP_R);
  const lying = actor.pose === 'lie' || actor.pose === 'sleep';
  const legs = lying ? null : (
    <>
      <Hose d={limb(hipL, rig.fl, rig.kl, seated ? 0 : 0.08)} fill={fill} />
      <Hose d={limb(hipR, rig.fr, rig.kr, seated ? 0 : 0.08)} fill={fill} />
    </>
  );
  return (
    <g transform={`translate(${rig.jitter[0]},${rig.jitter[1]}) scale(${flip * k},${k})`}>
      {legs}
      <g transform={`translate(${rig.dx},${rig.dy}) rotate(${rig.rot},0,-96)`}>
        {lying ? (
          <>
            <Hose d={limb(HIP_L, [-14, 60])} fill={fill} />
            <Hose d={limb(HIP_R, [14, 64])} fill={fill} />
          </>
        ) : null}
        <Hose d={limb(SHOULDER_L, rig.hl, rig.el)} fill={fill} />
        <BodyAndHead fill={fill} rig={rig} cast={cast} face={face} actor={actor} t={t} seed={seed} />
        <Hose d={limb(SHOULDER_R, rig.hr, rig.er)} fill={fill} />
        <PropView prop={actor.prop && actor.prop !== 'none' ? actor.prop : (actor.pose === 'phone' || actor.pose === 'reach' ? 'phone' : actor.pose === 'guitar' ? 'guitar' : 'none')}
          at={actor.pose === 'reach' ? rig.hr : [(rig.hl[0] + rig.hr[0]) / 2, (rig.hl[1] + rig.hr[1]) / 2]} glow={!!actor.glow} />
      </g>
    </g>
  );
};

const BodyAndHead: React.FC<{fill: string; rig: Rig; cast: Cast; face: Face; actor: Actor; t: number; seed: number}> = ({fill, rig, cast, face, actor, t, seed}) => (
  <>
    <g>
      {cast.wear === 'hood' ? <path d="M-74,-226 C-80,-310 80,-310 74,-226 C70,-176 50,-166 0,-164 C-50,-166 -70,-176 -74,-226 Z" fill={cast.color} stroke={INK} strokeWidth={LINE} /> : null}
      {cast.wear === 'long' || cast.wear === 'ponytail' ? <HairBack cast={cast} /> : null}
      {/* outline layer, then the fill: the head and the body read as one bean */}
      <path d={BODY} fill={INK} stroke={INK} strokeWidth={LINE * 2} />
      <circle cx={HEAD[0]} cy={HEAD[1]} r={HEAD_R + LINE} fill={INK} />
      <path d={BODY} fill={fill} />
      <circle cx={HEAD[0]} cy={HEAD[1]} r={HEAD_R} fill={fill} />
      {cast.wear === 'hood' ? <path d="M-60,-178 C-36,-160 36,-160 60,-178 C64,-160 40,-148 0,-148 C-40,-148 -64,-160 -60,-178 Z" fill={cast.color} stroke={INK} strokeWidth={LINE} /> : null}
    </g>
    <g transform={`rotate(${rig.head},0,-180)`}>
      <FaceView face={face} t={t} seed={seed} tear={!!actor.tear} sweat={!!actor.sweat} glow={!!actor.glow} />
      <WearView cast={cast} wear={cast.wear} />
      {cast.extra ? <WearView cast={cast} wear={cast.extra} /> : null}
    </g>
  </>
);

// ---------- faces ----------

type Brow = [number, number]; // inner and outer height offsets
const FACES: Record<Face, {eye: 'dot' | 'line' | 'half' | 'wide' | 'happy' | 'closed'; brow: Brow | null; mouth: string; blush?: boolean; bags?: boolean}> = {
  neutral: {eye: 'dot', brow: [0, 0], mouth: 'M-8,-206 L8,-206'},
  tired: {eye: 'half', brow: [2, 2], mouth: 'M-9,-205 L9,-205', bags: true},
  numb: {eye: 'line', brow: null, mouth: 'M-9,-205 L9,-205'},
  sad: {eye: 'dot', brow: [-7, 3], mouth: 'M-11,-201 Q0,-210 11,-201'},
  cry: {eye: 'dot', brow: [-9, 4], mouth: 'M-12,-199 Q0,-212 12,-199'},
  worried: {eye: 'dot', brow: [-8, 2], mouth: 'M-10,-204 Q-5,-208 0,-204 Q5,-200 10,-204'},
  anxious: {eye: 'wide', brow: [-10, 0], mouth: 'M-12,-203 L-6,-208 L0,-203 L6,-208 L12,-203'},
  angry: {eye: 'dot', brow: [8, -4], mouth: 'M-11,-201 Q0,-209 11,-201'},
  determined: {eye: 'half', brow: [7, -3], mouth: 'M-10,-205 L10,-205'},
  happy: {eye: 'happy', brow: [-2, -2], mouth: 'M-14,-210 Q0,-192 14,-210'},
  smile: {eye: 'dot', brow: [-1, -1], mouth: 'M-11,-208 Q0,-198 11,-208'},
  shock: {eye: 'wide', brow: [-12, -10], mouth: 'M0,-212 m-7,0 a7,9 0 1,0 14,0 a7,9 0 1,0 -14,0'},
  embarrassed: {eye: 'dot', brow: [-6, 2], mouth: 'M-10,-205 Q-5,-201 0,-205 Q5,-209 10,-205', blush: true},
  smug: {eye: 'half', brow: [-4, 4], mouth: 'M-10,-206 Q4,-200 12,-210'},
};

const FaceView: React.FC<{face: Face; t: number; seed: number; tear: boolean; sweat: boolean; glow: boolean}> = ({face, t, seed, tear, sweat, glow}) => {
  const f = FACES[face] ?? FACES.neutral;
  const blink = ((t + seed * 0.11) % 3.4) < 0.12 && f.eye !== 'happy' && f.eye !== 'closed';
  const eyes = [-19, 21].map((x, i) => {
    const y = -240;
    if (blink || f.eye === 'closed') return <path key={i} d={`M${x - 7},${y} Q${x},${y + 4} ${x + 7},${y}`} stroke={INK} strokeWidth={3.4} fill="none" strokeLinecap="round" />;
    switch (f.eye) {
      case 'line': return <path key={i} d={`M${x - 8},${y} L${x + 8},${y}`} stroke={INK} strokeWidth={3.6} strokeLinecap="round" />;
      case 'half': return <g key={i}><circle cx={x} cy={y + 1} r={5.2} fill={INK} /><path d={`M${x - 9},${y - 3} L${x + 9},${y - 3}`} stroke={INK} strokeWidth={3.4} strokeLinecap="round" /></g>;
      case 'wide': return <g key={i}><circle cx={x} cy={y} r={11} fill="#fff" stroke={INK} strokeWidth={2.6} /><circle cx={x + 1} cy={y + 1} r={4.6} fill={INK} /></g>;
      case 'happy': return <path key={i} d={`M${x - 8},${y + 3} Q${x},${y - 7} ${x + 8},${y + 3}`} stroke={INK} strokeWidth={3.6} fill="none" strokeLinecap="round" />;
      default: return <ellipse key={i} cx={x} cy={y} rx={5.2} ry={6.2} fill={INK} />;
    }
  });
  const brows = f.brow ? [-1, 1].map((s) => {
    const x0 = s * 9, x1 = s * 29;
    const [inner, outer] = f.brow as Brow;
    return <path key={s} d={`M${x0},${-256 + inner} L${x1},${-256 + outer}`} stroke={INK} strokeWidth={3.6} strokeLinecap="round" />;
  }) : null;
  return (
    <g>
      {glow ? <circle cx={0} cy={-230} r={62} fill="url(#stPhoneGlow)" /> : null}
      {f.bags ? [-19, 21].map((x) => <path key={x} d={`M${x - 8},${-231} Q${x},${-226} ${x + 8},${-231}`} stroke="#8a7f8f" strokeWidth={2.2} fill="none" />) : null}
      {eyes}
      {brows}
      <path d={f.mouth} stroke={INK} strokeWidth={3.4} fill={face === 'shock' ? INK : 'none'} strokeLinecap="round" strokeLinejoin="round" />
      {f.blush ? [-30, 32].map((x) => <ellipse key={x} cx={x} cy={-218} rx={9} ry={5} fill="#E88A8A" opacity={0.55} />) : null}
      {tear || face === 'cry' ? <Tears t={t} /> : null}
      {sweat || face === 'anxious' ? <path d="M48,-262 q-7,12 0,16 q7,-4 0,-16" fill="#9BD3F5" stroke={INK} strokeWidth={1.6} /> : null}
    </g>
  );
};

const Tears: React.FC<{t: number}> = ({t}) => {
  const k = (t % 1.2) / 1.2;
  return (
    <g fill="#8FD0F6">
      <path d={`M-22,-232 q-4,${10 + k * 20} 0,${16 + k * 26} q4,-6 0,-${16 + k * 26}`} opacity={0.9} />
      <path d={`M24,-232 q4,${10 + k * 18} 0,${14 + k * 24} q-4,-6 0,-${14 + k * 24}`} opacity={0.9} />
    </g>
  );
};

// ---------- what they wear ----------

const HairBack: React.FC<{cast: Cast}> = ({cast}) => (
  cast.wear === 'ponytail'
    ? <path d="M-30,-282 C40,-300 96,-250 74,-196 C66,-176 56,-200 54,-214 C60,-250 30,-270 -20,-276 Z" fill={cast.color} stroke={INK} strokeWidth={LINE} />
    : <path d="M-66,-240 C-70,-310 70,-310 66,-240 L70,-170 C40,-160 -40,-160 -70,-170 Z" fill={cast.color} stroke={INK} strokeWidth={LINE} />
);

const WearView: React.FC<{cast: Cast; wear: Cast['wear']}> = ({cast, wear}) => {
  const c = cast.color;
  switch (wear) {
    case 'bob':
      return <path d="M-64,-236 C-70,-312 70,-312 64,-236 L64,-200 L46,-200 L44,-262 C20,-256 -20,-256 -44,-262 L-46,-200 L-64,-200 Z" fill={c} stroke={INK} strokeWidth={LINE} />;
    case 'long':
    case 'ponytail':
      return <path d="M-62,-244 C-66,-306 66,-306 62,-244 C40,-266 -20,-272 -62,-244 Z" fill={c} stroke={INK} strokeWidth={LINE} />;
    case 'short':
      return <path d="M-56,-262 C-50,-302 50,-302 56,-262 C40,-276 30,-268 18,-280 C8,-268 -10,-276 -20,-272 C-34,-282 -44,-268 -56,-262 Z" fill={c} stroke={INK} strokeWidth={LINE} />;
    case 'curly':
      return <g fill={c} stroke={INK} strokeWidth={LINE}>{[-44, -24, -2, 20, 42].map((x, i) => <circle key={i} cx={x} cy={-284 + Math.abs(x) * 0.3} r={18} />)}</g>;
    case 'bun':
      return <g fill={c} stroke={INK} strokeWidth={LINE}><circle cx={0} cy={-306} r={20} /><path d="M-60,-250 C-62,-306 62,-306 60,-250 C30,-270 -30,-270 -60,-250 Z" /></g>;
    case 'beanie':
      return <g stroke={INK} strokeWidth={LINE}><path d="M-60,-262 C-60,-320 60,-320 60,-262 Z" fill={c} /><rect x={-64} y={-274} width={128} height={20} rx={8} fill={c} /><circle cx={0} cy={-318} r={9} fill={c} /></g>;
    case 'cap':
      return <g stroke={INK} strokeWidth={LINE} fill={c}><path d="M-58,-262 C-58,-314 58,-314 58,-262 Z" /><path d="M30,-266 L100,-262 C100,-252 60,-252 30,-256 Z" /></g>;
    case 'headband':
      return <g stroke={INK} strokeWidth={2.4} fill={c}><path d="M-60,-268 C-30,-282 30,-282 60,-268 L60,-254 C30,-268 -30,-268 -60,-254 Z" /><path d="M-58,-262 L-92,-250 L-86,-240 Z" /><path d="M-58,-258 L-96,-232 L-86,-226 Z" /></g>;
    case 'hardhat':
      return <g stroke={INK} strokeWidth={LINE} fill={c}><path d="M-56,-266 C-56,-326 56,-326 56,-266 Z" /><rect x={-70} y={-270} width={140} height={12} rx={6} /></g>;
    case 'scarf':
      return <g stroke={INK} strokeWidth={LINE} fill={c}><path d="M-48,-184 C-20,-170 20,-170 48,-184 L50,-166 C20,-152 -20,-152 -50,-166 Z" /><path d="M24,-168 L40,-120 L24,-118 L14,-160 Z" /></g>;
    default:
      return null;
  }
};

// ---------- things in hand ----------

const PropView: React.FC<{prop: Prop; at: P; glow: boolean}> = ({prop, at, glow}) => {
  const [x, y] = at;
  switch (prop) {
    case 'phone':
      return (
        <g transform={`translate(${x},${y}) rotate(-12)`}>
          <rect x={-13} y={-24} width={26} height={44} rx={5} fill="#1C1D22" stroke={INK} strokeWidth={2} />
          <rect x={-10} y={-20} width={20} height={34} rx={3} fill={glow ? '#BFD8FF' : '#2E3340'} />
        </g>
      );
    case 'book':
      return <g transform={`translate(${x},${y})`}><rect x={-26} y={-20} width={52} height={36} rx={3} fill="#C24E4E" stroke={INK} strokeWidth={2} /><line x1={0} y1={-20} x2={0} y2={16} stroke={INK} strokeWidth={2} /></g>;
    case 'drawing':
    case 'note':
      return <g transform={`translate(${x},${y - 20})`}><rect x={-40} y={-30} width={80} height={60} fill={prop === 'note' ? '#F7E27A' : '#FBFBF7'} stroke={INK} strokeWidth={2} />
        {prop === 'drawing' ? <><circle cx={-22} cy={-14} r={7} fill="#F6C945" /><path d="M-10,18 L-10,0 L4,-10 L18,0 L18,18 Z" fill="#E8708A" /></> : null}</g>;
    case 'guitar':
      return <g transform={`translate(${x - 20},${y + 10}) rotate(-28)`}><ellipse cx={0} cy={0} rx={38} ry={30} fill="#D9822B" stroke={INK} strokeWidth={2.4} /><circle cx={4} cy={0} r={9} fill="#3a2a1a" /><rect x={30} y={-6} width={90} height={12} fill="#7A4A22" stroke={INK} strokeWidth={2} /></g>;
    case 'umbrella':
      return <g transform={`translate(${x},${y})`}><line x1={0} y1={0} x2={0} y2={-150} stroke={INK} strokeWidth={4} /><path d="M-96,-140 C-90,-220 90,-220 96,-140 C70,-152 40,-150 0,-140 C-40,-150 -70,-152 -96,-140 Z" fill="#F2C230" stroke={INK} strokeWidth={3} /></g>;
    case 'coffee':
    case 'cup':
      return <g transform={`translate(${x},${y})`}><path d="M-14,-26 L14,-26 L11,10 L-11,10 Z" fill="#F4F1EA" stroke={INK} strokeWidth={2} /><rect x={-15} y={-32} width={30} height={7} rx={3} fill="#6B4A36" /></g>;
    case 'ball':
      return <g transform={`translate(${x},${y - 6})`}><circle r={22} fill="#E8812E" stroke={INK} strokeWidth={2.4} /><path d="M-22,0 L22,0 M0,-22 L0,22" stroke={INK} strokeWidth={1.6} /></g>;
    case 'bag':
      return <g transform={`translate(${x},${y + 20})`}><rect x={-22} y={-18} width={44} height={40} rx={6} fill="#5A6B8C" stroke={INK} strokeWidth={2} /></g>;
    case 'gift':
      return <g transform={`translate(${x},${y})`}><rect x={-24} y={-24} width={48} height={40} fill="#E15A6E" stroke={INK} strokeWidth={2} /><rect x={-4} y={-24} width={8} height={40} fill="#F6D45A" /></g>;
    case 'laptop':
      return <g transform={`translate(${x},${y})`}><rect x={-46} y={-40} width={92} height={56} rx={4} fill="#2B2F3A" stroke={INK} strokeWidth={2} /><rect x={-40} y={-34} width={80} height={44} fill={glow ? '#9CC2FF' : '#3B4252'} /></g>;
    case 'pen':
      return <line x1={x} y1={y} x2={x + 18} y2={y - 26} stroke="#2F6FDB" strokeWidth={5} strokeLinecap="round" />;
    default:
      return null;
  }
};
