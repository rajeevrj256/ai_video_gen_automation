import React from 'react';
import {interpolate, random} from 'remotion';
import {Check} from 'lucide-react';
import {iconFor} from '../long/icon';
import {TONES} from './Bean';
import {Digits, H, W} from './Sets';
import type {Cast, Phone, Shot} from './types';

// The close-ups the reference films cut to: the phone in both hands (chats, a feed, notifications, a dialog), the
// alarm clock, the wall calendar, a drawing or a note, a graph drawn into the dark. All drawn in the 1920x1080 frame.

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;
const INK = '#2A2A31';
const SANS = '"Comic Neue", "Noto Sans Devanagari", sans-serif';
const HAND = '"Caveat", "Comic Neue", cursive';

// ---------- the phone ----------

const PW = 500;
const PH = 960;
const PX = (W - PW) / 2;
const PY = 150;

const Hands: React.FC<{tone: string; tap: number; thumb: [number, number]}> = ({tone, tap, thumb}) => (
  <g>
    {/* left hand: fingers wrapping the left edge */}
    <path d={`M${PX - 160},${H + 40} C${PX - 120},${PY + 640} ${PX - 40},${PY + 600} ${PX + 10},${PY + 620}`} stroke={INK} strokeWidth={128} fill="none" strokeLinecap="round" />
    <path d={`M${PX - 160},${H + 40} C${PX - 120},${PY + 640} ${PX - 40},${PY + 600} ${PX + 10},${PY + 620}`} stroke={tone} strokeWidth={120} fill="none" strokeLinecap="round" />
    {/* no fingers drawn over the edge: three knuckles read as three dots, a finger shape as a button on the phone */}
    {/* right hand and thumb */}
    <path d={`M${PX + PW + 220},${H + 60} C${PX + PW + 120},${PY + 760} ${thumb[0] + 60},${thumb[1] + 140 + tap * 8} ${thumb[0]},${thumb[1] + tap * 10}`} stroke={INK} strokeWidth={98} fill="none" strokeLinecap="round" />
    <path d={`M${PX + PW + 220},${H + 60} C${PX + PW + 120},${PY + 760} ${thumb[0] + 60},${thumb[1] + 140 + tap * 8} ${thumb[0]},${thumb[1] + tap * 10}`} stroke={tone} strokeWidth={90} fill="none" strokeLinecap="round" />
  </g>
);

const Bubble: React.FC<{me: boolean; text: string; y: number; shown: number}> = ({me, text, y, shown}) => {
  const w = Math.min(380, 40 + text.length * 15);
  const x = me ? PX + PW - 30 - w : PX + 30;
  return (
    <g opacity={shown} transform={`translate(0,${(1 - shown) * 16})`}>
      <rect x={x} y={y} width={w} height={58} rx={22} fill={me ? '#2F7CF6' : '#3A3D46'} />
      <text x={x + 20} y={y + 38} fontFamily={SANS} fontWeight={700} fontSize={26} fill="#fff">{text}</text>
    </g>
  );
};

