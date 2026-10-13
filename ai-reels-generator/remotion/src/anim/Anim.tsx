import React from 'react';
import {Easing, Img, OffthreadVideo, Sequence, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {Audio} from '../Audio';
import {Layer} from '../Layer';
import {Cues, Music} from '../Sound';
import {FONT, clamp, useFonts} from '../theme';
import {type Face, LABEL, SOFT_SHADOW, faceFor, splitTitle, useAnimFonts} from './type';
import {NextTag, PartTag} from './Tags';
import type {AnimCamera, AnimProps, AnimShot} from './types';
import {CineIn, FilmTexture, GradeWash, SubscribeCard, TypedLabel, gradeFilter, useCineFonts} from '../cine/Cine';
import {type CineTransition, OVERLAPS, TRANSITION_FRAMES} from '../cine/types';

// The cold open's own cuts (cine/), and how far the shot before keeps running under a photo or a tear.
const CINE = new Set<string>(['glitch', 'photo', 'split', 'punch']);
const under = (next?: AnimShot) => (next && OVERLAPS.has(next.transition as CineTransition) ? TRANSITION_FRAMES[next.transition as CineTransition] : 0);
const HOOK_CUT = 5; // frames: the cold open's music and drone stop dead into its silence (keep in step with reelgen/soundtrack.py)
const DRONE_VOLUME = 0.6;

// Animated videos (reelgen/animated.py). The pictures and clips are AI-made; this times them to the voice and
// adds what an image model can't: the emphasised words landing on their syllables, numbers and names on
// screen, title and chapter cards, transitions, camera moves on shots that weren't animated, and the sound.

const OVERLAP = 10; // frames a crossfade/dip/zoom shot starts before its cut, over the shot before it

// Letter-spacing breaks Devanagari's joined letters ("भाग" came out "भा ग"), so Hindi text is never tracked.
const DEVANAGARI = /[\u0900-\u097F]/;
const track = (text: string, spacing: string | number) => (DEVANAGARI.test(text) ? 0 : spacing);

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

const Picture: React.FC<{src: string; camera: AnimCamera; frame: number; frames: number}> = ({src, camera, frame, frames}) => {
  const [s0, s1, x0, x1, y0, y1, r] = MOVES[camera] ?? MOVES['push-in'];
  const p = interpolate(frame, [0, frames], [0, 1], {...clamp, easing: Easing.inOut(Easing.sin)});
  const shakeX = camera === 'handheld' ? Math.sin(frame / 9) * 6 + Math.sin(frame / 23) * 5 : 0;
  const shakeY = camera === 'handheld' ? Math.cos(frame / 11) * 5 : 0;
  const scale = s0 + (s1 - s0) * p;
  return (
    <Img src={staticFile(src)} style={{position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover',
      transform: `scale(${scale}) translate(${x0 + (x1 - x0) * p + shakeX}px, ${y0 + (y1 - y0) * p + shakeY}px) rotate(${(p - 0.5) * r}deg)`}} />
  );
};

// The shot's moving picture: the AI clip at its own speed (the video runs at the clip's 24 fps, so every frame
// shows once: slowing it, or 24 fps in a 30 fps video, repeated frames unevenly and the motion juddered), then its
// last frame held, under one gentle drift across the whole shot so the hand-over doesn't jump; or the AI picture
// under a camera move.
const Visual: React.FC<{shot: AnimShot; frame: number; frames: number}> = ({shot, frame, frames}) => {
  const {fps} = useVideoConfig();
  if (shot.clip && shot.clipSeconds) {
    const clipFrames = Math.floor(shot.clipSeconds * fps) - 1;
    const drift = interpolate(frame, [0, frames], [1, 1.06], {...clamp, easing: Easing.inOut(Easing.sin)});
    const fill = {position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover'} as const;
    return (
      <div style={{position: 'absolute', inset: 0, transform: `scale(${drift})`}}>
        {frame < clipFrames
          ? <OffthreadVideo src={staticFile(shot.clip)} muted style={fill} />
          : <Img src={staticFile(shot.last || shot.image)} style={fill} />}
      </div>
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

// Words revealed one by one: rising a little, from soft focus to sharp.
const Reveal: React.FC<{words: string[]; t: number; at: number; span: number; fps: number}> = ({words, t, at, span, fps}) => (
  <>
    {words.map((w, i) => {
      const s = spring({frame: Math.round((t - at - (span * i) / Math.max(1, words.length)) * fps), fps, config: {damping: 16, mass: 0.6}});
      return <span key={i} style={{display: 'inline-block', marginRight: '0.24em', opacity: Math.min(1, s * 1.6),
        transform: `translateY(${(1 - s) * 26}px)`, filter: `blur(${(1 - Math.min(1, s)) * 8}px)`}}>{w}</span>;
    })}
  </>
);

// The emphasised words, landing word by word as they are said (a number counts up), in one of three looks:
// the display face with an accent rule wiping in under it, an accent tag, or the display face in the accent colour.
const Emphasis: React.FC<{text: string; t: number; at: number; end: number; look: number; accent: string; fps: number; face: Face; vertical?: boolean}> = ({text, t, at, end, look, accent, fps, face, vertical}) => {
  const span = Math.max(0.35, end - at);
  const words = text.split(' ');
  const hasNum = /\d/.test(text);
  const out = interpolate(t, [end + 1.6, end + 2.0], [1, 0], clamp);
  const k = interpolate(t, [at, at + span], [0, 1], {...clamp, easing: Easing.out(Easing.cubic)});
  const rule = interpolate(t, [at + span * 0.4, at + span + 0.3], [0, 1], {...clamp, easing: Easing.out(Easing.cubic)});
  const long = text.length > 18;
  const display: React.CSSProperties = {fontFamily: face.family, fontWeight: face.weight, textTransform: face.upper ? 'uppercase' : 'none',
    letterSpacing: track(text, face.tracking), fontSize: (long ? 82 : 108) * face.size * (vertical ? 0.9 : 1), lineHeight: 1.05,
    whiteSpace: vertical ? 'normal' : 'nowrap', maxWidth: vertical ? 920 : undefined, textAlign: 'center', textShadow: SOFT_SHADOW};
  const body = hasNum ? countUp(text, k) : <Reveal words={words} t={t} at={at} span={span} fps={fps} />;
  return (
    <div style={{position: 'absolute', left: 0, right: 0, top: 0, height: vertical ? 900 : 460, paddingTop: vertical ? 430 : 96, display: 'flex', flexDirection: 'column', alignItems: 'center', opacity: out,
      background: 'linear-gradient(to bottom, rgba(0,0,0,0.42), rgba(0,0,0,0))'}}>
      {look === 1 ? (
        <div style={{fontFamily: LABEL, fontWeight: 700, fontSize: long ? 56 : 70, letterSpacing: track(text, '0.04em'), textTransform: 'uppercase', color: '#0b0b0f',
          background: accent, padding: '10px 30px 12px', borderRadius: 6, transform: `rotate(-1.5deg) scale(${0.92 + 0.08 * Math.min(1, k * 2)})`,
          boxShadow: '0 12px 34px rgba(0,0,0,0.4)', whiteSpace: vertical ? 'normal' : 'nowrap', maxWidth: vertical ? 900 : undefined, textAlign: 'center'}}>{body}</div>
      ) : (
        <>
          <div style={{...display, color: look === 2 ? accent : '#fff', fontStyle: look === 2 ? face.italic : 'normal'}}>{body}</div>
          {look === 0 ? <div style={{marginTop: 14, height: 4, width: 260 * rule, background: accent, borderRadius: 2, boxShadow: '0 2px 10px rgba(0,0,0,0.35)'}} /> : null}
        </>
      )}
    </div>
  );
};

const OnScreen: React.FC<{text: string; frame: number; fps: number; accent: string; vertical?: boolean}> = ({text, frame, fps, accent, vertical}) => {
  const s = spring({frame: frame - 10, fps, config: {damping: 16}});
  return (
    <div style={{position: 'absolute', left: vertical ? 56 : 90, bottom: vertical ? 600 : 130, opacity: Math.min(1, s * 1.5), transform: `translateX(${(1 - s) * -60}px)`,
      display: 'flex', alignItems: 'stretch', fontFamily: LABEL, boxShadow: '0 10px 30px rgba(0,0,0,0.35)'}}>
      <div style={{width: 6, background: accent}} />
      <div style={{background: 'rgba(12,12,16,0.74)', color: '#fff', fontWeight: 700, fontSize: 44, padding: '12px 28px 14px', textTransform: 'uppercase', letterSpacing: track(text, '0.08em')}}>{text}</div>
    </div>
  );
};

const Caption: React.FC<{shot: AnimShot; t: number; vertical?: boolean}> = ({shot, t, vertical}) => {
  const w = shot.words ?? [];
  if (!w.length) return null;
  const now = t - (shot.lead ?? 0);
  if (now > w[w.length - 1].end + 0.5) return null; // the line is over: nothing lingers into the pause
  let i = w.findIndex((x) => x.end >= now);
  if (i < 0) i = w.length - 1;
  const most = vertical ? 5 : 8;
  const per = Math.ceil(w.length / Math.ceil(w.length / most));
  const from = Math.floor(i / per) * per;
  return (
    <div style={{position: 'absolute', left: 0, right: 0, bottom: vertical ? 470 : 54, display: 'flex', justifyContent: 'center'}}>
      <div style={{fontFamily: LABEL, fontWeight: 700, fontSize: vertical ? 50 : 36, color: '#fff', background: 'rgba(0,0,0,0.55)', padding: '6px 18px', borderRadius: 10, maxWidth: vertical ? 940 : 1200, textAlign: 'center'}}>
        {w.slice(from, from + per).map((x) => x.text).join(' ')}
      </div>
    </div>
  );
};

// A small tracked label between two thin rules: "— CHAPTER 3 OF 5 —".
const Kicker: React.FC<{text: string; accent: string; k: number}> = ({text, accent, k}) => (
  <div style={{display: 'flex', alignItems: 'center', gap: 22, opacity: k, transform: `translateY(${(1 - k) * 12}px)`}}>
    <div style={{width: 70 * k, height: 2, background: accent, opacity: 0.9}} />
    <div style={{fontFamily: LABEL, fontWeight: 600, fontSize: 28, letterSpacing: '0.42em', marginRight: '-0.42em', textTransform: 'uppercase',
      color: '#fff', textShadow: '0 2px 12px rgba(0,0,0,0.6)'}}>{text}</div>
    <div style={{width: 70 * k, height: 2, background: accent, opacity: 0.9}} />
  </div>
);

// Title and chapter cards, set like a film's: the picture darkened from below, a kicker, the line revealed word
// by word in the style's display face, a thin rule.
const Card: React.FC<{shot: AnimShot; frame: number; frames: number; fps: number; accent: string; face: Face}> = ({shot, frame, frames, fps, accent, face}) => {
  const title = shot.type === 'title';
  const t = frame / fps;
  const [kick, main] = title ? splitTitle(shot.cardText ?? '') : ['', shot.cardText ?? ''];
  const kicker = title ? kick : shot.chapterNo ? `Chapter ${shot.chapterNo}${shot.chapters ? ` of ${shot.chapters}` : ''}` : '';
  const k = spring({frame: frame - 2, fps, config: {damping: 18}});
  const words = main.split(' ');
  const base = title ? (main.length > 40 ? 92 : 112) : (main.length > 32 ? 80 : 96);
  const rule = spring({frame: frame - 6 - words.length * 3, fps, config: {damping: 20}});
  return (
    <>
      <Picture src={shot.image} camera="push-in" frame={frame} frames={frames} />
      <div style={{position: 'absolute', inset: 0, background: 'linear-gradient(to top, rgba(0,0,0,0.82) 0%, rgba(0,0,0,0.5) 45%, rgba(0,0,0,0.38) 100%)'}} />
      <div style={{position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 30, padding: '0 160px'}}>
        {kicker ? <Kicker text={kicker} accent={accent} k={k} /> : null}
        <div style={{fontFamily: face.family, fontWeight: face.weight, fontSize: base * face.size, letterSpacing: face.tracking, lineHeight: face.upper ? 0.98 : 1.06,
          textTransform: face.upper ? 'uppercase' : 'none', color: '#fff', textAlign: 'center', maxWidth: 1560, textWrap: 'balance', textShadow: SOFT_SHADOW} as React.CSSProperties}>
          <Reveal words={words} t={t} at={0.1} span={Math.min(0.75, 0.08 * words.length)} fps={fps} />
        </div>
        <div style={{width: 220 * rule, height: 3, background: accent, borderRadius: 2, opacity: 0.95}} />
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
  const opening = shot.type === 'shot' && shot.chapter < 0 && Boolean(props.drop); // the cinematic cold open
  const picture = (
    <div style={{position: 'absolute', inset: 0, transform: `scale(${zoomIn * (1 + punch)}) translate(${whip * 900 + shake}px, ${shake * 0.4}px) skewX(${whip * -12}deg)`}}>
      <div style={{position: 'absolute', inset: 0, filter: opening ? gradeFilter(shot.grade) : undefined}}>
        {shot.type === 'shot' ? <Visual shot={shot} frame={Math.max(0, frame)} frames={frames} />
          : <Card shot={shot} frame={Math.max(0, frame)} frames={frames} fps={fps} accent={props.accent} face={faceFor(props.style)} />}
      </div>
      {opening ? <GradeWash grade={shot.grade} /> : null}
      {/* a soft vignette ties the AI frames together */}
      <div style={{position: 'absolute', inset: 0, background: 'radial-gradient(ellipse at center, transparent 55%, rgba(0,0,0,0.38) 100%)'}} />
    </div>
  );
  return (
    <Layer name={`${shot.type} ${index + 1}`} style={{opacity, backgroundColor: CINE.has(tr) && OVERLAPS.has(tr as CineTransition) ? 'transparent' : '#000'}}>
      {CINE.has(tr) ? <CineIn kind={tr as CineTransition} seed={index + 1}>{picture}</CineIn> : picture}
      {shot.onScreen && opening ? <TypedLabel text={shot.onScreen} vertical={props.vertical} /> : null}
      {shot.onScreen && !opening ? <OnScreen text={shot.onScreen} frame={frame} fps={fps} accent={props.accent} vertical={props.vertical} /> : null}
      {em && em.text && fx.has('text') && t >= em.at ? <Emphasis text={em.text} t={t} at={em.at} end={em.end} look={index % 3} accent={props.accent} fps={fps} face={faceFor(props.style)} vertical={props.vertical} /> : null}
      {tr === 'dip' && early ? <div style={{position: 'absolute', inset: 0, background: '#000', opacity: interpolate(raw, [0, early, early + 10], [0, 1, 0], clamp)}} /> : null}
      {tr === 'flash' ? <div style={{position: 'absolute', inset: 0, background: '#fff', opacity: interpolate(frame, [0, 9], [0.9, 0], clamp)}} /> : null}
      {fx.has('flash') && sinceEm !== null && sinceEm < 8 ? <div style={{position: 'absolute', inset: 0, background: '#fff', opacity: interpolate(sinceEm, [0, 7], [0.8, 0], clamp)}} /> : null}
      {props.captions && shot.type === 'shot' ? <Caption shot={shot} t={t} vertical={props.vertical} /> : null}
    </Layer>
  );
};

export const Anim: React.FC<AnimProps> = (props) => {
  useFonts();
  useAnimFonts();
  useCineFonts();
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
          <Sequence key={s.id} name={`${s.type} ${i + 1}`} from={from} durationInFrames={Math.max(1, end - from + (next && ['crossfade', 'dip', 'zoom'].includes(next.transition) ? OVERLAP : 0) + under(next))}>
            <ShotView shot={s} props={props} index={i} early={early} />
          </Sequence>
        );
      })}
      {/* the cinematic cold open: film texture over it, then silence (a subscribe button clicked in the dark) */}
      {!props.soundOnly && props.drop ? (
        <Sequence name="cold open texture" durationInFrames={Math.max(1, f(props.hookEnd))}>
          <FilmTexture />
        </Sequence>
      ) : null}
      {!props.soundOnly && props.drop ? (
        <Sequence name="silence" from={f(props.hookEnd)} durationInFrames={Math.max(1, f(props.drop))}>
          {props.subscribe ? <SubscribeCard frames={f(props.drop)} vertical={props.vertical} /> : <div style={{position: 'absolute', inset: 0, background: '#000'}} />}
        </Sequence>
      ) : null}
      {!props.soundOnly && props.partLabel ? (
        <Sequence name="part label" durationInFrames={f(2.7)}>
          <PartTag label={props.partLabel} title={props.title} accent={props.accent} face={faceFor(props.style)} />
        </Sequence>
      ) : null}
      {!props.soundOnly && props.nextLabel ? (
        <Sequence name="next part" from={Math.max(0, total - f(1.15))}>
          <NextTag label={props.nextLabel} accent={props.accent} face={faceFor(props.style)} />
        </Sequence>
      ) : null}
      {!props.soundOnly && props.watermark ? (
        <div style={{position: 'absolute', left: props.vertical ? 48 : 36, ...(props.vertical ? {top: 120} : {bottom: 28}), fontFamily: LABEL, fontWeight: 700, fontSize: 26, letterSpacing: '0.06em', color: '#fff', opacity: 0.75, textShadow: '0 2px 8px rgba(0,0,0,0.6)'}}>{props.watermark}</div>
      ) : null}
      {shots.map((s) => (s.audio ? (
        <Sequence key={`v-${s.id}`} name={`voice ${s.id}`} from={f(s.start + (s.lead ?? 0))}>
          <Audio src={staticFile(s.audio)} />
        </Sequence>
      ) : null))}
      {/* The cold open's track, then a track per chapter (each fades in and out over its own span). */}
      {props.hookMusic ? (
        <Sequence name="hook music" durationInFrames={props.drop ? Math.max(1, f(props.hookEnd)) : f(props.hookEnd + 4.2)}>
          <Music src={props.hookMusic} speech={props.speech.filter(([a]) => a < props.hookEnd)} full={0.55} duck={0.2} loop={false}
            fadeOut={props.drop ? HOOK_CUT : 45} />
        </Sequence>
      ) : null}
      {props.hookDrone && props.hookEnd > 0 ? (
        <Sequence name="hook drone" durationInFrames={Math.max(1, f(props.hookEnd))}>
          <Drone src={props.hookDrone} frames={Math.max(1, f(props.hookEnd))} />
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

const Drone: React.FC<{src: string; frames: number}> = ({src, frames}) => (
  <Audio src={staticFile(src)} volume={(fr) => interpolate(fr, [frames - HOOK_CUT, frames], [DRONE_VOLUME, 0], clamp)} />
);
