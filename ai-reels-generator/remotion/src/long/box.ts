// The frame the long-video visuals lay themselves out in: 16:9 for long videos, 9:16 for the Shorts Studio's
// motion-graphics Shorts (reelgen/storyshorts.py, props.vertical). Long sets it once per render, before any
// visual draws (one render is always one size), so every template reads its margins from here.
export type Box = {V: boolean; W: number; H: number; SIDE: number; INNER: number; TOP: number; BOTTOM: number; FLOOR: number};

const WIDE: Box = {V: false, W: 1920, H: 1080, SIDE: 170, INNER: 1580, TOP: 110, BOTTOM: 820, FLOOR: 700};
// 9:16: the Shorts title bar covers the top ~250 px, the caption, channel and buttons the bottom ~450.
// Visuals end at 1260 so the subtitles (bottom 470) never cover them; with subtitles off they move down a little.
const TALL: Box = {V: true, W: 1080, H: 1920, SIDE: 70, INNER: 940, TOP: 300, BOTTOM: 1260, FLOOR: 1100};

export const BOX: Box = {...WIDE};
export const setBox = (vertical?: boolean) => {
  Object.assign(BOX, vertical ? TALL : WIDE);
};
