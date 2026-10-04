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
export type Prop = 'none' | 'phone' | 'book' | 'paper' | 'cup' | 'bag' | 'laptop' | 'ball' | 'plate' | 'remote' | 'thing';
export type Effect = 'none' | 'erupt' | 'smoke' | 'fire' | 'sparkle' | 'shake';
// An object in the scene: 'volcano' (drawn by hand) or a lucide icon name; on a small table or the floor.
export type Thing = {name: string; x: number; table: boolean; big: boolean; effect: Effect};
export type Setting =
  | 'living-room' | 'classroom' | 'kitchen' | 'bedroom' | 'street' | 'office' | 'bathroom'
  | 'park' | 'shop' | 'exam-hall' | 'blank';
export type Camera = 'wide' | 'close' | 'punch' | 'shake';
export type Action = 'none' | 'jump' | 'shake' | 'fall' | 'spin' | 'walk-in-left' | 'walk-in-right' | 'walk-out-left' | 'walk-out-right';

// A piece of furniture in the scene (kinds in sets.json): centre x and width on the 1920 px set.
export type Piece = {kind: string; x: number; width: number};

export type CastMember = {id: string; name: string; look: Look; outfit?: string}; // outfit: shirt or dress colour

export type ActorState = {
  id: string;
  x: number; // centre of the figure, 0-1920
  pose: Pose;
  face: Face;
  facing: 1 | -1; // 1 = looks right
  emote: Emote;
  prop: Prop;
  propText?: string; // text on a paper / phone screen ("F", "₹93")
  propThing?: string; // with prop 'thing': what they hold ('volcano' or a lucide icon name)
  action: Action;
};

export type Word = {text: string; start: number; end: number}; // seconds from the shot's start

export type Shot = {
  start: number;
  duration: number;
  scene: number; // a new scene number = a new place (a cut with a whoosh)
  setting: Setting;
  sign?: string; // a word on the set (a door sign, a board, a shop name)
  furniture?: Piece[]; // the scene's furniture; missing = the setting's usual pieces (sets.json)
  things?: Thing[]; // objects standing in the scene (not held)
  washing?: boolean; // kitchen: running water and soap foam in the sink (only when someone washes dishes)
  caption?: string; // meme caption at the top ("POV: ...")
  camera: Camera;
  focus?: string; // actor id the camera frames on 'close'
  actors: ActorState[];
  speaker?: string; // actor id speaking (or 'narrator')
  emotion?: string; // how the line is said (the voice follows it; the speaker's body acts it)
  text?: string; // the line, shown in a speech bubble
  words: Word[];
  audio?: string | null; // the line's voice file
  lead: number; // seconds of silence before the line starts (comic timing)
};


export type StoryProps = {
  // The sound pass of a long render (reelgen/video.py): no picture, so a frame costs almost nothing.
  soundOnly?: boolean;
  silent?: boolean;
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
