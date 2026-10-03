import React from 'react';
import SETS from './sets.json';
import type {Piece, Setting} from './types';

// Furniture is data, not part of a set's drawing: each scene lists its pieces (kind, x, width), the
// writer can arrange them per scene, and sitting or putting things down follows from the data: a
// figure that sits uses the seat at its x (or gets a stool), an object stands on the surface at its x
// (or gets a table). sets.json holds the kinds, their heights and each setting's usual pieces; the
// Python side reads the same file. A new kind needs an entry there and a drawing below.

const INK = '#161616';
const GREY = '#B4B4B4';
const DARK = '#9C9C9C';
const LIGHT = '#E4E4E4';
const SET_LINE = 4.5;
const ink = {stroke: INK, strokeWidth: SET_LINE, strokeLinejoin: 'round' as const, strokeLinecap: 'round' as const};

type Kind = {seat?: number; surface?: number; about: string};
const KINDS = SETS.furniture as Record<string, Kind>;
const SPOTS = SETS.spots as Record<string, number>;
export const STOOL_SEAT = 130;
export const TABLE_TOP = 150;

// The usual pieces of a setting, for scenes (and older videos) that list none.
export const defaultFurniture = (setting: Setting): Piece[] =>
  ((SETS.defaults as Record<string, {kind: string; spot: string; seats: number}[]>)[setting] ?? []).map((p) => ({
    kind: p.kind,
    x: SPOTS[p.spot] ?? 960,
    width: widthOf(p.kind, p.seats, SETS.spacing),
  }));

export const widthOf = (kind: string, seats: number, spacing: number) => {
  const one = {sofa: 300, bench: 300, bed: 380, counter: 360, 'shop-counter': 300, 'work-desk': 300, table: 260, desk: 260}[kind] ?? 0;
  if (!one) return {armchair: 230, chair: 160, stool: 160, washbasin: 240, tv: 260, plant: 140}[kind] ?? 200;
  return Math.max(one, (Math.max(1, seats) - 1) * spacing + one);
};

const within = (p: Piece, x: number) => Math.abs(x - p.x) <= p.width / 2 - 20;
export const seatAt = (pieces: Piece[], x: number) => {
  const p = pieces.find((q) => KINDS[q.kind]?.seat && within(q, x));
  return p ? KINDS[p.kind].seat! : null;
};
export const surfaceAt = (pieces: Piece[], x: number) => {
  const p = pieces.find((q) => KINDS[q.kind]?.surface && within(q, x));
  return p ? KINDS[p.kind].surface! : null;
};

export const Stool: React.FC<{x: number; floor: number}> = ({x, floor}) => (
  <g>
    <line x1={x - 52} y1={floor - STOOL_SEAT + 10} x2={x - 62} y2={floor} {...ink} />
    <line x1={x + 52} y1={floor - STOOL_SEAT + 10} x2={x + 62} y2={floor} {...ink} />
    <rect x={x - 80} y={floor - STOOL_SEAT - 6} width={160} height={22} rx={8} fill={GREY} {...ink} />
  </g>
);

export const TableUnder: React.FC<{x: number; floor: number}> = ({x, floor}) => (
  <g>
    <line x1={x - 90} y1={floor - TABLE_TOP + 14} x2={x - 90} y2={floor} {...ink} />
    <line x1={x + 90} y1={floor - TABLE_TOP + 14} x2={x + 90} y2={floor} {...ink} />
    <rect x={x - 120} y={floor - TABLE_TOP - 4} width={240} height={20} rx={6} fill={GREY} {...ink} />
  </g>
);

const legs = (l: number, r: number, from: number, floor: number) => (
  <>
    <line x1={l} y1={from} x2={l} y2={floor} {...ink} />
    <line x1={r} y1={from} x2={r} y2={floor} {...ink} />
  </>
);

