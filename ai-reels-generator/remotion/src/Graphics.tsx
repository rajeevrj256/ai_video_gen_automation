import React from 'react';
import {Easing, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {Layer} from './Layer';
import type {Graphic, Point} from './types';
import {COLORS, FONT, OUTLINE, clamp, exitProgress, fitSize, float, formatNumber, parseNumber, payoffPop, shineSweep} from './theme';

// One animated graphic per scene, chosen by Claude in the script (type + data).
// Everything enters with a spring, floats gently while it holds, and drifts up and
// fades out before the scene ends.

type Props = {g: Graphic; frames: number};

export const GraphicView: React.FC<Props> = ({g, frames}) => {
  const frame = useCurrentFrame();
  const exit = exitProgress(frame, frames, 8);
  const body =
    g.type === 'chart' && g.points.length >= 2 ? (
      <Chart g={g} />
    ) : g.type === 'compare' && g.points.length >= 2 ? (
      <Compare g={g} />
    ) : g.type === 'keyword' ? (
      <Keyword g={g} />
    ) : (
      <Stat g={g} />
    );
  return (
    <Layer
      name={`graphic-${g.type}`}
      style={{opacity: 1 - exit, transform: `translateY(${-40 * exit}px) scale(${1 - 0.05 * exit})`, fontFamily: FONT}}
    >
      {body}
    </Layer>
  );
};

const useEnter = (delay = 0) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  return spring({frame: frame - delay, fps, config: {damping: 14, mass: 0.7}});
};

const Card: React.FC<{children: React.ReactNode; top?: string}> = ({children, top = '19%'}) => {
  const frame = useCurrentFrame();
  const enter = useEnter();
  const x = shineSweep(frame, 120);
  return (
    <div
      style={{
        position: 'absolute',
        top,
        left: '6%',
        right: '6%',
        padding: '44px 44px 40px',
        borderRadius: 40,
        background: COLORS.card,
        border: '2px solid rgba(255,255,255,0.10)',
        boxShadow: '0 30px 80px rgba(0,0,0,0.45)',
        transform: `translateY(${(1 - enter) * 80 + float(frame, 5)}px) scale(${0.85 + 0.15 * enter})`,
        opacity: Math.min(1, enter),
        color: COLORS.text,
        textAlign: 'center',
        overflow: 'hidden',
      }}
    >
      {children}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          pointerEvents: 'none',
          background: `linear-gradient(105deg, transparent ${x - 18}%, rgba(255,255,255,0.07) ${x}%, transparent ${x + 18}%)`,
        }}
      />
    </div>
  );
};

const Label: React.FC<{text: string; size?: number}> = ({text, size = 44}) => (
  <div style={{fontSize: size, fontWeight: 800, lineHeight: 1.2, opacity: 0.92}}>{text}</div>
);

// Big number that counts up from zero, with an underline that draws in.
const Stat: React.FC<{g: Graphic}> = ({g}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = interpolate(frame, [4, 4 + fps * 0.9], [0, 1], {...clamp, easing: Easing.out(Easing.cubic)});
  const parsed = parseNumber(g.headline);
  // Only count up when there are enough steps to look like counting. "1 billion" would
  // sit on "0 billion" for a third of a second, which is a wrong figure on screen.
  const counts = parsed !== null && Math.abs(parsed.value) * 10 ** parsed.decimals >= 20;
  const text = counts ? formatNumber(parsed.value * t, parsed) : g.headline;
  const line = interpolate(frame, [10, 26], [0, 1], {...clamp, easing: Easing.out(Easing.quad)});
  const landed = Math.round(4 + fps * 0.9);
  const glow = interpolate(frame, [landed, landed + 6, landed + 24], [0, 1, 0.35], clamp);
  return (
    <Card>
      <div
        style={{
          fontSize: fitSize(g.headline, 190, 860),
          fontWeight: 900,
          color: COLORS.accent,
          lineHeight: 1.05,
          fontVariantNumeric: 'tabular-nums',
          transform: `scale(${payoffPop(frame, fps, landed)})`,
          textShadow: `0 8px 30px rgba(0,0,0,0.5), 0 0 ${40 * glow}px rgba(255,214,10,${0.8 * glow})`,
        }}
      >
        {text}
      </div>
      <div style={{height: 10, width: `${line * 60}%`, background: COLORS.accent, borderRadius: 5, margin: '18px auto 22px'}} />
      <Label text={g.label} />
    </Card>
  );
};

