import type {CaptionGroup} from '../types';
import type {Beat, Chapter, LongProps, Visual} from './types';

// Demo props for the Studio and `remotion still ... Long`: every visual type once,
// with made-up timings (no audio). The real props come from reelgen/longform.py.

const v = (type: Visual['type'], headline: string, sub = '', items: Visual['items'] = [], icons: string[] = []): Visual => ({type, headline, sub, items, icons});
const it = (label: string, text = '', value = 0, display = '') => ({label, text, value, display});

const SCRIPT: {chapter: number; text: string; visual: Visual}[] = [
  {chapter: 0, text: 'Do you know why one-day cricket exists at all?', visual: v('title', 'Why does one-day cricket exist?', 'The answer starts with three days of rain')},
  {chapter: 0, text: 'It began with a match nobody planned.', visual: v('icons', 'A match nobody planned', '', [], ['cloud-rain', 'calendar-x', 'ticket'])},
  {chapter: 1, text: 'Melbourne, the fifth of January, nineteen seventy-one.', visual: v('keyword', 'Melbourne, 1971')},
  {chapter: 1, text: 'Three days of an Ashes Test were washed out.', visual: v('stat', '3 days', 'of a five-day Test lost to rain')},
  {chapter: 1, text: 'So officials planned a forty-over game to save the gate money.', visual: v('steps', 'What officials did', '', [it('Test abandoned', 'rain, day after day'), it('Extra game', '40 eight-ball overs'), it('Tickets sold', 'to recover losses')])},
  {chapter: 2, text: 'They hoped for twenty thousand people. Forty-six thousand came.', visual: v('compare', 'More than double', '', [it('Expected', '', 20000, '20,000'), it('Turned up', '', 46000, '46,000')])},
  {chapter: 2, text: 'Four years later came the first men’s World Cup.', visual: v('timeline', 'From washout to World Cup', '', [it('1963', 'English one-day cup'), it('1971', 'First ODI'), it('1975', 'Men’s World Cup')])},
  {chapter: 2, text: 'As one writer put it, the rain gave cricket its future.', visual: v('quote', 'The rain gave cricket its future', 'A cricket writer (demo)')},
  {chapter: 2, text: 'ODIs played each year kept climbing.', visual: v('chart', 'ODIs per year', '(demo numbers)', [it('1975', '', 18, '18'), it('1985', '', 56, '56'), it('1995', '', 79, '79'), it('2005', '', 110, '110')])},
];

const SECONDS = 4.5;
const CARD = 2.2;

const build = (): LongProps => {
  const beats: Beat[] = [];
  const chapters: Chapter[] = [];
  const captions: CaptionGroup[] = [];
  let t = 0;
  let last = -1;
  for (const s of SCRIPT) {
    if (s.chapter !== last) {
      chapters.push({index: s.chapter, title: ['Intro', 'The washout', 'The crowd that changed cricket'][s.chapter], start: t, card: s.chapter === 0 ? 0 : CARD});
      if (s.chapter !== 0) t += CARD;
      last = s.chapter;
    }
    beats.push({start: t, duration: SECONDS, chapter: s.chapter, audio: null, visual: s.visual});
    const words = s.text.split(' ');
    const per = (SECONDS - 0.5) / words.length;
    captions.push({start: t + 0.2, end: t + SECONDS - 0.1, words: words.map((w, i) => ({text: w, start: t + 0.2 + i * per, end: t + 0.2 + (i + 1) * per}))});
    t += SECONDS;
  }
  return {title: 'Why one-day cricket exists', fps: 30, duration: t, chapters, beats, captions, music: null, sfx: null};
};

export const longDemoProps = build();
