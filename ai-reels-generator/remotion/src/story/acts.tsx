import React from 'react';
import {Easing, interpolate} from 'remotion';
import {clamp} from '../theme';
import {INK} from './ink';
import type {Action} from './types';

// Stick v2: the line acted out, not stood beside. The user on a 3-minute documentary: "i can feel what is
// telling and what is visualize its not matched ... animation are poor". People kick, juggle, type, write,
// shake hands, film, count money; the objects that carry a story (a goal, a screen with a counter, a board,
// a calendar page, money, a film camera, a crowd) are drawn, with their own words on them; a new place says
// where it is; the cold open hands over to the story with a rewind.

type Pt = [number, number];
export type ActRig = {hip: Pt; neck: Pt; head: Pt; tilt: number; lE: Pt; lH: Pt; rE: Pt; rH: Pt; lK: Pt; lF: Pt; rK: Pt; rF: Pt};

const ease = {...clamp, easing: Easing.inOut(Easing.quad)};
const at = (n: Pt, dx: number, dy: number): Pt => [n[0] + dx, n[1] + dy];

// When the ball meets the foot (kick) and how long each juggle takes; BallFx follows the same clock.
export const KICK_AT = 0.55;
const JUGGLE = 0.62;

// The body doing the action, on top of its pose (facing right, feet at 0, y up negative). Hands are placed
// from the neck so a sitting figure types at its desk as well as a standing one.
export const actRig = (r: ActRig, action: Action, t: number): ActRig => {
  const n = r.neck;
  switch (action) {
    case 'kick': {
      const back = interpolate(t, [0.2, KICK_AT - 0.08], [0, 1], ease);
      const swing = interpolate(t, [KICK_AT - 0.08, KICK_AT + 0.1], [0, 1], ease);
      const settle = interpolate(t, [KICK_AT + 0.35, KICK_AT + 0.8], [0, 1], ease);
      const f = (a: number, b: number, c: number) => a + (b - a) * back + (c - b) * swing + (a - c) * settle;
      return {...r, tilt: -6 * (swing - settle),
        rK: [f(18, -10, 60), f(-84, -92, -150)], rF: [f(28, -70, 120), f(0, -40, -120)],
        lH: at(n, -90, 90 - 40 * swing * (1 - settle)), rH: at(n, 60, 140)};
    }
    case 'juggle': {
      // The right foot lifts each time the ball comes down to it.
      const p = (t % JUGGLE) / JUGGLE;
      const lift = Math.max(0, Math.cos(p * Math.PI * 2)) ** 2;
      return {...r, rK: [30, -84 - 46 * lift], rF: [54, -70 * lift], lH: at(n, -80, 120), rH: at(n, 70, 120)};
    }
    case 'throw': {
      const wind = interpolate(t, [0.1, 0.4], [0, 1], ease);
      const go = interpolate(t, [0.4, 0.6], [0, 1], ease);
      return {...r, tilt: 8 * go, rE: at(n, 10 - 30 * wind + 70 * go, -20 + 10 * go), rH: at(n, -40 - 40 * wind + 190 * go, -70 + 40 * go)};
    }
    case 'type': {
      const k = Math.sin(t * 22);
      return {...r, lE: at(n, 28, 70), lH: at(n, 72, 112 + 4 * k), rE: at(n, 46, 70), rH: at(n, 96, 112 - 4 * k)};
    }
    case 'write': {
      const a = t * 7;
      return {...r, rE: at(n, 52, 66), rH: at(n, 104 + 12 * Math.cos(a), 92 + 6 * Math.sin(a * 2)), lE: at(n, 30, 72), lH: at(n, 70, 116)};
    }
    case 'handshake': {
      const pump = t < 1.4 ? Math.sin(t * 9) * 7 : 0;
      return {...r, rE: at(n, 56, 76), rH: at(n, 118, 100 + pump)};
    }
    case 'count-money': {
      return {...r, lE: at(n, 30, 80), lH: at(n, 62, 118), rE: at(n, 46, 74), rH: at(n, 80, 106 + 5 * Math.sin(t * 10))};
    }
    case 'film':
      return {...r, rE: at(n, 56, 26), rH: at(n, 84, -28), lE: at(n, 34, 30), lH: at(n, 70, -18)};
    case 'phone-call':
      return {...r, rE: at(n, 46, 34), rH: at(n, 34, -62)};
    case 'carry':
      return {...r, lE: at(n, 34, 66), lH: at(n, 84, 116), rE: at(n, 46, 66), rH: at(n, 96, 116)};
    case 'cheer': {
      const up = interpolate(t, [0, 0.25], [0, 1], ease);
      return {...r, lE: at(n, -58 * up, -42 * up + 63 * (1 - up)), lH: at(n, -82 * up - 44 * (1 - up), -118 * up + 130 * (1 - up)),
        rE: at(n, 58 * up, -42 * up + 63 * (1 - up)), rH: at(n, 82 * up + 44 * (1 - up), -118 * up + 130 * (1 - up))};
    }
    case 'nod':
      return {...r, tilt: r.tilt + (t < 1.2 ? 9 * Math.max(0, Math.sin(t * Math.PI * 2 / 0.6)) : 0)};
    case 'watch':
      return {...r, tilt: r.tilt + 5};
    default:
      return r;
  }
};

