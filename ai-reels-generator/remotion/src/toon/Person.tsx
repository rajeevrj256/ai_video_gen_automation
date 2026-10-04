import React from 'react';
import {shade} from './Mascot';
import type {Look, Mood, Pose} from './types';

// Flat cartoon people (no stick figures): skin, hair, beard, glasses, clothes, an expressive face and a
// mouth that moves on the words, in poses that act the line out. Drawn in a 300x600 box, feet at y=590.

const SKINS = ['#F6D3B3', '#EBB98F', '#D69A6C', '#B97A50', '#8D5A3B', '#6B3F28'];
export const skinTone = (i: number) => SKINS[Math.abs(i) % SKINS.length];

const HairBack: React.FC<{look: Look}> = ({look}) => {
  const c = look.hairColor;
  if (look.hair === 'long') return <path d="M108 70 Q150 30 192 70 L200 170 Q150 186 100 170 Z" fill={c} />;
  if (look.hair === 'bun') return <circle cx={150} cy={34} r={22} fill={c} />;
  return null;
};

const HairFront: React.FC<{look: Look}> = ({look}) => {
  const c = look.hairColor, d = shade(c, -0.25);
  switch (look.hair) {
    case 'bald':
      return <path d="M112 84 Q114 70 120 64" fill="none" stroke={d} strokeWidth={4} opacity={0.4} />;
    case 'side':
      return <path d="M104 92 Q102 46 150 42 Q196 44 196 92 Q188 70 160 66 Q130 66 116 74 Q108 82 104 92 Z" fill={c} />;
    case 'curly':
      return <g fill={c}>{[110, 128, 146, 164, 182, 192, 104].map((x, i) => <circle key={i} cx={x} cy={i > 4 ? 78 : 52 + (i % 2) * 6} r={18} />)}</g>;
    case 'spiky':
      return <path d="M104 86 L108 50 L122 62 L132 38 L146 58 L160 34 L170 58 L186 42 L190 64 L198 86 Q170 64 150 66 Q122 66 104 86 Z" fill={c} />;
    case 'cap':
      return <g><path d="M102 78 Q104 36 150 36 Q196 36 198 78 Z" fill={c} /><path d="M188 72 L232 80 L190 86 Z" fill={d} /></g>;
    case 'long':
    case 'bun':
      return <path d="M104 92 Q104 44 150 42 Q196 44 196 92 Q180 62 150 60 Q118 62 104 92 Z" fill={c} />;
    default:
      return <path d="M104 86 Q104 42 150 42 Q196 42 196 86 Q184 60 150 58 Q116 60 104 86 Z" fill={c} />;
  }
};

