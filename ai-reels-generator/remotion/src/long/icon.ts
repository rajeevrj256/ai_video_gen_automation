import {icons, type LucideIcon} from 'lucide-react';

// Claude names icons in lucide's kebab-case ("cloud-rain"), sometimes by an older or looser
// name ("trash-2", "circle-help", "help-circle"). Find the closest real icon instead of
// falling back to a generic one: exact name, without a trailing number, with common
// synonyms, words reordered, then any icon containing all (or the main) words.

const ALL = icons as Record<string, LucideIcon>;
const KEYS = Object.keys(ALL);
const SYNONYMS: Record<string, string> = {help: 'question-mark', question: 'question-mark', dollar: 'dollar-sign', money: 'banknote', person: 'user', people: 'users', warning: 'triangle-alert', alert: 'triangle-alert', delete: 'trash', bin: 'trash', danger: 'skull', love: 'heart', time: 'clock', world: 'globe', earth: 'earth', doctor: 'stethoscope', medicine: 'pill', lab: 'flask-conical', science: 'flask-conical', car: 'car', gun: 'crosshair', war: 'swords', soldier: 'shield'};
// Whole names that the word-by-word search gets wrong ("data-center" found TextAlignCenter).
const PHRASES: Record<string, string> = {
  'data-center': 'server', 'data-centre': 'server', datacenter: 'server', 'server-farm': 'server',
  'undersea-cable': 'cable', 'submarine-cable': 'cable', 'fiber-optic': 'cable', 'fibre-optic': 'cable',
  'power-plant': 'factory', 'power-grid': 'zap', 'electricity': 'zap', 'stock-market': 'chart-candlestick',
  ai: 'brain-circuit', 'artificial-intelligence': 'brain-circuit',
};
// Words that say nothing about the object; never pick an icon for them alone.
const VAGUE = new Set(['center', 'centre', 'align', 'text', 'big', 'small', 'new', 'old', 'red', 'blue', 'green', 'icon']);
const cache = new Map<string, LucideIcon>();

// Money icons follow the video's currency: a "receipt" in a rupee story must not show a $.
const CURRENCY: Record<string, Record<string, string>> = {
  rupee: {DollarSign: 'IndianRupee', CircleDollarSign: 'IndianRupee', BadgeDollarSign: 'BadgeIndianRupee', Receipt: 'ReceiptIndianRupee', ReceiptCent: 'ReceiptIndianRupee', Euro: 'IndianRupee', PoundSterling: 'IndianRupee', ReceiptEuro: 'ReceiptIndianRupee', ReceiptPoundSterling: 'ReceiptIndianRupee'},
  euro: {DollarSign: 'Euro', CircleDollarSign: 'CircleEuro', BadgeDollarSign: 'BadgeEuro', Receipt: 'ReceiptEuro'},
  pound: {DollarSign: 'PoundSterling', CircleDollarSign: 'CirclePoundSterling', BadgeDollarSign: 'BadgePoundSterling', Receipt: 'ReceiptPoundSterling'},
};
let currency = '';
export const setCurrency = (c?: string) => {
  currency = c && CURRENCY[c] ? c : '';
};
const NAME = new Map<LucideIcon, string>(KEYS.map((k) => [ALL[k], k]));
const inCurrency = (icon: LucideIcon): LucideIcon => {
  const swap = currency ? CURRENCY[currency][NAME.get(icon) ?? ''] : undefined;
  return swap ? ALL[swap] : icon;
};

const pascal = (words: string[]) => words.map((w) => w[0].toUpperCase() + w.slice(1)).join('');

export const iconFor = (name: string): LucideIcon => {
  const key = name.trim().toLowerCase();
  const hit = cache.get(key);
  if (hit) return inCurrency(hit);
  const phrase = PHRASES[key.replace(/[_\s]+/g, '-')];
  if (phrase && phrase !== key) return iconFor(phrase);
  let words = key.split(/[-_\s]+/).filter(Boolean);
  const tries: string[][] = [words, words.filter((w) => !/^\d+$/.test(w))];
  words = tries[1].flatMap((w) => (SYNONYMS[w] ?? w).split('-'));
  tries.push(words, [...words].reverse(), words.length > 1 ? [...words.slice(1), words[0]] : words);
  let found: LucideIcon | undefined;
  for (const t of tries) {
    if (t.length && ALL[pascal(t)]) {
      found = ALL[pascal(t)];
      break;
    }
  }
  if (!found && words.length) {
    const has = (k: string, w: string) => k.toLowerCase().includes(w);
    const all = KEYS.filter((k) => words.every((w) => has(k, w))).sort((a, b) => a.length - b.length);
    const main = [...words].filter((w) => !VAGUE.has(w)).sort((a, b) => b.length - a.length)[0] ?? '';
    const some = main ? KEYS.filter((k) => has(k, main)).sort((a, b) => a.length - b.length) : [];
    found = ALL[all[0] ?? some[0]];
  }
  const icon = found ?? ALL.Sparkles;
  cache.set(key, icon);
  return inCurrency(icon);
};
