import React from 'react';
import {Easing, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {type LucideIcon} from 'lucide-react';
import {iconFor} from './icon';
import {COLORS, FONT, clamp, exitProgress, fitSize, float, formatNumber, parseNumber, payoffPop} from '../theme';
import type {Item, Visual} from './types';

// One animated visual per beat, in the 16:9 frame. Everything enters with a spring,
// keeps moving slightly while it holds (so no beat is a still slide), and eases out
// in the last frames. The area below y=820 is kept free for the subtitles.

const W = 1920;
const SIDE = 170; // left/right margin
const INNER = W - SIDE * 2;

// `roomy`: subtitles are off, so the bottom band is free: sit in the true centre and grow ~10%.
export const VisualView: React.FC<{v: Visual; frames: number; accent: string; roomy?: boolean}> = ({v, frames, accent, roomy}) => {
  const frame = useCurrentFrame();
  const exit = exitProgress(frame, frames, 9);
  const push = interpolate(frame, [0, frames], [1, 1.035], clamp); // slow camera push
  const body = (() => {
    switch (v.type) {
      case 'stat':
        return <Stat v={v} accent={accent} />;
      case 'timeline':
        return v.items.length >= 2 ? <Timeline v={v} frames={frames} accent={accent} /> : <Title v={v} accent={accent} />;
      case 'compare':
        return v.items.length >= 2 ? <Compare v={v} accent={accent} /> : <Title v={v} accent={accent} />;
      case 'steps':
        return v.items.length >= 2 ? <Steps v={v} frames={frames} accent={accent} /> : <Title v={v} accent={accent} />;
      case 'icons':
        return <Icons v={v} accent={accent} />;
      case 'quote':
        return <Quote v={v} frames={frames} accent={accent} />;
      case 'keyword':
        return <Keyword v={v} accent={accent} />;
      case 'chart':
        return v.items.length >= 2 ? <Chart v={v} frames={frames} accent={accent} /> : <Stat v={v} accent={accent} />;
      default:
        return <Title v={v} accent={accent} />;
    }
  })();
  return (
    <div
      style={{
        position: 'absolute',
        inset: 0,
        fontFamily: FONT,
        color: COLORS.text,
        opacity: 1 - exit,
        transform: `translateY(${roomy ? 75 : 0}px) scale(${push * (1 - 0.04 * exit) * (roomy ? 1.1 : 1)}) translateY(${-30 * exit}px)`,
      }}
    >
      {body}
    </div>
  );
};

// ---------- helpers ----------

const useEnter = (delay = 0, config = {damping: 14, mass: 0.7}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  return spring({frame: frame - delay, fps, config});
};

const Stage: React.FC<{children: React.ReactNode; top?: number; bottom?: number}> = ({children, top = 110, bottom = 820}) => (
  <div
    style={{
      position: 'absolute',
      left: SIDE,
      width: INNER,
      top,
      height: bottom - top,
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      textAlign: 'center',
    }}
  >
    {children}
  </div>
);

const Sub: React.FC<{text: string; delay?: number; size?: number}> = ({text, delay = 10, size = 46}) => {
  const e = useEnter(delay);
  if (!text) return null;
  return (
    <div
      style={{
        marginTop: 28,
        fontSize: size,
        fontWeight: 800,
        lineHeight: 1.25,
        opacity: 0.88 * Math.min(1, e),
        transform: `translateY(${(1 - e) * 30}px)`,
        maxWidth: INNER * 0.85,
        textWrap: 'balance',
      }}
    >
      {text}
    </div>
  );
};

const Underline: React.FC<{accent: string; delay?: number; width?: number}> = ({accent, delay = 8, width = 420}) => {
  const frame = useCurrentFrame();
  const p = interpolate(frame, [delay, delay + 16], [0, 1], {...clamp, easing: Easing.out(Easing.cubic)});
  return <div style={{height: 10, width: width * p, borderRadius: 5, background: accent, marginTop: 22, boxShadow: `0 0 24px ${accent}`}} />;
};



// ---------- templates ----------

const Title: React.FC<{v: Visual; accent: string}> = ({v, accent}) => {
  const words = v.headline.split(/\s+/).filter(Boolean);
  const size = Math.max(64, fitSize(v.headline, 132, INNER * 1.7));
  return (
    <Stage>
      <div style={{fontSize: size, fontWeight: 900, lineHeight: 1.08, textWrap: 'balance', maxWidth: INNER}}>
        {words.map((w, i) => (
          <Word key={i} text={w} delay={i * 3} />
        ))}
      </div>
      <Underline accent={accent} delay={words.length * 3 + 2} />
      <Sub text={v.sub} delay={words.length * 3 + 6} />
    </Stage>
  );
};

const Word: React.FC<{text: string; delay: number}> = ({text, delay}) => {
  const e = useEnter(delay, {damping: 12, mass: 0.6});
  return (
    <span style={{display: 'inline-block', margin: '0 0.18em', opacity: Math.min(1, e), transform: `translateY(${(1 - e) * 60}px)`}}>
      {text}
    </span>
  );
};

const Stat: React.FC<{v: Visual; accent: string}> = ({v, accent}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const text = v.headline || v.items[0]?.display || '';
  const parsed = parseNumber(text);
  const t = interpolate(frame, [4, 4 + fps * 0.8], [0, 1], {...clamp, easing: Easing.out(Easing.cubic)});
  // Only count when there are enough steps to look like counting (never "0 billion").
  // A year ("1928", "1940s") is a date, not an amount: it lands, it never counts up.
  const year = /^(1[0-9]|20)\d{2}s?$/.test(text.trim());
  const counts = !year && parsed !== null && Math.abs(parsed.value) * 10 ** parsed.decimals >= 20;
  const shown = counts ? formatNumber(parsed.value * t, parsed) : text;
  const landed = Math.round(4 + fps * 0.8);
  const e = useEnter(0);
  const glow = interpolate(frame, [landed, landed + 8, landed + 30], [0, 1, 0.4], clamp);
  return (
    <Stage>
      <div
        style={{
          fontSize: Math.max(90, fitSize(text, 230, INNER * 1.12)),
          fontWeight: 900,
          whiteSpace: 'nowrap', // "5 to 1" must never break as "5 to / 1"
          color: accent,
          fontVariantNumeric: 'tabular-nums',
          lineHeight: 1,
          transform: `scale(${(0.7 + 0.3 * e) * payoffPop(frame, fps, landed)})`,
          textShadow: `0 0 ${50 * glow}px ${accent}`,
        }}
      >
        {shown}
      </div>
      <div style={{marginTop: 26}} />
      <Underline accent={accent} delay={10} width={360} />
      <Sub text={v.sub || v.items[0]?.label || ''} delay={12} size={50} />
    </Stage>
  );
};

const Keyword: React.FC<{v: Visual; accent: string}> = ({v, accent}) => {
  const frame = useCurrentFrame();
  const e = useEnter(0, {damping: 8, mass: 0.5});
  const shake = frame < 10 ? Math.sin(frame * 2.4) * (10 - frame) * 1.2 : 0;
  return (
    <Stage>
      <div
        style={{
          fontSize: Math.max(110, fitSize(v.headline, 250, INNER * 1.2)),
          fontWeight: 900,
          textTransform: 'uppercase',
          color: accent,
          lineHeight: 1,
          letterSpacing: '0.02em',
          transform: `translateX(${shake}px) scale(${0.4 + 0.6 * e})`,
          opacity: Math.min(1, e * 1.4),
          textShadow: '0 20px 60px rgba(0,0,0,0.5)',
        }}
      >
        {v.headline}
      </div>
      <Sub text={v.sub} delay={10} />
    </Stage>
  );
};

const Icons: React.FC<{v: Visual; accent: string}> = ({v, accent}) => {
  const frame = useCurrentFrame();
  const names = (v.icons.length ? v.icons : ['sparkles']).slice(0, 3);
  const size = names.length === 1 ? 260 : 200;
  return (
    <Stage>
      <div style={{display: 'flex', gap: 90, alignItems: 'center', justifyContent: 'center'}}>
        {names.map((n, i) => {
          const Icon = iconFor(n);
          return <IconDisc key={i} Icon={Icon} delay={i * 6} size={size} accent={accent} bob={float(frame + i * 30, 8, 90)} />;
        })}
      </div>
      <div style={{marginTop: 48, fontSize: fitSize(v.headline, 76, INNER * 1.6), fontWeight: 900, lineHeight: 1.12, textWrap: 'balance'}}>
        {v.headline.split(/\s+/).filter(Boolean).map((w, i) => (
          <Word key={i} text={w} delay={names.length * 6 + i * 2} />
        ))}
      </div>
      <Sub text={v.sub} delay={names.length * 6 + 10} size={42} />
    </Stage>
  );
};

const IconDisc: React.FC<{Icon: LucideIcon; delay: number; size: number; accent: string; bob: number}> = ({Icon, delay, size, accent, bob}) => {
  const e = useEnter(delay, {damping: 10, mass: 0.6});
  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: '50%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'rgba(255,255,255,0.08)',
        border: `4px solid ${accent}`,
        boxShadow: `0 0 50px ${accent}55, inset 0 0 40px rgba(255,255,255,0.06)`,
        transform: `translateY(${bob}px) scale(${e}) rotate(${(1 - e) * -20}deg)`,
        opacity: Math.min(1, e * 1.5),
      }}
    >
      <Icon size={size * 0.52} color={COLORS.text} strokeWidth={1.8} />
    </div>
  );
};

