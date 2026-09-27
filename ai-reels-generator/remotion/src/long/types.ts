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
  | 'model3d'; // a 3D model animated in its own world (src = .glb)

export type Visual = {
  type: VisualType;
  headline: string;
  sub: string;
  items: Item[];
  icons: string[]; // lucide names in kebab-case, e.g. "cloud-rain"
  src?: string; // footage clip or .glb, relative to the public dir
  length?: number; // footage: the clip's length in seconds
  scene?: 'sky' | 'space' | 'studio'; // model3d: the world it's shown in
};

export type Beat = {start: number; duration: number; chapter: number; audio: string | null; visual: Visual};

export type Chapter = {index: number; title: string; start: number; card: number}; // card: seconds of title card

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
};
