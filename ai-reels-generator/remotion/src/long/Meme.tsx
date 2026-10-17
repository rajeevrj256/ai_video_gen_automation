import React from 'react';
import '@fontsource/permanent-marker/400.css';
import {Img, OffthreadVideo, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig, Easing} from 'remotion';
import {FONT, clamp, exitProgress} from '../theme';
import {BOX} from './box';
import {iconFor} from './icon';
import {Person, skinTone} from '../toon/Person';
import {shade} from '../toon/Mascot';
import type {Look as PLook, Mood, Pose} from '../toon/types';
import type {MemeFace, MemeFormat, Visual} from './types';

// Memes that explain the line (reelgen/memes.py): the classic formats people know (two buttons, nope/yep, the
// distracted one, the expanding brain, this is fine...), redrawn here in code with the Toon editor's flat cartoon
// people, so nothing is copied from a meme picture or a real person, plus big reaction faces and the user's own
// meme files from the media library with top and bottom text. The format carries the joke; the labels map the
// line's concept onto it. One recurring cast per video (from the look's seed): the same 'you' in every meme.

const MARKER = '"Permanent Marker", "Noto Sans Devanagari", cursive';

// ---------- the cast ----------

const HAIRS: PLook['hair'][] = ['spiky', 'side', 'short', 'curly', 'side', 'spiky'];
const HAIR_COLOURS = ['#1b1410', '#2b1d14', '#3a2718', '#121212'];
const SHIRTS = ['#3B82F6', '#10B981', '#F59E0B', '#8B5CF6', '#EF4444', '#14B8A6', '#EC4899'];
const rnd = (seed: number, k: number, n: number) => Math.abs(Math.floor(Math.sin((seed + 1) * 9301.7 + k * 4929.3 + n * 233.1) * 100000));

// k = 0: 'you' (the recurring character), 1: someone else, 2: a third person, 3: a boss in a suit.
export const memeLook = (seed: number, k: number): PLook => {
  const r = (n: number) => rnd(seed, k, n);
  return {
    skin: skinTone(1 + (r(1) % 4)),
    hair: k === 2 ? (['bun', 'long', 'curly'] as const)[r(2) % 3] : HAIRS[r(2) % HAIRS.length],
    hairColor: HAIR_COLOURS[r(3) % HAIR_COLOURS.length],
    beard: k === 0 ? (r(4) % 3 === 0 ? 'stubble' : 'none') : (['none', 'mustache', 'stubble', 'none'] as const)[r(4) % 4],
    glasses: r(5) % 4 === 0,
    shirt: SHIRTS[(r(6) + k * 3) % SHIRTS.length],
    tie: k === 3 ? '#B91C1C' : null,
    pants: '#2f3542',
    coat: k === 3 ? '#1f2937' : null,
    age: 'young',
    build: 'average',
    outfit: k === 3 ? 'suit' : k === 0 ? 't-shirt' : 'shirt',
  };
};

// ---------- helpers ----------

const useSpring = (delay: number, config = {damping: 13, mass: 0.6}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  return spring({frame: frame - delay, fps, config});
};

// The biggest font size at which `text` fits `lines` lines of `width` px (Montserrat 800-900 is ~0.6 em a letter).
const fit = (text: string, width: number, lines: number, max: number, min = 22, em = 0.6) => {
  const len = Math.max(1, text.length);
  const longest = Math.max(1, ...text.split(/\s+/).map((w) => w.length));
  return Math.round(Math.max(min, Math.min(max, (width * lines) / (len * em * 1.08), width / (longest * em * 1.05))));
};

const outline = (size: number, color = '#000') => {
  const r = Math.max(2, Math.round(size * 0.07));
  const dirs = [[1, 0], [-1, 0], [0, 1], [0, -1], [0.7, 0.7], [-0.7, 0.7], [0.7, -0.7], [-0.7, -0.7]];
  return [...dirs.map(([x, y]) => `${x * r}px ${y * r}px 0 ${color}`), `0 ${r * 1.5}px ${r * 3}px rgba(0,0,0,0.45)`].join(', ');
};

// Classic meme text: white capitals with a black outline.
const Shout: React.FC<{text: string; size: number; width: number; style?: React.CSSProperties; delay?: number}> = ({text, size, width, style, delay = 0}) => {
  const s = useSpring(delay);
  if (!text) return null;
  return (
    <div style={{position: 'absolute', width, fontFamily: FONT, fontWeight: 900, fontSize: size, lineHeight: 1.05, color: '#fff',
      textTransform: 'uppercase', textAlign: 'center', textShadow: outline(size), textWrap: 'balance', opacity: Math.min(1, s * 1.5),
      transform: `scale(${0.7 + 0.3 * Math.min(1.05, s)})`, ...style}}>{text}</div>
  );
};

// Black words on white, like the text side of a meme.
const Words: React.FC<{text: string; size: number; style?: React.CSSProperties; delay?: number; font?: string}> = ({text, size, style, delay = 0, font}) => {
  const s = useSpring(delay);
  return (
    <div style={{fontFamily: font ?? FONT, fontWeight: 800, fontSize: size, lineHeight: 1.15, color: '#111', textWrap: 'balance',
      opacity: Math.min(1, s * 1.5), transform: `translateY(${(1 - Math.min(1, s)) * 24}px)`, ...style}}>{text}</div>
  );
};

// A person standing with feet at (x, feet), `h` px tall; what falls outside the panel is cut off by it.
const Guy: React.FC<{look: PLook; pose: Pose; mood: Mood; x: number; feet: number; h: number; flip?: boolean; seated?: boolean;
  arms?: [number, number, number, number]; delay?: number}> = ({look, pose, mood, x, feet, h, flip, seated, arms, delay = 0}) => {
  const frame = useCurrentFrame();
  const s = useSpring(delay);
  return (
    <div style={{position: 'absolute', left: x - h / 4, top: feet - h, width: h / 2, height: h, opacity: Math.min(1, s * 2),
      transform: `translateY(${(1 - Math.min(1, s)) * 40}px)`}}>
      <Person look={look} pose={pose} mood={mood} talk={0} frame={frame} height={h} flip={flip} seated={seated} arms={arms} />
    </div>
  );
};

const Panel: React.FC<{x: number; y: number; w: number; h: number; bg: string; children?: React.ReactNode; delay?: number; from?: 'left' | 'right' | 'up' | 'pop'}> = ({
  x, y, w, h, bg, children, delay = 0, from = 'pop',
}) => {
  const s = useSpring(delay);
  const k = Math.min(1, s);
  const t = from === 'left' ? `translateX(${(k - 1) * 60}px)` : from === 'right' ? `translateX(${(1 - k) * 60}px)`
    : from === 'up' ? `translateY(${(1 - k) * 50}px)` : `scale(${0.9 + 0.1 * s})`;
  return (
    <div style={{position: 'absolute', left: x, top: y, width: w, height: h, overflow: 'hidden', background: bg,
      opacity: Math.min(1, s * 2), transform: t}}>{children}</div>
  );
};

const Sweat: React.FC<{x: number; y: number; scale?: number; n?: number}> = ({x, y, scale = 1, n = 4}) => {
  const frame = useCurrentFrame();
  return (
    <>
      {Array.from({length: n}, (_, i) => {
        const period = 34 + i * 7;
        const t = ((frame + i * 13) % period) / period;
        return (
          <svg key={i} width={26 * scale} height={36 * scale} viewBox="0 0 26 36"
            style={{position: 'absolute', left: x + (i - n / 2) * 46 * scale + (i % 2) * 14, top: y + t * 90 * scale + (i % 2) * 20, opacity: 1 - t * 0.8}}>
            <path d="M13 1 C13 1 2 16 2 24 a11 11 0 0 0 22 0 C24 16 13 1 13 1 Z" fill="#9ad8ff" stroke="#3b82c4" strokeWidth={2} />
          </svg>
        );
      })}
    </>
  );
};