const Quote: React.FC<{v: Visual; frames: number; accent: string}> = ({v, frames, accent}) => {
  const frame = useCurrentFrame();
  const words = v.headline.split(/\s+/).filter(Boolean);
  // Words appear across the first 60% of the beat, like it's being said.
  const shown = Math.ceil(interpolate(frame, [4, Math.max(8, frames * 0.6)], [0, words.length], clamp));
  const mark = useEnter(0);
  return (
    <Stage>
      <div style={{fontSize: 220, lineHeight: 0.6, color: accent, fontWeight: 900, opacity: mark, transform: `scale(${mark})`}}>“</div>
      <div style={{fontSize: fitSize(v.headline, 72, INNER * 2.2), fontWeight: 800, lineHeight: 1.25, maxWidth: INNER * 0.9, textWrap: 'balance'}}>
        {words.map((w, i) => (
          <span key={i} style={{opacity: i < shown ? 1 : 0.12, transition: 'none'}}>
            {w}{' '}
          </span>
        ))}
      </div>
      <Sub text={v.sub ? `— ${v.sub}` : ''} delay={Math.round(frames * 0.5)} size={44} />
    </Stage>
  );
};

const Timeline: React.FC<{v: Visual; frames: number; accent: string}> = ({v, frames, accent}) => {
  const frame = useCurrentFrame();
  const items = v.items.slice(0, 5);
  const span = Math.min(Math.max(20, frames * 0.6), 75); // all items on screen within ~2.5 s, never half-built
  const line = interpolate(frame, [4, span], [0, 1], {...clamp, easing: Easing.inOut(Easing.cubic)});
  const gap = INNER / items.length;
  return (
    <>
      {v.headline ? (
        <div style={{position: 'absolute', top: 120, left: SIDE, width: INNER, textAlign: 'center', fontSize: 64, fontWeight: 900}}>
          {v.headline}
        </div>
      ) : null}
      <div style={{position: 'absolute', top: 470, left: SIDE, height: 8, width: INNER * line, background: accent, borderRadius: 4, boxShadow: `0 0 20px ${accent}`}} />
      {items.map((it, i) => {
        const at = 4 + (span - 4) * ((i + 0.5) / items.length);
        return <TimelinePoint key={i} item={it} x={SIDE + gap * (i + 0.5)} delay={at} accent={accent} width={gap - 30} />;
      })}
    </>
  );
};

