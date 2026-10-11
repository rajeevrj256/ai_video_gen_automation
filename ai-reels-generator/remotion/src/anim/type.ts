import '@fontsource/bebas-neue/400.css';
import '@fontsource/fraunces/600.css';
import '@fontsource/fraunces/600-italic.css';
import '@fontsource/fraunces/700.css';
import '@fontsource/montserrat/600.css';
import '@fontsource/montserrat/700.css';
import {useEffect, useState} from 'react';
import {continueRender, delayRender} from 'remotion';

// Typography for Animated videos. The first version used the Shorts' look everywhere (Montserrat 900 in capitals
// with a thick black outline and a coloured offset shadow), which read as cheap word art over painted frames.
// Now a display face that suits the art style, set like a film title: a refined serif for painted, 3D and
// storybook looks; a tall condensed face in capitals for anime, comic and neon looks. Labels and kickers stay
// in Montserrat at a lighter weight with wide tracking; shadows are soft, never outlines.

export type Face = {family: string; weight: number; upper: boolean; tracking: string; italic: string; size: number};

const SERIF: Face = {family: '"Fraunces", Georgia, serif', weight: 700, upper: false, tracking: '-0.01em', italic: 'italic', size: 1};
const CONDENSED: Face = {family: '"Bebas Neue", "Montserrat", sans-serif', weight: 400, upper: true, tracking: '0.03em', italic: 'normal', size: 1.45};
const CONDENSED_STYLES = new Set(['anime', 'comic', 'neon-synth', 'retro-cartoon', 'flat-vector', 'pixel-art', 'low-poly']);

export const faceFor = (style: string): Face => (CONDENSED_STYLES.has(style) ? CONDENSED : SERIF);

export const LABEL = '"Montserrat", "Noto Sans Devanagari", sans-serif';

// Soft depth instead of an outline: reads on bright skies and dark rooms alike.
export const SOFT_SHADOW = '0 2px 3px rgba(0,0,0,0.45), 0 10px 36px rgba(0,0,0,0.55)';

// "Leaning Tower of Pisa: How Engineers Stopped It From Falling" -> a small kicker and the main line.
export const splitTitle = (text: string): [string, string] => {
  const m = text.match(/^(.{4,48}?)[:—–|]\s+(.{6,})$/);
  return m ? [m[1].trim(), m[2].trim()] : ['', text.trim()];
};

export const useAnimFonts = () => {
  const [handle] = useState(() => delayRender('Loading the animated video fonts'));
  useEffect(() => {
    Promise.all(['700 80px Fraunces', 'italic 600 80px Fraunces', '400 80px "Bebas Neue"', '600 30px Montserrat', '700 30px Montserrat']
      .map((f) => document.fonts.load(f)))
      .catch(() => undefined)
      .finally(() => continueRender(handle));
  }, [handle]);
};