// ---------- a big reaction face ----------

const BigFace: React.FC<{face: MemeFace; look: PLook; size: number; frames: number; delay?: number}> = ({face, look, size, frames, delay = 0}) => {
  const frame = useCurrentFrame() - delay;
  const ink = '#2B2118';
  const skin = face === 'angry' ? shade(look.skin, -0.05) : look.skin;
  const later = interpolate(frame, [frames * 0.3, frames * 0.3 + 8], [0, 1], clamp); // the second beat of the reaction
  const look2 = face === 'side-eye' ? 26 * later : 0;
  const bounce = face === 'laughing' ? Math.abs(Math.sin(frame / 4)) * -14 : 0;
  const punch = face === 'shocked' ? 1 + 0.12 * Math.max(0, 1 - frame / 8) : face === 'deadpan' ? 1 + frame * 0.0006 : 1;
  const shake = face === 'angry' ? Math.sin(frame * 2.1) * 3 * later : face === 'shocked' ? Math.sin(frame * 3) * 4 * Math.max(0, 1 - frame / 10) : 0;
  const L = 145, R = 255, eyeY = 205;
  const line = {fill: 'none', stroke: ink, strokeWidth: 9, strokeLinecap: 'round' as const};
  const eyes = (() => {
    switch (face) {
      case 'laughing':
        return <g {...line}><path d={`M${L - 30} ${eyeY + 8} Q${L} ${eyeY - 26} ${L + 30} ${eyeY + 8}`} /><path d={`M${R - 30} ${eyeY + 8} Q${R} ${eyeY - 26} ${R + 30} ${eyeY + 8}`} /></g>;
      case 'crying':
        return <g {...line}><path d={`M${L - 30} ${eyeY - 4} Q${L} ${eyeY + 18} ${L + 30} ${eyeY - 4}`} /><path d={`M${R - 30} ${eyeY - 4} Q${R} ${eyeY + 18} ${R + 30} ${eyeY - 4}`} /></g>;
      case 'side-eye':
      case 'smug':
      case 'deadpan': {
        const lid = face === 'deadpan' ? 0.55 : 0.5;
        return (
          <g>
            {[L, R].map((x) => (
              <g key={x}>
                <ellipse cx={x} cy={eyeY} rx={36} ry={30} fill="#fff" stroke={ink} strokeWidth={5} />
                <circle cx={x + (face === 'smug' ? 0 : look2)} cy={eyeY + 6} r={13} fill={ink} />
                <path d={`M${x - 38} ${eyeY - 30 * (1 - lid * 2)} L${x + 38} ${eyeY - 30 * (1 - lid * 2)} L${x + 38} ${eyeY - 34} L${x - 38} ${eyeY - 34} Z`} fill={skin} />
                <line x1={x - 38} y1={eyeY - 30 * (1 - lid * 2)} x2={x + 38} y2={eyeY - 30 * (1 - lid * 2)} stroke={ink} strokeWidth={7} strokeLinecap="round" />
              </g>
            ))}
          </g>
        );
      }
      default: {
        const big = face === 'shocked' || face === 'mind-blown';
        const rx = big ? 44 : 34, ry = big ? 52 : 38, pr = big ? 9 : face === 'sweating' ? 11 : 14;
        const sx = face === 'confused' ? [1, 0.75] : [1, 1];
        return (
          <g>
            {[L, R].map((x, i) => (
              <g key={x}>
                <ellipse cx={x} cy={eyeY} rx={rx * sx[i]} ry={ry * sx[i]} fill="#fff" stroke={ink} strokeWidth={5} />
                <circle cx={x + (face === 'sweating' ? (i ? -6 : 6) : 0)} cy={eyeY + 2} r={pr} fill={ink} />
              </g>
            ))}
          </g>
        );
      }
    }
  })();
  const brows = (() => {
    const b = ({angry: [-6, 18], sad: [14, -12], crying: [16, -14], sweating: [12, -12], shocked: [-22, -22], 'mind-blown': [-24, -24],
      confused: [-18, 10], smug: [0, -14], 'side-eye': [-4, 8], laughing: [-8, -8], deadpan: [4, 4]} as Record<string, number[]>)[face] ?? [0, 0];
    const y = eyeY - 62;
    return (
      <g stroke={shade(look.hairColor, -0.1)} strokeWidth={14} strokeLinecap="round">
        <line x1={L - 34} y1={y + b[0]} x2={L + 30} y2={y + b[1]} />
        <line x1={R - 30} y1={y + (face === 'confused' ? -16 : face === 'smug' ? -18 : b[1])} x2={R + 34} y2={y + (face === 'confused' ? -26 : face === 'smug' ? -6 : b[0])} />
      </g>
    );
  })();
  const mouthY = 318;
  const mouth = (() => {
    switch (face) {
      case 'shocked':
      case 'mind-blown':
        return <ellipse cx={200} cy={mouthY + 6} rx={34} ry={44} fill="#5B1F1F" stroke={ink} strokeWidth={5} />;
      case 'laughing':
        return <g><path d={`M128 ${mouthY - 22} Q200 ${mouthY + 70} 272 ${mouthY - 22} Z`} fill="#5B1F1F" stroke={ink} strokeWidth={6} />
          <path d={`M138 ${mouthY - 18} L262 ${mouthY - 18} L256 ${mouthY - 4} L144 ${mouthY - 4} Z`} fill="#fff" />
          <ellipse cx={200} cy={mouthY + 26} rx={30} ry={12} fill="#e86a7a" /></g>;
      case 'crying':
        return <path d={`M146 ${mouthY + 20} Q200 ${mouthY - 40 + Math.sin(frame / 3) * 6} 254 ${mouthY + 20} Z`} fill="#5B1F1F" stroke={ink} strokeWidth={6} />;
      case 'smug':
        return <path d={`M160 ${mouthY + 2} Q216 ${mouthY + 18} 252 ${mouthY - 16}`} {...line} />;
      case 'side-eye':
      case 'deadpan':
        return <line x1={164} y1={mouthY} x2={236} y2={mouthY} {...line} />;
      case 'angry':
        return <g><rect x={150} y={mouthY - 16} width={100} height={34} rx={8} fill="#fff" stroke={ink} strokeWidth={6} />
          {[175, 200, 225].map((x) => <line key={x} x1={x} y1={mouthY - 16} x2={x} y2={mouthY + 18} stroke={ink} strokeWidth={4} />)}</g>;
      case 'confused':
      case 'sweating':
        return <path d={`M150 ${mouthY + 4} q12 -14 25 0 q12 14 25 0 q12 -14 25 0 q12 14 25 0`} {...line} />;
      default:
        return <path d={`M160 ${mouthY} Q200 ${mouthY + 26} 240 ${mouthY}`} {...line} />;
    }
  })();
  const hair = look.hair === 'spiky'
    ? <path d="M58 170 L66 80 L100 112 L118 40 L156 96 L190 26 L222 92 L262 36 L278 104 L318 62 L336 120 L344 170 Q300 110 200 106 Q100 110 58 170 Z" fill={look.hairColor} />
    : look.hair === 'curly'
      ? <g fill={look.hairColor}>{[70, 110, 150, 190, 230, 270, 310, 340].map((x, i) => <circle key={i} cx={x} cy={i % 2 ? 92 : 78} r={44} />)}</g>
      : look.hair === 'bun' || look.hair === 'long'
        ? <g fill={look.hairColor}><path d="M52 200 Q48 60 200 54 Q352 60 348 200 Q330 110 200 104 Q70 110 52 200 Z" />{look.hair === 'bun' ? <circle cx={200} cy={40} r={40} /> : null}</g>
        : <path d="M54 186 Q50 62 200 56 Q350 62 346 186 Q320 104 230 100 Q130 98 54 186 Z" fill={look.hairColor} />;
  return (
    <div style={{width: size, height: size * 1.05, transform: `translate(${shake}px, ${bounce}px) scale(${punch})`, position: 'relative'}}>
      <svg viewBox="0 0 400 420" width={size} height={size * 1.05} style={{overflow: 'visible'}}>
        {face === 'mind-blown' ? (
          <g opacity={later}>
            {Array.from({length: 14}, (_, i) => {
              const a = (i / 14) * Math.PI - Math.PI;
              const d = 60 + later * 150 + (i % 3) * 20;
              return <line key={i} x1={200 + Math.cos(a) * 60} y1={90 + Math.sin(a) * 40} x2={200 + Math.cos(a) * d * 1.4} y2={90 + Math.sin(a) * d}
                stroke={i % 2 ? '#FFD60A' : '#FF7A00'} strokeWidth={14} strokeLinecap="round" />;
            })}
            <circle cx={200} cy={90} r={70 * later} fill="#FFD60A" opacity={0.5} />
          </g>
        ) : null}
        <path d="M10 470 Q20 392 120 378 L280 378 Q380 392 390 470 Z" fill={look.shirt} />
        <rect x={168} y={340} width={64} height={50} fill={shade(skin, -0.12)} />
        <ellipse cx={52} cy={232} rx={26} ry={40} fill={shade(skin, -0.06)} />
        <ellipse cx={348} cy={232} rx={26} ry={40} fill={shade(skin, -0.06)} />
        <ellipse cx={200} cy={228} rx={150} ry={170} fill={skin} stroke={shade(skin, -0.3)} strokeWidth={5} />
        {face === 'mind-blown' ? <ellipse cx={200} cy={92} rx={120 * later} ry={40 * later} fill="#3b1d10" /> : hair}
        {face === 'angry' ? <ellipse cx={200} cy={228} rx={150} ry={170} fill="#ff2d2d" opacity={0.28 * later} /> : null}
        {brows}
        {eyes}
        <path d="M200 236 Q188 268 206 272" fill="none" stroke={shade(skin, -0.3)} strokeWidth={6} strokeLinecap="round" />
        {face === 'laughing' || face === 'smug' ? <g fill="#ff8a8a" opacity={0.5}><ellipse cx={110} cy={268} rx={30} ry={16} /><ellipse cx={290} cy={268} rx={30} ry={16} /></g> : null}
        {look.beard === 'stubble' ? <path d="M78 280 Q92 392 200 398 Q308 392 322 280 Q300 352 200 356 Q100 352 78 280 Z" fill={look.hairColor} opacity={0.22} /> : null}
        {look.beard === 'mustache' ? <path d="M150 292 Q200 270 250 292 Q200 286 150 292 Z" fill={look.hairColor} stroke={look.hairColor} strokeWidth={10} /> : null}
        {mouth}
        {look.glasses && face !== 'crying' && face !== 'laughing' ? <g fill="rgba(255,255,255,0.12)" stroke="#1d1d1d" strokeWidth={8}><circle cx={L} cy={eyeY} r={50} /><circle cx={R} cy={eyeY} r={50} /><line x1={L + 50} y1={eyeY} x2={R - 50} y2={eyeY} /></g> : null}
        {face === 'crying' ? (
          <g fill="#7cc6ff" opacity={0.9}>
            {[L + 26, R - 26].map((x, i) => (
              <path key={i} d={`M${x - 12} ${eyeY + 8} Q${x - 18 + Math.sin(frame / 3 + i) * 6} ${eyeY + 120} ${x - 8} ${eyeY + 190} L${x + 14} ${eyeY + 190} Q${x + 10 + Math.sin(frame / 4 + i) * 6} ${eyeY + 120} ${x + 12} ${eyeY + 8} Z`} />
            ))}
          </g>
        ) : null}
        {face === 'laughing' ? <g fill="#7cc6ff">{[L - 40, R + 40].map((x, i) => <path key={i} d={`M${x} ${eyeY + 4 + (frame * 3 + i * 20) % 40} q10 18 0 26 q-10 -8 0 -26 Z`} />)}</g> : null}
        {face === 'angry' ? <g fill="#e5e7eb" opacity={later}>{[[30, 200], [370, 200]].map(([x, y], i) => [0, 1, 2].map((k) => (
          <circle key={`${i}${k}`} cx={x + (i ? 1 : -1) * (10 + ((frame * 2 + k * 16) % 50))} cy={y - ((frame * 2 + k * 16) % 50)} r={14 + k * 4} opacity={1 - ((frame * 2 + k * 16) % 50) / 50} />
        )))}</g> : null}
      </svg>
      {face === 'sweating' ? <Sweat x={size * 0.62} y={size * 0.12} scale={size / 420} n={3} /> : null}
      {face === 'confused' ? (
        <div style={{position: 'absolute', right: -size * 0.12, top: -size * 0.08, fontFamily: FONT, fontWeight: 900, fontSize: size * 0.28, color: '#FFD60A',
          textShadow: outline(size * 0.28), transform: `rotate(${12 + Math.sin(frame / 8) * 8}deg)`}}>?</div>
      ) : null}
    </div>
  );
};

