import '@fontsource/vt323/400.css';
import '@fontsource/silkscreen/400.css';
import '@fontsource/anton/400.css';
import '@fontsource/special-elite/400.css';
import React, {useEffect, useState} from 'react';
import {Easing, continueRender, delayRender, interpolate, random, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {clamp, formatNumber, parseNumber} from '../theme';
import {BOX} from '../long/box';
import type {HookShot} from '../long/types';

// Two hook templates that draw the whole screen themselves (reelgen/cinehook.py SCREEN_TEMPLATES), from the user's
// reference hooks of a news-explainer channel, taken as a style and not copied:
//   bulletin:  a green phosphor terminal: a numbered bulletin tag, the shot's words typed in or its number counted up
//              in big pixel digits, its status flashed in an inverse block, a scan of lit cells, the source at the foot;
//   frontpage: a newspaper front page: the shot's headline in heavy condensed capitals on stained paper, columns of
//              text below, a typed caption strip; the first page spins in, the next ones slide over it.
// No AI picture is drawn for these: the screen is the picture.

export const useScreenFonts = () => {
  const [handle] = useState(() => delayRender('Loading the hook screen fonts'));
  useEffect(() => {
    Promise.all(['400 60px VT323', '400 60px Silkscreen', '400 60px Anton', '400 30px "Special Elite"'].map((f) => document.fonts.load(f)))
      .catch(() => undefined).finally(() => continueRender(handle));
  }, [handle]);
};

const words = (s: HookShot) => (s.text || (s.words ?? []).map((w) => w.text).join(' ')).trim();
const numeric = (t: string) => /\d/.test(t) && t.replace(/[^\p{L}\p{N}]/gu, '').length <= 9 && parseNumber(t) !== null;

// ---------- bulletin ----------

const G = '#8CFFAE';
const GLOW = `0 0 6px ${G}, 0 0 22px rgba(80,255,140,0.45)`;

// Bulletin screens (the user: 'why every slide on the hook is the same and just changes the text?'): a number gets the
// readout (counted up over a filling gauge); other lines rotate typed headline -> live log -> target scan, so no two
// lines in a row look alike. `log` = the earlier shots' words, for the live log.
export type Screen = 'headline' | 'readout' | 'log' | 'scan';
const ROTATION: Screen[] = ['headline', 'log', 'scan'];
// One screen per shot, never the same twice in a row: a number gets the readout unless the shot before had it.
export const bulletinScreens = (shots: HookShot[]): Screen[] => {
  const out: Screen[] = [];
  let k = 0;
  for (const s of shots) {
    const text = words(s);
    const prev = out[out.length - 1];
    if (numeric(text) && text.length <= 10 && prev !== 'readout') { out.push('readout'); continue; }
    let pick = ROTATION[k % ROTATION.length];
    if (pick === prev) pick = ROTATION[++k % ROTATION.length];
    k++;
    out.push(pick);
  }
  return out;
};

export const Bulletin: React.FC<{s: HookShot; i: number; n: number; frames: number; source?: string; log?: string[]; screen?: Screen}> = ({s, i, n, frames, log = [], screen: given}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const text = words(s);
  const num = numeric(text) && text.length <= 10; // '$50', '1,200+', '90%': counted up in pixel digits
  const side = BOX.V ? 60 : 130;
  const typeEnd = Math.max(8, Math.min(frames * 0.45, 3 + text.length * 1.4));
  const typed = Math.floor(interpolate(frame, [3, typeEnd], [0, text.length], clamp));
  const parsed = parseNumber(text);
  const count = interpolate(frame, [3, 3 + fps * 0.8], [0, 1], {...clamp, easing: Easing.out(Easing.cubic)});
  const shownNum = num && parsed && Math.abs(parsed.value) >= 2 ? formatNumber(parsed.value * count, parsed) : text;
  const statusAt = num ? Math.round(fps * 0.9) : typeEnd + 4;
  const flick = 0.92 + 0.08 * random(`f${frame}`);
  const cols = BOX.V ? 24 : 52, rows = BOX.V ? 12 : 10;
  const scan = interpolate(frame, [0, frames], [0, 1], clamp);
  const screen: Screen = given === 'readout' && !num ? 'headline' : given ?? (num ? 'readout' : 'headline');
  const caret = <span style={{opacity: Math.floor(frame / 8) % 2 ? 0 : 1}}>█</span>;
  const headSize = Math.min(BOX.V ? 100 : 130, Math.floor((BOX.V ? 2400 : 3600) / Math.max(1, text.length * 0.5)));
  return (
    <div style={{position: 'absolute', inset: 0, background: '#040705', overflow: 'hidden', fontFamily: 'VT323, monospace', color: G, opacity: flick}}>
      <div style={{position: 'absolute', inset: 0, background: 'radial-gradient(ellipse at 50% 45%, rgba(40,90,55,0.35) 0%, rgba(0,0,0,0) 60%)'}} />
      {/* the bulletin tag and the shots so far */}
      <div style={{position: 'absolute', left: side, right: side, top: BOX.V ? 280 : 70, display: 'flex', alignItems: 'center', justifyContent: 'space-between'}}>
        <div style={{display: 'flex', alignItems: 'center', gap: 22}}>
          <span style={{fontSize: 46, opacity: 0.7, textShadow: GLOW}}>›</span>
          <span style={{background: G, color: '#06210F', fontSize: BOX.V ? 46 : 54, padding: '0 18px', boxShadow: `0 0 18px rgba(80,255,140,0.5)`}}>
            BULLETIN {String(i + 1).padStart(2, '0')}
          </span>
        </div>
        <div style={{display: 'flex', gap: 10}}>
          {Array.from({length: n}, (_, k) => (
            <span key={k} style={{width: 24, height: 24, border: `2px solid ${G}`, background: k <= i ? 'rgba(140,255,174,0.65)' : 'transparent',
              boxShadow: k <= i ? GLOW : 'none', opacity: k <= i ? 1 : 0.5}} />
          ))}
        </div>
      </div>
      <div style={{position: 'absolute', left: side, right: side, top: BOX.V ? 360 : 150, borderTop: `2px dashed rgba(140,255,174,0.35)`}} />
      {screen === 'readout' ? (
        // the number counted up, a gauge filling under it
        <div style={{position: 'absolute', left: side, right: side, top: BOX.V ? 420 : 200, display: 'flex', flexDirection: 'column', gap: 30}}>
          <div style={{fontSize: 34, letterSpacing: '0.2em', opacity: 0.7}}>{'>'} READOUT</div>
          <div style={{fontFamily: 'Silkscreen, monospace', fontSize: Math.min(BOX.V ? 240 : 280, Math.floor((BOX.V ? 940 : 1600) / Math.max(1, text.length * 0.95))),
            lineHeight: 1, textShadow: GLOW, filter: 'blur(0.6px)'}}>{shownNum}</div>
          <div style={{display: 'flex', gap: 6}}>
            {Array.from({length: 30}, (_, k) => (
              <span key={k} style={{flex: 1, height: 26, background: k / 30 < count ? G : 'rgba(140,255,174,0.1)', boxShadow: k / 30 < count ? GLOW : 'none'}} />
            ))}
          </div>
          {s.kicker && frame >= statusAt ? <Kicker text={s.kicker} age={frame - statusAt} /> : null}
        </div>
      ) : screen === 'log' ? (
        // a live log: the earlier lines scrolled up and dimmed, this one typed in at the bottom, flagged NEW
        <div style={{position: 'absolute', left: side, right: side, top: BOX.V ? 420 : 190, display: 'flex', flexDirection: 'column', gap: 18}}>
          <div style={{fontSize: 34, letterSpacing: '0.2em', opacity: 0.7}}>{'>'} LIVE FEED</div>
          {log.slice(-3).map((l, k, all) => (
            <div key={k} style={{fontSize: BOX.V ? 40 : 46, opacity: 0.28 + 0.12 * k, textTransform: 'uppercase', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
              transform: `translateY(${interpolate(frame, [0, 8], [24, 0], clamp)}px)`}}>
              [{String(i - all.length + k + 1).padStart(2, '0')}] {l}
            </div>
          ))}
          <div style={{display: 'flex', alignItems: 'baseline', gap: 22}}>
            <span style={{background: G, color: '#06210F', fontSize: 40, padding: '0 12px', opacity: Math.floor(frame / 10) % 2 ? 0.55 : 1}}>NEW</span>
            <span style={{fontSize: Math.min(headSize, BOX.V ? 80 : 104), lineHeight: 1.04, textTransform: 'uppercase', textShadow: GLOW}}>{text.slice(0, typed)}{caret}</span>
          </div>
          {s.kicker && frame >= statusAt ? <Kicker text={s.kicker} age={frame - statusAt} /> : null}
        </div>
      ) : screen === 'scan' ? (
        // a radar sweep on one side, the words locked in a target box on the other
        <div style={{position: 'absolute', left: side, right: side, top: BOX.V ? 420 : 190, display: 'flex', flexDirection: BOX.V ? 'column' : 'row', gap: 60, alignItems: BOX.V ? 'flex-start' : 'center'}}>
          <svg width={BOX.V ? 420 : 460} height={BOX.V ? 420 : 460} viewBox="-100 -100 200 200" style={{flex: 'none', filter: 'drop-shadow(0 0 6px rgba(80,255,140,0.6))'}}>
            {[90, 62, 34].map((r) => <circle key={r} r={r} fill="none" stroke={G} strokeOpacity={0.35} strokeWidth={1.2} />)}
            <path d="M-95,0 L95,0 M0,-95 L0,95" stroke={G} strokeOpacity={0.25} strokeWidth={1} />
            <g transform={`rotate(${frame * 6})`}><path d="M0,0 L90,0 A90,90 0 0,0 63.6,-63.6 Z" fill={G} fillOpacity={0.18} /><line x1={0} y1={0} x2={90} y2={0} stroke={G} strokeWidth={2} /></g>
            {[0, 1, 2].map((k) => <circle key={k} cx={Math.cos(k * 2.1 + i) * (30 + k * 20)} cy={Math.sin(k * 2.1 + i) * (30 + k * 20)} r={4} fill={G} opacity={0.5 + 0.5 * Math.sin(frame / 5 + k)} />)}
          </svg>
          <div style={{position: 'relative', padding: '26px 34px'}}>
            {/* target corners closing in on the words */}
            {[[0, 0], [1, 0], [0, 1], [1, 1]].map(([x, y]) => {
              const close = interpolate(frame, [0, 12], [40, 0], clamp);
              return <span key={`${x}${y}`} style={{position: 'absolute', width: 34, height: 34, [x ? 'right' : 'left']: -close, [y ? 'bottom' : 'top']: -close,
                borderColor: G, borderStyle: 'solid', borderWidth: `${y ? 0 : 4}px ${x ? 4 : 0}px ${y ? 4 : 0}px ${x ? 0 : 4}px`}} />;
            })}
            <div style={{fontSize: 30, letterSpacing: '0.2em', opacity: 0.7, marginBottom: 12}}>{frame > 12 ? 'TARGET LOCKED' : 'SCANNING…'}</div>
            <div style={{fontSize: Math.min(headSize, BOX.V ? 86 : 110), lineHeight: 1.04, textTransform: 'uppercase', textShadow: GLOW, maxWidth: BOX.V ? 900 : 1000}}>
              {text.slice(0, typed)}{caret}
            </div>
          </div>
          {s.kicker && frame >= statusAt ? <div style={{position: 'absolute', left: 0, top: BOX.V ? 900 : 520}}><Kicker text={s.kicker} age={frame - statusAt} /></div> : null}
        </div>
      ) : (
        // the typed headline (the first screen)
        <div style={{position: 'absolute', left: side, right: side, top: BOX.V ? 420 : 210, display: 'flex', flexDirection: 'column', gap: 26}}>
          <div style={{fontSize: headSize, lineHeight: 1.02, textTransform: 'uppercase', textShadow: GLOW, maxWidth: BOX.V ? 960 : 1600}}>
            {text.slice(0, typed)}{caret}
          </div>
          {s.kicker && frame >= statusAt ? <Kicker text={s.kicker} age={frame - statusAt} /> : null}
        </div>
      )}
      {/* a scan of cells under the words */}
      <div style={{display: screen === 'headline' ? 'grid' : 'none', position: 'absolute', left: side, right: side, bottom: BOX.V ? 640 : 190, gridTemplateColumns: `repeat(${cols}, 1fr)`, gap: 6, opacity: 0.85}}>
        {Array.from({length: cols * rows}, (_, k) => {
          const col = k % cols;
          const on = random(`c${i}-${k}`) < 0.07 && col / cols < scan * 1.6;
          return <span key={k} style={{height: BOX.V ? 14 : 12, background: on ? G : 'rgba(140,255,174,0.1)', boxShadow: on ? GLOW : 'none'}} />;
        })}
      </div>
      <div style={{position: 'absolute', left: side, right: side, bottom: BOX.V ? 590 : 120, borderTop: '1px solid rgba(140,255,174,0.35)'}} />
      {/* the tube: scanlines, a rolling band, the dark corners */}
      <div style={{position: 'absolute', inset: 0, backgroundImage: 'repeating-linear-gradient(0deg, rgba(0,0,0,0.38) 0px, rgba(0,0,0,0.38) 2px, transparent 2px, transparent 4px)'}} />
      <div style={{position: 'absolute', left: 0, right: 0, height: 180, top: `${((frame * 6) % (BOX.H + 360)) - 180}px`,
        background: 'linear-gradient(transparent, rgba(140,255,174,0.05), transparent)'}} />
      <div style={{position: 'absolute', inset: 0, background: 'radial-gradient(ellipse at center, transparent 55%, rgba(0,0,0,0.85) 100%)'}} />
    </div>
  );
};

// a status flashed in an inverse block
const Kicker: React.FC<{text: string; age: number}> = ({text, age}) => (
  <div style={{alignSelf: 'flex-start', background: G, color: '#06210F', fontSize: BOX.V ? 52 : 66, padding: '2px 20px', textTransform: 'uppercase',
    boxShadow: '0 0 26px rgba(80,255,140,0.55)', opacity: age < 6 ? (Math.floor(age / 2) % 2 ? 0.2 : 1) : 1}}>{text}</div>
);

// ---------- front page ----------

const PAPER = `url("data:image/svg+xml;utf8,${encodeURIComponent(
  `<svg xmlns="http://www.w3.org/2000/svg" width="300" height="300"><filter id="n"><feTurbulence type="fractalNoise" baseFrequency="0.7" numOctaves="3" stitchTiles="stitch"/><feColorMatrix type="saturate" values="0"/></filter><rect width="300" height="300" filter="url(#n)" opacity="0.5"/></svg>`,
)}")`;

export const FrontPage: React.FC<{s: HookShot; i: number; frames: number}> = ({s, i, frames}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const head = words(s).toUpperCase();
  const spin = i === 0 ? spring({frame, fps, config: {damping: 16, mass: 0.9}, durationInFrames: Math.round(fps * 0.8)}) : 1;
  const slide = i === 0 ? 0 : interpolate(frame, [0, 8], [1, 0], {...clamp, easing: Easing.out(Easing.cubic)});
  const push = interpolate(frame, [0, frames], [1, 1.06], clamp);
  const tilt = (random(`p${i}`) - 0.5) * 2.4;
  const W = BOX.V ? 1000 : 1800;
  const size = Math.min(BOX.V ? 190 : 230, Math.floor((W * 2.9) / Math.max(6, head.length * 0.56)), Math.floor(W / (Math.max(...head.split(/\s+/).map((w) => w.length), 1) * 0.6)));
  const cap = s.kicker ? interpolate(frame, [Math.round(fps * 0.5), Math.round(fps * 0.5) + 8], [0, 1], clamp) : 0;
  const specks = Array.from({length: 26}, (_, k) => [random(`sx${i}${k}`), random(`sy${i}${k}`), random(`ss${i}${k}`)]);
  return (
    <div style={{position: 'absolute', inset: 0, background: '#16130F', overflow: 'hidden'}}>
      <div style={{position: 'absolute', inset: BOX.V ? '200px -20px' : '-20px', transformOrigin: '50% 45%',
        transform: `translateX(${slide * 110}%) rotate(${(1 - spin) * 720 + tilt}deg) scale(${(0.1 + 0.9 * spin) * push})`,
        background: '#D8D0BF', backgroundImage: `${PAPER}, radial-gradient(ellipse at 18% 22%, rgba(150,110,60,0.28), transparent 22%), radial-gradient(ellipse at 78% 66%, rgba(140,100,50,0.22), transparent 26%), radial-gradient(ellipse at 50% 50%, transparent 60%, rgba(90,70,40,0.35) 100%)`,
        backgroundBlendMode: 'multiply', boxShadow: '0 40px 120px rgba(0,0,0,0.7)'}}>
        <div style={{position: 'absolute', left: '5%', right: '5%', top: BOX.V ? 60 : 50, borderTop: '6px solid #2A241E', borderBottom: '2px solid #2A241E', height: 10}} />
        <div style={{position: 'absolute', left: '5%', right: '5%', top: BOX.V ? 90 : 76, bottom: BOX.V ? '38%' : '24%', display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
          <div style={{fontFamily: 'Anton, sans-serif', fontSize: size, lineHeight: 1.0, color: '#2A241E', textAlign: 'center', textWrap: 'balance',
            letterSpacing: '0.01em', filter: 'blur(0.4px)', textShadow: '0 0 1px rgba(42,36,30,0.6)'}}>{head}</div>
        </div>
        <div style={{position: 'absolute', left: '5%', right: '5%', bottom: BOX.V ? '36%' : '22%', borderTop: '2px solid #2A241E', borderBottom: '6px solid #2A241E', height: 10}} />
        <div style={{position: 'absolute', left: '5%', right: '5%', bottom: BOX.V ? '6%' : -40, height: BOX.V ? '28%' : '20%', display: 'flex', gap: 30}}>
          {Array.from({length: BOX.V ? 3 : 5}, (_, c) => (
            <div key={c} style={{flex: 1, display: 'flex', flexDirection: 'column', gap: 14, borderRight: c < (BOX.V ? 2 : 4) ? '2px solid rgba(42,36,30,0.35)' : undefined, paddingRight: 24}}>
              {Array.from({length: 9}, (_, r) => <span key={r} style={{height: 9, width: `${70 + random(`l${i}${c}${r}`) * 30}%`, background: 'rgba(60,52,44,0.55)'}} />)}
            </div>
          ))}
        </div>
        {specks.map(([x, y, z], k) => <span key={k} style={{position: 'absolute', left: `${x * 100}%`, top: `${y * 100}%`, width: 3 + z * 6, height: 3 + z * 6, borderRadius: '50%', background: 'rgba(40,30,20,0.55)'}} />)}
        {s.kicker ? (
          <div style={{position: 'absolute', right: BOX.V ? '6%' : '16%', bottom: BOX.V ? '33%' : '17%', padding: '8px 22px', background: '#EEE6D2', boxShadow: '0 6px 18px rgba(0,0,0,0.35)',
            fontFamily: '"Special Elite", monospace', fontSize: BOX.V ? 34 : 38, color: '#2A241E', transform: `rotate(-1.5deg) translateY(${(1 - cap) * 20}px)`, opacity: cap}}>
            {s.kicker}
          </div>
        ) : null}
      </div>
    </div>
  );
};
