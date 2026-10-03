import React from 'react';
import {Html5Audio, Sequence, interpolate, staticFile, useVideoConfig} from 'remotion';
import {clamp} from './theme';
import type {Cue, Span} from './types';

// Background music that dips while the narrator talks and comes back up in the pauses,
// plus the sound effects placed on words of the narration. Shared by Reel and Long.

const DUCK_RAMP = 0.35; // seconds to dip or recover

// `mute`: spans (seconds) where this track steps aside, e.g. the composed score under a chapter that
// plays the user's own track; it fades out and back in over MUTE_RAMP.
const MUTE_RAMP = 1.2;
export const Music: React.FC<{src: string; speech: Span[]; full: number; duck: number; loop?: boolean; mute?: Span[]}> = ({src, speech, full, duck, loop = true, mute = []}) => {
  const {fps, durationInFrames} = useVideoConfig();
  const level = (frame: number) => {
    const t = frame / fps;
    let distance = Infinity; // seconds to the nearest speech
    for (const [a, b] of speech) {
      if (t >= a && t <= b) {
        distance = 0;
        break;
      }
      distance = Math.min(distance, t < a ? a - t : t - b);
      if (a > t + DUCK_RAMP) break; // spans are sorted
    }
    const k = speech.length ? interpolate(distance, [0.05, DUCK_RAMP], [0, 1], clamp) : 1;
    const fade = interpolate(frame, [0, 15, durationInFrames - 45, durationInFrames], [0, 1, 1, 0], clamp);
    let away = 1;
    for (const [a, b] of mute) {
      away = Math.min(away, interpolate(t, [a - MUTE_RAMP, a, b, b + MUTE_RAMP], [1, 0, 0, 1], clamp));
    }
    return (duck + (full - duck) * k) * fade * away;
  };
  return <Html5Audio src={staticFile(src)} loop={loop} loopVolumeCurveBehavior="extend" volume={level} />;
};

export const Cues: React.FC<{cues: Cue[]}> = ({cues}) => {
  const {fps} = useVideoConfig();
  return (
    <>
      {cues.map((c, i) => (
        // No durationInFrames: every effect plays out its own tail.
        <Sequence key={i} name={`sound ${c.name}`} from={Math.round(c.at * fps)}>
          <Html5Audio src={staticFile(c.src)} volume={c.volume} trimBefore={Math.round((c.trim ?? 0) * fps) || undefined} />
        </Sequence>
      ))}
    </>
  );
};