// ---------- the formats ----------

type F = {v: Visual; labels: string[]; frames: number; w: number; h: number; seed: number};

const BUTTON = '#E0282E';

const MemeButton: React.FC<{x: number; y: number; rx: number; text: string; delay: number}> = ({x, y, rx, text, delay}) => {
  const s = useSpring(delay, {damping: 11, mass: 0.6});
  const ry = rx * 0.32, depth = rx * 0.22;
  const size = fit(text, rx * 1.5, 2, rx * 0.34, 18);
  return (
    <div style={{position: 'absolute', left: x - rx, top: y - ry, width: rx * 2, height: ry * 2 + depth + 30, transform: `scale(${Math.min(1.04, s)})`, opacity: Math.min(1, s * 2)}}>
      <svg width={rx * 2} height={ry * 2 + depth + 30} viewBox={`0 0 ${rx * 2} ${ry * 2 + depth + 30}`} style={{position: 'absolute', overflow: 'visible'}}>
        <ellipse cx={rx} cy={ry + depth + 14} rx={rx * 1.12} ry={ry * 1.15} fill="#d1d5db" stroke="#6b7280" strokeWidth={4} />
        <path d={`M0 ${ry} L0 ${ry + depth} A${rx} ${ry} 0 0 0 ${rx * 2} ${ry + depth} L${rx * 2} ${ry} Z`} fill={shade(BUTTON, -0.3)} />
        <ellipse cx={rx} cy={ry} rx={rx} ry={ry} fill={BUTTON} stroke={shade(BUTTON, -0.35)} strokeWidth={4} />
        <ellipse cx={rx * 0.8} cy={ry * 0.62} rx={rx * 0.5} ry={ry * 0.32} fill="#fff" opacity={0.18} />
      </svg>
      <div style={{position: 'absolute', left: rx * 0.22, width: rx * 1.56, top: 0, height: ry * 2, display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontFamily: FONT, fontWeight: 900, fontSize: size, lineHeight: 1, color: '#fff', textTransform: 'uppercase', textAlign: 'center',
        textShadow: '0 3px 0 rgba(0,0,0,0.35)', transform: 'scaleY(0.82) rotate(-2deg)', textWrap: 'balance'}}>{text}</div>
    </div>
  );
};

