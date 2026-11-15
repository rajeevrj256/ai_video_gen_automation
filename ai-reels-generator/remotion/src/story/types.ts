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
export type Thing = {name: string; x: number; table: boolean; big: boolean; effect: Effect; svg?: string | null; photo?: {src: string; w: number; h: number} | null; label?: string}; // svg: Claude's own drawing (200x200); photo: a real picture as proof (Wikimedia Commons), shown as a pinned print
export type Setting =
  | 'living-room' | 'classroom' | 'kitchen' | 'bedroom' | 'street' | 'office' | 'bathroom'
  | 'park' | 'shop' | 'exam-hall' | 'blank' | 'mine' | 'tunnel' | 'garage' | 'warehouse';
export type Camera = 'wide' | 'close' | 'punch' | 'shake' | 'push' | 'pan';
export type Action = 'none' | 'jump' | 'shake' | 'fall' | 'spin' | 'walk-in-left' | 'walk-in-right' | 'walk-out-left' | 'walk-out-right' | 'step' | 'walk-across' | 'turn' | 'look-up'
  // acted out with the body and what it brings (acts.tsx): a ball kicked or kept up, a camera, bills...
  | 'kick' | 'juggle' | 'throw' | 'type' | 'write' | 'handshake' | 'count-money' | 'film' | 'phone-call' | 'carry' | 'cheer' | 'nod' | 'watch';

// A piece of furniture in the scene (kinds in sets.json): centre x and width on the 1920 px set.
export type Piece = {kind: string; x: number; width: number};

// A character's design in the ink look (ink.tsx): written per story, kept for that name across episodes.
export type Design = {
  hair: 'messy' | 'spiky' | 'side-part' | 'curly' | 'short' | 'long' | 'ponytail' | 'bun' | 'braids' | 'bald';
  hairColour: string;
  top: 'hoodie' | 'tshirt' | 'shirt' | 'jacket' | 'suit' | 'sweater' | 'coat' | 'dress' | 'coveralls' | 'kurta';
  topColour: string;
  bottom: 'trousers' | 'jeans' | 'shorts' | 'skirt' | 'none';
  bottomColour: string;
  shoes: 'shoes' | 'boots' | 'sneakers' | 'sandals';
  shoesColour: string;
  headwear: 'none' | 'cap' | 'hard-hat' | 'beanie' | 'fedora' | 'cowboy' | 'helmet' | 'chef-hat' | 'headscarf' | 'beret' | 'bow' | 'headband';
  headwearColour: string;
  extras: ('glasses' | 'sunglasses' | 'beard' | 'stubble' | 'mustache' | 'earrings' | 'tie' | 'scarf' | 'satchel' | 'backpack'
    | 'apron' | 'lanyard' | 'stethoscope' | 'watch' | 'headlamp')[];
  extraColour: string; // tie, scarf, bag, apron
};

export type CastMember = {id: string; name: string; look: Look; outfit?: string; design?: Design}; // outfit: the grey look's shirt or dress colour

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
  back?: boolean; // seen from behind (walking away into a place): no face, the back of the head
  far?: boolean; // small, far away (a very wide shot): on the set's distant ground (ink.tsx FAR)
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
  weather?: 'none' | 'rain' | 'snow' | 'dust' | 'smoke'; // what drifts through the scene
  light?: 'day' | 'dawn' | 'dusk' | 'night';
  backdropSvg?: string | null; // Claude's own drawing of a place no setting shows (1920x900, floor at y=900)
  placeLabel?: string; // where a new place is ('San Mateo, California · 2005'): a tag for its first 3 s
  rewind?: boolean; // the first shot after the cold open: a short tape rewind into the story
  hook?: boolean; // a cold-open shot
  cut2?: {at: number; camera: Camera; focus?: string; x?: number}; // a second framing from `at` s (x: frame an object there)
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
  // how lines show: small subtitles under the scene (the channel's style), speech bubbles, or none (documentaries: the narration is heard, not shown)
  dialogue?: 'subtitle' | 'bubble' | 'none';
  vertical?: boolean; // a 9:16 Short: the same sets, framed on whoever is speaking
  art?: 'ink' | 'grey'; // ink = the hand-inked look (ink.tsx); missing = the old grey channel look
  ambience?: {src: string; from: number; to: number}[]; // quiet beds per scene (wind, rain, room tone)
};
