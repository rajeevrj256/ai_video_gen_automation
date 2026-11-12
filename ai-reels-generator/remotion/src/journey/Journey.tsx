import React from 'react';
import '@fontsource/montserrat/800-italic.css';
import '@fontsource/inter/700.css';
import {AbsoluteFill, OffthreadVideo, interpolate, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import type {JourneyLabel, JourneyProps} from './types';

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

export const Journey: React.FC<JourneyProps> = ({story, bg, top, bottom, labels, duration, grade}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = frame / fps;
  const fade = interpolate(t, [0, 0.25, duration - 0.6, duration], [0, 1, 1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  // lightning: the frame lights up twice in a moment, as a real strike lights a scene
  const flash = (grade ?? []).reduce((m, g) => Math.max(m,
    interpolate(t - g.flash, [-0.02, 0, 0.08, 0.16, 0.22, 0.5], [0, 0.85, 0.2, 0.6, 0.1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})), 0);
  const filter = flash > 0.001 ? `brightness(${1 + flash * 0.9})` : undefined;
  return (
    <AbsoluteFill style={{background: '#000'}}>
      <AbsoluteFill style={{opacity: fade}}>
        <div style={{position: 'absolute', inset: 0, filter}}>
          <OffthreadVideo src={staticFile(bg)} muted style={{position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover'}} />
        </div>
        <div style={{position: 'absolute', left: 0, top: BAND_TOP, width: 1080, height: BAND, overflow: 'hidden',
          boxShadow: '0 0 40px rgba(0,0,0,0.25)'}}>
          <div style={{position: 'absolute', inset: 0, filter}}>
            <OffthreadVideo src={staticFile(story)} muted style={{width: '100%', height: '100%', objectFit: 'cover'}} />
          </div>
        </div>
        {(labels ?? []).map((l, i) => <Label key={i} l={l} t={t} />)}
      </AbsoluteFill>
      {top ? <Line text={top} y={BAND_TOP / 2} /> : null}
      {bottom ? <Line text={bottom} y={BAND_TOP + BAND + BAND_TOP / 2} /> : null}
    </AbsoluteFill>
  );
};