const TwoButtons: React.FC<F> = ({labels, frames, w, h, seed}) => {
  const tall = BOX.V;
  const ph = tall ? h * 1.05 : h * 1.45;
  const desk = h * (tall ? 0.62 : 0.7);
  const rx = tall ? w * 0.23 : w * 0.17;
  const gap = tall ? w * 0.25 : w * 0.24;
  return (
    <div style={{position: 'absolute', inset: 0, background: 'radial-gradient(circle at 50% 35%, #8a8a8a 0%, #4b4b4b 55%, #262626 100%)'}}>
      <Guy look={memeLook(seed, 0)} pose="stand" mood="worried" x={w / 2} feet={ph} h={ph} arms={[50, 10, 50, 10]} />
      <Sweat x={w / 2 - ph * 0.02} y={ph * 0.06} scale={ph / 800} n={4} />
      <svg width={w} height={h - desk} style={{position: 'absolute', left: 0, top: desk}} viewBox={`0 0 ${w} ${h - desk}`} preserveAspectRatio="none">
        <path d={`M${w * 0.06} 0 L${w * 0.94} 0 L${w} ${h - desk} L0 ${h - desk} Z`} fill="#9ca3af" />
        <rect x={w * 0.06} y={0} width={w * 0.88} height={10} fill="#d1d5db" />
      </svg>
      <MemeButton x={w / 2 - gap} y={desk + (h - desk) * 0.42} rx={rx} text={labels[0] ?? ''} delay={6} />
      <MemeButton x={w / 2 + gap} y={desk + (h - desk) * 0.42} rx={rx} text={labels[1] ?? ''} delay={12} />
    </div>
  );
};

const NopeYep: React.FC<F> = ({labels, frames, w, h, seed}) => {
  const rowH = h / 2, art = w * (BOX.V ? 0.44 : 0.4), text = w - art;
  const look = memeLook(seed, 0);
  const second = Math.round(frames * 0.4);
  const ph = rowH * 2.3;
  const rows: [string, Pose, Mood, boolean, number][] = [[labels[0] ?? '', 'hold-up', 'angry', true, 0], [labels[1] ?? '', 'point', 'happy', false, second]];
  const armsFor = (i: number): [number, number, number, number] | undefined => (i === 0 ? [8, 4, 80, 95] : undefined);
  return (
    <div style={{position: 'absolute', inset: 0, background: '#fff'}}>
      {rows.map(([label, pose, mood, flip, delay], i) => (
        <React.Fragment key={i}>
          <Panel x={0} y={i * rowH} w={art} h={rowH} bg="linear-gradient(160deg, #FDBA3B, #F08A24)" delay={delay} from="left">
            <Guy look={look} pose={pose} mood={mood} x={art / 2} feet={ph * 0.97} h={ph} flip={flip} delay={delay} arms={armsFor(i)} />
          </Panel>
          <div style={{position: 'absolute', left: art, top: i * rowH, width: text, height: rowH, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 30, boxSizing: 'border-box'}}>
            <Words text={label} size={fit(label, text - 60, 3, BOX.V ? 70 : 78, 26)} delay={delay + 4} style={{textAlign: 'center'}} />
          </div>
        </React.Fragment>
      ))}
      <div style={{position: 'absolute', left: 0, top: rowH - 3, width: w, height: 6, background: '#111'}} />
      <div style={{position: 'absolute', left: art - 3, top: 0, width: 6, height: h, background: '#111'}} />
    </div>
  );
};

const Street: React.FC<{w: number; h: number}> = ({w, h}) => (
  <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{position: 'absolute', inset: 0}}>
    <defs><linearGradient id="memesky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#8ecdf7" /><stop offset="1" stopColor="#e9f6ff" /></linearGradient></defs>
    <rect width={w} height={h} fill="url(#memesky)" />
    {[0.02, 0.16, 0.31, 0.47, 0.6, 0.76, 0.88].map((x, i) => (
      <rect key={i} x={x * w} y={h * (0.18 + (i % 3) * 0.08)} width={w * 0.13} height={h} fill={['#b8c6d9', '#a5b4c8', '#c7d2e0'][i % 3]} />
    ))}
    {[0.05, 0.2, 0.36, 0.51, 0.65, 0.8, 0.92].map((x, i) => (
      <g key={i} fill="#e8eef5" opacity={0.8}>{[0, 1, 2, 3].map((r) => <rect key={r} x={x * w} y={h * (0.24 + (i % 3) * 0.08) + r * h * 0.09} width={w * 0.03} height={h * 0.05} />)}</g>
    ))}
    <rect y={h * 0.7} width={w} height={h * 0.3} fill="#cfc8bb" />
    <rect y={h * 0.7} width={w} height={8} fill="#a8a093" />
  </svg>
);

const IconThing: React.FC<{name: string; x: number; y: number; size: number; delay: number}> = ({name, x, y, size, delay}) => {
  const frame = useCurrentFrame();
  const s = useSpring(delay, {damping: 10, mass: 0.6});
  const Icon = iconFor(name || 'sparkles');
  return (
    <div style={{position: 'absolute', left: x - size / 2, top: y - size / 2 + Math.sin(frame / 12) * 8, width: size, height: size, borderRadius: '50%',
      background: 'radial-gradient(circle, #fff 0%, #ffe9a8 60%, #ffd166 100%)', boxShadow: `0 0 ${60 + Math.sin(frame / 6) * 20}px #ffd166`,
      display: 'flex', alignItems: 'center', justifyContent: 'center', transform: `scale(${Math.min(1.05, s)})`}}>
      <Icon size={size * 0.55} color="#1f2937" strokeWidth={2.2} />
    </div>
  );
};

const Distracted: React.FC<F> = ({v, labels, frames, w, h, seed}) => {
  const tall = BOX.V;
  const ph = h * (tall ? 0.7 : 0.95);
  const feet = h * 0.97;
  const xs = tall ? [0.2, 0.52, 0.83] : [0.2, 0.5, 0.78];
  const size = fit(labels.reduce((a, b) => (a.length > b.length ? a : b), ''), w * 0.26, 3, tall ? 52 : 64, 24);
  const turn = Math.round(frames * 0.25);
  return (
    <div style={{position: 'absolute', inset: 0}}>
      <Street w={w} h={h} />
      {v.icons?.[0] ? <IconThing name={v.icons[0]} x={w * xs[0]} y={h * 0.5} size={tall ? w * 0.26 : h * 0.36} delay={2} />
        : <Guy look={memeLook(seed, 1)} pose="wave" mood="happy" x={w * xs[0]} feet={feet} h={ph} delay={2} />}
      <Guy look={memeLook(seed, 0)} pose="point" mood="wink" x={w * xs[1]} feet={feet} h={ph} flip delay={turn} />
      <Guy look={memeLook(seed, 2)} pose="arms-crossed" mood="angry" x={w * xs[2]} feet={feet} h={ph} flip delay={turn + 8} />
      {labels.slice(0, 3).map((t, i) => (
        <Shout key={i} text={t} size={size} width={w * (tall ? 0.31 : 0.28)} delay={[6, turn + 4, turn + 12][i]}
          style={{left: w * xs[i] - w * (tall ? 0.155 : 0.14),
            top: i === 0 && v.icons?.[0] ? h * 0.5 + (tall ? w * 0.13 : h * 0.18) + 16 : h * (tall ? 0.12 : 0.36)}} />
      ))}
    </div>
  );
};

