// Props the Python pipeline passes to the "Long" composition (reelgen/longform.py).
// A 16:9 video of 8-10 minutes made only of motion graphics: no stock footage, so
// nothing on screen can show the wrong place or thing. Times are in seconds from
// the start of the video; file paths are relative to the render's public dir.

import type {CaptionGroup, Cue, Span} from '../types';

export type Item = {label: string; text: string; value: number; display: string};

export type VisualType =
  | 'title' // big kinetic headline + subline
  | 'stat' // one number that counts up + what it is
  | 'timeline' // 2-5 dated moments, drawn left to right
  | 'compare' // exactly 2 items side by side with bars
  | 'steps' // 2-4 steps of how something works, one after another
  | 'icons' // 1-3 icons that illustrate the line + a caption
  | 'quote' // a real quote and who said it
  | 'keyword' // one word or short phrase slammed on screen
  | 'chart' // 3-6 points over time
  | 'footage' // a real stock clip of a place or scene, full screen (src = clip)
  | 'model3d' // a 3D model animated in its own world (src = .glb)
  | 'scene'; // 1-4 icon actors acting the line out

export type Visual = {
  type: VisualType;
  headline: string;
  sub: string;
  items: Item[];
  icons: string[]; // lucide names in kebab-case, e.g. "cloud-rain"
  src?: string; // footage clip or .glb, relative to the public dir
  length?: number; // footage: the clip's length in seconds
  scene?: 'sky' | 'space' | 'studio'; // model3d: the world it's shown in
  parts?: Part[]; // model3d without a file: build it from these shapes
  actors?: Actor[]; // scene: who acts, in order
  camera?: Camera; // how the camera moves during the beat
  impact?: boolean; // the chapter's biggest moment: punch-in, freeze + flash, shake
  impactAt?: number; // seconds into the beat
};

export type Camera = 'push' | 'pull' | 'pan-left' | 'pan-right' | 'rise' | 'dutch' | 'orbit' | 'still';

export type ActorAction =
  | 'enter-left' | 'enter-right' | 'drop-in' | 'rise' | 'walk-across' | 'approach' | 'flee'
  | 'shake' | 'pulse' | 'spin' | 'fall' | 'grow' | 'shrink' | 'orbit' | 'multiply';

export type Actor = {icon: string; action: ActorAction; label: string; at: number}; // at: seconds into the beat

// This video's own look (reelgen/variety.py): colours, backdrop and transition style.
export type Look = {
  palette: string;
  worlds: [string, string][];
  accents: string[];
  backdrop: 'blobs' | 'grid' | 'rays' | 'waves' | 'dots' | 'paper';
  transition: 'smooth' | 'whip' | 'zoom' | 'glitch' | 'flash' | 'slide';
  seed: number;
  plates?: Record<string, string>; // chapter index -> background photo of that chapter's own setting
  hookPlate?: string | null; // the hook's background photo
  platesBaked?: Record<string, string>; // the same photos already blurred, darkened and graded once (chapter index or 'hook')
};

export type HookShot = {
  start: number;
  duration: number;
  beat: 'curiosity' | 'unexpected' | 'tension' | 'problem' | 'gap';
  text: string;
  audio: string | null;
  visual: Visual;
};

export type Hook = {duration: number; shots: HookShot[]; music: string | null; style: string};

// One simple shape of a 3D object Claude designed (reelgen/models3d.py Part). Metres, +Y up, front +Z.
export type Part = {
  shape: 'box' | 'sphere' | 'cylinder' | 'cone' | 'torus' | 'capsule';
  size: number[];
  position: number[];
  rotation?: number[]; // degrees
  color: string;
  material?: 'matte' | 'glossy' | 'metal' | 'glass' | 'glow';
};

export type Beat = {start: number; duration: number; chapter: number; audio: string | null; visual: Visual};

export type Chapter = {index: number; title: string; start: number; card: number; end?: number; intensity?: number; drop?: boolean;
  style?: 'blackout' | 'lowerthird' | 'trailer' | 'split' | 'cut'; text?: string}; // card: seconds of the break into it (long/Breaks.tsx)

export type LongProps = {
  title: string;
  fps: number;
  duration: number;
  chapters: Chapter[];
  beats: Beat[];
  captions: CaptionGroup[];
  music: string | null;
  sfx: {whoosh: string; impact: string; swish: string; glitch: string; shimmer: string; pop: string} | null;
  cues?: Cue[];
  speech?: Span[];
  look?: Look;
  hook?: Hook;
  musicFrom?: number; // the main track starts after the hook
  ambience?: {src: string; from: number; to: number}[];
  musicParts?: {src: string; from: number; to: number; name: string}[]; // the user's tracks on the chapters they fit
  currency?: string; // rupee | euro | pound: money icons show this symbol
};
