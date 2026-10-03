import React from 'react';
import {Easing, Freeze, Img, Sequence, interpolate, random, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {COLORS, FONT, clamp} from '../theme';
import {Layer} from '../Layer';
import type {Camera, Hook, HookShot, Look, Visual} from './types';

// The camera, this video's look (backdrop and transitions), impacts and the cinematic hook.
// Every video gets its own palette, backdrop style and transition style (reelgen/variety.py),
// so no two long videos look alike, while the typography and line style stay the brand.

const DEFAULT_LOOK: Look = {
  palette: 'default',
  worlds: [['#0B1E3F', '#1B4F72'], ['#2B0F3A', '#6A1B6E'], ['#0E2E24', '#1E6B4E'], ['#3A0E14', '#8E2430'], ['#14213D', '#3D5A80']],
  accents: ['#FFD60A', '#4DD0E1', '#FFB74D', '#FFE082', '#FF8A65'],
  backdrop: 'blobs',
  transition: 'smooth',
  seed: 1,
};

export const lookOf = (look?: Look) => look ?? DEFAULT_LOOK;
export const worldFor = (look: Look, chapter: number) => {
  const [a, b] = look.worlds[chapter % look.worlds.length];
  return {a, b, accent: look.accents[chapter % look.accents.length]};
};

// ---------- the camera ----------

// How the camera moves across a beat: 0 -> 1 over the beat, eased.
const cameraAt = (camera: Camera, p: number, frame: number) => {
  const e = Easing.inOut(Easing.cubic)(p);
  switch (camera) {
    case 'pull':
      return {s: 1.16 - 0.14 * e, x: 0, y: 0, r: 0};
    case 'pan-left':
      return {s: 1.1, x: 70 - 140 * e, y: 0, r: 0};
    case 'pan-right':
      return {s: 1.1, x: -70 + 140 * e, y: 0, r: 0};
    case 'rise':
      return {s: 1.08, x: 0, y: 60 - 100 * e, r: 0};
    case 'dutch':
      return {s: 1.1 + 0.04 * e, x: 0, y: 0, r: -3.5 * e};
    case 'orbit':
      return {s: 1.09, x: 50 * Math.sin(frame / 40), y: 20 * Math.cos(frame / 40), r: 1.4 * Math.sin(frame / 55)};
    case 'still':
      return {s: 1.02, x: 0, y: 0, r: 0};
    default: // push
      return {s: 1 + 0.13 * e, x: 0, y: -10 * e, r: 0};
  }
};

// One beat's frame: the camera move, the look's transition into the beat, and (for the
// chapter's biggest moment) a punch-in, a short freeze with a flash and a screen shake.
export const Shot: React.FC<{
  v: Visual;
  frames: number;
  transition: Look['transition'];
  intense?: boolean; // the hook: faster, more dramatic
  children: React.ReactNode;
}> = ({v, frames, transition, intense, children}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const cam = cameraAt(v.camera ?? 'push', frame / Math.max(1, frames), frame);
  // Wide layouts (a timeline, a comparison, steps, a chart) use the whole frame: a big move would crop them.
  const wide = ['timeline', 'compare', 'steps', 'chart'].includes(v.type);
  const k = (intense ? 1.8 : 1) * (wide ? 0.35 : 1);
  // Transition in.
  const tin = interpolate(frame, [0, 9], [0, 1], {...clamp, easing: Easing.out(Easing.cubic)});
  let tx = 0;
  let ty = 0;
  let ts = 1;
  let blur = 0;
  let opacity = 1;
  let flash = 0;
  let glitch = 0;
  switch (transition) {
    case 'whip':
      tx = (1 - tin) * 520;
      blur = (1 - tin) * 22;
      break;
    case 'zoom':
      ts = 1 + (1 - tin) * 0.4;
      blur = (1 - tin) * 12;
      break;
    case 'glitch':
      glitch = frame < 5 ? 1 : 0;
      break;
    case 'flash':
      flash = interpolate(frame, [0, 7], [0.85, 0], clamp);
      break;
    case 'slide':
      ty = (1 - tin) * 160;
      opacity = tin;
      break;
    default:
      opacity = interpolate(frame, [0, 7], [0, 1], clamp);
      ts = 1 + (1 - tin) * 0.04;
  }
  // Impact: punch-in, shake, flash, freeze.
  const at = Math.round((v.impactAt ?? 0.5) * fps);
  const hit = v.impact ? frame - at : -1;
  const punch = hit >= 0 ? 0.12 * spring({frame: hit, fps, config: {damping: 8, mass: 0.5}}) * interpolate(hit, [0, 30], [1, 0.4], clamp) : 0;
  const shake = hit >= 0 && hit < 14 ? (14 - hit) * 1.3 : 0;
  const sx = shake ? Math.sin(hit * 2.7) * shake : 0;
  const sy = shake ? Math.cos(hit * 3.1) * shake * 0.7 : 0;
  const freezing = v.impact === true && hit >= 0 && hit < Math.round(0.35 * fps);
  flash = Math.max(flash, hit >= 0 ? interpolate(hit, [0, 4], [0.9, 0], clamp) : 0);
  const scale = (1 + (cam.s - 1) * k) * ts * (1 + punch);
  return (
    <Layer name="shot">
      <div
        style={{
          position: 'absolute',
          inset: 0,
          opacity,
          transform: `translate(${cam.x * k + tx + sx}px, ${cam.y * k + ty + sy}px) rotate(${cam.r * k}deg) scale(${scale})`,
          filter: [blur ? `blur(${blur}px)` : '', freezing ? 'saturate(0.25) contrast(1.25)' : ''].join(' ') || undefined,
        }}
      >
        <Freeze frame={at} active={freezing}>
          {children}
        </Freeze>
      </div>
      {glitch ? <GlitchBars seed={frame} /> : null}
      {flash > 0 ? <div style={{position: 'absolute', inset: 0, background: '#fff', opacity: flash}} /> : null}
    </Layer>
  );
};

const GlitchBars: React.FC<{seed: number}> = ({seed}) => (
  <>
    {Array.from({length: 7}, (_, i) => (
      <div
        key={i}
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          top: `${random(`g${seed}-${i}`) * 100}%`,
          height: 10 + random(`h${seed}-${i}`) * 60,
          background: i % 2 ? 'rgba(255,0,90,0.35)' : 'rgba(0,220,255,0.35)',
          transform: `translateX(${(random(`x${seed}-${i}`) - 0.5) * 160}px)`,
          mixBlendMode: 'screen',
        }}
      />
    ))}
  </>
);

