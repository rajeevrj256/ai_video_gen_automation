import '@fontsource/permanent-marker/400.css';
import React, {useEffect, useState} from 'react';
import {Easing, Html5Audio, Sequence, continueRender, delayRender, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {FONT, clamp, useFonts} from '../theme';
import {Layer} from '../Layer';
import {Cues, Music} from '../Sound';
import type {ActorState, CastMember, Emote, Face, Look, Pose, Prop, Setting, Shot, StoryProps, Word} from './types';

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

const rig = (pose: Pose, t: number): Rig => {
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
      return {...s, hip: [0, -120], neck: [0, -272], head: [0, -272 - HEAD + 4],
        lE: [-30, -212], lH: [22, -170], rE: [32, -212], rH: [52, -168],
        lK: [62, -122], lF: [64, 0], rK: [80, -118], rF: [86, 0]};
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
      return {...s, rE: [62, -330], rH: [92 + 18 * Math.sin(t * 14), -420]};
    case 'hold':
      return {...s, rE: [52, -262], rH: [70, -270], lE: [-26, -250], lH: [44, -262]};
    default:
      return s;
  }
};

// ---------- the composition ----------

export const StickStory: React.FC<StoryProps> = ({cast, shots, music, cues, speech, vertical = false, dialogue = 'subtitle'}) => {
  useFonts();
  useHandFont();
  const {fps} = useVideoConfig();
  const f = (s: number) => Math.round(s * fps);
  const looks: Record<string, Look> = Object.fromEntries(cast.map((c) => [c.id, c.look]));
  return (
    <Layer name="stick story" style={{backgroundColor: PAPER, fontFamily: FONT}}>
      {shots.map((s, i) => (
        <Sequence key={i} name={`shot ${i + 1} ${s.setting}${s.speaker ? ` (${s.speaker})` : ''}`} from={f(s.start)} durationInFrames={Math.max(1, f(s.duration))}>
          <ShotView shot={s} looks={looks} cast={cast} vertical={vertical} dialogue={dialogue} newScene={i === 0 || shots[i - 1].scene !== s.scene} />
        </Sequence>
      ))}
      {shots.map((s, i) =>
        s.audio ? (
          <Sequence key={`v${i}`} name={`voice ${i + 1}`} from={f(s.start + s.lead)}>
            <Html5Audio src={staticFile(s.audio)} />
          </Sequence>
        ) : null,
      )}
      {music ? <Music src={music} speech={speech} full={0.16} duck={0.06} /> : null}
      <Cues cues={cues} speech={speech} />
    </Layer>
  );
};

// ---------- one shot ----------

