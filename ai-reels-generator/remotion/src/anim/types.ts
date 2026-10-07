import type {Cue, Span} from '../types';

// Animated videos (reelgen/animated.py): every shot is an AI picture (anim_worker keyframes) and, when it was
// animated, an AI clip (LTX-Video) that starts from that picture. Shots without a clip are moved by the camera.

export type AnimCamera = 'push-in' | 'pull-out' | 'pan-left' | 'pan-right' | 'tilt-up' | 'tilt-down' | 'orbit' | 'handheld' | 'static';
export type AnimTransition = 'cut' | 'crossfade' | 'whip' | 'flash' | 'zoom' | 'dip';
export type Word = {text: string; start: number; end: number};

export type AnimShot = {
  id: string;
  type: 'shot' | 'title' | 'chapter';
  start: number; // seconds
  duration: number;
  lead?: number; // silence before the line
  audio?: string | null;
  text?: string;
  words?: Word[];
  chapter: number; // -1 = cold open
  image: string; // the AI picture (keyframes/...)
  clip?: string | null; // the AI clip made from it (clips/...)
  clipSeconds?: number;
  last?: string | null; // the clip's last frame, held when the line outlasts the clip
  camera?: AnimCamera;
  transition: AnimTransition;
  importance?: 'low' | 'medium' | 'high' | 'critical';
  emphasis?: {text: string; at: number; end: number} | null; // seconds into the shot
  emphasisFx?: ('text' | 'zoom' | 'shake' | 'flash' | 'pause')[];
  onScreen?: string | null;
  cardText?: string; // title and chapter cards
  chapterNo?: number;
  chapters?: number;
};

export type AnimProps = {
  fps: number;
  duration: number;
  title: string;
  style: string; // the art style (reelgen.animated.ART_STYLES)
  accent: string;
  shots: AnimShot[];
  captions: boolean;
  watermark?: string | null;
  hookMusic?: string | null;
  hookEnd: number;
  musicParts: {src: string; from: number; to: number}[];
  speech: Span[];
  cues: Cue[];
  silent?: boolean;
  soundOnly?: boolean;
};
