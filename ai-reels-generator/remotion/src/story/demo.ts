import type {ActorState, Design, Shot, StoryProps} from './types';

// Demo props for the Studio and stills: the two-character cast in a few sets, no audio.
const a = (id: string, x: number, o: Partial<ActorState> = {}): ActorState => ({
  id, x, pose: 'stand', face: 'neutral', facing: 1, emote: 'none', prop: 'none', action: 'none', ...o,
});
const words = (text: string) => text.split(' ').map((w, i) => ({text: w, start: 0.2 + i * 0.32, end: 0.45 + i * 0.32}));
const shot = (start: number, o: Partial<Shot>): Shot => ({
  start, duration: 3, scene: 1, setting: 'living-room', camera: 'wide', actors: [], words: [], lead: 0.1, ...o,
});

const BEN: Design = {hair: 'messy', hairColour: '#1E1B18', top: 'hoodie', topColour: '#34435E', bottom: 'jeans', bottomColour: '#4C5D74',
  shoes: 'sneakers', shoesColour: '#5A4A3A', headwear: 'none', headwearColour: '', extras: ['satchel'], extraColour: '#A08458'};
const MOM: Design = {hair: 'bun', hairColour: '#3B2E24', top: 'sweater', topColour: '#9C4A3C', bottom: 'skirt', bottomColour: '#6E6F45',
  shoes: 'shoes', shoesColour: '#3B2E24', headwear: 'none', headwearColour: '', extras: ['earrings'], extraColour: '#8A6A44'};

export const storyDemoProps: StoryProps = {
  fps: 30,
  duration: 18,
  title: 'Result day',
  art: 'ink',
  cast: [{id: 'raju', name: 'Ben', look: 'boy', design: BEN}, {id: 'mom', name: 'Mom', look: 'woman', design: MOM}],
  shots: [
    shot(0, {caption: 'POV: result day', speaker: 'raju', text: 'Mom... I can explain.', words: words('Mom... I can explain.'),
      actors: [a('raju', 760, {face: 'nervous', emote: 'sweat', prop: 'paper', propText: 'F', pose: 'hold'}), a('mom', 1180, {facing: -1, pose: 'hands-on-hips', face: 'angry'})]}),
    shot(3, {camera: 'punch', speaker: 'mom', text: 'Explain WHAT?!', words: words('Explain WHAT?!'),
      actors: [a('raju', 760, {face: 'shock', emote: '!'}), a('mom', 1180, {facing: -1, pose: 'point', face: 'angry', emote: 'anger'})]}),
    shot(6, {scene: 2, setting: 'classroom', sign: 'EXAM', speaker: 'raju', text: 'I studied the wrong chapter.', words: words('I studied the wrong chapter.'),
      actors: [a('raju', 960, {pose: 'facepalm', face: 'sad'})]}),
    shot(9, {scene: 3, setting: 'kitchen', washing: true, speaker: 'mom', text: 'Hey, can I see your phone real quick?', words: words('Hey, can I see your phone real quick?'),
      actors: [a('mom', 880, {face: 'neutral'}), a('raju', 1080, {facing: -1, face: 'nervous', emote: 'sweat'})]}),
    shot(12, {scene: 4, setting: 'bathroom', camera: 'close', focus: 'raju', speaker: 'raju', text: 'Hiding here till dad sleeps.', words: words('Hiding here till dad sleeps.'),
      actors: [a('raju', 1300, {face: 'nervous', emote: 'sweat', facing: -1})]}),
    shot(15, {scene: 5, setting: 'street', actors: [a('raju', 700, {action: 'walk-out-right', face: 'happy'}), a('mom', 1400, {facing: -1, pose: 'cry', face: 'cry'})]}),
  ],
  music: null,
  cues: [],
  speech: [],
  sfx: null,
};
