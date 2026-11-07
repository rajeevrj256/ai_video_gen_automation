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
  | 'sky' // high above a sea of clouds: for anything that flies, a skydive, a fight on a plane's wing
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
  | 'crash-zoom' // a fast push in on him, then a hold
  // a vehicle under way (or someone in it): the car-chase and air-to-air shots
  | 'chase' // from a camera car behind it, a little above
  | 'lead' // ahead of it, low, looking back as it gains
  | 'tracking' // beside it at its speed
  | 'pass-by' // from the roadside as it whooshes past, a long lens panning
  | 'heli' // from a helicopter, high behind and to the side
  | 'drone' // straight down on it
  | 'cockpit' // on the dashboard, on the driver's or pilot's face
  | 'bumper' // low at its front corner along its flank (on a plane: the wing tip)
  | 'pedal' // down in the footwell: his foot on the accelerator or the brake
  | 'wheel'; // close on his hands on the steering wheel

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
  | 'gasp' // hands to the mouth
  // in or on a vehicle (`on`): at the controls, riding along, leaving it, falling free
  | 'drive' // at the wheel / the controls of the vehicle he is `on` (the driver's or pilot's seat)
  | 'ride' // a passenger seat of the vehicle he is `on`
  | 'jump-off' // standing on (or in) the vehicle, he leaps off at his moment and falls away
  | 'skydive' // falling free through the air, arms and legs spread
  | 'brace'; // standing on a moving vehicle's top, knees bent, arms out for balance

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
  on?: number; // index into the shot's big things: the vehicle he is in (drive, ride) or standing on (any other action)
};

export type Thing = {
  kind: 'phone' | 'alarm' | 'mug' | 'laptop' | 'book' | 'shoes' | 'plate' | 'bag' | 'plant' | 'bottle' | 'calendar' | 'note' | 'pizza';
  spot: Spot;
  glow?: boolean; // a lit screen
  label?: string; // a word on a note, the clock's time, a calendar's day
};

// Big things in a scene and what they do (seconds `at` into the shot): a car, a falling steel beam, a truck...
export type BigKind = 'car' | 'bus' | 'truck' | 'beam' | 'crate' | 'boulder' | 'barbell' | 'pipe' | 'door' | 'ball' | 'made';
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
  | 'shake'
  // vehicles under way (anyone `on` it moves with it, and the camera can travel with it): on the ground...
  | 'race' // flat out, accelerating
  | 'drift' // the tail swings out at its moment and it slides through, tyres smoking
  | 'spin' // a full spin at its moment, then on
  | 'reverse' // backwards
  | 'jump' // leaves the ground at its moment (a ramp, a roof's edge) and lands further on
  // ...and in the air
  | 'fly' // flies level (on the ground at first it lifts off at its moment)
  | 'climb' // noses up and climbs
  | 'dive' // noses down and dives
  | 'bank' // turns, leaning into the turn
  | 'roll'; // a full barrel roll at its moment
export type Big = {kind: BigKind; spot: Spot; motion: BigMotion; at?: number; color?: string; made?: string};

// Something the writer designed for this film (a plane, a jet, a helicopter, a motorbike, a boat...), built at render
// time from low-poly parts in its own frame: x right, y up from its bottom, z forward (metres, the man is ~2 m tall).
export type PartShape = 'box' | 'cylinder' | 'cone' | 'sphere' | 'wedge';
export type MadePart = {
  shape: PartShape;
  at: [number, number, number]; // centre
  size: [number, number, number]; // box/sphere/wedge: width, height, length; cylinder/cone: diameter, length (along its y), end diameter
  turn?: [number, number, number]; // degrees about x, y, z
  color: string; // hex
  glow?: boolean;
  glass?: boolean;
  spin?: '' | 'x' | 'y' | 'z'; // propellers, rotors, wheels: turns about this axis while it moves
};
export type Made = {
  parts: MadePart[];
  seats: [number, number, number][]; // where people sit, the driver's / pilot's first (the seat's top, under him)
  top: number; // the height of the surface someone can stand on (a roof, a wing)
  travel: 'ground' | 'air' | 'water' | 'none';
  dims: [number, number, number]; // width, height, length (from the parts)
};

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
  // a split-second cut-in inside the shot, as in an action film: his foot hitting the accelerator or the brake, or his
  // hands yanking the wheel, then back to the shot's own camera on what it does (seconds into the shot; `on` = the car)
  insert?: {cam: 'pedal' | 'wheel'; from: number; to: number; pedal?: 'gas' | 'brake'; on: number};
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
  made?: Record<string, Made>; // things the writer designed for this film, by name
};
