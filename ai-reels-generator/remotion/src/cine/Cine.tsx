import '@fontsource/courier-prime/700.css';
import React, {useEffect, useState} from 'react';
import {Easing, continueRender, delayRender, interpolate, random, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {Bell, Check, MousePointer2} from 'lucide-react';
import {clamp} from '../theme';
import {type CineTransition, type Grade, LABEL_AT, TRANSITION_FRAMES, TYPE_EVERY} from './types';

// The cinematic hook's effects (see ./types.ts). Every piece is cheap CSS on top of whatever the shot draws
// (a motion graphic, footage, an AI picture or clip), so the hook costs about what it did before.

export const useCineFonts = () => {
  const [handle] = useState(() => delayRender('Loading the hook label font'));
  useEffect(() => {
    document.fonts.load('700 60px "Courier Prime"').catch(() => undefined).finally(() => continueRender(handle));
  }, [handle]);
};

// ---------- grades ----------

// The picture's own colour per beat: warm archive amber, red alarm, black-and-white, fire, cold steel.
const FILTERS: Record<Grade, string> = {
  amber: 'sepia(0.5) saturate(1.3) contrast(1.14) brightness(0.94)',
  red: 'grayscale(1) contrast(1.4) brightness(0.86)',
  noir: 'grayscale(1) contrast(1.38) brightness(0.9)',
  fire: 'sepia(0.35) saturate(1.75) contrast(1.2) brightness(0.96)',
  cold: 'saturate(0.6) contrast(1.16) brightness(0.84)',
  natural: 'contrast(1.08) saturate(1.04)',
};

export const gradeFilter = (g?: Grade) => FILTERS[g ?? 'natural'] ?? FILTERS.natural;

// The colour wash over the graded picture (drawn above it, under the labels).
export const GradeWash: React.FC<{grade?: Grade}> = ({grade = 'natural'}) => {
  const frame = useCurrentFrame();
  const wash: Record<Grade, React.CSSProperties | null> = {
    amber: {background: 'linear-gradient(180deg, rgba(255,176,64,0.26), rgba(130,58,0,0.32))', mixBlendMode: 'soft-light'},
    red: {background: 'rgba(196,14,24,0.82)', mixBlendMode: 'multiply'}, // white turns blood red, shadows stay black
    noir: {background: 'radial-gradient(ellipse at center, rgba(255,255,255,0.06), rgba(0,0,0,0.25))'},
    fire: {background: `linear-gradient(0deg, rgba(255,86,0,${0.42 + 0.1 * Math.sin(frame * 0.9) * Math.sin(frame * 0.37)}), rgba(255,140,0,0.08) 60%, rgba(60,10,0,0.3))`, mixBlendMode: 'overlay'},
    cold: {background: 'linear-gradient(180deg, rgba(60,130,190,0.55), rgba(20,50,90,0.6))', mixBlendMode: 'multiply'},
    natural: null,
  };
  const style = wash[grade];
  return style ? <div style={{position: 'absolute', inset: 0, ...style}} /> : null;
};

// ---------- film texture ----------

const GRAIN = `url("data:image/svg+xml;utf8,${encodeURIComponent(
  `<svg xmlns="http://www.w3.org/2000/svg" width="220" height="220"><filter id="n"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="3" stitchTiles="stitch"/><feColorMatrix type="saturate" values="0"/></filter><rect width="220" height="220" filter="url(#n)"/></svg>`,
)}")`;

// Grain, dust, the odd scratch, a projector's flicker and a heavy vignette over the whole hook.
export const FilmTexture: React.FC<{strength?: number}> = ({strength = 1}) => {
  const frame = useCurrentFrame();
  const flicker = 0.04 + 0.06 * random(`fl${frame}`);
  const scratch = random(`sc${Math.floor(frame / 5)}`) < 0.3; // a scratch runs for a few frames now and then
  return (
    <>
      <div style={{position: 'absolute', inset: 0, backgroundImage: GRAIN, backgroundPosition: `${(frame * 53) % 220}px ${(frame * 97) % 220}px`,
        mixBlendMode: 'overlay', opacity: 0.22 * strength}} />
      {Array.from({length: 9}, (_, i) => {
        const r = random(`du${frame}-${i}`);
        if (r > 0.55) return null; // specks come and go every frame
        const size = 2 + random(`ds${frame}-${i}`) * 5;
        return <div key={i} style={{position: 'absolute', left: `${random(`dx${frame}-${i}`) * 100}%`, top: `${random(`dy${frame}-${i}`) * 100}%`,
          width: size, height: size * (0.6 + random(`dh${frame}-${i}`)), borderRadius: '50%', background: r < 0.25 ? '#000' : '#fff', opacity: 0.35 * strength}} />;
      })}
      {scratch ? (
        <div style={{position: 'absolute', top: 0, bottom: 0, left: `${8 + random(`sx${Math.floor(frame / 5)}`) * 84 + Math.sin(frame) * 0.15}%`, width: 1.5,
          background: 'linear-gradient(180deg, transparent, rgba(255,255,255,0.35) 20%, rgba(255,255,255,0.2) 80%, transparent)', opacity: strength}} />
      ) : null}
      <div style={{position: 'absolute', inset: 0, background: '#000', opacity: flicker * strength}} />
      <div style={{position: 'absolute', inset: 0, background: 'radial-gradient(ellipse at center, transparent 42%, rgba(0,0,0,0.72) 100%)'}} />
    </>
  );
};

// ---------- typed labels ----------

const DEVANAGARI = /[ऀ-ॿ]/;
const letters = (text: string): string[] => {
  try {
    return Array.from(new Intl.Segmenter(undefined, {granularity: 'grapheme'}).segment(text), (s) => s.segment);
  } catch {
    return Array.from(text);
  }
};

// "DAMASCUS, 1965" typed onto the picture in glowing yellow, one letter every TYPE_EVERY s, with a red cursor
// that keeps blinking after the last letter. The typewriter sound (reelgen/sfx.py hook-type-N) is cut to match.
// `subtitles`: the video shows subtitles, so the label sits above them instead of over them.
export const TypedLabel: React.FC<{text: string; vertical?: boolean; at?: number; color?: string; subtitles?: boolean}> = ({text, vertical, at = LABEL_AT, color = '#FFD23F', subtitles}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = frame / fps - at;
  if (t < 0 || !text) return null;
  const all = letters(text);
  const n = Math.min(all.length, Math.floor(t / TYPE_EVERY) + 1);
  const typing = n < all.length;
  const cursor = typing || Math.floor(t * 2.4) % 2 === 0;
  const hindi = DEVANAGARI.test(text);
  return (
    <div style={{position: 'absolute', left: vertical ? 60 : 110, right: vertical ? 60 : undefined, bottom: vertical ? (subtitles ? 730 : 560) : subtitles ? 250 : 140, display: 'flex',
      justifyContent: vertical ? 'center' : 'flex-start'}}>
      <div style={{padding: '10px 26px 12px 22px', background: 'linear-gradient(90deg, rgba(0,0,0,0.62), rgba(0,0,0,0.35) 75%, rgba(0,0,0,0))',
        fontFamily: hindi ? '"Noto Sans Devanagari", sans-serif' : '"Courier Prime", "Courier New", monospace', fontWeight: 700,
        fontSize: vertical ? 56 : 62, letterSpacing: hindi ? 0 : '0.06em', textTransform: 'uppercase', color, whiteSpace: vertical ? 'normal' : 'nowrap',
        textShadow: '0 0 12px rgba(255,190,40,0.75), 0 0 32px rgba(255,140,0,0.45), 0 3px 6px rgba(0,0,0,0.85)'}}>
        {all.slice(0, n).join('')}
        <span style={{display: 'inline-block', width: '0.55em', height: '0.95em', marginLeft: '0.08em', verticalAlign: '-0.12em',
          background: '#FF3B30', boxShadow: '0 0 14px rgba(255,59,48,0.8)', opacity: cursor ? 1 : 0}} />
      </div>
    </div>
  );
};

// ---------- transitions in ----------

// A torn paper edge, the same for a given seed: x offsets (0-1 of the edge's width) at 24 points down the frame.
const tornEdge = (seed: number) => Array.from({length: 25}, (_, i) => random(`tear${seed}-${i}`));

// How a hook shot comes in. `frame` 0 is the cut; the shot before is still drawn underneath for photo and split.
export const CineIn: React.FC<{kind: CineTransition; seed: number; children: React.ReactNode}> = ({kind, seed, children}) => {
  const frame = useCurrentFrame();
  const {width, height, fps} = useVideoConfig();
  const n = TRANSITION_FRAMES[kind] ?? 0;
  const p = n ? interpolate(frame, [0, n], [0, 1], clamp) : 1;
  const ease = Easing.out(Easing.cubic)(p);
  const fill: React.CSSProperties = {position: 'absolute', inset: 0};
  switch (kind) {
    case 'whip': { // a zoom-blur whip: in fast, from a blur and a tilt, with a streak of light
      const k = 1 - ease;
      return (
        <div style={fill}>
          <div style={{...fill, transform: `translateX(${k * -340}px) scale(${1 + k * 0.38}) rotate(${k * -2.5}deg)`, filter: k > 0.01 ? `blur(${k * 26}px)` : undefined}}>{children}</div>
          {k > 0.01 ? <div style={{...fill, background: `linear-gradient(90deg, transparent, rgba(255,255,255,${0.5 * k}) 50%, transparent)`, mixBlendMode: 'screen'}} /> : null}
        </div>
      );
    }
    case 'glitch': { // a VHS tracking glitch: the frame jumps, colour bands, a bright line rolling down
      const on = frame < n;
      const jx = on ? (random(`gx${seed}-${frame}`) - 0.5) * 70 : 0;
      return (
        <div style={fill}>
          <div style={{...fill, transform: `translateX(${jx}px)`, filter: on ? `hue-rotate(${(random(`gh${seed}-${frame}`) - 0.5) * 120}deg) saturate(1.6) contrast(1.3)` : undefined}}>{children}</div>
          {on ? (
            <>
              {Array.from({length: 6}, (_, i) => (
                <div key={i} style={{position: 'absolute', left: 0, right: 0, top: `${random(`gb${seed}-${frame}-${i}`) * 100}%`, height: 8 + random(`gt${seed}-${frame}-${i}`) * 50,
                  background: i % 2 ? 'rgba(255,0,90,0.38)' : 'rgba(0,220,255,0.38)', transform: `translateX(${(random(`gs${seed}-${frame}-${i}`) - 0.5) * 220}px)`, mixBlendMode: 'screen'}} />
              ))}
              <div style={{position: 'absolute', left: 0, right: 0, top: `${(frame / n) * 100}%`, height: 26,
                background: 'linear-gradient(180deg, transparent, rgba(255,255,255,0.75), transparent)', mixBlendMode: 'screen'}} />
              <div style={{...fill, backgroundImage: 'repeating-linear-gradient(0deg, rgba(0,0,0,0.28) 0px, rgba(0,0,0,0.28) 2px, transparent 2px, transparent 5px)'}} />
            </>
          ) : null}
        </div>
      );
    }
    case 'photo': { // a print flies in over the last shot, lands askew, then fills the frame
      const fly = spring({frame, fps, config: {damping: 15, mass: 0.7}});
      const grow = interpolate(frame, [12, n], [0, 1], {...clamp, easing: Easing.inOut(Easing.cubic)});
      const s = 0.44 + 0.56 * grow;
      const x = (1 - fly) * width * 0.6 + (1 - grow) * width * 0.06;
      const y = (1 - fly) * height * 0.5 + (1 - grow) * height * 0.03;
      const r = (1 - grow) * (-6 + (1 - fly) * 10);
      const border = (1 - grow) * 26;
      return (
        <div style={fill}>
          <div style={{...fill, background: '#000', opacity: 0.5 * (1 - grow)}} />
          <div style={{...fill, transform: `translate(${x}px, ${y}px) rotate(${r}deg) scale(${s})`, boxShadow: grow < 1 ? `0 40px 90px rgba(0,0,0,${0.7 * (1 - grow)})` : undefined, overflow: 'hidden'}}>
            {children}
            {grow < 1 ? (
              <>
                <div style={{...fill, backgroundImage: 'radial-gradient(rgba(0,0,0,0.5) 1.2px, transparent 1.6px)', backgroundSize: '7px 7px', mixBlendMode: 'multiply', opacity: 0.55 * (1 - grow)}} />
                <div style={{...fill, boxShadow: `inset 0 0 0 ${border}px #efe9dc`}} />
              </>
            ) : null}
          </div>
        </div>
      );
    }
    case 'split': { // paper torn across the frame, left to right, uncovering the new shot
      const edge = tornEdge(seed);
      const pos = -0.08 + 1.2 * ease; // the tear's position across the frame (0-1)
      const pts = edge.map((r, i) => `${(pos + (r - 0.5) * 0.05) * 100}% ${(i / 24) * 100}%`);
      const clip = `polygon(0% 0%, ${pts.join(', ')}, 0% 100%)`;
      const strip = edge.map((r, i) => `${(pos + (r - 0.5) * 0.05) * width},${(i / 24) * height}`);
      const back = edge.slice().reverse().map((r, i) => `${(pos + (r - 0.5) * 0.05) * width + 14 + random(`ts${seed}-${i}`) * 16},${((24 - i) / 24) * height}`);
      return (
        <div style={fill}>
          <div style={{...fill, clipPath: p < 1 ? clip : undefined}}>{children}</div>
          {p < 1 ? (
            <svg width={width} height={height} style={{position: 'absolute', inset: 0}}>
              <polygon points={[...strip, ...back].join(' ')} fill="#f1ebdd" stroke="rgba(0,0,0,0.25)" strokeWidth={1.5} />
            </svg>
          ) : null}
        </div>
      );
    }
    case 'dip': // out of black
      return (
        <div style={fill}>
          {children}
          <div style={{...fill, background: '#000', opacity: 1 - ease}} />
        </div>
      );
    case 'punch': { // a hard cut in tight, settling
      const k = 1 - ease;
      return (
        <div style={fill}>
          <div style={{...fill, transform: `scale(${1 + 0.2 * k})`}}>{children}</div>
          <div style={{...fill, background: '#fff', opacity: interpolate(frame, [0, 3], [0.4, 0], clamp)}} />
        </div>
      );
    }
    default:
      return <div style={fill}>{children}</div>;
  }
};

// ---------- the silence before the story ----------

// The hook drops to silence before the story starts; in that breath, a subscribe button is clicked, no sound.
export const SubscribeCard: React.FC<{frames: number; vertical?: boolean}> = ({frames, vertical}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const inK = spring({frame: frame - 2, fps, config: {damping: 14, mass: 0.6}});
  const click = Math.round(frames * 0.45);
  const done = frame >= click;
  const press = interpolate(frame, [click - 2, click, click + 4], [1, 0.92, 1], clamp);
  const cur = interpolate(frame, [4, click - 1], [0, 1], {...clamp, easing: Easing.inOut(Easing.cubic)});
  const out = interpolate(frame, [frames - 6, frames], [1, 0], clamp);
  const ring = done ? Math.sin((frame - click) * 1.4) * 16 * Math.max(0, 1 - (frame - click) / 14) : 0;
  const scale = vertical ? 1.15 : 1;
  return (
    <div style={{position: 'absolute', inset: 0, background: '#000', display: 'flex', alignItems: 'center', justifyContent: 'center', opacity: out}}>
      <div style={{position: 'relative', display: 'flex', alignItems: 'center', gap: 26, transform: `scale(${scale * (0.85 + 0.15 * inK) * press})`, opacity: Math.min(1, inK * 1.4)}}>
        <div style={{display: 'flex', alignItems: 'center', gap: 14, height: 82, padding: '0 40px', borderRadius: 41, fontFamily: '"Montserrat", sans-serif', fontWeight: 800,
          fontSize: 36, letterSpacing: '0.04em', color: done ? '#d8d8d8' : '#fff', background: done ? '#2b2b2f' : '#E62117', boxShadow: done ? 'none' : '0 0 40px rgba(230,33,23,0.45)'}}>
          {done ? <Check size={34} strokeWidth={3} /> : null}
          {done ? 'SUBSCRIBED' : 'SUBSCRIBE'}
        </div>
        <div style={{transform: `rotate(${ring}deg)`, transformOrigin: '50% 10%', color: '#fff', opacity: done ? 1 : 0.55}}>
          <Bell size={52} strokeWidth={2.2} fill={done ? '#fff' : 'none'} />
        </div>
        <div style={{position: 'absolute', left: 160 + (1 - cur) * 260, top: 50 + (1 - cur) * 160, color: '#fff', filter: 'drop-shadow(0 4px 8px rgba(0,0,0,0.6))', opacity: frame < frames - 8 ? 1 : 0}}>
          <MousePointer2 size={52} fill="#fff" stroke="#111" strokeWidth={1.5} />
        </div>
      </div>
    </div>
  );
};
