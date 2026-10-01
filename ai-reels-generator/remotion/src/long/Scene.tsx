import React from 'react';
import {Easing, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {type LucideIcon} from 'lucide-react';
import {iconFor} from './icon';
import {COLORS, FONT, clamp} from '../theme';
import type {Actor, Visual} from './types';

// A small animated scene: 1-4 icon "actors" act the line out on a stage (a floor line,
// shadows, speed lines), each starting at its own time (`at`, set by reelgen/sound_design.py,
// which also places the matching sounds). The idea is told by movement, not words.

const W = 1920;
const FLOOR = 700;


export const SceneView: React.FC<{v: Visual; frames: number; accent: string}> = ({v, frames, accent}) => {
  const actors = (v.actors ?? []).slice(0, 4);
  const n = Math.max(1, actors.length);
  const slot = (i: number) => (W / (n + 1)) * (i + 1);
  return (
    <div style={{position: 'absolute', inset: 0, fontFamily: FONT, color: COLORS.text}}>
      <Stage accent={accent} />
      {actors.map((a, i) => (
        <ActorView key={i} a={a} x={slot(i)} lead={{x: slot(0)}} frames={frames} accent={accent} size={n > 2 ? 230 : 290} />
      ))}
      {v.headline ? (
        <div style={{position: 'absolute', top: 100, width: W, textAlign: 'center', fontSize: 58, fontWeight: 900, opacity: 0.95}}>{v.headline}</div>
      ) : null}
    </div>
  );
};

const Stage: React.FC<{accent: string}> = ({accent}) => {
  const frame = useCurrentFrame();
  return (
    <>
      <div style={{position: 'absolute', left: 0, right: 0, top: FLOOR, height: 3, background: `linear-gradient(90deg, transparent, ${accent}88, transparent)`}} />
      <div style={{position: 'absolute', left: 0, right: 0, top: FLOOR, bottom: 0, background: 'linear-gradient(180deg, rgba(255,255,255,0.05), transparent 60%)'}} />
      {[0, 1, 2, 3, 4, 5, 6, 7].map((k) => (
        <div
          key={k}
          style={{
            position: 'absolute',
            left: `${(k * 13 + frame * 0.08 * (1 + (k % 3))) % 100}%`,
            top: 180 + ((k * 97) % 420),
            width: 6,
            height: 6,
            borderRadius: 3,
            background: accent,
            opacity: 0.25 + 0.2 * Math.sin(frame / 15 + k),
          }}
        />
      ))}
    </>
  );
};

const ActorView: React.FC<{a: Actor; x: number; lead: {x: number}; frames: number; accent: string; size: number}> = ({a, x, lead, frames, accent, size}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const start = Math.round(a.at * fps);
  const local = frame - start;
  const Icon = iconFor(a.icon);
  const e = spring({frame: local, fps, config: {damping: 11, mass: 0.7}});
  const p = (d: number) => interpolate(local, [0, d * fps], [0, 1], {...clamp, easing: Easing.inOut(Easing.cubic)});
  const idle = Math.sin(frame / 9) * 6;
  let dx = 0;
  let dy = 0;
  let scale = 1;
  let rot = 0;
  let opacity = local < 0 ? 0 : 1;
  let lines = 0; // speed lines strength
  let copies = 0;
  let orbitAngle: number | null = null;
  switch (a.action) {
    case 'enter-left':
    case 'enter-right': {
      const dir = a.action === 'enter-left' ? -1 : 1;
      dx = dir * (1 - e) * 1100;
      lines = Math.max(0, 1 - e) * 1.5;
      dy = idle;
      opacity = local < 0 ? 0 : 1;
      break;
    }
    case 'drop-in': {
      const s = spring({frame: local, fps, config: {damping: 7, mass: 0.9}});
      dy = (1 - s) * -900;
      scale = 1 + Math.max(0, 1 - Math.abs(s - 1) * 8) * 0.0;
      break;
    }
    case 'rise':
      dy = (1 - e) * 600 + idle;
      break;
    case 'walk-across': {
      const w = p(Math.max(1, frames / fps - a.at - 0.3));
      dx = -700 + 1400 * w - (x - W / 2);
      dy = -Math.abs(Math.sin(frame / 4)) * 22;
      rot = Math.sin(frame / 4) * 4;
      break;
    }
    case 'approach':
      scale = interpolate(p(1.6), [0, 1], [0.55, 1.7]);
      dy = idle;
      break;
    case 'flee': {
      const f = p(0.8);
      dx = f * 1400;
      rot = f * 12;
      lines = f > 0 && f < 1 ? 1.5 : 0;
      break;
    }
    case 'shake':
      dx = local > 0 ? Math.sin(frame * 2.6) * 14 : 0;
      rot = local > 0 ? Math.sin(frame * 1.9) * 5 : 0;
      break;
    case 'pulse':
      scale = 1 + (local > 0 ? 0.16 * Math.max(0, Math.sin((local / fps) * Math.PI * 2.2)) ** 3 : 0);
      break;
    case 'spin':
      rot = p(1.0) * 360;
      break;
    case 'fall': {
      const f = interpolate(local, [0, 0.5 * fps], [0, 1], {...clamp, easing: Easing.in(Easing.quad)});
      rot = f * 28; // tips and drops; a symbol turned sideways (₹, $) stops being readable
      dy = f * 170;
      scale = 1 - 0.12 * f;
      break;
    }
    case 'grow':
      scale = interpolate(spring({frame: local, fps, config: {damping: 9, mass: 1}}), [0, 1], [1, 1.9]);
      break;
    case 'shrink':
      scale = interpolate(p(0.9), [0, 1], [1, 0.45]);
      break;
    case 'orbit':
      orbitAngle = (local / fps) * Math.PI * 1.4;
      break;
    case 'multiply':
      copies = Math.min(6, Math.floor(Math.max(0, local) / 4));
      break;
  }
  if (a.action !== 'enter-left' && a.action !== 'enter-right' && a.action !== 'drop-in' && a.action !== 'rise' && local >= 0) {
    // everyone else pops in at their time
    scale *= Math.min(1, e * 1.05);
  }
  let ax = x + dx;
  let ay = FLOOR - size / 2 - 30 + dy;
  if (orbitAngle !== null) {
    ax = lead.x + Math.cos(orbitAngle) * 330;
    ay = FLOOR - size / 2 - 60 + Math.sin(orbitAngle) * 120;
  }
  const disc = (px: number, py: number, s: number, key?: number, alpha = 1) => (
    <div
      key={key}
      style={{
        position: 'absolute',
        left: px - (size * s) / 2,
        top: py - (size * s) / 2,
        width: size * s,
        height: size * s,
        opacity: opacity * alpha,
        transform: `rotate(${rot}deg)`,
        filter: `drop-shadow(0 0 22px ${accent}66)`,
      }}
    >
      <Icon size={size * s} color={COLORS.text} strokeWidth={1.6} />
    </div>
  );
  return (
    <>
      {/* shadow on the floor */}
      <div
        style={{
          position: 'absolute',
          left: ax - size * 0.4 * scale,
          top: FLOOR - 12,
          width: size * 0.8 * scale,
          height: 24,
          borderRadius: '50%',
          background: 'rgba(0,0,0,0.45)',
          opacity: opacity * interpolate(ay, [FLOOR - size - 400, FLOOR - size / 2], [0.2, 1], clamp),
          filter: 'blur(6px)',
        }}
      />
      {lines > 0
        ? [0, 1, 2].map((k) => (
            <div key={k} style={{position: 'absolute', left: ax - size * 1.3, top: ay - 60 + k * 60, width: size * 0.9 * lines, height: 6, borderRadius: 3, background: `${accent}AA`}} />
          ))
        : null}
      {Array.from({length: copies}, (_, k) => {
        const ang = (k / 6) * Math.PI * 2;
        return disc(ax + Math.cos(ang) * 260, ay + Math.sin(ang) * 120, 0.55, k, 0.8);
      })}
      {disc(ax, ay, scale)}
      {a.label ? (
        <div style={{position: 'absolute', left: ax - 300, width: 600, top: FLOOR + 30, textAlign: 'center', fontSize: 40, fontWeight: 800, opacity: opacity * Math.min(1, e)}}>
          {a.label}
        </div>
      ) : null}
    </>
  );
};
