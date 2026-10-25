import React from 'react';
import {AbsoluteFill, Sequence, interpolate, random, useCurrentFrame, useVideoConfig} from 'remotion';
import {Bean, KID, SEAT} from './Bean';
import {ShadowView} from './Shadow';
import {DESK_TOP, FLOOR, H, SetView, W, px, setInfo} from './Sets';
import {CalendarInsert, ClockInsert, GraphInsert, Grain, ObjectInsert, PhoneInsert} from './Inserts';
import {Bubbles, Caption, Hud, Notes, Pills, Stamp, TitleCard, Whisper, useStickyFonts} from './Overlay';
import type {Actor, Cast, Shot, StickyProps} from './types';

// The "Sticky" composition (reelgen/sticky/): a voiceless animated short film, shot by shot. A shot is a set with
// its actors and the inner voice, or an insert (the phone, the clock, the calendar, a drawing, a graph), a face
// close-up, a split screen, a card of words, or the title. Shots fade, dip to black or cut into each other; a grade
// (grey at the low point, warm when he is better) and a slow push keep the picture alive; the HUD stays on top.
// Picture only: the soundtrack is mixed from the same timeline by reelgen/sticky/mixdown.py.

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;
const FADE = 12; // frames a fade overlaps the shot before
const ZOOM = 1.28; // how close a room shot sits

const GRADES: Record<string, string> = {
  grey: 'grayscale(0.92) brightness(0.78) contrast(1.05)',
  cold: 'saturate(0.75) hue-rotate(-12deg) brightness(0.88)',
  warm: 'sepia(0.22) saturate(1.2) brightness(1.06)',
};

// Where an actor stands and sits: on the set's own bed, couch or chair when the pose needs one.
const placeActor = (a: Actor, shot: Shot, t: number, dur: number) => {
  const info = setInfo(shot.set ?? 'void');
  const f = info.furniture;
  let x = a.x;
  let seat = SEAT.chair;
  if ((a.pose === 'lie' || a.pose === 'sleep' || a.pose === 'sit_bed') && f.bed) {
    x = a.pose === 'sit_bed' ? Math.min(Math.max(x, f.bed[0]), f.bed[1]) : (f.bed[0] + f.bed[1]) / 2 + 2;
    seat = SEAT.bed;
  } else if (['sit', 'slump', 'shake', 'guitar'].includes(a.pose) && f.couch) {
    x = Math.min(Math.max(x, f.couch[0]), f.couch[1]);
    seat = SEAT.couch;
  } else if (['sit', 'type', 'write', 'slump', 'shake', 'guitar'].includes(a.pose) && f.chair !== undefined) {
    if (Math.abs(x - f.chair) < 18 || a.pose === 'type' || a.pose === 'write') x = f.chair - 1;
  } else if (['sit', 'slump', 'guitar'].includes(a.pose) && !f.chair && !f.couch) {
    seat = SEAT.floor;
  }
  if ((a.pose === 'walk' || a.pose === 'run' || a.pose === 'climb') && a.to !== undefined) {
    const k = interpolate(t, [0, dur], [0, 1], clamp);
    x = a.x + (a.to - a.x) * k;
  }
  // someone moving always faces the way they go (the writer's own facing made them walk backwards)
  const moving = (a.pose === 'walk' || a.pose === 'run' || a.pose === 'climb') && a.to !== undefined && a.to !== a.x;
  const facing = moving ? (a.to! < a.x ? 'left' : 'right') : a.facing ?? 'right';
  const xpx = px(x);
  const atDesk = (a.pose === 'type' || a.pose === 'write') && f.desk !== undefined && f.chair !== undefined;
  return {xpx, y: info.floorAt(xpx), seat, facing: facing as 'left' | 'right',
    desk: atDesk ? DESK_TOP : undefined, screen: atDesk && !!info.screen};
};

// Rain over the whole scene: slanted streaks falling at their own speeds (deterministic per streak), a cool veil.
const Rain: React.FC<{t: number}> = ({t}) => (
  <g stroke="#B9CBE6" strokeLinecap="round">
    <rect width={W} height={H} fill="#7F93B5" opacity={0.08} stroke="none" />
    {Array.from({length: 140}, (_, i) => {
      const sp = 900 + random(`rs${i}`) * 500;
      const x0 = random(`rx${i}`) * (W + 300);
      const y = ((random(`ry${i}`) * (H + 200) + t * sp) % (H + 200)) - 100;
      const x = x0 - (y + 100) * 0.18;
      return <line key={i} x1={x} y1={y} x2={x - 7} y2={y + 38} strokeWidth={2} opacity={0.28 + random(`ro${i}`) * 0.3} />;
    })}
  </g>
);

