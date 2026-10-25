import React from 'react';
import {random} from 'remotion';
import type {Light, SetName} from './types';

// The places of the films (reelgen/sticky/ANALYSIS.md): dark line-art rooms with only what the story needs, and
// light doing the mood (a moonlight beam, a lamp pool, dawn through the window, a phone glow). A set is data the
// actors use too: `furniture` says where its bed, chair or couch is, so a sitting or lying actor is put on it.

export const W = 1920;
export const H = 1080;
export const FLOOR = 860;
const LINE = 'rgba(222,226,234,0.78)';
const LINE_DIM = 'rgba(222,226,234,0.38)';
const FILL = '#1B1F28';

export type Furniture = {bed?: [number, number]; chair?: number; couch?: [number, number]; desk?: number};
export type SetInfo = {furniture: Furniture; floorAt: (x: number) => number; outdoor: boolean};

// x in 0..100 -> pixels
export const px = (x: number) => 150 + (W - 300) * (x / 100);

const WALLS: Record<Light, [string, string]> = {
  night: ['#161922', '#0C0D12'], lamp: ['#1F1B1A', '#0F0D0D'], dawn: ['#231C24', '#120E14'], day: ['#2A303B', '#1A1E26'],
  dusk: ['#251B26', '#120D14'], grey: ['#1C1C1E', '#0E0E10'], neon: ['#1E1420', '#0D080F'],
};
const SKIES: Record<Light, [string, string]> = {
  night: ['#0E1630', '#1D2B4F'], lamp: ['#0E1630', '#1D2B4F'], dawn: ['#3A2D52', '#E39A7A'], day: ['#6FA8DC', '#BFD9EE'],
  dusk: ['#3B2148', '#E0794E'], grey: ['#2A2A2E', '#4A4A50'], neon: ['#1A0F2A', '#3A1640'],
};

export const setInfo = (name: SetName): SetInfo => {
  const flat = () => FLOOR;
  switch (name) {
    case 'bedroom': return {furniture: {bed: [34, 58], chair: 82, desk: 86}, floorAt: flat, outdoor: false};
    case 'desk': return {furniture: {chair: 48, desk: 56}, floorAt: flat, outdoor: false};
    case 'living': return {furniture: {couch: [30, 52]}, floorAt: flat, outdoor: false};
    case 'kitchen': return {furniture: {chair: 70, desk: 76}, floorAt: flat, outdoor: false};
    case 'cafe': return {furniture: {chair: 20}, floorAt: flat, outdoor: false};
    case 'classroom': return {furniture: {chair: 40, desk: 46}, floorAt: flat, outdoor: false};
    case 'office': return {furniture: {chair: 44, desk: 50}, floorAt: flat, outdoor: false};
    case 'busstop': return {furniture: {couch: [40, 56]}, floorAt: flat, outdoor: true};
    case 'park': return {furniture: {couch: [44, 58]}, floorAt: flat, outdoor: true};
    case 'court': return {furniture: {couch: [30, 40]}, floorAt: flat, outdoor: true};
    case 'stage': return {furniture: {chair: 62}, floorAt: () => FLOOR - 70, outdoor: false};
    case 'stairs': return {furniture: {}, floorAt: (x) => FLOOR + 140 - (x - 100) * 0.5, outdoor: false};
    case 'street':
    case 'rooftop':
    case 'hill': return {furniture: {}, floorAt: flat, outdoor: true};
    default: return {furniture: {}, floorAt: flat, outdoor: false};
  }
};

// ---------- pieces ----------

