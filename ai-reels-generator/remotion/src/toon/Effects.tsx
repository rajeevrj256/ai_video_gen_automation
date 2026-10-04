import React from 'react';
import {Easing, interpolate, spring} from 'remotion';
import {clamp} from '../theme';
import {iconFor} from '../long/icon';
import {Mascot, shade} from './Mascot';
import type {Item, ToonPalette, ToonProps} from './types';

// Objects and the actions that happen to them. Every action is driven by `p` (0 before the action's word,
// rising after it) so the picture changes exactly when the narrator says the word.

type XY = {x: number; y: number};
const ease = (t: number) => interpolate(t, [0, 1], [0, 1], {...clamp, easing: Easing.out(Easing.cubic)});

// ---------- objects ----------

const Crate: React.FC<{s: number; open?: number; p: ToonPalette}> = ({s, open = 0, p}) => (
  <svg viewBox="0 0 200 200" width={s} height={s} style={{overflow: 'visible'}}>
    <path d={`M30 70 L100 40 L170 70 L170 160 L100 190 L30 160 Z`} fill="#26272D" stroke="#111" strokeWidth={6} />
    <path d="M30 70 L100 100 L170 70 M100 100 V190" stroke="#3a3b44" strokeWidth={5} fill="none" />
    {Array.from({length: 4}, (_, i) => <rect key={i} x={118} y={112 + i * 16} width={40} height={6} rx={3} fill="#3a3b44" transform="skewY(-22)" />)}
    <g transform={`translate(0 ${-open * 70}) rotate(${-open * 25} 30 70)`}><path d="M24 66 L100 34 L176 66 L100 98 Z" fill="#33343c" stroke="#111" strokeWidth={6} /></g>
    {open < 0.2 ? <text x={64} y={150} fontSize={64} fontWeight={900} fill="#fff" fontFamily="Montserrat">?</text> : null}
    <circle cx={100} cy={30} r={0} fill={p.glow} />
  </svg>
);

const Padlock: React.FC<{s: number; open: number; p: ToonPalette}> = ({s, open, p}) => (
  <svg viewBox="0 0 200 220" width={s} height={s * 1.1} style={{overflow: 'visible'}}>
    <g transform={`translate(${open * 28} ${-open * 34})`}>
      <path d="M58 100 V70 A42 42 0 0 1 142 70 V100" fill="none" stroke="#9aa0a6" strokeWidth={20} strokeLinecap="round" />
    </g>
    <rect x={36} y={96} width={128} height={110} rx={18} fill={p.accent} stroke={shade(p.accent, -0.35)} strokeWidth={6} />
    <circle cx={100} cy={142} r={14} fill={shade(p.accent, -0.5)} /><rect x={94} y={146} width={12} height={30} rx={5} fill={shade(p.accent, -0.5)} />
  </svg>
);

const Server: React.FC<{s: number; p: ToonPalette; frame: number}> = ({s, p, frame}) => (
  <svg viewBox="0 0 160 240" width={s * 0.67} height={s} style={{overflow: 'visible'}}>
    <rect x={10} y={6} width={140} height={228} rx={10} fill="#2a3550" stroke="#141a2a" strokeWidth={6} />
    {Array.from({length: 6}, (_, i) => <g key={i}>
      <rect x={24} y={22 + i * 35} width={112} height={24} rx={5} fill="#1b2337" />
      <circle cx={40} cy={34 + i * 35} r={5} fill={(frame + i * 7) % 24 < 12 ? p.glow : '#335'} />
      <rect x={56} y={31 + i * 35} width={66} height={6} rx={3} fill="#3c4a6b" />
    </g>)}
  </svg>
);

const ITEM_COLORS = ['#FF9F1C', '#2F9BFF', '#2FB36D', '#E5484D', '#8E5CF7', '#14B8A6', '#F15BB5'];

