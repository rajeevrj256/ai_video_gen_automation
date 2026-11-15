import '@fontsource/comic-neue/400.css';
import '@fontsource/comic-neue/700.css';
import '@fontsource/caveat/400.css';
import '@fontsource/caveat/700.css';
import React, {useEffect, useState} from 'react';
import {continueRender, delayRender, interpolate, random, spring} from 'remotion';
import {H, W} from './Sets';
import type {Meter, Shot} from './types';

// Words and numbers over the picture (reelgen/sticky/ANALYSIS.md): the meter that carries the story, the day and the
// clock; narration in short white lines (the second line the twist); the inner voice typed in its colour by hand;
// speech bubbles; worries as sticky notes; notification pills; a chalk 'DAY 1.'; the title card.

export const SANS = '"Comic Neue", "Noto Sans Devanagari", sans-serif';
export const HAND = '"Caveat", "Comic Neue", cursive';
const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

export const useStickyFonts = () => {
  const [handle] = useState(() => delayRender('Loading the Sticky fonts'));
  useEffect(() => {
    Promise.all(['400 40px "Comic Neue"', '700 40px "Comic Neue"', '400 40px Caveat', '700 40px Caveat'].map((f) => document.fonts.load(f)))
      .catch(() => undefined).finally(() => continueRender(handle));
  }, [handle]);
};

const fmt = (v: number) => Math.round(v).toLocaleString('en-US');

// ---------- the HUD ----------

export const Hud: React.FC<{meter: Meter; now: number[]; before: number[] | null; t: number; day?: string; time?: string; accent: string; fw?: number; top?: number; k?: number}> = ({meter, now, before, t, day, time, accent, fw: frameW = W, top = 0, k: big = 1}) => {
  const fw = frameW / big; // drawn at `big` times its size (a phone screen), laid out in that many fewer units
  const k = interpolate(t, [0.1, 0.9], [0, 1], clamp);
  const val = (i: number) => (before && before[i] !== undefined ? before[i] + (now[i] - before[i]) * k : now[i] ?? 0);
  const color = meter.color || accent;
  const reset = meter.kind === 'counter' && before && before[0] > 0 && now[0] === 0; // the streak crashed
  return (
    <g fontFamily={SANS} style={{filter: 'drop-shadow(0 1px 3px rgba(0,0,0,0.85))'}} transform={`translate(0,${top}) scale(${big})`}>
      <defs>
        <radialGradient id="hudBack" cx="0" cy="0" r="1"><stop offset="0" stopColor="#000" stopOpacity={0.5} /><stop offset="1" stopColor="#000" stopOpacity={0} /></radialGradient>
      </defs>
      {day || (meter.kind !== 'none' && meter.kind !== 'bar' && now.length) ? <rect x={0} y={0} width={620} height={260} fill="url(#hudBack)" /> : null}
      {day ? <text x={64} y={meter.kind === 'none' ? 66 : 54} fontSize={26} fontWeight={700} letterSpacing={2} fill="#C9CBD3">{day.toUpperCase()}</text> : null}
      {time ? <text x={fw - 64} y={66} textAnchor="end" fontSize={26} fontWeight={700} fill="#C9CBD3">{time}</text> : null}
      {meter.kind === 'battery' && now.length ? (() => {
        const v = Math.max(0, Math.min(100, val(0)));
        const c = v > 50 ? '#4CD964' : v > 20 ? '#F2C230' : '#FF453A';
        return (
          <g transform={`translate(64,${day ? 70 : 34})`}>
            <rect width={74} height={36} rx={8} fill="none" stroke="#DADCE2" strokeWidth={3.5} />
            <rect x={76} y={11} width={6} height={14} rx={2} fill="#DADCE2" />
            <rect x={5} y={5} width={64 * (v / 100)} height={26} rx={5} fill={c} />
            <text x={98} y={28} fontSize={30} fontWeight={700} fill={v > 20 ? '#E8EAEE' : c}>{Math.round(v)}{meter.unit ?? '%'}</text>
            {meter.labels[0] ? <text x={0} y={66} fontSize={22} fill="#AEB2BC">{meter.labels[0]}</text> : null}
          </g>
        );
      })() : null}
      {meter.kind === 'bar' && now.length ? (() => {
        const v = Math.max(0, Math.min(100, val(0)));
        return (
          <g transform={`translate(${fw / 2 - 190},34)`}>
            <text x={0} y={0} fontSize={22} fontWeight={700} letterSpacing={3} fill="#AEB2BC">{(meter.labels[0] ?? '').toUpperCase()}</text>
            <rect x={0} y={12} width={300} height={18} rx={9} fill="#2A2C33" />
            <rect x={0} y={12} width={300 * (v / 100)} height={18} rx={9} fill={color} />
            <text x={316} y={30} fontSize={26} fontWeight={700} fill="#E8EAEE">{Math.round(v)}{meter.unit ?? '%'}</text>
          </g>
        );
      })() : null}
      {meter.kind === 'counter' && now.length ? (
        <g transform={`translate(64,${day ? 98 : 62})`}>
          <text x={0} y={0} fontSize={28} fontWeight={700} letterSpacing={2} fill="#C9CBD3">{(meter.labels[0] ?? '').toUpperCase()}{' '}
            {reset ? (
              <>
                <tspan fill="#C9CBD3" textDecoration="line-through" opacity={interpolate(t, [0.4, 1.2], [1, 0.35], clamp)}>{fmt(before![0])}</tspan>
                <tspan fill={color} dx={12} opacity={interpolate(t, [0.6, 1], [0, 1], clamp)}>0</tspan>
              </>
            ) : <tspan>{fmt(val(0))}{meter.unit ?? ''}</tspan>}
          </text>
        </g>
      ) : null}
      {meter.kind === 'dual' && now.length ? (
        <g transform={`translate(64,${day ? 98 : 54})`}>
          {meter.labels.slice(0, 2).map((l, i) => (
            <text key={i} x={0} y={i * 34} fontSize={26} fontWeight={700} letterSpacing={2} fill="#C9CBD3">{l.toUpperCase()}{' '}
              <tspan fill={i === 0 ? color : '#F2C230'}>{fmt(val(i))}</tspan></text>
          ))}
        </g>
      ) : null}
    </g>
  );
};