// ---------- backdrops ----------

// A real photo of the chapter's own setting (reelgen/longform._plates), darkened and softened under
// the visuals and drifting slowly, tinted with this video's palette; the abstract style shows through faintly.
const Plate: React.FC<{src: string; tint: string; seed: number}> = ({src, tint, seed}) => {
  const frame = useCurrentFrame();
  const dir = seed % 2 ? 1 : -1;
  const scale = 1.12 + 0.06 * Math.min(1, frame / 600);
  return (
    <>
      <Img
        src={staticFile(src)}
        style={{
          position: 'absolute',
          inset: 0,
          width: '100%',
          height: '100%',
          objectFit: 'cover',
          transform: `scale(${scale}) translateX(${dir * Math.min(40, frame * 0.06)}px)`,
          filter: 'blur(3px) brightness(0.42) saturate(0.85) contrast(1.05)',
        }}
      />
      <div style={{position: 'absolute', inset: 0, background: `linear-gradient(135deg, ${tint}cc 0%, ${tint}55 45%, rgba(0,0,0,0.55) 100%)`}} />
    </>
  );
};

export const Backdrop: React.FC<{look: Look; chapter: number; seed: number; plate?: string | null}> = ({look, chapter, seed, plate}) => {
  const frame = useCurrentFrame() + seed * 37;
  const p = worldFor(look, chapter);
  if (plate) {
    return (
      <Layer name="backdrop photo">
        <div style={{position: 'absolute', inset: 0, background: COLORS.ink}} />
        <Plate src={plate} tint={p.a} seed={seed} />
        <div style={{position: 'absolute', inset: 0, background: 'radial-gradient(ellipse at center, transparent 45%, rgba(0,0,0,0.6) 100%)'}} />
      </Layer>
    );
  }
  const base = `linear-gradient(135deg, ${p.a}, ${COLORS.ink})`;
  const gx = 50 + 25 * Math.sin(frame / 140);
  const gy = 40 + 18 * Math.cos(frame / 170);
  const glow = `radial-gradient(ellipse 70% 60% at ${gx}% ${gy}%, ${p.b}, transparent 70%)`;
  let layer: React.ReactNode = null;
  switch (look.backdrop) {
    case 'grid':
      layer = (
        <div
          style={{
            position: 'absolute',
            left: '-50%',
            right: '-50%',
            top: '45%',
            height: '120%',
            transform: 'perspective(700px) rotateX(62deg)',
            backgroundImage: `linear-gradient(${p.accent}33 2px, transparent 2px), linear-gradient(90deg, ${p.accent}33 2px, transparent 2px)`,
            backgroundSize: '120px 120px',
            backgroundPosition: `0px ${(frame * 2) % 120}px`,
            maskImage: 'linear-gradient(180deg, transparent, black 40%)',
          }}
        />
      );
      break;
    case 'rays':
      layer = (
        <div
          style={{
            position: 'absolute',
            left: '50%',
            top: '-40%',
            width: 3200,
            height: 3200,
            transform: `translateX(-50%) rotate(${frame * 0.05}deg)`,
            background: `repeating-conic-gradient(from 0deg, ${p.accent}14 0deg 6deg, transparent 6deg 18deg)`,
            maskImage: 'radial-gradient(circle, black 0%, transparent 55%)',
          }}
        />
      );
      break;
    case 'waves':
      layer = (
        <svg width={1920} height={1080} style={{position: 'absolute', inset: 0}}>
          {[0, 1, 2].map((k) => {
            const pts = Array.from({length: 49}, (_, i) => {
              const x = i * 40;
              const y = 700 + k * 90 + Math.sin(i / 5 + frame / (60 + k * 15) + k) * (40 + k * 12);
              return `${x},${y}`;
            });
            return <polyline key={k} points={pts.join(' ')} fill="none" stroke={p.accent} strokeOpacity={0.12 + k * 0.05} strokeWidth={3} />;
          })}
        </svg>
      );
      break;
    case 'dots':
      layer = (
        <>
          {Array.from({length: 36}, (_, i) => (
            <div
              key={i}
              style={{
                position: 'absolute',
                left: `${(random(`dx${i}`) * 100 + frame * 0.03 * (1 + (i % 4))) % 100}%`,
                top: `${(random(`dy${i}`) * 100 + frame * 0.02 * (i % 3)) % 100}%`,
                width: 6 + (i % 5) * 4,
                height: 6 + (i % 5) * 4,
                borderRadius: '50%',
                background: p.accent,
                opacity: 0.08 + 0.1 * Math.abs(Math.sin(frame / 40 + i)),
                filter: i % 3 ? 'blur(2px)' : 'blur(6px)',
              }}
            />
          ))}
        </>
      );
      break;
    case 'paper':
      layer = (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            background: `radial-gradient(ellipse at ${30 + 10 * Math.sin(frame / 200)}% 20%, ${p.accent}22, transparent 50%)`,
          }}
        />
      );
      break;
    default: // blobs
      layer = (
        <>
          {[0, 1, 2, 3].map((k) => (
            <div
              key={k}
              style={{
                position: 'absolute',
                width: 520 + k * 140,
                height: 520 + k * 140,
                borderRadius: '50%',
                left: `${(k * 29 + 10 + 8 * Math.sin((frame + k * 90) / (200 + k * 40))) % 100}%`,
                top: `${(k * 41 + 5 + 10 * Math.cos((frame + k * 60) / (230 + k * 30))) % 90}%`,
                transform: 'translate(-50%, -50%)',
                background: `radial-gradient(circle, ${p.accent}14, transparent 65%)`,
              }}
            />
          ))}
        </>
      );
  }
  return (
    <Layer name={`backdrop ${look.backdrop}`} style={{background: `${glow}, ${base}`}}>
      {layer}
      <div style={{position: 'absolute', inset: 0, background: 'radial-gradient(ellipse at center, transparent 50%, rgba(0,0,0,0.55) 100%)'}} />
    </Layer>
  );
};

