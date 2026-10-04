import type {Cue, Span} from '../types';

// Toon Explainers (reelgen/toon.py): flat, colourful animated explainers. Every sentence is one shot in
// which something happens (an action on objects and the video's mascot), never a slide of text.

export type MascotShape = 'bubble' | 'blob' | 'bot' | 'cube' | 'coin' | 'drop' | 'ghost' | 'sun' | 'flame' | 'planet' | 'virus'
  | 'chip' | 'battery' | 'shield' | 'heart' | 'cloud' | 'star';
export type Accessory = 'none' | 'headset' | 'antenna' | 'cap' | 'glasses' | 'crown' | 'bowtie';
export type Mood = 'neutral' | 'happy' | 'wink' | 'smug' | 'angry' | 'sad' | 'scared' | 'shocked' | 'sleepy' | 'evil' | 'cool';
export type Tint = 'normal' | 'red' | 'grey' | 'gold' | 'green';
export type Pos = 'left' | 'center' | 'right';
export type Backdrop = 'grid' | 'flat' | 'dots' | 'sky' | 'city' | 'space' | 'lab' | 'stage' | 'desk';
export type Action =
  | 'none' | 'pop' | 'crack' | 'clone' | 'flood' | 'unlock' | 'lock' | 'toggle-off' | 'toggle-on' | 'gauge-up'
  | 'gauge-down' | 'strings' | 'strings-burn' | 'burst' | 'fly-out' | 'crosshair' | 'sparks' | 'cage' | 'connect'
  | 'orbit' | 'rain' | 'arrow-up' | 'arrow-down' | 'versus' | 'bars' | 'shake';
export type Camera = 'push' | 'pull' | 'pan' | 'still';
export type Enter = 'cut' | 'whip' | 'zoom' | 'flash';

export type Hair = 'short' | 'side' | 'curly' | 'bun' | 'long' | 'bald' | 'spiky' | 'cap';
export type Pose = 'stand' | 'point' | 'shrug' | 'hands-up' | 'hands-head' | 'think' | 'wave' | 'run' | 'sit' | 'present';
export type Look = {
  skin: string; hair: Hair; hairColor: string; beard: 'none' | 'stubble' | 'full' | 'mustache';
  glasses: boolean; shirt: string; tie: string | null; pants: string; coat: string | null;
};

export type PersonSpec = {
  look: Look; pose: Pose; mood: Mood; pos: 'far-left' | 'left' | 'center' | 'right' | 'far-right';
  talking: boolean; seated: boolean; flip: boolean;
};

export type Item = {icon: string; label?: string | null; badge?: boolean};
export type Word = {text: string; start: number; end: number}; // seconds from the start of the shot's voice

export type ToonShot = {
  start: number; // seconds
  duration: number;
  lead: number; // silence before the line
  audio?: string | null;
  text: string;
  words: Word[];
  segment: number;
  backdrop: Backdrop;
  tone: number; // which of the palette's tones colours this shot
  mascot?: {mood: Mood; tint: Tint; pos: Pos; size: 's' | 'm' | 'l'} | null;
  people?: PersonSpec[]; // cartoon people acting the line out (a podium, a desk, a street...)
  crowd?: boolean; // small running people across the scene
  items: Item[];
  action: Action;
  at: number; // seconds into the shot when the action fires (on its word)
  slam?: string | null; // 1-3 words, big
  card?: {kind: 'number' | 'date' | 'title'; text: string; sub?: string | null} | null;
  values?: number[]; // bars: heights (any scale)
  camera: Camera;
  enter: Enter;
};

export type ToonPalette = {
  tones: string[]; // flat backgrounds, one per segment in turn
  ink: string; // dark backgrounds (grid, space) and outlines
  glow: string; // grid lines, sparks
  accent: string; // slams, badges
  hot: string; // danger: crosshair, fire, red mascot
  paper: string; // cards, item tiles
};

export type ToonProps = {
  fps: number;
  duration: number;
  title: string;
  palette: ToonPalette;
  mascot: {shape: MascotShape; color: string; accessory: Accessory; name: string};
  style: {slam: 'pill' | 'stroke' | 'stamp'; card: 'badge' | 'ticket' | 'circle'; seed: number};
  shots: ToonShot[];
  captions: boolean;
  watermark?: string | null;
  music?: string | null;
  musicFrom?: number; // the main track starts after the title card
  hookMusic?: string | null; // the cold open's trailer track
  hookEnd?: number;
  speech: Span[];
  cues: Cue[];
  silent?: boolean;
  soundOnly?: boolean;
};