// People never overlap: two people side by side on a bench sat 8 apart (130 px) with their knees inside each other.
// Everyone not walking keeps a gap (wider when both sit: the knees stick out), pushed apart from the left and then
// moved back so the group stays where the writer put it. Two seated side by side face each other.
const SEATED = ['sit', 'sit_bed', 'slump', 'shake', 'guitar', 'type', 'write'];
const MOVING = ['walk', 'run', 'climb'];
const spread = (placed: {a: Actor; xpx: number; y: number; facing: 'left' | 'right'}[], shot: Shot) => {
  const still = placed.filter((p) => !MOVING.includes(p.a.pose)).sort((a, b) => a.xpx - b.xpx);
  if (still.length < 2) return;
  const before = still.reduce((s, p) => s + p.xpx, 0) / still.length;
  for (let i = 1; i < still.length; i++) {
    const both = SEATED.includes(still[i].a.pose) && SEATED.includes(still[i - 1].a.pose);
    const gap = both ? 220 : still[i].a.pose === 'pushup' || still[i - 1].a.pose === 'pushup' ? 300 : 170;
    if (still[i].xpx - still[i - 1].xpx < gap) still[i].xpx = still[i - 1].xpx + gap;
    if (both && still.length === 2) { still[0].facing = 'right'; still[1].facing = 'left'; }
  }
  const after = still.reduce((s, p) => s + p.xpx, 0) / still.length;
  const info = setInfo(shot.set ?? 'void');
  for (const p of still) {
    p.xpx = Math.min(W - 120, Math.max(120, p.xpx + before - after));
    p.y = info.floorAt(p.xpx);
  }
};

export const SceneView: React.FC<{shot: Shot; t: number; dur: number; cast: Cast[]; accent: string; heads?: Record<string, [number, number]>}> = ({shot, t, dur, cast, accent, heads}) => {
  const byId = Object.fromEntries(cast.map((c) => [c.id, c]));
  const hero = cast[0];
  const grey = shot.grade === 'grey';
  const actors = (shot.actors ?? []).filter((a) => byId[a.id]);
  const placed = actors.map((a) => ({a, ...placeActor(a, shot, t, dur)}));
  spread(placed, shot);
  for (const p of placed) {
    const k = byId[p.a.id].kid ? KID : 1;
    const low = p.a.pose === 'lie' || p.a.pose === 'sleep' ? 230 : p.a.pose === 'pushup' ? 170 : p.a.pose === 'curl' || p.a.pose === 'kneel' ? 260 : 330;
    const ahead = p.a.pose === 'pushup' ? (p.facing === 'left' ? -60 : 60) * k : 0;
    if (heads) heads[p.a.id] = [p.xpx + ahead, p.y - low * k];
  }
  const sh = shot.shadow;
  const heroX = placed[0]?.xpx ?? W / 2;
  return (
    <g>
      <SetView name={shot.set ?? 'void'} light={shot.light ?? 'night'} clock={shot.clock} t={t} accent={accent} />
      {placed.some((p) => p.a.glow) ? placed.filter((p) => p.a.glow).map((p) => (
        <ellipse key={p.a.id} cx={p.xpx} cy={p.y - 240} rx={150} ry={120} fill="#8FB6FF" opacity={0.07} />
      )) : null}
      {sh ? (
        <g transform={`translate(${px(sh.x)},${setInfo(shot.set ?? 'void').floorAt(px(sh.x))})`}>
          <ShadowView s={sh} t={t} dur={dur} accent={accent} cast={sh.copy ? byId[sh.copy] : undefined} facing={px(sh.x) > heroX ? -1 : 1} />
        </g>
      ) : null}
      {placed.map((p, i) => (
        <g key={i} transform={`translate(${p.xpx},${p.y})`}>
          <Bean cast={byId[p.a.id]} actor={{...p.a, facing: p.facing}} t={t} dur={dur} seat={p.seat} grey={grey && byId[p.a.id] !== hero ? true : undefined}
            desk={p.desk} screen={p.screen} company={placed.length > 1} />
        </g>
      ))}
      {shot.rain ? <Rain t={t} /> : null}
      {sh && !grey ? <rect width={W} height={H} fill={accent} opacity={0.06} /> : null}
      {shot.notes?.length ? <Notes notes={shot.notes} t={t} dur={dur} accent="#E5484D" /> : null}
      {shot.pills?.length ? <Pills pills={shot.pills} around={[heroX, placed[0]?.y ?? FLOOR]} t={t} accent={accent} /> : null}
    </g>
  );
};