const Head: React.FC<{level: number; n: number; size: number}> = ({level, n, size}) => {
  const frame = useCurrentFrame();
  const glow = (level + 1) / n;
  const top = level === n - 1;
  const Brain = iconFor('brain');
  const c = ['#94a3b8', '#fde68a', '#fbbf24', '#ffffff'][Math.min(3, Math.round(glow * 3))];
  return (
    <div style={{position: 'relative', width: size, height: size}}>
      {top ? (
        <svg width={size * 1.6} height={size * 1.6} viewBox="-100 -100 200 200" style={{position: 'absolute', left: -size * 0.3, top: -size * 0.42}}>
          {Array.from({length: 16}, (_, i) => {
            const a = (i / 16) * Math.PI * 2 + frame / 40;
            return <line key={i} x1={Math.cos(a) * 30} y1={Math.sin(a) * 30} x2={Math.cos(a) * 98} y2={Math.sin(a) * 98} stroke="#fff6c2" strokeWidth={5} opacity={0.65} />;
          })}
        </svg>
      ) : null}
      <svg viewBox="0 0 200 200" width={size} height={size} style={{position: 'absolute', inset: 0}}>
        <path d="M60 190 L64 150 Q30 136 32 96 Q30 30 104 26 Q170 26 172 92 Q176 120 160 134 L162 170 L130 176 L128 190 Z" fill={top ? '#cbd5e1' : '#475569'} opacity={0.9} />
      </svg>
      <div style={{position: 'absolute', left: size * 0.24, top: size * 0.1, width: size * 0.56, height: size * 0.56, borderRadius: '50%',
        boxShadow: `0 0 ${10 + glow * 70}px ${glow * 28}px ${c}`, background: glow > 0.5 ? c : 'transparent', opacity: 0.35 + glow * 0.6}} />
      <div style={{position: 'absolute', left: size * 0.26, top: size * 0.12}}><Brain size={size * 0.52} color={glow > 0.6 ? '#7c2d12' : '#e2e8f0'} strokeWidth={2} /></div>
    </div>
  );
};

const ExpandingBrain: React.FC<F> = ({labels, frames, w, h}) => {
  const rows = labels.slice(0, 4);
  const n = Math.max(2, rows.length);
  const rh = h / n, tw = w * 0.58;
  return (
    <div style={{position: 'absolute', inset: 0, background: '#111'}}>
      {rows.map((t, i) => {
        const delay = Math.round(frames * (0.04 + (0.74 * i) / n));
        return (
          <React.Fragment key={i}>
            <Panel x={0} y={i * rh} w={tw} h={rh - 4} bg="#fff" delay={delay} from="left">
              <div style={{position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24, boxSizing: 'border-box'}}>
                <Words text={t} size={fit(t, tw - 60, 2, BOX.V ? 52 : 60, 22)} delay={delay + 3} style={{textAlign: 'center'}} />
              </div>
            </Panel>
            <Panel x={tw + 4} y={i * rh} w={w - tw - 4} h={rh - 4} bg={`radial-gradient(circle at 50% 45%, ${['#1e293b', '#312e81', '#6d28d9', '#f59e0b'][Math.min(3, Math.round(((i + 1) / n) * 3))]} 0%, #0b0b12 80%)`} delay={delay} from="right">
              <div style={{position: 'absolute', left: (w - tw - rh * 0.86) / 2, top: rh * 0.06}}><Head level={i} n={n} size={rh * 0.86} /></div>
            </Panel>
          </React.Fragment>
        );
      })}
    </div>
  );
};

const Flames: React.FC<{w: number; h: number; grow: number}> = ({w, h, grow}) => {
  const frame = useCurrentFrame();
  const n = 14;
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{position: 'absolute', inset: 0}}>
      {Array.from({length: n}, (_, i) => {
        const x = (i / (n - 1)) * w;
        const edge = Math.min(i, n - 1 - i) < 3; // taller at the sides
        const fh = h * (edge ? 0.55 : 0.22) * (0.75 + 0.25 * grow) * (0.85 + 0.15 * Math.sin(frame / 4 + i * 1.7));
        const fw = w / n * 1.6;
        const sway = Math.sin(frame / 6 + i) * fw * 0.15;
        return (
          <g key={i}>
            <path d={`M${x - fw / 2} ${h} Q${x - fw / 2} ${h - fh * 0.5} ${x + sway} ${h - fh} Q${x + fw / 2} ${h - fh * 0.5} ${x + fw / 2} ${h} Z`} fill="#ff5a1f" opacity={0.9} />
            <path d={`M${x - fw / 4} ${h} Q${x - fw / 4} ${h - fh * 0.35} ${x + sway * 0.6} ${h - fh * 0.62} Q${x + fw / 4} ${h - fh * 0.35} ${x + fw / 4} ${h} Z`} fill="#ffc21a" />
          </g>
        );
      })}
    </svg>
  );
};

const Bubble: React.FC<{text: string; x: number; y: number; w: number; size: number; delay: number; tail?: 'left' | 'right'}> = ({text, x, y, w, size, delay, tail = 'left'}) => {
  const s = useSpring(delay, {damping: 11, mass: 0.5});
  return (
    <div style={{position: 'absolute', left: x, top: y, width: w, transform: `scale(${Math.min(1.05, s)})`, transformOrigin: tail === 'left' ? '0% 100%' : '100% 100%', opacity: Math.min(1, s * 2)}}>
      <div style={{background: '#fff', border: '5px solid #111', borderRadius: 28, padding: '18px 26px', fontFamily: FONT, fontWeight: 800, fontSize: size, color: '#111', textAlign: 'center', lineHeight: 1.15}}>{text}</div>
      <svg width={60} height={44} style={{position: 'absolute', [tail === 'left' ? 'left' : 'right']: 40, bottom: -38}} viewBox="0 0 60 44">
        <path d={tail === 'left' ? 'M4 0 L10 44 L40 0 Z' : 'M56 0 L50 44 L20 0 Z'} fill="#fff" stroke="#111" strokeWidth={5} />
        <rect x={0} y={0} width={60} height={6} fill="#fff" />
      </svg>
    </div>
  );
};

const Table: React.FC<{x: number; y: number; w: number; h: number; mug?: boolean}> = ({x, y, w, h, mug = true}) => (
  <svg width={w} height={h + 60} viewBox={`0 0 ${w} ${h + 60}`} style={{position: 'absolute', left: x, top: y - 60, overflow: 'visible'}}>
    {mug ? <g><rect x={w * 0.7} y={6} width={44} height={54} rx={6} fill="#f8fafc" stroke="#111" strokeWidth={4} /><path d={`M${w * 0.7 + 44} 18 q22 4 0 28`} fill="none" stroke="#111" strokeWidth={5} /></g> : null}
    <rect x={0} y={60} width={w} height={22} rx={6} fill="#8b5a2b" stroke="#5c3a1a" strokeWidth={4} />
    <rect x={w * 0.08} y={82} width={18} height={h - 22} fill="#6b4423" />
    <rect x={w * 0.92 - 18} y={82} width={18} height={h - 22} fill="#6b4423" />
  </svg>
);

// A plain wooden chair seen from the front: the seat at `seat`, its back behind the sitter.
const Chair: React.FC<{x: number; seat: number; floor: number; ph: number}> = ({x, seat, floor, ph}) => {
  const cw = ph * 0.3;
  return (
    <svg width={cw} height={floor - seat + ph * 0.42} viewBox={`0 0 ${cw} ${floor - seat + ph * 0.42}`} style={{position: 'absolute', left: x - cw / 2, top: seat - ph * 0.42}}>
      <rect x={cw * 0.08} y={0} width={cw * 0.84} height={ph * 0.36} rx={12} fill="#7a4a24" stroke="#4a2c14" strokeWidth={4} />
      <rect x={0} y={ph * 0.4} width={cw} height={ph * 0.04} rx={6} fill="#8b5a2b" stroke="#4a2c14" strokeWidth={4} />
      <rect x={cw * 0.06} y={ph * 0.44} width={ph * 0.025} height={floor - seat} fill="#5c3a1a" />
      <rect x={cw * 0.94 - ph * 0.025} y={ph * 0.44} width={ph * 0.025} height={floor - seat} fill="#5c3a1a" />
    </svg>
  );
};