export const ItemView: React.FC<{item: Item; s: number; p: ToonPalette; frame: number; color?: string; k?: number}> = ({item, s, p, frame, color, k = 0}) => {
  const name = item.icon.toLowerCase();
  let body: React.ReactNode;
  if (item.badge) {
    body = (
      <div style={{background: p.paper, color: '#15151c', borderRadius: 22, padding: `${s * 0.12}px ${s * 0.22}px`, fontWeight: 900,
        fontSize: s * 0.26, boxShadow: '0 10px 0 rgba(0,0,0,0.18)', border: `6px solid ${shade(p.paper, -0.2)}`, whiteSpace: 'nowrap'}}>
        {item.label || item.icon}
      </div>
    );
  } else if (/crate|mystery|pandora|box-question/.test(name)) body = <Crate s={s} p={p} />;
  else if (/padlock|^lock$|locked/.test(name)) body = <Padlock s={s} open={0} p={p} />;
  else if (/server|data-center|datacenter/.test(name)) body = <Server s={s} p={p} frame={frame} />;
  else {
    const Icon = iconFor(item.icon);
    const c = color ?? (k === 0 ? p.accent : ITEM_COLORS[(k + item.icon.length) % ITEM_COLORS.length]);
    body = (
      <div style={{width: s, height: s, borderRadius: '50%', background: c, border: `${s * 0.05}px solid ${shade(c, -0.3)}`,
        display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: `0 ${s * 0.06}px 0 ${shade(c, -0.45)}`}}>
        <Icon size={s * 0.56} color="#fff" strokeWidth={2.4} />
      </div>
    );
  }
  return (
    <div style={{display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12}}>
      {body}
      {item.label && !item.badge ? (
        <div style={{background: '#fff', color: '#15151c', fontWeight: 900, fontSize: Math.max(26, s * 0.17), padding: '6px 18px',
          borderRadius: 12, textTransform: 'uppercase', whiteSpace: 'nowrap', boxShadow: '0 6px 0 rgba(0,0,0,0.18)'}}>{item.label}</div>
      ) : null}
    </div>
  );
};

// ---------- actions ----------

const Crack: React.FC<{at: XY; p: number; color: string; seed: number}> = ({at, p, color, seed}) => {
  const arms = 7;
  return (
    <svg viewBox="0 0 1920 1080" style={{position: 'absolute', inset: 0}}>
      {Array.from({length: arms}, (_, i) => {
        const ang = (i / arms) * Math.PI * 2 + seed;
        let x = at.x, y = at.y, d = `M${x} ${y}`;
        const len = 230 * ease(p);
        for (let k = 1; k <= 5; k++) {
          const a = ang + Math.sin(k * 2.3 + i) * 0.5;
          x += Math.cos(a) * len / 5;
          y += Math.sin(a) * len / 5;
          d += ` L${x} ${y}`;
        }
        return <path key={i} d={d} stroke={color} strokeWidth={14 - i} fill="none" strokeLinecap="round" strokeLinejoin="round" />;
      })}
    </svg>
  );
};

const Bolt: React.FC<{a: XY; b: XY; frame: number; color: string}> = ({a, b, frame, color}) => {
  const pts = Array.from({length: 9}, (_, i) => {
    const t = i / 8, j = i === 0 || i === 8 ? 0 : Math.sin(frame * 1.7 + i * 3) * 40;
    return `${a.x + (b.x - a.x) * t + j * 0.3} ${a.y + (b.y - a.y) * t + j}`;
  });
  return (
    <svg viewBox="0 0 1920 1080" style={{position: 'absolute', inset: 0}}>
      <polyline points={pts.join(' ')} fill="none" stroke={color} strokeWidth={16} opacity={0.35} strokeLinejoin="round" />
      <polyline points={pts.join(' ')} fill="none" stroke="#fff" strokeWidth={6} strokeLinejoin="round" />
    </svg>
  );
};