const TimelinePoint: React.FC<{item: Item; x: number; delay: number; accent: string; width: number}> = ({item, x, delay, accent, width}) => {
  const e = useEnter(delay, {damping: 11, mass: 0.6});
  return (
    <div style={{position: 'absolute', left: x - width / 2, width, top: 300, textAlign: 'center', opacity: Math.min(1, e * 1.5)}}>
      <div style={{fontSize: 58, fontWeight: 900, color: accent, height: 120, display: 'flex', alignItems: 'flex-end', justifyContent: 'center', transform: `translateY(${(1 - e) * -30}px)`}}>
        {item.label}
      </div>
      <div style={{margin: '26px auto 0', width: 34, height: 34, borderRadius: '50%', background: COLORS.text, border: `8px solid ${accent}`, transform: `scale(${e})`}} />
      <div style={{marginTop: 30, fontSize: 36, fontWeight: 800, lineHeight: 1.25, opacity: 0.92, transform: `translateY(${(1 - e) * 30}px)`}}>{item.text}</div>
    </div>
  );
};

const Compare: React.FC<{v: Visual; accent: string}> = ({v, accent}) => {
  const frame = useCurrentFrame();
  const [a, b] = v.items;
  const max = Math.max(Math.abs(a.value), Math.abs(b.value), 1e-9);
  const grow = interpolate(frame, [8, 34], [0, 1], {...clamp, easing: Easing.out(Easing.cubic)});
  const barMax = 380;
  const col = (it: Item, color: string, delay: number) => (
    <CompareColumn key={it.label} item={it} color={color} height={(barMax * Math.abs(it.value)) / max} grow={grow} delay={delay} />
  );
  return (
    <>
      {v.headline ? (
        <div style={{position: 'absolute', top: 110, left: SIDE, width: INNER, textAlign: 'center', fontSize: 70, fontWeight: 900, color: accent}}>
          {v.headline}
        </div>
      ) : null}
      <div style={{position: 'absolute', left: SIDE, width: INNER, top: 230, height: 560, display: 'flex', justifyContent: 'center', alignItems: 'flex-end', gap: 220}}>
        {col(a, 'rgba(255,255,255,0.85)', 0)}
        {col(b, accent, 6)}
      </div>
    </>
  );
};

