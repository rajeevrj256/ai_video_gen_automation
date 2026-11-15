// 🌱 Journey (reelgen/journey/): a photoreal time-lapse in the middle of a 9:16 frame, a blurred copy of it behind,
// one line of text above and one below (the user's reference: 'The fall was just the beginning' / 'Rock bottom is
// fertile ground'). The picture and its blurred copy are made by reelgen/journey/motion.py; the sound is mixed apart.
export type JourneyLabel = {at: number; until: number; text: string}; // seconds; e.g. 'WEEK 6' (off by default)

// A lightning flash where a stage's thunder falls (seconds). The light and the weather are in the pictures: the
// rain lines and colour washes this editor drew at first looked fake.
export type JourneyGrade = {at: number; until: number; flash: number};

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
