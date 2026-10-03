import type {Cue} from '../types';

// Props for the "StickStory" composition: a 16:9 stick-figure comedy episode (3-8 minutes) with a
// recurring cast, drawn entirely in SVG in the channel's style (grey sets, white round heads, ink
// lines, speech bubbles). Made by reelgen/stickstory.py: one shot per line of dialogue.

export type Look = 'boy' | 'girl' | 'man' | 'woman' | 'kid' | 'old-man' | 'old-woman';
export type Pose =
  | 'stand' | 'walk' | 'run' | 'sit' | 'point' | 'arms-up' | 'facepalm' | 'shrug'
  | 'hands-on-hips' | 'think' | 'cry' | 'lie' | 'wave' | 'hold';
export type Face =
  | 'neutral' | 'happy' | 'laugh' | 'shock' | 'angry' | 'sad' | 'smirk' | 'cry'
  | 'nervous' | 'confused' | 'sleepy' | 'love' | 'dead';
export type Emote = 'none' | '!' | '?' | '!?' | 'sweat' | 'anger' | 'hearts' | 'zzz' | 'sparkle' | 'lines';
export type Prop = 'none' | 'phone' | 'book' | 'paper' | 'cup' | 'bag' | 'laptop' | 'ball' | 'plate' | 'remote';
export type Setting =
  | 'living-room' | 'classroom' | 'kitchen' | 'bedroom' | 'street' | 'office' | 'bathroom'
  | 'park' | 'shop' | 'exam-hall' | 'blank';
export type Camera = 'wide' | 'close' | 'punch' | 'shake';
export type Action = 'none' | 'jump' | 'shake' | 'fall' | 'spin' | 'walk-in-left' | 'walk-in-right' | 'walk-out-left' | 'walk-out-right';

export type CastMember = {id: string; name: string; look: Look};

export type ActorState = {
  id: string;
  x: number; // centre of the figure, 0-1920
  pose: Pose;
  face: Face;
  facing: 1 | -1; // 1 = looks right
  emote: Emote;
  prop: Prop;
  propText?: string; // text on a paper / phone screen ("F", "₹93")
  action: Action;
};

export type Word = {text: string; start: number; end: number}; // seconds from the shot's start

export type Shot = {
  start: number;
  duration: number;
  scene: number; // a new scene number = a new place (a cut with a whoosh)
  setting: Setting;
  sign?: string; // a word on the set (a door sign, a board, a shop name)
  caption?: string; // meme caption at the top ("POV: ...")
  camera: Camera;
  focus?: string; // actor id the camera frames on 'close'
  actors: ActorState[];
  speaker?: string; // actor id speaking (or 'narrator')
  text?: string; // the line, shown in a speech bubble
  words: Word[];
  audio?: string | null; // the line's voice file
  lead: number; // seconds of silence before the line starts (comic timing)
};


export type StoryProps = {
  fps: number;
  duration: number;
  title: string;
  cast: CastMember[];
  shots: Shot[];
  music: string | null;
  cues: Cue[]; // same shape as the other compositions' cues
  speech: [number, number][];
  sfx: Record<string, string> | null;
  dialogue?: 'subtitle' | 'bubble'; // how lines show: small subtitles under the scene (the channel's style) or speech bubbles
  vertical?: boolean; // a 9:16 Short: the same sets, framed on whoever is speaking
};
