import React from 'react';
import {iconFor} from '../long/icon';
import {shade} from './Mascot';
import type {Look, Mood, Pose} from './types';

// Flat cartoon people (no stick figures), cast per scene by the writer: age, build, outfit for the role and
// the period (suit, lab coat, hoodie, uniform, robe, dress, overalls, period coat...), headwear, something
// in the hand (an icon or a drawing Claude made for it), an expressive face and a mouth that moves on the
// words, in poses that act the line out. Drawn in a 300x600 box, feet at y=590.

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
  // Headwear that covers the hair replaces it.
  if (['headscarf', 'hood', 'turban', 'helmet'].includes(look.headwear ?? '')) return null;
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

const Headwear: React.FC<{look: Look}> = ({look}) => {
  const ink = '#15151c';
  switch (look.headwear) {
    case 'hard-hat':
      return <g><path d="M100 76 Q102 26 150 24 Q198 26 200 76 Z" fill="#F2B705" stroke={ink} strokeWidth={4} /><rect x={88} y={70} width={124} height={14} rx={6} fill="#E0A100" stroke={ink} strokeWidth={4} /><rect x={145} y={26} width={10} height={46} fill="#E0A100" /></g>;
    case 'cap':
      return <g><path d="M102 74 Q104 34 150 34 Q196 34 198 74 Z" fill={look.shirt} stroke={ink} strokeWidth={3} /><path d="M190 68 L240 78 L192 84 Z" fill={shade(look.shirt, -0.3)} /></g>;
    case 'top-hat':
      return <g><rect x={112} y={-34} width={76} height={92} rx={6} fill="#1c1c22" /><rect x={92} y={52} width={116} height={14} rx={6} fill="#1c1c22" /><rect x={112} y={34} width={76} height={10} fill="#8B1E2D" /></g>;
    case 'tricorn':
      return <path d="M86 70 Q100 30 150 26 Q200 30 214 70 Q182 56 150 58 Q118 56 86 70 Z" fill="#2a2320" stroke="#c9a227" strokeWidth={4} />;
    case 'headscarf':
      return <path d="M98 108 Q96 36 150 34 Q204 36 202 108 Q204 160 176 176 L176 120 Q176 70 150 68 Q124 70 124 120 L124 176 Q96 160 98 108 Z" fill={look.coat ?? '#C0392B'} />;
    case 'crown':
      return <path d="M110 58 L118 22 L134 46 L150 16 L166 46 L182 22 L190 58 Z" fill="#F2B705" stroke="#B07D00" strokeWidth={4} />;
    case 'helmet':
      return <g><path d="M98 96 Q98 30 150 28 Q202 30 202 96 Z" fill="#6b7280" stroke={ink} strokeWidth={4} /><rect x={96} y={88} width={108} height={12} rx={5} fill="#4b5563" /></g>;
    case 'beanie':
      return <g><path d="M102 80 Q104 30 150 30 Q196 30 198 80 Z" fill={look.coat ?? '#E5484D'} /><rect x={100} y={70} width={100} height={16} rx={6} fill={shade(look.coat ?? '#E5484D', -0.2)} /><circle cx={150} cy={26} r={10} fill="#fff" /></g>;
    case 'hood':
      return <path d="M96 120 Q92 34 150 30 Q208 34 204 120 Q196 82 182 72 Q150 58 118 72 Q104 82 96 120 Z" fill={look.shirt} stroke={shade(look.shirt, -0.3)} strokeWidth={3} />;
    case 'bowler':
      return <g><path d="M112 62 Q114 28 150 28 Q186 28 188 62 Z" fill="#1c1c22" /><rect x={96} y={58} width={108} height={10} rx={5} fill="#1c1c22" /></g>;
    case 'turban':
      return <path d="M98 88 Q96 30 150 28 Q204 30 202 88 Q180 70 150 76 Q120 70 98 88 Z" fill={look.coat ?? '#E9C46A'} stroke={shade(look.coat ?? '#E9C46A', -0.25)} strokeWidth={4} />;
    case 'chef-hat':
      return <g fill="#fff" stroke="#d6d6d6" strokeWidth={3}><rect x={114} y={46} width={72} height={26} /><circle cx={124} cy={30} r={22} /><circle cx={150} cy={20} r={24} /><circle cx={176} cy={30} r={22} /></g>;
    case 'graduation-cap':
      return <g><path d="M90 52 L150 30 L210 52 L150 74 Z" fill="#1c1c22" /><rect x={124} y={58} width={52} height={20} fill="#1c1c22" /><line x1={206} y1={52} x2={210} y2={92} stroke="#F2B705" strokeWidth={4} /></g>;
    default:
      return null;
  }
};

