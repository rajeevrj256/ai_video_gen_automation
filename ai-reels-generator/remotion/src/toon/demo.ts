import type {Look, ToonProps, ToonShot} from './types';

// Studio preview: every part of the Toon editor on a 40-second timeline (no voice).

const exec: Look = {skin: '#EBB98F', hair: 'side', hairColor: '#3b2a1e', beard: 'none', glasses: false, shirt: '#ffffff', tie: '#C0392B', pants: '#2b3245', coat: '#2f3a56'};
const eng: Look = {skin: '#B97A50', hair: 'curly', hairColor: '#1d1410', beard: 'stubble', glasses: true, shirt: '#2F7DE1', tie: null, pants: '#2b3245', coat: null};
const sci: Look = {skin: '#F6D3B3', hair: 'bun', hairColor: '#8a4b2a', beard: 'none', glasses: false, shirt: '#ffffff', tie: null, pants: '#3a3f55', coat: '#e9eef5'};

let t = 0;
const shot = (d: number, s: Partial<ToonShot>): ToonShot => {
  const out: ToonShot = {start: t, duration: d, lead: 0, text: '', words: [], segment: 0, backdrop: 'flat', tone: 0, items: [], action: 'none',
    at: 0.6, camera: 'push', enter: 'cut', ...s};
  t += d;
  return out;
};

const shots: ToonShot[] = [
  shot(2.4, {card: {kind: 'number', text: '5', sub: 'The sandbox that leaked'}, enter: 'whip', tone: 1}),
  shot(3, {backdrop: 'grid', mascot: {mood: 'happy', tint: 'normal', pos: 'center', size: 'l'}, items: [{icon: 'wifi-off'}, {icon: 'plug'}], action: 'pop', at: 0.8}),
  shot(3, {backdrop: 'grid', mascot: {mood: 'wink', tint: 'normal', pos: 'right', size: 'm'}, action: 'crack', at: 0.5, enter: 'zoom'}),
  shot(3, {backdrop: 'grid', mascot: {mood: 'smug', tint: 'normal', pos: 'center', size: 'm'}, action: 'clone', at: 0.4}),
  shot(3, {backdrop: 'flat', tone: 2, items: [{icon: 'crate'}], action: 'fly-out', at: 0.5, slam: 'Too late', enter: 'whip'}),
  shot(3.4, {backdrop: 'desk', tone: 3, card: {kind: 'date', text: 'March 2025'}, people: [{look: eng, pose: 'hands-head', mood: 'shocked', pos: 'center', talking: false, seated: true, flip: false}], items: [{icon: 'Research Lab', label: 'Research Lab', badge: true}], action: 'pop', at: 1}),
  shot(3.4, {backdrop: 'stage', tone: 4, people: [{look: exec, pose: 'present', mood: 'smug', pos: 'center', talking: true, seated: false, flip: false}], slam: 'Under control', at: 1.2, enter: 'flash'}),
  shot(3.4, {backdrop: 'flat', tone: 4, items: [{icon: 'brain-circuit'}, {icon: 'cpu'}, {icon: 'shield'}, {icon: 'bot'}], action: 'strings-burn', at: 1}),
  shot(3, {backdrop: 'lab', tone: 0, people: [{look: sci, pose: 'point', mood: 'scared', pos: 'left', talking: false, seated: false, flip: false}], mascot: {mood: 'evil', tint: 'red', pos: 'right', size: 'm'}, items: [{icon: 'gauge', label: 'Optimization'}], action: 'gauge-up', at: 0.6}),
  shot(3, {backdrop: 'flat', tone: 1, items: [{icon: 'power', label: 'Power grid switch'}], action: 'toggle-off', at: 1, enter: 'whip'}),
  shot(3, {backdrop: 'flat', tone: 2, mascot: {mood: 'smug', tint: 'normal', pos: 'center', size: 's'}, action: 'flood', at: 0.4}),
  shot(2.6, {backdrop: 'space', items: [{icon: 'shield'}], action: 'crosshair', at: 0.3, slam: 'Game over'}),
  shot(3, {backdrop: 'flat', tone: 3, items: [{icon: 'user', label: 'Humans'}, {icon: 'bot', label: 'AI'}], action: 'versus', at: 0.3}),
  shot(3, {backdrop: 'dots', tone: 0, items: [{icon: 'a', label: '2023'}, {icon: 'b', label: '2024'}, {icon: 'c', label: '2025'}], values: [12, 31, 74], action: 'bars', at: 0.3}),
  shot(3, {backdrop: 'city', tone: 1, crowd: true, people: [{look: eng, pose: 'run', mood: 'scared', pos: 'left', talking: false, seated: false, flip: false}], action: 'shake', at: 0.5, camera: 'pan'}),
];

export const toonDemoProps: ToonProps = {
  fps: 30,
  duration: t,
  title: 'Toon demo',
  palette: {tones: ['#7B2FF7', '#1F8EF1', '#FF8FAB', '#F9C74F', '#5E2B97'], ink: '#0B1430', glow: '#38BDF8', accent: '#FF9F1C', hot: '#E5484D', paper: '#FFFFFF'},
  mascot: {shape: 'bubble', color: '#2F9BFF', accessory: 'headset', name: 'Byte'},
  style: {slam: 'pill', card: 'circle', seed: 7},
  shots,
  captions: false,
  watermark: null,
  music: null,
  speech: [],
  cues: [],
};
