import React from 'react';
import type {Accessory, MascotShape, Mood, Tint} from './types';

// The video's mascot: one character (designed per video from a body, a colour and an accessory) that
// carries the story from shot to shot and acts it out with its face and colour. Drawn in a 200x200 box.

const TINTS: Record<Tint, string | null> = {normal: null, red: '#E5484D', grey: '#8A8F98', gold: '#F2B705', green: '#2FB36D'};

const shade = (hex: string, k: number) => {
  const n = parseInt(hex.replace('#', ''), 16);
  const f = (c: number) => Math.max(0, Math.min(255, Math.round(k < 0 ? c * (1 + k) : c + (255 - c) * k)));
  const r = f((n >> 16) & 255), g = f((n >> 8) & 255), b = f(n & 255);
  return `#${((r << 16) | (g << 8) | b).toString(16).padStart(6, '0')}`;
};

const BODY: Record<MascotShape, string> = {
  bubble: 'M100 22 C152 22 184 54 184 98 C184 142 152 172 104 172 C92 172 82 171 72 168 L42 188 L50 158 C28 144 16 122 16 98 C16 54 48 22 100 22 Z',
  blob: 'M104 24 C150 20 186 52 182 104 C178 152 146 182 98 180 C52 178 18 150 20 102 C22 56 58 28 104 24 Z',
  bot: 'M48 40 H152 Q178 40 178 66 V146 Q178 172 152 172 H48 Q22 172 22 146 V66 Q22 40 48 40 Z',
  cube: 'M36 58 L100 30 L164 58 V146 L100 176 L36 146 Z',
  coin: 'M100 18 A82 82 0 1 1 99.9 18 Z',
  drop: 'M100 14 C126 56 172 92 172 128 C172 166 140 188 100 188 C60 188 28 166 28 128 C28 92 74 56 100 14 Z',
  ghost: 'M100 22 C148 22 176 56 176 104 V176 L156 160 L136 178 L116 160 L100 178 L84 160 L64 178 L44 160 L24 176 V104 C24 56 52 22 100 22 Z',
  sun: 'M100 38 A62 62 0 1 1 99.9 38 Z',
  flame: 'M104 10 C120 48 168 70 168 126 C168 166 138 190 100 190 C62 190 32 166 32 126 C32 92 58 78 66 46 C80 66 84 76 90 84 C94 58 96 34 104 10 Z',
  planet: 'M100 34 A66 66 0 1 1 99.9 34 Z',
  virus: 'M100 40 A60 60 0 1 1 99.9 40 Z',
  chip: 'M48 38 H152 Q164 38 164 50 V154 Q164 166 152 166 H48 Q36 166 36 154 V50 Q36 38 48 38 Z',
  battery: 'M44 56 H156 Q170 56 170 70 V164 Q170 178 156 178 H44 Q30 178 30 164 V70 Q30 56 44 56 Z',
  shield: 'M100 18 L172 44 V100 C172 146 140 176 100 192 C60 176 28 146 28 100 V44 Z',
  heart: 'M100 182 C40 140 14 108 14 72 C14 40 40 22 64 22 C82 22 94 32 100 46 C106 32 118 22 136 22 C160 22 186 40 186 72 C186 108 160 140 100 182 Z',
  cloud: 'M54 168 C28 168 14 148 14 126 C14 102 32 86 54 86 C58 52 84 32 112 32 C146 32 168 56 170 86 C192 90 190 168 160 168 Z',
  star: 'M100 10 L126 70 L190 74 L140 116 L156 180 L100 146 L44 180 L60 116 L10 74 L74 70 Z',
};
// Where the face sits (centre y) for each body.
const FACE_Y: Record<MascotShape, number> = {bubble: 96, blob: 100, bot: 104, cube: 108, coin: 100, drop: 128, ghost: 98,
  sun: 100, flame: 132, planet: 100, virus: 100, chip: 102, battery: 118, shield: 96, heart: 84, cloud: 116, star: 110};