// A sitter's knees and shins over the chair's front (a seated Person draws no legs).
const Shins: React.FC<{x: number; seat: number; floor: number; ph: number}> = ({x, seat, floor, ph}) => {
  const lw = ph * 0.058;
  return (
    <svg width={ph * 0.3} height={floor - seat + 20} viewBox={`0 0 ${ph * 0.3} ${floor - seat + 20}`} style={{position: 'absolute', left: x - ph * 0.15, top: seat - 6}}>
      {[-1, 1].map((k) => (
        <g key={k}>
          <rect x={ph * 0.15 + k * ph * 0.045 - lw / 2} y={0} width={lw} height={floor - seat - 8} rx={lw / 2} fill="#2f3542" />
          <ellipse cx={ph * 0.15 + k * ph * 0.05 + ph * 0.012} cy={floor - seat - 4} rx={ph * 0.045} ry={ph * 0.02} fill="#2b2b2b" />
        </g>
      ))}
    </svg>
  );
};

const ThisIsFine: React.FC<F> = ({labels, frames, w, h, seed}) => {
  const frame = useCurrentFrame();
  const tall = BOX.V;
  const grow = interpolate(frame, [0, frames], [0, 1], clamp);
  const ph = h * (tall ? 0.72 : 0.9);
  const floor = h * 0.97;
  const seat = floor - ph * 0.26;
  const x = w * (tall ? 0.34 : 0.33);
  const say = labels[1] || 'This is fine.';
  return (
    <div style={{position: 'absolute', inset: 0, background: 'linear-gradient(#c96f2c, #e9a15b)'}}>
      <div style={{position: 'absolute', left: 0, top: 0, width: w, height: h * 0.3, background: `linear-gradient(rgba(40,30,30,${0.75 + 0.2 * grow}), rgba(40,30,30,0))`}} />
      <Chair x={x} seat={seat} floor={floor} ph={ph} />
      <Guy look={memeLook(seed, 0)} pose="sit" mood="happy" x={x} feet={seat + ph * (190 / 600)} h={ph} seated />
      <Shins x={x} seat={seat} floor={floor} ph={ph} />
      <Table x={x + ph * 0.16} y={seat - ph * 0.06} w={w * (tall ? 0.42 : 0.3)} h={floor - seat + ph * 0.06} />
      <Flames w={w} h={h} grow={grow} />
      <Bubble text={say} x={x + ph * 0.14} y={h * (tall ? 0.3 : 0.24)} w={w * (tall ? 0.46 : 0.3)} size={tall ? 46 : 50} delay={Math.round(frames * 0.35)} />
      <Shout text={labels[0] ?? ''} size={fit(labels[0] ?? '', w * 0.9, 2, tall ? 64 : 72, 26)} width={w * 0.92} delay={4} style={{left: w * 0.04, top: tall ? h * 0.05 : 18}} />
    </div>
  );
};

const PanikKalm: React.FC<F> = ({labels, frames, w, h, seed}) => {
  const rows = labels.slice(0, 3);
  const n = Math.max(2, rows.length);
  const rh = h / n, tw = w * 0.56;
  const look = memeLook(seed, 0);
  return (
    <div style={{position: 'absolute', inset: 0, background: '#111'}}>
      {rows.map((t, i) => {
        const kalm = i % 2 === 1;
        const delay = Math.round(frames * (0.03 + (0.7 * i) / n));
        return (
          <React.Fragment key={i}>
            <Panel x={0} y={i * rh} w={tw} h={rh - 4} bg="#fff" delay={delay} from="left">
              <div style={{position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24, boxSizing: 'border-box'}}>
                <Words text={t} size={fit(t, tw - 60, 2, BOX.V ? 50 : 56, 22)} delay={delay + 3} style={{textAlign: 'center'}} />
              </div>
            </Panel>
            <Panel x={tw + 4} y={i * rh} w={w - tw - 4} h={rh - 4} bg={kalm ? '#7dd3c0' : '#ff7676'} delay={delay} from="right">
              <div style={{position: 'absolute', left: (w - tw - rh * 0.8) / 2, top: rh * 0.02}}>
                <BigFace face={kalm ? 'smug' : 'shocked'} look={look} size={rh * 0.8} frames={frames} delay={delay} />
              </div>
              <Shout text={kalm ? 'kalm' : 'panik'} size={rh * 0.2} width={w - tw - 4} delay={delay + 6} style={{left: 0, bottom: rh * 0.02}} />
            </Panel>
          </React.Fragment>
        );
      })}
    </div>
  );
};

const ExpectationReality: React.FC<F> = ({labels, frames, w, h, seed}) => {
  const frame = useCurrentFrame();
  const tall = BOX.V;
  const pw = tall ? w : w / 2, phh = tall ? h / 2 : h;
  const second = Math.round(frames * 0.42);
  const look = memeLook(seed, 0);
  const sides: [string, string, Pose, Mood, string, number][] = [
    ['Expectation', labels[0] ?? '', 'celebrate', 'happy', 'linear-gradient(#7dd3fc, #fef9c3)', 0],
    ['Reality', labels[1] ?? '', 'facepalm', 'crying', 'linear-gradient(#6b7280, #374151)', second],
  ];
  return (
    <div style={{position: 'absolute', inset: 0, background: '#111'}}>
      {sides.map(([head, label, pose, mood, bg, delay], i) => (
        <Panel key={i} x={tall ? 0 : i * pw + (i ? 3 : 0)} y={tall ? i * phh + (i ? 3 : 0) : 0} w={pw - 3} h={phh - 3} bg={bg} delay={delay} from={tall ? 'up' : i ? 'right' : 'left'}>
          {i === 1 ? (
            <svg width={pw} height={phh} style={{position: 'absolute', inset: 0}}>
              {Array.from({length: 22}, (_, k) => {
                const x = (k * 97) % pw, y = ((frame * 14 + k * 61) % (phh + 60)) - 60;
                return <line key={k} x1={x} y1={y} x2={x - 8} y2={y + 40} stroke="#cbd5e1" strokeWidth={3} opacity={0.6} />;
              })}
            </svg>
          ) : null}
          <Guy look={look} pose={pose} mood={mood} x={pw / 2} feet={phh * (tall ? 1.25 : 0.9)} h={phh * (tall ? 1.05 : 0.74)} delay={delay} />
          <Shout text={head} size={tall ? 54 : 64} width={pw} delay={delay + 2} style={{left: 0, top: 14}} />
          <div style={{position: 'absolute', left: 20, right: 20, bottom: 18, display: 'flex', justifyContent: 'center'}}>
            <Words text={label} size={fit(label, pw - 80, 2, tall ? 44 : 48, 22)} delay={delay + 6}
              style={{background: 'rgba(255,255,255,0.92)', borderRadius: 14, padding: '10px 20px', textAlign: 'center'}} />
          </div>
        </Panel>
      ))}
    </div>
  );
};

const NobodyMe: React.FC<F> = ({labels, frames, w, h, seed}) => {
  const tall = BOX.V;
  const tw = tall ? w - 80 : w * 0.56;
  const me = labels[0] ?? '';
  const size = fit(`Me: ${me}`, tw, 3, tall ? 60 : 66, 26);
  const later = Math.round(frames * 0.3);
  return (
    <div style={{position: 'absolute', inset: 0, background: '#fff'}}>
      <div style={{position: 'absolute', left: 40, top: tall ? 40 : h * 0.2, width: tw, display: 'flex', flexDirection: 'column', gap: size * 0.9}}>
        <Words text={labels[1] || 'Nobody:'} size={size} delay={2} />
        <Words text={`Me: ${me}`} size={size} delay={later} />
      </div>
      <Guy look={memeLook(seed, 0)} pose={rnd(seed, 5, 1) % 2 ? 'celebrate' : 'shrug'} mood="laughing" x={tall ? w * 0.5 : w * 0.8}
        feet={h * 1.02} h={h * (tall ? 0.72 : 0.95)} delay={later + 4} />
    </div>
  );
};

