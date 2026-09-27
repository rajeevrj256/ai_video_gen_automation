// Props the Python pipeline passes to the "Reel" composition (reelgen/video.py).
// All times are in seconds from the start of the video; file paths are relative
// to the render's public dir (the video's working folder).

export type Word = {text: string; start: number; end: number};

export type CaptionGroup = {start: number; end: number; words: Word[]};

export type Cut = {
  src: string; // "" = animated gradient placeholder (no footage available)
  start: number;
  duration: number;
  offset: number; // where to start inside the source clip
  length: number | null; // source clip length, null for still images
  punchIn: boolean;
  image: boolean;
};

export type Point = {label: string; value: number; display: string};

export type Graphic = {
  type: 'none' | 'stat' | 'chart' | 'compare' | 'keyword';
  headline: string;
  label: string;
  points: Point[];
};

// How a scene cuts in from the previous one; the first scene is always 'none'.
export type Transition = 'none' | 'flash' | 'zoom' | 'slide' | 'glitch' | 'fade';

export type Scene = {start: number; duration: number; audio: string | null; graphic: Graphic; transition: Transition};

// A sound effect placed on a word of the narration (reelgen/media.py resolve_cues).
export type Cue = {src: string; at: number; trim?: number; volume: number; name: string}; // trim: seconds cut off the front

// Where the voice is talking, [start, end] in seconds: the music dips under it.
export type Span = [number, number];

export type ReelProps = {
  title: string;
  fps: number;
  duration: number;
  scenes: Scene[];
  cuts: Cut[];
  captions: CaptionGroup[];
  music: string | null;
  // Short sound effects synced to scene changes and graphic entrances; null = silent.
  sfx: {whoosh: string; impact: string; swish: string; glitch: string; shimmer: string; pop: string} | null;
  cues?: Cue[];
  speech?: Span[];
};
