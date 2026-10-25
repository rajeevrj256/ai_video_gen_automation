import '@fontsource/bebas-neue/400.css';
import '@fontsource/inter/400.css';
import '@fontsource/inter/600.css';
import '@fontsource/inter/800.css';
import '@fontsource/jetbrains-mono/500.css';
import '@fontsource/jetbrains-mono/700.css';
import React, {useEffect, useState} from 'react';
import {Easing, continueRender, delayRender, interpolate, random, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {Check, X} from 'lucide-react';
import {clamp, exitProgress, formatNumber, parseNumber} from '../../theme';
import {iconFor} from '../icon';
import {BOX} from '../box';
import type {Chapter, Item, Look, Tone, Visual} from '../types';

// The Briefing template (reelgen/briefing.py), from the user's reference frames of a news-explainer channel, read as
// a design language rather than copied: a near-black page with a faint grid, a header strip that names the chapter and
// the source, condensed display capitals with one word in the accent colour, small tracked mono labels, slate cards,
// and green / red / blue only for meaning (done, threat, information). Things build up in the order the line says
// them: rows tick, nodes light, arrows draw, numbers count, earlier steps stay lit and later ones wait dimmed.
// Claude picks the layout per beat (flow, checklist, grid, terminal, card, scale, dates, receipt and the classic
// types redrawn here), so no two videos are built the same way; each video also gets its own accent and paper tone.

export const DISPLAY = '"Bebas Neue", "Noto Sans Devanagari", sans-serif';
export const MONO = '"JetBrains Mono", "Noto Sans Devanagari", monospace';
export const SANS = '"Inter", "Noto Sans Devanagari", sans-serif';

export const useBriefFonts = () => {
  const [handle] = useState(() => delayRender('Loading the Briefing fonts'));
  useEffect(() => {
    Promise.all(['400 80px "Bebas Neue"', '600 40px Inter', '800 40px Inter', '500 20px "JetBrains Mono"', '700 20px "JetBrains Mono"']
      .map((f) => document.fonts.load(f))).catch(() => undefined).finally(() => continueRender(handle));
  }, [handle]);
};

// Each video's own accent and paper (by its look's seed); the meaning colours stay fixed.
const ACCENTS = ['#F5A623', '#FF7A45', '#38C6F4', '#C6F432', '#B18CFF', '#FFD23F'];
const PAPERS = ['#0B0D10', '#0A0D14', '#0E0C0B', '#0B0E0D'];
export type Pal = {bg: string; accent: string; ink: string; dim: string; faint: string; card: string; line: string;
  good: string; bad: string; info: string};
export const palFor = (seed: number): Pal => ({
  bg: PAPERS[Math.abs(seed) % PAPERS.length],
  accent: ACCENTS[Math.abs(seed * 7 + 3) % ACCENTS.length],
  ink: '#EFECE4', dim: '#8A919C', faint: '#3C424B', card: '#161B22', line: '#2A3038',
  good: '#3DDC97', bad: '#EF4444', info: '#7FB2FF',
});
export const toneColor = (p: Pal, t?: Tone | string, fallback?: string) =>
  t === 'good' ? p.good : t === 'bad' ? p.bad : t === 'info' ? p.info : t === 'warn' ? p.accent : fallback ?? p.ink;

const useIn = (delay = 0, damping = 16) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  return spring({frame: frame - delay, fps, config: {damping, mass: 0.6}});
};
// When item i of n lands: spread over the first ~70% of the beat, so the build follows the line being spoken.
const landAt = (i: number, n: number, frames: number, start = 6) => Math.round(start + (Math.max(20, frames * 0.7) - start) * (i / Math.max(1, n)));
const fit = (text: string, max: number, width: number, em = 0.45) => Math.max(18, Math.min(max, Math.floor(width / Math.max(1, text.length * em))));

// ---------- the page ----------

export const BriefBackdrop: React.FC<{pal: Pal}> = ({pal}) => (
  <div style={{position: 'absolute', inset: 0, background: pal.bg}}>
    <div style={{position: 'absolute', inset: 0, backgroundImage: 'linear-gradient(rgba(255,255,255,0.035) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.035) 1px, transparent 1px)',
      backgroundSize: '72px 72px', backgroundPosition: '-1px -1px'}} />
    <div style={{position: 'absolute', inset: 0, background: 'radial-gradient(ellipse at 50% 40%, transparent 45%, rgba(0,0,0,0.55) 100%)'}} />
  </div>
);

