import React from 'react';
import {Easing, Html5Audio, Sequence, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {COLORS, FONT, clamp, exitProgress, useFonts} from '../theme';
import {Layer} from '../Layer';
import type {CaptionGroup} from '../types';
import {VisualView} from './Visuals';
import type {Chapter, LongProps} from './types';

// The whole long video: an animated backdrop that changes colour per chapter, one
// motion-graphic visual per beat, a title card before each chapter, subtitles at the
// bottom, a chapter progress bar, the narration, music and sound effects.

// Each chapter gets its own colour world, so the viewer feels the story move on.
const PALETTES = [
  {a: '#0B1E3F', b: '#1B4F72', accent: '#FFD60A'},
  {a: '#2B0F3A', b: '#6A1B6E', accent: '#4DD0E1'},
  {a: '#0E2E24', b: '#1E6B4E', accent: '#FFB74D'},
  {a: '#3A0E14', b: '#8E2430', accent: '#FFE082'},
  {a: '#14213D', b: '#3D5A80', accent: '#FF8A65'},
  {a: '#1F1F1F', b: '#4A4E69', accent: '#A5D6A7'},
];
export const paletteFor = (chapter: number) => PALETTES[chapter % PALETTES.length];

export const Long: React.FC<LongProps> = ({chapters, beats, captions, music, sfx, duration}) => {
  useFonts();
  const {fps, durationInFrames} = useVideoConfig();
  const f = (s: number) => Math.round(s * fps);
  return (
    <Layer name="long" style={{backgroundColor: COLORS.ink, fontFamily: FONT, overflow: 'hidden'}}>
      {beats.map((b, i) => {
        const from = f(b.start);
        const next = beats[i + 1];
        const frames = Math.max(1, (next && next.chapter === b.chapter ? f(next.start) : f(b.start + b.duration)) - from);
        return (
          <Sequence key={i} name={`beat ${i + 1} (${b.visual.type})`} from={from} durationInFrames={frames}>
            <Backdrop chapter={b.chapter} seed={i} />
            <VisualView v={b.visual} frames={frames} accent={paletteFor(b.chapter).accent} />
          </Sequence>
        );
      })}

      {chapters
        .filter((c) => c.card > 0)
        .map((c) => (
          <Sequence key={`c${c.index}`} name={`chapter card ${c.index}`} from={f(c.start)} durationInFrames={f(c.card)}>
            <Backdrop chapter={c.index} seed={100 + c.index} />
            <ChapterCard chapter={c} frames={f(c.card)} total={chapters.filter((x) => x.card > 0).length} />
          </Sequence>
        ))}

      <Subtitles groups={captions} />
      <ChapterBar chapters={chapters} total={durationInFrames} duration={duration} />
      <Grain />

      {beats.map((b, i) =>
        b.audio ? (
          <Sequence key={`a${i}`} name={`voice ${i + 1}`} from={f(b.start)}>
            <Html5Audio src={staticFile(b.audio)} />
          </Sequence>
        ) : null,
      )}
      {music ? (
        <Html5Audio
          src={staticFile(music)}
          loop
          loopVolumeCurveBehavior="extend"
          volume={(frame) => interpolate(frame, [0, 30, durationInFrames - 60, durationInFrames], [0, 0.09, 0.09, 0], clamp)}
        />
      ) : null}
      {sfx
        ? chapters
            .filter((c) => c.card > 0)
            .map((c) => (
              <Sequence key={`s${c.index}`} name={`sfx chapter ${c.index}`} from={Math.max(0, f(c.start) - 3)} durationInFrames={f(1.2)}>
                <Html5Audio src={staticFile(sfx.whoosh)} volume={0.3} />
              </Sequence>
            ))
        : null}
    </Layer>
  );
};

// Slow-moving gradient light with drifting soft shapes: never a static slide.
const Backdrop: React.FC<{chapter: number; seed: number}> = ({chapter, seed}) => {
  const frame = useCurrentFrame() + seed * 37;
  const p = paletteFor(chapter);
  const gx = 50 + 25 * Math.sin(frame / 140);
  const gy = 40 + 18 * Math.cos(frame / 170);
  return (
    <Layer
      name="backdrop"
      style={{
        background: `radial-gradient(ellipse 70% 60% at ${gx}% ${gy}%, ${p.b}, transparent 70%), linear-gradient(135deg, ${p.a}, ${COLORS.ink})`,
      }}
    >
      {[0, 1, 2, 3].map((k) => (
        <div
          key={k}
          style={{
            position: 'absolute',
            width: 520 + k * 140,
            height: 520 + k * 140,
            borderRadius: '50%',
            left: `${(k * 29 + 10 + 8 * Math.sin((frame + k * 90) / (200 + k * 40))) % 100}%`,
            top: `${(k * 41 + 5 + 10 * Math.cos((frame + k * 60) / (230 + k * 30))) % 90}%`,
            transform: 'translate(-50%, -50%)',
            background: `radial-gradient(circle, ${p.accent}14, transparent 65%)`,
          }}
        />
      ))}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          backgroundImage: 'radial-gradient(rgba(255,255,255,0.07) 1.5px, transparent 1.5px)',
          backgroundSize: '44px 44px',
          backgroundPosition: `${(frame * 0.3) % 44}px ${(frame * 0.2) % 44}px`,
          maskImage: 'radial-gradient(ellipse at center, black 30%, transparent 80%)',
        }}
      />
      <div style={{position: 'absolute', inset: 0, background: 'radial-gradient(ellipse at center, transparent 50%, rgba(0,0,0,0.55) 100%)'}} />
    </Layer>
  );
};