// A one-time hop for a cheer (pixels up).
export const actLift = (action: Action, t: number) => (action === 'cheer' ? Math.max(0, Math.sin(Math.min(1, t / 0.5) * Math.PI)) * 46 : 0);

// ---------- what the action brings with it, drawn in the figure's own frame (facing right) ----------

const Ball: React.FC<{x: number; y: number; r?: number}> = ({x, y, r = 22}) => (
  <g transform={`translate(${x} ${y})`} stroke={INK} strokeWidth={4}>
    <circle r={r} fill="#F6F1E4" />
    <path d={`M 0 ${-r * 0.42} l ${r * 0.4} ${r * 0.3} l ${-r * 0.15} ${r * 0.46} h ${-r * 0.5} l ${-r * 0.15} ${-r * 0.46} Z`} fill={INK} strokeWidth={2} />
  </g>
);

// target: where the ball goes, in the figure's frame ([x, y]: x ahead of them, y up negative), or null = away.
export const ActFx: React.FC<{action: Action; t: number; d: number; target: Pt | null; hand: Pt; foot: Pt}> = ({action, t, d, target, hand, foot}) => {
  if (action === 'kick') {
    const rest: Pt = [70, -22];
    if (t < KICK_AT) return <Ball x={rest[0]} y={rest[1]} />;
    const goal: Pt = target ?? [900, -520];
    const fly = interpolate(t, [KICK_AT, KICK_AT + 0.45], [0, 1], clamp);
    const arc = (a: Pt, b: Pt, k: number, h: number): Pt => [a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k - h * Math.sin(k * Math.PI)];
    if (fly < 1 || !target) return <Ball x={arc(rest, goal, fly, 90)[0]} y={arc(rest, goal, fly, 90)[1]} />;
    // It hits the target and comes back to the kicker, then stays up: knee, foot, knee...
    const back = interpolate(t, [KICK_AT + 0.45, KICK_AT + 1.05], [0, 1], clamp);
    if (back < 1) {
      const p = arc(goal, [56, -150], back, 120);
      return (
        <g>
          {back < 0.25 ? <Hit x={goal[0]} y={goal[1]} k={back / 0.25} /> : null}
          <Ball x={p[0]} y={p[1]} />
        </g>
      );
    }
    const tt = t - (KICK_AT + 1.05);
    const p = (tt % JUGGLE) / JUGGLE;
    return <Ball x={56} y={-150 - 190 * Math.sin(p * Math.PI)} />;
  }
  if (action === 'juggle') {
    const p = (t % JUGGLE) / JUGGLE;
    return <Ball x={56} y={-96 - 210 * Math.sin(p * Math.PI)} />;
  }
  if (action === 'throw') {
    if (t < 0.5) return <Ball x={hand[0]} y={hand[1] - 10} r={18} />;
    const goal: Pt = target ?? [800, -300];
    const k = interpolate(t, [0.5, 1.1], [0, 1], clamp);
    return <Ball x={hand[0] + (goal[0] - hand[0]) * k} y={hand[1] + (goal[1] - hand[1]) * k - 160 * Math.sin(k * Math.PI)} r={18} />;
  }
  if (action === 'count-money') {
    // Bills peel off one by one from the stack in the hands.
    const n = Math.floor(t / 0.35);
    const p = (t % 0.35) / 0.35;
    return (
      <g transform={`translate(${hand[0]} ${hand[1] - 6})`} stroke={INK} strokeWidth={3}>
        <rect x={-28} y={-16} width={56} height={30} rx={3} fill="#9DB08A" />
        <rect x={-28 + 40 * p} y={-16 - 26 * Math.sin(p * Math.PI)} width={56} height={30} rx={3} fill="#B7C7A2"
          transform={`rotate(${-30 * p} ${-28 + 40 * p} ${-16})`} opacity={n < 40 ? 1 : 0} />
        <text x={0} y={5} fontSize={16} fontWeight={800} textAnchor="middle" fill={INK} stroke="none">$</text>
      </g>
    );
  }
  if (action === 'film') {
    const on = Math.floor(t * 1.2) % 2 === 0;
    return (
      <g transform={`translate(${hand[0]} ${hand[1] - 14})`} stroke={INK} strokeWidth={4}>
        <rect x={-34} y={-24} width={70} height={46} rx={6} fill="#3A3A3D" />
        <path d="M 36 -12 l 26 -14 v 50 l -26 -14 Z" fill="#5B6670" />
        <circle cx={-20} cy={-10} r={6} fill={on ? '#D64535' : '#6E3434'} stroke="none" />
      </g>
    );
  }
  if (action === 'phone-call') {
    return <rect x={hand[0] - 10} y={hand[1] - 40} width={22} height={46} rx={6} fill={INK} stroke={INK} strokeWidth={3} />;
  }
  if (action === 'carry') {
    return <rect x={hand[0] - 70} y={hand[1] - 70} width={110} height={78} rx={4} fill="#B8914A" stroke={INK} strokeWidth={4.5} />;
  }
  if (action === 'type') {
    // An open laptop under the typing hands (a desk's computer, or on the knees).
    return (
      <g transform={`translate(${hand[0] - 6} ${hand[1] + 6})`} stroke={INK} strokeWidth={4}>
        <path d="M -54 0 h 96 l 10 8 h -116 Z" fill="#8C8C88" />
        <path d="M -48 0 l 8 -62 h 78 l -6 62 Z" fill="#3A3A3D" />
        <path d="M -38 -8 l 6 -46 h 62 l -4 46 Z" fill="#DCE6E8" stroke="none" opacity={0.85 + 0.15 * Math.sin(t * 3)} />
      </g>
    );
  }
  if (action === 'write') {
    return null;
  }
  void d;
  void foot;
  return null;
};