const Flame: React.FC<{x: number; y: number; s: number; frame: number}> = ({x, y, s, frame}) => {
  const f = 1 + Math.sin(frame / 2 + x) * 0.08;
  return (
    <svg viewBox="0 0 100 140" width={s} height={s * 1.4} style={{position: 'absolute', left: x - s / 2, top: y - s * 1.2, transform: `scaleY(${f})`, transformOrigin: 'bottom'}}>
      <path d="M50 4 C70 40 96 56 92 92 C88 124 64 138 50 138 C30 138 8 124 8 92 C8 66 30 56 34 30 C42 48 46 56 50 4 Z" fill="#FF7A1A" />
      <path d="M50 52 C62 76 76 86 72 106 C68 124 58 130 50 130 C40 130 28 122 28 104 C28 88 40 82 44 66 C48 76 48 80 50 52 Z" fill="#FFD23F" />
    </svg>
  );
};

const Toggle: React.FC<{p: number; on: boolean; pal: ToonPalette; label?: string | null}> = ({p, on, pal, label}) => {
  const t = ease(p);
  const knob = on ? interpolate(t, [0, 1], [0, 1]) : interpolate(t, [0, 1], [1, 0]);
  const bg = interpolate(knob, [0, 1], [0, 1]) > 0.5 ? '#2FB36D' : '#4a4a52';
  return (
    <div style={{display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 30}}>
      <div style={{width: 560, height: 240, borderRadius: 120, background: bg, border: '14px solid #2a2a30', position: 'relative', boxShadow: '0 16px 0 rgba(0,0,0,0.25)'}}>
        <div style={{position: 'absolute', top: 14, left: 14 + knob * 304, width: 184, height: 184, borderRadius: '50%', background: 'radial-gradient(circle at 35% 30%, #fff, #cfd3da)', boxShadow: '0 8px 0 rgba(0,0,0,0.25)'}} />
        <div style={{position: 'absolute', top: 0, bottom: 0, left: knob > 0.5 ? 40 : 250, display: 'flex', alignItems: 'center', fontSize: 96, fontWeight: 900, color: '#fff'}}>{knob > 0.5 ? 'ON' : 'OFF'}</div>
      </div>
      {label ? <div style={{fontSize: 50, fontWeight: 900, color: '#15151c', textTransform: 'uppercase', textAlign: 'center', maxWidth: 1100, background: pal.paper, padding: '10px 26px', borderRadius: 14}}>{label}</div> : null}
    </div>
  );
};

const Gauge: React.FC<{p: number; up: boolean; pal: ToonPalette; label?: string | null; frame: number}> = ({p, up, pal, label, frame}) => {
  const t = ease(p);
  const jitter = t >= 1 ? Math.sin(frame / 3) * 2 : 0;
  const ang = (up ? interpolate(t, [0, 1], [-70, 72]) : interpolate(t, [0, 1], [70, -72])) + jitter;
  return (
    <svg viewBox="0 0 400 300" width={520} height={390} style={{overflow: 'visible'}}>
      <circle cx={200} cy={210} r={180} fill={pal.paper} stroke="#2a2a30" strokeWidth={14} />
      <path d="M50 210 A150 150 0 0 1 120 85" stroke="#2FB36D" strokeWidth={34} fill="none" />
      <path d="M120 85 A150 150 0 0 1 280 85" stroke="#F2B705" strokeWidth={34} fill="none" />
      <path d="M280 85 A150 150 0 0 1 350 210" stroke="#E5484D" strokeWidth={34} fill="none" />
      <g transform={`rotate(${ang} 200 210)`}><path d="M192 210 L200 72 L208 210 Z" fill="#2a2a30" /></g>
      <circle cx={200} cy={210} r={20} fill="#2a2a30" />
      {label ? <text x={200} y={270} textAnchor="middle" fontSize={34} fontWeight={900} fill="#2a2a30" fontFamily="Montserrat">{label.toUpperCase()}</text> : null}
    </svg>
  );
};

