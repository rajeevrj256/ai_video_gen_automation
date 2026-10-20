import React from 'react';
import type {Design, Setting} from './types';

// The "ink" look of a stick episode (props.art === 'ink'), after the hand-inked explainer style the user
// sent: thick slightly rough black ink outlines, a big round off-white head with small black oval eyes,
// a few loose strokes of hair, softly rounded shoulders and flat muted clothes (navy, brick, olive...),
// sets in tan, sage, dusty grey and cream, a paper grain, fine scanlines, a dark vignette and a
// desaturated grade. Each character's clothes, hair, headwear and things they carry come from their
// design (cast[].design, written per story by reelgen/stickstory.py and kept for that name), so a miner
// gets coveralls, a hard hat with a lamp and boots, and keeps them in every episode. Older videos
// (no art) keep the grey channel look in Story.tsx.

export const INK = '#1E1B18';
const EDGE = 5; // the ink edge either side of a sleeve or trouser leg
export const HEAD_FILL = 'url(#inkHead)';
const SKIN = '#F6F1E6'; // hands, the same off-white as the head

type Pt = [number, number];
type Rig = {hip: Pt; neck: Pt; head: Pt; tilt: number; lE: Pt; lH: Pt; rE: Pt; rH: Pt; lK: Pt; lF: Pt; rK: Pt; rF: Pt};

// ---------- shared defs: the rough ink line and the head's soft shading ----------

export const InkDefs: React.FC = () => (
  <defs>
    <filter id="inkRough" x="-5%" y="-5%" width="110%" height="110%">
      <feTurbulence type="fractalNoise" baseFrequency="0.035" numOctaves={2} seed={7} />
      <feDisplacementMap in="SourceGraphic" scale={3.6} xChannelSelector="R" yChannelSelector="G" />
    </filter>
    <radialGradient id="inkHead" cx="0.42" cy="0.36" r="0.7">
      <stop offset="0.55" stopColor="#F8F4EA" />
      <stop offset="1" stopColor="#DCD3C1" />
    </radialGradient>
  </defs>
);

// Over the finished picture (under the words): paper grain, fine scanlines, a soft dark vignette.
export const InkFinish: React.FC = () => (
  <>
    <svg width="100%" height="100%" style={{position: 'absolute', inset: 0, mixBlendMode: 'multiply', opacity: 0.22, pointerEvents: 'none'}}>
      <filter id="inkGrain">
        <feTurbulence type="fractalNoise" baseFrequency="0.8" numOctaves={3} seed={11} stitchTiles="stitch" />
        <feColorMatrix type="matrix" values="0 0 0 0 0.45  0 0 0 0 0.4  0 0 0 0 0.34  0 0 0 -1.1 1.05" />
      </filter>
      <rect width="100%" height="100%" filter="url(#inkGrain)" />
    </svg>
    <div style={{position: 'absolute', inset: 0, pointerEvents: 'none',
      background: 'repeating-linear-gradient(0deg, rgba(20,16,10,0.07) 0px, rgba(20,16,10,0.07) 1px, transparent 1px, transparent 4px)'}} />
    <div style={{position: 'absolute', inset: 0, pointerEvents: 'none',
      background: 'radial-gradient(ellipse at 50% 46%, rgba(0,0,0,0) 52%, rgba(24,16,8,0.5) 100%)'}} />
  </>
);
// The grade on the drawn scene: a little less colour, a touch warmer.
export const INK_GRADE = 'saturate(0.8) sepia(0.12) contrast(1.03)';

// ---------- the body ----------