// ---------- the hook ----------

// A cinematic trailer before the video: its own dark, graded world with light rays, drifting
// dust and letterbox bars, fast dramatic camera, words slammed in, and a glitch cut into the video.
export const HookView: React.FC<{hook: Hook; look: Look; render: (shot: HookShot, frames: number) => React.ReactNode}> = ({hook, look, render}) => {
  const {fps} = useVideoConfig();
  const frame = useCurrentFrame();
  const f = (s: number) => Math.round(s * fps);
  const total = f(hook.duration);
  const accent = look.accents[0];
  const bars = interpolate(frame, [0, 10, total - 6, total], [0, 1, 1, 0], clamp);
  const cut = interpolate(frame, [total - f(0.8), total - f(0.3)], [0, 1], clamp);
  return (
    <Layer name="hook" style={{background: '#050507'}}>
      <HookWorld accent={accent} />
      {hook.shots.map((s, i) => (
        <Sequence key={i} name={`hook ${i + 1} (${s.beat})`} from={f(s.start)} durationInFrames={f(s.duration)}>
          <Shot v={{...s.visual, camera: s.visual.camera === 'still' ? 'push' : s.visual.camera}} frames={f(s.duration)} transition={i % 2 ? 'glitch' : 'flash'} intense>
            {render(s, f(s.duration))}
          </Shot>
          {s.text ? <Slam text={s.text} accent={accent} /> : null}
        </Sequence>
      ))}
      {/* grade: crushed edges, a touch of teal/orange */}
      <div style={{position: 'absolute', inset: 0, background: 'radial-gradient(ellipse at center, transparent 35%, rgba(0,0,0,0.75) 100%)'}} />
      <div style={{position: 'absolute', inset: 0, background: `linear-gradient(180deg, rgba(0,80,90,0.18), transparent 40%, rgba(120,50,0,0.16))`, mixBlendMode: 'overlay'}} />
      {/* the cut into the video */}
      {cut > 0 ? (
        <>
          <GlitchBars seed={frame} />
          <div style={{position: 'absolute', inset: 0, background: '#000', opacity: cut}} />
        </>
      ) : null}
      <div style={{position: 'absolute', left: 0, right: 0, top: 0, height: 132 * bars, background: '#000'}} />
      <div style={{position: 'absolute', left: 0, right: 0, bottom: 0, height: 132 * bars, background: '#000'}} />
    </Layer>
  );
};