const Screen: React.FC<{p: Phone; t: number; dur: number; accent: string}> = ({p, t, dur, accent}) => {
  const sx = PX + 22, sy = PY + 70, sw = PW - 44;
  switch (p.mode) {
    case 'chat': {
      const msgs = p.messages ?? [];
      const typing = p.typing ?? '';
      const each = Math.max(0.35, Math.min(1.1, (dur * 0.55) / Math.max(1, msgs.length)));
      const typed = typing ? Math.floor(interpolate(t, [msgs.length * each * 0.6 + 0.3, dur * 0.85], [0, typing.length], clamp)) : 0;
      return (
        <g>
          <circle cx={sx + 46} cy={sy + 40} r={24} fill={accent} opacity={0.7} />
          <text x={sx + 84} y={sy + 50} fontFamily={SANS} fontWeight={700} fontSize={30} fill="#EEE">{p.title ?? ''}</text>
          <line x1={sx} y1={sy + 90} x2={sx + sw} y2={sy + 90} stroke="#333845" strokeWidth={2} />
          {msgs.map((m, i) => <Bubble key={i} me={m.me} text={m.text} y={sy + 120 + i * 76} shown={interpolate(t, [i * each * 0.6, i * each * 0.6 + 0.25], [0, 1], clamp)} />)}
          {p.seen && msgs.length ? <text x={sx + sw - 20} y={sy + 120 + msgs.length * 76 + 4} textAnchor="end" fontFamily={SANS} fontSize={20} fill="#9AA">Seen</text> : null}
          <rect x={sx + 10} y={PY + PH - 320} width={sw - 20} height={60} rx={30} fill="#262932" stroke="#3D414C" strokeWidth={2} />
          <text x={sx + 34} y={PY + PH - 280} fontFamily={SANS} fontWeight={700} fontSize={26} fill="#EEE">{typing.slice(0, typed)}{typing && t % 1 < 0.5 ? '|' : ''}</text>
          {Array.from({length: 30}, (_, i) => <rect key={i} x={sx + 14 + (i % 10) * 44} y={PY + PH - 240 + Math.floor(i / 10) * 56} width={36} height={46} rx={6} fill="#2E313A" />)}
        </g>
      );
    }
    case 'feed': {
      const items = p.items?.length ? p.items : ['hamburger', 'car', 'cat', 'palmtree'];
      const scroll = t * 260;
      return (
        <g>
          {Array.from({length: 8}, (_, i) => {
            const y = sy + 20 + i * 330 - (scroll % (items.length * 330));
            const name = items[i % items.length];
            const Icon = iconFor(name);
            const hue = ['#E36B4E', '#4E8BE3', '#E3B14E', '#4EBE8B', '#B44EE3'][i % 5];
            return y > sy - 340 && y < PY + PH ? (
              <g key={i}>
                <rect x={sx + 10} y={y} width={sw - 20} height={300} rx={16} fill={hue} opacity={0.85} />
                <Icon x={sx + sw / 2 - 90} y={y + 50} size={180} color="#fff" strokeWidth={1.6} />
                <circle cx={sx + 40} cy={y + 274} r={10} fill="#fff" opacity={0.8} />
              </g>
            ) : null;
          })}
        </g>
      );
    }
    case 'notif':
    case 'lock': {
      const items = p.mode === 'notif' ? p.items ?? [] : [];
      return (
        <g>
          <text x={PX + PW / 2} y={sy + 200} textAnchor="middle" fontFamily={SANS} fontWeight={700} fontSize={110} fill="#EEE">{p.time ?? '2:41'}</text>
          {items.map((s, i) => {
            const k = interpolate(t, [0.2 + i * 0.35, 0.45 + i * 0.35], [0, 1], clamp);
            return <g key={i} opacity={k} transform={`translate(0,${(1 - k) * -30})`}><rect x={sx + 16} y={sy + 290 + i * 104} width={sw - 32} height={88} rx={20} fill="#2B2E37" />
              <circle cx={sx + 60} cy={sy + 334 + i * 104} r={20} fill={accent} /><text x={sx + 96} y={sy + 344 + i * 104} fontFamily={SANS} fontWeight={700} fontSize={26} fill="#EEE">{s}</text></g>;
          })}
        </g>
      );
    }
    case 'dialog': {
      const press = interpolate(t, [dur * 0.65, dur * 0.75], [0, 1], clamp);
      const btns = p.items?.length ? p.items : ['cancel', 'delete'];
      return (
        <g>
          <rect x={sx + 30} y={sy + 260} width={sw - 60} height={260} rx={24} fill="#2B2E37" />
          <text x={PX + PW / 2} y={sy + 340} textAnchor="middle" fontFamily={SANS} fontWeight={700} fontSize={34} fill="#EEE">{p.title ?? 'Are you sure?'}</text>
          {btns.slice(0, 2).map((b, i) => <g key={i}><rect x={sx + 60 + i * 200} y={sy + 400} width={170} height={70} rx={35} fill={i === 1 ? (press > 0.5 ? '#B83030' : '#E04848') : '#3A3D46'} />
            <text x={sx + 145 + i * 200} y={sy + 446} textAnchor="middle" fontFamily={SANS} fontWeight={700} fontSize={28} fill="#fff">{b}</text></g>)}
        </g>
      );
    }
    case 'call': {
      const ring = Math.sin(t * 12) * 4;
      return (
        <g>
          <circle cx={PX + PW / 2} cy={sy + 230} r={90} fill={accent} opacity={0.6} />
          <text x={PX + PW / 2} y={sy + 390} textAnchor="middle" fontFamily={SANS} fontWeight={700} fontSize={44} fill="#EEE">{p.title ?? ''}</text>
          <text x={PX + PW / 2} y={sy + 436} textAnchor="middle" fontFamily={SANS} fontSize={26} fill="#AAB">calling...</text>
          <circle cx={sx + 110} cy={PY + PH - 220 + ring} r={46} fill="#E04848" /><circle cx={sx + sw - 110} cy={PY + PH - 220 - ring} r={46} fill="#3DBE6E" />
        </g>
      );
    }
    case 'video':
    case 'post':
      return (
        <g>
          <rect x={sx + 20} y={sy + 160} width={sw - 40} height={300} rx={14} fill={p.mode === 'post' ? '#F4F1EA' : accent} opacity={0.9} />
          <text x={PX + PW / 2} y={sy + 520} textAnchor="middle" fontFamily={SANS} fontWeight={700} fontSize={30} fill="#EEE">{p.title ?? ''}</text>
          {p.mode === 'post' ? (p.items ?? ['delete', 'post']).slice(0, 2).map((b, i) => <g key={i}><rect x={sx + 60 + i * 200} y={sy + 580} width={170} height={64} rx={32} fill={i ? '#2F7CF6' : '#3A3D46'} />
            <text x={sx + 145 + i * 200} y={sy + 622} textAnchor="middle" fontFamily={SANS} fontWeight={700} fontSize={26} fill="#fff">{b}</text></g>) : (
            <g><rect x={sx + 20} y={sy + 470} width={sw - 40} height={8} rx={4} fill="#3A3D46" /><rect x={sx + 20} y={sy + 470} width={(sw - 40) * ((t / dur) * 0.6 + 0.2)} height={8} rx={4} fill="#E04848" /></g>)}
        </g>
      );
    default:
      return null;
  }
};