const CompareColumn: React.FC<{item: Item; color: string; height: number; grow: number; delay: number}> = ({item, color, height, grow, delay}) => {
  const e = useEnter(delay);
  return (
    <div style={{display: 'flex', flexDirection: 'column', alignItems: 'center', width: 360, opacity: Math.min(1, e * 1.5)}}>
      <div style={{fontSize: 64, fontWeight: 900, marginBottom: 16}}>{item.display}</div>
      <div style={{width: 200, height: Math.max(8, height * grow), background: color, borderRadius: '18px 18px 6px 6px', boxShadow: `0 0 40px ${color}55`}} />
      <div style={{marginTop: 22, fontSize: 40, fontWeight: 800, textAlign: 'center', lineHeight: 1.2}}>{item.label}</div>
    </div>
  );
};

const Steps: React.FC<{v: Visual; frames: number; accent: string}> = ({v, frames, accent}) => {
  const items = v.items.slice(0, 4);
  const span = Math.min(Math.max(20, frames * 0.55), 75);
  const w = Math.min(470, (INNER - (items.length - 1) * 70) / items.length);
  return (
    <>
      {v.headline ? (
        <div style={{position: 'absolute', top: 120, left: SIDE, width: INNER, textAlign: 'center', fontSize: 64, fontWeight: 900}}>{v.headline}</div>
      ) : null}
      <div style={{position: 'absolute', left: SIDE, width: INNER, top: 250, display: 'flex', justifyContent: 'center', alignItems: 'stretch', gap: 70}}>
        {items.map((it, i) => (
          <StepCard key={i} n={i + 1} item={it} width={w} delay={4 + (span * i) / items.length} accent={accent} last={i === items.length - 1} />
        ))}
      </div>
    </>
  );
};

