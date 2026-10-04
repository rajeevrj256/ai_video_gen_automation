import React from 'react';
import {interpolate} from 'remotion';
import {shade} from './Mascot';
import type {Backdrop, ToonPalette} from './types';

// Flat, illustrated settings drawn in code (1920x1080), coloured by the video's palette: no photos, no
// stock art. `tone` is the shot's flat colour; `seed` varies the details so two videos never match.

const rnd = (seed: number) => {
  let s = seed * 9301 + 49297;
  return () => {
    s = (s * 9301 + 49297) % 233280;
    return s / 233280;
  };
};

// Soft horizontal brush strokes, the texture over flat colour.
const Strokes: React.FC<{color: string; seed: number; frame: number}> = ({color, seed, frame}) => {
  const r = rnd(seed);
  return (
    <>
      {Array.from({length: 9}, (_, i) => {
        const w = 160 + r() * 360, x = r() * 1920, y = 60 + r() * 960;
        return <rect key={i} x={x - ((frame * (0.15 + r() * 0.2)) % 2200) + 200} y={y} width={w} height={22 + r() * 18} rx={18} fill={color} opacity={0.18} />;
      })}
    </>
  );
};

const Grid: React.FC<{p: ToonPalette; frame: number}> = ({p, frame}) => {
  // A glowing room: back wall grid, floor and ceiling lines running to a vanishing point.
  const lines: React.ReactNode[] = [];
  const glow = p.glow;
  for (let x = 360; x <= 1560; x += 100) lines.push(<line key={`v${x}`} x1={x} y1={220} x2={x} y2={760} />);
  for (let y = 220; y <= 760; y += 90) lines.push(<line key={`h${y}`} x1={360} y1={y} x2={1560} y2={y} />);
  for (let i = 0; i <= 12; i++) {
    const x = 360 + i * 100, fx = (x - 960) * 3.2 + 960;
    lines.push(<line key={`f${i}`} x1={x} y1={760} x2={fx} y2={1080} />, <line key={`c${i}`} x1={x} y1={220} x2={fx} y2={0} />);
  }
  for (let k = 1; k <= 4; k++) {
    const t = k / 4.5, y = 760 + t * 320, x0 = 360 - t * 1300, x1 = 1560 + t * 1300;
    lines.push(<line key={`fl${k}`} x1={x0} y1={y} x2={x1} y2={y} />, <line key={`cl${k}`} x1={x0} y1={220 - t * 220} x2={x1} y2={220 - t * 220} />);
  }
  lines.push(<line key="wl" x1={360} y1={220} x2={-1000} y2={-300} />, <line key="wr" x1={1560} y1={220} x2={2900} y2={-300} />);
  const pulse = 0.55 + 0.15 * Math.sin(frame / 20);
  return (
    <>
      <rect width={1920} height={1080} fill={p.ink} />
      <g stroke={glow} strokeWidth={3} opacity={pulse} style={{filter: `drop-shadow(0 0 6px ${glow})`}}>{lines}</g>
    </>
  );
};

const Sky: React.FC<{p: ToonPalette; tone: string; seed: number; frame: number}> = ({tone, seed, frame}) => {
  const r = rnd(seed);
  return (
    <>
      <rect width={1920} height={1080} fill={shade(tone, 0.45)} />
      {Array.from({length: 5}, (_, i) => {
        const x = ((r() * 1920 + frame * (0.3 + i * 0.1)) % 2300) - 200, y = 90 + r() * 300, s = 0.8 + r() * 0.8;
        return <g key={i} transform={`translate(${x} ${y}) scale(${s})`} fill="#fff" opacity={0.9}>
          <ellipse cx={0} cy={0} rx={90} ry={34} /><ellipse cx={50} cy={-20} rx={60} ry={40} /><ellipse cx={-40} cy={-12} rx={50} ry={30} />
        </g>;
      })}
      <path d="M0 820 Q300 700 640 800 T1280 780 T1920 790 V1080 H0 Z" fill={shade(tone, -0.05)} />
      <path d="M0 900 Q420 820 860 900 T1920 880 V1080 H0 Z" fill={shade(tone, -0.2)} />
    </>
  );
};

const City: React.FC<{p: ToonPalette; tone: string; seed: number}> = ({tone, seed}) => {
  const r = rnd(seed);
  const row = (n: number, base: number, color: string, hmax: number) => {
    let x = -40;
    const out: React.ReactNode[] = [];
    for (let i = 0; i < n && x < 1960; i++) {
      const w = 90 + r() * 140, h = 120 + r() * hmax;
      out.push(<g key={i}>
        <rect x={x} y={base - h} width={w} height={h} fill={color} />
        {Array.from({length: Math.floor(h / 60)}, (_, k) => <rect key={k} x={x + 18} y={base - h + 24 + k * 60} width={w - 36} height={14} rx={3} fill="#fff" opacity={0.12} />)}
      </g>);
      x += w + 10 + r() * 30;
    }
    return out;
  };
  return (
    <>
      <rect width={1920} height={1080} fill={shade(tone, 0.25)} />
      <circle cx={1500} cy={260} r={110} fill="#fff" opacity={0.25} />
      {row(14, 860, shade(tone, -0.15), 420)}
      {row(16, 900, shade(tone, -0.32), 300)}
      <rect y={900} width={1920} height={180} fill={shade(tone, -0.45)} />
    </>
  );
};

