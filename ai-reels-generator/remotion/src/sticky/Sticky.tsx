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

// Someone sitting where the set has no seat (the second person at a cafe with one chair, one moved aside on a bench)
// gets a stool under them at the seat's height: before, they sat on air.
const needStools = (placed: {a: Actor; xpx: number; y: number; seat: number}[], shot: Shot) => {
  const f = setInfo(shot.set ?? 'void').furniture;
  return placed.filter((p) => SEATED.includes(p.a.pose) && p.seat !== SEAT.bed && p.seat !== SEAT.floor).filter((p) => {
    if (p.seat === SEAT.chair && f.chair !== undefined && Math.abs(p.xpx - px(f.chair)) < 40) return false;
    if (p.seat === SEAT.couch && f.couch && p.xpx >= px(f.couch[0]) - 30 && p.xpx <= px(f.couch[1]) + 30) return false;
    return true;
  }).map((p) => ({x: p.xpx, y: p.y, seat: p.seat}));
};

const Stool: React.FC<{x: number; y: number; seat: number}> = ({x, y, seat}) => (
  <g stroke="#C9CDD6" strokeWidth={3} strokeLinecap="round">
    <line x1={x - 30} y1={y + seat + 8} x2={x - 40} y2={y} />
    <line x1={x + 30} y1={y + seat + 8} x2={x + 40} y2={y} />
    <line x1={x - 34} y1={y + seat / 2.2} x2={x + 34} y2={y + seat / 2.2} />
    <rect x={x - 46} y={y + seat - 4} width={92} height={14} rx={6} fill="#2A2D36" />
  </g>
);

// People in a shot together look at each other: everyone not crossing the frame turns toward the nearest other person
// (the writer's facing left a colleague saying 'morning sam!' with her back to him). Typing or writing faces the desk.
const faceEachOther = (placed: {a: Actor; xpx: number; facing: 'left' | 'right'}[]) => {
  if (placed.length < 2) return;
  for (const p of placed) {
    if (p.a.pose === 'type' || p.a.pose === 'write') { p.facing = 'right'; continue; }
    const crossing = MOVING.includes(p.a.pose) && p.a.to !== undefined && p.a.to !== p.a.x;
    if (crossing || p.a.pose === 'lie' || p.a.pose === 'sleep') continue;
    const others = placed.filter((o) => o !== p);
    const near = others.reduce((b, o) => (Math.abs(o.xpx - p.xpx) < Math.abs(b.xpx - p.xpx) ? o : b), others[0]);
    if (Math.abs(near.xpx - p.xpx) > 1) p.facing = near.xpx < p.xpx ? 'left' : 'right';
  }
};

export const SceneView: React.FC<{shot: Shot; t: number; dur: number; cast: Cast[]; accent: string; heads?: Record<string, [number, number]>; flat?: boolean}> = ({shot, t, dur, cast, accent, heads, flat}) => {
  const byId = Object.fromEntries(cast.map((c) => [c.id, c]));
  const hero = cast[0];
  const grey = shot.grade === 'grey';
  const actors = (shot.actors ?? []).filter((a) => byId[a.id]);
  const placed = actors.map((a) => ({a, ...placeActor(a, shot, t, dur)}));
  spread(placed, shot);
  faceEachOther(placed);
  const stools = needStools(placed, shot);
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
      {stools.map((st, i) => <Stool key={`st${i}`} x={st.x} y={st.y} seat={st.seat} />)}
      {placed.map((p, i) => (
        <g key={i} transform={`translate(${p.xpx},${p.y})`}>
          <Bean cast={byId[p.a.id]} actor={{...p.a, facing: p.facing}} t={t} dur={dur} seat={p.seat} grey={grey && byId[p.a.id] !== hero ? true : undefined}
            desk={p.desk} screen={p.screen} company={placed.length > 1}
            speed={p.a.to !== undefined && MOVING.includes(p.a.pose) ? Math.abs(px(p.a.to) - px(p.a.x)) / Math.max(0.5, dur) : 0} />
        </g>
      ))}
      {shot.rain ? <Rain t={t} /> : null}
      {sh && !grey ? <rect width={W} height={H} fill={accent} opacity={0.06} /> : null}
      {shot.notes?.length && !flat ? <Notes notes={shot.notes} t={t} dur={dur} accent="#E5484D" /> : null}
      {shot.pills?.length && !flat ? <Pills pills={shot.pills} around={[heroX, placed[0]?.y ?? FLOOR]} t={t} accent={accent} /> : null}
    </g>
  );
};