const Hit: React.FC<{x: number; y: number; k: number}> = ({x, y, k}) => (
  <g transform={`translate(${x} ${y}) scale(${0.6 + k})`} stroke={INK} strokeWidth={4} opacity={1 - k}>
    {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => {
      const a = (i / 8) * Math.PI * 2;
      return <line key={i} x1={Math.cos(a) * 30} y1={Math.sin(a) * 30} x2={Math.cos(a) * 58} y2={Math.sin(a) * 58} />;
    })}
  </g>
);

// ---------- objects that carry a story, drawn with their own words ----------

export type StageKind = 'goal' | 'football' | 'screen' | 'board' | 'calendar' | 'money' | 'camera' | 'crowd';
const STAGE_WORDS: Record<string, StageKind> = {
  goal: 'goal', goalpost: 'goal', crossbar: 'goal', football: 'football', soccer: 'football', 'soccer-ball': 'football',
  screen: 'screen', monitor: 'screen', tv: 'screen', television: 'screen', computer: 'screen', 'laptop-screen': 'screen',
  board: 'board', whiteboard: 'board', chalkboard: 'board', noticeboard: 'board', signboard: 'board', banner: 'board',
  calendar: 'calendar', date: 'calendar', money: 'money', cash: 'money', bills: 'money', cheque: 'money', check: 'money',
  investment: 'money', camera: 'camera', 'video-camera': 'camera', camcorder: 'camera', crowd: 'crowd', audience: 'crowd',
  fans: 'crowd', people: 'crowd',
};
export const stageKind = (name: string): StageKind | null => {
  const n = name.toLowerCase().trim();
  if (STAGE_WORDS[n]) return STAGE_WORDS[n];
  for (const w of n.split(/[-_\s]+/)) if (STAGE_WORDS[w]) return STAGE_WORDS[w];
  return null;
};
// These stand on the floor whatever the writer said (a goal or a crowd on a little table looked absurd).
export const FLOOR_KINDS = new Set<StageKind>(['goal', 'board', 'crowd', 'camera']);
// The goal's crossbar height above the floor and half its width, for a ball kicked at it.
export const GOAL = {bar: 330, half: 300};

