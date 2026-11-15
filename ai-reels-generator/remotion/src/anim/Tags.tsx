import React from 'react';
import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {clamp} from '../theme';
import {type Face, LABEL, SOFT_SHADOW} from './type';

// The Shorts Studio's series tags (reelgen/storyshorts.py), shared by the Anim and Long compositions in 9:16.
// Letter-spacing breaks Devanagari's joined letters ("भाग" came out "भा ग"), so Hindi text is never tracked.
const DEVANAGARI = /[\u0900-\u097F]/;
const track = (text: string, spacing: string | number) => (DEVANAGARI.test(text) ? 0 : spacing);

// Story Shorts: "PART 2/3" and the series title as the Short opens (below the Shorts' top bar), gone after 2.6 s.
export const PartTag: React.FC<{label: string; title: string; accent: string; face: Face}> = ({label, title, accent, face}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const k = spring({frame: frame - 3, fps, config: {damping: 16}});
  const out = interpolate(frame, [fps * 2.2, fps * 2.6], [1, 0], clamp);
  return (
    <div style={{position: 'absolute', left: 0, right: 0, top: 150, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 14, opacity: Math.min(k, out)}}>
      <div style={{fontFamily: LABEL, fontWeight: 700, fontSize: 40, letterSpacing: track(label, '0.22em'), marginRight: DEVANAGARI.test(label) ? 0 : '-0.22em', color: '#0b0b0f', background: accent,
        padding: '8px 26px 10px', borderRadius: 6, transform: `translateY(${(1 - k) * -20}px)`, boxShadow: '0 10px 30px rgba(0,0,0,0.45)'}}>{label}</div>
      <div style={{fontFamily: face.family, fontWeight: face.weight, fontSize: 54 * face.size, letterSpacing: track(title, face.tracking), textTransform: face.upper ? 'uppercase' : 'none',
        color: '#fff', textAlign: 'center', maxWidth: 900, lineHeight: 1.08, textShadow: SOFT_SHADOW} as React.CSSProperties}>{title}</div>
    </div>
  );
};

// Story Shorts: "PART 3 →" over the last moment, so the viewer looks for the next part.
export const NextTag: React.FC<{label: string; accent: string; face: Face}> = ({label, accent, face}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const k = spring({frame: frame - 2, fps, config: {damping: 14, mass: 0.7}});
  return (
    <div style={{position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      background: `rgba(0,0,0,${0.6 * Math.min(1, k)})`}}>
      <div style={{fontFamily: face.family, fontWeight: face.weight, fontSize: 132 * face.size, letterSpacing: track(label, face.tracking), textTransform: face.upper ? 'uppercase' : 'none',
        color: '#fff', textShadow: SOFT_SHADOW, transform: `scale(${0.8 + 0.2 * k})`, opacity: Math.min(1, k * 1.4)} as React.CSSProperties}>{label}</div>
      <div style={{marginTop: 18, height: 6, width: 300 * k, background: accent, borderRadius: 3}} />
    </div>
  );
};