// ---------- narration ----------

// tall (9:16): bigger words for a phone, above the Shorts' title and buttons at the bottom, below the HUD at the top,
// each line shrunk to fit the narrow frame
export const Caption: React.FC<{c: NonNullable<Shot['caption']>; t: number; dur: number; fw?: number; fh?: number; tall?: boolean}> = ({c, t, dur, fw = W, fh = H, tall}) => {
  const lines = c.lines.slice(0, 3);
  const gap = tall ? 76 : 58, cgap = tall ? 100 : 64;
  const y0 = c.pos === 'bottom' ? fh - (tall ? 470 : 92) - (lines.length - 1) * gap : c.pos === 'center' ? fh / 2 - ((lines.length - 1) * cgap) / 2 : tall ? 450 : 120;
  const fadeOut = interpolate(t, [dur - 0.35, dur], [1, 0], clamp);
  const band = (lines.length - 1) * gap + (tall ? 300 : 240) + (tall && c.pos === 'bottom' ? 330 : 0);
  return (
    <g fontFamily={SANS} textAnchor="middle" opacity={fadeOut}>
      {c.pos !== 'center' ? (
        <>
          <defs>
            <linearGradient id={`capScrim${c.pos}`} x1="0" y1={c.pos === 'bottom' ? '1' : '0'} x2="0" y2={c.pos === 'bottom' ? '0' : '1'}>
              <stop offset="0" stopColor="#000" stopOpacity={0.72} /><stop offset="0.6" stopColor="#000" stopOpacity={0.5} /><stop offset="1" stopColor="#000" stopOpacity={0} />
            </linearGradient>
          </defs>
          <rect x={0} y={c.pos === 'bottom' ? fh - band : tall ? 300 : 0} width={fw} height={band} fill={`url(#capScrim${c.pos})`}
            opacity={interpolate(t, [0, 0.4], [0, 1], clamp)} />
        </>
      ) : null}
      {lines.map((l, i) => {
        const at = i * Math.min(1.1, dur * 0.3);
        const o = interpolate(t, [at + 0.1, at + 0.55], [0, 1], clamp);
        const bold = lines.length > 1 && i === lines.length - 1;
        const want = c.pos === 'center' ? (bold ? 54 : 48) : bold ? 46 : 40;
        const size = tall ? Math.min(want * (c.pos === 'center' ? 1.6 : 1.35), (fw - 110) / Math.max(1, l.length * 0.5)) : want;
        return (
          <text key={i} x={fw / 2} y={y0 + i * (c.pos === 'center' ? cgap : gap)} fontSize={size}
            fontWeight={bold ? 700 : 400} fill="#F2F2EE" opacity={o} style={{paintOrder: 'stroke', stroke: 'rgba(0,0,0,0.55)', strokeWidth: 6}}>
            {l}
          </text>
        );
      })}
    </g>
  );
};

