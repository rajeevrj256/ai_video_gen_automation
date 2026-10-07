import React from 'react';
import {Easing, Img, OffthreadVideo, Sequence, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {Audio} from '../Audio';
import {Layer} from '../Layer';
import {Cues, Music} from '../Sound';
import {FONT, clamp, useFonts} from '../theme';
import type {AnimCamera, AnimProps, AnimShot} from './types';

// Animated videos (reelgen/animated.py). The pictures and clips are AI-made; this times them to the voice and
// adds what an image model can't: the emphasised words landing on their syllables, numbers and names on
// screen, title and chapter cards, transitions, camera moves on shots that weren't animated, and the sound.

const OVERLAP = 10; // frames a crossfade/dip/zoom shot starts before its cut, over the shot before it

// The camera on a picture: [scale from, scale to, x from, x to, y from, y to, rotate].
const MOVES: Record<AnimCamera, [number, number, number, number, number, number, number]> = {
  'push-in': [1.02, 1.16, 0, 0, 0, 0, 0],
  'pull-out': [1.16, 1.02, 0, 0, 0, 0, 0],
  'pan-left': [1.14, 1.14, 70, -70, 0, 0, 0],
  'pan-right': [1.14, 1.14, -70, 70, 0, 0, 0],
  'tilt-up': [1.14, 1.14, 0, 0, 50, -50, 0],
  'tilt-down': [1.14, 1.14, 0, 0, -50, 50, 0],
  orbit: [1.08, 1.16, -30, 30, 0, 0, 1.2],
  handheld: [1.08, 1.1, 0, 0, 0, 0, 0],
  static: [1.02, 1.05, 0, 0, 0, 0, 0],
};

const Picture: React.FC<{src: string; camera: AnimCamera; frame: number; frames: number; gentle?: boolean}> = ({src, camera, frame, frames, gentle}) => {
  const [s0, s1, x0, x1, y0, y1, r] = MOVES[camera] ?? MOVES['push-in'];
  const p = interpolate(frame, [0, frames], [0, 1], {...clamp, easing: Easing.inOut(Easing.sin)});
  const k = gentle ? 0.35 : 1; // over an AI clip (which moves already) the camera only drifts
  const shakeX = camera === 'handheld' ? Math.sin(frame / 9) * 6 + Math.sin(frame / 23) * 5 : 0;
  const shakeY = camera === 'handheld' ? Math.cos(frame / 11) * 5 : 0;
  const scale = 1 + (s0 - 1 + (s1 - s0) * p) * k;
  return (
    <Img src={staticFile(src)} style={{position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover',
      transform: `scale(${scale}) translate(${(x0 + (x1 - x0) * p) * k + shakeX}px, ${(y0 + (y1 - y0) * p) * k + shakeY}px) rotate(${(p - 0.5) * r * k}deg)`}} />
  );
};

// The shot's moving picture: the AI clip (slowed a little when the line is longer, then its last frame held
// with the camera still drifting) or the AI picture under a camera move.
const Visual: React.FC<{shot: AnimShot; frame: number; frames: number}> = ({shot, frame, frames}) => {
  const {fps} = useVideoConfig();
  if (shot.clip && shot.clipSeconds) {
    const rate = Math.max(0.75, Math.min(1, shot.clipSeconds / (frames / fps)));
    const clipFrames = Math.floor((shot.clipSeconds / rate) * fps) - 1;
    const drift = interpolate(frame, [0, frames], [1, 1.05], clamp);
    return (
      <>
        <div style={{position: 'absolute', inset: 0, transform: `scale(${drift})`}}>
          {frame < clipFrames ? (
            <OffthreadVideo src={staticFile(shot.clip)} muted playbackRate={rate}
              style={{position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover'}} />
          ) : (
            <Picture src={shot.last || shot.image} camera={shot.camera ?? 'push-in'} frame={frame - clipFrames} frames={Math.max(1, frames - clipFrames)} gentle />
          )}
        </div>
      </>
    );
  }
  return <Picture src={shot.image} camera={shot.camera ?? 'push-in'} frame={frame} frames={frames} />;
};

const countUp = (text: string, k: number) => text.replace(/\d[\d,]*(\.\d+)?/, (m) => {
  const n = parseFloat(m.replace(/,/g, ''));
  const dec = (m.split('.')[1] ?? '').length;
  const v = n * k;
  return m.includes(',') ? v.toLocaleString('en-US', {minimumFractionDigits: dec, maximumFractionDigits: dec}) : v.toFixed(dec);
});

// The emphasised words, landing word by word as they are said (a number counts up), in one of three looks.
const Emphasis: React.FC<{text: string; t: number; at: number; end: number; look: number; accent: string; fps: number}> = ({text, t, at, end, look, accent, fps}) => {
  const span = Math.max(0.35, end - at);
  const words = text.split(' ');
  const hasNum = /\d/.test(text);
  const out = interpolate(t, [end + 1.6, end + 2.0], [1, 0], clamp);
  const base: React.CSSProperties = {fontFamily: FONT, fontWeight: 900, fontSize: text.length > 18 ? 92 : 124, textTransform: 'uppercase', lineHeight: 1, whiteSpace: 'nowrap'};
  const box: React.CSSProperties = look === 0
    ? {...base, color: '#fff', WebkitTextStroke: '12px #111', paintOrder: 'stroke', textShadow: `0 10px 0 ${accent}`}
    : look === 1
      ? {...base, color: '#111', background: accent, padding: '12px 36px', borderRadius: 16, boxShadow: '0 14px 30px rgba(0,0,0,0.45)'}
      : {...base, color: accent, WebkitTextStroke: '10px #111', paintOrder: 'stroke', textShadow: '0 8px 24px rgba(0,0,0,0.6)'};
  const k = interpolate(t, [at, at + span], [0, 1], {...clamp, easing: Easing.out(Easing.cubic)});
  const pop = spring({frame: Math.round((t - at) * fps), fps, config: {damping: 10, mass: 0.5}});
  return (
    <div style={{position: 'absolute', left: 0, right: 0, top: 110, display: 'flex', justifyContent: 'center', opacity: out}}>
      <div style={{...box, transform: `scale(${hasNum ? pop : 1})`}}>
        {hasNum ? countUp(text, k) : words.map((w, i) => {
          const s = spring({frame: Math.round((t - at - (span * i) / words.length) * fps), fps, config: {damping: 11, mass: 0.5}});
          return <span key={i} style={{display: 'inline-block', marginRight: '0.28em', opacity: Math.min(1, s * 2),
            transform: `translateY(${(1 - s) * 50}px) scale(${look === 0 ? 0.7 + 0.3 * s : 1})`}}>{w}</span>;
        })}
      </div>
    </div>
  );
};

const OnScreen: React.FC<{text: string; frame: number; fps: number; accent: string}> = ({text, frame, fps, accent}) => {
  const s = spring({frame: frame - 10, fps, config: {damping: 14}});
  return (
    <div style={{position: 'absolute', left: 90, bottom: 140, transform: `translateX(${(1 - s) * -600}px)`, display: 'flex', alignItems: 'stretch', fontFamily: FONT}}>
      <div style={{width: 14, background: accent}} />
      <div style={{background: 'rgba(10,10,14,0.82)', color: '#fff', fontWeight: 900, fontSize: 64, padding: '10px 30px', textTransform: 'uppercase', letterSpacing: 1}}>{text}</div>
    </div>
  );
};

const Caption: React.FC<{shot: AnimShot; t: number}> = ({shot, t}) => {
  const w = shot.words ?? [];
  if (!w.length) return null;
  const now = t - (shot.lead ?? 0);
  let i = w.findIndex((x) => x.end >= now);
  if (i < 0) i = w.length - 1;
  const per = Math.ceil(w.length / Math.ceil(w.length / 8));
  const from = Math.floor(i / per) * per;
  return (
    <div style={{position: 'absolute', left: 0, right: 0, bottom: 54, display: 'flex', justifyContent: 'center'}}>
      <div style={{fontFamily: FONT, fontWeight: 800, fontSize: 36, color: '#fff', background: 'rgba(0,0,0,0.55)', padding: '6px 18px', borderRadius: 10, maxWidth: 1200, textAlign: 'center'}}>
        {w.slice(from, from + per).map((x) => x.text).join(' ')}
      </div>
    </div>
  );
};

const Card: React.FC<{shot: AnimShot; frame: number; frames: number; fps: number; accent: string}> = ({shot, frame, frames, fps, accent}) => {
  const title = shot.type === 'title';
  const s = spring({frame: frame - 4, fps, config: {damping: 13}});
  const text = shot.cardText ?? '';
  const typed = title ? text : text.slice(0, Math.round(interpolate(frame, [8, 8 + text.length * 1.4], [0, text.length], clamp)));
  return (
    <>
      <Picture src={shot.image} camera="push-in" frame={frame} frames={frames} />
      <div style={{position: 'absolute', inset: 0, background: title ? 'radial-gradient(circle at 50% 55%, rgba(0,0,0,0.15), rgba(0,0,0,0.7))' : 'rgba(0,0,0,0.62)'}} />
      <div style={{position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 26, fontFamily: FONT}}>
        {!title && shot.chapterNo ? (
          <div style={{color: accent, fontWeight: 900, fontSize: 34, letterSpacing: 10, opacity: s}}>CHAPTER {shot.chapterNo}{shot.chapters ? ` / ${shot.chapters}` : ''}</div>
        ) : null}
        <div style={{color: '#fff', fontWeight: 900, fontSize: title ? (text.length > 42 ? 86 : 104) : 84, textAlign: 'center', maxWidth: 1500, lineHeight: 1.08,
          textTransform: 'uppercase', transform: `scale(${title ? 0.85 + 0.15 * s : 1})`, opacity: title ? s : 1,
          WebkitTextStroke: title ? '10px #111' : undefined, paintOrder: 'stroke', textShadow: `0 10px 0 ${title ? accent : 'transparent'}`}}>{typed}</div>
        <div style={{width: interpolate(s, [0, 1], [0, 420]), height: 8, background: accent, borderRadius: 4}} />
      </div>
    </>
  );
};

const ShotView: React.FC<{shot: AnimShot; props: AnimProps; index: number; early: number}> = ({shot, props, index, early}) => {
  const raw = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();
  const frame = raw - early; // 0 at the cut; negative while a crossfade/dip/zoom comes in over the last shot
  const frames = Math.max(1, durationInFrames - early);
  const t = frame / fps;
  const em = shot.emphasis ?? null;
  const fx = new Set(shot.emphasisFx ?? []);
  const sinceEm = em && t >= em.at ? Math.round((t - em.at) * fps) : null;
  const punch = fx.has('zoom') && sinceEm !== null ? interpolate(sinceEm, [0, 5], [0, 0.1], {...clamp, easing: Easing.out(Easing.back(2))}) : 0;
  const shake = fx.has('shake') && sinceEm !== null && sinceEm < 15 ? Math.sin(raw * 3.1) * 14 * (1 - sinceEm / 15) : 0;
  // Coming in.
  const tr = shot.transition;
  const into = interpolate(raw, [0, Math.max(1, early)], [0, 1], clamp);
  const opacity = early && (tr === 'crossfade' || tr === 'zoom') ? into : 1;
  const zoomIn = tr === 'zoom' ? interpolate(raw, [0, early + 8], [1.25, 1], {...clamp, easing: Easing.out(Easing.cubic)}) : 1;
  const whip = tr === 'whip' ? interpolate(frame, [0, 7], [1, 0], {...clamp, easing: Easing.out(Easing.cubic)}) : 0;
  return (
    <Layer name={`${shot.type} ${index + 1}`} style={{opacity, backgroundColor: '#000'}}>
      <div style={{position: 'absolute', inset: 0, transform: `scale(${zoomIn * (1 + punch)}) translate(${whip * 900 + shake}px, ${shake * 0.4}px) skewX(${whip * -12}deg)`}}>
        {shot.type === 'shot' ? <Visual shot={shot} frame={Math.max(0, frame)} frames={frames} />
          : <Card shot={shot} frame={Math.max(0, frame)} frames={frames} fps={fps} accent={props.accent} />}
        {/* a soft vignette ties the AI frames together */}
        <div style={{position: 'absolute', inset: 0, background: 'radial-gradient(ellipse at center, transparent 55%, rgba(0,0,0,0.38) 100%)'}} />
      </div>
      {shot.onScreen ? <OnScreen text={shot.onScreen} frame={frame} fps={fps} accent={props.accent} /> : null}
      {em && fx.has('text') && t >= em.at ? <Emphasis text={em.text} t={t} at={em.at} end={em.end} look={index % 3} accent={props.accent} fps={fps} /> : null}
      {tr === 'dip' && early ? <div style={{position: 'absolute', inset: 0, background: '#000', opacity: interpolate(raw, [0, early, early + 10], [0, 1, 0], clamp)}} /> : null}
      {tr === 'flash' ? <div style={{position: 'absolute', inset: 0, background: '#fff', opacity: interpolate(frame, [0, 9], [0.9, 0], clamp)}} /> : null}
      {fx.has('flash') && sinceEm !== null && sinceEm < 8 ? <div style={{position: 'absolute', inset: 0, background: '#fff', opacity: interpolate(sinceEm, [0, 7], [0.8, 0], clamp)}} /> : null}
      {props.captions && shot.type === 'shot' ? <Caption shot={shot} t={t} /> : null}
    </Layer>
  );
};

export const Anim: React.FC<AnimProps> = (props) => {
  useFonts();
  const {fps} = useVideoConfig();
  const f = (s: number) => Math.round(s * fps);
  const {shots} = props;
  const total = f(props.duration);
  return (
    <Layer name="anim" style={{backgroundColor: '#000', fontFamily: FONT, overflow: 'hidden'}}>
      {props.soundOnly ? null : shots.map((s, i) => {
        const next = shots[i + 1];
        const end = next ? f(next.start) : total;
        const early = i > 0 && ['crossfade', 'dip', 'zoom'].includes(s.transition) ? OVERLAP : 0;
        const from = f(s.start) - early;
        return (
          <Sequence key={s.id} name={`${s.type} ${i + 1}`} from={from} durationInFrames={Math.max(1, end - from + (next && ['crossfade', 'dip', 'zoom'].includes(next.transition) ? OVERLAP : 0))}>
            <ShotView shot={s} props={props} index={i} early={early} />
          </Sequence>
        );
      })}
      {!props.soundOnly && props.watermark ? (
        <div style={{position: 'absolute', left: 36, bottom: 28, fontFamily: FONT, fontWeight: 900, fontSize: 28, color: '#fff', opacity: 0.8, textShadow: '0 3px 6px rgba(0,0,0,0.6)'}}>{props.watermark}</div>
      ) : null}
      {shots.map((s) => (s.audio ? (
        <Sequence key={`v-${s.id}`} name={`voice ${s.id}`} from={f(s.start + (s.lead ?? 0))}>
          <Audio src={staticFile(s.audio)} />
        </Sequence>
      ) : null))}
      {/* The cold open's track, then a track per chapter (each fades in and out over its own span). */}
      {props.hookMusic ? (
        <Sequence name="hook music" durationInFrames={f(props.hookEnd + 4.2)}>
          <Music src={props.hookMusic} speech={props.speech.filter(([a]) => a < props.hookEnd)} full={0.55} duck={0.2} loop={false} />
        </Sequence>
      ) : null}
      {props.musicParts.map((m, i) => (
        <Sequence key={`m${i}`} name={`music ${i + 1}`} from={f(m.from)} durationInFrames={Math.max(1, f(m.to - m.from))}>
          <Music src={m.src} speech={props.speech.map(([a, b]) => [a - m.from, b - m.from] as [number, number])} full={0.26} duck={0.13} />
        </Sequence>
      ))}
      <Cues cues={props.cues} speech={props.speech} />
    </Layer>
  );
};
