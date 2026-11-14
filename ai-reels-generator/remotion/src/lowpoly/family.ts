// His family in a picture: the framed photo on his desk, the photos on his phone and the video of them laughing
// (the user's silent scene 'The Things He Misses'). Drawn on a canvas in the films' own look: the same people as the
// recurring cast (story.CAST_LIBRARY: his mum, his dad, Mia, and him), big round heads, flat muted clothes, a warm
// place behind them. Never a real photograph and never words.

type Person = {skin: string; hair: string; style: 'curly' | 'bun' | 'bald' | 'long'; top: string; glasses: boolean; beard?: boolean; h: number};

// = story.CAST_LIBRARY ('his dad', 'his mum', 'Mia') and the hero's own look (Man.tsx HERO)
const FAMILY: Person[] = [
  {skin: '#e2c6ab', hair: '#9c9a98', style: 'bald', top: '#2f3e5c', glasses: true, beard: true, h: 1.05},
  {skin: '#e6d8cb', hair: '#9c9a98', style: 'bun', top: '#e9dfc9', glasses: true, h: 0.96},
  {skin: '#e6d8cb', hair: '#94593a', style: 'curly', top: '#b2414e', glasses: true, h: 1.0},
  {skin: '#e6d8cb', hair: '#8e3f22', style: 'long', top: '#2f6f73', glasses: false, h: 0.9},
];

// the places the pictures were taken (sky, ground, a detail)
export type Place = 'park' | 'beach' | 'birthday' | 'kitchen' | 'garden' | 'snow';
export const PLACES: Place[] = ['park', 'beach', 'birthday', 'kitchen', 'garden', 'snow'];
const BACK: Record<Place, [string, string, string]> = {
  park: ['#f6c98a', '#e59a63', '#6f9a58'],
  beach: ['#9fd0ea', '#d8ecf2', '#e8d3a0'],
  birthday: ['#5a3f52', '#8a5a63', '#7a5a43'],
  kitchen: ['#e9dcc4', '#d9c7a8', '#a77d58'],
  garden: ['#b8dcf0', '#e6f1e0', '#5f8d4e'],
  snow: ['#c9d6e6', '#eef2f6', '#f4f6f8'],
};

const shade = (hex: string, k: number) => {
  const n = parseInt(hex.slice(1), 16);
  const c = (v: number) => Math.max(0, Math.min(255, Math.round(v * k)));
  return `rgb(${c((n >> 16) & 255)},${c((n >> 8) & 255)},${c(n & 255)})`;
};

const disc = (g: CanvasRenderingContext2D, x: number, y: number, r: number, col: string) => {
  g.fillStyle = col;
  g.beginPath();
  g.arc(x, y, r, 0, Math.PI * 2);
  g.fill();
};