const ShotPicture: React.FC<{shot: Shot; t: number; dur: number; p: StickyProps; heads: Record<string, [number, number]>}> = ({shot, t, dur, p, heads}) => {
  const flat = !!p.vertical;
  const hero = p.cast[0];
  switch (shot.kind) {
    case 'phone':
      return <PhoneInsert p={shot.phone ?? {mode: 'lock'}} t={t} dur={dur} accent={p.accent} hero={hero} below={flat ? 700 : 0} />;
    case 'clock':
      return <ClockInsert time={shot.clock ?? '3:17'} />;
    case 'calendar':
      return <CalendarInsert c={shot.calendar ?? {month: 'JAN', checks: 0}} t={t} dur={dur} accent={p.accent} />;
    case 'object':
      return <ObjectInsert o={shot.object ?? {kind: 'note'}} t={t} dur={dur} accent={p.accent} below={flat ? 900 : 0} />;
    case 'graph':
      return <GraphInsert g={shot.graph ?? {shape: 'wave'}} t={t} dur={dur} accent={p.accent} />;
    case 'card':
      return <rect width={W} height={H} fill="#0E0F12" />;
    case 'title':
      return flat ? null : <TitleCard title={p.title} tagline={p.tagline} t={t} accent={p.accent} />;
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
      return <SceneView shot={shot} t={t} dur={dur} cast={p.cast} accent={p.accent} heads={heads} flat={flat} />;
  }
};

