import React from 'react';
import {Sequence, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {Audio} from '../Audio';
import {Cues, Music} from '../Sound';
import {FONT, clamp, useFonts} from '../theme';
import {Layer} from '../Layer';
import {BackdropView} from './Backdrops';
import {ActionLayer, ItemView, itemWidth, layout} from './Effects';
import {Mascot, shade} from './Mascot';
import {Person} from './Person';
import type {PersonSpec, ToonProps, ToonShot} from './types';

// Toon Explainers (reelgen/toon.py): one shot per sentence. Each shot = a flat illustrated setting,
// cartoon people and/or the video's mascot, objects, and one action that fires on its word; numbered
// countdown cards, date cards and big word slams; whip/zoom/flash cuts and a moving camera.

const MASCOT_X = {left: 520, center: 960, right: 1400};
const MASCOT_S = {s: 300, m: 420, l: 560};
const PERSON_X = {'far-left': 260, left: 600, center: 960, right: 1320, 'far-right': 1660};
const OWN_STAGE = new Set(['toggle-off', 'toggle-on', 'gauge-up', 'gauge-down', 'bars', 'arrow-up', 'arrow-down', 'fly-out', 'rain', 'versus']);

const Slam: React.FC<{text: string; style: ToonProps['style']['slam']; frame: number; fps: number; pal: ToonProps['palette']; low: boolean}> = ({text, style, frame, fps, pal, low}) => {
  const s = spring({frame, fps, config: {damping: 10, mass: 0.6}});
  const base: React.CSSProperties = {fontFamily: FONT, fontWeight: 900, fontSize: text.length > 14 ? 92 : 118, textTransform: 'uppercase', letterSpacing: 2, whiteSpace: 'nowrap'};
  const box = style === 'pill'
    ? {...base, background: '#fff', color: '#15151c', padding: '14px 44px', borderRadius: 26, boxShadow: '0 12px 0 rgba(0,0,0,0.25)'}
    : style === 'stamp'
      ? {...base, color: pal.hot, border: `12px solid ${pal.hot}`, padding: '6px 36px', borderRadius: 14, background: 'rgba(255,255,255,0.85)', transform: 'rotate(-6deg)'}
      : {...base, color: '#fff', WebkitTextStroke: '10px #15151c', paintOrder: 'stroke' as const, textShadow: '0 10px 0 rgba(0,0,0,0.3)'};
  return (
    <div style={{position: 'absolute', left: 0, right: 0, top: low ? 760 : 90, display: 'flex', justifyContent: 'center', transform: `scale(${s})`, opacity: Math.min(1, s * 2)}}>
      <div style={box}>{text}</div>
    </div>
  );
};

const NumberCard: React.FC<{text: string; sub?: string | null; style: ToonProps['style']['card']; frame: number; fps: number; pal: ToonProps['palette']}> = ({text, sub, style, frame, fps, pal}) => {
  const s = spring({frame, fps, config: {damping: 12, mass: 0.8}});
  const spin = interpolate(s, [0, 1], [-200, 0]);
  const num = (
    <div style={{fontFamily: FONT, fontWeight: 900, fontSize: 300, color: '#15151c', lineHeight: 1}}>{text}</div>
  );
  const shape = style === 'circle'
    ? <div style={{width: 520, height: 520, borderRadius: '50%', background: 'radial-gradient(circle at 35% 30%, #fff, #d6dae0)', border: `26px solid ${shade(pal.paper, -0.3)}`, display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 22px 0 rgba(0,0,0,0.25)'}}>{num}</div>
    : style === 'ticket'
      ? <div style={{width: 700, height: 420, borderRadius: 40, background: pal.paper, border: `14px dashed ${shade(pal.accent, -0.2)}`, display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 22px 0 rgba(0,0,0,0.25)'}}>{num}</div>
      : <div style={{width: 520, height: 560, clipPath: 'polygon(50% 0, 100% 22%, 100% 78%, 50% 100%, 0 78%, 0 22%)', background: pal.paper, display: 'flex', alignItems: 'center', justifyContent: 'center'}}>{num}</div>;
  return (
    <div style={{position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 40}}>
      <div style={{transform: `scale(${s}) rotate(${spin}deg)`}}>{shape}</div>
      {sub ? <div style={{fontFamily: FONT, fontWeight: 900, fontSize: 64, color: '#fff', textTransform: 'uppercase', textShadow: '0 6px 0 rgba(0,0,0,0.3)', opacity: interpolate(frame, [12, 24], [0, 1], clamp), maxWidth: 1500, textAlign: 'center'}}>{sub}</div> : null}
    </div>
  );
};

const TitleCard: React.FC<{text: string; frame: number; fps: number; pal: ToonProps['palette']}> = ({text, frame, fps, pal}) => {
  const s = spring({frame: frame - 3, fps, config: {damping: 11, mass: 0.7}});
  const words = text.split(' ');
  return (
    <div style={{position: 'absolute', left: 0, right: 0, top: 120, display: 'flex', justifyContent: 'center'}}>
      <div style={{fontFamily: FONT, fontWeight: 900, fontSize: text.length > 40 ? 84 : 104, lineHeight: 1.08, color: '#fff', textAlign: 'center', maxWidth: 1600,
        textTransform: 'uppercase', WebkitTextStroke: '12px #15151c', paintOrder: 'stroke', textShadow: `0 12px 0 ${shade(pal.accent, -0.3)}`,
        transform: `scale(${s}) rotate(${(1 - s) * -4}deg)`}}>
        {words.map((w, i) => <span key={i} style={{opacity: interpolate(frame, [i * 2, i * 2 + 6], [0, 1], clamp)}}>{w} </span>)}
      </div>
    </div>
  );
};

const DateCard: React.FC<{text: string; frame: number; fps: number}> = ({text, frame, fps}) => {
  const s = spring({frame: frame - 4, fps, config: {damping: 12}});
  return (
    <div style={{position: 'absolute', left: 70, top: 70, transform: `translateX(${(1 - s) * -500}px) rotate(-3deg)`, fontFamily: FONT}}>
      <div style={{background: '#fff', borderRadius: 16, overflow: 'hidden', boxShadow: '0 12px 0 rgba(0,0,0,0.2)', minWidth: 340}}>
        <div style={{background: '#E5484D', color: '#fff', fontWeight: 900, fontSize: 30, padding: '8px 22px', letterSpacing: 4}}>DATE</div>
        <div style={{color: '#15151c', fontWeight: 900, fontSize: 64, padding: '10px 22px'}}>{text}</div>
      </div>
    </div>
  );
};

const Caption: React.FC<{shot: ToonShot; t: number}> = ({shot, t}) => {
  // The phrase being spoken: up to ~9 words around the current word, two short lines.
  const w = shot.words;
  if (!w.length) return null;
  const now = t - shot.lead;
  let i = w.findIndex((x) => x.end >= now);
  if (i < 0) i = w.length - 1;
  // Even chunks of at most 8 words (17 words → 9 + 8, never 9 + "to slip").
  const per = Math.ceil(w.length / Math.ceil(w.length / 8));
  const start = Math.floor(i / per) * per;
  const text = w.slice(start, start + per).map((x) => x.text).join(' ');
  return (
    <div style={{position: 'absolute', left: 0, right: 0, bottom: 58, display: 'flex', justifyContent: 'center'}}>
      <div style={{fontFamily: FONT, fontWeight: 800, fontSize: 34, color: '#fff', background: 'rgba(0,0,0,0.55)', padding: '6px 18px', borderRadius: 10, maxWidth: 1100, textAlign: 'center'}}>{text}</div>
    </div>
  );
};

const Foreground: React.FC<{kind: string; tone: string}> = ({kind, tone}) =>
  kind === 'stage' ? (
    <svg viewBox="0 0 1920 1080" style={{position: 'absolute', inset: 0}}>
      <path d="M800 700 H1120 L1090 1080 H830 Z" fill={shade(tone, -0.55)} />
      <rect x={780} y={680} width={360} height={40} rx={10} fill={shade(tone, -0.65)} />
      {[900, 960, 1020].map((x, i) => <g key={x}><line x1={x} y1={690} x2={x + (i - 1) * 30} y2={610} stroke="#222" strokeWidth={9} /><rect x={x + (i - 1) * 30 - 14} y={575} width={28} height={44} rx={12} fill={['#E5484D', '#333', '#2F7DE1'][i]} /></g>)}
    </svg>
  ) : kind === 'desk' ? (
    <svg viewBox="0 0 1920 1080" style={{position: 'absolute', inset: 0}}>
      <rect x={300} y={700} width={1320} height={44} rx={12} fill={shade(tone, -0.5)} />
      <rect x={340} y={744} width={1240} height={340} fill={shade(tone, -0.6)} />
    </svg>
  ) : null;

const PersonView: React.FC<{spec: PersonSpec; frame: number; talk: number; backdrop: string}> = ({spec, frame, talk, backdrop}) => {
  const seated = spec.seated || backdrop === 'desk';
  const atPodium = backdrop === 'stage' && spec.pos === 'center';
  // Chest-up behind a desk or a podium (big, like a close-up), full figure elsewhere.
  const H = seated ? 1000 : atPodium ? 1100 : 820;
  const x = PERSON_X[spec.pos] ?? 960;
  const top = seated ? 700 - (410 / 600) * H : atPodium ? 690 - (300 / 600) * H : 1010 - (590 / 600) * H;
  const enter = spring({frame, fps: 30, config: {damping: 14}});
  return (
    <div style={{position: 'absolute', left: x - H / 4, top: top + (1 - enter) * 60, opacity: enter}}>
      <Person look={spec.look} pose={seated ? (spec.pose === 'stand' ? 'sit' : spec.pose) : spec.pose} mood={spec.mood} talk={talk} frame={frame} height={H} flip={spec.flip} seated={seated} />
    </div>
  );
};

const ShotView: React.FC<{shot: ToonShot; props: ToonProps; index: number}> = ({shot, props, index}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const pal = props.palette;
  const t = frame / fps;
  const frames = Math.max(1, Math.round(shot.duration * fps));
  const tone = pal.tones[shot.tone % pal.tones.length];
  const p = Math.max(0, (t - shot.at) / 0.9); // the action, from its word
  const ownStage = OWN_STAGE.has(shot.action);
  const given = shot.mascot && !shot.card?.kind.startsWith('number') ? shot.mascot : null;
  // An action that fills the middle (switch, gauge, chart, versus...) moves the mascot to the side, smaller.
  const m = given && ownStage && given.pos === 'center' ? {...given, pos: 'right' as const, size: 's' as const} : given;
  const mascotAt = m ? {x: MASCOT_X[m.pos], y: 560} : null;
  const items = ownStage ? [] : shot.items.slice(0, 5);
  // What is already on screen, as x-ranges: the mascot, every person, the podium on a stage.
  const occupied: [number, number][] = [
    ...(m ? [[MASCOT_X[m.pos] - MASCOT_S[m.size] / 2 - 20, MASCOT_X[m.pos] + MASCOT_S[m.size] / 2 + 20] as [number, number]] : []),
    ...(shot.people ?? []).map((sp) => {
      const x = PERSON_X[sp.pos] ?? 960, half = sp.seated || shot.backdrop === 'desk' ? 270 : 200;
      return [x - half, x + half] as [number, number];
    }),
    ...(shot.backdrop === 'stage' ? [[760, 1160] as [number, number]] : []),
  ];
  const base = items.length > 3 ? 200 : 250;
  const placed = layout(items.length ? items.map((it) => itemWidth(it, base)) : [base], occupied);
  const spots = placed.pos;
  const size = Math.round(base * placed.scale);
  const isNumber = shot.card?.kind === 'number';
  // Camera and the cut into this shot.
  const cam = shot.camera === 'push' ? interpolate(frame, [0, frames], [1, 1.07]) : shot.camera === 'pull' ? interpolate(frame, [0, frames], [1.07, 1]) : 1;
  const pan = shot.camera === 'pan' ? interpolate(frame, [0, frames], [30, -30]) : 0;
  const zoomIn = shot.enter === 'zoom' ? interpolate(frame, [0, 10], [1.25, 1], clamp) : 1;
  const shake = shot.action === 'shake' && p > 0 && p < 1 ? Math.sin(frame * 3) * 14 : 0;
  // Who is talking: the mouth moves while the narrator says a word (the people act the line).
  const now = t - shot.lead;
  const speaking = shot.words.some((w) => now >= w.start && now <= w.end);
  const talk = speaking ? 0.5 + 0.5 * Math.sin(frame * 1.3) : 0;
  return (
    <Layer name={`shot ${index + 1}`}>
      <div style={{position: 'absolute', inset: 0, transform: `scale(${cam * zoomIn}) translate(${pan + shake}px, ${shake * 0.5}px)`}}>
        <BackdropView kind={isNumber ? 'flat' : shot.backdrop} p={pal} tone={tone} seed={props.style.seed + shot.segment * 13} frame={frame} />
        {isNumber ? (
          <NumberCard text={shot.card!.text} sub={shot.card!.sub} style={props.style.card} frame={frame} fps={fps} pal={pal} />
        ) : (
          <>
            {shot.crowd ? Array.from({length: 6}, (_, i) => {
              const x = ((frame * (9 + i)) + i * 360) % 2300 - 200;
              return <div key={`c${i}`} style={{position: 'absolute', left: x, top: 760 + (i % 2) * 40}}>
                <Person look={{...(shot.people?.[0]?.look ?? defaultLook), shirt: ['#E5484D', '#2F7DE1', '#2FB36D', '#F2B705', '#9b5de5', '#ff8fab'][i], skin: ['#F6D3B3', '#B97A50', '#EBB98F', '#8D5A3B', '#D69A6C', '#F6D3B3'][i], tie: null, coat: null}} pose="run" mood="scared" talk={0} frame={frame + i * 4} height={300} />
              </div>;
            }) : null}
            {(shot.people ?? []).map((sp, i) => <PersonView key={`p${i}`} spec={sp} frame={frame} talk={sp.talking ? talk : 0} backdrop={shot.backdrop} />)}
            <Foreground kind={shot.people?.length ? shot.backdrop : ''} tone={tone} />
{shot.action === 'connect' ? ( // the lines run behind the objects, never across their labels
                        <ActionLayer action={shot.action} p={p} frame={frame} fps={fps} pal={pal} items={shot.items} spots={spots} mascotAt={mascotAt}
              mascot={props.mascot} values={shot.values} seed={props.style.seed + index} />
            ) : null}
            {items.map((it, i) => {
              const s = spring({frame: frame - i * 4 - (shot.action === 'pop' ? Math.round(shot.at * fps) : 0), fps, config: {damping: 11, mass: 0.6}});
              const fall = shot.action === 'strings-burn' ? Math.max(0, p - 0.6) * 900 : 0;
              const sp = spots[i];
              if (i === 0 && (shot.action === 'lock' || shot.action === 'unlock')) return null; // the padlock stands in its place
              return <div key={i} style={{position: 'absolute', left: sp.x, top: sp.y - size / 2 + fall + Math.sin((frame + i * 20) / 18) * 6, transform: `translateX(-50%) scale(${s})`}}>
                <ItemView item={it} s={size} p={pal} frame={frame} k={i} />
              </div>;
            })}
            {m ? (() => {
              const size = MASCOT_S[m.size];
              const enter = spring({frame: frame - (shot.action === 'burst' ? Math.round(shot.at * fps) : 0), fps, config: {damping: 12}});
              return <div style={{position: 'absolute', left: mascotAt!.x - size / 2, top: mascotAt!.y - size / 2, transform: `scale(${enter})`}}>
                <Mascot shape={props.mascot.shape} color={props.mascot.color} accessory={props.mascot.accessory} mood={m.mood} tint={m.tint} frame={frame} size={size} flip={m.pos === 'right'} />
              </div>;
            })() : null}
{shot.action === 'connect' ? null : (
                        <ActionLayer action={shot.action} p={p} frame={frame} fps={fps} pal={pal} items={shot.items} spots={spots} mascotAt={mascotAt}
              mascot={props.mascot} values={shot.values} seed={props.style.seed + index} />
            )}
            {shot.slam && t >= Math.max(0, shot.at - 0.1) ? (
              <Slam text={shot.slam} style={props.style.slam} frame={frame - Math.round(Math.max(0, shot.at - 0.1) * fps)} fps={fps} pal={pal}
                low={ownStage || shot.action === 'strings' || shot.action === 'strings-burn'} />
            ) : null}
            {shot.card?.kind === 'date' ? <DateCard text={shot.card.text} frame={frame} fps={fps} /> : null}
            {shot.card?.kind === 'title' ? <TitleCard text={shot.card.text} frame={frame} fps={fps} pal={pal} /> : null}
          </>
        )}
      </div>
      {shot.enter === 'flash' ? <div style={{position: 'absolute', inset: 0, background: '#fff', opacity: interpolate(frame, [0, 8], [0.9, 0], clamp)}} /> : null}
      {shot.enter === 'whip' && frame < 12 ? (
        <div style={{position: 'absolute', top: -200, bottom: -200, width: 900, left: interpolate(frame, [0, 11], [-300, 2300]), background: pal.paper, transform: 'skewX(-24deg)', boxShadow: `0 0 0 40px ${pal.accent}`}} />
      ) : null}
      {props.captions ? <Caption shot={shot} t={t} /> : null}
    </Layer>
  );
};

const defaultLook = {skin: '#EBB98F', hair: 'short' as const, hairColor: '#3b2a1e', beard: 'none' as const, glasses: false, shirt: '#2F7DE1', tie: null, pants: '#2b3245', coat: null};

export const Toon: React.FC<ToonProps> = (props) => {
  useFonts();
  const {fps} = useVideoConfig();
  const f = (s: number) => Math.round(s * fps);
  const {shots} = props;
  return (
    <Layer name="toon" style={{backgroundColor: props.palette.ink, fontFamily: FONT, overflow: 'hidden'}}>
      {props.soundOnly ? null : shots.map((s, i) => {
        const next = shots[i + 1];
        const len = Math.max(1, (next ? f(next.start) : f(s.start + s.duration)) - f(s.start));
        return (
          <Sequence key={i} name={`shot ${i + 1} (${s.action}${s.card ? `, ${s.card.kind}` : ''})`} from={f(s.start)} durationInFrames={len}>
            <ShotView shot={s} props={props} index={i} />
          </Sequence>
        );
      })}
      {!props.soundOnly && props.watermark ? (
        <div style={{position: 'absolute', left: 36, bottom: 30, fontFamily: FONT, fontWeight: 900, fontSize: 30, color: '#fff', opacity: 0.85, textShadow: '0 3px 0 rgba(0,0,0,0.4)'}}>{props.watermark}</div>
      ) : null}
      {shots.map((s, i) => (s.audio ? (
        <Sequence key={`v${i}`} name={`voice ${i + 1}`} from={f(s.start + s.lead)}>
          <Audio src={staticFile(s.audio)} />
        </Sequence>
      ) : null))}
      {/* The cold open's trailer track, then the video's own track from the title card on. The narration
          barely pauses, so the main track's level under the voice (duck) has to stay audible. */}
      {props.hookMusic ? (
        <Sequence name="hook music" durationInFrames={f((props.hookEnd ?? 0) + 1.5)}>
          <Music src={props.hookMusic} speech={props.speech.filter(([a]) => a < (props.hookEnd ?? 0))} full={0.6} duck={0.2} loop={false} />
        </Sequence>
      ) : null}
      {props.music ? (
        <Sequence name="music" from={f(props.musicFrom ?? 0)}>
          <Music src={props.music} speech={props.speech.map(([a, b]) => [a - (props.musicFrom ?? 0), b - (props.musicFrom ?? 0)] as [number, number])} full={0.26} duck={0.13} />
        </Sequence>
      ) : null}
      <Cues cues={props.cues} speech={props.speech} />
    </Layer>
  );
};
