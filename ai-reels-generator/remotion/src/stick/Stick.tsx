import React from 'react';
import {Easing, Html5Audio, Sequence, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {FONT, clamp, useFonts} from '../theme';
import {Layer} from '../Layer';
import type {Extra, Face, Pose, Screen, StickProps, StickScene} from './types';

// A meme-style comedy short with one original stick-figure character, drawn entirely in
// SVG: black lines on light grey, thick outlines, expressive face. The same drawing code
// makes every scene, so the character is identical from start to finish.

const INK = '#111111';
const PAPER = '#EFEFEF';
const LINE = 13;
const FLOOR = 1560;

type Pt = [number, number];
type Skeleton = {
  head: Pt; tilt: number; neck: Pt; hip: Pt;
  lElbow: Pt; lHand: Pt; rElbow: Pt; rHand: Pt;
  lKnee: Pt; lFoot: Pt; rKnee: Pt; rFoot: Pt;
  phone: {x: number; y: number; rot: number} | null;
};

const POSES: Record<Pose, Skeleton> = {
  sit: {
    head: [540, 880], tilt: 0, neck: [540, 992], hip: [540, 1240],
    lElbow: [425, 1115], lHand: [500, 1055], rElbow: [655, 1115], rHand: [582, 1055],
    lKnee: [470, 1330], lFoot: [452, FLOOR - 8], rKnee: [610, 1330], rFoot: [628, FLOOR - 8],
    phone: {x: 541, y: 1030, rot: 0},
  },
  lean: {
    head: [440, 900], tilt: -14, neck: [478, 1012], hip: [540, 1240],
    lElbow: [352, 940], lHand: [400, 848], rElbow: [630, 1085], rHand: [668, 995],
    lKnee: [470, 1330], lFoot: [452, FLOOR - 8], rKnee: [650, 1300], rFoot: [705, FLOOR - 10],
    phone: {x: 672, y: 960, rot: 12},
  },
  upright: {
    head: [540, 845], tilt: 0, neck: [540, 958], hip: [540, 1240],
    lElbow: [418, 1095], lHand: [503, 1035], rElbow: [662, 1095], rHand: [577, 1035],
    lKnee: [470, 1330], lFoot: [452, FLOOR - 8], rKnee: [610, 1330], rFoot: [628, FLOOR - 8],
    phone: {x: 540, y: 1012, rot: 0},
  },
  slump: {
    head: [498, 988], tilt: -20, neck: [526, 1088], hip: [540, 1245],
    lElbow: [468, 1172], lHand: [428, 1256], rElbow: [652, 1206], rHand: [652, 1136],
    lKnee: [470, 1330], lFoot: [452, FLOOR - 8], rKnee: [610, 1330], rFoot: [628, FLOOR - 8],
    phone: {x: 660, y: 1112, rot: 8},
  },
  lying: {
    head: [262, 1452], tilt: -78, neck: [376, 1472], hip: [650, 1482],
    lElbow: [420, 1382], lHand: [468, 1318], rElbow: [420, 1540], rHand: [330, 1552],
    lKnee: [770, 1452], lFoot: [890, 1484], rKnee: [780, 1512], rFoot: [902, 1548],
    phone: {x: 575, y: 1540, rot: 90},
  },
};

export const Stick: React.FC<StickProps> = ({scenes, outro, outroSeconds, sfx}) => {
  useFonts();
  const {fps} = useVideoConfig();
  let t = 0;
  const starts = scenes.map((s) => {
    const at = t;
    t += s.seconds;
    return at;
  });
  const f = (s: number) => Math.round(s * fps);
  return (
    <Layer name="stick" style={{backgroundColor: PAPER, fontFamily: FONT}}>
      {scenes.map((s, i) => (
        <Sequence key={i} name={`scene ${i + 1} (${s.pose}, ${s.face})`} from={f(starts[i])} durationInFrames={f(s.seconds)}>
          <SceneView scene={s} frames={f(s.seconds)} />
        </Sequence>
      ))}
      <Sequence name="outro" from={f(t)} durationInFrames={f(outroSeconds)}>
        <Outro text={outro} />
      </Sequence>
      {sfx
        ? scenes.map((s, i) => (
            <React.Fragment key={`s${i}`}>
              <Sequence name={`sfx cut ${i + 1}`} from={Math.max(0, f(starts[i]) - 2)} durationInFrames={f(0.8)}>
                <Html5Audio src={staticFile(i === 0 ? sfx.pop : sfx.whoosh)} volume={0.3} />
              </Sequence>
              {s.extras.includes('shake') ? (
                <Sequence name={`sfx impact ${i + 1}`} from={f(starts[i]) + 4} durationInFrames={f(1)}>
                  <Html5Audio src={staticFile(sfx.impact)} volume={0.5} />
                </Sequence>
              ) : null}
              {s.extras.includes('soul') ? (
                <Sequence name={`sfx sad ${i + 1}`} from={f(starts[i]) + 8} durationInFrames={f(2.5)}>
                  <Html5Audio src={staticFile(sfx.sad)} volume={0.45} />
                </Sequence>
              ) : null}
              {s.extras.includes('plus-ones')
                ? [0.5, 1.1, 1.7].map((d) => (
                    <Sequence key={d} name={`sfx pop +1`} from={f(starts[i] + d)} durationInFrames={f(0.4)}>
                      <Html5Audio src={staticFile(sfx.pop)} volume={0.25} />
                    </Sequence>
                  ))
                : null}
            </React.Fragment>
          ))
        : null}
    </Layer>
  );
};

// ---------- one scene ----------

const SceneView: React.FC<{scene: StickScene; frames: number}> = ({scene, frames}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const sk = POSES[scene.pose];
  const has = (e: Extra) => scene.extras.includes(e);
  const enter = spring({frame, fps, config: {damping: 11, mass: 0.6}});
  const bob = scene.pose === 'lying' ? 0 : Math.sin(frame / 7) * (scene.face === 'hungry' ? 7 : 2.5);
  const shake = has('shake') && frame < 24 ? Math.sin(frame * 2.9) * (24 - frame) * 1.4 : 0;
  const zoom = has('zoom') ? interpolate(frame, [4, 30], [1, 1.14], {...clamp, easing: Easing.out(Easing.cubic)}) : 1;
  const focus = sk.phone ?? {x: 540, y: 1000};
  const tap = has('tap') ? Math.max(0, Math.sin((frame / fps) * Math.PI * 3.3)) : 0; // finger jabs, ~1.6 per second
  return (
    <Layer name="scene">
      <svg width={1080} height={1920} viewBox="0 0 1080 1920" style={{position: 'absolute', inset: 0}}>
        <g transform={`translate(${focus.x} ${focus.y}) scale(${zoom}) translate(${-focus.x} ${-focus.y})`}>
          <Room />
          {has('wallet') ? <Wallet x={scene.pose === 'lying' ? 960 : 300} y={scene.pose === 'lying' ? FLOOR - 4 : 1250} frame={frame} fps={fps} /> : null}
          <g transform={`translate(${shake} ${bob + (1 - enter) * 40})`}>
            <Figure sk={sk} face={scene.face} frame={frame} tap={tap} screen={scene.screen} amount={scene.amount} />
            {has('drool') ? <Drool sk={sk} frame={frame} /> : null}
            {has('sweat') ? <Sweat sk={sk} frame={frame} /> : null}
            {has('alarm') ? <Alarm sk={sk} frame={frame} fps={fps} /> : null}
            {has('soul') ? <Soul sk={sk} frame={frame} /> : null}
          </g>
          {has('thought-food') ? <Thought frame={frame} fps={fps} /> : null}
          {has('plus-ones') && sk.phone ? <PlusOnes x={sk.phone.x} y={sk.phone.y} frame={frame} fps={fps} /> : null}
        </g>
        {scene.screen !== 'none' && sk.phone ? (
          <PhoneBubble screen={scene.screen} amount={scene.amount} from={sk.phone} frame={frame} fps={fps} tap={tap} />
        ) : null}
      </svg>
      <Caption text={scene.caption} frames={frames} />
    </Layer>
  );
};

// ---------- the room ----------

const Room: React.FC = () => (
  <g stroke={INK} strokeWidth={9} fill="none" strokeLinecap="round" strokeLinejoin="round">
    <line x1={0} y1={FLOOR} x2={1080} y2={FLOOR} />
    {/* window with a moon: it's night */}
    <rect x={120} y={480} width={280} height={290} rx={10} fill="#FFFFFF" />
    <line x1={260} y1={480} x2={260} y2={770} />
    <line x1={120} y1={625} x2={400} y2={625} />
    <path d="M 335 530 a 32 32 0 1 0 22 52 a 26 26 0 1 1 -22 -52 Z" fill={INK} stroke="none" />
    {/* bed */}
    <rect x={140} y={1250} width={800} height={80} rx={14} fill="#FFFFFF" />
    <line x1={170} y1={1330} x2={170} y2={FLOOR} />
    <line x1={910} y1={1330} x2={910} y2={FLOOR} />
    <rect x={140} y={1080} width={46} height={170} rx={12} fill="#FFFFFF" />
    <path d="M 196 1250 q 18 -70 110 -64 q 60 6 64 64" fill="#FFFFFF" />
  </g>
);

// ---------- the character ----------

const Figure: React.FC<{sk: Skeleton; face: Face; frame: number; tap: number; screen: Screen; amount: string}> = ({sk, face, frame, tap, screen, amount}) => {
  const rHand: Pt = [sk.rHand[0] - tap * 26, sk.rHand[1] - tap * 18];
  const limb = (a: Pt, b: Pt, c: Pt) => `M ${a[0]} ${a[1]} Q ${b[0]} ${b[1]} ${c[0]} ${c[1]}`;
  return (
    <g stroke={INK} strokeWidth={LINE} fill="none" strokeLinecap="round" strokeLinejoin="round">
      {/* legs, body, arms: slightly curved lines read as drawn by hand */}
      <path d={limb(sk.hip, sk.lKnee, sk.lFoot)} />
      <path d={limb(sk.hip, sk.rKnee, sk.rFoot)} />
      <line x1={sk.hip[0]} y1={sk.hip[1]} x2={sk.neck[0]} y2={sk.neck[1]} />
      {sk.phone ? <Phone {...sk.phone} screen={screen} amount={amount} /> : null}
      <path d={limb(sk.neck, sk.lElbow, sk.lHand)} />
      <path d={limb(sk.neck, sk.rElbow, rHand)} />
      <g transform={`translate(${sk.head[0]} ${sk.head[1]}) rotate(${sk.tilt})`}>
        <circle r={105} fill="#FFFFFF" />
        <path d="M 4 -104 Q 12 -152 50 -142" strokeWidth={10} />
        <FaceView face={face} frame={frame} />
      </g>
    </g>
  );
};

const Phone: React.FC<{x: number; y: number; rot: number; screen: Screen; amount: string}> = ({x, y, rot}) => (
  <g transform={`translate(${x} ${y}) rotate(${rot})`}>
    <rect x={-44} y={-78} width={88} height={156} rx={16} fill={INK} strokeWidth={6} />
    <rect x={-32} y={-62} width={64} height={116} rx={6} fill="#FFFFFF" stroke="none" opacity={0.9} />
  </g>
);

const FaceView: React.FC<{face: Face; frame: number}> = ({face, frame}) => {
  const blink = frame % 75 > 71 ? 0.12 : 1; // a quick blink every 2.5 s
  const dot = (x: number, r = 15) => <ellipse cx={x} cy={-12} rx={r} ry={r * blink} fill={INK} stroke="none" />;
  switch (face) {
    case 'hungry':
      return (
        <g strokeWidth={9}>
          <circle cx={-38} cy={-14} r={21} fill={INK} stroke="none" />
          <circle cx={38} cy={-14} r={21} fill={INK} stroke="none" />
          <circle cx={-31} cy={-21} r={7} fill="#FFFFFF" stroke="none" />
          <circle cx={45} cy={-21} r={7} fill="#FFFFFF" stroke="none" />
          <path d="M -58 -52 q 20 -16 40 -4 M 18 -56 q 20 -12 40 4" />
          <path d="M -44 26 Q 0 92 44 26 Z" fill={INK} />
          <path d="M -16 58 q 16 -14 32 0" stroke="#FFFFFF" strokeWidth={7} />
        </g>
      );
    case 'happy':
      return (
        <g strokeWidth={9}>
          <path d="M -58 -8 Q -38 -34 -18 -8 M 18 -8 Q 38 -34 58 -8" />
          <path d="M -48 26 Q 0 80 48 26" />
          <ellipse cx={-62} cy={22} rx={14} ry={8} fill={INK} opacity={0.15} stroke="none" />
          <ellipse cx={62} cy={22} rx={14} ry={8} fill={INK} opacity={0.15} stroke="none" />
        </g>
      );
    case 'mischief':
      return (
        <g strokeWidth={9}>
          <path d="M -56 -10 L -22 -10" />
          {dot(38, 15)}
          <path d="M -58 -40 L -20 -34 M 20 -58 Q 40 -72 60 -54" />
          <path d="M -30 42 Q 14 52 48 18" />
        </g>
      );
    case 'shock':
      return (
        <g strokeWidth={8}>
          <circle cx={-38} cy={-14} r={28} fill="#FFFFFF" />
          <circle cx={38} cy={-14} r={28} fill="#FFFFFF" />
          <circle cx={-38} cy={-14} r={6} fill={INK} stroke="none" />
          <circle cx={38} cy={-14} r={6} fill={INK} stroke="none" />
          <path d="M -64 -60 q 24 -18 46 -6 M 18 -66 q 24 -12 46 6" />
          <ellipse cx={0} cy={50} rx={18} ry={26} fill={INK} />
        </g>
      );
    case 'terrified':
      return (
        <g strokeWidth={8}>
          <circle cx={-38} cy={-12} r={24} fill="#FFFFFF" />
          <circle cx={38} cy={-12} r={24} fill="#FFFFFF" />
          <circle cx={-38} cy={-2} r={7} fill={INK} stroke="none" />
          <circle cx={38} cy={-2} r={7} fill={INK} stroke="none" />
          <path d="M -60 -44 L -20 -54 M 20 -54 L 60 -44" />
          <path d="M -42 50 q 10 -14 21 0 t 21 0 t 21 0 t 21 0" />
        </g>
      );
    case 'dead':
      return (
        <g strokeWidth={9}>
          <path d="M -54 -28 l 32 32 M -22 -28 l -32 32 M 22 -28 l 32 32 M 54 -28 l -32 32" />
          <path d="M -34 46 L 34 46" />
          <path d="M 8 46 q 6 26 22 14" fill="#FFFFFF" strokeWidth={7} />
        </g>
      );
  }
};

// ---------- extras ----------

const headPoint = (sk: Skeleton, dx: number, dy: number): Pt => {
  const a = (sk.tilt * Math.PI) / 180;
  return [sk.head[0] + dx * Math.cos(a) - dy * Math.sin(a), sk.head[1] + dx * Math.sin(a) + dy * Math.cos(a)];
};

const Drool: React.FC<{sk: Skeleton; frame: number}> = ({sk, frame}) => {
  const [x, y] = headPoint(sk, 30, 62);
  const p = (frame % 40) / 40;
  return <path d={`M ${x} ${y} q 8 ${20 + p * 60} 0 ${24 + p * 70} q -8 -6 0 -${24 + p * 70}`} fill="#FFFFFF" stroke={INK} strokeWidth={6} opacity={1 - p * 0.3} />;
};

const Sweat: React.FC<{sk: Skeleton; frame: number}> = ({sk, frame}) => {
  const p = (frame % 36) / 36;
  const [x, y] = headPoint(sk, 104, -40 + p * 80);
  return <path d={`M ${x} ${y} q 16 26 0 38 q -16 -12 0 -38 Z`} fill="#FFFFFF" stroke={INK} strokeWidth={6} opacity={1 - p} />;
};

const Alarm: React.FC<{sk: Skeleton; frame: number; fps: number}> = ({sk, frame, fps}) => {
  const e = spring({frame: frame - 3, fps, config: {damping: 7, mass: 0.4}});
  const [x, y] = headPoint(sk, 150, -120);
  return (
    <text x={x} y={y} fontSize={130} fontWeight={900} fill={INK} stroke="none" transform={`rotate(12 ${x} ${y})`} opacity={Math.min(1, e)} style={{fontFamily: FONT}}>
      !!
    </text>
  );
};

const Soul: React.FC<{sk: Skeleton; frame: number}> = ({sk, frame}) => {
  const rise = interpolate(frame, [10, 90], [0, 300], clamp);
  const x = (sk.head[0] + sk.hip[0]) / 2 + Math.sin(frame / 9) * 20;
  const y = sk.hip[1] - 60 - rise;
  return (
    <g opacity={interpolate(frame, [10, 24], [0, 0.7], clamp)} stroke={INK} strokeWidth={9} fill="#FFFFFF" strokeDasharray="16 12">
      <circle cx={x} cy={y - 90} r={52} />
      <path d={`M ${x - 44} ${y - 50} Q ${x - 60} ${y + 60} ${x - 20} ${y + 70} Q ${x} ${y + 40} ${x + 20} ${y + 70} Q ${x + 60} ${y + 60} ${x + 44} ${y - 50}`} />
    </g>
  );
};

const Wallet: React.FC<{x: number; y: number; frame: number; fps: number}> = ({x, y, frame, fps}) => {
  const open = spring({frame: frame - 12, fps, config: {damping: 12}});
  const mothT = Math.max(0, frame - 24);
  const mx = x + mothT * 3 + Math.sin(mothT / 4) * 18;
  const my = y - 50 - mothT * 4;
  return (
    <g stroke={INK} strokeWidth={8} fill="#FFFFFF" strokeLinejoin="round">
      <rect x={x - 70} y={y - 70} width={140} height={70} rx={10} />
      <path d={`M ${x - 70} ${y - 70} L ${x - 70 + 140 * (1 - open * 0.15)} ${y - 70 - 46 * open} L ${x + 70} ${y - 70}`} />
      {mothT > 0 ? (
        <g transform={`translate(${mx} ${my})`}>
          <path d={`M 0 0 q -22 ${-18 * Math.abs(Math.sin(mothT / 2))} -30 6 q 14 6 30 -6 q 22 ${-18 * Math.abs(Math.sin(mothT / 2))} 30 6 q -14 6 -30 -6`} strokeWidth={5} />
        </g>
      ) : null}
    </g>
  );
};

const Thought: React.FC<{frame: number; fps: number}> = ({frame, fps}) => {
  const e = spring({frame: frame - 6, fps, config: {damping: 10, mass: 0.6}});
  const float = Math.sin(frame / 12) * 8;
  return (
    <g transform={`translate(0 ${float})`} opacity={Math.min(1, e)} stroke={INK} strokeWidth={8} fill="#FFFFFF">
      <circle cx={445} cy={760} r={12} />
      <circle cx={405} cy={715} r={20} />
      <path d="M 180 690 q -40 -60 20 -90 q 10 -70 90 -56 q 50 -50 110 0 q 70 -10 64 60 q 50 40 0 90 q -10 60 -90 44 q -50 40 -110 0 q -80 20 -84 -48 Z" />
      <Burger x={300} y={620} s={0.9 + 0.1 * e} />
    </g>
  );
};

const Burger: React.FC<{x: number; y: number; s?: number}> = ({x, y, s = 1}) => (
  <g transform={`translate(${x} ${y}) scale(${s})`} stroke={INK} strokeWidth={7} fill="#FFFFFF" strokeLinejoin="round">
    <path d="M -62 -8 Q -62 -60 0 -62 Q 62 -60 62 -8 Z" />
    <path d="M -66 4 q 11 10 22 0 q 11 10 22 0 q 11 10 22 0 q 11 10 22 0 q 11 10 22 0 q 11 10 22 0" fill="none" />
    <rect x={-64} y={16} width={128} height={20} rx={8} fill={INK} />
    <path d="M -62 44 L 62 44 Q 60 70 0 70 Q -60 70 -62 44 Z" />
    <circle cx={-20} cy={-36} r={3} fill={INK} /><circle cx={12} cy={-44} r={3} fill={INK} /><circle cx={30} cy={-28} r={3} fill={INK} />
  </g>
);

const PlusOnes: React.FC<{x: number; y: number; frame: number; fps: number}> = ({x, y, frame, fps}) => (
  <>
    {[0.5, 1.1, 1.7].map((d, i) => {
      const t = frame - d * fps;
      if (t < 0 || t > 30) return null;
      return (
        <text key={i} x={x - 330 + i * 40} y={y - 40 - t * 4} fontSize={70} fontWeight={900} fill={INK} opacity={interpolate(t, [0, 6, 24, 30], [0, 1, 1, 0])} style={{fontFamily: FONT}}>
          +1
        </text>
      );
    })}
  </>
);

// ---------- the zoomed phone screen ----------

const BX = 710;
const BY = 470;
const BW = 320;
const BH = 520;

const PhoneBubble: React.FC<{screen: Screen; amount: string; from: {x: number; y: number}; frame: number; fps: number; tap: number}> = ({screen, amount, from, frame, fps, tap}) => {
  const e = spring({frame: frame - 5, fps, config: {damping: 12, mass: 0.6}});
  const tx = Math.min(from.x + 40, BX + 40);
  return (
    <g opacity={Math.min(1, e)} transform={`translate(${BX + BW / 2} ${BY + BH / 2}) scale(${0.7 + 0.3 * e}) translate(${-(BX + BW / 2)} ${-(BY + BH / 2)})`}>
      <path d={`M ${BX + 30} ${BY + BH - 30} L ${tx} ${from.y - 60} L ${BX + 110} ${BY + BH - 10} Z`} fill="#FFFFFF" stroke={INK} strokeWidth={8} strokeLinejoin="round" />
      <rect x={BX} y={BY} width={BW} height={BH} rx={40} fill={INK} />
      <rect x={BX + 16} y={BY + 40} width={BW - 32} height={BH - 80} rx={16} fill="#FFFFFF" />
      <g transform={`translate(${BX + 16} ${BY + 40})`} style={{fontFamily: FONT}}>
        <ScreenContent screen={screen} amount={amount} frame={frame} fps={fps} tap={tap} w={BW - 32} h={BH - 80} />
      </g>
    </g>
  );
};

const Row: React.FC<{y: number; name: string; price: string; icon: React.ReactNode; pressed?: boolean}> = ({y, name, price, icon, pressed}) => (
  <g transform={`translate(0 ${y})`}>
    <g transform="translate(46 0) scale(0.42)">{icon}</g>
    <text x={92} y={-4} fontSize={26} fontWeight={800} fill={INK}>{name}</text>
    <text x={92} y={26} fontSize={22} fontWeight={800} fill="#777">{price}</text>
    <rect x={216} y={-24} width={50} height={46} rx={12} fill={pressed ? INK : '#FFFFFF'} stroke={INK} strokeWidth={4} />
    <text x={241} y={11} fontSize={34} fontWeight={900} fill={pressed ? '#FFFFFF' : INK} textAnchor="middle">+</text>
  </g>
);

const Pizza = (
  <g stroke={INK} strokeWidth={9} fill="#FFFFFF" strokeLinejoin="round">
    <path d="M -60 -50 L 60 -50 L 0 70 Z" />
    <path d="M -60 -50 Q 0 -80 60 -50" />
    <circle cx={-8} cy={-18} r={9} fill={INK} /><circle cx={18} cy={4} r={9} fill={INK} /><circle cx={-4} cy={30} r={8} fill={INK} />
  </g>
);
const Fries = (
  <g stroke={INK} strokeWidth={9} fill="#FFFFFF" strokeLinejoin="round">
    <path d="M -40 -70 L -32 0 M -12 -80 L -8 0 M 14 -76 L 10 0 M 38 -68 L 30 0" />
    <path d="M -52 -10 L 52 -10 L 40 70 L -40 70 Z" />
  </g>
);

const ScreenContent: React.FC<{screen: Screen; amount: string; frame: number; fps: number; tap: number; w: number; h: number}> = ({screen, amount, frame, fps, tap, w, h}) => {
  const header = (title: string) => (
    <>
      <rect x={0} y={0} width={w} height={64} fill={INK} />
      <text x={w / 2} y={43} fontSize={28} fontWeight={900} fill="#FFFFFF" textAnchor="middle">{title}</text>
    </>
  );
  const pop = spring({frame: frame - 10, fps, config: {damping: 8, mass: 0.5}});
  switch (screen) {
    case 'menu':
    case 'add':
      return (
        <>
          {header(screen === 'menu' ? 'Menu' : 'Cart: 6 items')}
          <Row y={130} name="Burger" price="₹249" icon={<Burger x={0} y={0} />} />
          <Row y={240} name="Pizza" price="₹329" icon={Pizza} />
          <Row y={350} name="Fries" price="₹129" icon={Fries} pressed={screen === 'add' && tap > 0.5} />
        </>
      );
    case 'placed':
      return (
        <>
          {header('Order')}
          <g transform={`translate(${w / 2} 200) scale(${pop})`}>
            <circle r={70} fill={INK} />
            <path d="M -32 2 L -8 26 L 36 -22" stroke="#FFFFFF" strokeWidth={14} fill="none" strokeLinecap="round" strokeLinejoin="round" />
          </g>
          <text x={w / 2} y={320} fontSize={30} fontWeight={900} fill={INK} textAnchor="middle">Order placed</text>
          <text x={w / 2} y={360} fontSize={22} fontWeight={800} fill="#777" textAnchor="middle">Arriving in 30 min</text>
        </>
      );
    case 'total':
      return (
        <>
          {header('Checkout')}
          {[110, 150, 190, 230].map((y) => <rect key={y} x={24} y={y} width={w - 48} height={18} rx={9} fill="#DDD" />)}
          <text x={w / 2} y={300} fontSize={26} fontWeight={900} fill="#777" textAnchor="middle">TOTAL</text>
          <text x={w / 2} y={372} fontSize={Math.min(76, 420 / Math.max(amount.length, 1))} fontWeight={900} fill={INK} textAnchor="middle" transform={`translate(${w / 2} 350) scale(${0.6 + 0.4 * pop}) translate(${-w / 2} -350)`}>
            {amount}
          </text>
        </>
      );
    case 'bank':
    case 'balance': {
      const dots = '.'.repeat(1 + (Math.floor(frame / 8) % 3));
      return (
        <>
          {header('Bank')}
          <text x={w / 2} y={170} fontSize={26} fontWeight={900} fill="#777" textAnchor="middle">Balance</text>
          {screen === 'bank' ? (
            <text x={w / 2} y={250} fontSize={60} fontWeight={900} fill={INK} textAnchor="middle">₹ {dots}</text>
          ) : (
            <text x={w / 2} y={260} fontSize={84} fontWeight={900} fill={INK} textAnchor="middle">{amount}</text>
          )}
          <rect x={30} y={320} width={w - 60} height={56} rx={14} fill="none" stroke={INK} strokeWidth={4} />
          <text x={w / 2} y={357} fontSize={24} fontWeight={800} fill={INK} textAnchor="middle">Add money</text>
        </>
      );
    }
    default:
      return null;
  }
};

// ---------- text ----------

const Caption: React.FC<{text: string; frames: number}> = ({text, frames}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const e = spring({frame, fps, config: {damping: 12, mass: 0.5}});
  const out = interpolate(frame, [frames - 5, frames], [1, 0], clamp);
  return (
    <div style={{position: 'absolute', top: 190, left: 70, right: 70, display: 'flex', justifyContent: 'center', opacity: out}}>
      <div
        style={{
          background: '#FFFFFF',
          border: `8px solid ${INK}`,
          borderRadius: 28,
          padding: '26px 34px',
          fontSize: text.length > 34 ? 60 : 70,
          fontWeight: 900,
          lineHeight: 1.18,
          color: INK,
          textAlign: 'center',
          textWrap: 'balance',
          boxShadow: `10px 10px 0 ${INK}`,
          transform: `scale(${0.8 + 0.2 * e}) rotate(${(1 - e) * -3}deg)`,
          opacity: Math.min(1, e * 1.4),
        }}
      >
        {text}
      </div>
    </div>
  );
};

const Outro: React.FC<{text: string}> = ({text}) => {
  const frame = useCurrentFrame();
  const shown = Math.ceil(interpolate(frame, [4, 40], [0, text.length], clamp));
  return (
    <Layer name="outro-text" style={{background: INK, display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
      <div style={{color: '#FFFFFF', fontSize: 96, fontWeight: 900, textAlign: 'center', padding: '0 90px', lineHeight: 1.15, textWrap: 'balance'}}>
        {text.slice(0, shown)}
        <span style={{opacity: frame % 20 < 10 ? 1 : 0}}>|</span>
      </div>
    </Layer>
  );
};