export const PhoneInsert: React.FC<{p: Phone; t: number; dur: number; accent: string; hero?: Cast}> = ({p, t, dur, accent, hero}) => {
  const tone = TONES[hero?.tone ?? 'cream'];
  const tap = p.mode === 'chat' && p.typing ? Math.abs(Math.sin(t * 14)) : p.mode === 'feed' ? Math.abs(Math.sin(t * 3)) : 0;
  const thumb: [number, number] = p.mode === 'chat' ? [PX + PW - 160, PY + PH - 190] : p.mode === 'dialog' ? [PX + PW - 150, PY + 560] : [PX + PW - 120, PY + 640];
  return (
    <g>
      <rect width={W} height={H} fill="#0D0E13" />
      <ellipse cx={W / 2} cy={PY + 400} rx={700} ry={520} fill="#1C2B4A" opacity={0.35} />
      <rect x={PX - 12} y={PY - 12} width={PW + 24} height={PH + 24} rx={70} fill="#0A0A0C" stroke="#3A3D46" strokeWidth={4} />
      <rect x={PX} y={PY} width={PW} height={PH} rx={60} fill="#15171D" />
      <defs><clipPath id="phoneClip"><rect x={PX} y={PY} width={PW} height={PH} rx={60} /></clipPath></defs>
      <g clipPath="url(#phoneClip)"><Screen p={p} t={t} dur={dur} accent={accent} /></g>
      <rect x={W / 2 - 60} y={PY + 18} width={120} height={30} rx={15} fill="#0A0A0C" />
      <Hands tone={tone} tap={tap} thumb={thumb} />
    </g>
  );
};

// ---------- the alarm clock ----------

export const ClockInsert: React.FC<{time: string}> = ({time}) => (
  <g>
    <rect width={W} height={H} fill="#0B0B0E" />
    <ellipse cx={W / 2} cy={H / 2} rx={620} ry={330} fill="#3A0E10" opacity={0.35} />
    <rect x={W / 2 - 430} y={H / 2 - 210} width={860} height={420} rx={50} fill="#121216" stroke="rgba(222,226,234,0.7)" strokeWidth={5} />
    <rect x={W / 2 - 60} y={H / 2 - 240} width={120} height={36} rx={14} fill="#121216" stroke="rgba(222,226,234,0.5)" strokeWidth={4} />
    <Digits text={time} x={W / 2 - 340} y={H / 2 - 130} h={260} />
    <line x1={W / 2 - 900} y1={H / 2 + 214} x2={W / 2 + 900} y2={H / 2 + 214} stroke="rgba(222,226,234,0.4)" strokeWidth={3} />
  </g>
);