const Face: React.FC<{mood: Mood; talk: number; look: Look; blink: boolean}> = ({mood, talk, look, blink}) => {
  const ink = '#2B2118';
  const eyeY = 98, L = 134, R = 166;
  // [outer end, inner end] offsets: angry = inner ends down, sad/scared = inner ends up.
  const brow = {angry: [-4, 9], evil: [-4, 9], sad: [7, -6], scared: [6, -7], shocked: [-7, -7], smug: [0, -5]}[mood as string] ?? [0, 0];
  const big = mood === 'shocked' || mood === 'scared';
  const open = talk > 0 ? 3 + talk * 9 : 0;
  const mouthY = 132;
  let mouth: React.ReactNode;
  if (open > 0) mouth = <ellipse cx={150} cy={mouthY} rx={9} ry={open / 2 + 2} fill="#5B1F1F" />;
  else if (mood === 'happy' || mood === 'wink') mouth = <path d={`M136 ${mouthY - 4} Q150 ${mouthY + 10} 164 ${mouthY - 4}`} fill="#fff" stroke={ink} strokeWidth={3} />;
  else if (mood === 'smug' || mood === 'cool' || mood === 'evil') mouth = <path d={`M140 ${mouthY + 2} Q154 ${mouthY + 6} 164 ${mouthY - 4}`} fill="none" stroke={ink} strokeWidth={4} strokeLinecap="round" />;
  else if (mood === 'sad' || mood === 'angry') mouth = <path d={`M138 ${mouthY + 6} Q150 ${mouthY - 4} 162 ${mouthY + 6}`} fill="none" stroke={ink} strokeWidth={4} strokeLinecap="round" />;
  else if (big) mouth = <ellipse cx={150} cy={mouthY + 2} rx={8} ry={11} fill="#5B1F1F" />;
  else mouth = <line x1={142} y1={mouthY} x2={158} y2={mouthY} stroke={ink} strokeWidth={4} strokeLinecap="round" />;
  return (
    <g>
      {blink && !big ? (
        <g stroke={ink} strokeWidth={4} strokeLinecap="round"><line x1={L - 6} y1={eyeY} x2={L + 6} y2={eyeY} /><line x1={R - 6} y1={eyeY} x2={R + 6} y2={eyeY} /></g>
      ) : (
        <g>
          <ellipse cx={L} cy={eyeY} rx={big ? 9 : 6} ry={big ? 10 : 7} fill="#fff" />
          <ellipse cx={R} cy={eyeY} rx={big ? 9 : 6} ry={big ? 10 : 7} fill="#fff" />
          <circle cx={L + 1} cy={eyeY + 1} r={big ? 4 : 4.5} fill={ink} /><circle cx={R + 1} cy={eyeY + 1} r={big ? 4 : 4.5} fill={ink} />
        </g>
      )}
      <g stroke={shade(look.hairColor, -0.2)} strokeWidth={5} strokeLinecap="round">
        <line x1={L - 9} y1={eyeY - 14 + brow[0]} x2={L + 8} y2={eyeY - 14 + brow[1]} />
        <line x1={R - 8} y1={eyeY - 14 + brow[1]} x2={R + 9} y2={eyeY - 14 + brow[0]} />
      </g>
      <path d="M150 104 Q146 116 152 118" fill="none" stroke={shade(look.skin, -0.25)} strokeWidth={3} strokeLinecap="round" />
      {look.beard === 'full' ? <path d="M112 112 Q114 162 150 166 Q186 162 188 112 Q178 140 150 142 Q122 140 112 112 Z" fill={look.hairColor} /> : null}
      {look.beard === 'stubble' ? <path d="M114 116 Q118 158 150 162 Q182 158 186 116 Q176 146 150 148 Q124 146 114 116 Z" fill={look.hairColor} opacity={0.3} /> : null}
      {look.beard === 'mustache' ? <path d="M134 124 Q150 116 166 124 Q150 122 134 124 Z" fill={look.hairColor} stroke={look.hairColor} strokeWidth={4} /> : null}
      {mouth}
      {look.glasses ? <g fill="rgba(255,255,255,0.15)" stroke="#1d1d1d" strokeWidth={4}><circle cx={L} cy={eyeY} r={14} /><circle cx={R} cy={eyeY} r={14} /><line x1={L + 14} y1={eyeY} x2={R - 14} y2={eyeY} /></g> : null}
      {mood === 'scared' || mood === 'shocked' ? <path d="M196 84 q6 10 0 16 q-6 -6 0 -16 Z" fill="#7cc6ff" /> : null}
    </g>
  );
};

// Arms per pose: [upper, forearm] for the left then the right arm, in degrees from straight down,
// positive = outward (each arm mirrors), the forearm relative to the upper arm.
const ARMS: Record<Pose, [number, number, number, number]> = {
  stand: [8, 4, 8, 4], point: [8, 4, 80, 10], shrug: [40, 100, 40, 100], 'hands-up': [150, 10, 150, 10],
  'hands-head': [150, 110, 150, 110], think: [8, 4, 30, -180], wave: [8, 4, 150, 30], run: [10, -70, 10, -70],
  sit: [20, -80, 20, -80], present: [8, 4, 70, 40],
};