const Stonks: React.FC<F & {down?: boolean}> = ({labels, frames, w, h, seed, down}) => {
  const frame = useCurrentFrame();
  const tall = BOX.V;
  const draw = interpolate(frame, [4, frames * 0.6], [0, 1], {...clamp, easing: Easing.out(Easing.cubic)});
  const pts = Array.from({length: 9}, (_, i) => {
    const t = i / 8;
    const base = down ? 0.2 + 0.6 * t : 0.8 - 0.6 * t;
    return [w * (0.08 + 0.86 * t), h * (base + (i % 2 ? 0.06 : -0.04))];
  });
  const shown = pts.slice(0, Math.max(2, Math.ceil(draw * pts.length)));
  const colour = down ? '#ff4d4d' : '#22e07a';
  const tip = shown[shown.length - 1];
  return (
    <div style={{position: 'absolute', inset: 0, background: 'radial-gradient(circle at 60% 40%, #13325e, #071226)'}}>
      <svg width={w} height={h} style={{position: 'absolute', inset: 0}}>
        {Array.from({length: 8}, (_, i) => <line key={i} x1={0} x2={w} y1={(i + 1) * h / 9} y2={(i + 1) * h / 9} stroke="#1e3a66" strokeWidth={2} />)}
        {Array.from({length: 12}, (_, i) => <line key={i} y1={0} y2={h} x1={(i + 1) * w / 13} x2={(i + 1) * w / 13} stroke="#1e3a66" strokeWidth={2} />)}
        <polyline points={shown.map((p) => p.join(',')).join(' ')} fill="none" stroke={colour} strokeWidth={14} strokeLinejoin="round" strokeLinecap="round"
          style={{filter: `drop-shadow(0 0 12px ${colour})`}} />
        <circle cx={tip[0]} cy={tip[1]} r={16} fill={colour} />
      </svg>
      <Guy look={memeLook(seed, 3)} pose={down ? 'facepalm' : 'arms-crossed'} mood={down ? 'sad' : 'proud'} x={w * (tall ? 0.3 : 0.24)} feet={h * 1.05} h={h * (tall ? 0.6 : 0.95)} delay={2} />
      <Shout text={labels[0] ?? ''} size={fit(labels[0] ?? '', w * 0.9, 2, tall ? 60 : 66, 24)} width={w * 0.92} delay={4} style={{left: w * 0.04, top: 16}} />
      <Shout text={down ? 'not stonks' : 'stonks'} size={tall ? 110 : 130} width={w} delay={Math.round(frames * 0.45)} style={{left: 0, ...(tall ? {top: h * 0.17} : {bottom: 20}), color: down ? '#ffd1d1' : '#fff'}} />
    </div>
  );
};

const ChangeMyMind: React.FC<F> = ({labels, frames, w, h, seed}) => {
  const tall = BOX.V;
  const ph = h * (tall ? 0.7 : 0.95);
  const top = h * (tall ? 0.6 : 0.56);
  const signW = tall ? w * 0.8 : w * 0.46;
  const text = labels[0] ?? '';
  return (
    <div style={{position: 'absolute', inset: 0, background: 'linear-gradient(#a7d8f5 0%, #e3f3fb 55%, #6fbf5f 55%, #4e9b43 100%)'}}>
      <svg width={w} height={h} style={{position: 'absolute', inset: 0}}>
        {[0.08, 0.22, 0.78, 0.92].map((x, i) => <circle key={i} cx={x * w} cy={h * 0.46} r={h * 0.13} fill={['#3f8f3a', '#4ea446'][i % 2]} />)}
      </svg>
      <Guy look={memeLook(seed, 0)} pose="sit" mood="smug" x={w * 0.5} feet={top + ph * 0.42} h={ph} seated />
      <div style={{position: 'absolute', left: (w - signW * 1.15) / 2, top, width: signW * 1.15, height: h - top, background: '#8b5a2b', borderTop: '14px solid #6b4423'}} />
      <div style={{position: 'absolute', left: (w - signW) / 2, top: top + 24, width: signW, height: (h - top) * 0.8, background: '#fff', border: '5px solid #222',
        display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 14, boxSizing: 'border-box'}}>
        <Words text={text} size={fit(text, signW - 40, 2, tall ? 46 : 48, 20)} delay={6} style={{textAlign: 'center'}} />
        <Words text="Change my mind" size={tall ? 26 : 28} delay={10} style={{marginTop: 8, color: '#444'}} />
      </div>
    </div>
  );
};

const Plan: React.FC<F> = ({labels, frames, w, h, seed}) => {
  const steps = [labels[0] ?? '', labels[1] ?? '', labels[2] ?? '', labels[2] ?? ''];
  const pw = w / 2, phh = h / 2;
  const look = memeLook(seed, 0);
  return (
    <div style={{position: 'absolute', inset: 0, background: '#111'}}>
      {steps.map((t, i) => {
        const delay = Math.round(frames * (0.03 + i * 0.2));
        const last = i === 3;
        const bw = pw * (BOX.V ? 0.46 : 0.5), bh = phh * 0.72, bx = pw * (BOX.V ? 0.5 : 0.44);
        return (
          <Panel key={i} x={(i % 2) * pw + (i % 2 ? 3 : 0)} y={Math.floor(i / 2) * phh + (i > 1 ? 3 : 0)} w={pw - 3} h={phh - 3}
            bg={last ? 'linear-gradient(#dbeafe, #93c5fd)' : 'linear-gradient(#f1f5f9, #cbd5e1)'} delay={delay}>
            <div style={{position: 'absolute', left: bx, top: phh * 0.08, width: bw, height: bh, background: '#fff', border: '6px solid #374151', borderRadius: 6,
              display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 10, boxSizing: 'border-box'}}>
              <Words text={t} font={MARKER} size={fit(t, bw - 30, 4, BOX.V ? 40 : 44, 16, 0.62)} delay={delay + 3} style={{textAlign: 'center', fontWeight: 400}} />
            </div>
            <div style={{position: 'absolute', left: bx + bw * 0.2, top: phh * 0.08 + bh, width: 10, height: phh * 0.2, background: '#374151'}} />
            <div style={{position: 'absolute', left: bx + bw * 0.8, top: phh * 0.08 + bh, width: 10, height: phh * 0.2, background: '#374151'}} />
            <Guy look={look} pose={last ? 'hands-head' : 'present'} mood={last ? 'shocked' : 'happy'} x={pw * 0.22} feet={phh * (BOX.V ? 1.3 : 1.45)}
              h={phh * (BOX.V ? 1.2 : 1.4)} delay={delay} />
          </Panel>
        );
      })}
    </div>
  );
};

const Pointing: React.FC<F> = ({labels, w, h, seed}) => {
  const tall = BOX.V;
  const ph = h * (tall ? 0.72 : 0.92);
  const look = memeLook(seed, 0);
  const size = fit(labels.reduce((a, b) => (a.length > b.length ? a : b), ''), w * 0.4, 2, tall ? 54 : 64, 22);
  return (
    <div style={{position: 'absolute', inset: 0, background: 'linear-gradient(#3b4a7a, #1d2747)'}}>
      <svg width={w} height={h} style={{position: 'absolute', inset: 0}}>
        <rect y={h * 0.78} width={w} height={h * 0.22} fill="#2a2f45" />
        {[0.15, 0.85].map((x, i) => <rect key={i} x={x * w - 50} y={h * 0.12} width={100} height={h * 0.5} fill="#55669a" opacity={0.5} />)}
      </svg>
      <Guy look={look} pose="point" mood="shocked" x={w * 0.3} feet={h * 0.98} h={ph} delay={2} />
      <Guy look={look} pose="point" mood="shocked" x={w * 0.7} feet={h * 0.98} h={ph} flip delay={8} />
      {labels.slice(0, 2).map((t, i) => (
        <Shout key={i} text={t} size={size} width={w * 0.44} delay={[6, 12][i]} style={{left: i ? w * 0.53 : w * 0.03, top: tall ? h * 0.08 : 18}} />
      ))}
    </div>
  );
};