// A number in the words counts up over the first 1.4 s ("1,000,000 views", "$3.5 million", "20,000 a day").
export const countUp = (label: string, t: number) => {
  const m = label.match(/(\d[\d,]*(?:\.\d+)?)/);
  if (!m) return label;
  const raw = m[1];
  const value = parseFloat(raw.replace(/,/g, ''));
  const decimals = (raw.split('.')[1] ?? '').length;
  const k = interpolate(t, [0.15, 1.4], [0, 1], {...clamp, easing: Easing.out(Easing.cubic)});
  const v = value * k;
  const shown = raw.includes(',') ? Math.round(v).toLocaleString('en-US') : v.toFixed(decimals);
  return label.replace(raw, shown);
};

const wrap = (s: string, n: number) => s.split(/\s+/).reduce<string[]>((rows, w) => {
  const last = rows[rows.length - 1];
  if (last !== undefined && (last + ' ' + w).length <= n) rows[rows.length - 1] = last + ' ' + w;
  else if (w) rows.push(w);
  return rows;
}, []).slice(0, 3);

// Standing on y = 0, centred on x = 0. `size` as for icons (120 small, 190 big); `label` = its own words.
export const StageThing: React.FC<{kind: StageKind; label?: string; size: number; t: number; hand: string}> = ({kind, label = '', size, t, hand}) => {
  const e = {stroke: INK, strokeWidth: 5, strokeLinejoin: 'round' as const, strokeLinecap: 'round' as const};
  const k = size / 150;
  const words = countUp(label, t);
  switch (kind) {
    case 'goal':
      return (
        <g {...e} fill="none">
          <path d={`M ${-GOAL.half} 0 V ${-GOAL.bar} H ${GOAL.half} V 0`} stroke="#F4EFE2" strokeWidth={16} />
          <path d={`M ${-GOAL.half} 0 V ${-GOAL.bar} H ${GOAL.half} V 0`} strokeWidth={4} />
          <g stroke="#9C988C" strokeWidth={2}>
            {Array.from({length: 11}, (_, i) => <line key={`v${i}`} x1={-GOAL.half + 40 + i * 52} y1={-GOAL.bar + 18} x2={-GOAL.half + 30 + i * 54} y2={-6} />)}
            {Array.from({length: 6}, (_, i) => <line key={`h${i}`} x1={-GOAL.half + 14} y1={-GOAL.bar + 30 + i * 52} x2={GOAL.half - 14} y2={-GOAL.bar + 30 + i * 52} />)}
          </g>
        </g>
      );
    case 'football':
      return <Ball x={0} y={-22 * k} r={22 * k} />;
    case 'screen': {
      const w = 210 * k;
      const h = 132 * k;
      return (
        <g {...e}>
          <path d={`M ${-14 * k} 0 h ${28 * k} l -6 ${-26 * k} h ${-16 * k} Z`} fill="#3A3A3D" />
          <rect x={-w / 2} y={-26 * k - h} width={w} height={h} rx={8} fill="#2B2D33" />
          <rect x={-w / 2 + 9} y={-26 * k - h + 9} width={w - 18} height={h - 18} rx={4} fill="#F2EEE3" />
          {words ? (
            wrap(words, 12).map((row, i, all) => (
              <text key={i} x={0} y={-26 * k - h / 2 + (i - (all.length - 1) / 2) * 26 * k + 9 * k} fontSize={24 * k} fontWeight={900}
                textAnchor="middle" fill="#1E1B18" stroke="none" fontFamily='"Montserrat", sans-serif'>{row}</text>
            ))
          ) : (
            <g transform={`translate(0 ${-26 * k - h / 2})`}>
              <rect x={-30 * k} y={-21 * k} width={60 * k} height={42 * k} rx={10 * k} fill="#D64535" stroke="none" />
              <path d={`M ${-9 * k} ${-12 * k} l ${22 * k} ${12 * k} l ${-22 * k} ${12 * k} Z`} fill="#fff" stroke="none" />
            </g>
          )}
        </g>
      );
    }
    case 'board': {
      const w = 300 * k;
      const h = 190 * k;
      return (
        <g {...e}>
          <line x1={-w * 0.35} y1={0} x2={-w * 0.3} y2={-h - 60 * k} />
          <line x1={w * 0.35} y1={0} x2={w * 0.3} y2={-h - 60 * k} />
          <rect x={-w / 2} y={-h - 90 * k} width={w} height={h} rx={6} fill="#F4F1E8" />
          {wrap(words, 14).map((row, i, all) => (
            <text key={i} x={0} y={-h / 2 - 90 * k + (i - (all.length - 1) / 2) * 38 * k + 12 * k} fontSize={34 * k}
              textAnchor="middle" fill="#2E4A7A" stroke="none" fontFamily={hand}>{row}</text>
          ))}
        </g>
      );
    }
    case 'calendar': {
      const [top, ...rest] = (label || 'Day').split(/\s+/);
      return (
        <g {...e} transform={`scale(${k})`}>
          <rect x={-70} y={-170} width={140} height={160} rx={8} fill="#F4F1E8" />
          <rect x={-70} y={-170} width={140} height={42} rx={8} fill="#B44A3C" />
          {[-40, 0, 40].map((x) => <line key={x} x1={x} y1={-182} x2={x} y2={-158} strokeWidth={6} />)}
          <text x={0} y={-139} fontSize={24} fontWeight={900} fill="#fff" stroke="none" textAnchor="middle" fontFamily='"Montserrat", sans-serif'>{top.toUpperCase()}</text>
          <text x={0} y={-62} fontSize={54} fill={INK} stroke="none" textAnchor="middle" fontFamily={hand}>{rest.join(' ') || ''}</text>
        </g>
      );
    }
    case 'money': {
      const stacks = [[-60, 0], [0, 0], [60, 0], [-30, -38], [30, -38], [0, -76]];
      return (
        <g {...e} transform={`scale(${k})`}>
          {stacks.map(([x, y], i) => (
            <g key={i} transform={`translate(${x} ${y})`}>
              <rect x={-30} y={-38} width={60} height={38} rx={3} fill="#9DB08A" />
              <line x1={-30} y1={-19} x2={30} y2={-19} stroke="#5E7350" strokeWidth={3} />
            </g>
          ))}
          {words ? (
            <g transform="translate(0 -140)">
              <rect x={-90} y={-26} width={180} height={46} rx={8} fill="#F4F1E8" />
              <text x={0} y={7} fontSize={28} fontWeight={900} textAnchor="middle" fill="#2F4F2A" stroke="none" fontFamily='"Montserrat", sans-serif'>{words}</text>
            </g>
          ) : null}
        </g>
      );
    }
    case 'camera': {
      const on = Math.floor(t * 1.2) % 2 === 0;
      return (
        <g {...e} transform={`scale(${k})`}>
          <path d="M 0 -150 L -60 0 M 0 -150 L 60 0 M 0 -150 L 0 0" />
          <rect x={-56} y={-212} width={100} height={64} rx={8} fill="#3A3A3D" />
          <path d="M 44 -196 l 34 -16 v 64 l -34 -16 Z" fill="#5B6670" />
          <circle cx={-36} cy={-196} r={7} fill={on ? '#D64535' : '#6E3434'} stroke="none" />
        </g>
      );
    }
    case 'crowd': {
      // Rows of small heads and shoulders, swaying a little out of step.
      return (
        <g {...e} strokeWidth={3.5}>
          {Array.from({length: 2}, (_, row) =>
            Array.from({length: 9}, (_, i) => {
              const x = -320 + i * 80 + row * 40;
              const y = -row * 46 + Math.sin(t * 2 + i * 1.7 + row) * 3;
              return (
                <g key={`${row}-${i}`} transform={`translate(${x} ${y})`}>
                  <path d="M -30 0 q 0 -46 30 -46 q 30 0 30 46 Z" fill={['#5B6670', '#9C4A3C', '#6E6F45', '#B8914A', '#34435E'][(i + row) % 5]} />
                  <circle cy={-66} r={22} fill="#F4EFE2" />
                </g>
              );
            }),
          )}
        </g>
      );
    }
  }
};