// ---------- the camera ----------
// Where a shot looks in the 16:9 world (Sets W x H): `fx`,`ay` = the world point at screen (FW/2, sy), `s` = its scale.
// A film (16:9) keeps its old framing. A Short (9:16, `p.vertical`) cuts a tall window out of the same world: a room
// at its full height around the people in it (about a third of the set's width), tighter for medium and close
// framings, each insert scaled to fill the phone screen (the phone itself nearly fills it).
export const VW = 1080, VH = 1920;
type Cam = {fx: number; ay: number; sy: number; s: number; bg: string};
const INSERT_CAM: Record<string, [number, number, number, string]> = { // 9:16: world centre x, y, scale, the frame's colour
  phone: [W / 2, 630, 1.45, '#0D0E13'], clock: [W / 2, H / 2, 1.1, '#0B0B0E'], calendar: [W / 2, 465, 1.25, '#121317'],
  object: [W / 2, H / 2 + 40, 0.92, '#121317'], graph: [W / 2, 560, 0.74, '#0F1014'],
};
const centreOf = (shot: Shot, subj?: Actor) => {
  const xs = (shot.actors ?? []).map((a) => px(a.to !== undefined ? (a.x + a.to) / 2 : a.x)).concat(shot.shadow ? [px(shot.shadow.x)] : []);
  return subj ? px(subj.to !== undefined && subj.to >= 0 ? (subj.x + subj.to) / 2 : subj.x) : xs.length ? (Math.min(...xs) + Math.max(...xs)) / 2 : W / 2;
};
export const camFor = (shot: Shot, vertical: boolean): Cam => {
  const zoomed = shot.kind === 'scene' && shot.set && shot.set !== 'void' && shot.set !== 'stairs';
  // Film framing (movie parts): medium = one person waist-up, close = face and hands, centred on `subject`; wide = the room.
  const subj = shot.framing && shot.framing !== 'wide' ? (shot.actors ?? []).find((a) => a.id === shot.subject) ?? (shot.actors ?? [])[0] : undefined;
  if (!vertical) {
    const framed = zoomed && !!subj;
    const z = framed ? (shot.framing === 'close' ? 3.0 : 1.9) : zoomed ? (shot.shadow?.size === 'giant' ? 1.05 : ZOOM) : 1;
    const cx = centreOf(shot, subj);
    return {fx: zoomed ? Math.min(W - W / (2 * z), Math.max(W / (2 * z), cx)) : W / 2, ay: framed ? FLOOR - (shot.framing === 'close' ? 250 : 170) : FLOOR,
      sy: framed ? H * (shot.framing === 'close' ? 0.5 : 0.6) : FLOOR, s: z, bg: '#000'};
  }
  const b = VH / H; // the world's height fills the tall frame
  if (INSERT_CAM[shot.kind]) {
    const [x, y, s, bg] = INSERT_CAM[shot.kind];
    return {fx: x, ay: y, sy: VH / 2, s, bg};
  }
  if (shot.kind === 'scene') {
    const close = subj && shot.framing === 'close';
    const s = b * (subj ? (close ? 2.5 : 1.65) : 1);
    const half = VW / (2 * s);
    // the subject (else the first person) stays whole in the narrow frame: centred between him and a giant shadow,
    // he was cut in half at the edge
    const lead = subj ?? (shot.actors ?? [])[0];
    const keep = lead ? px(lead.to !== undefined && lead.to >= 0 ? (lead.x + lead.to) / 2 : lead.x) : undefined;
    let fx = centreOf(shot, subj);
    if (keep !== undefined) fx = Math.min(keep + half - 140, Math.max(keep - half + 140, fx));
    return {fx: Math.min(W - half, Math.max(half, fx)), ay: subj ? FLOOR - (close ? 270 : 190) : FLOOR,
      sy: subj ? VH * (close ? 0.46 : 0.58) : VH * (FLOOR / H), s, bg: '#000'};
  }
  return {fx: W / 2, ay: H / 2, sy: VH / 2, s: b, bg: '#000'}; // face close-ups, cards, splits
};

// Draws when React reaches it: after the shot's picture (an earlier sibling), which writes where every head is.
// The heads were converted to the screen in ShotView's own body, before any of them was written, so bubbles got
// world positions: a little off in a film's 1.28 room zoom, at the top corner of a 9:16 Short.
const Later: React.FC<{draw: () => React.ReactNode}> = ({draw}) => <>{draw()}</>;

// A split screen in a Short: the two lives stacked, each half framed on its own people.
const TallSplit: React.FC<{shot: Shot; t: number; dur: number; p: StickyProps}> = ({shot, t, dur, p}) => {
  const vw = W * 0.63; // a 1080x960 half shows the world's full height and this much of its width
  const half = (s: Shot | undefined, y: number) => {
    if (!s) return null;
    const cx = Math.min(W - vw / 2, Math.max(vw / 2, centreOf(s)));
    return (
      <svg x={0} y={y} width={VW} height={VH / 2} viewBox={`${cx - vw / 2} 0 ${vw} ${H}`} preserveAspectRatio="xMidYMid slice">
        <SceneView shot={{...s, start: shot.start, duration: shot.duration}} t={t} dur={dur} cast={p.cast} accent={p.accent} flat />
      </svg>
    );
  };
  return <g>{half(shot.left, 0)}{half(shot.right, VH / 2)}<line x1={0} y1={VH / 2} x2={VW} y2={VH / 2} stroke="#E8E8EC" strokeWidth={4} opacity={0.8} /></g>;
};