const ChapterCard: React.FC<{chapter: Chapter; frames: number; total: number}> = ({chapter, frames, total}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const e = spring({frame, fps, config: {damping: 13, mass: 0.7}});
  const exit = exitProgress(frame, frames, 10);
  const accent = paletteFor(chapter.index).accent;
  const line = interpolate(frame, [6, 26], [0, 1], {...clamp, easing: Easing.out(Easing.cubic)});
  return (
    <div style={{position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', opacity: 1 - exit, color: COLORS.text}}>
      <div style={{fontSize: 44, fontWeight: 800, letterSpacing: '0.3em', color: accent, opacity: e, transform: `translateY(${(1 - e) * -30}px)`}}>
        CHAPTER {chapter.index} OF {total}
      </div>
      <div style={{height: 8, width: 520 * line, background: accent, borderRadius: 4, margin: '30px 0', boxShadow: `0 0 24px ${accent}`}} />
      <div style={{fontSize: 104, fontWeight: 900, textAlign: 'center', maxWidth: 1500, lineHeight: 1.08, textWrap: 'balance', transform: `scale(${0.85 + 0.15 * e})`, opacity: e}}>
        {chapter.title}
      </div>
    </div>
  );
};

// Sentence-sized subtitles at the bottom; the word being spoken lights up.
const Subtitles: React.FC<{groups: CaptionGroup[]}> = ({groups}) => {
  const {fps} = useVideoConfig();
  return (
    <Layer name="subtitles">
      {groups.map((g, i) => {
        const from = Math.round(g.start * fps);
        const frames = Math.max(1, Math.round(g.end * fps) - from);
        return (
          <Sequence key={i} name={`subtitle ${i + 1}`} from={from} durationInFrames={frames}>
            <SubtitleLine group={g} />
          </Sequence>
        );
      })}
    </Layer>
  );
};

const SubtitleLine: React.FC<{group: CaptionGroup}> = ({group}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = group.start + frame / fps;
  const e = interpolate(frame, [0, 5], [0, 1], clamp);
  return (
    <div style={{position: 'absolute', left: 200, right: 200, bottom: 70, display: 'flex', justifyContent: 'center', opacity: e}}>
      <div
        style={{
          padding: '14px 30px',
          borderRadius: 18,
          background: 'rgba(0,0,0,0.55)',
          fontSize: 46,
          fontWeight: 800,
          lineHeight: 1.3,
          textAlign: 'center',
          textWrap: 'balance',
        }}
      >
        {group.words.map((w, i) => (
          <span key={i} style={{color: t >= w.start ? COLORS.text : 'rgba(255,255,255,0.78)'}}>
            {w.text}{' '}
          </span>
        ))}
      </div>
    </div>
  );
};

// Thin bar along the top, split into chapters, so viewers see how far along they are.
const ChapterBar: React.FC<{chapters: Chapter[]; total: number; duration: number}> = ({chapters, total, duration}) => {
  const frame = useCurrentFrame();
  const p = frame / Math.max(1, total - 1);
  return (
    <Layer name="chapter-bar">
      <div style={{position: 'absolute', top: 0, left: 0, right: 0, height: 10, background: 'rgba(255,255,255,0.12)'}} />
      <div style={{position: 'absolute', top: 0, left: 0, height: 10, width: `${p * 100}%`, background: COLORS.accent, boxShadow: '0 0 16px rgba(255,214,10,0.6)'}} />
      {chapters.slice(1).map((c) => (
        <div key={c.index} style={{position: 'absolute', top: 0, height: 10, width: 4, left: `${(c.start / duration) * 100}%`, background: COLORS.ink}} />
      ))}
    </Layer>
  );
};

const GRAIN = `url("data:image/svg+xml;utf8,${encodeURIComponent(
  `<svg xmlns="http://www.w3.org/2000/svg" width="180" height="180"><filter id="n"><feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="3" stitchTiles="stitch"/><feColorMatrix type="saturate" values="0"/></filter><rect width="180" height="180" filter="url(#n)"/></svg>`,
)}")`;

const Grain: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <Layer
      name="film-grain"
      style={{
        backgroundImage: GRAIN,
        backgroundPosition: `${(frame * 37) % 180}px ${(frame * 71) % 180}px`,
        mixBlendMode: 'overlay',
        opacity: 0.1,
      }}
    />
  );
};