const Space: React.FC<{p: ToonPalette; seed: number; frame: number}> = ({p, seed, frame}) => {
  const r = rnd(seed);
  return (
    <>
      <rect width={1920} height={1080} fill={p.ink} />
      {Array.from({length: 70}, (_, i) => {
        const x = r() * 1920, y = r() * 1080, s = 1 + r() * 3, tw = 0.4 + 0.6 * Math.abs(Math.sin(frame / 25 + i));
        return <circle key={i} cx={x} cy={y} r={s} fill="#fff" opacity={tw} />;
      })}
      {Array.from({length: 6}, (_, i) => {
        const x = r() * 1920, y = r() * 1080;
        return <path key={`s${i}`} d={`M${x} ${y - 16} L${x + 4} ${y - 4} L${x + 16} ${y} L${x + 4} ${y + 4} L${x} ${y + 16} L${x - 4} ${y + 4} L${x - 16} ${y} L${x - 4} ${y - 4} Z`} fill={p.glow} opacity={0.8} />;
      })}
    </>
  );
};

const Room: React.FC<{tone: string; kind: 'lab' | 'stage' | 'desk'; p: ToonPalette}> = ({tone, kind, p}) => (
  <>
    <rect width={1920} height={1080} fill={shade(tone, 0.15)} />
    {Array.from({length: 7}, (_, i) => <rect key={i} x={i * 300 - 40} y={0} width={140} height={820} fill="#fff" opacity={0.05} />)}
    <rect y={820} width={1920} height={260} fill={shade(tone, -0.3)} />
    <rect y={812} width={1920} height={14} fill={shade(tone, -0.45)} />
    {kind === 'lab' ? (
      <g>
        <rect x={140} y={300} width={420} height={18} rx={6} fill={shade(tone, -0.4)} />
        {[180, 260, 340, 430, 500].map((x, i) => <path key={x} d={`M${x} ${300} v-${50 + (i % 3) * 20} h22 v${50 + (i % 3) * 20} Z`} fill={[p.accent, p.glow, p.hot, '#fff', p.accent][i]} opacity={0.85} />)}
        <rect x={1380} y={250} width={380} height={240} rx={14} fill={p.ink} stroke={shade(tone, -0.4)} strokeWidth={10} />
        <path d="M1410 430 L1480 380 L1540 410 L1620 320 L1730 360" fill="none" stroke={p.glow} strokeWidth={8} />
      </g>
    ) : kind === 'stage' ? (
      <g>
        <path d="M960 0 L640 1080 H1280 Z" fill="#fff" opacity={0.08} />
        <rect x={760} y={640} width={400} height={200} rx={10} fill={shade(tone, -0.5)} />
        <rect x={720} y={620} width={480} height={36} rx={10} fill={shade(tone, -0.6)} />
        {[880, 960, 1040].map((x) => <g key={x}><line x1={x} y1={620} x2={x + (x - 960) * 0.3} y2={540} stroke="#222" strokeWidth={8} /><ellipse cx={x + (x - 960) * 0.3} cy={530} rx={14} ry={20} fill="#333" /></g>)}
      </g>
    ) : (
      <g>
        <rect x={420} y={640} width={1080} height={40} rx={10} fill={shade(tone, -0.5)} />
        <rect x={470} y={680} width={30} height={160} fill={shade(tone, -0.55)} /><rect x={1420} y={680} width={30} height={160} fill={shade(tone, -0.55)} />
        <rect x={1060} y={440} width={320} height={200} rx={12} fill={p.ink} /><rect x={1200} y={640} width={40} height={10} fill="#333" />
      </g>
    )}
  </>
);

export const BackdropView: React.FC<{kind: Backdrop; p: ToonPalette; tone: string; seed: number; frame: number}> = ({kind, p, tone, seed, frame}) => {
  const drift = interpolate(frame, [0, 300], [0, -20]);
  return (
    <svg viewBox="0 0 1920 1080" width="100%" height="100%" style={{position: 'absolute', inset: 0}} preserveAspectRatio="xMidYMid slice">
      <g transform={`translate(${kind === 'grid' || kind === 'space' ? 0 : drift} 0)`}>
        {kind === 'grid' ? <Grid p={p} frame={frame} />
          : kind === 'sky' ? <Sky p={p} tone={tone} seed={seed} frame={frame} />
          : kind === 'city' ? <City p={p} tone={tone} seed={seed} />
          : kind === 'space' ? <Space p={p} seed={seed} frame={frame} />
          : kind === 'lab' || kind === 'stage' || kind === 'desk' ? <Room tone={tone} kind={kind} p={p} />
          : kind === 'dots' ? (
            <>
              <rect width={1960} height={1080} fill={tone} />
              {Array.from({length: 13 * 8}, (_, i) => <circle key={i} cx={(i % 13) * 160 + ((Math.floor(i / 13) % 2) * 80)} cy={Math.floor(i / 13) * 150 + 40} r={18} fill={shade(tone, 0.2)} opacity={0.5} />)}
            </>
          ) : (
            <>
              <rect width={1960} height={1080} fill={tone} />
              <Strokes color={shade(tone, 0.35)} seed={seed} frame={frame} />
            </>
          )}
      </g>
    </svg>
  );
};
