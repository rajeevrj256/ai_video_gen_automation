import '@fontsource/permanent-marker/400.css';
import React, {useEffect, useState} from 'react';
import {Easing, Sequence, continueRender, delayRender, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {Audio} from '../Audio';
import {FONT, clamp, useFonts} from '../theme';
import {Layer} from '../Layer';
import {Cues, Music} from '../Sound';
import {iconFor} from '../long/icon';
import {PieceView, STOOL_SEAT, Stool, TABLE_TOP, TableUnder, defaultFurniture, seatAt, surfaceAt} from './furniture';
import {CustomSet, HEAD_FILL, INK_GRADE, InkBody, InkDefs, InkFaceExtras, InkFinish, InkHair, InkHairBack, InkHairBackView, InkHeadwear, InkSet, InkThing, Light, VEHICLES, Weather, defaultDesign, drawnKind, farOf, inkPalette, type SetPal, GREY_PAL} from './ink';
import type {ActorState, CastMember, Design, Effect, Emote, Face, Look, Piece, Pose, Prop, Setting, Shot, StoryProps, Thing, Word} from './types';

// A stick-figure comedy episode in the channel's style: light grey sets drawn in grey tones with
// ink outlines, white round heads, thin stick bodies, speech bubbles. One Sequence per shot (one
// line of dialogue); the cast keeps its look from shot to shot because the same drawing code
// makes every frame.

const W = 1920;
const H = 1080;
const FLOOR = 900;
// The channel's look (e.g. its Short "Pass or failed"): thin hand-drawn lines, big heads on small
// bodies, eyebrows on every face, minimal sets, red marker writing on props.
const INK = '#161616';
const PAPER = '#CFCFCF';
const GREY = '#B4B4B4';
const DARK = '#9C9C9C';
const LIGHT = '#E4E4E4';
const LINE = 5.5;
const SET_LINE = 4.5;
const HEAD = 84;
const FACE = HEAD / 64; // faces are drawn for a 64 px head and scaled up
const HAND = '"Permanent Marker", "Noto Sans Devanagari", cursive';

const useHandFont = () => {
  const [handle] = useState(() => delayRender('Loading the marker font'));
  useEffect(() => {
    document.fonts.load('40px "Permanent Marker"').catch(() => undefined).finally(() => continueRender(handle));
  }, [handle]);
};

type Pt = [number, number];
// Relative to the figure's feet centre, facing right; y up is negative.
type Rig = {hip: Pt; neck: Pt; head: Pt; tilt: number; lE: Pt; lH: Pt; rE: Pt; rH: Pt; lK: Pt; lF: Pt; rK: Pt; rF: Pt};

const STAND: Rig = {
  hip: [0, -165], neck: [0, -318], head: [0, -318 - HEAD + 4], tilt: 0,
  lE: [-34, -255], lH: [-44, -188], rE: [34, -255], rH: [44, -188],
  lK: [-18, -84], lF: [-28, 0], rK: [18, -84], rF: [28, 0],
};

const rig = (pose: Pose, t: number, SEAT: number): Rig => {
  const s = {...STAND};
  const swing = Math.sin(t * 9);
  switch (pose) {
    case 'walk':
    case 'run': {
      const k = pose === 'run' ? 1.6 : 1;
      return {...s, tilt: pose === 'run' ? 8 : 0,
        lK: [-10 + 26 * swing * k, -84], lF: [-14 + 46 * swing * k, 0], rK: [10 - 26 * swing * k, -84], rF: [14 - 46 * swing * k, 0],
        lE: [-30 - 18 * swing * k, -255], lH: [-34 - 34 * swing * k, -192], rE: [30 + 18 * swing * k, -255], rH: [34 + 34 * swing * k, -192]};
    }
    case 'sit':
      // Seen from the front, on the seat under them (SEAT px high, from the scene's furniture): thighs
      // out to the knees, shins straight down, hands resting on the knees.
      return {...s, hip: [0, -SEAT], neck: [0, -SEAT - 150], head: [0, -SEAT - 150 - HEAD + 4],
        lE: [-44, -SEAT - 70], lH: [-50, -SEAT + 8], rE: [44, -SEAT - 70], rH: [50, -SEAT + 8],
        lK: [-54, -SEAT + 10], lF: [-56, 0], rK: [54, -SEAT + 10], rF: [56, 0]};
    case 'point':
      return {...s, rE: [62, -282], rH: [136, -300]};
    case 'arms-up':
      return {...s, lE: [-58, -360], lH: [-82, -436], rE: [58, -360], rH: [82, -436]};
    case 'facepalm':
      return {...s, tilt: 10, rE: [56, -300], rH: [22, -372]};
    case 'shrug':
      return {...s, lE: [-70, -262], lH: [-96, -312], rE: [70, -262], rH: [96, -312]};
    case 'hands-on-hips':
      return {...s, lE: [-72, -238], lH: [-20, -172], rE: [72, -238], rH: [20, -172]};
    case 'think':
      return {...s, tilt: -6, rE: [46, -252], rH: [26, -330], lE: [-20, -232], lH: [30, -236]};
    case 'cry':
      return {...s, tilt: 12, lE: [-50, -300], lH: [-16, -366], rE: [50, -300], rH: [16, -366]};
    case 'wave':
      return {...s, rE: [62, -330], rH: [92 + 16 * Math.sin(t * 6), -420]}; // a calm wave, not a buzz
    case 'hold':
      return {...s, rE: [52, -262], rH: [70, -270], lE: [-26, -250], lH: [44, -262]};
    default:
      return s;
  }
};

// ---------- the composition ----------

export const StickStory: React.FC<StoryProps> = ({cast, shots, music, cues, speech, vertical = false, dialogue = 'subtitle', soundOnly = false, art = 'grey', ambience = []}) => {
  useFonts();
  useHandFont();
  const {fps} = useVideoConfig();
  const f = (s: number) => Math.round(s * fps);
  const looks: Record<string, Look> = Object.fromEntries(cast.map((c) => [c.id, c.look]));
  return (
    <Layer name="stick story" style={{backgroundColor: PAPER, fontFamily: FONT}}>
      {soundOnly ? null : shots.map((s, i) => (
        <Sequence key={i} name={`shot ${i + 1} ${s.setting}${s.speaker ? ` (${s.speaker})` : ''}`} from={f(s.start)} durationInFrames={Math.max(1, f(s.duration))}>
          <ShotView shot={s} looks={looks} cast={cast} vertical={vertical} dialogue={dialogue} ink={art === 'ink'} newScene={i > 0 && shots[i - 1].scene !== s.scene} />
        </Sequence>
      ))}
      {shots.map((s, i) =>
        s.audio ? (
          <Sequence key={`v${i}`} name={`voice ${i + 1}`} from={f(s.start + s.lead)}>
            <Audio src={staticFile(s.audio)} />
          </Sequence>
        ) : null,
      )}
      {music ? <Music src={music} speech={speech} full={0.16} duck={0.06} /> : null}
      {ambience.map((a, i) => (
        // A scene's quiet bed (wind, rain, room tone), faded in and out; soundtrack._story mirrors it.
        <Sequence key={`amb${i}`} name={`ambience ${i + 1}`} from={f(a.from)} durationInFrames={Math.max(1, f(a.to - a.from))}>
          <Audio src={staticFile(a.src)} loop
            volume={(fr) => interpolate(fr, [0, 30, Math.max(31, f(a.to - a.from) - 30), Math.max(32, f(a.to - a.from))], [0, 0.1, 0.1, 0], clamp)} />
        </Sequence>
      ))}
      <Cues cues={cues} speech={speech} />
    </Layer>
  );
};

// ---------- one shot ----------

const ShotView: React.FC<{shot: Shot; looks: Record<string, Look>; cast: CastMember[]; newScene: boolean; vertical: boolean; dialogue: 'subtitle' | 'bubble' | 'none'; ink: boolean}> = ({shot, looks, cast, newScene, vertical, dialogue, ink}) => {
  const frame = useCurrentFrame();
  const {fps, width: OW, height: OH} = useVideoConfig();
  // A Short frames the cast close (big heads, like the channel's Shorts): a slice of the 1920 px set
  // in the upper part of the frame, following whoever speaks; subtitles go below it. The slice is as
  // close as possible (1.9x, ~570 px) but always wide enough for everyone and every object on screen.
  const xsOnScreen = [...shot.actors.map((a) => a.x), ...(shot.things ?? []).map((th) => th.x)];
  const spread = xsOnScreen.length ? Math.max(...xsOnScreen) - Math.min(...xsOnScreen) : 0;
  const base = vertical ? Math.min(1.9, Math.max(1.1, OW / (spread + 300))) : 1;
  const t = frame / fps;
  const frames = Math.max(1, Math.round(shot.duration * fps));
  const speaking = (id: string) => shot.speaker === id;
  const focus = shot.actors.find((a) => a.id === (shot.focus || shot.speaker)) ?? shot.actors[0];
  let scale = 1;
  // A Short is already framed close: its close-up and punch-in are gentler.
  const zoomMax = vertical ? 1.22 : 1.5;
  // A very slow push-in over the whole shot (documentaries: the camera stays locked or creeps in).
  if (shot.camera === 'push') scale = interpolate(frame, [0, frames], [1, vertical ? 1.06 : 1.1], {...clamp, easing: Easing.inOut(Easing.sin)});
  if (shot.camera === 'close') scale = interpolate(frame, [0, 10], [1 + (zoomMax - 1) * 0.5, zoomMax], {...clamp, easing: Easing.out(Easing.cubic)});
  // A 'shake' camera (older props) is a punch-in now: the user wants no vibration at all.
  if (shot.camera === 'punch' || shot.camera === 'shake') scale = 1 + (vertical ? 0.1 : 0.2) * spring({frame: frame - Math.round(shot.lead * fps), fps, config: {damping: 14}});
  const shake = 0;
  const fx = focus ? focus.x : W / 2;
  // A far-away figure (actor.far) stands on the set's distant ground: the camera centres on it there.
  const farInfo = farOf(shot.setting);
  const fy = focus?.far ? FLOOR - farInfo.lift - 260 * farInfo.size : FLOOR - 300;
  const group = xsOnScreen.length ? (Math.max(...xsOnScreen) + Math.min(...xsOnScreen)) / 2 : W / 2;
  const total = base * scale;
  const halfW = OW / (2 * total);
  const halfH = OH / (2 * total);
  const wantX = vertical ? (scale > 1 ? fx : group) : scale > 1 ? fx : W / 2;
  const cx = Math.min(W - Math.min(halfW, W / 2), Math.max(Math.min(halfW, W / 2), wantX));
  const cy = scale > 1 ? Math.min(H - halfH, Math.max(halfH, fy)) : vertical ? FLOOR - 250 : H / 2;
  const front = frontHeight(shot.setting);
  const floorY = (FLOOR - front - cy) * total + OH / 2;
  const flash = newScene ? interpolate(frame, [0, 5], [0.9, 0], clamp) : 0;
  const speaker = shot.actors.find((a) => a.id === shot.speaker);
  const furniture = shot.furniture ?? defaultFurniture(shot.setting);
  const outfits: Record<string, string | undefined> = Object.fromEntries(cast.map((c) => [c.id, c.outfit]));
  const seat = (a: ActorState) => seatAt(furniture, a.x) ?? STOOL_SEAT;
  // The ink look: each character's own design (a default from their look for older props).
  const designs: Record<string, Design | undefined> = ink ? Object.fromEntries(cast.map((c, i) => [c.id, c.design ?? defaultDesign(c.look, i)])) : {};
  const pal = ink ? inkPalette(shot.setting) : GREY_PAL;
  return (
    <Layer name="shot">
      <svg width={OW} height={OH} viewBox={`0 0 ${OW} ${OH}`} style={{position: 'absolute', inset: 0, filter: ink ? INK_GRADE : undefined}}>
        {ink ? <InkDefs /> : null}
        <g transform={`translate(${OW / 2 + shake} ${OH / 2}) scale(${total}) translate(${-cx} ${-cy})`}>
          <g filter={ink ? 'url(#inkRough)' : undefined}>
          {shot.backdropSvg ? <CustomSet svg={shot.backdropSvg} floor={FLOOR} /> : ink ? <InkSet setting={shot.setting} sign={shot.sign} floor={FLOOR} hand={HAND} font={FONT} t={t} /> : <SetView setting={shot.setting} sign={shot.sign} />}
          {furniture.map((p, i) => <PieceView key={`f${i}`} p={p} floor={FLOOR} pal={pal} />)}
          {shot.actors.filter((a) => a.pose === 'sit' && !a.action.startsWith('walk') && seatAt(furniture, a.x) === null).map((a) => (
            <Stool key={`stool-${a.id}`} x={a.x} floor={FLOOR} pal={pal} />
          ))}
          {shot.actors.map((a) => (
            <Figure key={a.id} a={a} seat={seat(a)} outfit={outfits[a.id]} design={designs[a.id]} look={looks[a.id] ?? 'boy'} t={t} frame={frame} frames={frames} far={farOf(shot.setting)}
              talking={speaking(a.id) ? shot.words.map((w) => ({...w, start: w.start + shot.lead, end: w.end + shot.lead})) : []} />
          ))}
          <SetFront setting={shot.setting} washing={!!shot.washing} xs={shot.actors.map((a) => a.x)} t={t} pal={ink ? pal : undefined} />
          {(shot.things ?? []).map((th, i) => <ThingView key={`th${i}`} th={th} furniture={furniture} front={front} t={t} pal={pal} />)}
          </g>
        </g>
      </svg>
      {shot.weather && shot.weather !== 'none' ? <Weather kind={shot.weather} t={t} /> : null}
      {shot.light && shot.light !== 'day' ? <Light kind={shot.light} /> : null}
      {ink ? <InkFinish /> : null}
      {speaker && shot.text && dialogue === 'subtitle' ? (
        <Subtitle text={shot.text} lead={shot.lead} top={vertical ? floorY + 40 : undefined} big={vertical} ink={ink} />
      ) : null}
      {speaker && shot.text && dialogue === 'bubble' ? (
        <Bubble text={shot.text} words={shot.words} lead={shot.lead} x={(speaker.x - cx) * total + OW / 2}
          y={(FLOOR - 470 - (speaker.pose === 'sit' ? -(165 - seat(speaker)) : 0) - cy) * total + OH / 2} big={vertical} />
      ) : null}
      {!speaker && shot.text && dialogue !== 'none' ? <Narration text={shot.text} top={vertical ? floorY + 40 : undefined} big={vertical} /> : null}
      {shot.caption ? <Caption text={shot.caption} top={vertical ? 230 : 36} ink={ink} /> : null}
      {flash > 0 ? <div style={{position: 'absolute', inset: 0, background: '#fff', opacity: flash}} /> : null}
    </Layer>
  );
};

// ---------- a character ----------

const actionOffset = (a: ActorState, t: number, frames: number, fps: number) => {
  const d = frames / fps;
  let dx = 0;
  let dy = 0;
  let rot = 0;
  switch (a.action) {
    case 'jump':
      dy = -Math.max(0, Math.sin(Math.min(1, t / 0.6) * Math.PI)) * 120;
      break;
    // 'shake' (older props) no longer moves anyone: the user asked for no character vibration.
    case 'fall':
      rot = interpolate(t, [0.1, 0.5], [0, 82], {...clamp, easing: Easing.in(Easing.quad)});
      break;
    case 'spin':
      rot = interpolate(t, [0, 0.6], [0, 360], clamp);
      break;
    case 'walk-in-left':
      dx = interpolate(t, [0, 0.8], [-1100, 0], {...clamp, easing: Easing.out(Easing.cubic)});
      break;
    case 'walk-in-right':
      dx = interpolate(t, [0, 0.8], [1100, 0], {...clamp, easing: Easing.out(Easing.cubic)});
      break;
    case 'walk-out-left':
      dx = interpolate(t, [Math.max(0, d - 1), d], [0, -1100], {...clamp, easing: Easing.in(Easing.cubic)});
      break;
    case 'walk-out-right':
      dx = interpolate(t, [Math.max(0, d - 1), d], [0, 1100], {...clamp, easing: Easing.in(Easing.cubic)});
      break;
  }
  // One step forward (0.8-1.8 s): seen from behind it goes into the picture (a little smaller and higher),
  // otherwise toward where they face. `stepT` gives the walking legs exactly one swing.
  let k = 1;
  let stepT: number | null = null;
  if (a.action === 'step') {
    const p = interpolate(t, [0.8, 1.8], [0, 1], {...clamp, easing: Easing.inOut(Easing.quad)});
    if (a.back) {
      k = 1 - 0.07 * p;
      dy = -16 * p;
    } else dx = 70 * p * a.facing;
    if (t > 0.8 && t < 1.8) stepT = ((t - 0.8) / 1) * (Math.PI / 9);
  }
  // Across the frame the way they face, walking the whole shot.
  if (a.action === 'walk-across') dx = interpolate(t, [0, d], [-520, 520], clamp) * a.facing;
  // A head turn: they face the other way from halfway through.
  const facing = a.action === 'turn' && t > d / 2 ? -a.facing : a.facing;
  // Looking up: the head tips back and stays there (one movement, no wobble).
  const headUp = a.action === 'look-up' ? -interpolate(t, [0.3, 0.9], [0, 20], {...clamp, easing: Easing.out(Easing.quad)}) : 0;
  const walking = (a.action.startsWith('walk-in') && t < 0.8) || (a.action.startsWith('walk-out') && t > d - 1) || stepT !== null
    || a.action === 'walk-across';
  return {dx, dy, rot, walking, k, stepT, facing, headUp};
};

// Small body movements that carry an emotion (pixels and degrees; lean is toward where they look).
// Held poses only, never a repeating bounce, wobble or tremble: the user saw those as the characters
// vibrating ("remove character vibration effect"). Shock gets one hop at the start, nothing else moves.
const acting = (face: Face, talking: boolean, t: number) => {
  const none = {dx: 0, dy: 0, lean: 0, head: 0};
  switch (face) {
    case 'laugh':
      return {...none, head: -8, lean: -3};
    case 'cry':
    case 'sad':
      return {...none, head: 9, lean: talking ? 3 : 2};
    case 'shock':
      return {...none, dy: talking ? -Math.max(0, Math.sin(Math.min(t, 0.35) * 9)) * 18 : 0, lean: -4};
    case 'angry':
      return {...none, lean: talking ? 7 : 3};
    case 'happy':
    case 'love':
      return talking ? {...none, head: -4} : none;
    default:
      return none;
  }
};

// Clothes, like the channel's characters: men and boys wear a shirt with a collar and short sleeves,
// women and girls an A-line dress to the knee; each character keeps their own colour (cast.outfit).
const dressed = (look: Look) => look === 'girl' || look === 'woman' || look === 'old-woman';
const shoulder = (r: Rig, side: -1 | 1): Pt => [r.neck[0] + side * 36, r.neck[1] + 20];
const Clothes: React.FC<{r: Rig; look: Look; colour?: string; sitting: boolean}> = ({r, look, colour, sitting}) => {
  const [nx, ny] = r.neck;
  const [hx, hy] = r.hip;
  if (dressed(look)) {
    const bottom = hy + (sitting ? 34 : 80);
    const half = sitting ? 66 : 58;
    return (
      <path d={`M ${nx - 20} ${ny + 8} Q ${nx} ${ny + 2} ${nx + 20} ${ny + 8} L ${hx + half} ${bottom} Q ${hx} ${bottom + 8} ${hx - half} ${bottom} Z`}
        fill={colour || DARK} strokeWidth={LINE} />
    );
  }
  return (
    <g>
      <path d={`M ${nx - 44} ${ny + 22} Q ${nx - 40} ${ny + 6} ${nx} ${ny + 4} Q ${nx + 40} ${ny + 6} ${nx + 44} ${ny + 22} L ${hx + 38} ${hy + 16} L ${hx - 38} ${hy + 16} Z`}
        fill={colour || '#FFFFFF'} strokeWidth={LINE} />
      <path d={`M ${nx - 16} ${ny + 6} L ${nx} ${ny + 30} L ${nx + 16} ${ny + 6}`} strokeWidth={LINE - 1} />
      <line x1={nx} y1={ny + 30} x2={hx} y2={hy + 12} strokeWidth={2.5} />
    </g>
  );
};
// Short sleeves: the top of each arm drawn thick in the shirt's colour with an ink edge.
const Sleeves: React.FC<{r: Rig; colour?: string}> = ({r, colour}) => (
  <>
    {([[-1, r.lE], [1, r.rE]] as const).map(([side, e]) => {
      const s = shoulder(r, side);
      const end: Pt = [s[0] + (e[0] - s[0]) * 0.55, s[1] + (e[1] - s[1]) * 0.55];
      return (
        <g key={side}>
          <line x1={s[0]} y1={s[1]} x2={end[0]} y2={end[1]} strokeWidth={28} />
          <line x1={s[0]} y1={s[1]} x2={end[0]} y2={end[1]} strokeWidth={18} stroke={colour || '#FFFFFF'} />
        </g>
      );
    })}
  </>
);

const Figure: React.FC<{a: ActorState; seat: number; look: Look; outfit?: string; design?: Design; t: number; frame: number; frames: number; talking: Word[]; far?: {lift: number; size: number}}> = ({a, seat, look, outfit, design, t, frame, frames, talking, far}) => {
  const {fps} = useVideoConfig();
  const {dx, dy, rot, walking, k, stepT, facing, headUp} = actionOffset(a, t, frames, fps);
  const pose: Pose = walking ? 'walk' : a.pose;
  const small = (look === 'kid' ? 0.78 : 1) * k * (a.far && far ? far.size : 1);
  const lift = a.far && far ? far.lift : 0;
  const r = rig(pose, stepT ?? t, seat);
  const breathe = 0; // no breathing bob: it read as the figures vibrating
  const speakingNow = talking.some((w) => t >= w.start && t <= w.end);
  const mouthOpen = speakingNow && frame % 6 < 3;
  const lying = pose === 'lie' || a.action === 'fall';
  // Acting the feeling: laughing and crying and fear show all the time, anger and joy while talking.
  const act = acting(a.face, speakingNow || talking.length > 0, t);
  const limb = (p: Pt, k: Pt, e: Pt) => `M ${p[0]} ${p[1]} Q ${k[0]} ${k[1]} ${e[0]} ${e[1]}`;
  // A sitting leg bends at the knee instead of curving.
  const leg = (p: Pt, k: Pt, e: Pt) => (pose === 'sit' ? `M ${p[0]} ${p[1]} L ${k[0]} ${k[1]} L ${e[0]} ${e[1]}` : limb(p, k, e));
  return (
    <g transform={`translate(${a.x + dx + act.dx} ${FLOOR - lift + dy + act.dy}) rotate(${pose === 'lie' ? 0 : rot + act.lean * facing}) scale(${facing * small} ${small})`}>
      <g transform={pose === 'lie' ? 'translate(-150 -40) rotate(-90 0 0)' : `translate(0 ${breathe})`}>
        <ellipse cx={0} cy={4} rx={60} ry={9} fill="rgba(0,0,0,0.18)" stroke="none" />
        {design ? (
          <g stroke={INK} strokeWidth={LINE} fill="none" strokeLinecap="round" strokeLinejoin="round">
            <InkBody r={r} d={design} sitting={pose === 'sit'} back={!!a.back} />
            {a.back ? null : <PropView prop={a.prop} text={a.propText} thing={a.propThing} t={t} at={r.rH} />}
            <g transform={`translate(${r.head[0]} ${r.head[1]}) rotate(${r.tilt + act.head + headUp})`}>
              {a.back ? null : <g transform={`scale(${FACE})`}><InkHairBack d={design} /></g>}
              <circle r={HEAD} fill={HEAD_FILL} strokeWidth={6} />
              <g transform={`scale(${FACE})`} strokeWidth={LINE / FACE}>
                {a.back ? (
                  // From behind: the back of the head, no face.
                  <InkHairBackView d={design} />
                ) : (
                  <>
                    <InkHair d={design} />
                    <FaceView face={lying && a.face === 'neutral' ? 'dead' : a.face} frame={frame} mouthOpen={mouthOpen} look="man" />
                    <InkFaceExtras d={design} ex={10} />
                  </>
                )}
                <InkHeadwear d={design} back={!!a.back} />
              </g>
            </g>
          </g>
        ) : (
        <g stroke={INK} strokeWidth={LINE} fill="none" strokeLinecap="round" strokeLinejoin="round">
          <path d={leg(r.hip, r.lK, r.lF)} />
          <path d={leg(r.hip, r.rK, r.rF)} />
          <Clothes r={r} look={look} colour={outfit} sitting={pose === 'sit'} />
          <path d={limb(shoulder(r, -1), r.lE, r.lH)} />
          <path d={limb(shoulder(r, 1), r.rE, r.rH)} />
          {dressed(look) ? null : <Sleeves r={r} colour={outfit} />}
          <PropView prop={a.prop} text={a.propText} thing={a.propThing} t={t} at={r.rH} />
          <g transform={`translate(${r.head[0]} ${r.head[1]}) rotate(${r.tilt + act.head + headUp})`}>
            <g transform={`scale(${FACE})`}><Hair look={look} back /></g>
            <circle r={HEAD} fill="#FFFFFF" />
            <g transform={`scale(${FACE})`} strokeWidth={LINE / FACE}>
              <Hair look={look} />
              <FaceView face={lying && a.face === 'neutral' ? 'dead' : a.face} frame={frame} mouthOpen={mouthOpen} look={look} />
            </g>
          </g>
        </g>
        )}
      </g>
      <g transform={`scale(${facing} 1)`}>
        <EmoteView emote={a.emote} t={t} head={[r.head[0] * facing, r.head[1]]} />
      </g>
    </g>
  );
};

const Hair: React.FC<{look: Look; back?: boolean}> = ({look, back}) => {
  const HEAD = 64; // drawn for a 64 px head, scaled with the face
  if (back) {
    if (look === 'girl') return <circle cx={-6} cy={-HEAD - 18} r={26} fill="#FFFFFF" stroke={INK} strokeWidth={LINE / FACE} />;
    if (look === 'woman') return <path d={`M ${-HEAD + 4} -10 Q -80 70 -40 96 M ${HEAD - 4} -10 Q 80 70 40 96`} strokeWidth={LINE / FACE} />;
    if (look === 'old-woman') return <circle cx={0} cy={-HEAD - 14} r={22} fill="#FFFFFF" stroke={INK} strokeWidth={LINE / FACE} />;
    return null;
  }
  switch (look) {
    case 'boy':
    case 'kid':
      return <path d={`M 0 ${-HEAD + 2} Q 10 ${-HEAD - 34} 34 ${-HEAD - 24}`}  />;
    case 'man':
      return <path d={`M ${-HEAD + 10} -28 Q -30 ${-HEAD - 18} 10 ${-HEAD - 8} Q 40 ${-HEAD - 12} ${HEAD - 10} -26`}  />;
    case 'old-man':
      return (
        <g strokeWidth={4.2}>
          <circle cx={-18} cy={-10} r={17} />
          <circle cx={26} cy={-10} r={17} />
          <line x1={-1} y1={-10} x2={9} y2={-10} />
          <path d={`M ${-HEAD + 6} -26 q -14 -8 -6 -22 M ${HEAD - 6} -26 q 14 -8 6 -22`} />
        </g>
      );
    default:
      return null;
  }
};

const FaceView: React.FC<{face: Face; frame: number; mouthOpen: boolean; look: Look}> = ({face, frame, mouthOpen, look}) => {
  const blink = frame % 90 > 86 ? 0.15 : 1;
  const ex = 10; // features shifted toward where the figure looks
  const eyes = (r = 7, dy = -6) =>
    look === 'old-man' ? null : (
      <>
        <ellipse cx={ex - 16} cy={dy} rx={r * 0.8} ry={r * 1.4 * blink} fill={INK} stroke="none" />
        <ellipse cx={ex + 18} cy={dy} rx={r * 0.8} ry={r * 1.4 * blink} fill={INK} stroke="none" />
      </>
    );
  const brows = <path d={`M ${ex - 25} -22 q 9 -6 18 -2 M ${ex + 9} -24 q 9 -4 18 2`} strokeWidth={4} />;
  // The talking mouth keeps the feeling: a shouting square with teeth when angry, a wobbling frown
  // when sad, a wide open grin when happy (one neutral oval for every face made them all look calm).
  const talk = !mouthOpen ? null : face === 'angry' ? (
    <g>
      <path d={`M ${ex - 20} 16 h 40 l -6 24 h -28 Z`} fill={INK} stroke="none" />
      <rect x={ex - 16} y={16} width={32} height={6} fill="#fff" stroke="none" />
      <rect x={ex - 12} y={34} width={24} height={5} fill="#fff" stroke="none" />
    </g>
  ) : face === 'sad' || face === 'cry' ? (
    <path d={`M ${ex - 16} 36 Q ${ex} ${12 + (frame % 4)} ${ex + 16} 36 Z`} fill={INK} stroke="none" />
  ) : face === 'happy' || face === 'love' || face === 'smirk' ? (
    <g>
      <path d={`M ${ex - 20} 16 Q ${ex} 46 ${ex + 20} 16 Z`} fill={INK} stroke="none" />
      <rect x={ex - 13} y={16} width={26} height={5} rx={2} fill="#fff" stroke="none" />
    </g>
  ) : face === 'nervous' ? (
    <ellipse cx={ex} cy={26} rx={10} ry={8} fill={INK} stroke="none" />
  ) : (
    <g>
      <ellipse cx={ex} cy={26} rx={15} ry={12} fill={INK} stroke="none" />
      <rect x={ex - 9} y={15} width={18} height={5} rx={2} fill="#fff" stroke="none" />
    </g>
  );
  switch (face) {
    case 'happy':
      return <g strokeWidth={4.2}>{brows}{eyes()}{talk ?? <path d={`M ${ex - 18} 18 Q ${ex} 36 ${ex + 18} 18`} />}</g>;
    case 'laugh':
      return (
        <g strokeWidth={4.2}>
          <path d={`M ${ex - 24} -6 l 8 -8 l 8 8 M ${ex + 10} -6 l 8 -8 l 8 8`} />
          <path d={`M ${ex - 22} 12 Q ${ex} ${mouthOpen ? 56 : 44} ${ex + 22} 12 Z`} fill={INK} />
        </g>
      );
    case 'shock':
      return (
        <g strokeWidth={4.2}>
          <circle cx={ex - 16} cy={-8} r={13} fill="#fff" /><circle cx={ex - 16} cy={-8} r={5} fill={INK} stroke="none" />
          <circle cx={ex + 18} cy={-8} r={13} fill="#fff" /><circle cx={ex + 18} cy={-8} r={5} fill={INK} stroke="none" />
          <path d={`M ${ex - 26} -30 q 9 -8 18 -4 M ${ex + 10} -34 q 9 -4 18 4`} strokeWidth={4} />
          <ellipse cx={ex} cy={30} rx={20} ry={mouthOpen ? 20 : 16} fill={INK} stroke="none" />
          <rect x={ex - 12} y={16} width={24} height={6} rx={2} fill="#fff" stroke="none" />
        </g>
      );
    case 'angry':
      return (
        <g strokeWidth={4.2}>
          <path d={`M ${ex - 28} -24 L ${ex - 8} -14 M ${ex + 30} -24 L ${ex + 10} -14`} />
          {eyes(6, -2)}
          {talk ?? <path d={`M ${ex - 16} 30 Q ${ex} 18 ${ex + 16} 30`} />}
        </g>
      );
    case 'sad':
      return (
        <g strokeWidth={4.2}>
          <path d={`M ${ex - 28} -18 L ${ex - 8} -26 M ${ex + 30} -18 L ${ex + 10} -26`} />
          {eyes(6, -4)}
          {talk ?? <path d={`M ${ex - 16} 32 Q ${ex} 20 ${ex + 16} 32`} />}
        </g>
      );
    case 'smirk':
      return <g strokeWidth={4.2}>{brows}{eyes(6)}{talk ?? <path d={`M ${ex - 14} 26 Q ${ex + 8} 30 ${ex + 22} 14`} />}</g>;
    case 'cry':
      return (
        <g strokeWidth={4.2}>
          <path d={`M ${ex - 24} -6 q 8 6 16 0 M ${ex + 10} -6 q 8 6 16 0`} />
          <path d={`M ${ex - 16} 0 q -4 ${18 + (frame % 20)} 0 ${30 + (frame % 20)}`} stroke="#5aa9e6" strokeWidth={5} />
          <ellipse cx={ex} cy={30} rx={14} ry={mouthOpen ? 14 : 9} fill={INK} stroke="none" />
        </g>
      );
    case 'nervous':
      return (
        <g strokeWidth={4.2}>
          <path d={`M ${ex - 25} -20 q 9 -8 18 -10 M ${ex + 9} -30 q 9 2 18 10`} strokeWidth={4} />
          {eyes(6)}
          {talk ?? <path d={`M ${ex - 16} 26 l 8 -5 l 8 5 l 8 -5 l 8 5`} />}
        </g>
      );
    case 'confused':
      return (
        <g strokeWidth={4.2}>
          <path d={`M ${ex + 8} -26 Q ${ex + 20} -34 ${ex + 32} -24`} />
          {eyes(6)}
          {talk ?? <path d={`M ${ex - 12} 26 L ${ex + 14} 22`} />}
        </g>
      );
    case 'sleepy':
      return <g strokeWidth={4.2}><path d={`M ${ex - 24} -6 h 16 M ${ex + 10} -6 h 16`} />{talk ?? <circle cx={ex} cy={26} r={6} />}</g>;
    case 'love':
      return (
        <g strokeWidth={4}>
          {[ex - 16, ex + 18].map((x) => <path key={x} d={`M ${x} 2 l -10 -10 a 6 6 0 0 1 10 -6 a 6 6 0 0 1 10 6 Z`} fill="#e63946" stroke="none" />)}
          {talk ?? <path d={`M ${ex - 16} 20 Q ${ex} 36 ${ex + 16} 20`} strokeWidth={6} />}
        </g>
      );
    case 'dead':
      return <g strokeWidth={4.2}><path d={`M ${ex - 24} -14 l 14 14 m 0 -14 l -14 14 M ${ex + 10} -14 l 14 14 m 0 -14 l -14 14`} /><path d={`M ${ex - 12} 28 h 24`} /></g>;
    default:
      return <g strokeWidth={4.2}>{brows}{eyes()}{talk ?? <path d={`M ${ex - 10} 26 h 20`} />}</g>;
  }
};

const PropView: React.FC<{prop: Prop; text?: string; thing?: string; t: number; at: Pt}> = ({prop, text, thing, t, at}) => {
  const [x, y] = at;
  switch (prop) {
    case 'thing':
      // Held in the hand, beside it.
      return <g transform={`translate(${x + 30} ${y - 46})`}><ThingArt name={thing || 'box'} size={110} t={t} effect="none" /></g>;
    case 'phone':
      return (
        <g transform={`translate(${x} ${y - 26})`}>
          <rect x={-18} y={-32} width={36} height={64} rx={7} fill={INK} strokeWidth={4} />
          {text ? <text x={0} y={6} fontSize={13} fill="#fff" stroke="none" textAnchor="middle" fontWeight={800}>{text}</text> : null}
        </g>
      );
    case 'paper': {
      // Red marker writing, like the channel's "F-- BRING YOUR PARENTS" report card.
      const rows = (text ?? '').toUpperCase().split(/\s+/).reduce<string[]>((acc, w) => {
        const last = acc[acc.length - 1];
        if (last !== undefined && (last + ' ' + w).length <= 8) acc[acc.length - 1] = last + ' ' + w;
        else if (w) acc.push(w);
        return acc;
      }, []);
      return (
        <g transform={`translate(${x + 40} ${y - 60}) rotate(6)`}>
          <rect x={-58} y={-74} width={116} height={148} fill="#fff" strokeWidth={4} />
          {rows.map((r, i) => (
            <text key={i} x={0} y={-74 + (i === 0 ? 44 : 44 + 24 * i)} fontSize={i === 0 ? 40 : 22} fill="#d62828" stroke="none"
              textAnchor="middle" fontFamily={HAND}>{r}</text>
          ))}
        </g>
      );
    }
    case 'book':
      return <rect x={x - 6} y={y - 52} width={56} height={70} rx={4} fill={DARK} strokeWidth={5} transform={`rotate(-8 ${x} ${y})`} />;
    case 'cup':
      return <g transform={`translate(${x + 8} ${y - 20})`}><path d="M -16 -26 h 32 l -4 40 h -24 Z" fill="#fff" strokeWidth={5} /><path d="M 15 -16 q 14 4 2 18" strokeWidth={5} /></g>;
    case 'bag':
      return <g transform={`translate(${x + 10} ${y + 20})`}><rect x={-30} y={-24} width={60} height={56} rx={8} fill={GREY} strokeWidth={5} /><path d="M -14 -24 q 14 -24 28 0" strokeWidth={5} /></g>;
    case 'laptop':
      return <g transform={`translate(${x - 10} ${y - 10})`}><rect x={-50} y={-50} width={90} height={56} rx={4} fill={DARK} strokeWidth={5} /><path d="M -60 8 h 110"  /></g>;
    case 'ball':
      return <circle cx={x + 16} cy={y - 14} r={24} fill="#fff" strokeWidth={5} />;
    case 'plate':
      return <ellipse cx={x + 12} cy={y - 6} rx={42} ry={11} fill="#fff" strokeWidth={5} />;
    case 'remote':
      return <rect x={x - 8} y={y - 40} width={18} height={50} rx={5} fill={INK} strokeWidth={3} />;
    default:
      return null;
  }
};

const EmoteView: React.FC<{emote: Emote; t: number; head: Pt}> = ({emote, t, head}) => {
  if (emote === 'none') return null;
  const [hx, hy] = head;
  const pop = Math.min(1, t / 0.18);
  const bob = Math.sin(t * 6) * 4;
  const text = (s: string, color = INK) => (
    <text x={hx + 70} y={hy - 70 + bob} fontSize={64 * pop} fontWeight={900} fill={color} stroke="none" fontFamily={FONT}>{s}</text>
  );
  switch (emote) {
    case '!':
    case '?':
    case '!?':
      return text(emote, emote === '?' ? INK : '#d62828');
    case 'sweat':
      return <path d={`M ${hx + 62} ${hy - 40 + t * 18} q 10 16 0 26 q -10 -10 0 -26 Z`} fill="#5aa9e6" stroke={INK} strokeWidth={3} />;
    case 'anger':
      return <path d={`M ${hx + 50} ${hy - 72} l 10 10 m 10 -10 l -10 10 m 20 0 l -10 -10 m -10 20 l 10 -10`} stroke="#d62828" strokeWidth={6} transform={`scale(${pop})`} />;
    case 'hearts':
      return <text x={hx + 60} y={hy - 60 - t * 20} fontSize={46} stroke="none">❤️</text>;
    case 'zzz':
      return <text x={hx + 60} y={hy - 50 - t * 14} fontSize={44} fontWeight={800} fill={INK} stroke="none">z z z</text>;
    case 'sparkle':
      return <text x={hx + 64} y={hy - 64 + bob} fontSize={48} stroke="none">✨</text>;
    case 'lines':
      return <path d={`M ${hx - 90} ${hy - 90} l -24 -24 M ${hx} ${hy - 110} v -30 M ${hx + 90} ${hy - 90} l 24 -24`} stroke={INK} strokeWidth={6} opacity={pop} />;
    default:
      return null;
  }
};

// ---------- objects: a hand-drawn volcano, anything else from lucide ----------

const LAVA = '#e4572e';

// A science-fair volcano: a lumpy cone with a crater and lava dripping down; 'erupt' throws lava up.
const Volcano: React.FC<{size: number; t: number; erupt: boolean}> = ({size, t, erupt}) => {
  const w = size;
  const h = size * 0.78;
  const blobs = erupt
    ? Array.from({length: 10}, (_, i) => {
        const p = ((t * 1.3 + i / 10) % 1);
        const dir = ((i * 37) % 11) / 10 - 0.5;
        return [dir * w * 1.1 * p, -h - (h * 1.5) * p + h * 1.7 * p * p, 9 + (i % 3) * 5, 1 - p] as const;
      })
    : [];
  return (
    <g stroke={INK} strokeWidth={4} strokeLinejoin="round" strokeLinecap="round">
      <path d={`M ${-w / 2} 0 Q ${-w / 3} ${-h * 0.4} ${-w * 0.14} ${-h} H ${w * 0.14} Q ${w / 3} ${-h * 0.4} ${w / 2} 0 Z`} fill="#8d7966" />
      <path d={`M ${-w * 0.15} ${-h} q ${w * 0.05} ${h * 0.28} ${w * 0.1} ${h * 0.12} q ${w * 0.04} ${h * 0.3} ${w * 0.1} ${h * 0.05} q ${w * 0.04} ${h * 0.2} ${w * 0.1} ${-h * 0.17} L ${w * 0.15} ${-h} Z`} fill={LAVA} />
      <ellipse cx={0} cy={-h} rx={w * 0.15} ry={w * 0.04} fill="#5a3a2a" />
      {blobs.map(([bx, by, r, o], i) => <circle key={i} cx={bx} cy={by} r={r} fill={i % 3 ? LAVA : '#f6a623'} opacity={o} strokeWidth={2.5} />)}
      {erupt ? <Puffs y={-h - 40} t={t} /> : null}
    </g>
  );
};

const Puffs: React.FC<{y: number; t: number}> = ({y, t}) => (
  <g fill="#ececec" stroke={INK} strokeWidth={3}>
    {[0, 1, 2, 3].map((i) => {
      const p = (t * 0.7 + i / 4) % 1;
      return <circle key={i} cx={Math.sin(i * 2.1 + t) * 26} cy={y - p * 150} r={16 + p * 26} opacity={1 - p} />;
    })}
  </g>
);

const ThingArt: React.FC<{name: string; size: number; t: number; effect: Effect; svg?: string | null}> = ({name, size, t, effect, svg}) => {
  const wiggle = effect === 'shake' ? Math.sin(t * 40) * 5 : 0;
  // Claude's own drawing of something nothing built in shows (200x200, standing on its bottom edge).
  if (svg) return <g transform={`rotate(${wiggle}) translate(${-size / 2} ${-size}) scale(${size / 200})`} dangerouslySetInnerHTML={{__html: svg}} />;
  if (/volcano|lava/.test(name)) {
    return <g transform={`rotate(${wiggle})`}><Volcano size={size * 1.5} t={t} erupt={effect === 'erupt'} /></g>;
  }
  // Animals and vehicles are drawn whole (lucide's dog and cat are only faces, its vehicles thin outlines).
  const drawn = drawnKind(name);
  if (drawn) return <g transform={`rotate(${wiggle})`}><InkThing kind={drawn} name={name} size={size} /></g>;
  const Icon = iconFor(name);
  const s = size / 24;
  return (
    <g transform={`rotate(${wiggle})`}>
      {/* lucide draws in a 24 px box, lines only: a white disc behind it keeps it readable on grey sets */}
      <g transform={`translate(${-size / 2} ${-size}) scale(${s})`}>
        <Icon width={24} height={24} color={INK} strokeWidth={2.2 / Math.max(1, s / 4)} fill="#fff" />
      </g>
      {effect === 'smoke' || effect === 'erupt' ? <Puffs y={-size - 10} t={t} /> : null}
      {effect === 'fire' ? (
        <g stroke={INK} strokeWidth={3} strokeLinejoin="round">
          {[-1, 0, 1].map((k) => {
            const f = 1 + Math.sin(t * 18 + k * 2) * 0.15;
            return <path key={k} d={`M ${k * 26 - 18} ${-size * 0.85} q 18 ${-60 * f} 18 ${-90 * f} q 4 ${40 * f} 18 ${90 * f} Z`} fill={k ? '#f6a623' : LAVA} />;
          })}
        </g>
      ) : null}
      {effect === 'sparkle' ? (
        <g fill="#ffd23f" stroke={INK} strokeWidth={2.5}>
          {[0, 1, 2, 3].map((i) => {
            const a = i * 1.6 + t * 2;
            const k = 0.6 + 0.4 * Math.abs(Math.sin(t * 6 + i));
            return <path key={i} transform={`translate(${Math.cos(a) * size * 0.7} ${-size / 2 + Math.sin(a) * size * 0.6}) scale(${k})`}
              d="M 0 -16 L 4 -4 L 16 0 L 4 4 L 0 16 L -4 4 L -16 0 L -4 -4 Z" />;
          })}
        </g>
      ) : null}
    </g>
  );
};

const ThingView: React.FC<{th: Thing; furniture: Piece[]; front: number; t: number; pal: SetPal}> = ({th, furniture, front, t, pal}) => {
  const ink = {stroke: INK, strokeWidth: SET_LINE, strokeLinejoin: 'round' as const, strokeLinecap: 'round' as const};
  const size = th.big ? 190 : 120;
  // On the table or desk at its spot; on a table brought in when there's none.
  // A set with a counter in front of the cast (the kitchen) puts things on that counter.
  const kind = drawnKind(th.name);
  const onTable = th.table && !(kind && VEHICLES.has(kind)); // a vehicle always stands on the ground
  const desk = onTable ? (front || surfaceAt(furniture, th.x)) : null;
  const top = FLOOR - (desk ?? (onTable ? TABLE_TOP : 0));
  return (
    <g>
      {onTable && desk === null ? <TableUnder x={th.x} floor={FLOOR} pal={pal} /> : null}
      <g transform={`translate(${th.x} ${top - 4})`}><ThingArt name={th.name} size={size} t={t} effect={th.effect} svg={th.svg} /></g>
    </g>
  );
};

// ---------- the sets ----------

// A counter across the front of the set hides the legs and is where things stand (0 = none).
const frontHeight = (setting: Setting) => (setting === 'kitchen' ? COUNTER : 0);
const COUNTER = 190; // the kitchen counter's height: it hides the legs, the scene reads as a mid shot

// What stands in front of the cast: the kitchen counter; its tap, running water and soap foam only
// when the scene is about washing dishes (otherwise every kitchen scene looked like the same dish gag).
const SetFront: React.FC<{setting: Setting; washing: boolean; xs: number[]; t: number; pal?: SetPal}> = ({setting, washing, xs, t, pal}) => {
  if (setting !== 'kitchen') return null;
  const top = FLOOR - COUNTER;
  const left = xs.length ? Math.min(...xs) : 800;
  const tapX = left - 150;
  const foam = Array.from({length: 9}, (_, i) => [left - 70 + i * 17, top - 8 - (i % 3) * 13 - Math.sin(t * 3 + i) * 2, 20 + (i % 4) * 5]);
  return (
    <g>
      <rect x={-400} y={top} width={W + 800} height={H + 400} fill={pal ? pal.fabric : PAPER} />
      {pal ? (
        <g stroke={INK} strokeWidth={3.5}>
          <rect x={-400} y={top - 4} width={W + 800} height={30} fill={pal.wood} />
          {Array.from({length: 13}, (_, i) => (
            <g key={i}>
              <rect x={-120 + i * 180} y={top + 50} width={150} height={260} rx={6} fill={pal.fabricDeep} />
              <line x1={-120 + i * 180 + (i % 2 ? 20 : 130)} y1={top + 90} x2={-120 + i * 180 + (i % 2 ? 20 : 130)} y2={top + 150} strokeWidth={7} />
            </g>
          ))}
        </g>
      ) : null}
      <line x1={-400} y1={top} x2={W + 400} y2={top} stroke={INK} strokeWidth={SET_LINE + 1} />
      <g stroke={INK} strokeWidth={SET_LINE} fill="#fff" strokeLinejoin="round">
        {washing && <path d={`M ${tapX} ${top} v -110 h 70 v 30 h -14 v -16 h -42 v 96 Z`} />}
        {washing && <rect x={tapX - 16} y={top - 128} width={60} height={14} rx={6} />}
        {washing && [0, 1, 2].map((k) => (
          <line key={k} x1={tapX + 56 + k * 7} y1={top - 66} x2={tapX + 60 + k * 9} y2={top - 8} stroke="#7fb8e0" strokeWidth={3}
            strokeDasharray="10 8" strokeDashoffset={-t * 120 - k * 6} />
        ))}
        {washing && foam.map(([x, y, r], i) => <circle key={i} cx={x} cy={y} r={r} />)}
      </g>
    </g>
  );
};

const SetView: React.FC<{setting: Setting; sign?: string}> = ({setting, sign}) => {
  const ink = {stroke: INK, strokeWidth: SET_LINE, strokeLinejoin: 'round' as const, strokeLinecap: 'round' as const};
  const floor = <line x1={-200} y1={FLOOR} x2={W + 200} y2={FLOOR} {...ink} />;
  const base = <rect x={-400} y={-400} width={W + 800} height={H + 800} fill={PAPER} />;
  const signText = (x: number, y: number, size = 38) =>
    sign ? <text x={x} y={y} fontSize={size} textAnchor="middle" fill={INK} fontFamily={HAND}>{sign.toUpperCase()}</text> : null;
  switch (setting) {
    case 'living-room':
      return (
        <g>
          {base}
          <rect x={1280} y={240} width={300} height={240} fill={LIGHT} {...ink} />
          <line x1={1430} y1={240} x2={1430} y2={480} {...ink} />
          {floor}
        </g>
      );
    case 'classroom':
    case 'exam-hall':
      return (
        <g>
          {base}
          <rect x={420} y={150} width={1080} height={300} fill="#3d4a3f" {...ink} />
          {sign ? <text x={960} y={320} fontSize={64} textAnchor="middle" fill="#f1f1f1" fontFamily={FONT}>{sign}</text> : null}
          {floor}
        </g>
      );
    case 'kitchen':
      return (
        <g>
          {base}
          <rect x={200} y={180} width={600} height={180} fill={GREY} {...ink} />
          <line x1={500} y1={180} x2={500} y2={360} {...ink} />
          <rect x={1400} y={260} width={260} height={FLOOR - 260} fill={LIGHT} {...ink} />
          <line x1={1400} y1={520} x2={1660} y2={520} {...ink} />
          {floor}
        </g>
      );
    case 'bedroom':
      return (
        <g>
          {base}
          <rect x={300} y={230} width={260} height={230} fill="#f4f4f4" {...ink} />
          {floor}
        </g>
      );
    case 'street':
      return (
        <g>
          {base}
          {[[0, 260, 320], [340, 160, 260], [620, 300, 380], [1050, 200, 300], [1380, 120, 320], [1720, 280, 260]].map(([x, top, w]) => (
            <rect key={x} x={x} y={top} width={w} height={FLOOR - top} fill={x % 2 ? GREY : LIGHT} {...ink} />
          ))}
          <rect x={-200} y={FLOOR} width={W + 400} height={200} fill={DARK} />
          <line x1={140} y1={FLOOR + 90} x2={W} y2={FLOOR + 90} stroke={LIGHT} strokeWidth={10} strokeDasharray="80 60" />
          {floor}
        </g>
      );
    case 'office':
      return (
        <g>
          {base}
          <rect x={300} y={200} width={420} height={260} fill={LIGHT} {...ink} />
          {floor}
        </g>
      );
    case 'bathroom':
      return (
        <g>
          {base}
          <rect x={720} y={180} width={480} height={FLOOR - 180} fill={LIGHT} {...ink} />
          <rect x={760} y={230} width={400} height={FLOOR - 230} fill="none" {...ink} />
          {signText(960, 216, 40) ?? <text x={960} y={216} fontSize={40} fontWeight={800} textAnchor="middle" fill={INK} fontFamily={FONT}>TOILET</text>}
          <circle cx={1120} cy={560} r={12} fill={INK} />
          {floor}
        </g>
      );
    case 'park':
      return (
        <g>
          {base}
          <rect x={250} y={540} width={50} height={FLOOR - 540} fill={DARK} {...ink} />
          <circle cx={275} cy={420} r={180} fill={GREY} {...ink} />
          {floor}
        </g>
      );
    case 'shop':
      return (
        <g>
          {base}
          <rect x={600} y={120} width={720} height={110} fill={LIGHT} {...ink} />
          {signText(960, 195, 56) ?? <text x={960} y={195} fontSize={56} fontWeight={800} textAnchor="middle" fill={INK} fontFamily={FONT}>SHOP</text>}
          {[320, 460, 600].map((y) => <line key={y} x1={160} y1={y} x2={560} y2={y} {...ink} />)}
          {[320, 460, 600].map((y) => <line key={`r${y}`} x1={1360} y1={y} x2={1760} y2={y} {...ink} />)}
          {floor}
        </g>
      );
    default:
      return (
        <g>
          {base}
          {floor}
        </g>
      );
  }
};

// ---------- words on screen ----------

const Bubble: React.FC<{text: string; words: Word[]; lead: number; x: number; y: number; big?: boolean}> = ({text, words, lead, x, y, big}) => {
  const frame = useCurrentFrame();
  const {fps, width: OW, height: OH} = useVideoConfig();
  const t = frame / fps - lead;
  const pop = spring({frame: frame - Math.round(lead * fps), fps, config: {damping: 13, mass: 0.6}});
  const shown = words.length ? words.filter((w) => t >= w.start - 0.05).length : text.split(/\s+/).length;
  const all = text.split(/\s+/);
  const visible = words.length ? all.slice(0, Math.max(1, Math.round((shown / words.length) * all.length))).join(' ') : text;
  const fs = big ? 50 : 40;
  const width = Math.min(OW - 80, Math.min(760, Math.max(260, text.length * fs * 0.48)));
  const left = Math.min(OW - width - 40, Math.max(40, x - width / 2));
  const bottom = OH - Math.max(big ? 420 : 160, y);
  return (
    <div style={{position: 'absolute', left, bottom, width, transform: `scale(${pop})`, transformOrigin: `${x - left}px 100%`, opacity: t < -0.05 ? 0 : 1}}>
      <div style={{background: '#fff', border: `4px solid ${INK}`, borderRadius: 34, padding: '18px 28px', fontSize: fs, fontWeight: 400, fontFamily: HAND, letterSpacing: '0.02em', lineHeight: 1.25, color: INK, textAlign: 'center', textWrap: 'balance'}}>
        {visible}
      </div>
      <svg width={60} height={44} style={{position: 'absolute', left: Math.min(width - 80, Math.max(20, x - left - 30)), top: '100%', marginTop: -5}}>
        <path d="M 8 0 L 30 40 L 44 0" fill="#fff" stroke={INK} strokeWidth={4} strokeLinejoin="round" />
        <path d="M 10 0 L 42 0" stroke="#fff" strokeWidth={8} />
      </svg>
    </div>
  );
};

// The channel's way: the line as a small subtitle in white boxes under the scene.
const Subtitle: React.FC<{text: string; lead: number; top?: number; big?: boolean; ink?: boolean}> = ({text, lead, top, big, ink}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  if (frame / fps < lead - 0.05) return null;
  const pos: React.CSSProperties = top !== undefined ? {top} : {bottom: 56};
  return (
    <div style={{position: 'absolute', left: 60, right: 60, ...pos, display: 'flex', justifyContent: 'center'}}>
      <div style={{fontSize: big ? 46 : 40, lineHeight: 1.35, textAlign: 'center', maxWidth: big ? 920 : 1400, textWrap: 'balance'}}>
        <span style={{background: ink ? 'rgba(242,235,220,0.94)' : '#fff', color: INK, padding: ink ? '4px 14px' : '3px 12px', boxDecorationBreak: 'clone', WebkitBoxDecorationBreak: 'clone',
          fontFamily: FONT, fontWeight: 800, borderRadius: ink ? 6 : 0, boxShadow: ink ? `0 0 0 3px ${INK}` : undefined}}>{text}</span>
      </div>
    </div>
  );
};

// The narrator's line: a dark caption box (people's lines are white), where subtitles go in a Short.
const Narration: React.FC<{text: string; top?: number; big?: boolean}> = ({text, top, big}) => (
  <div style={{position: 'absolute', left: big ? 70 : 160, right: big ? 70 : 160, ...(top !== undefined ? {top} : {bottom: 70}), display: 'flex', justifyContent: 'center'}}>
    <div style={{background: 'rgba(0,0,0,0.78)', color: '#fff', borderRadius: 14, padding: '14px 26px', fontSize: big ? 46 : 40, fontWeight: 700, textAlign: 'center', textWrap: 'balance'}}>
      {text}
    </div>
  </div>
);

const Caption: React.FC<{text: string; top: number; ink?: boolean}> = ({text, top, ink}) =>
  ink ? (
    // The ink look: a cream card with an ink edge, readable over a chalkboard or a dark wall.
    <div style={{position: 'absolute', left: 60, right: 60, top, display: 'flex', justifyContent: 'center'}}>
      <div style={{background: 'rgba(242,235,220,0.95)', border: `4px solid ${INK}`, borderRadius: 10, padding: '8px 22px', fontSize: 50,
        fontFamily: HAND, color: INK, textAlign: 'center', textWrap: 'balance', transform: 'rotate(-1.2deg)'}}>{text}</div>
    </div>
  ) : (
    <div style={{position: 'absolute', left: 80, right: 80, top, textAlign: 'center', fontSize: 52, fontWeight: 400, fontFamily: HAND, color: INK, textWrap: 'balance',
      textShadow: '0 0 6px #fff, 0 0 10px #fff'}}>
      {text}
    </div>
  );
