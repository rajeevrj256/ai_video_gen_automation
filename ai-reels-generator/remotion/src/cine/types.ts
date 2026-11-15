// The cinematic hook's vocabulary, shared by the Long hook (long/Cinematic.tsx) and the Anim cold open
// (anim/Anim.tsx). Modelled on a documentary-trailer cold open the user wanted every video to open like:
// each beat in its own colour grade, film texture over everything, typed labels, hard whips and glitches,
// a photo flown in, paper torn across the frame, then a breath of silence before the story starts.

export type Grade = 'amber' | 'red' | 'noir' | 'fire' | 'cold' | 'natural';

export type CineTransition = 'whip' | 'glitch' | 'photo' | 'split' | 'dip' | 'punch' | 'cut';

// Frames each transition takes. Photo and split show the shot before underneath while they play, so that shot
// keeps running this long past its cut (the shot after is drawn on top).
export const TRANSITION_FRAMES: Record<CineTransition, number> = {
  whip: 8,
  glitch: 7,
  photo: 24,
  split: 13,
  dip: 9,
  punch: 5,
  cut: 0,
};

export const OVERLAPS: ReadonlySet<CineTransition> = new Set(['photo', 'split']);

// Seconds per typed letter: keep in step with reelgen/sfx.py TYPE_EVERY (the typewriter sound is made per label).
export const TYPE_EVERY = 0.045;
// Seconds into a shot when its label starts typing: keep in step with reelgen/longform.py LABEL_AT.
export const LABEL_AT = 0.3;
