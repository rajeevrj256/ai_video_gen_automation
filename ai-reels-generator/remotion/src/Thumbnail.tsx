import React from 'react';
import {Img, staticFile} from 'remotion';
import {FONT, useFonts} from './theme';
import {iconFor, setCurrency} from './long/icon';

// A YouTube thumbnail made from the video's own frame (reelgen/thumbnail.py): Claude picks the
// frame, the 2-4 words (taken from the video) and the layout; this draws it in the video's colours,
// so the thumbnail always matches what the viewer then sees. Rendered as a still.

export type ThumbProps = {
  src: string; // a frame of the video, relative to the public dir
  text: string; // 2-4 words, the biggest thing on it
  highlight?: string; // the word(s) in the accent colour
  sub?: string; // optional small line (a figure or a date from the video)
  side: 'left' | 'right' | 'top' | 'bottom';
  focusX: number; // 0-1, the part of the frame to keep in view
  focusY: number;
  zoom: number; // 1-2
  accent: string;
  accent2: string;
  icon?: string; // optional big icon next to the words
  mark?: 'none' | 'circle' | 'arrow';
  markX?: number; // 0-1 on the final image
  markY?: number;
  currency?: string;
  wide: boolean; // 16:9 (long video) or 9:16 (Short)
};

export const thumbSize = (wide: boolean) => (wide ? {width: 1280, height: 720} : {width: 1080, height: 1920});

const outline = (px: number) =>
  Array.from({length: 16}, (_, i) => {
    const a = (i / 16) * Math.PI * 2;
    return `${(Math.cos(a) * px).toFixed(1)}px ${(Math.sin(a) * px).toFixed(1)}px 0 #000`;
  }).join(', ');