// The strip across the top: the chapter on the left, the source (or the video and where we are in it) on the right.
export const BriefHeader: React.FC<{pal: Pal; label: string; right: string; source: boolean}> = ({pal, label, right, source}) => {
  const side = BOX.V ? 60 : 110;
  return (
    <div style={{position: 'absolute', left: side, right: side, top: BOX.V ? 230 : 0, height: BOX.V ? 90 : 96, display: 'flex', alignItems: 'center',
      justifyContent: 'space-between', borderBottom: `1px solid ${pal.line}`, fontFamily: MONO, fontSize: BOX.V ? 20 : 19, letterSpacing: '0.24em',
      textTransform: 'uppercase', color: pal.dim, gap: 30}}>
      <div style={{display: 'flex', alignItems: 'center', gap: 22, minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden'}}>
        <span style={{width: 13, height: 13, background: pal.accent, flex: 'none'}} />{label}
      </div>
      {right ? (
        <div style={{display: 'flex', alignItems: 'center', gap: 16, whiteSpace: 'nowrap', overflow: 'hidden', color: source ? pal.dim : '#6E7580'}}>
          {source ? <span style={{width: 16, height: 12, border: `2px solid ${pal.dim}`, borderWidth: '5px 2px 2px', flex: 'none'}} /> : null}
          {source ? `Source: ${right}` : right}
        </div>
      ) : null}
    </div>
  );
};

// The usable area below the header.
const AREA = () => ({left: BOX.V ? 60 : 130, right: BOX.V ? 60 : 130, top: BOX.V ? 380 : 150, bottom: BOX.V ? 640 : 90});

// ---------- shared pieces ----------

const Kicker: React.FC<{text?: string; pal: Pal; color?: string; delay?: number; size?: number}> = ({text, pal, color, delay = 0, size = 22}) => {
  const e = useIn(delay);
  if (!text) return null;
  return <div style={{fontFamily: MONO, fontSize: size, letterSpacing: '0.24em', textTransform: 'uppercase', color: color ?? pal.dim,
    opacity: Math.min(1, e), transform: `translateY(${(1 - e) * 10}px)`}}>{text}</div>;
};

// A headline in display capitals: words rise in one by one, the accent words in the accent colour.
const Headline: React.FC<{text: string; accent?: string; pal: Pal; size: number; delay?: number; align?: 'left' | 'center'; color?: string}> =
  ({text, accent, pal, size, delay = 0, align = 'left', color}) => {
    const frame = useCurrentFrame();
    const hot = new Set((accent ?? '').toLowerCase().split(/\s+/).filter(Boolean).map((w) => w.replace(/[^\p{L}\p{N}]/gu, '')));
    const words = text.split(/\s+/).filter(Boolean);
    return (
      <div style={{fontFamily: DISPLAY, fontSize: size, lineHeight: 0.98, letterSpacing: '0.01em', textTransform: 'uppercase', color: color ?? pal.ink,
        textAlign: align, textWrap: 'balance'}}>
        {words.map((w, i) => {
          const p = interpolate(frame, [delay + i * 2.5, delay + i * 2.5 + 9], [0, 1], {...clamp, easing: Easing.out(Easing.cubic)});
          return (
            <span key={i} style={{display: 'inline-block', overflow: 'hidden', verticalAlign: 'top', marginRight: '0.22em'}}>
              <span style={{display: 'inline-block', transform: `translateY(${(1 - p) * 100}%)`,
                color: hot.has(w.toLowerCase().replace(/[^\p{L}\p{N}]/gu, '')) ? pal.accent : undefined}}>{w}</span>
            </span>
          );
        })}
      </div>
    );
  };

const Tags: React.FC<{tags?: string[]; pal: Pal; tone?: Tone; delay?: number; size?: number}> = ({tags, pal, tone, delay = 0, size = 24}) => {
  if (!tags?.length) return null;
  return (
    <div style={{display: 'flex', gap: 18, flexWrap: 'wrap'}}>
      {tags.slice(0, 3).map((t, i) => <Tag key={i} text={t} color={toneColor(pal, tone || (i === 0 ? 'warn' : 'bad'), pal.accent)} delay={delay + i * 4} size={size} />)}
    </div>
  );
};
const Tag: React.FC<{text: string; color: string; delay: number; size?: number; solid?: boolean}> = ({text, color, delay, size = 24, solid}) => {
  const e = useIn(delay, 12);
  return <div style={{fontFamily: MONO, fontWeight: 700, fontSize: size, letterSpacing: '0.16em', textTransform: 'uppercase', padding: '8px 16px',
    border: `2px solid ${color}`, color: solid ? '#0B0D10' : color, background: solid ? color : 'transparent', whiteSpace: 'nowrap',
    opacity: Math.min(1, e * 1.5), transform: `scale(${0.85 + 0.15 * e})`}}>{text}</div>;
};

const Sub: React.FC<{text?: string; pal: Pal; delay?: number; size?: number; align?: 'left' | 'center'}> = ({text, pal, delay = 10, size = 40, align}) => {
  const e = useIn(delay);
  if (!text) return null;
  return <div style={{fontFamily: SANS, fontWeight: 600, fontSize: size, color: '#A5ACB6', lineHeight: 1.3, opacity: Math.min(1, e), textAlign: align,
    transform: `translateY(${(1 - e) * 14}px)`}}>{text}</div>;
};

// A heading block: kicker, headline, tags.
const Head: React.FC<{v: Visual; pal: Pal; size?: number; align?: 'left' | 'center'; text?: string}> = ({v, pal, size, align = 'left', text}) => {
  const words = text ?? v.headline;
  const s = size ?? fit(words, BOX.V ? 120 : 150, (BOX.V ? 960 : 1500) * (words.length > 26 ? 1.6 : 1), 0.42);
  return (
    <div style={{display: 'flex', flexDirection: 'column', gap: 20, alignItems: align === 'center' ? 'center' : 'flex-start'}}>
      <Kicker text={v.kicker} pal={pal} />
      {words ? <Headline text={words} accent={v.accent} pal={pal} size={s} align={align} /> : null}
      <Tags tags={v.tags} pal={pal} tone={v.tone} delay={8 + words.split(/\s+/).length * 2.5} />
    </div>
  );
};

const Frame: React.FC<{children: React.ReactNode; justify?: string; align?: string; gap?: number}> = ({children, justify = 'center', align = 'stretch', gap = 46}) => {
  const a = AREA();
  return <div style={{position: 'absolute', left: a.left, right: a.right, top: a.top, bottom: a.bottom, display: 'flex', flexDirection: 'column',
    justifyContent: justify, alignItems: align, gap}}>{children}</div>;
};

// ---------- the beat ----------

export const BriefVisual: React.FC<{v: Visual; frames: number; pal: Pal}> = ({v, frames, pal}) => {
  const frame = useCurrentFrame();
  const exit = exitProgress(frame, frames, 8);
  const n = v.items.length;
  const body = (() => {
    switch (v.type) {
      case 'stat': return <Stat v={v} pal={pal} />;
      case 'keyword': return <Frame align="center"><Head v={v} pal={pal} align="center" size={fit(v.headline, BOX.V ? 200 : 260, BOX.V ? 960 : 1500, 0.42)} /><Sub text={v.sub} pal={pal} align="center" /></Frame>;
      case 'compare': return n >= 2 ? <Compare v={v} pal={pal} /> : <Title v={v} pal={pal} />;
      case 'steps': return n >= 2 ? <Progress v={v} frames={frames} pal={pal} /> : <Title v={v} pal={pal} />;
      case 'timeline': return n >= 2 ? <Track v={v} frames={frames} pal={pal} /> : <Title v={v} pal={pal} />;
      case 'chart': return n >= 2 ? <Chart v={v} frames={frames} pal={pal} /> : <Stat v={v} pal={pal} />;
      case 'icons': return <Icons v={v} frames={frames} pal={pal} />;
      case 'quote': return <Quote v={v} frames={frames} pal={pal} />;
      case 'flow': return n >= 2 ? <Flow v={v} frames={frames} pal={pal} /> : <Title v={v} pal={pal} />;
      case 'checklist': return n ? <Checklist v={v} frames={frames} pal={pal} /> : <Title v={v} pal={pal} />;
      case 'grid': return <Grid v={v} frames={frames} pal={pal} />;
      case 'terminal': return <Terminal v={v} frames={frames} pal={pal} />;
      case 'card': return <Card v={v} pal={pal} />;
      case 'scale': return n >= 2 ? <Scale v={v} frames={frames} pal={pal} /> : <Stat v={v} pal={pal} />;
      case 'dates': return n ? <Dates v={v} frames={frames} pal={pal} /> : <Title v={v} pal={pal} />;
      case 'receipt': return n ? <Receipt v={v} frames={frames} pal={pal} /> : <Title v={v} pal={pal} />;
      default: return <Title v={v} pal={pal} />;
    }
  })();
  return <div style={{position: 'absolute', inset: 0, opacity: 1 - exit, transform: `translateY(${-14 * exit}px)`}}>{body}</div>;
};

const Title: React.FC<{v: Visual; pal: Pal}> = ({v, pal}) => {
  const center = random(`t${v.headline}`) < 0.5; // some headlines centred, some flush left
  return <Frame align={center ? 'center' : 'flex-start'}><Head v={v} pal={pal} align={center ? 'center' : 'left'} /><Sub text={v.sub} pal={pal} align={center ? 'center' : 'left'} delay={14} /></Frame>;
};

// One number, counted up, with what it is in mono above and a sentence below.
const Stat: React.FC<{v: Visual; pal: Pal}> = ({v, pal}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const text = v.headline || v.items[0]?.display || '';
  const parsed = parseNumber(text);
  const year = /^(1[0-9]|20)\d{2}s?$/.test(text.trim());
  const counts = !year && parsed !== null && Math.abs(parsed.value) * 10 ** parsed.decimals >= 20;
  const t = interpolate(frame, [4, 4 + fps * 0.9], [0, 1], {...clamp, easing: Easing.out(Easing.cubic)});
  const shown = counts && parsed ? formatNumber(parsed.value * t, parsed) : text;
  const color = toneColor(pal, v.tone, pal.accent);
  return (
    <Frame align="flex-start" gap={10}>
      <Kicker text={v.kicker || v.items[0]?.label} pal={pal} />
      <div style={{fontFamily: DISPLAY, color, lineHeight: 0.9, fontSize: Math.min(BOX.V ? 300 : 380, Math.floor((BOX.V ? 960 : 1500) / Math.max(1, text.length * 0.5))),
        fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap', textShadow: `0 0 60px ${color}33`}}>{shown}</div>
      <Sub text={v.sub} pal={pal} size={46} delay={18} />
      <Tags tags={v.tags} pal={pal} tone={v.tone} delay={24} />
    </Frame>
  );
};

// Two slate cards with a coloured top edge, each a big number and a bar for its size.
const Compare: React.FC<{v: Visual; pal: Pal}> = ({v, pal}) => {
  const [a, b] = v.items;
  const max = Math.max(Math.abs(a.value), Math.abs(b.value), 1e-9);
  return (
    <Frame gap={40}>
      {v.headline || v.kicker ? <Head v={v} pal={pal} size={fit(v.headline, 110, 1500, 0.42)} /> : null}
      <div style={{display: 'flex', flexDirection: BOX.V ? 'column' : 'row', gap: BOX.V ? 30 : 0, alignItems: 'center'}}>
        <SideCard item={a} pal={pal} color={toneColor(pal, a.tone, pal.info)} share={Math.abs(a.value) / max} delay={4} />
        <div style={{fontFamily: DISPLAY, fontSize: 70, color: pal.dim, width: BOX.V ? 'auto' : 140, textAlign: 'center'}}>{v.sub && v.sub.length < 5 ? v.sub : 'VS'}</div>
        <SideCard item={b} pal={pal} color={toneColor(pal, b.tone, pal.accent)} share={Math.abs(b.value) / max} delay={12} />
      </div>
    </Frame>
  );
};
const SideCard: React.FC<{item: Item; pal: Pal; color: string; share: number; delay: number}> = ({item, pal, color, share, delay}) => {
  const e = useIn(delay);
  const grow = interpolate(useCurrentFrame(), [delay + 6, delay + 30], [0, share], {...clamp, easing: Easing.out(Easing.cubic)});
  return (
    <div style={{flex: 1, width: BOX.V ? '100%' : undefined, background: pal.card, borderRadius: 14, borderTop: `5px solid ${color}`, padding: '34px 40px',
      display: 'flex', flexDirection: 'column', gap: 14, opacity: Math.min(1, e * 1.4), transform: `translateY(${(1 - e) * 30}px)`}}>
      <div style={{fontFamily: MONO, fontSize: 22, letterSpacing: '0.2em', textTransform: 'uppercase', color: pal.info}}>{item.label}</div>
      <div style={{fontFamily: DISPLAY, fontSize: fit(item.display || String(item.value), 150, 620, 0.5), color: pal.ink, lineHeight: 0.95}}>{item.display || item.value}</div>
      {item.text ? <div style={{fontFamily: MONO, fontSize: 20, letterSpacing: '0.18em', textTransform: 'uppercase', color: pal.dim}}>{item.text}</div> : null}
      {item.value ? <div style={{height: 10, background: '#232A33', borderRadius: 5}}><div style={{height: 10, width: `${grow * 100}%`, background: color, borderRadius: 5}} /></div> : null}
    </div>
  );
};

// Steps as nodes on a line that light up one by one (a check in a glowing disc), later ones waiting dimmed.
const Progress: React.FC<{v: Visual; frames: number; pal: Pal}> = ({v, frames, pal}) => {
  const frame = useCurrentFrame();
  const items = v.items.slice(0, 5);
  const ats = items.map((_, i) => landAt(i, items.length, frames));
  const tall = BOX.V;
  return (
    <Frame gap={tall ? 50 : 90}>
      {v.headline ? <Head v={v} pal={pal} align="center" size={fit(v.headline, 120, 1400, 0.42)} /> : null}
      <div style={{display: 'flex', flexDirection: tall ? 'column' : 'row', alignItems: 'flex-start', justifyContent: 'center', gap: tall ? 26 : 0}}>
        {items.map((it, i) => {
          const on = frame >= ats[i];
          const pop = spring({frame: frame - ats[i], fps: 30, config: {damping: 11, mass: 0.5}});
          const line = interpolate(frame, [ats[i], ats[i + 1] ?? ats[i] + 12], [0, 1], clamp);
          const color = it.tone === 'bad' ? pal.bad : pal.good;
          return (
            <div key={i} style={{display: 'flex', flexDirection: 'row', alignItems: tall ? 'center' : 'flex-start'}}>
              <div style={{display: 'flex', flexDirection: tall ? 'row' : 'column', alignItems: 'center', gap: tall ? 30 : 22, width: tall ? undefined : 230}}>
                <div style={{width: 96, height: 96, borderRadius: 48, border: `3px solid ${on ? color : '#3A414B'}`, background: on ? color : 'transparent',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: on ? `0 0 ${50 * Math.min(1, pop)}px ${color}88` : 'none',
                  transform: `scale(${on ? 0.8 + 0.2 * pop : 1})`}}>
                  {on ? (it.tone === 'bad' ? <X size={50} color="#0B0D10" strokeWidth={3.5} /> : <Check size={50} color="#0B0D10" strokeWidth={3.5} />) : null}
                </div>
                <div style={{fontFamily: DISPLAY, fontSize: fit(it.label, 54, 230, 0.46), lineHeight: 1, textAlign: tall ? 'left' : 'center', textTransform: 'uppercase',
                  color: on ? pal.ink : '#4A515B'}}>{it.label}</div>
                {it.text && on ? <div style={{fontFamily: MONO, fontSize: 18, letterSpacing: '0.16em', textTransform: 'uppercase', color: pal.dim, textAlign: 'center', opacity: Math.min(1, pop)}}>{it.text}</div> : null}
              </div>
              {i < items.length - 1 && !tall ? (
                <div style={{position: 'relative', width: 120, height: 2, marginTop: 47, background: '#3A414B'}}>
                  <div style={{position: 'absolute', left: 0, top: 0, height: 2, width: `${line * 100}%`, background: pal.good}} />
                  <div style={{position: 'absolute', right: -2, top: -7, width: 14, height: 14, borderRight: `2px solid ${line >= 1 ? pal.good : '#3A414B'}`,
                    borderTop: `2px solid ${line >= 1 ? pal.good : '#3A414B'}`, transform: 'rotate(45deg)'}} />
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </Frame>
  );
};

// A dated track: the bar fills to each moment in turn; a red diamond marks a 'bad' one, a dot the others.
const Track: React.FC<{v: Visual; frames: number; pal: Pal}> = ({v, frames, pal}) => {
  const frame = useCurrentFrame();
  const items = v.items.slice(0, 5);
  if (BOX.V) return <Checklist v={{...v, items: items.map((it) => ({...it, text: it.text || it.label, label: it.text ? it.label : ''}))}} frames={frames} pal={pal} plain />;
  const ats = items.map((_, i) => landAt(i, items.length, frames));
  const W = 1560;
  const xs = items.map((_, i) => 60 + (W - 120) * (i / Math.max(1, items.length - 1)));
  const fill = interpolate(frame, [ats[0], ats[ats.length - 1] + 8], [0, 1], clamp);
  return (
    <Frame gap={110}>
      {v.headline ? <Head v={v} pal={pal} size={fit(v.headline, 120, 1400, 0.42)} /> : null}
      <div style={{position: 'relative', height: 240, width: W}}>
        <div style={{position: 'absolute', left: 0, right: 0, top: 120, height: 14, background: '#1D232B', borderRadius: 7}} />
        <div style={{position: 'absolute', left: 0, width: W * fill, top: 120, height: 14, background: pal.accent, borderRadius: 7, boxShadow: `0 0 26px ${pal.accent}66`}} />
        {items.map((it, i) => {
          const on = frame >= ats[i];
          const e = spring({frame: frame - ats[i], fps: 30, config: {damping: 12, mass: 0.5}});
          const color = toneColor(pal, it.tone, pal.accent);
          const now = on && (i === items.length - 1 || frame < ats[i + 1]);
          return (
            <React.Fragment key={i}>
              <div style={{position: 'absolute', left: xs[i] - 14, top: 113, width: 28, height: 28, background: on ? color : '#2A3038',
                borderRadius: it.tone === 'bad' ? 3 : 14, transform: `rotate(${it.tone === 'bad' ? 45 : 0}deg) scale(${on ? 0.7 + 0.3 * e : 0.6})`,
                boxShadow: on ? `0 0 24px ${color}` : 'none'}} />
              <div style={{position: 'absolute', left: xs[i] - 180, width: 360, top: 0, height: 96, display: 'flex', alignItems: 'flex-end', justifyContent: 'center',
                textAlign: 'center', fontFamily: MONO, fontWeight: 700, fontSize: 24, letterSpacing: '0.12em', textTransform: 'uppercase',
                color: now ? color : on ? '#9AA1AB' : 'transparent', opacity: Math.min(1, e)}}>{it.text}</div>
              <div style={{position: 'absolute', left: xs[i] - 150, width: 300, top: 160, textAlign: 'center', fontFamily: DISPLAY, fontSize: 46,
                color: on ? pal.ink : '#4A515B'}}>{it.label}</div>
            </React.Fragment>
          );
        })}
      </div>
      <Sub text={v.sub} pal={pal} delay={ats[ats.length - 1] + 6} size={36} />
    </Frame>
  );
};

// A thin line chart with mono labels.
const Chart: React.FC<{v: Visual; frames: number; pal: Pal}> = ({v, frames, pal}) => {
  const frame = useCurrentFrame();
  const items = v.items.slice(0, 6);
  const W = BOX.V ? 900 : 1500, H = BOX.V ? 520 : 470;
  const vals = items.map((i) => i.value);
  const lo = Math.min(0, ...vals), hi = Math.max(...vals, 1e-9);
  const pts = items.map((it, i) => [40 + (W - 80) * (i / Math.max(1, items.length - 1)), H - 40 - (H - 100) * ((it.value - lo) / (hi - lo || 1))]);
  const draw = interpolate(frame, [6, Math.max(26, frames * 0.6)], [0, 1], {...clamp, easing: Easing.inOut(Easing.cubic)});
  const path = pts.map(([x, y], i) => `${i ? 'L' : 'M'}${x},${y}`).join(' ');
  const len = pts.reduce((s, p, i) => (i ? s + Math.hypot(p[0] - pts[i - 1][0], p[1] - pts[i - 1][1]) : 0), 0);
  return (
    <Frame gap={30}>
      <Head v={v} pal={pal} size={fit(v.headline, 100, 1400, 0.42)} />
      <svg width={W} height={H} style={{overflow: 'visible'}}>
        {[0.25, 0.5, 0.75, 1].map((k) => <line key={k} x1={0} x2={W} y1={H - 40 - (H - 100) * k} y2={H - 40 - (H - 100) * k} stroke="#1E242C" strokeWidth={1} />)}
        <line x1={0} x2={W} y1={H - 40} y2={H - 40} stroke="#3A414B" strokeWidth={2} />
        <path d={path} fill="none" stroke={pal.accent} strokeWidth={5} strokeDasharray={len} strokeDashoffset={len * (1 - draw)} strokeLinejoin="round" />
        {pts.map(([x, y], i) => {
          const shown = draw >= i / Math.max(1, pts.length - 1) - 0.001;
          return shown ? (
            <g key={i}>
              <circle cx={x} cy={y} r={9} fill={pal.bg} stroke={pal.accent} strokeWidth={4} />
              <text x={x} y={y - 24} textAnchor="middle" fontFamily={MONO} fontWeight={700} fontSize={24} fill={pal.ink}>{items[i].display}</text>
            </g>
          ) : null;
        })}
        {items.map((it, i) => <text key={i} x={pts[i][0]} y={H} textAnchor="middle" fontFamily={MONO} fontSize={22} letterSpacing={3} fill={pal.dim}>{it.label.toUpperCase()}</text>)}
      </svg>
      <Sub text={v.sub} pal={pal} size={30} delay={20} />
    </Frame>
  );
};

// Line icons in outlined tiles; a 'bad' tone crosses them out.
const Icons: React.FC<{v: Visual; frames: number; pal: Pal}> = ({v, frames, pal}) => {
  const frame = useCurrentFrame();
  const names = (v.icons.length ? v.icons : ['circle-help']).slice(0, 3);
  const size = BOX.V ? 220 : 250;
  const cross = interpolate(frame, [frames * 0.45, frames * 0.45 + 10], [0, 1], clamp);
  return (
    <Frame align="center" gap={50}>
      <div style={{display: 'flex', gap: 60}}>
        {names.map((n, i) => {
          const Icon = iconFor(n);
          const e = spring({frame: frame - i * 6, fps: 30, config: {damping: 13, mass: 0.6}});
          const color = toneColor(pal, v.tone, pal.ink);
          return (
            <div key={i} style={{position: 'relative', width: size, height: size, border: `2px solid ${pal.line}`, background: '#11151B', borderRadius: 18,
              display: 'flex', alignItems: 'center', justifyContent: 'center', opacity: Math.min(1, e * 1.4), transform: `translateY(${(1 - e) * 40}px)`}}>
              <Icon size={size * 0.5} color={color} strokeWidth={1.4} />
              {v.tone === 'bad' ? <div style={{position: 'absolute', left: '8%', top: '50%', height: 6, width: `${84 * cross}%`, background: pal.bad, transform: 'rotate(-35deg)', transformOrigin: 'left center', borderRadius: 3}} /> : null}
            </div>
          );
        })}
      </div>
      <Head v={v} pal={pal} align="center" size={fit(v.headline, 96, 1400, 0.42)} />
      <Sub text={v.sub} pal={pal} align="center" delay={16} size={36} />
    </Frame>
  );
};

// A quote card: a bar on the left, the words lit as they are said, who said it in mono.
const Quote: React.FC<{v: Visual; frames: number; pal: Pal}> = ({v, frames, pal}) => {
  const frame = useCurrentFrame();
  const words = v.headline.split(/\s+/).filter(Boolean);
  const lit = Math.ceil(interpolate(frame, [4, Math.max(10, frames * 0.65)], [0, words.length], clamp));
  const hot = new Set((v.accent ?? '').toLowerCase().split(/\s+/).filter(Boolean));
  const e = useIn(0);
  return (
    <Frame>
      <div style={{background: pal.card, borderLeft: `6px solid #5B626C`, padding: BOX.V ? '40px 44px' : '56px 70px', borderRadius: 6, boxShadow: '0 30px 80px rgba(0,0,0,0.45)',
        opacity: Math.min(1, e * 1.4), transform: `translateY(${(1 - e) * 30}px)`}}>
        <div style={{fontFamily: SANS, fontWeight: 800, fontSize: 130, lineHeight: 0.5, color: '#3E454F', height: 50}}>“</div>
        <div style={{fontFamily: SANS, fontWeight: 600, fontSize: fit(v.headline, 72, BOX.V ? 2400 : 3200, 0.5), lineHeight: 1.22, textWrap: 'balance'}}>
          {words.map((w, i) => (
            <span key={i} style={{color: i >= lit ? '#3E454F' : hot.has(w.toLowerCase()) ? pal.accent : pal.ink}}>{w} </span>
          ))}
        </div>
        {v.sub ? <div style={{marginTop: 30, fontFamily: MONO, fontSize: 22, letterSpacing: '0.18em', textTransform: 'uppercase', color: pal.dim}}>{v.sub}</div> : null}
      </div>
    </Frame>
  );
};

// A box's name: up to two lines, its longest word across the box.
const flowSize = (t: string, w: number) => Math.max(26, Math.min(76, Math.floor(w / (Math.max(1, ...t.split(/\s+/).map((x) => x.length)) * 0.46)),
  Math.floor((w * 2) / Math.max(1, t.length * 0.46))));

// Boxes joined by arrows that draw as the chain is told: a small mono label over each name.
const Flow: React.FC<{v: Visual; frames: number; pal: Pal}> = ({v, frames, pal}) => {
  const frame = useCurrentFrame();
  const items = v.items.slice(0, 5);
  const ats = items.map((_, i) => landAt(i, items.length, frames));
  const tall = BOX.V;
  const width = tall ? 840 : Math.min(400, (1560 - (items.length - 1) * 70) / items.length);
  return (
    <Frame gap={60}>
      {v.headline ? <Head v={v} pal={pal} size={fit(v.headline, 100, 1400, 0.42)} /> : null}
      <div style={{display: 'flex', flexDirection: tall ? 'column' : 'row', alignItems: 'center', justifyContent: 'center'}}>
        {items.map((it, i) => {
          const e = spring({frame: frame - ats[i], fps: 30, config: {damping: 13, mass: 0.5}});
          const color = toneColor(pal, it.tone, i === items.length - 1 ? pal.accent : pal.ink);
          const arrow = interpolate(frame, [ats[i] + 4, (ats[i + 1] ?? ats[i] + 14)], [0, 1], clamp);
          return (
            <div key={i} style={{display: 'flex', flexDirection: tall ? 'column' : 'row', alignItems: 'center'}}>
              <div style={{width, padding: '22px 26px', border: `2px solid ${color}`, borderRadius: 10, background: pal.card, opacity: Math.min(1, e * 1.5),
                transform: `scale(${0.9 + 0.1 * e})`, display: 'flex', flexDirection: 'column', gap: 8}}>
                {it.label ? <div style={{fontFamily: MONO, fontSize: 17, letterSpacing: '0.16em', textTransform: 'uppercase', color: pal.dim, lineHeight: 1.35}}>{it.label}</div> : null}
                <div style={{fontFamily: DISPLAY, fontSize: flowSize(it.text || it.display, width - 52), lineHeight: 0.95, color: it.tone ? color : pal.ink}}>{it.text || it.display}</div>
              </div>
              {i < items.length - 1 ? (
                tall ? (
                  <div style={{width: 3, height: 50 * arrow, background: pal.bad}} />
                ) : (
                  <svg width={70} height={30} style={{flex: 'none'}}>
                    <line x1={8} y1={15} x2={8 + 50 * arrow} y2={15} stroke={pal.bad} strokeWidth={3} />
                    {arrow > 0.9 ? <polyline points="48,6 60,15 48,24" fill="none" stroke={pal.bad} strokeWidth={3} /> : null}
                  </svg>
                )
              ) : null}
            </div>
          );
        })}
      </div>
      <Sub text={v.sub} pal={pal} delay={ats[ats.length - 1] + 8} size={34} />
    </Frame>
  );
};

// Rows that tick (good), cross (bad) or wait in an empty box, in the order they are said.
const Checklist: React.FC<{v: Visual; frames: number; pal: Pal; plain?: boolean}> = ({v, frames, pal, plain}) => {
  const frame = useCurrentFrame();
  const items = v.items.slice(0, plain ? 5 : 4);
  const ats = items.map((_, i) => landAt(i, items.length, frames, 10));
  return (
    <Frame justify="center" gap={34}>
      <Head v={v} pal={pal} size={fit(v.headline, 120, 1400, 0.42)} />
      {v.sub ? <Sub text={v.sub} pal={pal} size={34} delay={6} /> : null}
      <div style={{display: 'flex', flexDirection: 'column', gap: 30, marginTop: 10}}>
        {items.map((it, i) => {
          const e = spring({frame: frame - ats[i], fps: 30, config: {damping: 13, mass: 0.6}});
          const tick = spring({frame: frame - ats[i] - 8, fps: 30, config: {damping: 10, mass: 0.4}});
          const now = frame >= ats[i];
          const box = it.tone === 'bad' ? pal.bad : pal.good;
          const done = it.tone === 'good' || it.tone === 'bad' || plain;
          return (
            <div key={i} style={{display: 'flex', alignItems: 'center', gap: 34, opacity: now ? Math.min(1, e * 1.5) : 0.18, transform: `translateX(${now ? (1 - e) * -30 : 0}px)`}}>
              {plain ? <div style={{width: 18, height: 18, borderRadius: 9, background: toneColor(pal, it.tone, pal.accent), flex: 'none'}} /> : (
                <div style={{width: 66, height: 66, borderRadius: 12, flex: 'none', border: `3px solid ${done && now ? box : '#4A515B'}`, background: done && now ? box : 'transparent',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', transform: `scale(${done && now ? 0.85 + 0.15 * tick : 1})`}}>
                  {done && now && tick > 0.05 ? (it.tone === 'bad' ? <X size={44} color="#0B0D10" strokeWidth={3.5} /> : <Check size={44} color="#0B0D10" strokeWidth={3.5} />) : null}
                </div>
              )}
              <div style={{display: 'flex', flexDirection: 'column', gap: 6}}>
                {it.label ? <div style={{fontFamily: MONO, fontSize: 20, letterSpacing: '0.2em', textTransform: 'uppercase', color: pal.dim}}>{it.label}</div> : null}
                <div style={{fontFamily: SANS, fontWeight: 600, fontSize: fit(it.text, 54, BOX.V ? 1500 : 2400, 0.5), color: pal.ink, lineHeight: 1.2}}>{it.text}</div>
              </div>
            </div>
          );
        })}
      </div>
    </Frame>
  );
};

// A count made visible: rows of one icon, lighting up; the marked ones in the tone's colour.
const Grid: React.FC<{v: Visual; frames: number; pal: Pal}> = ({v, frames, pal}) => {
  const frame = useCurrentFrame();
  const total = Math.max(2, Math.min(120, Math.round(v.items[0]?.value || 40)));
  const marked = Math.max(0, Math.min(total, Math.round(v.items[1]?.value || 0)));
  const Icon = iconFor(v.icons[0] || 'square');
  const cols = BOX.V ? Math.min(10, Math.ceil(Math.sqrt(total * 0.8))) : Math.min(20, Math.ceil(Math.sqrt(total * 2.6)));
  const cell = Math.min(BOX.V ? 90 : 84, Math.floor((BOX.V ? 940 : 1600) / cols));
  const lit = interpolate(frame, [6, Math.max(20, frames * 0.5)], [0, total], clamp);
  const markFrom = Math.max(24, frames * 0.55);
  const markColor = toneColor(pal, v.items[1]?.tone || v.tone || 'bad', pal.bad);
  // The marked cells are scattered, the same ones every frame.
  const order = Array.from({length: total}, (_, i) => i).sort((a, b) => random(`g${a}`) - random(`g${b}`));
  const isMarked = new Set(order.slice(0, Math.round(interpolate(frame, [markFrom, markFrom + 20], [0, marked], clamp))));
  return (
    <Frame gap={30}>
      <div style={{display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 40, flexWrap: 'wrap'}}>
        <Head v={v} pal={pal} size={fit(v.headline, 100, 1100, 0.42)} />
        <div style={{display: 'flex', gap: 30}}>
          {v.items[0]?.display ? <Tag text={`${v.items[0].label ? v.items[0].label + ': ' : ''}${v.items[0].display}`} color={pal.dim} delay={4} size={24} /> : null}
          {marked && v.items[1]?.display ? <Tag text={`${v.items[1].label ? v.items[1].label + ': ' : ''}${v.items[1].display}`} color={markColor} delay={markFrom} size={24} solid /> : null}
        </div>
      </div>
      <div style={{display: 'grid', gridTemplateColumns: `repeat(${cols}, ${cell}px)`, gap: 0, justifyContent: 'center', borderTop: `1px solid ${pal.line}`, paddingTop: 20}}>
        {Array.from({length: total}, (_, i) => {
          const on = i < lit;
          const m = isMarked.has(i);
          return (
            <div key={i} style={{width: cell, height: cell, display: 'flex', alignItems: 'center', justifyContent: 'center', opacity: on ? 1 : 0.08}}>
              <Icon size={cell * 0.62} color={m ? markColor : '#C9CDD3'} strokeWidth={1.6} style={{filter: m ? `drop-shadow(0 0 8px ${markColor})` : undefined}} />
            </div>
          );
        })}
      </div>
      <Sub text={v.sub} pal={pal} size={30} delay={markFrom} />
    </Frame>
  );
};

// A terminal (or code) window, its lines typed in; a 'warn' line gets a red bar, 'bad' lines are red.
const Terminal: React.FC<{v: Visual; frames: number; pal: Pal}> = ({v, frames, pal}) => {
  const frame = useCurrentFrame();
  const lines = v.items.slice(0, 7);
  const chars = lines.map((l) => (l.label ? l.label + ' ' : '') + l.text);
  const total = chars.reduce((s, c) => s + c.length, 0);
  const typed = interpolate(frame, [6, Math.max(24, frames * 0.7)], [0, total], clamp);
  const e = useIn(0);
  let used = 0;
  const blink = Math.floor(frame / 15) % 2 === 0;
  return (
    <Frame>
      {v.kicker ? <Kicker text={v.kicker} pal={pal} /> : null}
      <div style={{background: '#06080C', border: `1px solid ${pal.line}`, borderRadius: 14, overflow: 'hidden', boxShadow: '0 40px 90px rgba(0,0,0,0.5)',
        opacity: Math.min(1, e * 1.4), transform: `translateY(${(1 - e) * 30}px)`, maxWidth: BOX.V ? undefined : 1300}}>
        <div style={{display: 'flex', alignItems: 'center', gap: 12, padding: '16px 22px', borderBottom: `1px solid ${pal.line}`, background: '#0C1016'}}>
          {[0, 1, 2].map((k) => <span key={k} style={{width: 14, height: 14, borderRadius: 7, background: '#3A414B'}} />)}
          <span style={{marginLeft: 14, fontFamily: MONO, fontSize: 20, color: pal.dim}}>{v.headline || 'terminal'}</span>
        </div>
        <div style={{padding: '30px 34px 40px', display: 'flex', flexDirection: 'column', gap: 16, minHeight: 300}}>
          {lines.map((l, i) => {
            const full = chars[i];
            const show = Math.max(0, Math.min(full.length, Math.floor(typed - used)));
            used += full.length;
            if (show <= 0) return null;
            const text = full.slice(0, show);
            const color = l.tone === 'bad' ? pal.bad : l.tone === 'good' ? pal.good : l.tone === 'info' ? pal.info : l.label === '#' ? '#7D848E' : pal.ink;
            return (
              <div key={i} style={{fontFamily: MONO, fontWeight: l.tone === 'warn' ? 700 : 500, fontSize: BOX.V ? 30 : 36, color: l.tone === 'warn' ? pal.ink : color,
                whiteSpace: 'pre-wrap', padding: l.tone === 'warn' ? '10px 16px' : 0, borderLeft: l.tone === 'warn' ? `5px solid ${pal.bad}` : undefined,
                background: l.tone === 'warn' ? '#2A1215' : undefined}}>
                {text}{show < full.length || (i === lines.length - 1 && blink) ? <span style={{color: pal.accent}}>▌</span> : null}
              </div>
            );
          })}
        </div>
      </div>
      <Sub text={v.sub} pal={pal} size={30} delay={Math.round(frames * 0.6)} />
    </Frame>
  );
};

// A profile card for one organisation or thing: a coloured bar, the name, a status badge, what it is.
const Card: React.FC<{v: Visual; pal: Pal}> = ({v, pal}) => {
  const e = useIn(0);
  const color = toneColor(pal, v.tone || 'good', pal.good);
  return (
    <Frame align="flex-start">
      <Kicker text={v.kicker} pal={pal} />
      <div style={{background: pal.card, borderLeft: `6px solid ${color}`, borderRadius: 6, padding: '40px 50px', display: 'flex', flexDirection: 'column', gap: 22,
        minWidth: BOX.V ? undefined : 900, opacity: Math.min(1, e * 1.4), transform: `translateX(${(1 - e) * -40}px)`}}>
        <div style={{display: 'flex', alignItems: 'center', gap: 40, justifyContent: 'space-between', flexWrap: 'wrap'}}>
          <div style={{fontFamily: SANS, fontWeight: 800, fontSize: fit(v.headline, 96, 1100, 0.55), color: pal.ink, letterSpacing: '-0.02em'}}>{v.headline}</div>
          {v.tags?.[0] ? <Tag text={`${v.tone === 'bad' ? '✕' : '✓'} ${v.tags[0]}`} color={color} delay={14} size={26} solid /> : null}
        </div>
        {v.sub ? <div style={{fontFamily: SANS, fontWeight: 600, fontSize: 40, color: '#A5ACB6'}}>{v.sub}</div> : null}
        {v.tags && v.tags.length > 1 ? <div style={{display: 'flex', gap: 16}}>{v.tags.slice(1).map((t, i) => <Tag key={i} text={t} color={pal.dim} delay={20 + i * 4} size={20} />)}</div> : null}
      </div>
    </Frame>
  );
};

// One value on a range: the ends in mono, the marker sliding to its place while the figure counts.
const Scale: React.FC<{v: Visual; frames: number; pal: Pal}> = ({v, frames, pal}) => {
  const frame = useCurrentFrame();
  const items = v.items;
  const lo = items[0], hi = items[items.length - 1];
  const marks = items.slice(1, -1).length ? items.slice(1, -1) : [items[items.length - 1]];
  const W = BOX.V ? 900 : 1400;
  const span = (hi.value - lo.value) || 1;
  const go = interpolate(frame, [8, Math.max(30, frames * 0.5)], [0, 1], {...clamp, easing: Easing.out(Easing.cubic)});
  return (
    <Frame gap={60}>
      <Head v={v} pal={pal} size={fit(v.headline, 90, 1300, 0.42)} />
      <div style={{position: 'relative', width: W, height: 260, alignSelf: 'center'}}>
        <div style={{position: 'absolute', left: 0, right: 0, top: 170, height: 8, background: '#2A3038', borderRadius: 4}} />
        {[lo, hi].map((it, k) => (
          <div key={k} style={{position: 'absolute', top: 196, [k ? 'right' : 'left']: 0, fontFamily: MONO, fontSize: 22, color: pal.dim, letterSpacing: '0.1em'}}>{it.display || it.value}</div>
        ))}
        {marks.map((m, i) => {
          const at = Math.max(0, Math.min(1, (m.value - lo.value) / span)) * go;
          const color = toneColor(pal, m.tone || 'bad', pal.bad);
          const parsed = parseNumber(m.display);
          const shown = parsed && go < 1 ? formatNumber(parsed.value * go, parsed) : m.display;
          return (
            <React.Fragment key={i}>
              <div style={{position: 'absolute', left: W * at - 22, top: 162, width: 44, height: 24, borderRadius: 4, background: color, boxShadow: `0 0 24px ${color}`}} />
              <div style={{position: 'absolute', left: W * at - 250, width: 500, top: 10, textAlign: 'center', fontFamily: DISPLAY, fontSize: 110, color: pal.ink, lineHeight: 1}}>{shown}</div>
              {m.label ? <div style={{position: 'absolute', left: W * at - 250, width: 500, top: 124, textAlign: 'center', fontFamily: MONO, fontSize: 18, letterSpacing: '0.16em', textTransform: 'uppercase', color: pal.dim}}>{m.label}</div> : null}
            </React.Fragment>
          );
        })}
      </div>
      <Sub text={v.sub} pal={pal} size={32} delay={Math.round(frames * 0.5)} />
    </Frame>
  );
};

// A strip of days: small mono above, big day below; the marked ones light in the accent with a note.
const Dates: React.FC<{v: Visual; frames: number; pal: Pal}> = ({v, frames, pal}) => {
  const frame = useCurrentFrame();
  const items = v.items.slice(0, 7);
  const ats = items.map((_, i) => landAt(i, items.length, frames * 0.6));
  const tile = BOX.V ? 118 : 130;
  return (
    <Frame gap={40}>
      <Head v={v} pal={pal} size={fit(v.headline, 110, 1400, 0.42)} />
      <div style={{display: 'flex', gap: 18, flexWrap: 'wrap'}}>
        {items.map((it, i) => {
          const e = spring({frame: frame - ats[i], fps: 30, config: {damping: 13, mass: 0.5}});
          const hot = !!it.tone;
          const color = toneColor(pal, it.tone, pal.accent);
          const lit = hot && frame > Math.max(26, frames * 0.55);
          return (
            <div key={i} style={{width: tile, height: tile * 1.08, borderRadius: 12, background: '#11151B', border: `2px solid ${lit ? color : pal.line}`,
              display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 4, opacity: Math.min(1, e * 1.4),
              transform: `translateY(${(1 - e) * 24}px)`, boxShadow: lit ? `0 0 30px ${color}55` : 'none'}}>
              <div style={{fontFamily: MONO, fontSize: 18, letterSpacing: '0.16em', color: lit ? color : pal.dim, textTransform: 'uppercase'}}>{it.label}</div>
              <div style={{fontFamily: DISPLAY, fontSize: fit(it.text || it.display, 76, tile - 16, 0.46), color: lit ? pal.ink : '#C9CDD3', lineHeight: 1}}>{it.text || it.display}</div>
            </div>
          );
        })}
      </div>
      {v.sub ? <div style={{fontFamily: MONO, fontSize: 22, letterSpacing: '0.18em', textTransform: 'uppercase', color: pal.dim,
        opacity: frame > Math.max(26, frames * 0.55) ? 1 : 0}}>↑ {v.sub}</div> : null}
    </Frame>
  );
};

// A bill: rows printed one by one with dotted leaders, the last row the total in the accent.
const Receipt: React.FC<{v: Visual; frames: number; pal: Pal}> = ({v, frames, pal}) => {
  const frame = useCurrentFrame();
  const rows = v.items.slice(0, 6);
  const ats = rows.map((_, i) => landAt(i, rows.length, frames));
  const e = useIn(0);
  const zig = 'polygon(' + Array.from({length: 31}, (_, i) => `${(i * 100) / 30}% ${i % 2 ? 0 : 14}px`).join(',') + ', 100% 100%, 0 100%)';
  return (
    <Frame align="center">
      <div style={{width: BOX.V ? 860 : 820, background: '#E9E5DA', color: '#16181C', clipPath: zig, padding: '50px 54px 46px', fontFamily: MONO,
        boxShadow: '0 40px 90px rgba(0,0,0,0.5)', transform: `translateY(${(1 - e) * 80}px) rotate(${-1.2 + random(v.headline) * 2.4}deg)`, opacity: Math.min(1, e * 1.5)}}>
        <div style={{textAlign: 'center', fontWeight: 700, fontSize: 30, letterSpacing: '0.24em', textTransform: 'uppercase'}}>{v.headline || 'Receipt'}</div>
        {v.kicker ? <div style={{textAlign: 'center', fontSize: 18, letterSpacing: '0.2em', textTransform: 'uppercase', color: '#6A6E75', marginTop: 8}}>{v.kicker}</div> : null}
        <div style={{borderTop: '2px dashed #9A9EA5', margin: '26px 0 18px'}} />
        {rows.map((r, i) => {
          const total = i === rows.length - 1 && rows.length > 1;
          if (frame < ats[i]) return null;
          return (
            <div key={i} style={{display: 'flex', alignItems: 'baseline', gap: 12, fontSize: total ? 40 : 28, fontWeight: total ? 700 : 500, marginTop: total ? 22 : 10,
              paddingTop: total ? 16 : 0, borderTop: total ? '2px solid #16181C' : undefined, color: total ? '#16181C' : '#2A2D33'}}>
              <span style={{textTransform: 'uppercase', letterSpacing: '0.06em'}}>{r.label}</span>
              <span style={{flex: 1, borderBottom: total ? 'none' : '2px dotted #A9ADB3', transform: 'translateY(-6px)'}} />
              <span style={{color: total ? toneColor(pal, r.tone || 'warn', pal.accent) : undefined, background: total ? '#16181C' : undefined, padding: total ? '2px 12px' : 0}}>{r.display || r.text}</span>
            </div>
          );
        })}
      </div>
      <Sub text={v.sub} pal={pal} size={32} align="center" delay={ats[ats.length - 1] + 6} />
    </Frame>
  );
};

// ---------- the break into a chapter ----------

// A folder tab with the chapter's number and title over its line, and above it every chapter as a tab of the whole
// video: the ones done ticked in green, this one lit.
export const BriefBreak: React.FC<{chapter: Chapter; chapters: Chapter[]; frames: number; pal: Pal}> = ({chapter, chapters, frames, pal}) => {
  const frame = useCurrentFrame();
  const exit = exitProgress(frame, frames, 8);
  const list = chapters.filter((c) => c.card > 0);
  const k = Math.max(0, list.findIndex((c) => c.index === chapter.index));
  const e = useIn(4);
  const text = (chapter.text || '').trim();
  const a = AREA();
  const many = list.length > 6;
  return (
    <div style={{position: 'absolute', inset: 0, opacity: 1 - exit}}>
      <div style={{position: 'absolute', left: a.left, right: a.right, top: a.top + 10, display: 'flex', gap: 18}}>
        {(many ? list.slice(Math.max(0, k - 2), k + 3) : list).map((c) => {
          const i = list.indexOf(c);
          const done = i < k, now = i === k;
          const p = interpolate(frame, [6 + i * 2, 18 + i * 2], [0, 1], clamp);
          return (
            <div key={c.index} style={{flex: 1, minWidth: 0}}>
              <div style={{height: 4, background: '#232A33', borderRadius: 2}}>
                <div style={{height: 4, width: `${(done ? 1 : now ? p : 0) * 100}%`, background: done ? '#2F7F61' : pal.good, borderRadius: 2}} />
              </div>
              <div style={{marginTop: 14, fontFamily: MONO, fontSize: 17, letterSpacing: '0.16em', textTransform: 'uppercase', whiteSpace: 'nowrap', overflow: 'hidden',
                textOverflow: 'ellipsis', color: now ? pal.ink : done ? '#2F9F75' : '#59606A'}}>
                {String(i + 1).padStart(2, '0')} · {c.title}{done ? ' ✓' : ''}
              </div>
            </div>
          );
        })}
      </div>
      <div style={{position: 'absolute', left: a.left, right: a.right, top: BOX.V ? 700 : 330, transform: `translateY(${(1 - e) * 40}px)`, opacity: Math.min(1, e * 1.4)}}>
        <div style={{display: 'inline-flex', alignItems: 'baseline', gap: 26, background: pal.card, padding: '22px 44px 16px', borderRadius: '14px 14px 0 0'}}>
          <span style={{fontFamily: MONO, fontSize: 26, color: pal.dim}}>{String(k + 1).padStart(2, '0')}</span>
          <span style={{fontFamily: DISPLAY, fontSize: fit(chapter.title, 96, BOX.V ? 760 : 1200, 0.44), color: pal.ink, lineHeight: 1}}>{chapter.title}</span>
        </div>
        <div style={{background: pal.card, borderRadius: '0 14px 14px 14px', padding: '44px 48px', minHeight: 140, display: 'flex', alignItems: 'center'}}>
          {text && text.toLowerCase() !== chapter.title.toLowerCase() ? (
            <Headline text={text} pal={pal} size={fit(text, 76, BOX.V ? 1400 : 2600, 0.42)} delay={10} color="#C9CDD3" />
          ) : <div style={{height: 6, width: 240 * interpolate(frame, [8, 24], [0, 1], clamp), background: pal.accent}} />}
        </div>
      </div>
    </div>
  );
};

// The camera of a Briefing beat: the page holds still; only full-frame media keep their own moves.
export const BRIEF_STILL = new Set(['title', 'stat', 'timeline', 'compare', 'steps', 'icons', 'quote', 'keyword', 'chart', 'flow', 'checklist', 'grid',
  'terminal', 'card', 'scale', 'dates', 'receipt']);
export const isBriefing = (look?: Look) => look?.template === 'briefing';