// The first part of a quadratic curve p0 -> p2 (control c) up to t, as a path, and the point at t.
const part = (p0: Pt, c: Pt, p2: Pt, t: number): {d: string; end: Pt} => {
  const a: Pt = [p0[0] + (c[0] - p0[0]) * t, p0[1] + (c[1] - p0[1]) * t];
  const b: Pt = [c[0] + (p2[0] - c[0]) * t, c[1] + (p2[1] - c[1]) * t];
  const end: Pt = [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
  return {d: `M ${p0[0]} ${p0[1]} Q ${a[0]} ${a[1]} ${end[0]} ${end[1]}`, end};
};
const rest = (p0: Pt, c: Pt, p2: Pt, t: number): string => {
  const {end} = part(p0, c, p2, t);
  const b: Pt = [c[0] + (p2[0] - c[0]) * t, c[1] + (p2[1] - c[1]) * t];
  return `M ${end[0]} ${end[1]} Q ${b[0]} ${b[1]} ${p2[0]} ${p2[1]}`;
};
// A sleeve or trouser leg: the line drawn wide in ink, then narrower in the cloth's colour.
const Tube: React.FC<{d: string; w: number; fill: string}> = ({d, w, fill}) => (
  <>
    <path d={d} stroke={INK} strokeWidth={w + 2 * EDGE} fill="none" />
    <path d={d} stroke={fill} strokeWidth={w} fill="none" />
  </>
);

const DRESSY = new Set(['dress']);
const LONG_TOPS: Record<string, number> = {coat: 112, kurta: 92, dress: 80}; // how far below the hip the top reaches
const SHORT_SLEEVES = new Set(['tshirt', 'dress']);

export const shoulderAt = (r: Rig, side: -1 | 1): Pt => [r.neck[0] + side * 38, r.neck[1] + 30];

// Legs, shoes, the top and the arms, in drawing order. The head is drawn by the caller on top.
export const InkBody: React.FC<{r: Rig; d: Design; sitting: boolean; under?: React.ReactNode}> = ({r, d, sitting, under}) => {
  const [nx, ny] = r.neck;
  const [hx, hy] = r.hip;
  const top = d.top;
  const cloth = d.topColour;
  const legsCloth = top === 'coveralls' ? cloth : d.bottomColour;
  const bare = DRESSY.has(top) || d.bottom === 'skirt' || d.bottom === 'none';
  const hips: Pt[] = [[hx - 15, hy + 8], [hx + 15, hy + 8]];
  const legs = [[hips[0], r.lK, r.lF], [hips[1], r.rK, r.rF]] as const;
  const legPath = (p: Pt, k: Pt, f: Pt, t = 1) =>
    sitting ? (t >= 1 ? `M ${p[0]} ${p[1]} L ${k[0]} ${k[1]} L ${f[0]} ${f[1]}` : `M ${p[0]} ${p[1]} L ${k[0]} ${k[1]}`) : part(p, k, f, t).d;
  const shins = (p: Pt, k: Pt, f: Pt, t: number) => (sitting ? `M ${k[0]} ${k[1]} L ${f[0]} ${f[1]}` : rest(p, k, f, t));
  const long = LONG_TOPS[top] ?? 0;
  const hem = hy + (top === 'dress' ? (sitting ? 34 : long) : long ? (sitting ? 40 : long) : 22);
  const half = top === 'dress' ? (sitting ? 70 : 62) : long ? 52 : 42;
  const S = 46;
  const torso = `M ${nx - S + 12} ${ny + 12} Q ${nx - S - 2} ${ny + 16} ${nx - S} ${ny + 46} L ${hx - half} ${hem} `
    + `Q ${hx} ${hem + 10} ${hx + half} ${hem} L ${nx + S} ${ny + 46} Q ${nx + S + 2} ${ny + 16} ${nx + S - 12} ${ny + 12} `
    + `Q ${nx} ${ny + 2} ${nx - S + 12} ${ny + 12} Z`;
  const sleeveT = SHORT_SLEEVES.has(top) ? 0.42 : 0.86;
  const arms = [[shoulderAt(r, -1), r.lE, r.lH], [shoulderAt(r, 1), r.rE, r.rH]] as const;
  const has = (x: string) => d.extras.includes(x as never);
  const extra = d.extraColour || '#8A6A44';
  return (
    <g strokeLinecap="round" strokeLinejoin="round">
      {has('backpack') ? <rect x={nx - 84} y={ny + 30} width={44} height={110} rx={14} fill={extra} stroke={INK} strokeWidth={EDGE} /> : null}
      {/* legs: trousers as wide tubes, shorts to the knee, bare stick legs under a dress or skirt */}
      {legs.map(([p, k, f], i) =>
        bare ? (
          <path key={i} d={legPath(p, k, f)} stroke={INK} strokeWidth={6} fill="none" />
        ) : d.bottom === 'shorts' && top !== 'coveralls' ? (
          <g key={i}>
            <path d={shins(p, k, f, 0.5)} stroke={INK} strokeWidth={6} fill="none" />
            <Tube d={legPath(p, k, f, 0.5)} w={30} fill={legsCloth} />
          </g>
        ) : (
          <Tube key={i} d={legPath(p, k, f, sitting ? 1 : 0.94)} w={26} fill={legsCloth} />
        ),
      )}
      {legs.map(([, , f], i) => <Shoe key={`s${i}`} at={f} kind={d.shoes} colour={d.shoesColour} />)}
      {/* the top */}
      {top === 'hoodie' ? <ellipse cx={nx} cy={ny + 10} rx={54} ry={24} fill={cloth} stroke={INK} strokeWidth={EDGE} /> : null}
      <path d={torso} fill={cloth} stroke={INK} strokeWidth={EDGE + 1} />
      {d.bottom === 'skirt' && !DRESSY.has(top) ? (
        <path d={`M ${hx - 44} ${hy + 14} L ${hx - 64} ${hy + (sitting ? 46 : 82)} Q ${hx} ${hy + (sitting ? 54 : 92)} ${hx + 64} ${hy + (sitting ? 46 : 82)} L ${hx + 44} ${hy + 14} Z`}
          fill={d.bottomColour} stroke={INK} strokeWidth={EDGE} />
      ) : null}
      <TopDetail top={top} nx={nx} ny={ny} hx={hx} hy={hy} hem={hem} />
      {has('apron') ? (
        <path d={`M ${nx - 26} ${ny + 52} h 52 L ${hx + 40} ${hy + 70} Q ${hx} ${hy + 76} ${hx - 40} ${hy + 70} Z`} fill={extra} stroke={INK} strokeWidth={EDGE - 1} />
      ) : null}
      {has('tie') || top === 'suit' ? (
        <path d={`M ${nx - 7} ${ny + 14} h 14 l -3 10 l 9 64 l -13 16 l -13 -16 l 9 -64 Z`} fill={has('tie') ? extra : '#6E3434'} stroke={INK} strokeWidth={3.5} />
      ) : null}
      {has('lanyard') ? (
        <g stroke={INK} strokeWidth={3}>
          <path d={`M ${nx - 22} ${ny + 14} L ${nx} ${ny + 74} L ${nx + 22} ${ny + 14}`} stroke={extra} strokeWidth={5} fill="none" />
          <rect x={nx - 16} y={ny + 72} width={32} height={40} rx={4} fill="#EDE6D6" />
        </g>
      ) : null}
      {has('stethoscope') ? (
        <path d={`M ${nx - 30} ${ny + 18} Q ${nx - 34} ${ny + 90} ${nx} ${ny + 96} Q ${nx + 20} ${ny + 96} ${nx + 22} ${ny + 70}`} stroke="#5D6266" strokeWidth={6} fill="none" />
      ) : null}
      {has('satchel') ? (
        <g>
          <path d={`M ${nx + 34} ${ny + 18} L ${hx - 34} ${hy - 4}`} stroke={INK} strokeWidth={16} />
          <path d={`M ${nx + 34} ${ny + 18} L ${hx - 34} ${hy - 4}`} stroke={extra} strokeWidth={8} />
          <rect x={hx - 66} y={hy - 18} width={58} height={46} rx={8} fill={extra} stroke={INK} strokeWidth={EDGE - 1} />
          <path d={`M ${hx - 66} ${hy - 2} h 58`} stroke={INK} strokeWidth={3} />
        </g>
      ) : null}
      {has('scarf') ? (
        <g>
          <path d={`M ${nx - 34} ${ny + 14} Q ${nx} ${ny + 34} ${nx + 34} ${ny + 14}`} stroke={INK} strokeWidth={30} fill="none" />
          <path d={`M ${nx - 34} ${ny + 14} Q ${nx} ${ny + 34} ${nx + 34} ${ny + 14}`} stroke={extra} strokeWidth={20} fill="none" />
          <path d={`M ${nx + 16} ${ny + 26} l 10 62 h 18 l -6 -64 Z`} fill={extra} stroke={INK} strokeWidth={4} />
        </g>
      ) : null}
      {/* arms: a sleeve from the shoulder, then the bare stick forearm and a small hand */}
      {arms.map(([s, e, h], i) => (
        <g key={`a${i}`}>
          <path d={rest(s, e, h, sleeveT)} stroke={INK} strokeWidth={6} fill="none" />
          <Tube d={part(s, e, h, sleeveT).d} w={24} fill={cloth} />
          <circle cx={h[0]} cy={h[1]} r={10} fill={SKIN} stroke={INK} strokeWidth={4} />
          {has('watch') && i === 0 ? <circle cx={part(s, e, h, 0.9).end[0]} cy={part(s, e, h, 0.9).end[1]} r={7} fill="#C9B26A" stroke={INK} strokeWidth={3} /> : null}
        </g>
      ))}
      {under}
    </g>
  );
};

const TopDetail: React.FC<{top: string; nx: number; ny: number; hx: number; hy: number; hem: number}> = ({top, nx, ny, hx, hy, hem}) => {
  const line = {stroke: INK, strokeWidth: 3.5, fill: 'none'};
  switch (top) {
    case 'hoodie':
      return (
        <g {...line}>
          <path d={`M ${nx - 10} ${ny + 14} v 36 M ${nx + 10} ${ny + 14} v 32`} />
          <path d={`M ${hx - 30} ${hy - 30} h 60 l 8 36 h -76 Z`} />
        </g>
      );
    case 'tshirt':
      return <path d={`M ${nx - 18} ${ny + 8} Q ${nx} ${ny + 26} ${nx + 18} ${ny + 8}`} {...line} />;
    case 'shirt':
      return (
        <g {...line}>
          <path d={`M ${nx - 18} ${ny + 6} L ${nx - 2} ${ny + 30} L ${nx - 4} ${ny + 8} M ${nx + 18} ${ny + 6} L ${nx + 2} ${ny + 30} L ${nx + 4} ${ny + 8}`} />
          {[0, 1, 2].map((k) => <circle key={k} cx={nx} cy={ny + 50 + k * 34} r={3} fill={INK} stroke="none" />)}
        </g>
      );
    case 'jacket':
    case 'suit':
      return (
        <g>
          <path d={`M ${nx - 16} ${ny + 8} L ${nx} ${ny + 70} L ${nx + 16} ${ny + 8} Z`} fill="#EDE6D6" stroke={INK} strokeWidth={3.5} />
          <path d={`M ${nx - 24} ${ny + 8} L ${nx - 4} ${ny + 76} L ${hx - 2} ${hem - 4} M ${nx + 24} ${ny + 8} L ${nx + 4} ${ny + 76}`} {...line} />
          <circle cx={hx + 8} cy={hy - 30} r={3.5} fill={INK} />
        </g>
      );
    case 'sweater':
      return (
        <g {...line}>
          <path d={`M ${nx - 20} ${ny + 8} Q ${nx} ${ny + 24} ${nx + 20} ${ny + 8}`} />
          <path d={`M ${hx - 40} ${hem - 14} Q ${hx} ${hem - 6} ${hx + 40} ${hem - 14}`} />
          {[-24, -8, 8, 24].map((x) => <path key={x} d={`M ${hx + x} ${hem - 10} v 10`} strokeWidth={2.5} />)}
        </g>
      );
    case 'coat':
      return (
        <g {...line}>
          <path d={`M ${nx - 26} ${ny + 8} L ${nx - 6} ${ny + 60} M ${nx + 26} ${ny + 8} L ${nx + 6} ${ny + 60}`} />
          <path d={`M ${nx + 4} ${ny + 60} L ${hx + 4} ${hem - 2}`} />
          {[0, 1, 2].map((k) => <circle key={k} cx={nx + 16} cy={ny + 84 + k * 46} r={4} fill={INK} stroke="none" />)}
          <path d={`M ${hx - 44} ${hy - 6} h 88`} strokeWidth={4} />
        </g>
      );
    case 'coveralls':
      return (
        <g {...line}>
          <path d={`M ${nx - 18} ${ny + 6} L ${nx} ${ny + 26} L ${nx + 18} ${ny + 6}`} />
          <path d={`M ${nx} ${ny + 26} L ${hx} ${hy + 8}`} />
          <rect x={nx + 8} y={ny + 46} width={26} height={22} rx={3} />
          <path d={`M ${hx - 42} ${hy - 22} h 84`} strokeWidth={4} />
        </g>
      );
    case 'kurta':
      return (
        <g {...line}>
          <path d={`M ${nx} ${ny + 6} v 52`} />
          {[0, 1, 2].map((k) => <circle key={k} cx={nx + 7} cy={ny + 16 + k * 14} r={2.5} fill={INK} stroke="none" />)}
        </g>
      );
    case 'dress':
      return <path d={`M ${nx - 18} ${ny + 8} Q ${nx} ${ny + 26} ${nx + 18} ${ny + 8} M ${hx - 40} ${hy - 6} Q ${hx} ${hy + 2} ${hx + 40} ${hy - 6}`} {...line} />;
    default:
      return null;
  }
};

const Shoe: React.FC<{at: Pt; kind: string; colour: string}> = ({at, kind, colour}) => {
  const [x, y] = at;
  if (kind === 'boots') {
    return <path d={`M ${x - 16} ${y - 34} h 26 v 18 q 18 2 18 16 h -48 Z`} fill={colour} stroke={INK} strokeWidth={4} />;
  }
  if (kind === 'sneakers') {
    return (
      <g>
        <path d={`M ${x - 18} ${y - 14} q 4 -8 18 -8 q 20 2 24 14 v 8 h -42 Z`} fill={colour} stroke={INK} strokeWidth={4} />
        <path d={`M ${x - 18} ${y - 2} h 42`} stroke="#EDE6D6" strokeWidth={4} />
      </g>
    );
  }
  if (kind === 'sandals') return <path d={`M ${x - 16} ${y} h 40 M ${x - 2} ${y - 2} l 10 -12`} stroke={colour} strokeWidth={6} fill="none" />;
  return <path d={`M ${x - 16} ${y} q 0 -14 16 -14 q 22 0 26 14 Z`} fill={colour} stroke={INK} strokeWidth={4} />;
};

// ---------- the head (drawn for a 64 px head, scaled by the caller) ----------

const R = 64;
export const InkHairBack: React.FC<{d: Design}> = ({d}) => {
  const c = d.hairColour || INK;
  const edge = {stroke: INK, strokeWidth: 4};
  switch (d.hair) {
    case 'long':
      // Two locks falling beside the face onto the shoulders, open under the chin: one solid shape there read as a beard.
      return (
        <g fill={c} {...edge}>
          <path d={`M ${-R + 2} -10 Q ${-R - 14} 60 -60 108 L -30 108 Q -38 74 -38 30 Z`} />
          <path d={`M ${R - 2} -10 Q ${R + 14} 60 60 108 L 30 108 Q 38 74 38 30 Z`} />
        </g>
      );
    case 'ponytail':
      return <path d={`M ${-R + 10} -40 Q ${-R - 40} -30 ${-R - 30} 40 Q ${-R - 14} 10 ${-R + 6} -14 Z`} fill={c} {...edge} />;
    case 'bun':
      return <circle cx={-10} cy={-R - 14} r={24} fill={c} {...edge} />;
    case 'braids':
      return (
        <g fill={c} {...edge}>
          <path d={`M ${-R + 6} -4 q -14 50 -6 96 l 14 0 q -4 -46 8 -90 Z`} />
          <path d={`M ${R - 6} -4 q 14 50 6 96 l -14 0 q 4 -46 -8 -90 Z`} />
        </g>
      );
    default:
      return null;
  }
};

export const InkHair: React.FC<{d: Design}> = ({d}) => {
  const c = d.hairColour || INK;
  const s = {stroke: c, strokeWidth: 3.6, fill: 'none', strokeLinecap: 'round' as const};
  // Under a hat only the strokes below its brim show (the miner's "few strokes beneath the brim").
  const hatted = d.headwear !== 'none' && d.headwear !== 'bow' && d.headwear !== 'headband';
  if (hatted) {
    return d.hair === 'bald' ? null : <path d={`M -52 -26 q 4 10 12 12 M -40 -30 q 2 10 10 14 M 46 -30 q 2 10 -4 16`} {...s} />;
  }
  switch (d.hair) {
    case 'messy':
      return (
        <g {...s}>
          <path d="M -50 -38 Q -46 -70 -14 -78" />
          <path d="M -22 -62 Q -14 -92 12 -88" />
          <path d="M 2 -64 Q 22 -92 40 -76" />
          <path d="M 24 -60 Q 52 -70 58 -44" />
          <path d="M -36 -52 Q -60 -60 -66 -40" />
        </g>
      );
    case 'spiky':
      return <path d="M -54 -34 L -48 -70 L -32 -54 L -22 -84 L -6 -60 L 8 -88 L 20 -60 L 36 -80 L 42 -52 L 58 -60 L 56 -32" {...s} fill={c} fillOpacity={0.9} stroke={INK} />;
    case 'side-part':
      return <path d="M -58 -24 Q -62 -66 -10 -66 Q 46 -68 60 -26 Q 30 -54 -6 -50 Q -36 -48 -58 -24 Z" fill={c} stroke={INK} strokeWidth={3.6} />;
    case 'curly':
      return (
        <g {...s} fill={c} stroke={INK}>
          {[-48, -28, -6, 16, 38, 54].map((x, i) => <circle key={x} cx={x} cy={-50 - Math.cos(((x + 4) / 64) * 1.4) * 14 - (i % 2) * 4} r={14} />)}
        </g>
      );
    case 'short':
      return <path d="M -60 -20 Q -62 -60 -8 -66 Q 52 -66 60 -20 Q 50 -46 0 -48 Q -48 -46 -60 -20 Z" fill={c} stroke={INK} strokeWidth={3.6} />;
    case 'long':
    case 'ponytail':
    case 'braids':
      return <path d="M -60 -12 Q -62 -66 -4 -66 Q 54 -66 62 -12 Q 44 -50 6 -46 Q 30 -40 26 -30 Q -10 -50 -60 -12 Z" fill={c} stroke={INK} strokeWidth={3.6} />;
    case 'bun':
      return <path d="M -60 -16 Q -58 -66 -2 -64 Q 56 -64 60 -16 Q 40 -50 0 -50 Q -40 -50 -60 -16 Z" fill={c} stroke={INK} strokeWidth={3.6} />;
    case 'bald':
      return <path d="M 18 -52 q 14 4 20 14" stroke="#FFFFFF" strokeWidth={4} fill="none" opacity={0.8} />;
    default:
      return null;
  }
};

// Beard, glasses, earrings: over the face.
export const InkFaceExtras: React.FC<{d: Design; ex: number}> = ({d, ex}) => {
  const has = (x: string) => d.extras.includes(x as never);
  const c = d.hairColour || INK;
  return (
    <g>
      {has('beard') ? <path d={`M -54 6 Q -50 66 ${ex} 70 Q ${R} 64 ${R - 4} 6 Q 50 40 ${ex + 18} 40 Q ${ex} 50 ${ex - 18} 40 Q -40 42 -54 6 Z`} fill={c} stroke={INK} strokeWidth={3.6} /> : null}
      {has('stubble') ? (
        <g fill={c} opacity={0.5}>{Array.from({length: 16}, (_, i) => <circle key={i} cx={-40 + (i % 8) * 12 + ex / 2} cy={40 + Math.floor(i / 8) * 9 + Math.abs(i % 8 - 3.5) * -2} r={1.8} />)}</g>
      ) : null}
      {has('mustache') ? <path d={`M ${ex - 18} 18 Q ${ex - 8} 8 ${ex} 14 Q ${ex + 8} 8 ${ex + 18} 18 Q ${ex} 22 ${ex - 18} 18 Z`} fill={c} stroke={INK} strokeWidth={2.5} /> : null}
      {has('glasses') || has('sunglasses') ? (
        <g stroke={INK} strokeWidth={3.6} fill={has('sunglasses') ? INK : 'none'}>
          <circle cx={ex - 16} cy={-6} r={13} />
          <circle cx={ex + 18} cy={-6} r={13} />
          <path d={`M ${ex - 3} -8 h 8 M ${ex - 29} -8 L -60 -14`} fill="none" />
        </g>
      ) : null}
      {has('earrings') ? <circle cx={-52} cy={30} r={5} fill="#C9B26A" stroke={INK} strokeWidth={2} /> : null}
    </g>
  );
};

export const InkHeadwear: React.FC<{d: Design}> = ({d}) => {
  const c = d.headwearColour || '#7A6A4E';
  const e = {stroke: INK, strokeWidth: 4, strokeLinejoin: 'round' as const};
  const lamp = d.extras.includes('headlamp' as never);
  const lampAt = (y: number) => (lamp ? (
    <g>
      <rect x={30} y={y - 12} width={22} height={18} rx={4} fill="#2E2C2A" {...e} />
      <circle cx={48} cy={y - 3} r={5} fill="#E8DFB0" stroke="none" />
    </g>
  ) : null);
  switch (d.headwear) {
    case 'cap':
      return (
        <g>
          <path d={`M -60 -24 Q -60 -78 0 -78 Q 58 -78 60 -26 Z`} fill={c} {...e} />
          <path d={`M 34 -28 Q 80 -30 100 -18 Q 70 -16 40 -20 Z`} fill={c} {...e} />
          {lampAt(-46)}
        </g>
      );
    case 'hard-hat':
      return (
        <g>
          <path d={`M -58 -30 Q -58 -94 0 -94 Q 58 -94 58 -30 Z`} fill={c} {...e} />
          <path d={`M -10 -92 Q -6 -60 -8 -32 M 10 -92 Q 14 -60 12 -32`} stroke={INK} strokeWidth={3} fill="none" />
          <path d={`M -80 -30 Q 0 -40 82 -30 L 82 -20 Q 0 -28 -80 -20 Z`} fill={c} {...e} />
          {lampAt(-52)}
        </g>
      );
    case 'beanie':
      return (
        <g>
          <path d={`M -60 -26 Q -60 -90 0 -90 Q 60 -90 60 -26 Z`} fill={c} {...e} />
          <rect x={-64} y={-40} width={128} height={20} rx={8} fill={c} {...e} />
          <circle cx={0} cy={-94} r={12} fill={c} {...e} />
          {lampAt(-30)}
        </g>
      );
    case 'fedora':
    case 'cowboy':
      return (
        <g>
          <path d={`M -44 -38 Q -46 -96 0 -88 Q 46 -96 44 -38 Z`} fill={c} {...e} />
          <path d={`M -44 -50 h 88`} stroke="#2E2C2A" strokeWidth={9} />
          <path d={d.headwear === 'cowboy' ? `M -96 -56 Q -60 -30 0 -34 Q 60 -30 96 -56 Q 80 -24 0 -24 Q -80 -24 -96 -56 Z` : `M -88 -34 Q 0 -48 88 -34 Q 0 -24 -88 -34 Z`}
            fill={c} {...e} />
        </g>
      );
    case 'helmet':
      return (
        <g>
          <path d={`M -62 -18 Q -66 -96 4 -94 Q 66 -92 64 -24 L 40 -30 Q 0 -40 -62 -18 Z`} fill={c} {...e} />
          <path d={`M -30 -88 l 10 30 M 4 -92 l 4 32 M 36 -84 l -4 30`} stroke={INK} strokeWidth={3} />
          {lampAt(-46)}
        </g>
      );
    case 'chef-hat':
      return (
        <g fill="#F1ECE0" {...e}>
          <rect x={-46} y={-62} width={92} height={36} rx={4} />
          <path d={`M -46 -60 Q -76 -96 -40 -112 Q -20 -140 4 -120 Q 34 -142 50 -110 Q 80 -96 46 -60 Z`} />
        </g>
      );
    case 'headscarf':
      return (
        <g>
          <path d={`M -66 30 Q -76 -84 0 -84 Q 76 -84 66 30 Q 54 -44 0 -48 Q -54 -44 -66 30 Z`} fill={c} {...e} />
          <path d={`M -60 20 q -20 30 -6 52 q 12 -10 18 -34 Z`} fill={c} {...e} />
        </g>
      );
    case 'beret':
      return <path d={`M -66 -40 Q -60 -86 4 -86 Q 76 -84 70 -50 Q 40 -40 -66 -40 Z M 2 -86 l 2 -10`} fill={c} {...e} />;
    case 'bow':
      return <path d={`M 30 -60 l -26 -16 v 34 Z M 30 -60 l 26 -18 v 36 Z`} fill={c} {...e} transform="rotate(20 30 -60)" />;
    case 'headband':
      return (
        <g>
          <path d={`M -62 -34 Q 0 -70 62 -34`} stroke={INK} strokeWidth={14} fill="none" />
          <path d={`M -62 -34 Q 0 -70 62 -34`} stroke={c} strokeWidth={8} fill="none" />
          {lampAt(-48)}
        </g>
      );
    default:
      return lamp ? (
        <g>
          <path d={`M -62 -34 Q 0 -70 62 -34`} stroke="#2E2C2A" strokeWidth={8} fill="none" />
          {lampAt(-48)}
        </g>
      ) : null;
  }
};

// A design for a character who has none (older props, the demo): from their look and place in the cast.
const COLOURS = ['#34435E', '#9C4A3C', '#6E6F45', '#3E6B6A', '#A0613A', '#6B4A5E', '#5B6670', '#B8914A'];
export const defaultDesign = (look: string, i: number): Design => {
  const girl = look === 'girl' || look === 'woman' || look === 'old-woman';
  const old = look.startsWith('old');
  return {
    hair: old ? (girl ? 'bun' : 'bald') : girl ? (i % 2 ? 'long' : 'ponytail') : (['messy', 'short', 'side-part', 'curly'] as const)[i % 4],
    hairColour: old ? '#8E8A84' : '#1E1B18',
    top: girl ? 'dress' : (['hoodie', 'shirt', 'sweater', 'jacket'] as const)[i % 4],
    topColour: COLOURS[i % COLOURS.length],
    bottom: girl ? 'none' : 'trousers',
    bottomColour: i % 2 ? '#3A3A3D' : '#5A5446',
    shoes: 'shoes',
    shoesColour: '#3B2E24',
    headwear: 'none',
    headwearColour: '',
    extras: old && !girl ? ['glasses'] : [],
    extraColour: '#8A6A44',
  };
};

// ---------- the sets ----------

export type SetPal = {fabric: string; fabricDeep: string; soft: string; wood: string; woodDeep: string; screen: string; pot: string; leaf: string; paper: string};
export const GREY_PAL: SetPal = {fabric: '#B4B4B4', fabricDeep: '#9C9C9C', soft: '#E4E4E4', wood: '#B4B4B4', woodDeep: '#9C9C9C', screen: '#9C9C9C', pot: '#B4B4B4', leaf: '#9C9C9C', paper: '#CFCFCF'};

type Room = {wall: string; trim: string; floor: string; boards: string; pal: SetPal};
const BASE: SetPal = {fabric: '#9C5A48', fabricDeep: '#7C4436', soft: '#E6DCC6', wood: '#A47E56', woodDeep: '#7E5E3E', screen: '#2F302F', pot: '#A9684A', leaf: '#6E7A4A', paper: '#D8CDB4'};
const ROOMS: Record<Setting, Room> = {
  'living-room': {wall: '#C8B893', trim: '#8C7656', floor: '#8E7556', boards: '#735E44', pal: {...BASE, fabric: '#5E6B7C', fabricDeep: '#475262'}},
  classroom: {wall: '#B5BC9E', trim: '#7E8466', floor: '#9C8462', boards: '#7E694C', pal: BASE},
  'exam-hall': {wall: '#BDB9AA', trim: '#86826F', floor: '#9C8462', boards: '#7E694C', pal: BASE},
  kitchen: {wall: '#D7CDB2', trim: '#9A8E70', floor: '#A39A86', boards: '#8A816D', pal: {...BASE, fabric: '#8E9A7E', fabricDeep: '#6F7A60'}},
  bedroom: {wall: '#A8ADA9', trim: '#7A7F7A', floor: '#8C7656', boards: '#705C42', pal: {...BASE, fabric: '#8C5A5A', soft: '#E3DAC6'}},
  street: {wall: '#E0D6BE', trim: '#8E8676', floor: '#77736A', boards: '#5E5A52', pal: BASE},
  office: {wall: '#C2BEB2', trim: '#86827A', floor: '#7E7A70', boards: '#686459', pal: {...BASE, fabric: '#5B6670', wood: '#8E8270', woodDeep: '#6E6456'}},
  bathroom: {wall: '#BFC7C0', trim: '#88908A', floor: '#A9A69A', boards: '#8E8B80', pal: {...BASE, soft: '#EDE8DC'}},
  park: {wall: '#E2D8BE', trim: '#7F8A5E', floor: '#7F8A5E', boards: '#6B754E', pal: {...BASE, wood: '#8E6E4A'}},
  shop: {wall: '#D2C29C', trim: '#9A8660', floor: '#9A8F7A', boards: '#7F7663', pal: {...BASE, wood: '#8C6C4C'}},
  blank: {wall: '#D8CDB4', trim: '#9A8E70', floor: '#A8987A', boards: '#8E7F64', pal: BASE},
};
export const inkPalette = (setting: Setting): SetPal => (ROOMS[setting] ?? ROOMS.blank).pal;

const W = 1920;
const H = 1080;
const ink = {stroke: INK, strokeWidth: 4.5, strokeLinejoin: 'round' as const, strokeLinecap: 'round' as const};

// A window onto rolling hills: the view most rooms get (flat bands, no gradients).
const Window: React.FC<{x: number; y: number; w: number; h: number; city?: boolean; night?: boolean}> = ({x, y, w, h, city, night}) => (
  <g>
    <rect x={x - 14} y={y - 14} width={w + 28} height={h + 28} fill="#8C7656" {...ink} />
    <rect x={x} y={y} width={w} height={h} fill={night ? '#46505E' : '#E4DAC2'} {...ink} />
    <g clipPath="none">
      {city ? (
        [[0.02, 0.45, 0.16], [0.2, 0.3, 0.14], [0.36, 0.55, 0.18], [0.56, 0.38, 0.12], [0.7, 0.5, 0.16], [0.86, 0.34, 0.12]].map(([a, top, ww], i) => (
          <rect key={i} x={x + a * w} y={y + top * h} width={ww * w} height={h * (1 - top)} fill={i % 2 ? '#9C9A92' : '#B3AFA2'} stroke={INK} strokeWidth={2.5} />
        ))
      ) : (
        <>
          <path d={`M ${x} ${y + h * 0.62} Q ${x + w * 0.3} ${y + h * 0.42} ${x + w * 0.55} ${y + h * 0.6} Q ${x + w * 0.8} ${y + h * 0.48} ${x + w} ${y + h * 0.58} V ${y + h} H ${x} Z`} fill="#A9AE8A" stroke={INK} strokeWidth={2.5} />
          <path d={`M ${x} ${y + h * 0.78} Q ${x + w * 0.4} ${y + h * 0.66} ${x + w} ${y + h * 0.8} V ${y + h} H ${x} Z`} fill="#8C946C" stroke={INK} strokeWidth={2.5} />
          <circle cx={x + w * 0.72} cy={y + h * 0.26} r={Math.min(w, h) * 0.08} fill={night ? '#E8E0C4' : '#EFE6CC'} stroke={INK} strokeWidth={2.5} />
        </>
      )}
    </g>
    <line x1={x + w / 2} y1={y} x2={x + w / 2} y2={y + h} {...ink} />
    <line x1={x} y1={y + h / 2} x2={x + w} y2={y + h / 2} {...ink} strokeWidth={3} />
    <rect x={x - 24} y={y + h + 10} width={w + 48} height={16} fill="#8C7656" {...ink} />
  </g>
);

const Frame: React.FC<{x: number; y: number; w: number; h: number; tint?: string}> = ({x, y, w, h, tint = '#B9A27A'}) => (
  <g>
    <rect x={x} y={y} width={w} height={h} fill="#6E5A40" {...ink} />
    <rect x={x + 12} y={y + 12} width={w - 24} height={h - 24} fill={tint} {...ink} strokeWidth={3} />
    <path d={`M ${x + 12} ${y + h - 30} Q ${x + w * 0.4} ${y + h * 0.4} ${x + w - 12} ${y + h - 44}`} stroke={INK} strokeWidth={3} fill="none" />
  </g>
);

const Floor: React.FC<{room: Room; floor: number}> = ({room, floor}) => (
  <g>
    <rect x={-400} y={floor} width={W + 800} height={H + 400 - floor} fill={room.floor} />
    {[34, 84, 160].map((dy) => <line key={dy} x1={-400} y1={floor + dy} x2={W + 400} y2={floor + dy} stroke={room.boards} strokeWidth={3} />)}
    {[-200, 260, 700, 1160, 1600, 2050].map((x, i) => <line key={x} x1={x + (i % 2) * 120} y1={floor} x2={x + (i % 2) * 120 - 40} y2={floor + 34} stroke={room.boards} strokeWidth={3} />)}
    <rect x={-400} y={floor - 26} width={W + 800} height={26} fill={room.trim} {...ink} />
  </g>
);

export const InkSet: React.FC<{setting: Setting; sign?: string; floor: number; hand: string; font: string}> = ({setting, sign, floor, hand, font}) => {
  const room = ROOMS[setting] ?? ROOMS.blank;
  const base = <rect x={-400} y={-400} width={W + 800} height={H + 800} fill={room.wall} />;
  const signText = (x: number, y: number, size = 38, fill = INK) =>
    sign ? <text x={x} y={y} fontSize={size} textAnchor="middle" fill={fill} fontFamily={hand}>{sign.toUpperCase()}</text> : null;
  switch (setting) {
    case 'living-room':
      return (
        <g>
          {base}
          <Window x={1290} y={210} w={300} h={250} />
          <path d={`M 1250 180 h 380`} {...ink} />
          <path d={`M 1262 186 q -20 160 6 330 h 40 q -20 -170 -6 -330 Z M 1618 186 q 20 160 -6 330 h -40 q 20 -170 6 -330 Z`} fill="#9C5A48" {...ink} />
          <Frame x={560} y={250} w={200} h={150} />
          <Frame x={800} y={280} w={120} h={120} tint="#9DA585" />
          <g>
            <line x1={180} y1={floor - 26} x2={180} y2={floor - 360} {...ink} strokeWidth={6} />
            <path d={`M 120 ${floor - 360} h 120 l -26 -90 h -68 Z`} fill="#D9C79A" {...ink} />
            <ellipse cx={180} cy={floor - 22} rx={46} ry={10} fill="#5E4A36" {...ink} />
          </g>
          <Floor room={room} floor={floor} />
          <ellipse cx={960} cy={floor + 70} rx={620} ry={46} fill="#8E5E48" {...ink} strokeWidth={3.5} opacity={0.9} />
        </g>
      );
    case 'classroom':
    case 'exam-hall':
      return (
        <g>
          {base}
          <rect x={400} y={140} width={1120} height={330} fill="#7E6448" {...ink} />
          <rect x={420} y={160} width={1080} height={290} fill="#45544A" {...ink} />
          {sign ? <text x={960} y={330} fontSize={64} textAnchor="middle" fill="#E6E0CC" fontFamily={hand}>{sign}</text> : (
            <path d="M 480 220 q 60 -20 120 0 t 120 0 M 480 270 q 40 -14 90 0" stroke="#D8D2BE" strokeWidth={4} fill="none" opacity={0.6} />
          )}
          <rect x={430} y={470} width={1060} height={14} fill="#7E6448" {...ink} />
          <circle cx={1700} cy={200} r={54} fill="#E8E0CC" {...ink} />
          <path d="M 1700 200 v -32 M 1700 200 l 24 12" {...ink} />
          <rect x={120} y={210} width={150} height={190} fill="#C9A86A" {...ink} />
          <path d="M 140 250 h 110 M 140 290 h 80 M 140 330 h 100" stroke={INK} strokeWidth={3} />
          <Floor room={room} floor={floor} />
        </g>
      );
    case 'kitchen':
      return (
        <g>
          {base}
          <rect x={160} y={150} width={700} height={210} fill="#8E9A7E" {...ink} />
          {[160, 393, 626].map((x) => <rect key={x} x={x + 14} y={164} width={205} height={182} fill="#9DA98C" {...ink} strokeWidth={3} />)}
          {[290, 520, 750].map((x) => <circle key={x} cx={x} cy={330} r={6} fill={INK} />)}
          <g>
            {Array.from({length: 7}, (_, i) => <line key={`h${i}`} x1={160} y1={400 + i * 36} x2={860} y2={400 + i * 36} stroke="#BDB49C" strokeWidth={2.5} />)}
            {Array.from({length: 12}, (_, i) => <line key={`v${i}`} x1={160 + i * 64} y1={380} x2={160 + i * 64} y2={floor - 26} stroke="#BDB49C" strokeWidth={2.5} />)}
          </g>
          <rect x={1380} y={240} width={290} height={floor - 266} rx={14} fill="#E3DCC8" {...ink} />
          <line x1={1380} y1={500} x2={1670} y2={500} {...ink} />
          <path d="M 1410 290 v 70 M 1410 540 v 90" {...ink} strokeWidth={8} />
          <Window x={1010} y={190} w={220} h={180} />
          <Floor room={room} floor={floor} />
        </g>
      );
    case 'bedroom':
      return (
        <g>
          {base}
          <Window x={300} y={220} w={260} h={230} night />
          <rect x={1520} y={200} width={170} height={230} fill="#8C6A9A" opacity={0.55} {...ink} />
          <path d="M 1560 260 l 40 60 l 30 -30 l 40 90" stroke={INK} strokeWidth={3} fill="none" />
          <rect x={700} y={330} width={240} height={26} fill="#8E6E4A" {...ink} />
          {[712, 740, 764, 800, 830, 860].map((x, i) => <rect key={x} x={x} y={262 + (i % 3) * 8} width={22} height={68 - (i % 3) * 8} fill={['#9C5A48', '#5E6B7C', '#6E7A4A'][i % 3]} {...ink} strokeWidth={3} />)}
          <Floor room={room} floor={floor} />
        </g>
      );
    case 'office':
      return (
        <g>
          {base}
          <Window x={240} y={170} w={560} h={330} city />
          <rect x={1000} y={210} width={300} height={190} fill="#E9E3D2" {...ink} />
          <path d="M 1030 360 l 60 -60 l 50 30 l 70 -80" stroke="#7E5E3E" strokeWidth={5} fill="none" />
          <circle cx={1650} cy={220} r={50} fill="#E8E0CC" {...ink} />
          <path d="M 1650 220 v -28 M 1650 220 l 20 10" {...ink} />
          <Floor room={room} floor={floor} />
        </g>
      );
    case 'bathroom':
      return (
        <g>
          {base}
          {Array.from({length: 14}, (_, i) => <line key={`h${i}`} x1={-400} y1={120 + i * 60} x2={W + 400} y2={120 + i * 60} stroke="#A9B1AA" strokeWidth={2.5} />)}
          {Array.from({length: 24}, (_, i) => <line key={`v${i}`} x1={-160 + i * 100} y1={0} x2={-160 + i * 100} y2={floor} stroke="#A9B1AA" strokeWidth={2.5} />)}
          <rect x={720} y={170} width={480} height={floor - 170} fill="#9C8466" {...ink} />
          <rect x={760} y={220} width={400} height={floor - 220} fill="#B09676" {...ink} />
          {signText(960, 206, 40) ?? <text x={960} y={206} fontSize={40} fontWeight={800} textAnchor="middle" fill={INK} fontFamily={font}>TOILET</text>}
          <circle cx={1120} cy={560} r={12} fill={INK} />
          <rect x={210} y={260} width={180} height={220} rx={90} fill="#D9DED8" {...ink} />
          <Floor room={room} floor={floor} />
        </g>
      );
    case 'park':
      return (
        <g>
          {base}
          <circle cx={1500} cy={210} r={64} fill="#EFE3C2" {...ink} strokeWidth={3} />
          <path d={`M -400 ${floor - 200} Q 300 ${floor - 380} 900 ${floor - 230} Q 1400 ${floor - 380} ${W + 400} ${floor - 220} V ${floor} H -400 Z`} fill="#A9AE8A" {...ink} />
          <path d={`M -400 ${floor - 90} Q 600 ${floor - 200} 1300 ${floor - 100} Q 1700 ${floor - 160} ${W + 400} ${floor - 90} V ${floor} H -400 Z`} fill="#939A72" {...ink} />
          {[[250, 1], [560, 0.7], [1760, 0.85]].map(([x, k]) => (
            <g key={x}>
              <rect x={x - 22 * k} y={floor - 330 * k} width={44 * k} height={330 * k} fill="#6E5A40" {...ink} />
              <circle cx={x} cy={floor - 420 * k} r={170 * k} fill="#6E7A4A" {...ink} />
              <circle cx={x - 90 * k} cy={floor - 330 * k} r={100 * k} fill="#7A8656" {...ink} />
            </g>
          ))}
          <rect x={-400} y={floor} width={W + 800} height={H + 400 - floor} fill={room.floor} />
          <path d={`M 700 ${H + 200} Q 900 ${floor + 60} 1150 ${floor}`} stroke="#C9BC98" strokeWidth={90} fill="none" />
          <line x1={-400} y1={floor} x2={W + 400} y2={floor} {...ink} />
        </g>
      );
    case 'street':
      return (
        <g>
          {base}
          {[[0, 260, 320, '#C2A27A'], [340, 160, 260, '#9C5E48'], [620, 300, 380, '#93A08A'], [1050, 200, 300, '#B7A88A'], [1380, 120, 320, '#8E7F70'], [1720, 280, 260, '#A9886A']].map(([x, top, w, c]) => (
            <g key={x as number}>
              <rect x={x as number} y={top as number} width={w as number} height={floor - (top as number)} fill={c as string} {...ink} />
              {Array.from({length: Math.floor((floor - (top as number) - 120) / 110)}, (_, r) =>
                [0.2, 0.6].map((fx) => <rect key={`${r}${fx}`} x={(x as number) + (w as number) * fx} y={(top as number) + 40 + r * 110} width={(w as number) * 0.2} height={60} fill="#E2D8BE" {...ink} strokeWidth={3} />),
              )}
            </g>
          ))}
          <rect x={-400} y={floor} width={W + 800} height={60} fill="#B0A994" {...ink} />
          <rect x={-400} y={floor + 60} width={W + 800} height={400} fill="#5E5B55" />
          <line x1={140} y1={floor + 150} x2={W} y2={floor + 150} stroke="#D8CDB4" strokeWidth={10} strokeDasharray="80 60" />
        </g>
      );
    case 'shop':
      return (
        <g>
          {base}
          <rect x={600} y={110} width={720} height={120} fill="#5E6B5A" {...ink} />
          {signText(960, 192, 56, '#F0E8D0') ?? <text x={960} y={192} fontSize={56} fontWeight={800} textAnchor="middle" fill="#F0E8D0" fontFamily={font}>SHOP</text>}
          {[[160, 560], [1360, 1760]].map(([a, b]) => (
            <g key={a}>
              <rect x={a - 10} y={290} width={b - a + 20} height={360} fill="#8C6C4C" {...ink} />
              {[320, 440, 560].map((y, r) => (
                <g key={y}>
                  {Array.from({length: 6}, (_, i) => (
                    <rect key={i} x={a + 10 + i * 64} y={y + (i % 2) * 10} width={52} height={86 - (i % 2) * 10}
                      fill={['#9C5A48', '#B8914A', '#5E6B7C', '#6E7A4A', '#C9B48E', '#7A5A6A'][(i + r) % 6]} {...ink} strokeWidth={3} />
                  ))}
                  <rect x={a - 10} y={y + 86} width={b - a + 20} height={14} fill="#6E5236" {...ink} />
                </g>
              ))}
            </g>
          ))}
          <Floor room={room} floor={floor} />
        </g>
      );
    default:
      return (
        <g>
          {base}
          <Floor room={room} floor={floor} />
        </g>
      );
  }
};