// ---------- the wall calendar ----------

export const CalendarInsert: React.FC<{c: NonNullable<Shot['calendar']>; t: number; dur: number; accent: string}> = ({c, t, dur, accent}) => {
  const days = c.days ?? 30;
  const cols = 7;
  const cw = 104, ch = 86;
  const x0 = W / 2 - (cols * cw) / 2, y0 = 300;
  // What this month's calendar already showed stays drawn; only the days since then are ticked (or scribbled) during
  // the shot. Before, every calendar shot ticked from day 1 again. With no earlier calendar, the last week is new.
  const before = c.before ?? Math.max(0, c.checks - 7);
  const oldMarks = new Set(c.beforeMarks ?? []);
  const newMarks = (c.marks ?? []).filter((d) => !oldMarks.has(d));
  const fresh = Math.max(0, c.checks - before) + newMarks.length;
  const span = Math.max(0.6, dur * 0.7);
  const step = fresh ? (span - 0.3) / fresh : 1;
  const drawn = before + Math.floor(interpolate(t, [0.3, span], [0, Math.max(0, c.checks - before)], clamp));
  const markAt = (d: number) => 0.3 + (Math.max(0, c.checks - before) + newMarks.indexOf(d)) * step; // after the new ticks
  return (
    <g>
      <rect width={W} height={H} fill="#121317" />
      <g transform={`rotate(-2,${W / 2},${H / 2})`}>
        <rect x={x0 - 40} y={y0 - 150} width={cols * cw + 80} height={Math.ceil(days / cols) * ch + 200} rx={18} fill="#F4F1EA" />
        <rect x={x0 - 40} y={y0 - 150} width={cols * cw + 80} height={110} rx={18} fill="#D8414A" />
        <text x={W / 2} y={y0 - 76} textAnchor="middle" fontFamily={SANS} fontWeight={700} fontSize={56} fill="#fff">{c.month.toUpperCase()}</text>
        {Array.from({length: days}, (_, i) => {
          const x = x0 + (i % cols) * cw, y = y0 + Math.floor(i / cols) * ch;
          const bad = (c.marks ?? []).includes(i + 1);
          return (
            <g key={i}>
              <rect x={x + 6} y={y + 6} width={cw - 12} height={ch - 12} rx={8} fill="#E7E2D6" />
              <text x={x + 16} y={y + 30} fontFamily={SANS} fontSize={20} fill="#888">{i + 1}</text>
              {i < drawn && !bad ? <Check x={x + 26} y={y + 14} size={62} color="#2FA35A" strokeWidth={4} /> : null}
              {bad && (oldMarks.has(i + 1) || t >= markAt(i + 1)) ? (
                <path d={`M${x + 18},${y + 30} q20,-24 30,6 t30,-4 t20,10 M${x + 16},${y + 52} q24,-20 34,8 t34,-6`} stroke={accent} strokeWidth={8}
                  fill="none" strokeLinecap="round" pathLength={1} strokeDasharray={1}
                  strokeDashoffset={oldMarks.has(i + 1) ? 0 : interpolate(t, [markAt(i + 1), markAt(i + 1) + 0.35], [1, 0], clamp)} />
              ) : null}
            </g>
          );
        })}
      </g>
    </g>
  );
};

// ---------- a drawing, a note, a letter, a list, a bill ----------

