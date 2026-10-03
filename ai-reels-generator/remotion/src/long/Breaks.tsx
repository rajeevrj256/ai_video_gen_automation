import React from 'react';
import {Easing, Img, interpolate, random, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {COLORS, FONT, clamp, exitProgress} from '../theme';
import type {Chapter} from './types';

// The break into a chapter. It used to be one card on every chapter of every video ("CHAPTER 1 OF 7",
// a gold bar, the title over rays). Now each break has its own style (reelgen/longform.BREAKS picks
// them so neighbours and recent videos differ) and shows the chapter's own line (a question or a
// sharp phrase Claude wrote for it) over the chapter's own background photo when there is one.

export type BreakStyle = 'blackout' | 'lowerthird' | 'trailer' | 'split' | 'cut';

type Props = {chapter: Chapter; frames: number; accent: string; tint: string; plate?: string | null; count: number};

const Photo: React.FC<{plate?: string | null; tint: string; brightness: number; zoom: number; style?: React.CSSProperties}> = ({plate, tint, brightness, zoom, style}) =>
  plate ? (
    <div style={{position: 'absolute', inset: 0, overflow: 'hidden', ...style}}>
      <Img src={staticFile(plate)} style={{width: '100%', height: '100%', objectFit: 'cover', transform: `scale(${zoom})`, filter: `brightness(${brightness}) saturate(0.9)`}} />
      <div style={{position: 'absolute', inset: 0, background: `linear-gradient(120deg, ${tint}bb, transparent 70%)`}} />
    </div>
  ) : (
    <div style={{position: 'absolute', inset: 0, background: `radial-gradient(ellipse at 60% 40%, ${tint}, ${COLORS.ink} 75%)`, ...style}} />
  );

const lineText = (c: Chapter) => (c.text || c.title).trim();

// Fade to black, a beat of nothing, the line typed in, then the chapter's photo rises behind it.
const Blackout: React.FC<Props> = ({chapter, frames, accent, tint, plate}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const text = lineText(chapter);
  const typeFrom = Math.round(0.55 * fps);
  const shown = Math.floor(interpolate(frame, [typeFrom, typeFrom + Math.min(text.length * 1.4, fps * 1.1)], [0, text.length], clamp));
  const rise = interpolate(frame, [frames * 0.55, frames], [0, 1], {...clamp, easing: Easing.in(Easing.cubic)});
  const caret = frame > typeFrom && frame % 16 < 9;
  return (
    <div style={{position: 'absolute', inset: 0, background: '#000'}}>
      <div style={{position: 'absolute', inset: 0, opacity: rise * 0.9}}>
        <Photo plate={plate} tint={tint} brightness={0.5} zoom={1.15 - 0.05 * rise} />
      </div>
      <div style={{position: 'absolute', left: 180, right: 180, top: 0, bottom: 0, display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
        <div style={{fontSize: 92, fontWeight: 800, lineHeight: 1.15, textAlign: 'center', textWrap: 'balance', color: COLORS.text, fontFamily: FONT}}>
          {text.slice(0, shown)}
          <span style={{color: accent, opacity: caret ? 1 : 0}}>▍</span>
        </div>
      </div>
    </div>
  );
};

// A documentary lower third over the chapter's photo, with progress dots instead of "chapter N of M".
const LowerThird: React.FC<Props> = ({chapter, frames, accent, tint, plate, count}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const e = spring({frame: frame - 6, fps, config: {damping: 16, mass: 0.8}});
  const bar = interpolate(frame, [0, 14], [0, 1], {...clamp, easing: Easing.out(Easing.cubic)});
  const exit = exitProgress(frame, frames, 8);
  return (
    <div style={{position: 'absolute', inset: 0, opacity: 1 - exit}}>
      <Photo plate={plate} tint={tint} brightness={0.62} zoom={1.05 + 0.05 * (frame / frames)} />
      <div style={{position: 'absolute', inset: 0, background: 'linear-gradient(0deg, rgba(0,0,0,0.85) 0%, transparent 55%)'}} />
      <div style={{position: 'absolute', left: 140, bottom: 170, width: 12, height: 190 * bar, background: accent, boxShadow: `0 0 20px ${accent}`}} />
      <div style={{position: 'absolute', left: 190, right: 260, bottom: 170, transform: `translateX(${(1 - e) * -60}px)`, opacity: e}}>
        <div style={{display: 'flex', gap: 12, marginBottom: 22}}>
          {Array.from({length: count}, (_, i) => (
            <div key={i} style={{width: i + 1 === chapter.index ? 46 : 14, height: 14, borderRadius: 7, background: i + 1 <= chapter.index ? accent : 'rgba(255,255,255,0.35)'}} />
          ))}
        </div>
        <div style={{fontSize: 84, fontWeight: 900, lineHeight: 1.08, color: COLORS.text, textWrap: 'balance', fontFamily: FONT}}>{lineText(chapter)}</div>
      </div>
    </div>
  );
};

// The hook's trailer look: letterbox bars close in, the line is slammed in with a glitch.
const Trailer: React.FC<Props> = ({chapter, frames, accent, tint, plate}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const bars = interpolate(frame, [0, 10], [0, 1], {...clamp, easing: Easing.out(Easing.cubic)});
  const slam = spring({frame: frame - 8, fps, config: {damping: 9, mass: 0.6}});
  const glitch = frame >= 8 && frame < 14 ? (random(`g${frame}`) - 0.5) * 40 : 0;
  const exit = exitProgress(frame, frames, 6);
  return (
    <div style={{position: 'absolute', inset: 0, background: '#000', opacity: 1 - exit}}>
      <Photo plate={plate} tint={tint} brightness={0.38} zoom={1.25 - 0.1 * (frame / frames)} />
      <div style={{position: 'absolute', inset: 0, background: `repeating-conic-gradient(from ${frame * 0.4}deg at 50% 120%, ${accent}12 0deg 5deg, transparent 5deg 16deg)`}} />
      <div style={{position: 'absolute', left: 0, right: 0, top: 0, height: 130 * bars, background: '#000'}} />
      <div style={{position: 'absolute', left: 0, right: 0, bottom: 0, height: 130 * bars, background: '#000'}} />
      <div style={{position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0 200px'}}>
        <div
          style={{
            fontSize: 110,
            fontWeight: 900,
            textTransform: 'uppercase',
            textAlign: 'center',
            lineHeight: 1.02,
            letterSpacing: '-0.01em',
            color: COLORS.text,
            textWrap: 'balance',
            fontFamily: FONT,
            opacity: Math.min(1, slam * 1.4),
            transform: `scale(${2.2 - 1.2 * Math.min(1, slam)}) translateX(${glitch}px)`,
            textShadow: glitch ? `${glitch / 4}px 0 #ff0050, ${-glitch / 4}px 0 #00e5ff` : `0 0 40px ${accent}88`,
          }}
        >
          {lineText(chapter)}
        </div>
      </div>
    </div>
  );
};

// A panel in the chapter's colour sweeps across with the line; the photo holds the other side.
const Split: React.FC<Props> = ({chapter, frames, accent, tint, plate}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const sweep = interpolate(frame, [0, 14], [0, 1], {...clamp, easing: Easing.out(Easing.exp)});
  const e = spring({frame: frame - 10, fps, config: {damping: 15}});
  const exit = interpolate(frame, [frames - 10, frames], [0, 1], {...clamp, easing: Easing.in(Easing.cubic)});
  return (
    <div style={{position: 'absolute', inset: 0, background: COLORS.ink}}>
      <Photo plate={plate} tint={tint} brightness={0.55} zoom={1.1} style={{left: '42%'}} />
      <div
        style={{
          position: 'absolute',
          top: 0,
          bottom: 0,
          left: 0,
          width: `${46 * sweep}%`,
          transform: `translateX(${-exit * 100}%)`,
          background: `linear-gradient(160deg, ${tint}, ${COLORS.ink})`,
          borderRight: `10px solid ${accent}`,
          boxShadow: `0 0 50px ${accent}55`,
        }}
      />
      <div style={{position: 'absolute', left: 110, width: '34%', top: 0, bottom: 0, display: 'flex', alignItems: 'center', opacity: e * (1 - exit)}}>
        <div style={{fontSize: 78, fontWeight: 900, lineHeight: 1.1, color: COLORS.text, textWrap: 'balance', fontFamily: FONT, transform: `translateY(${(1 - e) * 40}px)`}}>
          {lineText(chapter)}
        </div>
      </div>
    </div>
  );
};

// A quick punch: the line hits big over the photo for a moment and the story goes on.
const Cut: React.FC<Props> = ({chapter, frames, accent, tint, plate}) => {
  const frame = useCurrentFrame();
  const p = frame / Math.max(1, frames);
  const flash = interpolate(frame, [0, 4], [0.85, 0], clamp);
  return (
    <div style={{position: 'absolute', inset: 0, background: '#000'}}>
      <Photo plate={plate} tint={tint} brightness={0.45} zoom={1.0 + 0.12 * p} />
      <div style={{position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0 220px'}}>
        <div style={{fontSize: 96, fontWeight: 900, textAlign: 'center', lineHeight: 1.08, color: COLORS.text, textWrap: 'balance', fontFamily: FONT, transform: `scale(${1.08 - 0.08 * p})`, textShadow: `0 0 30px ${accent}66`}}>
          {lineText(chapter)}
        </div>
      </div>
      <div style={{position: 'absolute', inset: 0, background: '#fff', opacity: flash}} />
    </div>
  );
};

export const ChapterBreak: React.FC<Props & {style?: BreakStyle}> = (p) => {
  switch (p.style) {
    case 'blackout':
      return <Blackout {...p} />;
    case 'lowerthird':
      return <LowerThird {...p} />;
    case 'trailer':
      return <Trailer {...p} />;
    case 'split':
      return <Split {...p} />;
    case 'cut':
      return <Cut {...p} />;
    default:
      return <LowerThird {...p} />;
  }
};
