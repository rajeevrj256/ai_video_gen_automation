import {icons, type LucideIcon} from 'lucide-react';

// Claude names icons in lucide's kebab-case ("cloud-rain"), sometimes by an older or looser
// name ("trash-2", "circle-help", "help-circle"). Find the closest real icon instead of
// falling back to a generic one: exact name, without a trailing number, with common
// synonyms, words reordered, then any icon containing all (or the main) words.

const ALL = icons as Record<string, LucideIcon>;
const KEYS = Object.keys(ALL);
const SYNONYMS: Record<string, string> = {help: 'question-mark', question: 'question-mark', dollar: 'dollar-sign', money: 'banknote', person: 'user', people: 'users', warning: 'triangle-alert', alert: 'triangle-alert', delete: 'trash', bin: 'trash', danger: 'skull', love: 'heart', time: 'clock', world: 'globe', earth: 'earth', doctor: 'stethoscope', medicine: 'pill', lab: 'flask-conical', science: 'flask-conical', car: 'car', gun: 'crosshair', war: 'swords', soldier: 'shield'};
const cache = new Map<string, LucideIcon>();

const pascal = (words: string[]) => words.map((w) => w[0].toUpperCase() + w.slice(1)).join('');

export const iconFor = (name: string): LucideIcon => {
  const key = name.trim().toLowerCase();
  const hit = cache.get(key);
  if (hit) return hit;
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
    const main = [...words].sort((a, b) => b.length - a.length)[0];
    const some = KEYS.filter((k) => has(k, main)).sort((a, b) => a.length - b.length);
    found = ALL[all[0] ?? some[0]];
  }
  const icon = found ?? ALL.Sparkles;
  cache.set(key, icon);
  return icon;
};