const KidFigure: React.FC<{x: number; y: number; color: string; phone?: boolean; heart?: boolean}> = ({x, y, color, phone, heart}) => (
  <g stroke="#333" strokeWidth={5} fill="none" strokeLinecap="round">
    {phone ? <rect x={x - 30} y={y - 150} width={60} height={96} rx={10} fill="#222" /> : <circle cx={x} cy={y - 110} r={34} fill="#F6D2B0" />}
    {!phone ? <><circle cx={x - 12} cy={y - 116} r={4} fill="#333" /><circle cx={x + 12} cy={y - 116} r={4} fill="#333" /><path d={`M${x - 14},${y - 98} Q${x},${y - 84} ${x + 14},${y - 98}`} /></> : null}
    <path d={`M${x - 40},${y - 70} L${x + 40},${y - 70} L${x + 30},${y + 10} L${x - 30},${y + 10} Z`} fill={color} />
    <path d={`M${x - 16},${y + 10} L${x - 20},${y + 80} M${x + 16},${y + 10} L${x + 20},${y + 80} M${x - 40},${y - 60} L${x - 74},${y - 20} M${x + 40},${y - 60} L${x + 74},${y - 20}`} />
    {heart ? <path d={`M${x + 70},${y - 150} c-10,-20 -40,-10 -26,14 l26,26 l26,-26 c14,-24 -16,-34 -26,-14 Z`} fill="#E8506A" stroke="none" /> : null}
  </g>
);

export const ObjectInsert: React.FC<{o: NonNullable<Shot['object']>; t: number; dur: number; accent: string}> = ({o, t, dur, accent}) => {
  const pop = interpolate(t, [0, 0.4], [0.92, 1], clamp);
  const k = o.kind;
  const paper = k === 'note' ? '#F7E27A' : '#FBFAF4';
  const lines = o.lines ?? [];
  const shownLines = Math.ceil(interpolate(t, [0.2, Math.max(0.6, dur * 0.6)], [0, lines.length], clamp));
  return (
    <g>
      <rect width={W} height={H} fill="#121317" />
      <g transform={`translate(${W / 2},${H / 2 + (k === 'drawing' ? 40 : 0)}) scale(${pop}) rotate(${k === 'note' ? -3 : -1.5})`}>
        <rect x={-560} y={-360} width={1120} height={720} fill={paper} stroke="#00000022" strokeWidth={6} />
        {k === 'drawing' ? (
          <g>
            <circle cx={-420} cy={-230} r={60} fill="#F6C945" />
            {Array.from({length: 10}, (_, i) => <line key={i} x1={-420 + Math.cos(i * 0.63) * 80} y1={-230 + Math.sin(i * 0.63) * 80} x2={-420 + Math.cos(i * 0.63) * 120} y2={-230 + Math.sin(i * 0.63) * 120} stroke="#F6C945" strokeWidth={8} />)}
            <path d="M260,140 L260,-20 L360,-110 L460,-20 L460,140 Z" fill="#F2A7C0" stroke="#333" strokeWidth={5} />
            <rect x={-560} y={250} width={1120} height={110} fill="#8FD18A" />
            <text x={-80} y={-250} textAnchor="middle" fontFamily={HAND} fontWeight={700} fontSize={72} fill="#D8414A">{o.title ?? ''}</text>
            {(o.who ?? ['me', 'you']).slice(0, 3).map((w, i, all) => (
              <KidFigure key={i} x={-260 + i * 210 - (all.length - 2) * 60} y={160} color={['#E8506A', '#4E8BE3', '#4EBE8B'][i % 3]}
                phone={/phone/i.test(w)} heart={/heart|love/i.test(w)} />
            ))}
          </g>
        ) : (
          <g>
            {o.title ? <text x={0} y={-240} textAnchor="middle" fontFamily={k === 'bill' ? SANS : HAND} fontWeight={700} fontSize={k === 'bill' ? 70 : 78} fill={k === 'bill' ? '#D8414A' : '#2A2A31'}>{o.title}</text> : null}
            {lines.slice(0, shownLines).map((l, i) => (
              <g key={i}>
                {k === 'list' ? <rect x={-420} y={-150 + i * 92} width={44} height={44} fill="none" stroke="#555" strokeWidth={5} /> : null}
                {k === 'list' && i < (o.checked ?? 0) ? <Check x={-424} y={-160 + i * 92} size={56} color="#2FA35A" strokeWidth={5} /> : null}
                <text x={k === 'list' ? -340 : 0} y={-110 + i * 92} textAnchor={k === 'list' ? 'start' : 'middle'} fontFamily={HAND} fontSize={64} fill="#2A2A31">{l}</text>
              </g>
            ))}
            {k === 'bill' ? <g transform="rotate(-14)"><rect x={60} y={120} width={420} height={120} fill="none" stroke="#D8414A" strokeWidth={10} /><text x={270} y={204} textAnchor="middle" fontFamily={SANS} fontWeight={700} fontSize={62} fill="#D8414A">FINAL NOTICE</text></g> : null}
          </g>
        )}
      </g>
      {k === 'drawing' ? (
        // held up in two hands: the arms from below and a thumb over each bottom corner (two balls before)
        <g transform={`translate(${W / 2},${H / 2 + 40}) scale(${pop}) rotate(-1.5)`}>
          {[-1, 1].map((sd) => (
            <g key={sd}>
              <path d={`M${sd * 640},${700} C${sd * 600},${560} ${sd * 520},${460} ${sd * 470},${400}`} stroke={INK} strokeWidth={98} fill="none" strokeLinecap="round" />
              <path d={`M${sd * 640},${700} C${sd * 600},${560} ${sd * 520},${460} ${sd * 470},${400}`} stroke={TONES.cream} strokeWidth={90} fill="none" strokeLinecap="round" />
              <rect x={sd * 470 - 26} y={300} width={52} height={96} rx={26} fill={TONES.cream} stroke={INK} strokeWidth={4} transform={`rotate(${sd * -12},${sd * 470},${348})`} />
            </g>
          ))}
        </g>
      ) : null}
      <rect width={W} height={H} fill={accent} opacity={0} />
    </g>
  );
};

