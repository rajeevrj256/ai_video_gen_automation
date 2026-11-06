// Low-poly films: a faceted 3D man (the user's own recurring character from their reference Short 'Life of a Man':
// curly brown hair, square glasses, a red sweater, brown trousers, white shoes) living small everyday struggles,
// told by a calm narrator with word-by-word captions. Python (reelgen/lowpoly/) writes these props.

export type SetName =
  | 'bedroom'
  | 'hallway' // inside the flat at the front door: shoe rack, coat hooks
  | 'street' // a city pavement past lit windows
  | 'park' // a path at dawn: low hills, trees, a lamp post
  | 'kitchen'
  | 'living' // couch, TV, coffee table
  | 'office' // desk, monitor, office chair, plant
  | 'bathroom' // mirror, sink
  | 'gym'
  | 'cafe'
  | 'busstop'
  | 'rooftop'
  | 'void'; // a plain warm studio floor: for a thought, a title

export type Light = 'night' | 'lamp' | 'dawn' | 'morning' | 'day' | 'evening' | 'dark';

export type Cam =
  | 'face' // close-up of the face
  | 'face-top' // close-up from above (lying down)
  | 'top' // straight down over the whole body (lying, sitting on the floor)
  | 'medium' // chest up
  | 'wide' // the room from a high corner
  | 'side' // from the side, tracking a walk
  | 'front' // from the front, walking toward the camera
  | 'back' // from behind, over the shoulder at what he faces
  | 'low' // from the floor, looking up
  | 'detail'; // the object he holds or that the shot is about

export type Action =
  | 'stand'
  | 'walk'
  | 'run'
  | 'sit' // on a chair / couch / bed edge (whatever is at his spot)
  | 'sit-floor'
  | 'lie' // on his back
  | 'lie-side'
  | 'lie-phone' // on his back holding the phone over his face
  | 'phone' // standing or sitting, looking at the phone in his hand
  | 'type' // at a desk or with a laptop on his knees
  | 'reach' // reaching to the side (the alarm, a switch)
  | 'sit-up' // from lying to sitting
  | 'get-up' // from sitting to standing
  | 'shoes' // sitting, bent forward, putting shoes on
  | 'head-in-hands'
  | 'slump'
  | 'stretch'
  | 'sigh'
  | 'nod'
  | 'shake-head'
  | 'shrug'
  | 'think' // a hand to the chin
  | 'drink'
  | 'eat'
  | 'look-out' // at a window, hands at his sides
  | 'wave'
  | 'point'
  | 'cheer'
  | 'jog' // jogging on the spot / easy run
  | 'pushup'
  | 'read' // a book in both hands
  | 'cry';

export type Expr = 'neutral' | 'tired' | 'sad' | 'worried' | 'surprised' | 'happy' | 'determined' | 'annoyed' | 'asleep' | 'blank';

export type Spot = 'center' | 'left' | 'right' | 'bed' | 'chair' | 'desk' | 'door' | 'window' | 'couch' | 'mirror' | 'counter' | 'far';

export type Hold = 'none' | 'phone' | 'mug' | 'book' | 'laptop' | 'shoes' | 'bag' | 'keys' | 'fork';

export type Design = {
  skin: string;
  hair: string;
  hairStyle: 'curly' | 'short' | 'long' | 'bun' | 'bald' | 'ponytail';
  glasses: boolean;
  top: string; // sweater colour
  topKind: 'sweater' | 'shirt' | 'dress' | 'hoodie' | 'suit';
  trousers: string;
  shoes: string;
  beard?: boolean;
  height?: number; // 1 = the hero; a kid 0.7
};

export type Actor = {
  who: string; // a key of cast
  action: Action;
  expression: Expr;
  spot: Spot;
  to?: Spot; // walk/run: where he goes (else across the frame)
  facing?: 'camera' | 'left' | 'right' | 'away';
  hold?: Hold;
  covered?: boolean; // in bed under the blanket
};

export type Thing = {
  kind: 'phone' | 'alarm' | 'mug' | 'laptop' | 'book' | 'shoes' | 'plate' | 'bag' | 'plant' | 'bottle' | 'calendar' | 'note' | 'pizza';
  spot: Spot;
  glow?: boolean; // a lit screen
  label?: string; // a word on a note, the clock's time, a calendar's day
};

export type LPShot = {
  start: number; // seconds
  duration: number;
  set: SetName;
  light: Light;
  camera: Cam;
  actors: Actor[];
  things?: Thing[];
  focus?: number; // index of the actor the camera follows
  fadeIn?: number; // seconds of fade from black
  fadeOut?: number;
  cut?: 'hard' | 'dip'; // dip = through black
  seed?: number;
};

export type Caption = {start: number; end: number; text: string; red?: boolean; stamp?: boolean};

export type LowPolyProps = {
  fps: number;
  duration: number;
  vertical: boolean; // 1080x1920 Short, else 1920x1080 film
  silent?: boolean;
  watermark: string; // the channel's name at the top ('' = none)
  cast: Record<string, Design>;
  shots: LPShot[];
  captions: Caption[];
  seed: number;
  dof?: boolean; // depth of field (on unless a slow machine turns it off)
};