const StarterPack: React.FC<F> = ({v, labels, frames, w, h}) => {
  const tall = BOX.V;
  const raw = labels[0] ?? '';
  const title = /starter pack/i.test(raw) ? raw : `${raw} starter pack`;
  const items = labels.slice(1, 5);
  const cols = tall ? 2 : Math.max(2, items.length), rows = Math.ceil(items.length / cols) || 1;
  const head = tall ? 150 : 120;
  const tw = w / cols, th = (h - head) / rows;
  return (
    <div style={{position: 'absolute', inset: 0, background: '#fff'}}>
      <div style={{position: 'absolute', left: 0, top: 0, width: w, height: head, display: 'flex', alignItems: 'center', justifyContent: 'center', borderBottom: '5px solid #111'}}>
        <Words text={title} size={fit(title, w - 60, tall ? 2 : 1, tall ? 60 : 66, 26)} delay={2} style={{textAlign: 'center', textTransform: 'none'}} />
      </div>
      {items.map((t, i) => {
        const Icon = iconFor(v.icons?.[i] || 'sparkles');
        const delay = Math.round(6 + i * Math.max(4, frames * 0.12));
        const s = Math.min(tw, th);
        return (
          <Panel key={i} x={(i % cols) * tw} y={head + Math.floor(i / cols) * th} w={tw} h={th} bg="#fff" delay={delay}>
            <div style={{position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 12,
              borderRight: (i % cols) < cols - 1 ? '3px solid #e5e7eb' : 'none'}}>
              <div style={{width: s * 0.62, height: s * 0.62, borderRadius: 28, background: '#f3f4f6', display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
                <Icon size={s * 0.42} color="#111827" strokeWidth={2} />
              </div>
              <Words text={t} size={fit(t, tw - 40, 2, 48, 20)} delay={delay + 2} style={{textAlign: 'center', padding: '0 14px'}} />
            </div>
          </Panel>
        );
      })}
    </div>
  );
};

const FACE_BG: Record<MemeFace, string> = {
  shocked: '#1f2937', crying: '#1e3a8a', laughing: '#f59e0b', 'side-eye': '#334155', smug: '#6d28d9', sweating: '#475569',
  'mind-blown': '#0f172a', confused: '#0f766e', angry: '#7f1d1d', deadpan: '#4b5563',
};

const Reaction: React.FC<F> = ({v, labels, frames, w, h, seed}) => {
  const face: MemeFace = v.face && v.face in FACE_BG ? v.face : 'shocked';
  const size = Math.min(w * 0.62, h * 0.64);
  const top = labels[0] ?? '', bottom = labels[1] ?? '';
  return (
    <div style={{position: 'absolute', inset: 0, background: `radial-gradient(circle at 50% 50%, ${shade(FACE_BG[face], 0.25)}, ${FACE_BG[face]} 70%)`}}>
      <div style={{position: 'absolute', left: (w - size) / 2, top: (h - size * 1.05) / 2 + (BOX.V ? 0 : 20)}}>
        <BigFace face={face} look={memeLook(seed, 0)} size={size} frames={frames} />
      </div>
      <Shout text={top} size={fit(top, w * 0.92, 2, BOX.V ? 64 : 74, 24)} width={w * 0.94} delay={2} style={{left: w * 0.03, top: 14}} />
      <Shout text={bottom} size={fit(bottom, w * 0.92, 2, BOX.V ? 64 : 74, 24)} width={w * 0.94} delay={Math.round(frames * 0.32)} style={{left: w * 0.03, bottom: 16}} />
    </div>
  );
};

// The user's own meme picture or clip (Settings > Media library > Memes), with top and bottom text.
const OwnMeme: React.FC<F> = ({v, labels, frames, w, h}) => {
  const top = labels[0] ?? '', bottom = labels[1] ?? '';
  const isVideo = /\.(mp4|webm|mov)$/i.test(v.src ?? '');
  return (
    <div style={{position: 'absolute', inset: 0, background: '#000'}}>
      {isVideo ? <OffthreadVideo src={staticFile(v.src!)} muted style={{width: '100%', height: '100%', objectFit: 'contain'}} />
        : <Img src={staticFile(v.src!)} style={{width: '100%', height: '100%', objectFit: 'contain'}} />}
      <Shout text={top} size={fit(top, w * 0.92, 2, BOX.V ? 64 : 74, 24)} width={w * 0.94} delay={2} style={{left: w * 0.03, top: 14}} />
      <Shout text={bottom} size={fit(bottom, w * 0.92, 2, BOX.V ? 64 : 74, 24)} width={w * 0.94} delay={Math.round(frames * 0.32)} style={{left: w * 0.03, bottom: 16}} />
    </div>
  );
};

const FORMATS: Record<MemeFormat, React.FC<F>> = {
  'two-buttons': TwoButtons,
  'nope-yep': NopeYep,
  distracted: Distracted,
  brain: ExpandingBrain,
  'this-is-fine': ThisIsFine,
  'panik-kalm': PanikKalm,
  'expectation-reality': ExpectationReality,
  'nobody-me': NobodyMe,
  stonks: (p) => <Stonks {...p} />,
  'not-stonks': (p) => <Stonks {...p} down />,
  'change-my-mind': ChangeMyMind,
  plan: Plan,
  pointing: Pointing,
  'starter-pack': StarterPack,
  reaction: Reaction,
};

// The card the meme sits on, over the video's own backdrop: a white-edged picture that pops in, tilted a little.
export const MemeView: React.FC<{v: Visual; frames: number; roomy: boolean; seed: number}> = ({v, frames, roomy, seed}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const s = spring({frame, fps, config: {damping: 12, mass: 0.7}});
  const exit = exitProgress(frame, frames, 9);
  const top = roomy ? (BOX.V ? BOX.TOP : 70) : BOX.TOP;
  const bottom = roomy ? (BOX.V ? 1460 : 1010) : BOX.BOTTOM;
  const W = BOX.V ? BOX.INNER : Math.min(BOX.INNER, roomy ? 1560 : 1400);
  const H = bottom - top;
  const border = 10;
  const w = W - border * 2, h = H - border * 2;
  const labels = (v.labels ?? []).map((t) => t.trim()).filter(Boolean);
  const Format = v.src ? OwnMeme : FORMATS[v.meme as MemeFormat] ?? Reaction;
  const tilt = ((seed % 2) ? 1 : -1) * interpolate(s, [0, 1], [5, 0.8]);
  return (
    <div style={{position: 'absolute', left: (BOX.W - W) / 2, top, width: W, height: H, transform: `scale(${(0.8 + 0.2 * Math.min(1.02, s)) * (1 - 0.05 * exit)}) rotate(${tilt}deg)`,
      opacity: Math.min(1, s * 1.8) * (1 - exit), borderRadius: 18, background: '#fff', boxShadow: '0 30px 90px rgba(0,0,0,0.6)', padding: border, boxSizing: 'border-box'}}>
      <div style={{position: 'relative', width: w, height: h, overflow: 'hidden', borderRadius: 10, fontFamily: FONT}}>
        <Format v={v} labels={labels} frames={frames} w={w} h={h} seed={seed} />
      </div>
    </div>
  );
};