// Line chart that draws itself left to right; green if it ends higher, red if lower.
const Chart: React.FC<{g: Graphic}> = ({g}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const pts = g.points;
  const W = 880;
  const H = 440;
  const pad = 36;
  const values = pts.map((p) => p.value);
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const span = hi - lo || Math.abs(hi) || 1;
  const yMin = lo - span * 0.15;
  const yMax = hi + span * 0.15;
  const xy = pts.map((p, i) => [
    pad + (i * (W - 2 * pad)) / (pts.length - 1),
    pad + (1 - (p.value - yMin) / (yMax - yMin)) * (H - 2 * pad),
  ]);
  const seg = xy.slice(1).map((p, i) => Math.hypot(p[0] - xy[i][0], p[1] - xy[i][1]));
  const total = seg.reduce((a, b) => a + b, 0);
  const draw = interpolate(frame, [8, 8 + fps * 1.2], [0, 1], {...clamp, easing: Easing.inOut(Easing.cubic)});
  const up = values[values.length - 1] >= values[0];
  const color = up ? COLORS.up : COLORS.down;
  const d = xy.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ');
  const area = `${d} L${xy[xy.length - 1][0]},${H} L${xy[0][0]},${H} Z`;

  // Head of the line: where the drawing currently is.
  let remaining = draw * total;
  let head = xy[0];
  let reached = 0;
  for (let i = 0; i < seg.length; i++) {
    if (remaining >= seg[i]) {
      remaining -= seg[i];
      head = xy[i + 1];
      reached = i + 1;
      continue;
    }
    const f = seg[i] ? remaining / seg[i] : 0;
    head = [xy[i][0] + (xy[i + 1][0] - xy[i][0]) * f, xy[i][1] + (xy[i + 1][1] - xy[i][1]) * f];
    break;
  }
  const showAllLabels = pts.length <= 5;
  const headlineIn = useEnter(Math.round(8 + fps * 1.2));

  return (
    <Card top="17%">
      <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 20, marginBottom: 18}}>
        <div style={{textAlign: 'left', flex: 1}}>
          <Label text={g.label} size={40} />
        </div>
        <div
          style={{
            fontSize: fitSize(g.headline, 84, 360),
            fontWeight: 900,
            color,
            transform: `scale(${0.6 + 0.4 * headlineIn})`,
            opacity: headlineIn,
          }}
        >
          {g.headline}
        </div>
      </div>
      <svg width="100%" viewBox={`0 0 ${W} ${H + 60}`} style={{overflow: 'visible'}}>
        <defs>
          <linearGradient id="fill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.45} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
          <clipPath id="reveal">
            <rect x={0} y={0} width={head[0]} height={H} />
          </clipPath>
        </defs>
        {[0.25, 0.5, 0.75].map((f) => (
          <line key={f} x1={pad} x2={W - pad} y1={H * f} y2={H * f} stroke="rgba(255,255,255,0.10)" strokeWidth={2} />
        ))}
        <path d={area} fill="url(#fill)" clipPath="url(#reveal)" />
        <path
          d={d}
          fill="none"
          stroke={color}
          strokeWidth={10}
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeDasharray={total}
          strokeDashoffset={total * (1 - draw)}
        />
        {xy.map((p, i) =>
          i <= reached ? <circle key={i} cx={p[0]} cy={p[1]} r={9} fill="#fff" stroke={color} strokeWidth={5} /> : null,
        )}
        <circle cx={head[0]} cy={head[1]} r={16 + 4 * Math.sin(frame / 3)} fill={color} opacity={0.35} />
        {pts.map((p: Point, i) => {
          const visible = i <= reached && (showAllLabels || i === 0 || i === pts.length - 1);
          if (!visible) return null;
          const [x, y] = xy[i];
          return (
            <g key={`l${i}`}>
              <text x={x} y={y - 26} fill="#fff" fontSize={34} fontWeight={800} textAnchor="middle" fontFamily={FONT}>
                {p.display}
              </text>
              <text x={x} y={H + 46} fill="rgba(255,255,255,0.75)" fontSize={30} fontWeight={800} textAnchor="middle" fontFamily={FONT}>
                {p.label}
              </text>
            </g>
          );
        })}
      </svg>
    </Card>
  );
};