// one person, standing at x with their feet at `foot`, `s` = their head's radius; `laugh` 0..1 opens the mouth and
// tips the head back a little, `lean` leans them toward their neighbour
const drawPerson = (g: CanvasRenderingContext2D, p: Person, x: number, foot: number, s: number, laugh: number, lean: number) => {
  const bodyH = s * 2.1 * p.h;
  const bodyW = s * 1.55;
  const top = foot - bodyH;
  g.save();
  g.translate(x, foot);
  g.rotate(lean);
  g.translate(-x, -foot);
  // the body: a rounded block in their top's colour, shaded on one side like the films' flat-shaded boxes
  g.fillStyle = p.top;
  g.beginPath();
  g.roundRect(x - bodyW / 2, top, bodyW, bodyH, s * 0.35);
  g.fill();
  g.fillStyle = shade(p.top, 0.8);
  g.beginPath();
  g.roundRect(x + bodyW * 0.18, top, bodyW * 0.32, bodyH, [0, s * 0.35, s * 0.35, 0]);
  g.fill();
  const hy = top - s * 0.82 - laugh * s * 0.08;
  // hair behind the head
  if (p.style === 'long') {
    g.fillStyle = p.hair;
    g.beginPath();
    g.roundRect(x - s * 1.08, hy - s * 0.6, s * 2.16, s * 2.0, s * 0.8);
    g.fill();
  }
  disc(g, x, hy, s, p.skin);
  g.fillStyle = shade(p.skin, 0.9);
  g.beginPath();
  g.arc(x, hy, s, -0.6, 1.0);
  g.lineTo(x, hy);
  g.fill();
  // hair on top
  g.fillStyle = p.hair;
  if (p.style === 'curly') {
    for (let i = 0; i < 9; i++) {
      const a = Math.PI * (1.05 + (i / 8) * 0.9);
      disc(g, x + Math.cos(a) * s * 0.92, hy + Math.sin(a) * s * 0.88, s * 0.34, p.hair);
    }
    disc(g, x, hy - s * 0.82, s * 0.4, p.hair);
  } else if (p.style === 'bun') {
    g.beginPath();
    g.arc(x, hy, s * 1.02, Math.PI * 1.02, Math.PI * 1.98);
    g.fill();
    disc(g, x, hy - s * 1.12, s * 0.36, p.hair);
  } else if (p.style === 'long') {
    g.beginPath();
    g.arc(x, hy, s * 1.04, Math.PI * 1.0, Math.PI * 2.0);
    g.fill();
  } else if (p.style === 'bald') {
    g.beginPath();
    g.arc(x, hy, s * 1.02, Math.PI * 0.92, Math.PI * 1.12);
    g.arc(x, hy, s * 1.02, Math.PI * 1.88, Math.PI * 2.08);
    g.fill();
  }
  if (p.beard) {
    g.fillStyle = p.hair;
    g.beginPath();
    g.arc(x, hy + s * 0.2, s * 0.78, 0.15 * Math.PI, 0.85 * Math.PI);
    g.fill();
  }
  // eyes: closed happy arcs when laughing, else dots; glasses over them
  const ey = hy - s * 0.02;
  g.strokeStyle = '#1b1a1a';
  g.fillStyle = '#1b1a1a';
  g.lineWidth = Math.max(1, s * 0.09);
  for (const sx of [-1, 1]) {
    if (laugh > 0.35) {
      g.beginPath();
      g.arc(x + sx * s * 0.36, ey + s * 0.04, s * 0.13, Math.PI * 1.1, Math.PI * 1.9);
      g.stroke();
    } else disc(g, x + sx * s * 0.36, ey, s * 0.11, '#1b1a1a');
    if (p.glasses) {
      g.lineWidth = Math.max(1, s * 0.07);
      g.strokeRect(x + sx * s * 0.36 - s * 0.24, ey - s * 0.18, s * 0.48, s * 0.36);
    }
  }
  // the mouth: a smile, open when laughing
  const my = hy + s * 0.42;
  if (laugh > 0.2) {
    g.fillStyle = '#5a2224';
    g.beginPath();
    g.ellipse(x, my, s * 0.24, s * (0.08 + 0.14 * laugh), 0, 0, Math.PI * 2);
    g.fill();
  } else {
    g.lineWidth = Math.max(1, s * 0.08);
    g.beginPath();
    g.arc(x, my - s * 0.16, s * 0.22, 0.2 * Math.PI, 0.8 * Math.PI);
    g.stroke();
  }
  g.restore();
};