const HookWorld: React.FC<{accent: string}> = ({accent}) => {
  const frame = useCurrentFrame();
  return (
    <>
      <div
        style={{
          position: 'absolute',
          left: '50%',
          top: '-60%',
          width: 3400,
          height: 3400,
          transform: `translateX(-50%) rotate(${frame * 0.12}deg)`,
          background: `repeating-conic-gradient(from 0deg, ${accent}10 0deg 4deg, transparent 4deg 22deg)`,
          maskImage: 'radial-gradient(circle, black 0%, transparent 50%)',
        }}
      />
      {Array.from({length: 40}, (_, i) => (
        <div
          key={i}
          style={{
            position: 'absolute',
            left: `${(random(`hx${i}`) * 100 + frame * 0.06 * (1 + (i % 3))) % 100}%`,
            top: `${(((random(`hy${i}`) * 100 - frame * 0.04 * (i % 4)) % 100) + 100) % 100}%`, // drifts up, wraps
            width: 3 + (i % 4) * 2,
            height: 3 + (i % 4) * 2,
            borderRadius: '50%',
            background: '#fff',
            opacity: 0.12 + 0.25 * Math.abs(Math.sin(frame / 25 + i)),
            filter: i % 4 === 0 ? 'blur(3px)' : undefined,
          }}
        />
      ))}
      {/* anamorphic light streak */}
      <div
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          top: `${45 + 5 * Math.sin(frame / 70)}%`,
          height: 4,
          background: `linear-gradient(90deg, transparent, ${accent}88, transparent)`,
          filter: 'blur(3px)',
          opacity: 0.5 + 0.3 * Math.sin(frame / 18),
        }}
      />
    </>
  );
};

// A word slammed onto the screen: too big, then settles, with a shake and a glow.
const Slam: React.FC<{text: string; accent: string}> = ({text, accent}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const at = Math.round(0.35 * fps);
  const e = spring({frame: frame - at, fps, config: {damping: 10, mass: 0.6}});
  const shake = frame - at >= 0 && frame - at < 8 ? Math.sin(frame * 3) * (8 - (frame - at)) * 2 : 0;
  if (frame < at) return null;
  return (
    <>
    {/* the picture steps back (blurred and dark) behind the word, so the two never overlap */}
    <div style={{position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.62)', backdropFilter: `blur(${16 * Math.min(1, e)}px)`, opacity: Math.min(1, e)}} />
    <div
      style={{
        position: 'absolute',
        inset: 0,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontFamily: FONT,
        fontWeight: 900,
        fontSize: 170,
        letterSpacing: '0.04em',
        color: '#fff',
        textShadow: `0 0 40px ${accent}, 0 8px 0 rgba(0,0,0,0.6)`,
        transform: `translateX(${shake}px) scale(${1.7 - 0.7 * e})`,
        opacity: Math.min(1, e * 1.4),
        textTransform: 'uppercase',
      }}
    >
      {text}
    </div>
    </>
  );
};
