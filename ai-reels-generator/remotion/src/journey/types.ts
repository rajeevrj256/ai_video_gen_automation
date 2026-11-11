// 🌱 Journey (reelgen/journey/): a photoreal time-lapse in the middle of a 9:16 frame, a blurred copy of it behind,
// one line of text above and one below (the user's reference: 'The fall was just the beginning' / 'Rock bottom is
// fertile ground'). The picture and its blurred copy are made by reelgen/journey/motion.py; the sound is mixed apart.
export type JourneyLabel = {at: number; until: number; text: string}; // seconds; e.g. 'WEEK 6' (off by default)

// Light and weather drawn by the editor, per stage (pictures from this computer's engine can't repaint a sky: a test's
// storm stage came out as the sunny base), cross-faded at the joins like a time-lapse's light.
export type JourneyLight = 'dawn' | 'morning' | 'midday' | 'golden' | 'overcast' | 'storm' | 'rain' | 'dusk' | 'night';
export type JourneyGrade = {at: number; until: number; light: JourneyLight; flash?: number}; // flash: seconds, a lightning strike

export type JourneyProps = {
  fps: number;
  duration: number; // seconds
  story: string; // story.mp4: the 16:9 time-lapse
  bg: string; // story-bg.mp4: the same, blurred, 9:16
  top: string; // the line above the picture ('' = none)
  bottom: string; // the line below
  labels?: JourneyLabel[];
  grade?: JourneyGrade[];
  silent?: boolean;
};
