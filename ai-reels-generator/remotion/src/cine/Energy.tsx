import React from 'react';
import {Easing, Sequence, interpolate, random, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {FONT, clamp} from '../theme';
import {Layer} from '../Layer';
import {BOX} from '../long/box';
import type {Hook, HookShot, HookWord, Look} from '../long/types';
import {SubscribeCard} from './Cine';
import {Bulletin, FrontPage, bulletinScreens, useScreenFonts} from './Screens';
import type {Screen} from './Screens';

// The energetic hook templates (reelgen/cinehook.py TEMPLATES). The user's cinematic hook came out as dark, slow
// film stills with a small typed word in a corner, "like a simple slide read out": these open at full energy on
// frame 0 (white flash, punch-in, a hit) and keep something moving every half second.
//   kinetic: every spoken word slams onto the screen as it is said, huge, over the dimmed picture;
//   rapid:   the picture full and bright, jump-cut zooms inside every shot, bold 2-3 word captions;
//   stakes:  the shot's key words or number slam in giant and shake the frame, the line small below;
//   myth:    key words slam in; the belief's shot gets a red MYTH stamp right after its line;
//   mirror:  each line pops in as a phone notification over the bright picture;
//   rewind:  how it ends first, then a VHS rewind into the past with a camcorder time stamp;
//   promise: key words slam in, then the video's points tick onto a checklist;
//   teaser:  a COMING UP tag over jump-cut pictures, each moment's tag below it;
//   bulletin, frontpage: the template draws the whole screen (Screens.tsx); a meme shot keeps its picture.
// The spoken words themselves are drawn only with subtitles on (hook.subtitles).
// No progress bar across the top: on a phone the user saw it as a stray slider. The silence and the subscribe
// click at the end stay.

export type HookTemplate = 'cinematic' | 'kinetic' | 'rapid' | 'stakes' | 'myth' | 'mirror' | 'rewind' | 'promise' | 'teaser' | 'bulletin' | 'frontpage';
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

// Seconds into a shot when its stamp lands: just after its line. Keep in step with reelgen/cinehook.py stamp_at.
const stampAt = (s: HookShot) => {
  const words = s.words ?? [];
  const at = words.length ? words[words.length - 1].end + 0.12 : s.duration * 0.55;
  return Math.min(at, Math.max(0.2, s.duration - 0.35));
};

// A red rubber stamp (MYTH, WRONG, TRUE...) slammed across the frame, tilted, with a worn double border.
const Stamp: React.FC<{s: HookShot}> = ({s}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const at = Math.round(stampAt(s) * fps);
  if (frame < at || !s.stamp) return null;
  const pop = spring({frame: frame - at, fps, config: {damping: 10, mass: 0.5}});
  const good = /^(TRUE|CONFIRMED|REAL)$/.test(s.stamp);
  const color = good ? '#2BD96B' : '#FF2D2D';
  const size = Math.floor(Math.min(BOX.V ? 210 : 280, (BOX.INNER * 0.82) / (s.stamp.length * 0.78)));
  return (
    <div style={{position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
      <div style={{fontFamily: FONT, fontWeight: 900, fontSize: size, lineHeight: 1, letterSpacing: size * 0.06, color,
        padding: `${size * 0.14}px ${size * 0.3}px`, border: `${size * 0.09}px solid ${color}`, outline: `${size * 0.03}px solid ${color}`,
        outlineOffset: size * 0.06, borderRadius: size * 0.12, background: 'rgba(0,0,0,0.18)', textShadow: '0 4px 18px rgba(0,0,0,0.6)',
        boxShadow: `0 0 50px ${color}55`, transform: `rotate(-12deg) scale(${2.4 - 1.4 * pop})`, opacity: Math.min(1, pop * 2.5)}}>
        {s.stamp}
      </div>
    </div>
  );
};

// mirror: the line as a phone notification sliding down from the top (an app badge, the words, 'now').
const Notify: React.FC<{text: string; accent: string}> = ({text, accent}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const pop = spring({frame: frame - 3, fps, config: {damping: 14, mass: 0.6}});
  const width = Math.min(BOX.V ? BOX.W * 0.88 : 1120, BOX.INNER);
  const size = Math.floor(Math.min(BOX.V ? 66 : 76, (width - 220) * 2 / (text.length * 0.6)));
  return (
    <div style={{position: 'absolute', left: (BOX.W - width) / 2, width, top: BOX.V ? BOX.TOP + 60 : 70,
      transform: `translateY(${(1 - pop) * -260}px) scale(${0.92 + 0.08 * pop})`, opacity: Math.min(1, pop * 2)}}>
      <div style={{display: 'flex', alignItems: 'center', gap: 26, padding: '26px 32px', borderRadius: 34,
        background: 'rgba(245,245,250,0.94)', boxShadow: '0 24px 60px rgba(0,0,0,0.55)'}}>
        <div style={{width: 112, height: 112, flex: '0 0 112px', borderRadius: 26, background: accent, display: 'flex',
          alignItems: 'center', justifyContent: 'center', fontSize: 52, fontFamily: FONT, fontWeight: 900, color: '#111'}}>!</div>
        <div style={{flex: 1, minWidth: 0}}>
          <div style={{fontFamily: FONT, fontWeight: 700, fontSize: 30, color: '#6B6B76', letterSpacing: 1, display: 'flex', justifyContent: 'space-between'}}>
            <span>MESSAGE</span><span>now</span>
          </div>
          <div style={{fontFamily: FONT, fontWeight: 800, fontSize: size, lineHeight: 1.15, color: '#111118', marginTop: 4}}>{text}</div>
        </div>
      </div>
    </div>
  );
};

// rewind: the first ~0.9 s of the rewind shot is the tape running back (tracking bands, noise, ◀◀), then a
// camcorder corner with PLAY and the time stamp (the shot's text) for the rest of the shot.
const Rewind: React.FC<{s: HookShot; seed: number}> = ({s, seed}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const run = Math.round(0.9 * fps);
  const mono = '"Courier Prime", "Courier New", monospace';
  const blink = Math.floor(frame / Math.round(fps * 0.4)) % 2 === 0;
  if (frame < run) {
    const band = (frame * 97) % BOX.H;
    return (
      <div style={{position: 'absolute', inset: 0, background: 'rgba(10,10,30,0.35)'}}>
        {Array.from({length: 7}, (_, k) => (
          <div key={k} style={{position: 'absolute', left: 0, width: BOX.W, top: (band + k * BOX.H / 7 + random(`rw${seed}-${frame}-${k}`) * 40) % BOX.H,
            height: 10 + random(`rh${seed}-${k}`) * 26, background: 'rgba(255,255,255,0.28)', transform: `translateX(${(random(`rx${frame}-${k}`) - 0.5) * 80}px)`}} />
        ))}
        <div style={{position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center'}}>
          <div style={{fontFamily: FONT, fontWeight: 900, fontSize: BOX.V ? 180 : 210, color: '#FFFFFF', textShadow: '6px 0 #FF2D55, -6px 0 #2DE2FF'}}>◀◀</div>
          <div style={{fontFamily: mono, fontWeight: 700, fontSize: BOX.V ? 84 : 104, color: '#FFFFFF', letterSpacing: 10, textShadow: '3px 0 #FF2D55, -3px 0 #2DE2FF'}}>REWIND</div>
        </div>
      </div>
    );
  }
  const size = BOX.V ? 62 : 74;
  return (
    <div style={{position: 'absolute', left: BOX.V ? 60 : 90, top: BOX.V ? BOX.TOP + 40 : 70, fontFamily: mono, fontWeight: 700,
      color: '#FFFFFF', textShadow: '2px 0 #FF2D55, -2px 0 #2DE2FF, 0 0 12px rgba(0,0,0,0.9)'}}>
      <div style={{fontSize: size * 0.8, letterSpacing: 4}}>{blink ? '●' : '\u00a0'} PLAY ▶</div>
      {s.text ? <div style={{fontSize: size * 1.25, letterSpacing: 3, marginTop: 10, textTransform: 'uppercase'}}>{s.text}</div> : null}
    </div>
  );
};

// promise: the points so far as a checklist; the newest one ticks in.
const Checklist: React.FC<{items: string[]; accent: string}> = ({items, accent}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const size = BOX.V ? 70 : 86;
  const width = BOX.V ? BOX.W * 0.86 : 1150;
  return (
    <div style={{position: 'absolute', left: BOX.V ? (BOX.W - width) / 2 : 110, top: BOX.V ? BOX.H * 0.3 : BOX.H * 0.24, width,
      display: 'flex', flexDirection: 'column', gap: size * 0.4}}>
      {items.map((it, k) => {
        const latest = k === items.length - 1;
        const pop = latest ? spring({frame: frame - 2, fps, config: {damping: 12, mass: 0.5}}) : 1;
        const tick = latest ? spring({frame: frame - 9, fps, config: {damping: 10, mass: 0.4}}) : 1;
        return (
          <div key={k} style={{display: 'flex', alignItems: 'center', gap: size * 0.4, padding: `${size * 0.22}px ${size * 0.34}px`,
            borderRadius: size * 0.24, background: latest ? 'rgba(10,10,16,0.82)' : 'rgba(10,10,16,0.6)',
            boxShadow: latest ? `0 0 0 4px ${accent}, 0 18px 50px rgba(0,0,0,0.5)` : 'none',
            transform: `translateX(${(1 - pop) * -120}px)`, opacity: Math.min(1, pop * 2) * (latest ? 1 : 0.8)}}>
            <div style={{width: size, height: size, flex: `0 0 ${size}px`, borderRadius: size * 0.2, border: `5px solid ${accent}`,
              display: 'flex', alignItems: 'center', justifyContent: 'center', background: tick > 0.5 ? accent : 'transparent'}}>
              <span style={{fontFamily: FONT, fontWeight: 900, fontSize: size * 0.72, color: '#111', transform: `scale(${tick})`}}>✓</span>
            </div>
            <span style={{fontFamily: FONT, fontWeight: 900, fontSize: size, lineHeight: 1.05, color: '#FFFFFF', textTransform: 'uppercase', textShadow: SHADOW}}>{it}</span>
          </div>
        );
      })}
    </div>
  );
};

// teaser: a COMING UP tag with a blinking red dot, the moment's own tag under it.
const ComingUp: React.FC<{text: string}> = ({text}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const blink = Math.floor(frame / Math.round(fps * 0.35)) % 2 === 0;
  const pop = spring({frame, fps, config: {damping: 13, mass: 0.5}});
  return (
    <div style={{position: 'absolute', left: BOX.V ? 60 : 80, top: BOX.V ? BOX.TOP + 40 : 64, display: 'flex', flexDirection: 'column', gap: 14,
      alignItems: 'flex-start', transform: `translateX(${(1 - pop) * -80}px)`}}>
      <div style={{display: 'flex', alignItems: 'center', gap: 14, padding: '10px 22px', borderRadius: 10, background: '#E50914',
        fontFamily: FONT, fontWeight: 900, fontSize: BOX.V ? 50 : 58, letterSpacing: 5, color: '#FFFFFF'}}>
        <span style={{width: 22, height: 22, borderRadius: 11, background: '#FFFFFF', opacity: blink ? 1 : 0.25}} />COMING UP
      </div>
      {text ? <div style={{padding: '8px 22px', borderRadius: 10, background: 'rgba(0,0,0,0.72)', fontFamily: FONT, fontWeight: 900,
        fontSize: BOX.V ? 76 : 92, color: '#FFFFFF', textTransform: 'uppercase', opacity: Math.min(1, pop * 2)}}>{text}</div> : null}
    </div>
  );
};

const EnergyShot: React.FC<{s: HookShot; i: number; frames: number; template: HookTemplate; accent: string; render: Render; spoken: boolean;
  items: string[]; last: boolean; seed: number; n: number; source?: string; log?: string[]; screen?: Screen}> = (p) => {
  const {s, i, frames, template, accent, render, spoken, items, last, seed} = p;
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const meme = s.visual.type === 'meme';
  if (!meme && template === 'bulletin') return <Bulletin s={s} i={i} n={p.n} frames={frames} log={p.log} screen={p.screen} />;
  if (!meme && template === 'frontpage') return <FrontPage s={s} i={i} frames={frames} />;
  // Every shot comes in punched: from close to its frame in a few frames, a shake, a flash (white on the first).
  const inP = spring({frame, fps, config: {damping: 15, mass: 0.5}});
  let scale = 1 + 0.24 * (1 - inP) + (meme ? 0 : 0.07 * Math.min(1, frame / Math.max(1, frames)));
  let x = 0;
  let y = 0;
  if ((template === 'rapid' || template === 'teaser') && !meme) {
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
  const slams = template === 'stakes' || template === 'myth' || (template === 'promise' && !items.length) || (!spoken && template === 'kinetic');
  const stamped = s.stamp && frame >= Math.round(stampAt(s) * fps);
  const filter = meme ? 'none' : stamped ? 'grayscale(0.85) brightness(0.55) contrast(1.15)'
    : spoken && (template === 'kinetic' || wordy) ? 'brightness(0.42) saturate(1.15) blur(4px)'
    : template === 'promise' && items.length ? 'brightness(0.5) saturate(1.1) blur(3px)'
    : slams ? (s.text ? 'brightness(0.38) saturate(1.2) blur(5px)' : 'contrast(1.1) saturate(1.25)')
    : s.rewind && frame < Math.round(0.9 * fps) ? 'contrast(1.3) saturate(0.6) blur(2px) hue-rotate(-20deg)'
    : 'contrast(1.12) saturate(1.3) brightness(1.04)';
  const flash = interpolate(frame, [0, 5], [i === 0 ? 1 : 0.5, 0], clamp);
  const split = (template === 'rapid' || template === 'teaser') && frame < 4 && !meme ? (4 - frame) * 9 : 0; // an RGB split on the cut
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
      <div style={{position: 'absolute', inset: 0, opacity: stamped ? 0.3 : 1}}>{/* the words step back under a stamp */}
      {meme ? null /* a meme carries its own words: a caption only said them twice */
        : s.rewind ? <Rewind s={s} seed={seed} />
        : template === 'mirror' ? <>{s.text ? <Notify text={s.text} accent={accent} /> : null}{spoken ? <Captions s={s} accent={accent} /> : null}</>
        : template === 'promise' && items.length ? <><Checklist items={items} accent={accent} />{spoken ? <Captions s={s} accent={accent} small /> : null}</>
        : template === 'teaser' ? <>{last ? (s.text ? <Slam text={s.text} color={accent} /> : null) : <ComingUp text={s.text} />}{spoken ? <Captions s={s} accent={accent} /> : null}</>
        : template === 'myth' ? <>{s.text ? <Slam text={s.text} color={accent} /> : null}{spoken ? <Captions s={s} accent={accent} small /> : null}</>
        : template === 'promise' ? <>{s.text ? <Slam text={s.text} color={accent} /> : null}{spoken ? <Captions s={s} accent={accent} small /> : null}</>
        : !spoken ? (s.text ? <Slam text={s.text} color={accent} /> : null)
        : template === 'kinetic' ? <Kinetic s={s} accent={accent} />
        : template === 'stakes' ? (s.text ? <><Slam text={s.text} color={accent} /><Captions s={s} accent={accent} small /></> : <Kinetic s={s} accent={accent} />)
        : <>{s.text && !(s.words ?? []).length ? <Slam text={s.text} color={accent} /> : null}<Captions s={s} accent={accent} /></>}
      </div>
      {!meme && s.stamp ? <Stamp s={s} /> : null}
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
  useScreenFonts();
  return (
    <Layer name={`hook (${template})`} style={{background: '#000'}}>
      {hook.shots.map((s, i) => {
        const frames = Math.max(1, f(s.duration));
        // A different hot colour per shot, never the same twice in a row.
        const accent = i === 0 ? look.accents[0] ?? HOT[0] : HOT[(i + seed) % HOT.length];
        return (
          <Sequence key={i} name={`hook ${i + 1} (${template})`} from={f(s.start)} durationInFrames={frames}>
            <EnergyShot s={s} i={i} frames={frames} template={template} accent={accent} render={render} spoken={hook.subtitles === true}
              items={template === 'promise' && i >= 2 && i < hook.shots.length - 1 ? hook.shots.slice(2, i + 1).map((x) => x.text).filter(Boolean) : []}
              last={i === hook.shots.length - 1} seed={seed} n={hook.shots.length} source={hook.source ?? undefined}
              log={hook.shots.slice(0, i).map((x) => (x.text || (x.words ?? []).map((w) => w.text).join(' ')).trim()).filter(Boolean)}
              screen={template === 'bulletin' ? bulletinScreens(hook.shots)[i] : undefined} />
          </Sequence>
        );
      })}
      {drop > 0 ? (
        <Sequence name="silence" from={live}>
          {hook.subscribe ? <SubscribeCard frames={f(drop)} vertical={BOX.V} /> : <div style={{position: 'absolute', inset: 0, background: '#000'}} />}
        </Sequence>
      ) : null}
    </Layer>
  );
};