// ---------- a graph drawn into the dark ----------

const SHAPES: Record<string, (x: number) => number> = {
  wave: (x) => Math.exp(-Math.pow((x - 0.45) / 0.16, 2)),
  spikes: (x) => Math.max(0, Math.sin(x * Math.PI * 7)) * (0.4 + x * 0.6) - (Math.sin(x * Math.PI * 7) < 0 ? 0.25 : 0),
  rise: (x) => x * x,
  plateau: (x) => 1 - Math.exp(-x * 5),
  dip_rise: (x) => (x < 0.3 ? -Math.sin((x / 0.3) * Math.PI) * 0.25 : Math.pow((x - 0.3) / 0.7, 1.4)),
  fall: (x) => 1 - x * x,
};

export const GraphInsert: React.FC<{g: NonNullable<Shot['graph']>; t: number; dur: number; accent: string}> = ({g, t, dur, accent}) => {
  const f = SHAPES[g.shape] ?? SHAPES.wave;
  const x0 = 260, x1 = W - 260, y0 = 820, hgt = 480;
  const k = interpolate(t, [0.2, Math.max(0.8, dur * 0.7)], [0, 1], clamp);
  const pts = Array.from({length: 121}, (_, i) => {
    const u = i / 120;
    return [x0 + (x1 - x0) * u, y0 - 60 - f(u) * hgt * 0.8] as [number, number];
  }).filter((_, i) => i / 120 <= k);
  const labels = g.labels ?? [];
  return (
    <g>
      <rect width={W} height={H} fill="#0F1014" />
      <line x1={x0} y1={y0} x2={x1} y2={y0} stroke="rgba(222,226,234,0.6)" strokeWidth={3} />
      <line x1={x0} y1={y0} x2={x0} y2={y0 - hgt - 40} stroke="rgba(222,226,234,0.6)" strokeWidth={3} />
      <path d={pts.map((p, i) => `${i ? 'L' : 'M'}${p[0]},${p[1]}`).join(' ')} stroke={accent} strokeWidth={7} fill="none" strokeLinecap="round" style={{filter: `drop-shadow(0 0 10px ${accent})`}} />
      {labels.map((l, i) => {
        const u = (i + 0.5) / labels.length;
        return k > u ? <text key={i} x={x0 + (x1 - x0) * u} y={y0 - 60 - f(u) * hgt * 0.8 - 30} textAnchor="middle" fontFamily={HAND} fontSize={44} fill="#E8E8E0">{l}</text> : null;
      })}
    </g>
  );
};

// ---------- noise for depth ----------

export const Grain: React.FC<{frame: number}> = ({frame}) => (
  <g opacity={0.05}>
    {Array.from({length: 90}, (_, i) => <rect key={i} x={random(`gx${i}${frame % 6}`) * W} y={random(`gy${i}${frame % 6}`) * H} width={2} height={2} fill="#fff" />)}
  </g>
);