const Room: React.FC<{light: Light}> = ({light}) => {
  const [a, b] = WALLS[light] ?? WALLS.night;
  return (
    <>
      <defs>
        <linearGradient id={`wall-${light}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={a} /><stop offset="1" stopColor={b} /></linearGradient>
      </defs>
      <rect width={W} height={H} fill={`url(#wall-${light})`} />
      <rect y={FLOOR} width={W} height={H - FLOOR} fill="#0B0C10" />
      <line x1={0} y1={FLOOR} x2={W} y2={FLOOR} stroke={LINE} strokeWidth={2.5} />
    </>
  );
};

const Sky: React.FC<{light: Light; id: string}> = ({light, id}) => {
  const [a, b] = SKIES[light] ?? SKIES.night;
  return <linearGradient id={id} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={a} /><stop offset="1" stopColor={b} /></linearGradient>;
};

const Window: React.FC<{x: number; y: number; w: number; h: number; light: Light; view?: 'moon' | 'city'}> = ({x, y, w, h, light, view = 'moon'}) => (
  <g>
    <defs><Sky light={light} id={`sky-${x}`} /></defs>
    <rect x={x} y={y} width={w} height={h} rx={10} fill={`url(#sky-${x})`} stroke={LINE} strokeWidth={3} />
    {view === 'city' ? Array.from({length: 7}, (_, i) => {
      const bw = w / 7, bh = h * (0.3 + random(`wb${x}${i}`) * 0.45);
      return <g key={i}><rect x={x + i * bw} y={y + h - bh} width={bw - 4} height={bh} fill="#0E1220" />
        {Array.from({length: 6}, (_, j) => random(`wl${x}${i}${j}`) < 0.4 ? <rect key={j} x={x + i * bw + 6 + (j % 2) * 14} y={y + h - bh + 10 + Math.floor(j / 2) * 18} width={7} height={9} fill="#E9C46A" opacity={0.8} /> : null)}</g>;
    }) : null}
    {view === 'moon' && (light === 'night' || light === 'lamp' || light === 'neon' || light === 'grey') ? <circle cx={x + w * 0.7} cy={y + h * 0.3} r={Math.min(w, h) * 0.12} fill="#E8E6DA" /> : null}
    {view === 'moon' && (light === 'dawn' || light === 'dusk') ? <circle cx={x + w * 0.5} cy={y + h * 0.85} r={Math.min(w, h) * 0.2} fill="#F2B36B" opacity={0.85} /> : null}
    <line x1={x + w / 2} y1={y} x2={x + w / 2} y2={y + h} stroke={LINE} strokeWidth={3} />
    <line x1={x} y1={y + h / 2} x2={x + w} y2={y + h / 2} stroke={LINE} strokeWidth={3} />
  </g>
);

const Beam: React.FC<{from: [number, number, number]; to: [number, number, number]; color: string; opacity: number}> = ({from, to, color, opacity}) => (
  <g>
    <defs>
      <linearGradient id={`beam-${from[0]}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={color} stopOpacity={opacity} /><stop offset="1" stopColor={color} stopOpacity={opacity * 0.25} /></linearGradient>
    </defs>
    <polygon points={`${from[0]},${from[1]} ${from[0] + from[2]},${from[1]} ${to[0] + to[2]},${to[1]} ${to[0]},${to[1]}`} fill={`url(#beam-${from[0]})`} />
  </g>
);

const Pool: React.FC<{x: number; y: number; r: number; color: string; opacity: number}> = ({x, y, r, color, opacity}) => (
  <g>
    <defs><radialGradient id={`pool-${x}-${y}`}><stop offset="0" stopColor={color} stopOpacity={opacity} /><stop offset="1" stopColor={color} stopOpacity={0} /></radialGradient></defs>
    <ellipse cx={x} cy={y} rx={r} ry={r * 0.55} fill={`url(#pool-${x}-${y})`} />
  </g>
);

// A red seven-segment alarm clock (the time is story in these films).
export const Digits: React.FC<{text: string; x: number; y: number; h: number; color?: string}> = ({text, x, y, h, color = '#FF3B3B'}) => {
  const SEG: Record<string, string> = {'0': 'abcdef', '1': 'bc', '2': 'abged', '3': 'abgcd', '4': 'fgbc', '5': 'afgcd', '6': 'afgedc', '7': 'abc', '8': 'abcdefg', '9': 'abfgcd'};
  const w = h * 0.55, t = h * 0.12;
  let cx = x;
  const out: React.ReactNode[] = [];
  for (const ch of text) {
    if (ch === ':') {
      out.push(<g key={cx}><rect x={cx + t * 0.4} y={y + h * 0.28} width={t} height={t} fill={color} /><rect x={cx + t * 0.4} y={y + h * 0.62} width={t} height={t} fill={color} /></g>);
      cx += t * 2.2;
      continue;
    }
    const on = SEG[ch] ?? '';
    const seg = (k: string, sx: number, sy: number, sw: number, sh: number) => (
      <rect key={k} x={cx + sx} y={y + sy} width={sw} height={sh} rx={t / 2} fill={color} opacity={on.includes(k) ? 1 : 0.08} />
    );
    out.push(<g key={cx}>{seg('a', t, 0, w - 2 * t, t)}{seg('g', t, h / 2 - t / 2, w - 2 * t, t)}{seg('d', t, h - t, w - 2 * t, t)}
      {seg('f', 0, t / 2, t, h / 2 - t / 2)}{seg('b', w - t, t / 2, t, h / 2 - t / 2)}{seg('e', 0, h / 2, t, h / 2 - t / 2)}{seg('c', w - t, h / 2, t, h / 2 - t / 2)}</g>);
    cx += w + t * 1.2;
  }
  return <g style={{filter: `drop-shadow(0 0 ${h * 0.12}px ${color})`}}>{out}</g>;
};

const Bed: React.FC<{x0: number; x1: number}> = ({x0, x1}) => {
  const a = px(x0) - 60, b = px(x1) + 60;
  return (
    <g stroke={LINE} strokeWidth={3} fill={FILL}>
      <rect x={a} y={FLOOR - 230} width={18} height={230} />
      <rect x={a} y={FLOOR - 150} width={b - a} height={70} rx={10} fill="#232A3A" />
      <path d={`M${a + 60},${FLOOR - 150} C${a + 200},${FLOOR - 200} ${b - 40},${FLOOR - 180} ${b},${FLOOR - 150} L${b},${FLOOR - 92} L${a + 60},${FLOOR - 92} Z`} fill="#2C3550" />
      <ellipse cx={a + 70} cy={FLOOR - 162} rx={52} ry={18} fill="#3A4256" />
      <line x1={a + 18} y1={FLOOR - 80} x2={a + 18} y2={FLOOR} />
      <line x1={b - 6} y1={FLOOR - 80} x2={b - 6} y2={FLOOR} />
    </g>
  );
};

const Nightstand: React.FC<{x: number; clock?: string}> = ({x, clock}) => (
  <g>
    <rect x={x} y={FLOOR - 150} width={150} height={150} rx={6} fill={FILL} stroke={LINE} strokeWidth={3} />
    <line x1={x + 50} y1={FLOOR - 76} x2={x + 100} y2={FLOOR - 76} stroke={LINE} strokeWidth={3} />
    <rect x={x + 18} y={FLOOR - 214} width={114} height={60} rx={8} fill="#0B0B0E" stroke={LINE} strokeWidth={2.5} />
    {clock ? <Digits text={clock} x={x + 30} y={FLOOR - 204} h={40} /> : null}
  </g>
);

const Desk: React.FC<{x: number; lamp?: boolean; screen?: boolean}> = ({x, lamp = true, screen}) => (
  <g stroke={LINE} strokeWidth={3} fill={FILL}>
    <rect x={x - 40} y={FLOOR - 200} width={380} height={16} />
    <line x1={x - 30} y1={FLOOR - 184} x2={x - 30} y2={FLOOR} />
    <line x1={x + 330} y1={FLOOR - 184} x2={x + 330} y2={FLOOR} />
    {lamp ? <g><line x1={x + 280} y1={FLOOR - 200} x2={x + 250} y2={FLOOR - 300} /><path d={`M${x + 210},${FLOOR - 300} L${x + 290},${FLOOR - 300} L${x + 270},${FLOOR - 330} L${x + 230},${FLOOR - 330} Z`} /></g> : null}
    {screen ? <g><rect x={x + 60} y={FLOOR - 340} width={170} height={110} rx={6} fill="#2A3A5A" /><line x1={x + 145} y1={FLOOR - 230} x2={x + 145} y2={FLOOR - 200} /></g> : null}
  </g>
);

const Chair: React.FC<{x: number}> = ({x}) => (
  <g stroke={LINE} strokeWidth={3} fill="none">
    <line x1={x - 40} y1={FLOOR - 118} x2={x + 40} y2={FLOOR - 118} />
    <line x1={x - 36} y1={FLOOR - 118} x2={x - 36} y2={FLOOR} />
    <line x1={x + 36} y1={FLOOR - 118} x2={x + 36} y2={FLOOR} />
    <line x1={x - 40} y1={FLOOR - 118} x2={x - 46} y2={FLOOR - 250} />
  </g>
);

const Door: React.FC<{x: number; open?: number; light?: boolean}> = ({x, open = 0, light}) => (
  <g>
    <rect x={x} y={FLOOR - 340} width={150} height={340} fill={light ? '#E8B86A' : '#121418'} stroke={LINE} strokeWidth={3} />
    {light ? <polygon points={`${x},${FLOOR} ${x + 150},${FLOOR} ${x + 320},${H} ${x - 170},${H}`} fill="#E8B86A" opacity={0.15} /> : null}
    <rect x={x} y={FLOOR - 340} width={150 * (1 - open)} height={340} fill={FILL} stroke={LINE} strokeWidth={3} />
    <circle cx={x + 130 * (1 - open)} cy={FLOOR - 170} r={6} fill={LINE} />
  </g>
);

const Couch: React.FC<{x0: number; x1: number}> = ({x0, x1}) => {
  const a = px(x0) - 80, b = px(x1) + 80;
  return (
    <g stroke={LINE} strokeWidth={3} fill="#272C3B">
      <rect x={a} y={FLOOR - 230} width={b - a} height={120} rx={26} />
      <rect x={a - 30} y={FLOOR - 170} width={60} height={150} rx={20} />
      <rect x={b - 30} y={FLOOR - 170} width={60} height={150} rx={20} />
      <rect x={a + 20} y={FLOOR - 130} width={b - a - 40} height={70} rx={14} fill="#2F3546" />
      <line x1={a + 10} y1={FLOOR - 20} x2={a + 10} y2={FLOOR} />
      <line x1={b - 10} y1={FLOOR - 20} x2={b - 10} y2={FLOOR} />
    </g>
  );
};

const Shelf: React.FC<{x: number; y: number}> = ({x, y}) => (
  <g>
    {[0, 1, 2].map((r) => (
      <g key={r}>
        <line x1={x} y1={y + r * 90} x2={x + 220} y2={y + r * 90} stroke={LINE} strokeWidth={3} />
        {Array.from({length: 9}, (_, i) => (
          <rect key={i} x={x + 8 + i * 23} y={y + r * 90 - 60 - random(`bk${x}${r}${i}`) * 16} width={18} height={60 + random(`bk${x}${r}${i}`) * 16}
            fill={['#7A3E3E', '#3E5A7A', '#7A6A3E', '#3E7A5A', '#5A3E7A'][(i + r) % 5]} opacity={0.7} />
        ))}
      </g>
    ))}
  </g>
);

const Note: React.FC<{x: number; y: number; title?: string}> = ({x, y, title = 'PLAN'}) => (
  <g transform={`rotate(-4,${x},${y})`}>
    <rect x={x} y={y} width={110} height={130} fill="#E9DDB0" opacity={0.92} />
    <text x={x + 55} y={y + 28} textAnchor="middle" fontFamily="Comic Neue" fontWeight={700} fontSize={20} fill="#333">{title}</text>
    {[0, 1, 2].map((i) => <g key={i}><rect x={x + 14} y={y + 46 + i * 26} width={12} height={12} fill="none" stroke="#555" strokeWidth={2} /><line x1={x + 34} y1={y + 52 + i * 26} x2={x + 92} y2={y + 52 + i * 26} stroke="#777" strokeWidth={3} /></g>)}
  </g>
);

const Plant: React.FC<{x: number}> = ({x}) => (
  <g stroke={LINE} strokeWidth={2.5}>
    <path d={`M${x - 30},${FLOOR - 90} L${x + 30},${FLOOR - 90} L${x + 22},${FLOOR} L${x - 22},${FLOOR} Z`} fill={FILL} />
    {[-50, -20, 10, 40].map((a, i) => <ellipse key={i} cx={x + a * 0.8} cy={FLOOR - 150 - Math.abs(a)} rx={18} ry={46} transform={`rotate(${a},${x + a * 0.8},${FLOOR - 150 - Math.abs(a)})`} fill="#26402F" />)}
  </g>
);

const Skyline: React.FC<{y: number; color?: string; lights?: boolean; seed?: string}> = ({y, color = '#0D111C', lights = true, seed = 's'}) => (
  <g>
    {Array.from({length: 16}, (_, i) => {
      const w = 90 + random(`${seed}w${i}`) * 80, h = 140 + random(`${seed}h${i}`) * 300;
      const x = i * 124 - 20;
      return <g key={i}><rect x={x} y={y - h} width={w} height={h} fill={color} />
        {lights ? Array.from({length: 12}, (_, j) => random(`${seed}l${i}${j}`) < 0.33 ? <rect key={j} x={x + 12 + (j % 3) * 26} y={y - h + 20 + Math.floor(j / 3) * 34} width={10} height={14} fill="#F1C76B" opacity={0.75} /> : null) : null}</g>;
    })}
  </g>
);

const Lamp: React.FC<{x: number; y: number}> = ({x, y}) => (
  <g stroke={LINE} strokeWidth={3}>
    <line x1={x} y1={y} x2={x} y2={FLOOR} />
    <path d={`M${x - 20},${y} Q${x},${y - 16} ${x + 40},${y + 4}`} fill="none" />
    <circle cx={x + 40} cy={y + 8} r={9} fill="#F6D58E" stroke="none" />
  </g>
);

const Rain: React.FC<{t: number}> = ({t}) => (
  <g stroke="rgba(190,205,230,0.35)" strokeWidth={2}>
    {Array.from({length: 120}, (_, i) => {
      const x = random(`rx${i}`) * W;
      const y = ((random(`ry${i}`) * H + t * 900) % (H + 60)) - 60;
      return <line key={i} x1={x} y1={y} x2={x - 8} y2={y + 34} />;
    })}
  </g>
);

// ---------- the sets ----------

export const SetView: React.FC<{name: SetName; light: Light; clock?: string; t: number; accent: string}> = ({name, light, clock, t, accent}) => {
  const f = setInfo(name).furniture;
  const nightish = light === 'night' || light === 'grey' || light === 'neon' || light === 'lamp';
  switch (name) {
    case 'bedroom':
      return (
        <g>
          <Room light={light} />
          <Window x={px(42)} y={150} w={250} h={230} light={light} />
          {nightish ? <Beam from={[px(42), 380, 250]} to={[px(38), FLOOR, 520]} color="#9FB4E8" opacity={0.16} /> : null}
          <Note x={px(22)} y={300} />
          <Bed x0={f.bed![0]} x1={f.bed![1]} />
          <Nightstand x={px(f.bed![0]) - 260} clock={clock} />
          <Desk x={px(76)} lamp screen={false} />
          <Chair x={px(f.chair!)} />
          <Plant x={px(97)} />
          {light === 'lamp' ? <Pool x={px(88)} y={FLOOR - 120} r={420} color="#F3C27A" opacity={0.18} /> : null}
          <ellipse cx={px(46)} cy={FLOOR + 50} rx={420} ry={40} fill="#14171F" />
        </g>
      );
    case 'desk':
      return (
        <g>
          <Room light={light} />
          <Shelf x={px(4)} y={330} />
          <rect x={px(28)} y={190} width={330} height={210} fill="#4A3A2A" stroke={LINE} strokeWidth={3} />
          {Array.from({length: 7}, (_, i) => <rect key={i} x={px(29) + (i % 4) * 78} y={206 + Math.floor(i / 4) * 92} width={58} height={56} fill={['#E9DDB0', '#B8D8E8', '#F2C4C4', '#C8E6C0'][i % 4]} transform={`rotate(${(i % 3 - 1) * 5},${px(29) + (i % 4) * 78 + 29},${236 + Math.floor(i / 4) * 92})`} />)}
          <Window x={px(66)} y={170} w={360} h={250} light={light} view="city" />
          <Desk x={px(50)} lamp screen />
          <Chair x={px(f.chair!)} />
          {nightish ? <Pool x={px(62)} y={FLOOR - 180} r={360} color="#F3C27A" opacity={0.22} /> : null}
        </g>
      );
    case 'living':
      return (
        <g>
          <Room light={light} />
          <Window x={px(6)} y={170} w={260} h={250} light={light} />
          <Couch x0={f.couch![0]} x1={f.couch![1]} />
          <g stroke={LINE} strokeWidth={3} fill="#0E0F14"><rect x={px(76)} y={FLOOR - 330} width={300} height={180} rx={8} /><rect x={px(78)} y={FLOOR - 150} width={250} height={60} fill={FILL} /></g>
          <Lamp x={px(64)} y={FLOOR - 360} />
          {light === 'lamp' || nightish ? <Pool x={px(66)} y={FLOOR - 160} r={380} color="#F3C27A" opacity={0.16} /> : null}
          <ellipse cx={px(42)} cy={FLOOR + 60} rx={460} ry={46} fill="#1A1C24" />
        </g>
      );
    case 'kitchen':
      return (
        <g>
          <Room light={light} />
          <g stroke={LINE} strokeWidth={3} fill={FILL}>
            <rect x={px(2)} y={FLOOR - 400} width={150} height={400} rx={8} fill="#D9DCDF" opacity={0.85} />
            <rect x={px(12)} y={FLOOR - 180} width={620} height={180} fill="#2E3B33" />
            <rect x={px(12)} y={FLOOR - 196} width={620} height={16} />
            <rect x={px(12)} y={FLOOR - 470} width={620} height={150} fill="#2E3B33" />
          </g>
          <Window x={px(56)} y={200} w={220} h={200} light={light} />
          <g stroke={LINE} strokeWidth={3} fill={FILL}><rect x={px(64)} y={FLOOR - 200} width={240} height={14} /><line x1={px(65)} y1={FLOOR - 186} x2={px(65)} y2={FLOOR} /><line x1={px(64) + 230} y1={FLOOR - 186} x2={px(64) + 230} y2={FLOOR} /></g>
          <Chair x={px(f.chair!)} />
          <line x1={px(50)} y1={0} x2={px(50)} y2={170} stroke={LINE} strokeWidth={2} />
          <circle cx={px(50)} cy={182} r={14} fill="#F6D58E" />
          <Pool x={px(50)} y={FLOOR - 200} r={520} color="#F3D9A0" opacity={0.12} />
        </g>
      );
    case 'bathroom':
      return (
        <g>
          <Room light={light} />
          {Array.from({length: 14}, (_, i) => <line key={`v${i}`} x1={i * 140} y1={0} x2={i * 140} y2={FLOOR} stroke={LINE_DIM} strokeWidth={1} />)}
          {Array.from({length: 7}, (_, i) => <line key={`h${i}`} x1={0} y1={i * 130} x2={W} y2={i * 130} stroke={LINE_DIM} strokeWidth={1} />)}
          <rect x={px(48)} y={200} width={360} height={300} rx={20} fill="#2C3440" stroke={LINE} strokeWidth={4} />
          <rect x={px(50)} y={160} width={300} height={12} rx={6} fill="#E8EEF4" />
          <g stroke={LINE} strokeWidth={3} fill={FILL}><path d={`M${px(50)},${FLOOR - 300} L${px(50) + 300},${FLOOR - 300} L${px(50) + 260},${FLOOR - 230} L${px(50) + 40},${FLOOR - 230} Z`} /><rect x={px(50) + 130} y={FLOOR - 230} width={40} height={230} /></g>
        </g>
      );
    case 'hallway':
      return (
        <g>
          <Room light={light} />
          <Door x={px(46)} open={0.55} light />
          <rect x={px(14)} y={300} width={220} height={150} fill="#2B2E37" stroke={LINE} strokeWidth={3} />
          <rect x={px(14) + 16} y={316} width={188} height={118} fill="#3B4252" opacity={0.6} />
          <g stroke={LINE} strokeWidth={3} fill={FILL}><rect x={px(74)} y={FLOOR - 160} width={240} height={160} rx={6} /><line x1={px(74)} y1={FLOOR - 80} x2={px(74) + 240} y2={FLOOR - 80} /></g>
        </g>
      );
    case 'cafe':
      return (
        <g>
          <Room light={light === 'night' ? 'lamp' : light} />
          <Window x={px(2)} y={180} w={300} h={300} light={light} view="city" />
          <rect x={px(56)} y={170} width={420} height={250} rx={10} fill="#1B1D1A" stroke={LINE} strokeWidth={4} />
          <text x={px(56) + 210} y={222} textAnchor="middle" fontFamily="Comic Neue" fontWeight={700} fontSize={34} fill="#EEE">MENU</text>
          {['hot chocolate  3', 'latte  3.5', 'tea  2', 'cookie  2'].map((s, i) => <text key={i} x={px(56) + 210} y={268 + i * 38} textAnchor="middle" fontFamily="Comic Neue" fontSize={24} fill="#DDD">{s}</text>)}
          {[px(30), px(40), px(50)].map((x) => <g key={x}><line x1={x} y1={0} x2={x} y2={120} stroke={LINE} strokeWidth={2} /><circle cx={x} cy={132} r={12} fill="#F6D58E" /></g>)}
          <g stroke={LINE} strokeWidth={3} fill="#4A3426"><rect x={px(46)} y={FLOOR - 220} width={720} height={220} /><rect x={px(46) - 10} y={FLOOR - 236} width={740} height={18} fill="#2A1E16" /></g>
          <Pool x={px(50)} y={FLOOR - 240} r={620} color="#F3C27A" opacity={0.14} />
        </g>
      );
    case 'classroom':
      return (
        <g>
          <Room light={light === 'night' ? 'day' : light} />
          <rect x={px(56)} y={190} width={560} height={300} fill="#22382C" stroke="#8A6B4A" strokeWidth={10} />
          <text x={px(56) + 60} y={270} fontFamily="Caveat" fontSize={52} fill="#E8E8E0">x + 4 = 10</text>
          <Window x={px(6)} y={190} w={260} h={230} light={light === 'night' ? 'day' : light} />
          <circle cx={px(40)} cy={240} r={44} fill="#F4F1EA" stroke={LINE} strokeWidth={3} />
          <line x1={px(40)} y1={240} x2={px(40)} y2={212} stroke="#333" strokeWidth={4} /><line x1={px(40)} y1={240} x2={px(40) + 20} y2={252} stroke="#333" strokeWidth={4} />
          {[px(18), px(46), px(74)].map((x) => <g key={x} stroke={LINE} strokeWidth={3} fill={FILL}><rect x={x - 20} y={FLOOR - 170} width={220} height={14} /><line x1={x} y1={FLOOR - 156} x2={x} y2={FLOOR} /><line x1={x + 180} y1={FLOOR - 156} x2={x + 180} y2={FLOOR} /></g>)}
        </g>
      );
    case 'office':
      return (
        <g>
          <Room light={light} />
          <Window x={px(64)} y={170} w={420} h={260} light={light} view="city" />
          <Desk x={px(40)} lamp={false} screen />
          <Chair x={px(f.chair!)} />
          <Desk x={px(6)} lamp={false} screen />
        </g>
      );
    case 'gym':
      return (
        <g>
          <Room light="lamp" />
          {[px(8), px(80)].map((x, i) => <g key={x} transform={`rotate(${i ? 3 : -3},${x + 60},${300})`}><rect x={x} y={220} width={130} height={170} fill="#C4A57A" opacity={0.75} /><text x={x + 65} y={270} textAnchor="middle" fontFamily="Comic Neue" fontWeight={700} fontSize={26} fill="#5A2E1E">{i ? 'NO DAYS OFF' : 'STRONGER'}</text></g>)}
          <g stroke={LINE} strokeWidth={3} fill={FILL}><rect x={px(10)} y={FLOOR - 220} width={300} height={14} /><line x1={px(10)} y1={FLOOR - 206} x2={px(10)} y2={FLOOR} /><line x1={px(10) + 300} y1={FLOOR - 206} x2={px(10) + 300} y2={FLOOR} />
            {[0, 1, 2, 3].map((i) => <g key={i}><circle cx={px(11) + i * 74} cy={FLOOR - 236} r={20} /><circle cx={px(11) + i * 74} cy={FLOOR - 120} r={18} /></g>)}</g>
          <line x1={px(50)} y1={0} x2={px(50)} y2={150} stroke={LINE} strokeWidth={3} />
          <path d={`M${px(50) - 90},210 L${px(50) + 90},210 L${px(50) + 50},150 L${px(50) - 50},150 Z`} fill="#3A3026" stroke={LINE} strokeWidth={3} />
          <polygon points={`${px(50) - 80},210 ${px(50) + 80},210 ${px(50) + 380},${FLOOR + 40} ${px(50) - 380},${FLOOR + 40}`} fill="#F3C27A" opacity={0.12} />
          <Pool x={px(50)} y={FLOOR + 10} r={420} color="#F3C27A" opacity={0.3} />
          {Array.from({length: 12}, (_, i) => <line key={i} x1={i * 170} y1={FLOOR} x2={i * 170 - 60} y2={H} stroke={LINE_DIM} strokeWidth={1.5} />)}
        </g>
      );
    case 'stairs':
      return (
        <g>
          <rect width={W} height={H} fill={WALLS[light]?.[1] ?? '#0C0D12'} />
          <path d={`M${0},${H} ${Array.from({length: 26}, (_, i) => `L${80 + i * 72},${FLOOR + 160 - i * 36 - 36} L${80 + (i + 1) * 72},${FLOOR + 160 - i * 36 - 36}`).join(' ')} L${W},${H} Z`} fill="#15161B" stroke={LINE} strokeWidth={3} />
          <line x1={80} y1={FLOOR + 70} x2={W} y2={FLOOR + 70 - (W - 80) * 0.5} stroke={LINE} strokeWidth={3} />
        </g>
      );
    case 'street':
      return (
        <g>
          <defs><Sky light={light === 'day' ? 'day' : light === 'dawn' ? 'dawn' : light === 'dusk' ? 'dusk' : 'night'} id="streetSky" /></defs>
          <rect width={W} height={H} fill="url(#streetSky)" />
          <Skyline y={FLOOR - 40} seed="st" lights={light !== 'day'} />
          {[px(10), px(45), px(80)].map((x) => <g key={x}><line x1={x} y1={FLOOR - 360} x2={x} y2={FLOOR} stroke={LINE} strokeWidth={4} /><circle cx={x + 20} cy={FLOOR - 360} r={10} fill="#F6D58E" /><Pool x={x + 20} y={FLOOR + 30} r={200} color="#F6D58E" opacity={0.2} /></g>)}
          <rect y={FLOOR} width={W} height={H - FLOOR} fill="#14151A" />
          <line x1={0} y1={FLOOR} x2={W} y2={FLOOR} stroke={LINE} strokeWidth={3} />
          {Array.from({length: 10}, (_, i) => <rect key={i} x={i * 200 + 40} y={FLOOR + 120} width={100} height={8} fill="#E8E2C8" opacity={0.6} />)}
        </g>
      );
    case 'busstop':
      return (
        <g>
          <defs><Sky light="night" id="busSky" /></defs>
          <rect width={W} height={H} fill="url(#busSky)" />
          <Skyline y={FLOOR - 40} seed="bs" />
          <rect y={FLOOR} width={W} height={H - FLOOR} fill="#14151A" />
          <g stroke={LINE} strokeWidth={4} fill="rgba(160,190,230,0.12)"><rect x={px(36)} y={FLOOR - 380} width={560} height={14} fill={FILL} /><rect x={px(37)} y={FLOOR - 366} width={520} height={300} /><line x1={px(36) + 10} y1={FLOOR - 366} x2={px(36) + 10} y2={FLOOR} /><line x1={px(36) + 550} y1={FLOOR - 366} x2={px(36) + 550} y2={FLOOR} /></g>
          <g stroke={LINE} strokeWidth={3} fill={FILL}><rect x={px(38)} y={FLOOR - 122} width={460} height={14} /></g>
          <rect x={px(70)} y={FLOOR - 420} width={60} height={40} fill="#2F6FDB" /><line x1={px(70) + 30} y1={FLOOR - 380} x2={px(70) + 30} y2={FLOOR} stroke={LINE} strokeWidth={4} />
          <Rain t={t} />
        </g>
      );
    case 'rooftop':
    case 'hill': {
      const sky = light === 'night' ? 'night' : light === 'day' ? 'day' : light === 'dawn' ? 'dawn' : 'dusk';
      return (
        <g>
          <defs><Sky light={sky} id={`top-${name}`} /></defs>
          <rect width={W} height={H} fill={`url(#top-${name})`} />
          {sky !== 'night' && sky !== 'day' ? <circle cx={W * 0.62} cy={FLOOR - 120} r={150} fill="#F6B66A" opacity={0.9} /> : <circle cx={W * 0.8} cy={180} r={60} fill="#EDEBDD" />}
          {name === 'rooftop' ? <Skyline y={FLOOR - 10} color="#151020" seed="rt" lights={sky === 'night'} /> : (
            <g>
              <path d={`M0,${FLOOR - 140} L320,${FLOOR - 320} L620,${FLOOR - 160} L980,${FLOOR - 380} L1360,${FLOOR - 170} L1700,${FLOOR - 300} L${W},${FLOOR - 200} L${W},${H} L0,${H} Z`} fill="#3A2440" opacity={0.75} />
              <path d={`M0,${FLOOR - 60} L420,${FLOOR - 200} L760,${FLOOR - 90} L1180,${FLOOR - 230} L${W},${FLOOR - 70} L${W},${H} L0,${H} Z`} fill="#261830" />
              <path d={`M${W * 0.36},${H} L${W * 0.5},${FLOOR - 40} L${W * 0.64},${H} Z`} fill="#140D18" />
            </g>
          )}
          {name === 'rooftop' ? <><rect y={FLOOR} width={W} height={H - FLOOR} fill="#0E0B12" /><line x1={0} y1={FLOOR} x2={W} y2={FLOOR} stroke={LINE} strokeWidth={3} /></> : null}
        </g>
      );
    }
    case 'park':
      return (
        <g>
          <defs><Sky light={light === 'night' ? 'night' : light} id="parkSky" /></defs>
          <rect width={W} height={H} fill="url(#parkSky)" />
          {[px(4), px(22), px(70), px(90)].map((x, i) => <g key={x}><rect x={x - 12} y={FLOOR - 220} width={24} height={220} fill="#3A2A1C" /><circle cx={x} cy={FLOOR - 270} r={110 - i * 8} fill="#2F5A3A" /></g>)}
          <rect y={FLOOR} width={W} height={H - FLOOR} fill="#2C4A2E" />
          <g stroke={LINE} strokeWidth={3} fill="#4A3426"><rect x={px(42)} y={FLOOR - 122} width={420} height={18} /><rect x={px(42)} y={FLOOR - 200} width={420} height={14} /></g>
        </g>
      );
    case 'court':
      return (
        <g>
          <defs><Sky light="night" id="courtSky" /></defs>
          <rect width={W} height={H} fill="url(#courtSky)" />
          <Skyline y={FLOOR - 160} seed="ct" />
          <g stroke={LINE_DIM} strokeWidth={2}>{Array.from({length: 40}, (_, i) => <g key={i}><line x1={i * 50} y1={FLOOR - 300} x2={i * 50 + 150} y2={FLOOR} /><line x1={i * 50 + 150} y1={FLOOR - 300} x2={i * 50} y2={FLOOR} /></g>)}</g>
          <line x1={0} y1={FLOOR - 300} x2={W} y2={FLOOR - 300} stroke={LINE} strokeWidth={4} />
          <rect y={FLOOR} width={W} height={H - FLOOR} fill="#2A2420" />
          <g stroke={LINE} strokeWidth={4} fill="none"><line x1={px(82)} y1={FLOOR} x2={px(82)} y2={FLOOR - 460} /><rect x={px(82) - 90} y={FLOOR - 520} width={110} height={80} /><ellipse cx={px(82) - 50} cy={FLOOR - 440} rx={34} ry={8} stroke="#E8812E" /></g>
          <line x1={px(40)} y1={FLOOR - 420} x2={px(40)} y2={FLOOR} stroke={LINE} strokeWidth={4} /><circle cx={px(40) + 20} cy={FLOOR - 420} r={10} fill="#F6D58E" />
          <Pool x={px(46)} y={FLOOR + 30} r={460} color="#F6D58E" opacity={0.22} />
        </g>
      );
    case 'stage':
      return (
        <g>
          <Room light="lamp" />
          {Array.from({length: 14}, (_, i) => <circle key={i} cx={80 + i * 135} cy={70 + Math.sin(i) * 14} r={6} fill="#F6D58E" />)}
          <rect x={px(40)} y={FLOOR - 70} width={W} height={70} fill="#3A2A1E" stroke={LINE} strokeWidth={3} />
          <polygon points={`${px(62) - 60},0 ${px(62) + 60},0 ${px(62) + 260},${FLOOR - 70} ${px(62) - 260},${FLOOR - 70}`} fill="#F6E2B0" opacity={0.16} />
          <line x1={px(78)} y1={FLOOR - 70} x2={px(78)} y2={FLOOR - 300} stroke={LINE} strokeWidth={3} /><circle cx={px(78)} cy={FLOOR - 304} r={10} fill="#333" stroke={LINE} strokeWidth={2} />
          <g stroke={LINE} strokeWidth={3} fill="none"><line x1={px(62) - 34} y1={FLOOR - 188} x2={px(62) + 34} y2={FLOOR - 188} strokeWidth={5} /><line x1={px(62) - 26} y1={FLOOR - 188} x2={px(62) - 38} y2={FLOOR - 70} /><line x1={px(62) + 26} y1={FLOOR - 188} x2={px(62) + 38} y2={FLOOR - 70} /><line x1={px(62) - 32} y1={FLOOR - 120} x2={px(62) + 32} y2={FLOOR - 120} /></g>
          {[px(4), px(14), px(24)].map((x) => <g key={x}><rect x={x} y={FLOOR - 110} width={90} height={14} fill={FILL} stroke={LINE} strokeWidth={2} /><circle cx={x + 45} cy={FLOOR - 124} r={6} fill="#F6B25A" /></g>)}
        </g>
      );
    default:
      return <rect width={W} height={H} fill="#0B0B0E" />;
  }
};

// The colour of the screen light on a face, and the film's neon (the accent) when the voice is near.
export const neonWash = (accent: string) => <rect width={W} height={H} fill={accent} opacity={0.07} style={{mixBlendMode: 'screen'}} />;