const ShotPicture: React.FC<{shot: Shot; t: number; dur: number; p: StickyProps; heads: Record<string, [number, number]>}> = ({shot, t, dur, p, heads}) => {
  const hero = p.cast[0];
  switch (shot.kind) {
    case 'phone':
      return <PhoneInsert p={shot.phone ?? {mode: 'lock'}} t={t} dur={dur} accent={p.accent} hero={hero} />;
    case 'clock':
      return <ClockInsert time={shot.clock ?? '3:17'} />;
    case 'calendar':
      return <CalendarInsert c={shot.calendar ?? {month: 'JAN', checks: 0}} t={t} dur={dur} accent={p.accent} />;
    case 'object':
      return <ObjectInsert o={shot.object ?? {kind: 'note'}} t={t} dur={dur} accent={p.accent} />;
    case 'graph':
      return <GraphInsert g={shot.graph ?? {shape: 'wave'}} t={t} dur={dur} accent={p.accent} />;
    case 'card':
      return <rect width={W} height={H} fill="#0E0F12" />;
    case 'title':
      return <TitleCard title={p.title} tagline={p.tagline} t={t} accent={p.accent} />;
    case 'face': {
      const who = p.cast.find((c) => c.id === shot.focus) ?? hero;
      const a = (shot.actors ?? []).find((x) => x.id === who.id) ?? {id: who.id, x: 50, pose: 'stand' as const, face: 'neutral' as const};
      heads[who.id] = [W / 2 + 120, 260];
      return (
        <g>
          <g style={{filter: 'blur(7px) brightness(0.5)'}}><SetView name={shot.set ?? 'void'} light={shot.light ?? 'night'} clock={shot.clock} t={t} accent={p.accent} /></g>
          <g transform={`translate(${W / 2},${560 + 236 * 3})`}><Bean cast={who} actor={{...a, pose: a.pose === 'lie' ? 'stand' : a.pose}} t={t} dur={dur} seat={SEAT.chair} scale={3} /></g>
        </g>
      );
    }
    case 'split': {
      const half = (s: Shot | undefined, side: 0 | 1) => s ? (
        <g clipPath={`url(#half${side})`}>
          <g transform={`translate(${side ? W / 4 : -W / 4},0)`}><SceneView shot={{...s, start: shot.start, duration: shot.duration}} t={t} dur={dur} cast={p.cast} accent={p.accent} heads={heads} /></g>
        </g>
      ) : null;
      return (
        <g>
          <defs><clipPath id="half0"><rect width={W / 2} height={H} /></clipPath><clipPath id="half1"><rect x={W / 2} width={W / 2} height={H} /></clipPath></defs>
          {half(shot.left, 0)}
          {half(shot.right, 1)}
          <line x1={W / 2} y1={0} x2={W / 2} y2={H} stroke="#E8E8EC" strokeWidth={3} opacity={0.8} />
        </g>
      );
    }
    default:
      return <SceneView shot={shot} t={t} dur={dur} cast={p.cast} accent={p.accent} heads={heads} />;
  }
};