// Parts drawn behind the body: rays, a ring, spikes, pins, a terminal.
const Behind: React.FC<{shape: MascotShape; body: string; frame: number}> = ({shape, body, frame}) => {
  const dark = shade(body, -0.35);
  if (shape === 'sun') return <g transform={`rotate(${frame * 0.6} 100 100)`}>{Array.from({length: 12}, (_, i) => <path key={i} d="M92 20 L100 -6 L108 20 Z" fill={shade(body, 0.1)} stroke={dark} strokeWidth={3} transform={`rotate(${i * 30} 100 100)`} />)}</g>;
  if (shape === 'virus') return <g>{Array.from({length: 10}, (_, i) => <g key={i} transform={`rotate(${i * 36 + Math.sin(frame / 12) * 3} 100 100)`}><line x1={100} y1={40} x2={100} y2={14} stroke={dark} strokeWidth={7} /><circle cx={100} cy={12} r={9} fill={shade(body, 0.15)} stroke={dark} strokeWidth={3} /></g>)}</g>;
  if (shape === 'chip') return <g>{[56, 80, 104, 128, 148].map((v) => <g key={v} fill={dark}><rect x={v - 5} y={22} width={10} height={18} rx={2} /><rect x={v - 5} y={164} width={10} height={18} rx={2} /><rect x={20} y={v - 5} width={18} height={10} rx={2} /><rect x={162} y={v - 5} width={18} height={10} rx={2} /></g>)}</g>;
  if (shape === 'battery') return <rect x={78} y={40} width={44} height={20} rx={5} fill={dark} />;
  return null;
};
const Front: React.FC<{shape: MascotShape; body: string}> = ({shape, body}) => {
  if (shape === 'planet') return <path d="M14 116 C14 92 186 66 188 88 C190 108 150 122 100 132" fill="none" stroke={shade(body, 0.4)} strokeWidth={10} strokeLinecap="round" opacity={0.9} />;
  if (shape === 'battery') return <rect x={44} y={150} width={112} height={16} rx={6} fill="#2FB36D" opacity={0.85} />;
  return null;
};

const Eyes: React.FC<{mood: Mood; y: number; blink: boolean; ink: string}> = ({mood, y, blink, ink}) => {
  const L = 76, R = 124;
  if (blink && !['happy', 'sleepy', 'wink', 'cool'].includes(mood)) {
    return <g stroke={ink} strokeWidth={6} strokeLinecap="round">
      <line x1={L - 10} y1={y} x2={L + 10} y2={y} /><line x1={R - 10} y1={y} x2={R + 10} y2={y} />
    </g>;
  }
  switch (mood) {
    case 'happy':
      return <g fill="none" stroke={ink} strokeWidth={6} strokeLinecap="round">
        <path d={`M${L - 11} ${y + 4} Q${L} ${y - 10} ${L + 11} ${y + 4}`} /><path d={`M${R - 11} ${y + 4} Q${R} ${y - 10} ${R + 11} ${y + 4}`} />
      </g>;
    case 'wink':
      return <g>
        <ellipse cx={L} cy={y} rx={8} ry={10} fill={ink} />
        <path d={`M${R - 11} ${y + 2} Q${R} ${y - 8} ${R + 11} ${y + 2}`} fill="none" stroke={ink} strokeWidth={6} strokeLinecap="round" />
      </g>;
    case 'sleepy':
      return <g fill="none" stroke={ink} strokeWidth={6} strokeLinecap="round">
        <path d={`M${L - 11} ${y} Q${L} ${y + 9} ${L + 11} ${y}`} /><path d={`M${R - 11} ${y} Q${R} ${y + 9} ${R + 11} ${y}`} />
      </g>;
    case 'smug':
      return <g>
        <rect x={L - 12} y={y - 2} width={24} height={9} rx={4} fill={ink} /><rect x={R - 12} y={y - 2} width={24} height={9} rx={4} fill={ink} />
      </g>;
    case 'angry':
    case 'evil':
      return <g>
        <path d={`M${L - 14} ${y - 6} L${L + 12} ${y + 2} L${L + 10} ${y + 10} L${L - 12} ${y + 8} Z`} fill={mood === 'evil' ? '#FF2E3B' : ink} />
        <path d={`M${R + 14} ${y - 6} L${R - 12} ${y + 2} L${R - 10} ${y + 10} L${R + 12} ${y + 8} Z`} fill={mood === 'evil' ? '#FF2E3B' : ink} />
      </g>;
    case 'sad':
      return <g>
        <ellipse cx={L} cy={y + 2} rx={7} ry={9} fill={ink} /><ellipse cx={R} cy={y + 2} rx={7} ry={9} fill={ink} />
        <g stroke={ink} strokeWidth={5} strokeLinecap="round"><line x1={L - 12} y1={y - 10} x2={L + 8} y2={y - 16} /><line x1={R + 12} y1={y - 10} x2={R - 8} y2={y - 16} /></g>
      </g>;
    case 'scared':
    case 'shocked':
      return <g>
        <circle cx={L} cy={y} r={13} fill="#fff" stroke={ink} strokeWidth={4} /><circle cx={R} cy={y} r={13} fill="#fff" stroke={ink} strokeWidth={4} />
        <circle cx={L} cy={y + 1} r={5} fill={ink} /><circle cx={R} cy={y + 1} r={5} fill={ink} />
      </g>;
    case 'cool':
      return <g>
        <path d={`M${L - 22} ${y - 8} H${R + 22} V${y + 2} Q${R + 20} ${y + 16} ${R} ${y + 14} Q${R - 12} ${y + 12} ${(L + R) / 2 + 6} ${y + 2} H${(L + R) / 2 - 6} Q${L + 12} ${y + 12} ${L} ${y + 14} Q${L - 20} ${y + 16} ${L - 22} ${y + 2} Z`} fill="#111" />
        <line x1={L - 12} y1={y - 3} x2={L - 2} y2={y - 3} stroke="#fff" strokeWidth={3} opacity={0.6} />
      </g>;
    default:
      return <g><ellipse cx={L} cy={y} rx={8} ry={10} fill={ink} /><ellipse cx={R} cy={y} rx={8} ry={10} fill={ink} /></g>;
  }
};

