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
  | 'construction' // a building site: steel frame, a crane with a hanging beam, barriers
  | 'highway' // a wide road with lanes, guard rails, the city beyond
  | 'alley' // a narrow brick alley at night: dumpster, fire escape, puddles
  | 'lab' // a white lab with a glowing chamber and screens
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
  | 'detail' // the object he holds or that the shot is about
  | 'aerial' // high above, looking down, circling slowly
  | 'orbit' // circling round him at his height
  | 'crash-zoom'; // a fast push in on him, then a hold

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
  | 'cry'
  // action and fiction
  | 'lift' // crouch, then raise a big object overhead
  | 'catch' // arms up, a falling object lands in his hands
  | 'push-stop' // braced, arms out: a vehicle stops against his hands
  | 'throw' // from overhead, flings the object away
  | 'super-jump' // crouch and leap high out of the shot
  | 'land' // drops from the sky into a one-knee landing
  | 'dash' // super speed: a blur across the place
  | 'punch'
  | 'crush' // squeezes something in his hand
  | 'look-hands' // stares at his own hands
  | 'crouch'
  | 'kneel'
  | 'carry' // carries a person (an actor 'carried' in the same shot) or a crate
  | 'carried' // being carried by the 'carry' actor
  | 'fall' // knocked down
  | 'flee' // runs away, scared
  | 'cower' // crouched, arms over the head
  | 'help-up' // reaches a hand down
  | 'talk' // talking, a hand moving
  | 'gasp'; // hands to the mouth

export type Expr = 'neutral' | 'tired' | 'sad' | 'worried' | 'surprised' | 'happy' | 'determined' | 'annoyed' | 'asleep' | 'blank' | 'scared' | 'angry' | 'amazed' | 'pained';

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
  hat?: 'none' | 'hardhat' | 'cap';
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
  talk?: [number, number][]; // seconds into the shot when this person is speaking (the mouth moves)
  at?: number; // seconds into the shot of his key moment (the catch, the jump, the landing, the punch)
  look?: string; // a key of cast: the person in this shot he looks at, talks to, points at or walks up to
};

export type Thing = {
  kind: 'phone' | 'alarm' | 'mug' | 'laptop' | 'book' | 'shoes' | 'plate' | 'bag' | 'plant' | 'bottle' | 'calendar' | 'note' | 'pizza';
  spot: Spot;
  glow?: boolean; // a lit screen
  label?: string; // a word on a note, the clock's time, a calendar's day
};

// Big things in a scene and what they do (seconds `at` into the shot): a car, a falling steel beam, a truck...
export type BigKind = 'car' | 'bus' | 'truck' | 'beam' | 'crate' | 'boulder' | 'barbell' | 'pipe' | 'door' | 'ball';
export type BigMotion =
  | 'still'
  | 'fall' // drops from high above onto its spot
  | 'caught' // drops into the hands of the actor who 'catch'es
  | 'lifted' // raised overhead by the actor who 'lift's
  | 'held' // already overhead
  | 'thrown' // flies off from overhead
  | 'stop' // drives at the actor who 'push-stop's and stops against his hands
  | 'drive' // drives across the place
  | 'crushed'
  | 'hang' // swinging from the crane
  | 'shake';
export type Big = {kind: BigKind; spot: Spot; motion: BigMotion; at?: number; color?: string};

export type FxKind = 'shockwave' | 'crack' | 'dust' | 'speed' | 'sparks' | 'debris' | 'glass' | 'smoke' | 'fire' | 'shake' | 'flash' | 'alarm' | 'rain' | 'wind';
export type Fx = {kind: FxKind; at?: number; spot?: Spot};

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
  big?: Big[];
  fx?: Fx[];
  slowmo?: boolean; // the action at 0.4x while the words run at speed
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