const ShotView: React.FC<{shot: Shot; p: StickyProps; first: boolean}> = ({shot, p, first}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = frame / fps;
  const dur = shot.duration;
  const V = !!p.vertical;
  const FW = V ? VW : W, FH = V ? VH : H;
  const heads: Record<string, [number, number]> = {};
  const fadeIn = shot.transition === 'fade' && !first ? interpolate(frame, [0, FADE], [0, 1], clamp) : 1;
  const push = shot.camera === 'push' ? interpolate(t, [0, dur], [1, 1.06], clamp) : shot.camera === 'pull' ? interpolate(t, [0, dur], [1.08, 1], clamp) : 1;
  const drift = shot.camera === 'drift' ? interpolate(t, [0, dur], [-20, 20], clamp) : 0;
  const filter = GRADES[shot.grade ?? 'normal'];
  // Scene shots sit closer than the set's full width, like the reference films (camFor). Bubble anchors follow it.
  const cam = camFor(shot, V);
  const tallSplit = V && shot.kind === 'split';
  const picture = tallSplit ? <TallSplit shot={shot} t={t} dur={dur} p={p} /> : <ShotPicture shot={shot} t={t} dur={dur} p={p} heads={heads} />;
  const onScreen = () => Object.fromEntries(Object.entries(heads).map(([k, h]) => [k, [FW / 2 + (h[0] - cam.fx) * cam.s, cam.sy + (h[1] - cam.ay) * cam.s] as [number, number]]));
  return (
    <AbsoluteFill style={{opacity: fadeIn}}>
      <svg width={FW} height={FH} viewBox={`0 0 ${FW} ${FH}`} style={{position: 'absolute', inset: 0}}>
        <defs>
          <radialGradient id="stPhoneGlow"><stop offset="0" stopColor="#BFD8FF" stopOpacity={0.4} /><stop offset="1" stopColor="#BFD8FF" stopOpacity={0} /></radialGradient>
        </defs>
        {V ? <rect width={FW} height={FH} fill={cam.bg} /> : null}
        <g style={{filter}} transform={`translate(${FW / 2 + drift},${FH / 2}) scale(${push}) translate(${-FW / 2},${-FH / 2})`}>
          {tallSplit ? picture : <g transform={`translate(${FW / 2},${cam.sy}) scale(${cam.s}) translate(${-cam.fx},${-cam.ay})`}>{picture}</g>}
        </g>
        {V && shot.kind === 'title' ? <TitleCard title={p.title} tagline={p.tagline} t={t} accent={p.accent} fw={FW} fh={FH} /> : null}
        {V && shot.notes?.length ? <Notes notes={shot.notes} t={t} dur={dur} accent="#E5484D" box={[60, 330, FW - 290, FH * 0.36]} /> : null}
        {V && shot.pills?.length ? <Later draw={() => {
          const all = onScreen();
          const hero = all[p.cast[0]?.id] ?? Object.values(all)[0] ?? [FW / 2, FH * 0.45];
          return <Pills pills={shot.pills!} around={[hero[0], hero[1] + 120]} t={t} accent={p.accent} fw={FW} k={1.4} />;
        }} /> : null}
        {shot.whisper ? <Whisper w={shot.whisper} t={t} dur={dur} accent={p.accent} fw={FW} fh={FH} /> : null}
        {shot.bubbles?.length ? <Later draw={() => <Bubbles b={shot.bubbles!} heads={onScreen()} t={t} dur={dur} fw={FW} fh={FH} k={V ? 1.4 : 1} />} /> : null}
        {shot.stamp ? <Stamp text={shot.stamp} t={t} fw={FW} y={V ? 600 : 260} /> : null}
        {shot.caption?.lines?.length ? <Caption c={shot.caption} t={t} dur={dur} fw={FW} fh={FH} tall={V} /> : null}
        <Grain frame={frame} fw={FW} fh={FH} />
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
    <svg width={p.vertical ? VW : W} height={p.vertical ? VH : H} viewBox={`0 0 ${p.vertical ? VW : W} ${p.vertical ? VH : H}`} style={{position: 'absolute', inset: 0}}>
      <Hud meter={p.meter} now={shot.meter ?? prev?.meter ?? []} before={prev?.meter ?? null} t={frame / fps} day={shot.day} time={shot.time} accent={p.accent}
        fw={p.vertical ? VW : W} top={p.vertical ? 170 : 0} k={p.vertical ? 1.5 : 1} />
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
