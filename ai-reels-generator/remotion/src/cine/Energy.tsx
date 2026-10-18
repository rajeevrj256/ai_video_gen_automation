import React from 'react';
import {Easing, Sequence, interpolate, random, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {FONT, clamp} from '../theme';
import {Layer} from '../Layer';
import {BOX} from '../long/box';
import type {Hook, HookShot, HookWord, Look} from '../long/types';
import {SubscribeCard} from './Cine';

// The energetic hook templates (reelgen/cinehook.py TEMPLATES). The user's cinematic hook came out as dark, slow
// film stills with a small typed word in a corner, "like a simple slide read out": these open at full energy on
// frame 0 (white flash, punch-in, a hit) and keep something moving every half second.
//   kinetic: every spoken word slams onto the screen as it is said, huge, over the dimmed picture;
//   rapid:   the picture full and bright, jump-cut zooms inside every shot, bold 2-3 word captions;
//   stakes:  the shot's key words or number slam in giant and shake the frame, the line small below.
// A thin bar across the top fills as the hook runs. The silence and the subscribe click at the end stay.

export type HookTemplate = 'cinematic' | 'kinetic' | 'rapid' | 'stakes';
type Render = (shot: HookShot, frames: number) => React.ReactNode;

const HOT = ['#FFD60A', '#FF4D4D', '#4DE8FF', '#7CFF6B'];
const SHADOW = '0 6px 0 rgba(0,0,0,0.55), 0 0 28px rgba(0,0,0,0.85), 0 0 4px #000';
const EM = 0.66; // Montserrat 900 capitals, average width per letter

const clean = (w: string) => w.toLowerCase().replace(/[^\p{L}\p{N}]/gu, '');
const longest = (words: string[]) => Math.max(1, ...words.map((w) => w.length));

// The words being spoken at `t` (seconds into the shot), in groups of up to `size` words.
const chunkAt = (words: HookWord[], t: number, size: number) => {
  const i = Math.max(0, words.findIndex((w, k) => t < (words[k + 1]?.start ?? Infinity)));
  const from = Math.floor(i / size) * size;
  return {words: words.slice(from, from + size), current: i - from};
};

// kinetic: the line builds up word by word as it is spoken, the newest word popping in in the accent colour.
const Kinetic: React.FC<{s: HookShot; accent: string}> = ({s, accent}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = frame / fps;
  const words = s.words ?? [];
  if (!words.length) return s.text ? <Slam text={s.text} color={accent} /> : null;
  const hot = new Set((s.text || '').split(/\s+/).map(clean).filter(Boolean));
  const said = words.filter((w) => w.start <= t + 0.04);
  const chars = words.reduce((n, w) => n + w.text.length + 1, 0);
  const width = BOX.INNER * 0.92;
  const size = Math.floor(Math.min(BOX.V ? 118 : 150, (width * 3) / (chars * EM), width / (longest(words.map((w) => w.text)) * EM)));
  return (
    <div style={{position: 'absolute', left: (BOX.W - width) / 2, width, top: BOX.V ? BOX.H * 0.3 : 0, height: BOX.V ? BOX.H * 0.4 : BOX.H,
      display: 'flex', flexWrap: 'wrap', alignContent: 'center', justifyContent: 'center', columnGap: size * 0.28, rowGap: size * 0.05}}>
      {said.map((w, k) => {
        const age = frame - Math.round(w.start * fps);
        const pop = spring({frame: age, fps, config: {damping: 11, mass: 0.45}});
        const newest = k === said.length - 1;
        const key = hot.has(clean(w.text));
        return (
          <span key={k} style={{fontFamily: FONT, fontWeight: 900, fontSize: size * (key ? 1.08 : 1), lineHeight: 1.05, textTransform: 'uppercase',
            color: key ? accent : newest ? '#FFFFFF' : 'rgba(255,255,255,0.88)', textShadow: SHADOW, display: 'inline-block',
            transform: `scale(${1.3 - 0.3 * pop}) rotate(${(1 - pop) * (k % 2 ? 5 : -5)}deg)`, transformOrigin: 'left center', opacity: Math.min(1, pop * 2)}}>
            {w.text}
          </span>
        );
      })}
    </div>
  );
};

// rapid: bold captions of 2-3 words, the word being said in the accent colour, in the lower part of the frame.
const Captions: React.FC<{s: HookShot; accent: string; small?: boolean}> = ({s, accent, small}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const words = s.words ?? [];
  if (!words.length) return null;
  const t = frame / fps;
  if (t < words[0].start - 0.05) return null;
  const {words: chunk, current} = chunkAt(words, t, small ? 4 : 3);
  const width = BOX.INNER * 0.9;
  const size = Math.floor(Math.min(small ? (BOX.V ? 62 : 70) : BOX.V ? 96 : 112,
    width / (chunk.reduce((n, w) => n + w.text.length + 1, 0) * EM), width / (longest(chunk.map((w) => w.text)) * EM)));
  const age = frame - Math.round(chunk[0].start * fps);
  const pop = spring({frame: age, fps, config: {damping: 12, mass: 0.4}});
  const top = BOX.V ? BOX.BOTTOM + 40 : BOX.H * 0.79; // low in the frame, on its own dark band (reads over any slide)
  return (
    <div style={{position: 'absolute', left: 0, width: BOX.W, top, display: 'flex', justifyContent: 'center', transform: `scale(${1.25 - 0.25 * pop})`}}>
    <div style={{maxWidth: width, display: 'flex', flexWrap: 'wrap', justifyContent: 'center', columnGap: size * 0.26,
      padding: `${size * 0.12}px ${size * 0.34}px`, borderRadius: size * 0.22, background: 'rgba(8,8,12,0.72)', boxShadow: '0 10px 40px rgba(0,0,0,0.5)'}}>
      {chunk.map((w, k) => (
        <span key={k} style={{fontFamily: FONT, fontWeight: 900, fontSize: size, lineHeight: 1.1, textTransform: 'uppercase',
          color: k === current ? accent : '#FFFFFF', WebkitTextStroke: `${Math.max(2, size / 26)}px #000`, paintOrder: 'stroke fill',
          textShadow: SHADOW, transform: k === current ? 'translateY(-4%)' : undefined, display: 'inline-block'}}>
          {w.text}
        </span>
      ))}
    </div>
    </div>
  );
};

// stakes (and any silent shot with key words): the words slam in giant, shake the frame and settle; a number
// counts up to its value.
const Slam: React.FC<{text: string; color: string}> = ({text, color}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const pop = spring({frame, fps, config: {damping: 9, mass: 0.6}});
  const m = text.match(/^(\D*?)(\d[\d,]*(?:\.\d+)?)(.*)$/);
  let shown = text;
  if (m) {
    const target = parseFloat(m[2].replace(/,/g, ''));
    const decimals = (m[2].split('.')[1] || '').length;
    const p = interpolate(frame, [0, Math.round(0.55 * fps)], [0, 1], {...clamp, easing: Easing.out(Easing.cubic)});
    const v = target * p;
    const grouped = m[2].includes(',') ? v.toLocaleString(text.includes('₹') ? 'en-IN' : 'en-US', {maximumFractionDigits: decimals, minimumFractionDigits: decimals})
      : v.toFixed(decimals);
    shown = `${m[1]}${grouped}${m[3]}`;
  }
  const words = text.split(/\s+/);
  const width = BOX.INNER * 0.94;
  const size = Math.floor(Math.min(BOX.V ? 190 : 230, (width * 2) / (text.length * EM), width / (longest(words) * EM)));
  return (
    <div style={{position: 'absolute', left: (BOX.W - width) / 2, width, top: 0, height: BOX.V ? BOX.H * 0.9 : BOX.H * 0.86,
      display: 'flex', alignItems: 'center', justifyContent: 'center', textAlign: 'center'}}>
      <div style={{fontFamily: FONT, fontWeight: 900, fontSize: size, lineHeight: 1, textTransform: 'uppercase', color,
        textShadow: `0 8px 0 rgba(0,0,0,0.6), 0 0 60px ${color}66, 0 0 6px #000`, transform: `scale(${2.1 - 1.1 * pop})`, opacity: Math.min(1, pop * 3)}}>
        {shown}
      </div>
    </div>
  );
};

const EnergyShot: React.FC<{s: HookShot; i: number; frames: number; template: HookTemplate; accent: string; render: Render; spoken: boolean}> = (p) => {
  const {s, i, frames, template, accent, render, spoken} = p;
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const meme = s.visual.type === 'meme';
  // Every shot comes in punched: from close to its frame in a few frames, a shake, a flash (white on the first).
  const inP = spring({frame, fps, config: {damping: 15, mass: 0.5}});
  let scale = 1 + 0.24 * (1 - inP) + (meme ? 0 : 0.07 * Math.min(1, frame / Math.max(1, frames)));
  let x = 0;
  let y = 0;
  if (template === 'rapid' && !meme) {
    // Jump cuts inside the shot: a new framing every ~0.7 s, so the picture never sits still.
    const step = Math.floor(frame / Math.max(1, Math.round(0.7 * fps)));
    scale += [0, 0.16, 0.08, 0.24][step % 4];
    x += step % 4 ? (random(`jx${i}-${step}`) - 0.5) * 120 : 0;
    y += step % 4 ? (random(`jy${i}-${step}`) - 0.5) * 60 : 0;
  }
  const shake = frame < 7 ? (7 - frame) * (i === 0 ? 5 : 3) : 0;
  x += Math.sin(frame * 2.9 + i) * shake;
  y += Math.cos(frame * 3.4 + i) * shake * 0.6;
  // A slide that carries its own words (a keyword, a title) would say the line twice next to the captions: it
  // sits back, dimmed and soft, like the kinetic template's picture.
  // With subtitles off (the default) no spoken word is drawn: only the shot's own key words slam in.
  const wordy = spoken && ['keyword', 'title', 'quote'].includes(s.visual.type);
  const filter = meme ? 'none' : spoken && (template === 'kinetic' || wordy) ? 'brightness(0.42) saturate(1.15) blur(4px)'
    : template === 'stakes' || (!spoken && template === 'kinetic') ? (s.text ? 'brightness(0.38) saturate(1.2) blur(5px)' : 'contrast(1.1) saturate(1.25)')
    : 'contrast(1.12) saturate(1.3) brightness(1.04)';
  const flash = interpolate(frame, [0, 5], [i === 0 ? 1 : 0.5, 0], clamp);
  const split = template === 'rapid' && frame < 4 && !meme ? (4 - frame) * 9 : 0; // an RGB split on the cut
  return (
    <>
      <div style={{position: 'absolute', inset: -40, transform: `translate(${x}px, ${y}px) scale(${scale})`, filter}}>
        <div style={{position: 'absolute', inset: 40}}>{render(s, frames)}</div>
      </div>
      {split ? (
        <>
          <div style={{position: 'absolute', inset: 0, background: 'rgba(255,0,60,0.18)', transform: `translateX(${split}px)`, mixBlendMode: 'screen'}} />
          <div style={{position: 'absolute', inset: 0, background: 'rgba(0,200,255,0.18)', transform: `translateX(${-split}px)`, mixBlendMode: 'screen'}} />
        </>
      ) : null}
      <div style={{position: 'absolute', inset: 0, background: 'radial-gradient(ellipse at center, transparent 55%, rgba(0,0,0,0.5) 100%)'}} />
      {meme ? null /* a meme carries its own words: a caption only said them twice */
        : !spoken ? (s.text ? <Slam text={s.text} color={accent} /> : null)
        : template === 'kinetic' ? <Kinetic s={s} accent={accent} />
        : template === 'stakes' ? (s.text ? <><Slam text={s.text} color={accent} /><Captions s={s} accent={accent} small /></> : <Kinetic s={s} accent={accent} />)
        : <>{s.text && !(s.words ?? []).length ? <Slam text={s.text} color={accent} /> : null}<Captions s={s} accent={accent} /></>}
      {flash > 0 ? <div style={{position: 'absolute', inset: 0, background: '#FFFFFF', opacity: flash}} /> : null}
    </>
  );
};

export const EnergyHook: React.FC<{hook: Hook; look: Look; render: Render}> = ({hook, look, render}) => {
  const {fps} = useVideoConfig();
  const frame = useCurrentFrame();
  const f = (sec: number) => Math.round(sec * fps);
  const drop = hook.drop ?? 0;
  const live = f(hook.duration - drop);
  const template = (hook.template ?? 'kinetic') as HookTemplate;
  const seed = look.seed ?? 1;
  const bar = interpolate(frame, [0, live], [0, 1], clamp);
  return (
    <Layer name={`hook (${template})`} style={{background: '#000'}}>
      {hook.shots.map((s, i) => {
        const frames = Math.max(1, f(s.duration));
        // A different hot colour per shot, never the same twice in a row.
        const accent = i === 0 ? look.accents[0] ?? HOT[0] : HOT[(i + seed) % HOT.length];
        return (
          <Sequence key={i} name={`hook ${i + 1} (${template})`} from={f(s.start)} durationInFrames={frames}>
            <EnergyShot s={s} i={i} frames={frames} template={template} accent={accent} render={render} spoken={hook.subtitles === true} />
          </Sequence>
        );
      })}
      {frame < live ? <div style={{position: 'absolute', left: 0, top: 0, height: BOX.V ? 10 : 8, width: `${bar * 100}%`,
        background: look.accents[0] ?? HOT[0], boxShadow: `0 0 18px ${look.accents[0] ?? HOT[0]}`}} /> : null}
      {drop > 0 ? (
        <Sequence name="silence" from={live}>
          {hook.subscribe ? <SubscribeCard frames={f(drop)} vertical={BOX.V} /> : <div style={{position: 'absolute', inset: 0, background: '#000'}} />}
        </Sequence>
      ) : null}
    </Layer>
  );
};