const ShotView: React.FC<{shot: Shot; p: StickyProps; first: boolean}> = ({shot, p, first}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = frame / fps;
  const dur = shot.duration;
  const heads: Record<string, [number, number]> = {};
  const fadeIn = shot.transition === 'fade' && !first ? interpolate(frame, [0, FADE], [0, 1], clamp) : 1;
  const push = shot.camera === 'push' ? interpolate(t, [0, dur], [1, 1.06], clamp) : 1;
  const drift = shot.camera === 'drift' ? interpolate(t, [0, dur], [-20, 20], clamp) : 0;
  const filter = GRADES[shot.grade ?? 'normal'];
  // Scene shots sit closer than the set's full width, like the reference films: a zoom about the floor line, centred
  // on the actors (kept inside the set's edges). Bubble anchors follow the same zoom.
  const zoomed = shot.kind === 'scene' && shot.set && shot.set !== 'void' && shot.set !== 'stairs';
  const xs = (shot.actors ?? []).map((a) => px(a.to !== undefined ? (a.x + a.to) / 2 : a.x)).concat(shot.shadow ? [px(shot.shadow.x)] : []);
  const z = zoomed ? (shot.shadow?.size === 'giant' ? 1.05 : ZOOM) : 1;
  const fx = zoomed ? Math.min(W - W / (2 * z), Math.max(W / (2 * z), xs.length ? (Math.min(...xs) + Math.max(...xs)) / 2 : W / 2)) : W / 2;
  const picture = <ShotPicture shot={shot} t={t} dur={dur} p={p} heads={heads} />;
  for (const k of Object.keys(heads)) heads[k] = [W / 2 + (heads[k][0] - fx) * z, FLOOR + (heads[k][1] - FLOOR) * z];
  return (
    <AbsoluteFill style={{opacity: fadeIn}}>
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} style={{position: 'absolute', inset: 0}}>
        <defs>
          <radialGradient id="stPhoneGlow"><stop offset="0" stopColor="#BFD8FF" stopOpacity={0.4} /><stop offset="1" stopColor="#BFD8FF" stopOpacity={0} /></radialGradient>
        </defs>
        <g style={{filter}} transform={`translate(${W / 2 + drift},${H / 2}) scale(${push}) translate(${-W / 2},${-H / 2})`}>
          <g transform={`translate(${W / 2},${FLOOR}) scale(${z}) translate(${-fx},${-FLOOR})`}>{picture}</g>
        </g>
        {shot.whisper ? <Whisper w={shot.whisper} t={t} dur={dur} accent={p.accent} /> : null}
        {shot.bubbles?.length ? <Bubbles b={shot.bubbles} heads={heads} t={t} dur={dur} /> : null}
        {shot.stamp ? <Stamp text={shot.stamp} t={t} /> : null}
        {shot.caption?.lines?.length ? <Caption c={shot.caption} t={t} dur={dur} /> : null}
        <Grain frame={frame} />
      </svg>
      {shot.transition === 'black' && !first ? <AbsoluteFill style={{background: '#000', opacity: interpolate(frame, [0, 14], [1, 0], clamp)}} /> : null}
    </AbsoluteFill>
  );
};

const HudLayer: React.FC<{shot: Shot; prev: Shot | null; p: StickyProps}> = ({shot, prev, p}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  if (shot.kind === 'title' || shot.kind === 'card') return null;
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} style={{position: 'absolute', inset: 0}}>
      <Hud meter={p.meter} now={shot.meter ?? prev?.meter ?? []} before={prev?.meter ?? null} t={frame / fps} day={shot.day} time={shot.time} accent={p.accent} />
    </svg>
  );
};

export const Sticky: React.FC<StickyProps> = (p) => {
  useStickyFonts();
  const {fps} = useVideoConfig();
  const f = (s: number) => Math.round(s * fps);
  if (p.soundOnly) return null;
  // the meter's last value before each shot (a shot without one keeps the previous)
  let last: Shot | null = null;
  const prevs = p.shots.map((s) => {
    const before = last;
    if (s.meter?.length) last = s;
    return before;
  });
  return (
    <AbsoluteFill style={{background: '#000'}}>
      {p.shots.map((s, i) => {
        const next = p.shots[i + 1];
        const tail = next?.transition === 'fade' ? FADE : 0;
        return (
          <Sequence key={i} name={`${i + 1} ${s.kind}${s.set ? ' ' + s.set : ''}`} from={f(s.start)} durationInFrames={Math.max(1, f(s.duration) + tail)}>
            <ShotView shot={s} p={p} first={i === 0} />
          </Sequence>
        );
      })}
      {p.meter.kind !== 'none' || p.shots.some((s) => s.day || s.time) ? p.shots.map((s, i) => (
        <Sequence key={`h${i}`} name={`hud ${i + 1}`} from={f(s.start)} durationInFrames={Math.max(1, f(s.duration))}>
          <HudLayer shot={s} prev={prevs[i]} p={p} />
        </Sequence>
      )) : null}
    </AbsoluteFill>
  );
};