export const Thumbnail: React.FC<ThumbProps> = (p) => {
  useFonts();
  setCurrency(p.currency);
  const {width: W, height: H} = thumbSize(p.wide);
  const words = p.text.trim().split(/\s+/);
  const hi = new Set((p.highlight ?? '').toLowerCase().split(/\s+/).filter(Boolean));
  const sideways = p.side === 'left' || p.side === 'right';
  // Beside the subject: one word per line (3 words) or two pairs (4), as big as the free side allows.
  // Above/below it: two lines at most.
  const per = sideways ? (words.length === 4 ? 2 : 1) : words.length > 2 ? Math.ceil(words.length / 2) : p.wide ? 1 : words.length;
  const lines: string[][] = [];
  for (let i = 0; i < words.length; i += per) lines.push(words.slice(i, i + per));
  const longest = Math.max(...lines.map((l) => l.join(' ').length));
  const box = sideways ? W * 0.5 : W * 0.9;
  const tall = H * (sideways ? 0.72 : p.wide ? 0.4 : 0.32); // room for the lines (and the badge)
  const size = Math.min(p.wide ? 190 : 200, box / (Math.max(3, longest) * 0.78), tall / (lines.length + (p.sub ? 0.6 : 0)));
  const Icon = p.icon ? iconFor(p.icon) : null;
  const shade = {
    left: 'linear-gradient(90deg, rgba(0,0,0,0.85) 0%, rgba(0,0,0,0.55) 45%, transparent 75%)',
    right: 'linear-gradient(270deg, rgba(0,0,0,0.85) 0%, rgba(0,0,0,0.55) 45%, transparent 75%)',
    top: 'linear-gradient(180deg, rgba(0,0,0,0.85) 0%, rgba(0,0,0,0.5) 40%, transparent 70%)',
    bottom: 'linear-gradient(0deg, rgba(0,0,0,0.85) 0%, rgba(0,0,0,0.5) 40%, transparent 70%)',
  }[p.side];
  const place: React.CSSProperties = {
    left: {left: W * 0.05, top: 0, bottom: 0, width: box, justifyContent: 'center', alignItems: 'flex-start'},
    right: {right: W * 0.05, top: 0, bottom: 0, width: box, justifyContent: 'center', alignItems: 'flex-end'},
    top: {left: W * 0.05, right: W * 0.05, top: H * (p.wide ? 0.06 : 0.07), alignItems: 'center'},
    bottom: {left: W * 0.05, right: W * 0.05, bottom: H * (p.wide ? 0.07 : 0.1), alignItems: 'center'},
  }[p.side];
  const zoom = Math.min(2, Math.max(1, p.zoom || 1));
  return (
    <div style={{position: 'absolute', inset: 0, overflow: 'hidden', background: '#000', fontFamily: FONT}}>
      <Img
        src={staticFile(p.src)}
        style={{
          position: 'absolute',
          inset: 0,
          width: '100%',
          height: '100%',
          objectFit: 'cover',
          objectPosition: `${p.focusX * 100}% ${p.focusY * 100}%`,
          transform: `scale(${zoom})`,
          transformOrigin: `${p.focusX * 100}% ${p.focusY * 100}%`,
          filter: 'saturate(1.35) contrast(1.15) brightness(1.05)',
        }}
      />
      <div style={{position: 'absolute', inset: 0, background: shade}} />
      <div style={{position: 'absolute', inset: 0, boxShadow: `inset 0 0 ${W * 0.12}px rgba(0,0,0,0.7)`}} />
      {p.mark === 'circle' ? (
        <div
          style={{
            position: 'absolute',
            left: (p.markX ?? 0.7) * W - W * 0.1,
            top: (p.markY ?? 0.5) * H - W * 0.1,
            width: W * 0.2,
            height: W * 0.2,
            borderRadius: '50%',
            border: `${W * 0.009}px solid ${p.accent}`,
            boxShadow: `0 0 30px ${p.accent}, inset 0 0 20px ${p.accent}88`,
          }}
        />
      ) : null}
      {p.mark === 'arrow' ? (
        <svg style={{position: 'absolute', left: 0, top: 0, width: W, height: H, overflow: 'visible'}}>
          <path
            d={`M ${(p.markX ?? 0.7) * W - W * 0.16} ${(p.markY ?? 0.5) * H + H * 0.2} L ${(p.markX ?? 0.7) * W - W * 0.03} ${(p.markY ?? 0.5) * H + H * 0.03}`}
            stroke={p.accent}
            strokeWidth={W * 0.016}
            strokeLinecap="round"
            style={{filter: `drop-shadow(0 0 12px ${p.accent})`}}
          />
          <path
            d={`M ${(p.markX ?? 0.7) * W - W * 0.085} ${(p.markY ?? 0.5) * H + H * 0.02} L ${(p.markX ?? 0.7) * W - W * 0.03} ${(p.markY ?? 0.5) * H + H * 0.03} L ${(p.markX ?? 0.7) * W - W * 0.035} ${(p.markY ?? 0.5) * H + H * 0.1}`}
            stroke={p.accent}
            strokeWidth={W * 0.016}
            strokeLinecap="round"
            strokeLinejoin="round"
            fill="none"
          />
        </svg>
      ) : null}
      <div style={{position: 'absolute', display: 'flex', flexDirection: 'column', gap: size * 0.05, ...place}}>
        {Icon && !p.wide ? (
          <Icon size={size * 1.6} color="#fff" strokeWidth={2.2} style={{filter: `drop-shadow(0 0 24px ${p.accent})`, marginBottom: size * 0.2}} />
        ) : null}
        {lines.map((line, i) => (
          <div
            key={i}
            style={{
              fontSize: size,
              lineHeight: 1.0,
              fontWeight: 900,
              textTransform: 'uppercase',
              letterSpacing: '-0.01em',
              color: '#fff',
              textShadow: `${outline(size * 0.055)}, 0 ${size * 0.09}px ${size * 0.12}px rgba(0,0,0,0.6)`,
              transform: `rotate(-2deg)`,
              whiteSpace: 'nowrap',
              textAlign: p.side === 'right' ? 'right' : p.side === 'left' ? 'left' : 'center',
            }}
          >
            {line.map((w, k) => (
              <span key={k} style={{color: hi.has(w.toLowerCase().replace(/[^\p{L}\p{N}₹$€£%.]/gu, '')) ? p.accent : '#fff'}}>
                {w}
                {k < line.length - 1 ? ' ' : ''}
              </span>
            ))}
          </div>
        ))}
        {p.sub ? (
          <div
            style={{
              marginTop: size * 0.12,
              padding: `${size * 0.08}px ${size * 0.22}px`,
              background: p.accent2,
              color: '#000',
              fontSize: size * 0.36,
              fontWeight: 900,
              textTransform: 'uppercase',
              borderRadius: size * 0.08,
              transform: 'rotate(-2deg)',
              boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
            }}
          >
            {p.sub}
          </div>
        ) : null}
      </div>
      {Icon && p.wide ? (
        <div
          style={{
            position: 'absolute',
            [p.side === 'right' ? 'left' : 'right']: W * 0.06,
            bottom: H * 0.1,
            filter: `drop-shadow(0 0 28px ${p.accent})`,
          }}
        >
          <Icon size={H * 0.34} color="#fff" strokeWidth={2.2} />
        </div>
      ) : null}
    </div>
  );
};