const Mouth: React.FC<{mood: Mood; y: number; ink: string}> = ({mood, y, ink}) => {
  const c = 100, my = y + 30;
  const line = {fill: 'none', stroke: ink, strokeWidth: 6, strokeLinecap: 'round' as const};
  switch (mood) {
    case 'happy':
    case 'wink':
      return <path d={`M${c - 18} ${my - 4} Q${c} ${my + 16} ${c + 18} ${my - 4}`} {...line} />;
    case 'smug':
    case 'cool':
      return <path d={`M${c - 12} ${my + 2} Q${c + 6} ${my + 8} ${c + 18} ${my - 6}`} {...line} />;
    case 'evil':
      return <path d={`M${c - 22} ${my - 6} Q${c} ${my + 18} ${c + 22} ${my - 6} Z`} fill="#3a0a0a" stroke={ink} strokeWidth={4} />;
    case 'angry':
    case 'sad':
      return <path d={`M${c - 16} ${my + 8} Q${c} ${my - 6} ${c + 16} ${my + 8}`} {...line} />;
    case 'scared':
      return <path d={`M${c - 14} ${my + 4} q5 -6 10 0 q5 6 10 0 q4 -6 8 0`} {...line} strokeWidth={4} />;
    case 'shocked':
      return <ellipse cx={c} cy={my + 4} rx={9} ry={12} fill={ink} />;
    case 'sleepy':
      return <ellipse cx={c} cy={my + 2} rx={6} ry={4} fill={ink} />;
    default:
      return <line x1={c - 10} y1={my + 2} x2={c + 10} y2={my + 2} {...line} />;
  }
};