const StepCard: React.FC<{n: number; item: Item; width: number; delay: number; accent: string; last: boolean}> = ({n, item, width, delay, accent, last}) => {
  const e = useEnter(delay, {damping: 12, mass: 0.6});
  return (
    <div
      style={{
        position: 'relative',
        width,
        padding: '44px 30px',
        borderRadius: 32,
        background: 'rgba(10,10,16,0.55)',
        border: '2px solid rgba(255,255,255,0.12)',
        opacity: Math.min(1, e * 1.4),
        transform: `translateY(${(1 - e) * 60}px)`,
        textAlign: 'center',
      }}
    >
      <div style={{margin: '0 auto', width: 84, height: 84, borderRadius: '50%', background: accent, color: COLORS.ink, fontSize: 48, fontWeight: 900, display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
        {n}
      </div>
      <div style={{marginTop: 26, fontSize: 48, fontWeight: 900, lineHeight: 1.15}}>{item.label}</div>
      {item.text ? <div style={{marginTop: 16, fontSize: 38, fontWeight: 800, opacity: 0.85, lineHeight: 1.25}}>{item.text}</div> : null}
      {!last ? <div style={{position: 'absolute', right: -58, top: '42%', fontSize: 56, color: accent, fontWeight: 900}}>→</div> : null}
    </div>
  );
};

const Chart: React.FC<{v: Visual; frames: number; accent: string}> = ({v, frames, accent}) => {
  const frame = useCurrentFrame();
  const pts = v.items.slice(0, 6);
  const vals = pts.map((p) => p.value);
  const lo = Math.min(...vals, 0);
  const hi = Math.max(...vals);
  const box = {x: SIDE + 80, y: 230, w: INNER - 160, h: 440};
  const xy = pts.map((p, i) => [box.x + (box.w * i) / Math.max(1, pts.length - 1), box.y + box.h - (box.h * (p.value - lo)) / Math.max(hi - lo, 1e-9)]);
  const draw = interpolate(frame, [6, Math.max(24, frames * 0.5)], [0, 1], {...clamp, easing: Easing.inOut(Easing.cubic)});
  const d = xy.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ');
  const length = xy.reduce((s, p, i) => (i ? s + Math.hypot(p[0] - xy[i - 1][0], p[1] - xy[i - 1][1]) : 0), 0);
  return (
    <>
      <div style={{position: 'absolute', top: 110, left: SIDE, width: INNER, textAlign: 'center', fontSize: 64, fontWeight: 900}}>
        {v.headline} <span style={{fontSize: 40, opacity: 0.8, fontWeight: 800}}>{v.sub}</span>
      </div>
      <svg width={1920} height={1080} style={{position: 'absolute', inset: 0}}>
        <line x1={box.x} x2={box.x + box.w} y1={box.y + box.h} y2={box.y + box.h} stroke="rgba(255,255,255,0.25)" strokeWidth={3} />
        <path d={d} fill="none" stroke={accent} strokeWidth={10} strokeLinecap="round" strokeLinejoin="round" strokeDasharray={length} strokeDashoffset={length * (1 - draw)} style={{filter: `drop-shadow(0 0 14px ${accent})`}} />
        {xy.map((p, i) => {
          const on = draw >= i / Math.max(1, pts.length - 1) - 0.001;
          return <circle key={i} cx={p[0]} cy={p[1]} r={on ? 16 : 0} fill={COLORS.text} stroke={accent} strokeWidth={6} />;
        })}
      </svg>
      {xy.map((p, i) => {
        const on = draw >= i / Math.max(1, pts.length - 1) - 0.001;
        return (
          <div key={i} style={{position: 'absolute', left: p[0] - 150, width: 300, top: p[1] - 90, textAlign: 'center', fontSize: 40, fontWeight: 900, opacity: on ? 1 : 0}}>
            {pts[i].display}
            <div style={{position: 'absolute', top: box.y + box.h - p[1] + 110, width: 300, fontSize: 34, fontWeight: 800, opacity: 0.8}}>{pts[i].label}</div>
          </div>
        );
      })}
    </>
  );
};