// Before -> after with an arrow; the "after" side is coloured by direction.
const Compare: React.FC<{g: Graphic}> = ({g}) => {
  const frame = useCurrentFrame();
  const [a, b] = g.points;
  const left = useEnter(2);
  const right = useEnter(14);
  const arrow = interpolate(frame, [8, 18], [0, 1], clamp);
  const color = b.value >= a.value ? COLORS.up : COLORS.down;
  const Side: React.FC<{p: Point; enter: number; tint: string}> = ({p, enter, tint}) => (
    <div style={{flex: 1, transform: `scale(${0.7 + 0.3 * enter})`, opacity: enter}}>
      <div style={{fontSize: 34, fontWeight: 800, opacity: 0.75, marginBottom: 8}}>{p.label}</div>
      <div style={{fontSize: fitSize(p.display, 96, 340), fontWeight: 900, color: tint}}>{p.display}</div>
    </div>
  );
  return (
    <Card>
      <Label text={g.label} size={42} />
      <div style={{display: 'flex', alignItems: 'center', gap: 10, marginTop: 26}}>
        <Side p={a} enter={left} tint="#fff" />
        <svg width={110} height={70} viewBox="0 0 110 70" style={{opacity: arrow}}>
          <path
            d="M6 35 H86 M62 12 L92 35 L62 58"
            fill="none"
            stroke={COLORS.accent}
            strokeWidth={10}
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeDasharray={200}
            strokeDashoffset={200 * (1 - arrow)}
          />
        </svg>
        <Side p={b} enter={right} tint={color} />
      </div>
      {g.headline ? (
        <div
          style={{
            display: 'inline-block',
            marginTop: 26,
            padding: '10px 28px',
            borderRadius: 999,
            background: color,
            color: COLORS.ink,
            fontSize: 44,
            fontWeight: 900,
            transform: `scale(${right})`,
          }}
        >
          {g.headline}
        </div>
      ) : null}
    </Card>
  );
};

// A word or short phrase slammed onto the screen over a highlighter swipe.
const Keyword: React.FC<{g: Graphic}> = ({g}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const slam = spring({frame, fps, config: {damping: 10, mass: 0.6, stiffness: 180}});
  const swipe = interpolate(frame, [3, 12], [0, 1], {...clamp, easing: Easing.out(Easing.cubic)});
  const words = g.headline.toUpperCase();
  // Heavy uppercase runs ~0.8em per character: one line if it fits, else two,
  // and never smaller than the longest word needs to stay on one line.
  const longest = Math.max(...words.split(/\s+/).map((w) => w.length), 1);
  const size = Math.floor(Math.min(150, 840 / (0.8 * longest), Math.max(840 / (0.8 * words.length), 72)));
  return (
    <div
      style={{
        position: 'absolute',
        top: '22%',
        left: '8%',
        right: '8%',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        transform: `translateY(${float(frame, 5)}px)`,
      }}
    >
      {g.label ? (
        <div style={{fontSize: 44, fontWeight: 800, color: '#fff', textShadow: OUTLINE, marginBottom: 22, opacity: swipe, textAlign: 'center'}}>
          {g.label}
        </div>
      ) : null}
      <div style={{position: 'relative', transform: `scale(${2 - slam}) rotate(-3deg)`, opacity: Math.min(1, slam * 1.5)}}>
        <div
          style={{
            position: 'absolute',
            left: -24,
            right: -24,
            top: '10%',
            bottom: '4%',
            background: COLORS.accent,
            transformOrigin: 'left center',
            transform: `scaleX(${swipe})`,
            borderRadius: 12,
            boxShadow: '0 20px 60px rgba(0,0,0,0.45)',
          }}
        />
        <div
          style={{
            position: 'relative',
            fontSize: size,
            fontWeight: 900,
            color: COLORS.ink,
            padding: '0 8px',
            lineHeight: 1.1,
            textAlign: 'center',
            textWrap: 'balance',
          }}
        >
          {words}
        </div>
      </div>
    </div>
  );
};
