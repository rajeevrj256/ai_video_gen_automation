import React from 'react';
import {Html5Audio, Sequence, staticFile, useVideoConfig} from 'remotion';
import type {ReelProps} from './types';
import {COLORS, useFonts} from './theme';
import {Cues, Music} from './Sound';
import {Layer} from './Layer';
import {Background} from './Background';
import {GraphicView} from './Graphics';
import {HookTitle} from './HookTitle';
import {Captions} from './Captions';

// The whole video: footage, one graphic per scene (when the script has one),
// the hook title, word-by-word captions, narration, music that dips under the voice,
// transition sounds and the sound effects placed on words. Every time comes from the props in seconds.

const TITLE_SECONDS = 2.6;

// Sound for each scene transition: which effect, how many frames early, how loud.
const TRANSITION_SOUND: Record<string, {name: 'whoosh' | 'impact' | 'swish' | 'glitch' | 'shimmer'; lead: number; volume: number}> = {
  flash: {name: 'whoosh', lead: 3, volume: 0.28},
  zoom: {name: 'impact', lead: 0, volume: 0.4},
  slide: {name: 'swish', lead: 2, volume: 0.3},
  glitch: {name: 'glitch', lead: 0, volume: 0.22},
  fade: {name: 'shimmer', lead: 2, volume: 0.2},
};
const MIN_GRAPHIC_SECONDS = 1.4; // shorter than this and it can't finish animating
const GRAPHIC_DELAY = 4; // frames after the cut, so the flash lands first

export const Reel: React.FC<ReelProps> = ({title, scenes, cuts, captions, music, sfx, cues = [], speech = []}) => {
  useFonts();
  const {fps} = useVideoConfig();
  const f = (s: number) => Math.round(s * fps);
  const titleFrames = f(Math.min(TITLE_SECONDS, scenes[0]?.duration ?? TITLE_SECONDS));
  // A word's own sound effect replaces the stock transition sound near it: never two at once.
  const cueNear = (t: number) => cues.some((c) => Math.abs(c.at - t) < 0.45);

  // A graphic fills its scene; in the first scene it waits for the hook title to leave.
  const graphics = scenes.flatMap((s, i) => {
    if (!s.graphic || s.graphic.type === 'none') return [];
    const from = Math.max(f(s.start) + GRAPHIC_DELAY, i === 0 ? titleFrames : 0);
    const frames = f(s.start + s.duration) - from;
    return frames >= f(MIN_GRAPHIC_SECONDS) ? [{from, frames, graphic: s.graphic, scene: i}] : [];
  });

  return (
    <Layer name="reel" style={{backgroundColor: COLORS.ink}}>
      <Background cuts={cuts} transitions={scenes.map((s) => ({start: s.start, type: s.transition ?? 'flash'}))} />

      {graphics.map(({from, frames, graphic, scene}) => (
        <Sequence key={scene} name={`graphic scene ${scene + 1}`} from={from} durationInFrames={frames}>
          <GraphicView g={graphic} frames={frames} />
        </Sequence>
      ))}

      {title ? (
        <Sequence name="hook title" durationInFrames={titleFrames}>
          <HookTitle text={title} frames={titleFrames} />
        </Sequence>
      ) : null}

      <Captions groups={captions} />

      {scenes.map((s, i) =>
        s.audio ? (
          // No durationInFrames: the voice always plays to its natural end.
          <Sequence key={i} name={`voice ${i + 1}`} from={f(s.start)}>
            <Html5Audio src={staticFile(s.audio)} />
          </Sequence>
        ) : null,
      )}

      {music ? <Music src={music} speech={speech} full={0.2} duck={0.07} /> : null}
      <Cues cues={cues} speech={speech} />

      {sfx ? (
        <>
          {cueNear(0) ? null : (
            <Sequence name="sfx whoosh (title)" durationInFrames={f(1)}>
              <Html5Audio src={staticFile(sfx.whoosh)} volume={0.22} />
            </Sequence>
          )}
          {scenes.slice(1).map((s, i) => {
            if (cueNear(s.start)) return null;
            // Each transition has its own sound. Swells start a few frames early so they
            // peak on the cut; hits start exactly on it.
            const cue = TRANSITION_SOUND[s.transition ?? 'flash'] ?? TRANSITION_SOUND.flash;
            return (
              <Sequence
                key={`t${i}`}
                name={`sfx ${cue.name} ${i + 2}`}
                from={Math.max(0, f(s.start) - cue.lead)}
                durationInFrames={f(1)}
              >
                <Html5Audio src={staticFile(sfx[cue.name])} volume={cue.volume} />
              </Sequence>
            );
          })}
          {graphics.map(({from, scene}) => (
            <Sequence key={`p${scene}`} name={`sfx pop ${scene + 1}`} from={from + 3} durationInFrames={f(0.5)}>
              <Html5Audio src={staticFile(sfx.pop)} volume={0.35} />
            </Sequence>
          ))}
        </>
      ) : null}
    </Layer>
  );
};
