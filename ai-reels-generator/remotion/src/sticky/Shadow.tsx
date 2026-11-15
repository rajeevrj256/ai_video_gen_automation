import React from 'react';
import {interpolate, random} from 'remotion';
import {Bean} from './Bean';
import type {Cast, Shadow} from './types';

// The inner voice as a character (reelgen/sticky/ANALYSIS.md): a black silhouette with a glowing outline in the
// film's accent (pink for a craving, red for fear), crescent eyes and a crescent smile. It appears, leans in, grows
// when he gives in, looms as a giant, can wear his own face ("it learned to sound like him"), and dissolves into
// particles when he walks away. Drawn with its feet at (0, 0).

const SIZE = {small: 0.72, normal: 1.15, giant: 1.75};
const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

export const ShadowView: React.FC<{s: Shadow; t: number; dur: number; accent: string; cast?: Cast; facing: 1 | -1}> = ({s, t, dur, accent, cast, facing}) => {
  const appear = s.act === 'appear' ? interpolate(t, [0, 0.7], [0, 1], clamp) : 1;
  const grow = s.act === 'grow' ? interpolate(t, [0, dur], [1, s.size === 'giant' ? 1.15 : 1.5], clamp) : 1;
  const lean = s.act === 'lean' || s.act === 'whisper' ? interpolate(t, [0, 0.8], [0, 1], clamp) : 0;
  const gone = s.act === 'dissolve' ? interpolate(t, [0.2, 1.4], [0, 1], clamp) : 0;
  const bob = Math.sin(t * 2.2) * 4;
  const k = SIZE[s.size] * grow;
  const glow = `drop-shadow(0 0 ${10 + 6 * Math.sin(t * 3)}px ${accent}) drop-shadow(0 0 3px ${accent})`;
  if (s.copy && cast) {
    // the voice wearing his face: his own bean, darkened, a glowing ring under the feet
    return (
      <g opacity={appear * (1 - gone)} transform={`translate(0,${(1 - appear) * 30}) scale(${SIZE.normal * 0.9 * grow})`}>
        <ellipse cx={0} cy={4} rx={64} ry={12} fill="none" stroke={accent} strokeWidth={4} style={{filter: glow}} />
        {/* his own outline (hood, hair) in black, with the voice's glow and its crescent face: a grey twin of him read
            as a ghost */}
        <g style={{filter: `brightness(0) ${glow}`}}>
          <Bean cast={{...cast, id: cast.id + '-voice'}} actor={{id: cast.id, x: 0, pose: 'stand', face: 'neutral', facing: facing === 1 ? 'right' : 'left'}} t={t} dur={dur} seat={-118} />
        </g>
        <g stroke={accent} strokeWidth={6} fill="none" strokeLinecap="round" style={{filter: `drop-shadow(0 0 6px ${accent})`}}>
          <path d="M-34,-246 Q-22,-234 -10,-246" />
          <path d="M12,-246 Q24,-234 36,-246" />
          <path d="M-22,-214 Q2,-196 26,-214" />
        </g>
        {gone > 0 ? <Particles t={t} accent={accent} k={1} gone={gone} /> : null}
      </g>
    );
  }
  return (
    <g transform={`scale(${facing},1)`}>
      <g opacity={appear * (1 - gone * 0.95)} transform={`translate(0,${(1 - appear) * 60 + bob}) scale(${k}) rotate(${-lean * 8},0,0)`}>
        <g style={{filter: glow}}>
          {/* legs, body, long arms */}
          <path d="M-22,-110 L-30,0 M22,-110 L30,0" stroke="#050507" strokeWidth={26} strokeLinecap="round" />
          <path d="M-46,-210 C-74,-170 -92,-120 -96,-70 M46,-210 C74,-170 92,-120 96,-70" stroke="#050507" strokeWidth={22} strokeLinecap="round" fill="none" />
          <path d="M-52,-224 C-60,-150 -54,-110 -40,-96 C-20,-84 20,-84 40,-96 C54,-110 60,-150 52,-224 Z" fill="#050507" />
          <circle cx={0} cy={-268} r={66} fill="#050507" />
        </g>
        {/* the face: crescent eyes and a crescent smile, glowing */}
        <g stroke={accent} strokeWidth={6} fill="none" strokeLinecap="round" style={{filter: `drop-shadow(0 0 6px ${accent})`}}>
          <path d="M-36,-280 Q-24,-268 -12,-280" />
          <path d="M14,-280 Q26,-268 38,-280" />
          <path d={s.act === 'loom' || s.act === 'grow' ? 'M-30,-244 Q2,-214 34,-244' : 'M-24,-246 Q2,-226 28,-246'} />
        </g>
      </g>
      {gone > 0 ? <Particles t={t} accent={accent} k={k} gone={gone} /> : null}
    </g>
  );
};

const Particles: React.FC<{t: number; accent: string; k: number; gone: number}> = ({accent, k, gone}) => (
  <g>
    {Array.from({length: 70}, (_, i) => {
      const x0 = (random(`px${i}`) - 0.5) * 140 * k;
      const y0 = -random(`py${i}`) * 320 * k;
      const drift = 40 + random(`pd${i}`) * 160;
      const x = x0 + (random(`pv${i}`) - 0.5) * drift * gone;
      const y = y0 - drift * gone * 1.4;
      const r = 2 + random(`pr${i}`) * 5;
      return <circle key={i} cx={x} cy={y} r={r * (1 - gone * 0.6)} fill={i % 3 ? accent : '#ffffff'} opacity={(1 - gone) * 0.9} />;
    })}
  </g>
);