const Hand: React.FC<{x: number; y: number}> = ({x, y}) => (
  <svg viewBox="0 0 300 200" width={420} height={280} style={{position: 'absolute', left: x - 210, top: y - 230}}>
    <rect x={110} y={-200} width={80} height={240} fill="#2c2f3a" />
    <path d="M60 60 Q60 20 110 24 H200 Q250 24 250 70 V120 Q250 150 220 150 H80 Q50 150 50 120 Z" fill="#F0C9A0" stroke="#d4a77c" strokeWidth={5} />
    {[80, 120, 160, 200].map((fx) => <rect key={fx} x={fx - 14} y={120} width={28} height={58} rx={14} fill="#F0C9A0" stroke="#d4a77c" strokeWidth={4} />)}
  </svg>
);

const Bricks: React.FC<{p: number; x: number}> = ({p, x}) => (
  <div style={{position: 'absolute', left: x - 200, top: 140, width: 400, height: 800}}>
    {Array.from({length: 40}, (_, i) => {
      const r = Math.floor(i / 4), c = i % 4, fly = ease(p);
      const dx = (c - 1.5) * 260 * fly + Math.sin(i) * 80 * fly, dy = -Math.cos(i) * 200 * fly + fly * fly * 300;
      return <div key={i} style={{position: 'absolute', left: c * 100 + (r % 2) * 50 - 25, top: r * 80, width: 96, height: 74, background: '#B5562F',
        border: '5px solid #7d3518', borderRadius: 6, transform: `translate(${dx}px, ${dy}px) rotate(${fly * (i * 37 % 180)}deg)`, opacity: 1 - fly * 0.6}} />;
    })}
  </div>
);

const Bars: React.FC<{values: number[]; items: Item[]; p: number; pal: ToonPalette}> = ({values, items, p, pal}) => {
  const max = Math.max(...values, 1);
  const colors = [pal.accent, pal.glow, pal.hot, '#2FB36D', '#9b5de5'];
  return (
    <div style={{display: 'flex', alignItems: 'flex-end', gap: 60, height: 560}}>
      {values.slice(0, 5).map((v, i) => {
        const h = (v / max) * 480 * ease(Math.min(1, Math.max(0, p * 1.6 - i * 0.15)));
        return (
          <div key={i} style={{display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 14}}>
            <div style={{fontSize: 46, fontWeight: 900, color: '#fff', textShadow: '0 4px 0 rgba(0,0,0,0.35)'}}>{h > 10 ? v : ''}</div>
            <div style={{width: 150, height: h, background: colors[i % colors.length], borderRadius: '18px 18px 0 0', border: '6px solid rgba(0,0,0,0.25)'}} />
            <div style={{fontSize: 30, fontWeight: 900, color: '#15151c', background: pal.paper, borderRadius: 10, padding: '4px 12px', textTransform: 'uppercase'}}>{items[i]?.label ?? ''}</div>
          </div>
        );
      })}
    </div>
  );
};

const Trend: React.FC<{p: number; up: boolean; pal: ToonPalette}> = ({p, up, pal}) => {
  const pts = up ? [[0, 400], [180, 300], [320, 360], [480, 200], [640, 240], [820, 40]] : [[0, 40], [180, 160], [320, 110], [480, 280], [640, 230], [820, 420]];
  const len = ease(p);
  const n = Math.max(2, Math.ceil(len * pts.length));
  const shown = pts.slice(0, n);
  const [lx, ly] = shown[shown.length - 1];
  return (
    <svg viewBox="-40 -60 920 520" width={1100} height={620} style={{overflow: 'visible'}}>
      <polyline points={shown.map((q) => q.join(' ')).join(' ')} fill="none" stroke={up ? '#2FB36D' : pal.hot} strokeWidth={34} strokeLinejoin="round" strokeLinecap="round" />
      <g transform={`translate(${lx} ${ly}) rotate(${up ? -35 : 35})`}><path d="M-10 -46 L60 0 L-10 46 Z" fill={up ? '#2FB36D' : pal.hot} /></g>
    </svg>
  );
};