// ---------- overlays ----------

// Where a new place is ("San Mateo, California · 2005"): a paper tag with marker words, bottom left.
export const PlaceTag: React.FC<{text: string; t: number; vertical: boolean; hand: string}> = ({text, t, vertical, hand}) => {
  const inP = interpolate(t, [0.15, 0.45], [0, 1], {...clamp, easing: Easing.out(Easing.back(1.4))});
  const out = interpolate(t, [2.8, 3.2], [1, 0], clamp);
  if (out <= 0) return null;
  return (
    <div style={{position: 'absolute', left: vertical ? 44 : 64, ...(vertical ? {top: 300} : {bottom: 70}), opacity: out,
      transform: `translateX(${(1 - inP) * -60}px) rotate(-2deg)`, background: '#F4EFE2', border: `4px solid ${INK}`,
      borderRadius: 6, padding: vertical ? '10px 22px' : '12px 26px', boxShadow: '6px 6px 0 rgba(0,0,0,0.25)',
      fontFamily: hand, fontSize: vertical ? 40 : 44, color: INK, maxWidth: vertical ? 900 : 1100, lineHeight: 1.15}}>
      {text}
    </div>
  );
};

// The cold open hands over to the story: a short tape rewind (lines, a greyed picture, ◀◀).
export const Rewind: React.FC<{t: number; vertical: boolean}> = ({t, vertical}) => {
  const k = interpolate(t, [0, 0.15, 0.7, 0.9], [0, 1, 1, 0], clamp);
  if (k <= 0) return null;
  return (
    <div style={{position: 'absolute', inset: 0, pointerEvents: 'none', opacity: k}}>
      <div style={{position: 'absolute', inset: 0, background: 'rgba(30,27,24,0.35)', backdropFilter: 'grayscale(1) blur(1.5px)'}} />
      {Array.from({length: 7}, (_, i) => {
        const y = (((i * 173 + t * 1900) % 1100) / 1100) * 100;
        return <div key={i} style={{position: 'absolute', left: 0, right: 0, top: `${y}%`, height: 6 + (i % 3) * 5, background: 'rgba(244,239,226,0.55)'}} />;
      })}
      <div style={{position: 'absolute', top: vertical ? 220 : 60, right: vertical ? 60 : 90, fontSize: vertical ? 90 : 110, fontWeight: 900,
        color: '#F4EFE2', fontFamily: '"Montserrat", sans-serif', textShadow: '4px 4px 0 #1E1B18'}}>◀◀</div>
    </div>
  );
};
