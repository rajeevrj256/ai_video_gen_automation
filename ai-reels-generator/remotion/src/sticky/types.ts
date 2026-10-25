// Props of the "Sticky" composition (reelgen/sticky/): voiceless sticky-animation films told with pictures, a few
// lines of on-screen text, a visible inner voice and a meter. Picture only: the soundtrack is mixed by the pipeline.
// Times are seconds from the start of the film.

export type Tone = 'cream' | 'grey' | 'peach' | 'tan' | 'brown' | 'pale';
export type Wear = 'none' | 'hood' | 'bob' | 'ponytail' | 'short' | 'beanie' | 'cap' | 'headband' | 'bun' | 'curly'
  | 'scarf' | 'hardhat' | 'long' | 'bald';

export type Cast = {
  id: string;
  name: string;
  tone: Tone;
  wear: Wear; // the one identity item (or hair) that tells who is who
  color: string; // its colour, hex
  kid?: boolean; // smaller
  extra?: Wear; // a second item (a scarf with a bob...)
};

export type Pose = 'stand' | 'walk' | 'run' | 'sit' | 'sit_bed' | 'lie' | 'curl' | 'kneel' | 'slump' | 'reach' | 'phone'
  | 'type' | 'shake' | 'pushup' | 'punch' | 'climb' | 'cheer' | 'hug' | 'hold_out' | 'write' | 'wave' | 'fall' | 'think'
  | 'guitar' | 'sleep';

export type Face = 'neutral' | 'tired' | 'sad' | 'cry' | 'worried' | 'anxious' | 'angry' | 'determined' | 'happy'
  | 'smile' | 'shock' | 'embarrassed' | 'numb' | 'smug';

export type Prop = 'none' | 'phone' | 'book' | 'guitar' | 'drawing' | 'umbrella' | 'coffee' | 'ball' | 'bag' | 'pen'
  | 'note' | 'cup' | 'gift' | 'laptop';

export type Actor = {
  id: string; // cast id
  x: number; // 0..100 across the floor
  pose: Pose;
  face: Face;
  facing?: 'left' | 'right';
  to?: number; // walk/run: where they end up (0..100)
  prop?: Prop;
  glow?: boolean; // a phone screen lights the face
  tear?: boolean;
  sweat?: boolean;
  faceAt?: number; // seconds into the shot when `face2` replaces `face`
  face2?: Face;
};

export type Shadow = {
  x: number; // 0..100
  size: 'small' | 'normal' | 'giant';
  act: 'appear' | 'lean' | 'grow' | 'whisper' | 'dissolve' | 'loom';
  copy?: string; // a cast id: the voice wears his face (it learned to sound like him)
};

export type SetName = 'bedroom' | 'desk' | 'living' | 'kitchen' | 'bathroom' | 'hallway' | 'street' | 'busstop' | 'cafe'
  | 'classroom' | 'gym' | 'office' | 'stairs' | 'rooftop' | 'hill' | 'park' | 'court' | 'stage' | 'void';
export type Light = 'night' | 'lamp' | 'dawn' | 'day' | 'dusk' | 'grey' | 'neon';

export type Message = {me: boolean; text: string};
export type Phone = {
  mode: 'chat' | 'feed' | 'notif' | 'lock' | 'dialog' | 'call' | 'video' | 'post';
  title?: string; // the contact, the app, the video title, the dialog's question
  messages?: Message[];
  typing?: string; // typed into the box during the shot
  items?: string[]; // feed posts (emoji or short words), notifications, dialog buttons
  time?: string; // lock screen
  seen?: boolean; // 'Seen' under the last message
};

export type Shot = {
  start: number;
  duration: number;
  kind: 'scene' | 'phone' | 'clock' | 'calendar' | 'card' | 'title' | 'object' | 'graph' | 'face' | 'split';
  act?: string;
  set?: SetName;
  light?: Light;
  actors?: Actor[];
  shadow?: Shadow | null;
  clock?: string; // the time on the alarm clock (in a room, or the clock insert)
  phone?: Phone;
  // before / beforeMarks: what the same month's calendar already showed (drawn at once; only the rest is animated)
  rain?: boolean; // rain falling over the scene (the shot's sounds have rain)
  calendar?: {month: string; checks: number; marks?: number[]; days?: number; before?: number; beforeMarks?: number[]};
  object?: {kind: 'drawing' | 'note' | 'letter' | 'poster' | 'list' | 'bill'; title?: string; lines?: string[]; who?: string[]; checked?: number};
  graph?: {shape: 'wave' | 'spikes' | 'rise' | 'plateau' | 'dip_rise' | 'fall'; labels?: string[]};
  left?: Shot; // split screen: two lives side by side
  right?: Shot;
  caption?: {lines: string[]; pos: 'top' | 'bottom' | 'center'};
  whisper?: {text: string; x: number; y: number};
  bubbles?: {who: string; text: string}[];
  notes?: string[]; // worries as sticky notes, piling up
  pills?: string[]; // notification pills around the hero
  stamp?: string; // a big chalk line: 'DAY 1.'
  grade?: 'normal' | 'grey' | 'cold' | 'warm';
  transition?: 'cut' | 'fade' | 'black';
  camera?: 'still' | 'push' | 'drift';
  meter?: number[]; // the HUD's value(s) during this shot
  day?: string; // 'DAY 23'
  time?: string; // the HUD clock
  focus?: string; // face: whose face
};

export type Meter = {
  kind: 'battery' | 'bar' | 'counter' | 'dual' | 'none';
  labels: string[]; // 'his battery' | 'SCREEN TIME' | 'DAY' | ['SEEN', 'KNOWN']
  unit?: string; // '%'
  color?: string;
};

export type StickyProps = {
  title: string;
  tagline: string[]; // two lines: the statement and the dare (the dare in the accent colour)
  accent: string; // the voice's colour and the title underline
  meter: Meter;
  cast: Cast[];
  shots: Shot[];
  fps: number;
  duration: number;
  silent?: boolean;
  soundOnly?: boolean;
};