// Where objects go: the free places, away from the people and the mascot (x centres in `taken`), the
// ones nearest the middle first. A shot with no one in it uses the middle itself.
export const slots = (n: number, taken: number[]): XY[] => {
  const xs = [960, 620, 1300, 330, 1590];
  const free = xs.filter((x) => taken.every((t) => Math.abs(t - x) > 380));
  // Nowhere fully free: the place farthest from everyone.
  const far = [...xs].sort((a, b) => Math.min(...taken.map((t) => Math.abs(t - b))) - Math.min(...taken.map((t) => Math.abs(t - a))))[0];
  const pool = free.length ? free : [far];
  const ordered = [...pool].sort((a, b) => Math.abs(a - 960) - Math.abs(b - 960));
  if (n <= ordered.length) return ordered.slice(0, n).sort((a, b) => a - b).map((x) => ({x, y: taken.length ? 470 : 520}));
  // More objects than free places: stack them in two rows in the free places.
  return Array.from({length: n}, (_, i) => ({x: ordered[i % ordered.length], y: 330 + Math.floor(i / ordered.length) * 300}));
};

export const ActionLayer: React.FC<{
  action: string; p: number; frame: number; fps: number; pal: ToonPalette; items: Item[]; spots: XY[]; mascotAt: XY | null;
  mascot: ToonProps['mascot']; values?: number[]; seed: number;
}> = ({action, p, frame, fps, pal, items, spots, mascotAt, mascot, values, seed}) => {
  if (p <= 0 && !['strings', 'strings-burn', 'toggle-off', 'toggle-on', 'gauge-up', 'gauge-down', 'versus', 'fly-out', 'unlock', 'lock', 'burst', 'cage'].includes(action)) return null;
  const centre: XY = {x: 960, y: 520};
  const target = spots[0] ?? centre;
  const mc = mascot;
  const mini = (k: number, mood: 'happy' | 'smug' | 'evil' | 'wink' = 'happy', tint: 'normal' | 'grey' = 'normal', s = 150) => (
    <Mascot shape={mc.shape} color={mc.color} accessory={mc.accessory} mood={mood} tint={tint} frame={frame + k * 7} size={s} />
  );
  switch (action) {
    case 'crack': {
      const at = mascotAt ? {x: mascotAt.x - 380, y: mascotAt.y - 40} : target;
      return <>
        <Crack at={at} p={p} color={pal.glow} seed={seed} />
        {p > 0.4 && mascotAt ? <Bolt a={at} b={mascotAt} frame={frame} color={pal.glow} /> : null}
      </>;
    }
    case 'clone':
    case 'flood': {
      const n = action === 'flood' ? 46 : 8;
      return <>{Array.from({length: n}, (_, i) => {
        const delay = i * (action === 'flood' ? 0.02 : 0.08);
        const s = spring({frame: Math.round((p - delay) * fps * 2), fps, config: {damping: 11}});
        const x = action === 'flood' ? (i % 9) * 230 - 40 + (Math.floor(i / 9) % 2) * 110 : 960 + Math.cos(i * 0.785 + seed) * 560;
        const y = action === 'flood' ? 1150 - Math.floor(i / 9) * 210 - interpolate(p, [0, 1], [400, 0], clamp) : 520 + Math.sin(i * 0.785 + seed) * 300;
        return <div key={i} style={{position: 'absolute', left: x - 90, top: y - 90, transform: `scale(${s})`}}>{mini(i, action === 'flood' ? 'smug' : 'happy', action === 'clone' ? 'grey' : 'normal', action === 'flood' ? 230 : 170)}</div>;
      })}</>;
    }
    case 'unlock':
    case 'lock': {
      const open = action === 'unlock' ? ease(p) : 1 - ease(p);
      return <div style={{position: 'absolute', left: target.x - 130, top: target.y - 330}}><Padlock s={260} open={open} p={pal} /></div>;
    }
    case 'toggle-off':
    case 'toggle-on':
      return <div style={{position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center'}}><Toggle p={p} on={action === 'toggle-on'} pal={pal} label={items[0]?.label} /></div>;
    case 'gauge-up':
    case 'gauge-down':
      return <div style={{position: 'absolute', left: target.x - 260, top: 260}}><Gauge p={p} up={action === 'gauge-up'} pal={pal} label={items[0]?.label} frame={frame} /></div>;
    case 'strings':
    case 'strings-burn': {
      const hand = {x: 960, y: 250};
      const burn = action === 'strings-burn' ? ease(p) : 0;
      return <>
        <svg viewBox="0 0 1920 1080" style={{position: 'absolute', inset: 0}}>
          {spots.map((s, i) => <line key={i} x1={hand.x - 60 + i * 40} y1={hand.y} x2={s.x} y2={s.y - 140 + burn * 400}
            stroke="#d9c19a" strokeWidth={6} strokeDasharray={burn > 0.6 ? '20 40' : undefined} opacity={1 - burn * 0.8} />)}
        </svg>
        <Hand x={hand.x} y={hand.y} />
        {burn > 0 ? spots.map((s, i) => <Flame key={i} x={(hand.x - 60 + i * 40 + s.x) / 2} y={(hand.y + s.y - 140) / 2 + 40} s={70 + burn * 30} frame={frame + i * 5} />) : null}
      </>;
    }
    case 'burst':
      return <Bricks p={p} x={mascotAt?.x ?? 960} />;
    case 'fly-out': {
      return <>
        <div style={{position: 'absolute', left: 960 - 170, top: 560}}><Crate s={340} open={ease(Math.min(1, p * 3))} p={pal} /></div>
        {p > 0.1 ? Array.from({length: 9}, (_, i) => {
          const t = ease(Math.min(1, (p - 0.1 - i * 0.04) * 2));
          const x = 960 + Math.cos(-Math.PI / 2 + (i - 4) * 0.3) * 700 * t, y = 600 - Math.sin(Math.PI / 2 + (i - 4) * 0.25) * 520 * t;
          return t > 0 ? <div key={i} style={{position: 'absolute', left: x - 50, top: y - 50, transform: `scale(${0.4 + t * 0.6}) rotate(${(i - 4) * 12 * t}deg)`}}>{mini(i, 'wink', 'normal', 110)}</div> : null;
        }) : null}
      </>;
    }
    case 'crosshair': {
      const s = interpolate(p, [0, 0.6], [520, 300], clamp), rot = interpolate(p, [0, 1], [90, 0], clamp);
      return <svg viewBox="-150 -150 300 300" width={s} height={s} style={{position: 'absolute', left: target.x - s / 2, top: target.y - 60 - s / 2, transform: `rotate(${rot}deg)`}}>
        <circle r={110} fill="rgba(229,72,77,0.25)" stroke={pal.hot} strokeWidth={14} /><circle r={60} fill="none" stroke={pal.hot} strokeWidth={10} />
        {[0, 90, 180, 270].map((a) => <line key={a} x1={0} y1={-140} x2={0} y2={-70} stroke={pal.hot} strokeWidth={12} transform={`rotate(${a})`} />)}
      </svg>;
    }
    case 'sparks':
      return <>{spots.slice(0, 3).map((s, i) => <Bolt key={i} a={{x: s.x - 220, y: s.y - 260}} b={{x: s.x + 40, y: s.y - 40}} frame={frame + i * 9} color={pal.glow} />)}</>;
    case 'cage': {
      const at = mascotAt ?? target, drop = ease(p);
      return <div style={{position: 'absolute', left: at.x - 230, top: at.y - 330 - (1 - drop) * 900, width: 460, height: 560}}>
        {Array.from({length: 7}, (_, i) => <div key={i} style={{position: 'absolute', left: i * 72, top: 0, width: 26, height: 560, borderRadius: 13, background: 'linear-gradient(90deg,#8e949c,#d5d9de,#8e949c)'}} />)}
        <div style={{position: 'absolute', left: -10, top: -10, width: 480, height: 30, borderRadius: 12, background: '#7a8088'}} />
      </div>;
    }
    case 'connect': {
      const ends = spots.length > 1 ? spots : mascotAt ? [mascotAt, target] : spots;
      return <svg viewBox="0 0 1920 1080" style={{position: 'absolute', inset: 0}}>
        {ends.slice(1).map((b, i) => {
          const a = ends[0];
          const k = ((frame / 30 + i * 0.3) % 1);
          return <g key={i}>
            <line x1={a.x} y1={a.y - 60} x2={a.x + (b.x - a.x) * ease(p)} y2={a.y - 60 + (b.y - a.y) * ease(p)} stroke="#fff" strokeWidth={8} strokeDasharray="26 22" />
            {p > 0.9 ? <rect x={a.x + (b.x - a.x) * k - 26} y={a.y - 60 + (b.y - a.y) * k - 18} width={52} height={36} rx={8} fill={pal.paper} stroke={pal.accent} strokeWidth={5} /> : null}
          </g>;
        })}
      </svg>;
    }
    case 'orbit': {
      const c = mascotAt ?? centre;
      return <>{items.map((it, i) => {
        const a = frame / 30 + (i / Math.max(1, items.length)) * Math.PI * 2;
        return <div key={i} style={{position: 'absolute', left: c.x + Math.cos(a) * 380 * ease(p) - 70, top: c.y - 40 + Math.sin(a) * 200 * ease(p) - 70}}><ItemView item={{...it, label: null}} s={140} p={pal} frame={frame} /></div>;
      })}</>;
    }
    case 'rain': {
      const it = items[0] ?? {icon: 'coins'};
      return <>{Array.from({length: 18}, (_, i) => {
        const x = (i * 113 + seed * 50) % 1920, y = ((frame * (6 + (i % 4))) + i * 140) % 1300 - 200;
        return <div key={i} style={{position: 'absolute', left: x, top: y, transform: `rotate(${(frame + i * 20) % 360}deg)`, opacity: Math.min(1, p * 3)}}><ItemView item={{...it, label: null}} s={110} p={pal} frame={frame} /></div>;
      })}</>;
    }
    case 'arrow-up':
    case 'arrow-down':
      return <div style={{position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center'}}><Trend p={p} up={action === 'arrow-up'} pal={pal} /></div>;
    case 'bars':
      return <div style={{position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', paddingTop: 60}}><Bars values={values?.length ? values : [3, 5, 8]} items={items} p={p} pal={pal} /></div>;
    case 'versus': {
      const s = ease(Math.min(1, p * 2 + 0.5));
      return <>
        <div style={{position: 'absolute', left: 0, top: 0, width: 960, height: 1080, background: shade(pal.accent, -0.2), opacity: 0.35}} />
        {items.slice(0, 2).map((it, i) => <div key={i} style={{position: 'absolute', left: (i ? 1440 : 480) - 170, top: 330}}><ItemView item={it} s={340} p={pal} frame={frame} k={i * 3} /></div>)}
        <div style={{position: 'absolute', left: 960 - 110, top: 430, width: 220, height: 220, borderRadius: '50%', background: pal.hot, color: '#fff', fontSize: 110, fontWeight: 900,
          display: 'flex', alignItems: 'center', justifyContent: 'center', transform: `scale(${s}) rotate(${(1 - s) * 90}deg)`, border: '10px solid #fff'}}>VS</div>
      </>;
    }
    default:
      return null;
  }
};