const ShotView: React.FC<{shot: Shot; looks: Record<string, Look>; cast: CastMember[]; newScene: boolean; vertical: boolean; dialogue: 'subtitle' | 'bubble'}> = ({shot, looks, newScene, vertical, dialogue}) => {
  const frame = useCurrentFrame();
  const {fps, width: OW, height: OH} = useVideoConfig();
  // A Short frames the cast close (big heads, like the channel's Shorts): a ~570 px slice of the
  // 1920 px set in the upper part of the frame, following whoever speaks; subtitles go below it.
  const base = vertical ? 1.9 : 1;
  const t = frame / fps;
  const frames = Math.max(1, Math.round(shot.duration * fps));
  const speaking = (id: string) => shot.speaker === id;
  const focus = shot.actors.find((a) => a.id === (shot.focus || shot.speaker)) ?? shot.actors[0];
  let scale = 1;
  // A Short is already framed close: its close-up and punch-in are gentler.
  const zoomMax = vertical ? 1.22 : 1.5;
  if (shot.camera === 'close') scale = interpolate(frame, [0, 10], [1 + (zoomMax - 1) * 0.5, zoomMax], {...clamp, easing: Easing.out(Easing.cubic)});
  if (shot.camera === 'punch') scale = 1 + (vertical ? 0.1 : 0.2) * spring({frame: frame - Math.round(shot.lead * fps), fps, config: {damping: 14}});
  const shake = shot.camera === 'shake' && frame < 16 ? Math.sin(frame * 2.7) * (16 - frame) * 1.6 : 0;
  const fx = focus ? focus.x : W / 2;
  const fy = FLOOR - 300;
  const group = shot.actors.length ? shot.actors.reduce((n, a) => n + a.x, 0) / shot.actors.length : W / 2;
  const total = base * scale;
  const halfW = OW / (2 * total);
  const halfH = OH / (2 * total);
  const wantX = vertical ? (scale > 1 ? fx : group) : scale > 1 ? fx : W / 2;
  const cx = Math.min(W - Math.min(halfW, W / 2), Math.max(Math.min(halfW, W / 2), wantX));
  const cy = scale > 1 ? Math.min(H - halfH, Math.max(halfH, fy)) : vertical ? FLOOR - 250 : H / 2;
  const floorY = (FLOOR - (shot.setting === 'kitchen' ? COUNTER : 0) - cy) * total + OH / 2;
  const flash = newScene ? interpolate(frame, [0, 5], [0.9, 0], clamp) : 0;
  const speaker = shot.actors.find((a) => a.id === shot.speaker);
  return (
    <Layer name="shot">
      <svg width={OW} height={OH} viewBox={`0 0 ${OW} ${OH}`} style={{position: 'absolute', inset: 0}}>
        <g transform={`translate(${OW / 2 + shake} ${OH / 2}) scale(${total}) translate(${-cx} ${-cy})`}>
          <SetView setting={shot.setting} sign={shot.sign} />
          {shot.actors.map((a) => (
            <Figure key={a.id} a={a} look={looks[a.id] ?? 'boy'} t={t} frame={frame} frames={frames}
              talking={speaking(a.id) ? shot.words.map((w) => ({...w, start: w.start + shot.lead, end: w.end + shot.lead})) : []} />
          ))}
          <SetFront setting={shot.setting} xs={shot.actors.map((a) => a.x)} t={t} />
        </g>
      </svg>
      {speaker && shot.text && dialogue === 'subtitle' ? (
        <Subtitle text={shot.text} lead={shot.lead} top={vertical ? floorY + 40 : undefined} big={vertical} />
      ) : null}
      {speaker && shot.text && dialogue === 'bubble' ? (
        <Bubble text={shot.text} words={shot.words} lead={shot.lead} x={(speaker.x - cx) * total + OW / 2}
          y={(FLOOR - 470 - (speaker.pose === 'sit' ? -46 : 0) - cy) * total + OH / 2} big={vertical} />
      ) : null}
      {!speaker && shot.text ? <Narration text={shot.text} /> : null}
      {shot.caption ? <Caption text={shot.caption} top={vertical ? 230 : 36} /> : null}
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
    case 'shake':
      dx = t < 0.7 ? Math.sin(t * 60) * 10 : 0;
      break;
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
  const walking = (a.action.startsWith('walk-in') && t < 0.8) || (a.action.startsWith('walk-out') && t > d - 1);
  return {dx, dy, rot, walking};
};

const Figure: React.FC<{a: ActorState; look: Look; t: number; frame: number; frames: number; talking: Word[]}> = ({a, look, t, frame, frames, talking}) => {
  const {fps} = useVideoConfig();
  const {dx, dy, rot, walking} = actionOffset(a, t, frames, fps);
  const pose: Pose = walking ? 'walk' : a.pose;
  const small = look === 'kid' ? 0.78 : 1;
  const r = rig(pose, t);
  const breathe = pose === 'lie' ? 0 : Math.sin(t * 2.4 + a.x) * 3;
  const speakingNow = talking.some((w) => t >= w.start && t <= w.end);
  const mouthOpen = speakingNow && frame % 6 < 3;
  const lying = pose === 'lie' || a.action === 'fall';
  const limb = (p: Pt, k: Pt, e: Pt) => `M ${p[0]} ${p[1]} Q ${k[0]} ${k[1]} ${e[0]} ${e[1]}`;
  return (
    <g transform={`translate(${a.x + dx} ${FLOOR + dy}) rotate(${pose === 'lie' ? 0 : rot}) scale(${a.facing * small} ${small})`}>
      <g transform={pose === 'lie' ? 'translate(-150 -40) rotate(-90 0 0)' : `translate(0 ${breathe})`}>
        <ellipse cx={0} cy={4} rx={60} ry={9} fill="rgba(0,0,0,0.18)" stroke="none" />
        <g stroke={INK} strokeWidth={LINE} fill="none" strokeLinecap="round" strokeLinejoin="round">
          <path d={limb(r.hip, r.lK, r.lF)} />
          <path d={limb(r.hip, r.rK, r.rF)} />
          <line x1={r.hip[0]} y1={r.hip[1]} x2={r.neck[0]} y2={r.neck[1]} />
          {look === 'girl' || look === 'woman' || look === 'old-woman' ? (
            <path d={`M ${r.neck[0] - 4} ${r.neck[1] + 70} L ${r.hip[0] - 46} ${r.hip[1] + 40} L ${r.hip[0] + 46} ${r.hip[1] + 40} Z`} fill={LIGHT} strokeWidth={7} />
          ) : null}
          <path d={limb(r.neck, r.lE, r.lH)} />
          <path d={limb(r.neck, r.rE, r.rH)} />
          <PropView prop={a.prop} text={a.propText} at={r.rH} />
          <g transform={`translate(${r.head[0]} ${r.head[1]}) rotate(${r.tilt})`}>
            <g transform={`scale(${FACE})`}><Hair look={look} back /></g>
            <circle r={HEAD} fill="#FFFFFF" />
            <g transform={`scale(${FACE})`} strokeWidth={LINE / FACE}>
              <Hair look={look} />
              <FaceView face={lying && a.face === 'neutral' ? 'dead' : a.face} frame={frame} mouthOpen={mouthOpen} look={look} />
            </g>
          </g>
        </g>
      </g>
      <g transform={`scale(${a.facing} 1)`}>
        <EmoteView emote={a.emote} t={t} head={[r.head[0] * a.facing, r.head[1]]} />
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
  const talk = mouthOpen ? (
    <g>
      <ellipse cx={ex} cy={26} rx={15} ry={12} fill={INK} stroke="none" />
      <rect x={ex - 9} y={15} width={18} height={5} rx={2} fill="#fff" stroke="none" />
    </g>
  ) : null;
  switch (face) {
    case 'happy':
      return <g strokeWidth={4.2}>{brows}{eyes()}{talk ?? <path d={`M ${ex - 18} 18 Q ${ex} 36 ${ex + 18} 18`} />}</g>;
    case 'laugh':
      return (
        <g strokeWidth={4.2}>
          <path d={`M ${ex - 24} -6 l 8 -8 l 8 8 M ${ex + 10} -6 l 8 -8 l 8 8`} />
          <path d={`M ${ex - 22} 12 Q ${ex} 50 ${ex + 22} 12 Z`} fill={INK} />
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

const PropView: React.FC<{prop: Prop; text?: string; at: Pt}> = ({prop, text, at}) => {
  const [x, y] = at;
  switch (prop) {
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

// ---------- the sets ----------

const COUNTER = 190; // the kitchen counter's height: it hides the legs, the scene reads as a mid shot

// What stands in front of the cast: the kitchen counter with a running tap and soap foam in the sink.
const SetFront: React.FC<{setting: Setting; xs: number[]; t: number}> = ({setting, xs, t}) => {
  if (setting !== 'kitchen') return null;
  const top = FLOOR - COUNTER;
  const left = xs.length ? Math.min(...xs) : 800;
  const tapX = left - 150;
  const foam = Array.from({length: 9}, (_, i) => [left - 70 + i * 17, top - 8 - (i % 3) * 13 - Math.sin(t * 3 + i) * 2, 20 + (i % 4) * 5]);
  return (
    <g>
      <rect x={-400} y={top} width={W + 800} height={H + 400} fill={PAPER} />
      <line x1={-400} y1={top} x2={W + 400} y2={top} stroke={INK} strokeWidth={SET_LINE + 1} />
      <g stroke={INK} strokeWidth={SET_LINE} fill="#fff" strokeLinejoin="round">
        <path d={`M ${tapX} ${top} v -110 h 70 v 30 h -14 v -16 h -42 v 96 Z`} />
        <rect x={tapX - 16} y={top - 128} width={60} height={14} rx={6} />
        {[0, 1, 2].map((k) => (
          <line key={k} x1={tapX + 56 + k * 7} y1={top - 66} x2={tapX + 60 + k * 9} y2={top - 8} stroke="#7fb8e0" strokeWidth={3}
            strokeDasharray="10 8" strokeDashoffset={-t * 120 - k * 6} />
        ))}
        {foam.map(([x, y, r], i) => <circle key={i} cx={x} cy={y} r={r} />)}
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
          <path d={`M 520 ${FLOOR - 4} v -150 q 0 -40 40 -40 h 520 q 40 0 40 40 v 150`} fill={GREY} {...ink} />
          <rect x={470} y={FLOOR - 160} width={90} height={156} rx={20} fill={DARK} {...ink} />
          <rect x={1080} y={FLOOR - 160} width={90} height={156} rx={20} fill={DARK} {...ink} />
          <rect x={1660} y={560} width={150} height={FLOOR - 560} fill={GREY} {...ink} />
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
          {[260, 960, 1660].map((x) => (
            <g key={x}>
              <rect x={x - 130} y={FLOOR - 170} width={260} height={30} fill={GREY} {...ink} />
              <line x1={x - 110} y1={FLOOR - 140} x2={x - 110} y2={FLOOR} {...ink} />
              <line x1={x + 110} y1={FLOOR - 140} x2={x + 110} y2={FLOOR} {...ink} />
            </g>
          ))}
          {floor}
        </g>
      );
    case 'kitchen':
      return (
        <g>
          {base}
          <rect x={200} y={180} width={600} height={180} fill={GREY} {...ink} />
          <line x1={500} y1={180} x2={500} y2={360} {...ink} />
          <rect x={120} y={FLOOR - 300} width={1100} height={300} fill={GREY} {...ink} />
          <rect x={300} y={FLOOR - 300} width={320} height={40} fill={LIGHT} {...ink} />
          <path d={`M 470 ${FLOOR - 300} v -70 h 60 v 20`} fill="none" {...ink} />
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
          <rect x={980} y={FLOOR - 190} width={760} height={110} rx={16} fill={LIGHT} {...ink} />
          <rect x={980} y={FLOOR - 330} width={60} height={330} rx={14} fill={GREY} {...ink} />
          <line x1={1010} y1={FLOOR - 80} x2={1010} y2={FLOOR} {...ink} />
          <line x1={1710} y1={FLOOR - 80} x2={1710} y2={FLOOR} {...ink} />
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
          <rect x={1100} y={FLOOR - 240} width={600} height={40} fill={GREY} {...ink} />
          <line x1={1130} y1={FLOOR - 200} x2={1130} y2={FLOOR} {...ink} />
          <line x1={1670} y1={FLOOR - 200} x2={1670} y2={FLOOR} {...ink} />
          <rect x={1300} y={FLOOR - 420} width={240} height={160} rx={8} fill={DARK} {...ink} />
          <line x1={1420} y1={FLOOR - 260} x2={1420} y2={FLOOR - 240} {...ink} />
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
          <rect x={200} y={FLOOR - 320} width={260} height={60} fill={LIGHT} {...ink} />
          <path d={`M 330 ${FLOOR - 320} v -50 h 40 v 16`} fill="none" {...ink} />
          <line x1={330} y1={FLOOR - 260} x2={330} y2={FLOOR} {...ink} />
          {floor}
        </g>
      );
    case 'park':
      return (
        <g>
          {base}
          <rect x={250} y={540} width={50} height={FLOOR - 540} fill={DARK} {...ink} />
          <circle cx={275} cy={420} r={180} fill={GREY} {...ink} />
          <rect x={1200} y={FLOOR - 140} width={460} height={30} fill={DARK} {...ink} />
          <line x1={1230} y1={FLOOR - 110} x2={1230} y2={FLOOR} {...ink} />
          <line x1={1630} y1={FLOOR - 110} x2={1630} y2={FLOOR} {...ink} />
          <rect x={1200} y={FLOOR - 230} width={460} height={24} fill={DARK} {...ink} />
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
          <rect x={700} y={FLOOR - 220} width={520} height={220} fill={GREY} {...ink} />
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
const Subtitle: React.FC<{text: string; lead: number; top?: number; big?: boolean}> = ({text, lead, top, big}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  if (frame / fps < lead - 0.05) return null;
  const pos: React.CSSProperties = top !== undefined ? {top} : {bottom: 56};
  return (
    <div style={{position: 'absolute', left: 60, right: 60, ...pos, display: 'flex', justifyContent: 'center'}}>
      <div style={{fontSize: big ? 46 : 40, lineHeight: 1.35, textAlign: 'center', maxWidth: big ? 920 : 1400, textWrap: 'balance'}}>
        <span style={{background: '#fff', color: INK, padding: '3px 12px', boxDecorationBreak: 'clone', WebkitBoxDecorationBreak: 'clone',
          fontFamily: FONT, fontWeight: 800}}>{text}</span>
      </div>
    </div>
  );
};

const Narration: React.FC<{text: string}> = ({text}) => (
  <div style={{position: 'absolute', left: 160, right: 160, bottom: 70, display: 'flex', justifyContent: 'center'}}>
    <div style={{background: 'rgba(0,0,0,0.78)', color: '#fff', borderRadius: 14, padding: '14px 26px', fontSize: 40, fontWeight: 700, textAlign: 'center', textWrap: 'balance'}}>
      {text}
    </div>
  </div>
);

const Caption: React.FC<{text: string; top: number}> = ({text, top}) => (
  <div style={{position: 'absolute', left: 80, right: 80, top, textAlign: 'center', fontSize: 52, fontWeight: 400, fontFamily: HAND, color: INK, textWrap: 'balance',
    textShadow: '0 0 6px #fff, 0 0 10px #fff'}}>
    {text}
  </div>
);