// The family together in one picture filling (x, y, w, h). `t` (seconds) animates it: with `laughing` they laugh
// (heads bob, mouths open, leaning into each other), the way a video of them would; `seed` changes who stands where.
export const drawFamily = (g: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, place: Place,
  {t = 0, laughing = false, seed = 0}: {t?: number; laughing?: boolean; seed?: number} = {}) => {
  const [sky, low, ground] = BACK[place];
  g.save();
  g.beginPath();
  g.rect(x, y, w, h);
  g.clip();
  const grad = g.createLinearGradient(0, y, 0, y + h);
  grad.addColorStop(0, sky);
  grad.addColorStop(0.62, low);
  g.fillStyle = grad;
  g.fillRect(x, y, w, h);
  g.fillStyle = ground;
  g.fillRect(x, y + h * 0.72, w, h * 0.28);
  // a detail of the place behind them
  if (place === 'park' || place === 'garden') {
    for (let i = 0; i < 4; i++) {
      const tx = x + w * (0.08 + i * 0.28 + ((seed * 0.13) % 0.1));
      g.fillStyle = shade(ground, 0.8);
      g.fillRect(tx - w * 0.012, y + h * 0.5, w * 0.024, h * 0.24);
      disc(g, tx, y + h * 0.47, w * 0.075, shade(ground, 1.05 - i * 0.06));
    }
    if (place === 'park') disc(g, x + w * 0.78, y + h * 0.2, w * 0.07, '#ffe2a8');
  } else if (place === 'beach') {
    g.fillStyle = '#5aa6c9';
    g.fillRect(x, y + h * 0.58, w, h * 0.14);
    disc(g, x + w * 0.2, y + h * 0.18, w * 0.06, '#fff4cf');
  } else if (place === 'birthday') {
    g.fillStyle = '#c9a77a';
    g.fillRect(x + w * 0.05, y + h * 0.74, w * 0.9, h * 0.06);
    g.fillStyle = '#f0e2d0';
    g.fillRect(x + w * 0.42, y + h * 0.62, w * 0.16, h * 0.12);
    for (let i = 0; i < 3; i++) {
      g.fillStyle = '#fff';
      g.fillRect(x + w * (0.45 + i * 0.045), y + h * 0.56, w * 0.01, h * 0.06);
      disc(g, x + w * (0.455 + i * 0.045), y + h * 0.55, w * 0.008 + 0.6 * Math.abs(Math.sin(t * 9 + i)), '#ffcf5a');
    }
    for (let i = 0; i < 9; i++) disc(g, x + w * ((i * 0.37 + seed * 0.1) % 1), y + h * (0.08 + ((i * 0.23) % 0.3)), w * 0.008, '#ffe9a8');
  } else if (place === 'kitchen') {
    g.fillStyle = '#c4b08e';
    for (let i = 0; i < 3; i++) g.fillRect(x + w * (0.1 + i * 0.3), y + h * 0.12, w * 0.22, h * 0.2);
  } else if (place === 'snow') {
    for (let i = 0; i < 30; i++) disc(g, x + w * ((i * 0.37 + t * 0.05) % 1), y + h * ((i * 0.53 + t * 0.12) % 0.7), w * 0.006, '#ffffff');
  }
  // the four of them, close together, the tallest at the back
  const order = [0, 1, 2, 3].map((i) => (i + seed) % 4);
  const n = order.length;
  const s = Math.min(w / (n * 2.2), h * 0.13);
  const foot = y + h * 0.98;
  order.forEach((i, k) => {
    const px = x + w * (0.5 + (k - (n - 1) / 2) * (1 / (n + 0.6)));
    const bob = laughing ? Math.max(0, Math.sin(t * 7.5 + k * 1.3)) : 0;
    const laugh = laughing ? 0.4 + 0.6 * bob : 0;
    const lean = laughing ? (k < n / 2 ? 1 : -1) * 0.06 * bob : (k - (n - 1) / 2) * -0.02;
    drawPerson(g, FAMILY[i], px, foot - bob * s * 0.12, s, laugh, lean);
  });
  // a film's soft light: warm at the top, a vignette
  const vig = g.createRadialGradient(x + w / 2, y + h / 2, Math.min(w, h) * 0.3, x + w / 2, y + h / 2, Math.max(w, h) * 0.75);
  vig.addColorStop(0, 'rgba(0,0,0,0)');
  vig.addColorStop(1, 'rgba(40,20,10,0.32)');
  g.fillStyle = vig;
  g.fillRect(x, y, w, h);
  g.restore();
};