const Arm: React.FC<{x: number; y: number; a: number; b: number; side: number; sleeve: string; skin: string}> = ({x, y, a, b, side, sleeve, skin}) => {
  const len = 62;
  const rad = (d: number) => (d * Math.PI) / 180;
  const ex = x + side * Math.sin(rad(a)) * len, ey = y + Math.cos(rad(a)) * len;
  const hx = ex + side * Math.sin(rad(a + b)) * 56, hy = ey + Math.cos(rad(a + b)) * 56;
  return (
    <g strokeLinecap="round">
      <line x1={x} y1={y} x2={ex} y2={ey} stroke={sleeve} strokeWidth={26} />
      <line x1={ex} y1={ey} x2={hx} y2={hy} stroke={sleeve} strokeWidth={22} />
      <circle cx={hx} cy={hy} r={13} fill={skin} />
    </g>
  );
};

export const Person: React.FC<{look: Look; pose: Pose; mood: Mood; talk: number; frame: number; height: number; flip?: boolean; seated?: boolean}> = ({
  look, pose, mood, talk, frame, height, flip, seated,
}) => {
  const run = pose === 'run';
  const step = run ? Math.sin(frame / 3) : 0;
  const bob = run ? Math.abs(Math.sin(frame / 3)) * -10 : Math.sin(frame / 22) * 1.5;
  const [la, lb, ra, rb] = ARMS[pose];
  const swing = run ? step * 35 : 0;
  const top = look.coat ?? look.shirt;
  const blink = frame % 110 > 105;
  const legs = seated ? null : (
    <g strokeLinecap="round">
      <line x1={136} y1={400} x2={136 + step * 40} y2={575} stroke={look.pants} strokeWidth={34} />
      <line x1={164} y1={400} x2={164 - step * 40} y2={575} stroke={look.pants} strokeWidth={34} />
      <ellipse cx={136 + step * 40 + 8} cy={582} rx={26} ry={12} fill="#2b2b2b" />
      <ellipse cx={164 - step * 40 + 8} cy={582} rx={26} ry={12} fill="#2b2b2b" />
    </g>
  );
  return (
    <svg viewBox="0 0 300 600" width={height / 2} height={height} style={{overflow: 'visible', transform: `translateY(${bob}px) scaleX(${flip ? -1 : 1})`}}>
      {!seated ? <ellipse cx={150} cy={592} rx={70} ry={10} fill="rgba(0,0,0,0.18)" /> : null}
      <HairBack look={look} />
      {legs}
      <Arm x={108} y={212} side={-1} a={la + swing} b={lb} sleeve={shade(top, -0.08)} skin={look.skin} />
      <path d="M104 200 Q104 184 122 180 H178 Q196 184 196 200 L200 410 H100 Z" fill={top} />
      {look.coat ? <path d="M150 182 L132 182 L150 260 L168 182 Z" fill={look.shirt} /> : <path d="M132 180 L150 202 L168 180 Z" fill={shade(look.shirt, -0.15)} />}
      {look.tie ? <path d="M146 196 L154 196 L160 290 L150 304 L140 290 Z" fill={look.tie} /> : null}
      <rect x={136} y={156} width={28} height={30} fill={shade(look.skin, -0.1)} />
      <ellipse cx={104} cy={104} rx={9} ry={14} fill={shade(look.skin, -0.05)} />
      <ellipse cx={196} cy={104} rx={9} ry={14} fill={shade(look.skin, -0.05)} />
      <path d="M104 92 Q102 46 150 44 Q198 46 196 92 L194 120 Q190 164 150 168 Q110 164 106 120 Z" fill={look.skin} />
      <HairFront look={look} />
      <Face mood={mood} talk={talk} look={look} blink={blink} />
      <Arm x={192} y={212} side={1} a={ra - swing} b={rb} sleeve={shade(top, -0.08)} skin={look.skin} />
    </svg>
  );
};
