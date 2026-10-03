import React from 'react';
import {Easing, Html5Audio, Sequence, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {COLORS, FONT, clamp, exitProgress, useFonts} from '../theme';
import {Layer} from '../Layer';
import type {CaptionGroup} from '../types';
import {VisualView} from './Visuals';
import {Cues, Music} from '../Sound';
import {Footage, Model3D} from './Media';
import {SceneView} from './Scene';
import {setCurrency} from './icon';
import {Backdrop, HookView, Shot, lookOf, worldFor} from './Cinematic';
import type {Chapter, Look, LongProps, Visual} from './types';

// The whole long video: a cinematic trailer hook, then one motion visual per beat with its
// own camera move, this video's backdrop and transition style, a title card before each
// chapter, subtitles, the narration, the hook's trailer music, the main track (composed for
// the story, dipping under the voice), ambience beds and sound on every visual action.

// Older props (made before looks) keep the old colours.
export const paletteFor = (chapter: number, look?: Look) => worldFor(lookOf(look), chapter);

// One visual, whatever its kind.
const Body: React.FC<{v: Visual; frames: number; accent: string; roomy: boolean; look: Look; chapter: number; seed: number}> = ({v, frames, accent, roomy, look, chapter, seed}) => {
  if (v.type === 'footage' && v.src) return <Footage v={v} frames={frames} accent={accent} />;
  if (v.type === 'model3d' && (v.src || v.parts?.length)) return <Model3D v={v} frames={frames} accent={accent} />;
  return (
    <>
      <Backdrop look={look} chapter={chapter} seed={seed} />
      {v.type === 'scene' && v.actors?.length ? (
        <SceneView v={v} frames={frames} accent={accent} />
      ) : (
        <VisualView v={v} frames={frames} accent={accent} roomy={roomy} />
      )}
    </>
  );
};

export const Long: React.FC<LongProps> = ({chapters, beats, captions, music, sfx, cues = [], speech = [], look: rawLook, hook, musicFrom = 0, ambience = [], musicParts = [], currency}) => {
  useFonts();
  setCurrency(currency);
  const {fps} = useVideoConfig();
  const f = (s: number) => Math.round(s * fps);
  const look = lookOf(rawLook);
  const roomy = captions.length === 0;
  return (
    <Layer name="long" style={{backgroundColor: COLORS.ink, fontFamily: FONT, overflow: 'hidden'}}>
      {hook && hook.shots.length ? (
        <Sequence name="hook (trailer)" durationInFrames={f(hook.duration)}>
          <HookView
            hook={hook}
            look={look}
            render={(s, frames) => (
              <Body v={s.visual} frames={frames} accent={look.accents[0]} roomy={roomy} look={{...look, backdrop: 'rays'}} chapter={0} seed={7} />
            )}
          />
        </Sequence>
      ) : null}

      {beats.map((b, i) => {
        const from = f(b.start);
        const next = beats[i + 1];
        const frames = Math.max(1, (next && next.chapter === b.chapter ? f(next.start) : f(b.start + b.duration)) - from);
        const accent = paletteFor(b.chapter, look).accent;
        return (
          <Sequence key={i} name={`beat ${i + 1} (${b.visual.type}, ${b.visual.camera ?? 'push'})`} from={from} durationInFrames={frames}>
            <Shot v={b.visual} frames={frames} transition={look.transition}>
              <Body v={b.visual} frames={frames} accent={accent} roomy={roomy} look={look} chapter={b.chapter} seed={i} />
            </Shot>
          </Sequence>
        );
      })}

      {chapters
        .filter((c) => c.card > 0)
        .map((c) => (
          <Sequence key={`c${c.index}`} name={`chapter card ${c.index}`} from={f(c.start)} durationInFrames={f(c.card)}>
            <Backdrop look={look} chapter={c.index} seed={100 + c.index} />
            <ChapterCard chapter={c} frames={f(c.card)} total={chapters.filter((x) => x.card > 0).length} accent={paletteFor(c.index, look).accent} />
          </Sequence>
        ))}

      <Subtitles groups={captions} />
      <Grain />

      {/* voice: the hook's lines, then every beat */}
      {(hook?.shots ?? []).map((s, i) =>
        s.audio ? (
          <Sequence key={`h${i}`} name={`hook voice ${i + 1}`} from={f(s.start)}>
            <Html5Audio src={staticFile(s.audio)} />
          </Sequence>
        ) : null,
      )}
      {beats.map((b, i) =>
        b.audio ? (
          <Sequence key={`a${i}`} name={`voice ${i + 1}`} from={f(b.start)}>
            <Html5Audio src={staticFile(b.audio)} />
          </Sequence>
        ) : null,
      )}
      {/* music: the hook's trailer track, then the main track from where the hook ends */}
      {hook?.music ? (
        <Sequence name="hook music" durationInFrames={f(hook.duration + 1.8)}>
          <Music src={hook.music} speech={speech.filter(([a]) => a < hook.duration)} full={0.62} duck={0.3} loop={false} />
        </Sequence>
      ) : null}
      {music ? (
        <Sequence name="music" from={f(musicFrom)}>
          <Music src={music} speech={speech.map(([a, b]) => [a - musicFrom, b - musicFrom] as [number, number])} full={0.18} duck={0.065}
            mute={musicParts.map((m) => [m.from - musicFrom, m.to - musicFrom] as [number, number])} />
        </Sequence>
      ) : null}
      {/* the user's own tracks on the chapters they fit (the composed score steps aside there) */}
      {musicParts.map((m, i) => (
        <Sequence key={`own${i}`} name={`music: ${m.name}`} from={f(m.from)} durationInFrames={Math.max(1, f(m.to - m.from))}>
          <Music src={m.src} speech={speech.map(([a, b]) => [a - m.from, b - m.from] as [number, number])} full={0.16} duck={0.06} />
        </Sequence>
      ))}
      {ambience.map((a, i) => (
        <Sequence key={`amb${i}`} name={`ambience ${i + 1}`} from={f(a.from)} durationInFrames={Math.max(1, f(a.to - a.from))}>
          <Ambience src={a.src} frames={Math.max(1, f(a.to - a.from))} />
        </Sequence>
      ))}
      <Cues cues={cues} />
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

// A quiet bed under a chapter, faded in and out.
const Ambience: React.FC<{src: string; frames: number}> = ({src, frames}) => (
  <Html5Audio
    src={staticFile(src)}
    loop
    volume={(fr) => interpolate(fr, [0, 30, frames - 30, frames], [0, 0.1, 0.1, 0], clamp)}
  />
);

const ChapterCard: React.FC<{chapter: Chapter; frames: number; total: number; accent: string}> = ({chapter, frames, total, accent}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const e = spring({frame, fps, config: {damping: 13, mass: 0.7}});
  const exit = exitProgress(frame, frames, 10);
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