const Extra: React.FC<{accessory: Accessory; shape: MascotShape; color: string}> = ({accessory, shape, color}) => {
  const dark = shade(color, -0.45);
  switch (accessory) {
    case 'headset':
      return <g>
        <path d="M30 96 C30 40 170 40 170 96" fill="none" stroke={dark} strokeWidth={10} strokeLinecap="round" />
        <rect x={16} y={84} width={22} height={40} rx={10} fill={dark} /><rect x={162} y={84} width={22} height={40} rx={10} fill={dark} />
        <path d="M28 122 Q34 150 62 150" fill="none" stroke={dark} strokeWidth={6} strokeLinecap="round" /><circle cx={66} cy={150} r={7} fill={dark} />
      </g>;
    case 'antenna':
      return <g><line x1={100} y1={shape === 'bot' ? 40 : 24} x2={100} y2={4} stroke={dark} strokeWidth={6} /><circle cx={100} cy={6} r={9} fill="#FF5A5F" /></g>;
    case 'cap':
      return <g><path d="M48 46 Q100 0 152 46 Z" fill={dark} /><path d="M140 42 L186 52 L146 58 Z" fill={dark} /></g>;
    case 'glasses':
      return <g fill="none" stroke="#111" strokeWidth={5}><circle cx={76} cy={FACE_Y[shape]} r={17} /><circle cx={124} cy={FACE_Y[shape]} r={17} /><line x1={93} y1={FACE_Y[shape]} x2={107} y2={FACE_Y[shape]} /></g>;
    case 'crown':
      return <path d="M62 30 L72 4 L88 22 L100 0 L112 22 L128 4 L138 30 Z" fill="#F2B705" stroke="#B07D00" strokeWidth={3} />;
    case 'bowtie':
      return <g transform="translate(0 4)"><path d="M100 170 L74 158 V184 Z M100 170 L126 158 V184 Z" fill="#E5484D" /><circle cx={100} cy={171} r={6} fill="#B5262D" /></g>;
    default:
      return null;
  }
};

export const Mascot: React.FC<{
  shape: MascotShape; color: string; accessory: Accessory; mood: Mood; tint?: Tint; frame: number; size: number; flip?: boolean;
}> = ({shape, color, accessory, mood, tint = 'normal', frame, size, flip}) => {
  const body = TINTS[tint] ?? color;
  const ink = '#14213D';
  const y = FACE_Y[shape];
  const blink = frame % 96 > 91;
  const bob = Math.sin(frame / 14) * 3;
  return (
    <svg viewBox="-10 -10 220 220" width={size} height={size} style={{overflow: 'visible', transform: `translateY(${bob}px) scaleX(${flip ? -1 : 1})`}}>
      <ellipse cx={100} cy={198} rx={64} ry={9} fill="rgba(0,0,0,0.18)" />
      <Behind shape={shape} body={body} frame={frame} />
      <path d={BODY[shape]} fill={body} stroke={shade(body, -0.35)} strokeWidth={5} strokeLinejoin="round" />
      <Front shape={shape} body={body} />
      {shape === 'cube' ? <path d="M36 58 L100 86 L164 58" fill="none" stroke={shade(body, -0.25)} strokeWidth={4} /> : null}
      {shape === 'coin' ? <circle cx={100} cy={100} r={66} fill="none" stroke={shade(body, -0.2)} strokeWidth={5} /> : null}
      <ellipse cx={100} cy={y + 8} rx={({star: 36, heart: 48, flame: 44, shield: 50} as Record<string, number>)[shape] ?? 56} ry={({star: 28, heart: 34, flame: 36} as Record<string, number>)[shape] ?? 40} fill={shade(body, 0.35)} opacity={0.75} />
      <ellipse cx={70} cy={50} rx={16} ry={8} fill="#fff" opacity={0.35} transform="rotate(-25 70 50)" />
      <Eyes mood={mood} y={y} blink={blink} ink={ink} />
      <Mouth mood={mood} y={y} ink={ink} />
      {mood === 'sleepy' ? <text x={150} y={40 + Math.sin(frame / 10) * 4} fontSize={30} fontWeight={900} fill={ink}>z</text> : null}
      {mood === 'scared' ? <path d="M160 70 q6 10 0 16 q-6 -6 0 -16 Z" fill="#7cc6ff" /> : null}
      <Extra accessory={accessory} shape={shape} color={body} />
    </svg>
  );
};

export {shade};