// ---------- the inner voice ----------

export const Whisper: React.FC<{w: NonNullable<Shot['whisper']>; t: number; dur: number; accent: string; fw?: number; fh?: number}> = ({w, t, dur, accent, fw = W, fh = H}) => {
  const n = Math.floor(interpolate(t, [0.15, 0.15 + w.text.length / 16], [0, w.text.length], clamp));
  const size = Math.max(40, Math.min(fw < W ? 66 : 58, (fw * (fw < W ? 0.86 : 0.62)) / Math.max(1, w.text.length * 0.42)));
  const half = (w.text.length * size * 0.42) / 2 + 70;
  const x = Math.max(Math.min(half, fw / 2), Math.min(fw - Math.min(half, fw / 2), (w.x / 100) * fw)), y = Math.max(fw < W ? 420 : 150, Math.min(fh - (fw < W ? 520 : 160), (w.y / 100) * fh));
  const out = interpolate(t, [dur - 0.4, dur], [1, 0], clamp);
  return (
    <text x={x} y={y + Math.sin(t * 2) * 3} textAnchor="middle" fontFamily={HAND} fontWeight={700} fontSize={size} fill={accent} opacity={out}
      style={{filter: `drop-shadow(0 0 6px ${accent})`, paintOrder: 'stroke', stroke: 'rgba(5,5,8,0.85)', strokeWidth: 9, strokeLinejoin: 'round'}}
      transform={`rotate(-4,${x},${y})`}>
      {w.text.slice(0, n)}
    </text>
  );
};

// ---------- speech bubbles ----------

export const Bubbles: React.FC<{b: NonNullable<Shot['bubbles']>; heads: Record<string, [number, number]>; t: number; dur: number; fw?: number; fh?: number; k?: number}> = ({b, heads, t, dur, fw = W, fh = H, k: big = 1}) => {
  const each = Math.max(0.9, (dur * 0.75) / Math.max(1, b.length));
  return (
    <g fontFamily={SANS}>
      {b.map((q, i) => {
        const at = i * each;
        if (t < at) return null;
        const pop = spring({frame: Math.round((t - at) * 30), fps: 30, config: {damping: 12, mass: 0.5}});
        const [hx, hy] = heads[q.who] ?? [fw / 2, fh / 2 - 100];
        const w = Math.min(560, 60 + q.text.length * 17);
        const x = Math.max(30, Math.min(fw - w * big - 30, hx - (w / 2 - 30) * big));
        const y = Math.max(fw < W ? 300 : 40, hy - 150 * big);
        const gone = i < b.length - 1 && t > at + each * 1.6 ? 0.25 : 1;
        return (
          <g key={i} opacity={Math.min(1, pop) * gone} transform={`translate(${x},${y}) scale(${(0.7 + 0.3 * pop) * big})`}>
            <rect width={w} height={70} rx={22} fill="#F7F6F2" stroke="#2A2A31" strokeWidth={3} />
            <path d={`M30,68 L14,96 L60,68 Z`} fill="#F7F6F2" stroke="#2A2A31" strokeWidth={3} strokeLinejoin="round" />
            <rect x={28} y={60} width={34} height={12} fill="#F7F6F2" />
            <text x={w / 2} y={46} textAnchor="middle" fontSize={30} fontWeight={700} fill="#2A2A31">{q.text}</text>
          </g>
        );
      })}
    </g>
  );
};

// ---------- worries as sticky notes, notification pills ----------

// `box` [x, y, w, h]: where they pile up (the wall of the 16:9 set by default; the tall frame's upper half in a Short)
export const Notes: React.FC<{notes: string[]; t: number; dur: number; accent: string; box?: [number, number, number, number]}> = ({notes, t, dur, accent, box = [200, 120, W - 520, 520]}) => {
  const shown = Math.ceil(interpolate(t, [0.1, Math.max(0.5, dur * 0.7)], [0, notes.length], clamp));
  return (
    <g fontFamily={HAND}>
      {notes.slice(0, shown).map((n, i) => {
        const x = box[0] + random(`nx${i}`) * box[2], y = box[1] + random(`ny${i}`) * box[3];
        const r = (random(`nr${i}`) - 0.5) * 16;
        return (
          <g key={i} transform={`rotate(${r},${x + 80},${y + 70})`}>
            <rect x={x} y={y} width={170} height={150} fill={accent} style={{filter: 'drop-shadow(0 6px 6px rgba(0,0,0,0.4))'}} />
            <text x={x + 85} y={y + 66} textAnchor="middle" fontSize={36} fontWeight={700} fill="#2A1010">{n.length > 12 ? n.slice(0, 12) : n}</text>
            {n.length > 12 ? <text x={x + 85} y={y + 104} textAnchor="middle" fontSize={36} fontWeight={700} fill="#2A1010">{n.slice(12, 24)}</text> : null}
          </g>
        );
      })}
    </g>
  );
};

