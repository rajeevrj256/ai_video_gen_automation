// Props for the "Stick" composition: a 9:16 meme-style comedy video with one original
// stick-figure character, drawn in SVG (no images), black and white. Each scene picks a
// pose, a face, what the phone shows, a caption and a few animated extras.

export type Pose = 'sit' | 'lean' | 'upright' | 'slump' | 'lying';
export type Face = 'hungry' | 'happy' | 'mischief' | 'shock' | 'terrified' | 'dead';
export type Screen = 'none' | 'menu' | 'placed' | 'add' | 'total' | 'bank' | 'balance';
export type Extra =
  | 'thought-food' // thought bubble with food
  | 'drool'
  | 'tap' // finger taps the phone
  | 'plus-ones' // "+1" pops rise from the phone
  | 'shake'
  | 'zoom' // camera pushes in on the phone
  | 'alarm' // "!!" beside the head
  | 'sweat'
  | 'wallet' // an empty wallet (opens, a moth flies out)
  | 'soul'; // a faint soul drifts up out of the body

export type StickScene = {
  seconds: number;
  pose: Pose;
  face: Face;
  screen: Screen;
  amount: string; // the number the phone shows for 'total' / 'balance', e.g. "₹847"
  caption: string;
  extras: Extra[];
};

export type StickProps = {
  fps: number;
  scenes: StickScene[];
  outro: string; // final black screen text
  outroSeconds: number;
  sfx: {whoosh: string; impact: string; pop: string; sad: string} | null;
};