const Face: React.FC<{mood: Mood; talk: number; look: Look; blink: boolean}> = ({mood, talk, look, blink}) => {
  const ink = '#2B2118';
  const eyeY = 98, L = 134, R = 166;
  // [outer end, inner end] offsets: angry = inner ends down, sad/scared = inner ends up.
  const brow = ({angry: [-4, 9], evil: [-4, 9], determined: [-2, 6], sad: [7, -6], crying: [7, -6], scared: [6, -7],
    worried: [5, -6], shocked: [-7, -7], smug: [0, -5], proud: [-3, -3], confused: [-8, 2]} as Record<string, number[]>)[mood] ?? [0, 0];
  const big = mood === 'shocked' || mood === 'scared';
  const closed = mood === 'laughing' || mood === 'proud';
  const open = talk > 0 ? 3 + talk * 9 : 0;
  const mouthY = 132;
  const line = {fill: 'none', stroke: ink, strokeWidth: 4, strokeLinecap: 'round' as const};
  let mouth: React.ReactNode;
  if (open > 0) mouth = <ellipse cx={150} cy={mouthY} rx={9} ry={open / 2 + 2} fill="#5B1F1F" />;
  else if (mood === 'laughing') mouth = <path d={`M134 ${mouthY - 6} Q150 ${mouthY + 18} 166 ${mouthY - 6} Z`} fill="#5B1F1F" stroke={ink} strokeWidth={3} />;
  else if (mood === 'happy' || mood === 'wink' || mood === 'proud') mouth = <path d={`M136 ${mouthY - 4} Q150 ${mouthY + 10} 164 ${mouthY - 4}`} fill="#fff" stroke={ink} strokeWidth={3} />;
  else if (mood === 'smug' || mood === 'cool' || mood === 'evil') mouth = <path d={`M140 ${mouthY + 2} Q154 ${mouthY + 6} 164 ${mouthY - 4}`} {...line} />;
  else if (mood === 'sad' || mood === 'angry' || mood === 'crying') mouth = <path d={`M138 ${mouthY + 6} Q150 ${mouthY - 4} 162 ${mouthY + 6}`} {...line} />;
  else if (mood === 'confused' || mood === 'worried') mouth = <path d={`M138 ${mouthY + 2} q6 -5 12 0 q6 5 12 0`} {...line} />;
  else if (big) mouth = <ellipse cx={150} cy={mouthY + 2} rx={8} ry={11} fill="#5B1F1F" />;
  else mouth = <line x1={142} y1={mouthY} x2={158} y2={mouthY} stroke={ink} strokeWidth={4} strokeLinecap="round" />;
  return (
    <g>
      {closed ? (
        <g {...line}><path d={`M${L - 7} ${eyeY + 2} Q${L} ${eyeY - 6} ${L + 7} ${eyeY + 2}`} /><path d={`M${R - 7} ${eyeY + 2} Q${R} ${eyeY - 6} ${R + 7} ${eyeY + 2}`} /></g>
      ) : blink && !big ? (
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
        <line x1={R - 8} y1={eyeY - 14 + (mood === 'confused' ? -6 : brow[1])} x2={R + 9} y2={eyeY - 14 + (mood === 'confused' ? -9 : brow[0])} />
      </g>
      <path d="M150 104 Q146 116 152 118" fill="none" stroke={shade(look.skin, -0.25)} strokeWidth={3} strokeLinecap="round" />
      {look.age === 'elder' ? <g stroke={shade(look.skin, -0.25)} strokeWidth={2.5} fill="none"><path d="M118 112 q4 4 0 8" /><path d="M182 112 q-4 4 0 8" /><path d="M136 72 h28" /></g> : null}
      {look.beard === 'full' ? <path d="M112 112 Q114 162 150 166 Q186 162 188 112 Q178 140 150 142 Q122 140 112 112 Z" fill={look.hairColor} /> : null}
      {look.beard === 'stubble' ? <path d="M114 116 Q118 158 150 162 Q182 158 186 116 Q176 146 150 148 Q124 146 114 116 Z" fill={look.hairColor} opacity={0.3} /> : null}
      {look.beard === 'mustache' ? <path d="M134 124 Q150 116 166 124 Q150 122 134 124 Z" fill={look.hairColor} stroke={look.hairColor} strokeWidth={4} /> : null}
      {mouth}
      {look.glasses ? <g fill="rgba(255,255,255,0.15)" stroke="#1d1d1d" strokeWidth={4}><circle cx={L} cy={eyeY} r={14} /><circle cx={R} cy={eyeY} r={14} /><line x1={L + 14} y1={eyeY} x2={R - 14} y2={eyeY} /></g> : null}
      {mood === 'scared' || mood === 'shocked' || mood === 'worried' ? <path d="M196 84 q6 10 0 16 q-6 -6 0 -16 Z" fill="#7cc6ff" /> : null}
      {mood === 'crying' ? <g fill="#7cc6ff"><path d="M128 106 q5 12 0 18 q-5 -6 0 -18 Z" /><path d="M172 106 q5 12 0 18 q-5 -6 0 -18 Z" /></g> : null}
    </g>
  );
};

// Arms per pose: [upper, forearm] for the left then the right arm, in degrees from straight down,
// positive = outward (each arm mirrors), the forearm relative to the upper arm.
const ARMS: Record<Pose, [number, number, number, number]> = {
  stand: [8, 4, 8, 4], point: [8, 4, 80, 10], shrug: [40, 100, 40, 100], 'hands-up': [150, 10, 150, 10],
  'hands-head': [150, 110, 150, 110], think: [8, 4, 30, -180], wave: [8, 4, 150, 30], run: [10, -70, 10, -70],
  sit: [20, -80, 20, -80], present: [8, 4, 70, 40], 'arms-crossed': [24, -118, 24, -118], celebrate: [150, -25, 150, -25],
  typing: [22, -78, 22, -72], sneak: [30, -60, 50, -40], cower: [150, 120, 150, 120], facepalm: [8, 4, 26, -176],
  'hold-up': [8, 4, 160, 0],
};

const armEnds = (x: number, y: number, a: number, b: number, side: number) => {
  const rad = (d: number) => (d * Math.PI) / 180;
  const ex = x + side * Math.sin(rad(a)) * 62, ey = y + Math.cos(rad(a)) * 62;
  return {ex, ey, hx: ex + side * Math.sin(rad(a + b)) * 56, hy: ey + Math.cos(rad(a + b)) * 56};
};

const Arm: React.FC<{x: number; y: number; a: number; b: number; side: number; sleeve: string; fore: string; skin: string}> = ({x, y, a, b, side, sleeve, fore, skin}) => {
  const {ex, ey, hx, hy} = armEnds(x, y, a, b, side);
  return (
    <g strokeLinecap="round">
      <line x1={x} y1={y} x2={ex} y2={ey} stroke={sleeve} strokeWidth={26} />
      <line x1={ex} y1={ey} x2={hx} y2={hy} stroke={fore} strokeWidth={22} />
      <circle cx={hx} cy={hy} r={13} fill={skin} />
    </g>
  );
};

const Held: React.FC<{look: Look; x: number; y: number}> = ({look, x, y}) => {
  if (look.heldSvg) {
    return <g transform={`translate(${x - 36} ${y - 60}) scale(0.36)`} dangerouslySetInnerHTML={{__html: look.heldSvg}} />;
  }
  if (!look.held) return null;
  const Icon = iconFor(look.held);
  return (
    <g>
      <circle cx={x} cy={y - 26} r={30} fill="#fff" stroke="#15151c" strokeWidth={4} />
      <Icon x={x - 18} y={y - 44} width={36} height={36} color="#15151c" strokeWidth={2.4} />
    </g>
  );
};

// The clothes over the torso (x from l to r), by outfit.
const Clothes: React.FC<{look: Look; l: number; r: number}> = ({look, l, r}) => {
  const shirt = look.shirt, coat = look.coat ?? shade(shirt, -0.35);
  const torso = `M${l} 200 Q${l} 184 ${l + 18} 180 H${r - 18} Q${r} 184 ${r} 200 L${r + 4} 410 H${l - 4} Z`;
  switch (look.outfit) {
    case 'suit':
    case 'jacket':
      return <g><path d={torso} fill={coat} /><path d="M150 182 L132 182 L150 262 L168 182 Z" fill={shirt} />
        {look.outfit === 'suit' ? <path d="M146 196 L154 196 L160 290 L150 304 L140 290 Z" fill={look.tie ?? '#1d3557'} /> : null}</g>;
    case 'lab-coat':
      return <g><path d={torso} fill={shirt} /><path d={`M${l - 2} 196 Q${l} 182 ${l + 18} 180 H132 L150 250 L168 180 H${r - 18} Q${r} 182 ${r + 2} 196 L${r + 12} 480 H${l - 12} Z`} fill={look.coat ?? '#F1F5F9'} stroke="#cbd5e1" strokeWidth={3} />
        <rect x={168} y={250} width={22} height={28} rx={3} fill="#e2e8f0" stroke="#cbd5e1" strokeWidth={2} /><line x1={150} y1={250} x2={150} y2={480} stroke="#cbd5e1" strokeWidth={3} /></g>;
    case 'hoodie':
      return <g><path d={torso} fill={shirt} /><path d="M118 186 Q150 214 182 186" fill="none" stroke={shade(shirt, -0.3)} strokeWidth={8} />
        <rect x={120} y={320} width={60} height={42} rx={10} fill={shade(shirt, -0.12)} /><g stroke="#fff" strokeWidth={3}><line x1={140} y1={198} x2={138} y2={240} /><line x1={160} y1={198} x2={162} y2={240} /></g></g>;
    case 'uniform':
      return <g><path d={torso} fill={look.coat ?? '#24365e'} /><path d="M150 182 L138 182 L150 220 L162 182 Z" fill={shirt} />
        <path d="M120 250 l6 -12 l6 12 l-12 -7 h12 Z" fill="#F2B705" /><rect x={l - 2} y={350} width={r - l + 4} height={14} fill="#1c1c22" />
        <rect x={l} y={190} width={26} height={8} fill="#F2B705" /><rect x={r - 26} y={190} width={26} height={8} fill="#F2B705" /></g>;
    case 'robe':
      return <path d={`M${l} 200 Q${l} 184 ${l + 18} 180 H${r - 18} Q${r} 184 ${r} 200 L${r + 30} 580 H${l - 30} Z`} fill={look.coat ?? shirt} stroke={shade(look.coat ?? shirt, -0.25)} strokeWidth={3} />;
    case 'dress':
      return <path d={`M${l + 4} 200 Q${l + 4} 184 ${l + 20} 180 H${r - 20} Q${r - 4} 184 ${r - 4} 200 L${r - 8} 300 L${r + 40} 470 H${l - 40} L${l + 8} 300 Z`} fill={shirt} stroke={shade(shirt, -0.25)} strokeWidth={3} />;
    case 'overalls':
      return <g><path d={torso} fill={shirt} /><rect x={120} y={250} width={60} height={160} rx={6} fill={look.coat ?? '#3a6ea5'} /><path d={`M120 254 L${l + 10} 188 M180 254 L${r - 10} 188`} stroke={look.coat ?? '#3a6ea5'} strokeWidth={12} /></g>;
    case 'period-coat':
      return <g><path d={`M${l - 2} 196 Q${l} 182 ${l + 18} 180 H${r - 18} Q${r} 182 ${r + 2} 196 L${r + 16} 490 H${l - 16} Z`} fill={coat} />
        <path d="M134 180 L150 168 L166 180 L150 214 Z" fill="#fff" />{[230, 270, 310, 350].map((y) => <g key={y} fill="#c9a227"><circle cx={136} cy={y} r={5} /><circle cx={164} cy={y} r={5} /></g>)}</g>;
    case 't-shirt':
      return <g><path d={torso} fill={shirt} /><path d="M132 182 Q150 200 168 182" fill="none" stroke={shade(shirt, -0.3)} strokeWidth={6} /></g>;
    default: // shirt
      return <g><path d={torso} fill={look.coat ?? shirt} />{look.coat ? <path d="M150 182 L132 182 L150 260 L168 182 Z" fill={shirt} /> : <path d="M132 180 L150 202 L168 180 Z" fill={shade(shirt, -0.15)} />}
        {look.tie ? <path d="M146 196 L154 196 L160 290 L150 304 L140 290 Z" fill={look.tie} /> : null}</g>;
  }
};

export const Person: React.FC<{look: Look; pose: Pose; mood: Mood; talk: number; frame: number; height: number; flip?: boolean; seated?: boolean}> = ({
  look, pose, mood, talk, frame, height, flip, seated,
}) => {
  const run = pose === 'run';
  const step = run ? Math.sin(frame / 3) : pose === 'sneak' ? Math.sin(frame / 9) * 0.5 : 0;
  const bob = run ? Math.abs(Math.sin(frame / 3)) * -10 : pose === 'celebrate' ? Math.abs(Math.sin(frame / 6)) * -14 : Math.sin(frame / 22) * 1.5;
  const crouch = pose === 'cower' || pose === 'sneak' ? 30 : 0;
  const [la, lb, ra, rb] = ARMS[pose] ?? ARMS.stand;
  const swing = run ? step * 35 : 0;
  const w = look.build === 'slim' ? -8 : look.build === 'broad' ? 10 : 0;
  const l = 104 - w, r = 196 + w;
  const sleeveColor = ['suit', 'jacket', 'lab-coat', 'uniform', 'period-coat', 'robe'].includes(look.outfit ?? '')
    ? (look.outfit === 'lab-coat' ? look.coat ?? '#F1F5F9' : look.coat ?? shade(look.shirt, -0.35)) : look.shirt;
  const fore = look.outfit === 't-shirt' ? look.skin : sleeveColor;
  const blink = frame % 110 > 105;
  const child = look.age === 'child';
  const scale = child ? 0.7 : look.age === 'elder' ? 0.96 : 1;
  const hand = armEnds(r - 4, 212, ra - swing, rb, 1);
  const hidesLegs = look.outfit === 'robe';
  const legs = seated || hidesLegs ? (hidesLegs && !seated ? <g><ellipse cx={136} cy={582} rx={26} ry={12} fill="#2b2b2b" /><ellipse cx={164} cy={582} rx={26} ry={12} fill="#2b2b2b" /></g> : null) : (
    <g strokeLinecap="round">
      <line x1={136} y1={400} x2={136 + step * 40} y2={575 - crouch} stroke={look.pants} strokeWidth={34} />
      <line x1={164} y1={400} x2={164 - step * 40} y2={575 - crouch} stroke={look.pants} strokeWidth={34} />
      <ellipse cx={136 + step * 40 + 8} cy={582 - crouch} rx={26} ry={12} fill="#2b2b2b" />
      <ellipse cx={164 - step * 40 + 8} cy={582 - crouch} rx={26} ry={12} fill="#2b2b2b" />
    </g>
  );
  return (
    <svg viewBox="0 0 300 600" width={height / 2} height={height}
      style={{overflow: 'visible', transform: `translateY(${bob}px) scaleX(${flip ? -1 : 1}) scale(${scale})`, transformOrigin: '50% 100%'}}>
      {!seated ? <ellipse cx={150} cy={592} rx={70} ry={10} fill="rgba(0,0,0,0.18)" /> : null}
      <g transform={`translate(0 ${crouch}) rotate(${look.age === 'elder' ? 3 : pose === 'sneak' ? 8 : 0} 150 400)`}>
        {look.headwear === 'hood' ? null : <HairBack look={look} />}
        {legs}
        <Arm x={l + 4} y={212} side={-1} a={la + swing} b={lb} sleeve={sleeveColor} fore={fore} skin={look.skin} />
        <Clothes look={look} l={l} r={r} />
        <rect x={136} y={156} width={28} height={30} fill={shade(look.skin, -0.1)} />
        <g transform={child ? 'translate(150 168) scale(1.18) translate(-150 -168)' : undefined}>
          <ellipse cx={104} cy={104} rx={9} ry={14} fill={shade(look.skin, -0.05)} />
          <ellipse cx={196} cy={104} rx={9} ry={14} fill={shade(look.skin, -0.05)} />
          <path d="M104 92 Q102 46 150 44 Q198 46 196 92 L194 120 Q190 164 150 168 Q110 164 106 120 Z" fill={look.skin} />
          <HairFront look={look} />
          <Face mood={mood} talk={talk} look={look} blink={blink} />
          <Headwear look={look} />
        </g>
        <Arm x={r - 4} y={212} side={1} a={ra - swing} b={rb} sleeve={sleeveColor} fore={fore} skin={look.skin} />
        <Held look={look} x={hand.hx} y={hand.hy} />
      </g>
    </svg>
  );
};