export const PieceView: React.FC<{p: Piece; floor: number}> = ({p, floor}) => {
  const k = KINDS[p.kind];
  const l = p.x - p.width / 2;
  const r = p.x + p.width / 2;
  const top = floor - (k?.surface ?? k?.seat ?? 0);
  switch (p.kind) {
    case 'sofa':
    case 'armchair': {
      const arm = 90;
      const n = p.kind === 'sofa' ? Math.max(1, Math.round((p.width - 2 * arm) / 280)) : 1;
      const inner = [l + arm, r - arm];
      const step = (inner[1] - inner[0]) / n;
      return (
        <g>
          <rect x={l + 20} y={top - 200} width={p.width - 40} height={230} rx={34} fill={GREY} {...ink} />
          {Array.from({length: n - 1}, (_, i) => (
            <line key={i} x1={inner[0] + step * (i + 1)} y1={top - 182} x2={inner[0] + step * (i + 1)} y2={top - 6} {...ink} />
          ))}
          <rect x={inner[0] - 6} y={top - 12} width={inner[1] - inner[0] + 12} height={44} rx={14} fill={LIGHT} {...ink} />
          <rect x={inner[0]} y={top + 32} width={inner[1] - inner[0]} height={floor - top - 60} fill={DARK} {...ink} />
          <rect x={l} y={top - 100} width={arm + 10} height={floor - top + 70} rx={26} fill={GREY} {...ink} />
          <rect x={r - arm - 10} y={top - 100} width={arm + 10} height={floor - top + 70} rx={26} fill={GREY} {...ink} />
          {[l + 30, r - 30].map((x) => <line key={x} x1={x} y1={floor - 30} x2={x} y2={floor} {...ink} strokeWidth={SET_LINE + 3} />)}
        </g>
      );
    }
    case 'chair':
      return (
        <g>
          <rect x={l + 10} y={top - 170} width={p.width - 20} height={150} rx={14} fill={GREY} {...ink} />
          {legs(l + 18, r - 18, top + 10, floor)}
          <rect x={l} y={top - 6} width={p.width} height={22} rx={8} fill={GREY} {...ink} />
        </g>
      );
    case 'stool':
      return <Stool x={p.x} floor={floor} />;
    case 'bench':
      return (
        <g>
          <rect x={l} y={top - 92} width={p.width} height={24} fill={DARK} {...ink} />
          {legs(l + 30, r - 30, top + 20, floor)}
          <rect x={l} y={top - 6} width={p.width} height={28} fill={DARK} {...ink} />
        </g>
      );
    case 'bed':
      return (
        <g>
          <rect x={l} y={top - 140} width={60} height={floor - top + 140} rx={14} fill={GREY} {...ink} />
          <rect x={l} y={top} width={p.width} height={110} rx={16} fill={LIGHT} {...ink} />
          <rect x={l + 70} y={top - 30} width={140} height={40} rx={18} fill="#fff" {...ink} />
          {legs(l + 30, r - 30, top + 110, floor)}
        </g>
      );
    case 'desk':
    case 'table':
      return (
        <g>
          <rect x={l} y={top} width={p.width} height={30} fill={GREY} {...ink} />
          {legs(l + 20, r - 20, top + 30, floor)}
        </g>
      );
    case 'work-desk':
      return (
        <g>
          <rect x={l} y={top} width={p.width} height={40} fill={GREY} {...ink} />
          {legs(l + 30, r - 30, top + 40, floor)}
          <rect x={p.x - 120} y={top - 180} width={240} height={160} rx={8} fill={DARK} {...ink} />
          <line x1={p.x} y1={top - 20} x2={p.x} y2={top} {...ink} />
        </g>
      );
    case 'counter':
      return (
        <g>
          <rect x={l} y={top} width={p.width} height={floor - top} fill={GREY} {...ink} />
          <rect x={p.x - 160} y={top} width={320} height={40} fill={LIGHT} {...ink} />
          <path d={`M ${p.x + 10} ${top} v -70 h 60 v 20`} fill="none" {...ink} />
        </g>
      );
    case 'shop-counter':
      return <rect x={l} y={top} width={p.width} height={floor - top} fill={GREY} {...ink} />;
    case 'washbasin':
      return (
        <g>
          <rect x={l} y={top} width={p.width} height={60} fill={LIGHT} {...ink} />
          <path d={`M ${p.x} ${top} v -50 h 40 v 16`} fill="none" {...ink} />
          <line x1={p.x} y1={top + 60} x2={p.x} y2={floor} {...ink} />
        </g>
      );
    case 'tv':
      return (
        <g>
          <rect x={l + 20} y={floor - 120} width={p.width - 40} height={120} fill={GREY} {...ink} />
          <rect x={l} y={floor - 300} width={p.width} height={170} rx={8} fill={DARK} {...ink} />
        </g>
      );
    case 'plant':
      return (
        <g>
          <path d={`M ${p.x - 50} ${floor - 110} h 100 l -14 110 h -72 Z`} fill={GREY} {...ink} />
          {[-1, 0, 1].map((s) => (
            <ellipse key={s} cx={p.x + s * 34} cy={floor - 170 - (s ? 0 : 30)} rx={30} ry={64} transform={`rotate(${s * 24} ${p.x + s * 34} ${floor - 170})`} fill={DARK} {...ink} />
          ))}
        </g>
      );
    default:
      return null;
  }
};