export const Pills: React.FC<{pills: string[]; around: [number, number]; t: number; accent: string; fw?: number; k?: number}> = ({pills, around, t, accent, fw, k: big = 1}) => (
  <g fontFamily={SANS}>
    {pills.map((p, i) => {
      const k = interpolate(t, [0.2 + i * 0.4, 0.5 + i * 0.4], [0, 1], clamp);
      const a = -2.4 + i * (2.2 / Math.max(1, pills.length - 1 || 1));
      const x = around[0] + Math.cos(a) * 300, y = around[1] - 160 + Math.sin(a) * 160;
      const w = 60 + p.length * 15;
      const left = fw ? Math.max(20, Math.min(fw - w * big - 20, x - (w / 2) * big)) : x - w / 2; // inside a tall frame
      return (
        <g key={i} opacity={k} transform={`translate(${left},${y}) scale(${(0.8 + 0.2 * k) * big})`}>
          <rect width={w} height={46} rx={23} fill="#F4F1EA" />
          <circle cx={24} cy={23} r={9} fill={accent} />
          <text x={42} y={31} fontSize={22} fontWeight={700} fill="#2A2A31">{p.toUpperCase()}</text>
        </g>
      );
    })}
  </g>
);

// ---------- chalk lines ----------

export const Stamp: React.FC<{text: string; t: number; fw?: number; y?: number}> = ({text, t, fw = W, y = 260}) => {
  const k = interpolate(t, [0.1, 0.7], [0, 1], clamp);
  return (
    <text x={fw / 2} y={y} textAnchor="middle" fontFamily={SANS} fontWeight={700} fontSize={150} fill="#F4F2EC" opacity={k}
      transform={`scale(${0.94 + 0.06 * k})`} style={{transformOrigin: `${fw / 2}px ${y - 40}px`, filter: 'drop-shadow(0 0 18px rgba(255,255,255,0.25))'}}>
      {text}
    </text>
  );
};

export const TitleCard: React.FC<{title: string; tagline: string[]; t: number; accent: string; fw?: number; fh?: number}> = ({title, tagline, t, accent, fw = W, fh = H}) => {
  const W = fw, H = fh; // the frame it fills (16:9 film or 9:16 Short)
  const shown = Math.ceil(interpolate(t, [0.2, 1.2], [0, title.length], clamp));
  const line = interpolate(t, [1.2, 1.8], [0, 1], clamp);
  const size = Math.min(170, Math.floor((W < H ? 900 : 1500) / Math.max(4, title.length * 0.62)));
  return (
    <g fontFamily={SANS} textAnchor="middle">
      <rect width={W} height={H} fill="#0F1013" />
      {Array.from({length: 40}, (_, i) => <circle key={i} cx={random(`ts${i}`) * W} cy={random(`tt${i}`) * H} r={1.6} fill="#fff" opacity={0.25 + 0.2 * Math.sin(t * 2 + i)} />)}
      <text x={W / 2} y={H / 2 - 40} fontSize={size} fontWeight={700} fill="#F4F2EC" letterSpacing={4}>{title.slice(0, shown)}</text>
      <path d={`M${W / 2 - 260},${H / 2 + 6} q${260 * line},14 ${520 * line},-4`} stroke={accent} strokeWidth={7} fill="none" strokeLinecap="round" />
      {tagline.slice(0, 2).map((l, i) => (
        <text key={i} x={W / 2} y={H / 2 + (W < H ? 120 : 90) + i * (W < H ? 76 : 56)} fontSize={(i ? 44 : 38) * (W < H ? 1.4 : 1)} fontWeight={i ? 700 : 400} fill={i ? accent : '#E6E6E0'}
          opacity={interpolate(t, [1.8 + i * 1.1, 2.3 + i * 1.1], [0, 1], clamp)}>{l}</text>
      ))}
    </g>
  );
};
