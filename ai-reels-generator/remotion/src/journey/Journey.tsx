import React from 'react';
import '@fontsource/montserrat/800-italic.css';
import '@fontsource/inter/700.css';
import {AbsoluteFill, OffthreadVideo, interpolate, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import type {JourneyGrade, JourneyLabel, JourneyLight, JourneyProps} from './types';

// The reference's layout: the 16:9 picture across the middle (1080 x 607 of a 1080 x 1920 frame), the same picture
// blurred and a little darker filling the rest, the two lines centred in the space above and below it.
export const BAND = 1080 * 9 / 16;
const BAND_TOP = (1920 - BAND) / 2;

const Line: React.FC<{text: string; y: number}> = ({text, y}) => {
  const long = text.length > 34;
  return (
    <div style={{position: 'absolute', left: 70, right: 70, top: y, transform: 'translateY(-50%)', textAlign: 'center',
      fontFamily: 'Montserrat', fontWeight: 800, fontStyle: 'italic', fontSize: long ? 60 : 70, lineHeight: 1.16, textWrap: 'balance',
      color: '#fff', letterSpacing: 0.2, textShadow: '0 3px 14px rgba(0,0,0,0.55), 0 1px 3px rgba(0,0,0,0.6)'}}>
      {text}
    </div>
  );
};

const Label: React.FC<{l: JourneyLabel; t: number}> = ({l, t}) => {
  const o = interpolate(t, [l.at, l.at + 0.35, l.until - 0.35, l.until], [0, 1, 1, 0],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  if (o <= 0) return null;
  return (
    <div style={{position: 'absolute', left: 0, right: 0, top: BAND_TOP + BAND - 64, textAlign: 'center', opacity: o}}>
      <span style={{fontFamily: 'Inter', fontWeight: 700, fontSize: 30, letterSpacing: 4, color: '#fff',
        background: 'rgba(0,0,0,0.42)', padding: '8px 18px', borderRadius: 8}}>{l.text}</span>
    </div>
  );
};

// Each light as a CSS filter and a colour laid over the picture (multiply), plus how much rain falls.
type Look = {b: number; s: number; tint: string; tintA: number; rain: number};
const LOOKS: Record<JourneyLight, Look> = {
  dawn: {b: 0.92, s: 0.9, tint: '#ffb08a', tintA: 0.12, rain: 0},
  morning: {b: 1.03, s: 1.02, tint: '#fff4e0', tintA: 0.05, rain: 0},
  midday: {b: 1.05, s: 1.05, tint: '#ffffff', tintA: 0, rain: 0},
  golden: {b: 0.98, s: 1.08, tint: '#ffa64d', tintA: 0.16, rain: 0},
  overcast: {b: 0.88, s: 0.78, tint: '#c8d0d8', tintA: 0.12, rain: 0},
  storm: {b: 0.6, s: 0.55, tint: '#2d3a48', tintA: 0.42, rain: 1},
  rain: {b: 0.76, s: 0.7, tint: '#3d4a58', tintA: 0.28, rain: 0.65},
  dusk: {b: 0.74, s: 0.85, tint: '#6a4a7a', tintA: 0.22, rain: 0},
  night: {b: 0.55, s: 0.6, tint: '#1d3f78', tintA: 0.55, rain: 0},
};
const FADE = 0.8;

const lookAt = (grade: JourneyGrade[], t: number): Look => {
  const i = Math.max(0, grade.findIndex((g) => t < g.until));
  const cur = LOOKS[grade[i]?.light ?? 'midday'];
  const next = grade[i + 1];
  if (!next) return cur;
  const k = interpolate(t, [next.at - FADE / 2, next.at + FADE / 2], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  if (k <= 0) return cur;
  const n = LOOKS[next.light];
  const mix = (a: number, b: number) => a + (b - a) * k;
  return {b: mix(cur.b, n.b), s: mix(cur.s, n.s), tint: k < 0.5 ? cur.tint : n.tint,
    // the colour changes at the middle of the fade: the old one fades out, then the new one fades in
    tintA: k < 0.5 ? cur.tintA * (1 - 2 * k) : n.tintA * (2 * k - 1), rain: mix(cur.rain, n.rain)};
};

// Falling rain: thin streaks, the same every render (positions from the frame number, not random).
const Rain: React.FC<{amount: number; frame: number}> = ({amount, frame}) => {
  if (amount <= 0.02) return null;
  const n = Math.round(140 * amount);
  return (
    <svg viewBox="0 0 1080 608" preserveAspectRatio="none" style={{position: 'absolute', inset: 0, width: '100%', height: '100%', opacity: 0.55 * amount}}>
      {Array.from({length: n}, (_, i) => {
        const x = ((i * 137.5) % 1080 + frame * 2.2) % 1100 - 10;
        const y = ((i * 71.3 + frame * (38 + (i % 5) * 4)) % 700) - 60;
        return <line key={i} x1={x} y1={y} x2={x - 7} y2={y + 34 + (i % 4) * 6} stroke="#dfe8f2" strokeWidth={1.1 + (i % 3) * 0.4} strokeLinecap="round" />;
      })}
    </svg>
  );
};

export const Journey: React.FC<JourneyProps> = ({story, bg, top, bottom, labels, duration, grade}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = frame / fps;
  const fade = interpolate(t, [0, 0.25, duration - 0.6, duration], [0, 1, 1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const look = grade && grade.length ? lookAt(grade, t) : null;
  const flash = (grade ?? []).reduce((m, g) => g.flash !== undefined ? Math.max(m,
    interpolate(t - g.flash, [-0.02, 0, 0.08, 0.16, 0.22, 0.5], [0, 0.85, 0.2, 0.6, 0.1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})) : m, 0);
  const filter = look ? `brightness(${look.b + flash * 0.9}) saturate(${look.s})` : undefined;
  const tint = look && look.tintA > 0.01 ? <div style={{position: 'absolute', inset: 0, background: look.tint, opacity: look.tintA, mixBlendMode: 'multiply'}} /> : null;
  return (
    <AbsoluteFill style={{background: '#000'}}>
      <AbsoluteFill style={{opacity: fade}}>
        <div style={{position: 'absolute', inset: 0, filter}}>
          <OffthreadVideo src={staticFile(bg)} muted style={{position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover'}} />
          {tint}
        </div>
        <div style={{position: 'absolute', left: 0, top: BAND_TOP, width: 1080, height: BAND, overflow: 'hidden',
          boxShadow: '0 0 40px rgba(0,0,0,0.25)'}}>
          <div style={{position: 'absolute', inset: 0, filter}}>
            <OffthreadVideo src={staticFile(story)} muted style={{width: '100%', height: '100%', objectFit: 'cover'}} />
            {tint}
          </div>
          {look ? <Rain amount={look.rain} frame={frame} /> : null}
        </div>
        {(labels ?? []).map((l, i) => <Label key={i} l={l} t={t} />)}
      </AbsoluteFill>
      {top ? <Line text={top} y={BAND_TOP / 2} /> : null}
      {bottom ? <Line text={bottom} y={BAND_TOP + BAND + BAND_TOP / 2} /> : null}
    </AbsoluteFill>
  );
};
