import type {Shot, StickyProps} from './types';

// A short demo film in the reference style (reelgen/sticky/ANALYSIS.md): the phone, his battery, his sister.
const S: Omit<Shot, 'start'>[] = [
  {kind: 'card', duration: 4.5, caption: {lines: ['His phone was always at 100%.', 'He never was.'], pos: 'center'}, transition: 'cut'},
  {kind: 'scene', duration: 4, set: 'bedroom', light: 'night', clock: '1:07', meter: [64], time: '1:07 AM',
    actors: [{id: 'leo', x: 46, pose: 'lie', face: 'tired', glow: true, prop: 'phone'}], transition: 'fade', camera: 'push'},
  {kind: 'phone', duration: 3.5, phone: {mode: 'feed', items: ['hamburger', 'car', 'cat', 'dumbbell']}, meter: [61], transition: 'cut'},
  {kind: 'scene', duration: 4, set: 'bedroom', light: 'night', clock: '2:03', meter: [58], time: '2:03 AM',
    actors: [{id: 'leo', x: 46, pose: 'lie', face: 'numb', glow: true, prop: 'phone'}],
    shadow: {x: 66, size: 'normal', act: 'whisper'}, whisper: {text: 'just one more.', x: 74, y: 30}, transition: 'fade'},
  {kind: 'scene', duration: 4, set: 'hallway', light: 'night', meter: [56], time: '7:40 PM',
    actors: [{id: 'mia', x: 44, pose: 'hold_out', face: 'smile', prop: 'drawing'}, {id: 'leo', x: 70, pose: 'phone', face: 'numb', glow: true}],
    bubbles: [{who: 'mia', text: 'look what i made!'}, {who: 'leo', text: 'in a minute.'}], transition: 'cut'},
  {kind: 'object', duration: 4.5, object: {kind: 'drawing', title: 'ME + MY BROTHER', who: ['me', 'brother phone']},
    caption: {lines: ['This is how she saw him.'], pos: 'top'}, transition: 'fade'},
  {kind: 'face', duration: 3.5, focus: 'leo', set: 'hallway', light: 'night', actors: [{id: 'leo', x: 50, pose: 'stand', face: 'sad', tear: true}], transition: 'cut'},
  {kind: 'scene', duration: 3, set: 'void', stamp: 'DAY 1.', meter: [5], day: 'Day 1', transition: 'black'},
  {kind: 'scene', duration: 3.5, set: 'living', light: 'lamp', meter: [12], day: 'Day 3',
    actors: [{id: 'leo', x: 40, pose: 'shake', face: 'anxious'}], transition: 'cut', grade: 'cold'},
  {kind: 'calendar', duration: 3, calendar: {month: 'March', checks: 9}, meter: [27], day: 'Day 9', transition: 'cut'},
  {kind: 'scene', duration: 3.5, set: 'park', light: 'day', meter: [43], day: 'Day 16', grade: 'warm',
    actors: [{id: 'leo', x: 34, pose: 'run', to: 64, face: 'happy'}, {id: 'mia', x: 44, pose: 'run', to: 74, face: 'happy'}], transition: 'cut'},
  {kind: 'scene', duration: 4, set: 'living', light: 'lamp', meter: [51], day: 'Day 23',
    actors: [{id: 'leo', x: 34, pose: 'stand', face: 'determined'}], shadow: {x: 62, size: 'giant', act: 'grow'},
    whisper: {text: 'you earned it.', x: 72, y: 22}, transition: 'cut'},
  {kind: 'scene', duration: 3.5, set: 'living', light: 'lamp', meter: [51], day: 'Day 23',
    actors: [{id: 'leo', x: 34, pose: 'walk', to: 20, face: 'determined'}], shadow: {x: 62, size: 'giant', act: 'dissolve'}, transition: 'cut'},
  {kind: 'object', duration: 4.5, object: {kind: 'drawing', title: 'ME + MY BROTHER', who: ['me heart', 'brother']},
    caption: {lines: ['This time, she drew his face.'], pos: 'top'}, meter: [64], day: 'Day 30', transition: 'fade', grade: 'warm'},
  {kind: 'card', duration: 4.5, caption: {lines: ['Your phone is at 100%.', 'What are you at?'], pos: 'center'}, transition: 'black'},
  {kind: 'title', duration: 5, transition: 'fade'},
];

let t = 0;
const shots: Shot[] = S.map((s) => {
  const shot = {...s, start: t} as Shot;
  t += s.duration;
  return shot;
});

export const stickyDemoProps: StickyProps = {
  title: 'DOPAMINE.',
  tagline: ['Your phone can wait.', "They can't."],
  accent: '#FF4FA3',
  meter: {kind: 'battery', labels: ['his battery'], unit: '%'},
  cast: [
    {id: 'leo', name: 'Leo', tone: 'cream', wear: 'hood', color: '#4A505C'},
    {id: 'mia', name: 'Mia', tone: 'cream', wear: 'bob', color: '#1F1F24', kid: true},
  ],
  shots,
  fps: 30,
  duration: t,
};
