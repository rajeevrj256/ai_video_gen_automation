import React from 'react';
import {Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {FONT, clamp} from '../theme';
import {BOX} from './box';

// The end of a Short made from a long video (reelgen/clipshort.py): over the outro line, the full video as a card
// (its thumbnail with a play button and its length), its title, and an arrow down to the related-video link YouTube
// shows under a Short. The card covers the frame, so the beat's own slide under it never shows.
export type EndCardInfo = {from: number; title: string; length: string; thumb: string | null};

export const EndCard: React.FC<{card: EndCardInfo; accent: string}> = ({card, accent}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const pop = spring({frame, fps, config: {damping: 14, mass: 0.6}});
  const tag = spring({frame: frame - 6, fps, config: {damping: 12}});
  const words = spring({frame: frame - 10, fps, config: {damping: 16}});
  const arrow = spring({frame: frame - 16, fps, config: {damping: 12}});
  const bob = Math.sin(frame / 5) * 14;
  const pulse = 1 + 0.06 * Math.sin(frame / 4);
  const w = BOX.V ? 960 : 1100;
  const h = Math.round((w * 9) / 16);
  const size = Math.floor(Math.min(BOX.V ? 74 : 64, (w * 2.2) / Math.max(12, card.title.length) / 0.55));
  const fade = interpolate(frame, [0, 6], [0, 1], clamp);
  return (
    <div style={{position: 'absolute', inset: 0, opacity: fade, background: '#07070b', overflow: 'hidden'}}>
      {card.thumb ? (
        <Img src={staticFile(card.thumb)} style={{position: 'absolute', inset: -60, width: 'calc(100% + 120px)', height: 'calc(100% + 120px)',
          objectFit: 'cover', filter: 'blur(38px) brightness(0.38) saturate(1.2)'}} />
      ) : null}
      <div style={{position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center',
        justifyContent: 'center', gap: BOX.V ? 46 : 30, paddingBottom: BOX.V ? 260 : 0}}>
        <div style={{display: 'flex', alignItems: 'center', gap: 16, padding: '12px 30px', borderRadius: 12, background: '#E50914',
          fontFamily: FONT, fontWeight: 900, fontSize: BOX.V ? 52 : 44, letterSpacing: 4, color: '#fff',
          transform: `translateY(${(1 - tag) * -40}px)`, opacity: Math.min(1, tag * 2)}}>
          ▶ FULL VIDEO
        </div>
        <div style={{position: 'relative', width: w, height: h, borderRadius: 26, overflow: 'hidden', background: '#111',
          border: '6px solid #fff', boxShadow: `0 30px 90px rgba(0,0,0,0.7), 0 0 0 10px ${accent}55`,
          transform: `scale(${0.7 + 0.3 * pop}) rotate(${(1 - pop) * -4}deg)`}}>
          {card.thumb ? <Img src={staticFile(card.thumb)} style={{width: '100%', height: '100%', objectFit: 'cover'}} /> : null}
          <div style={{position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
            <div style={{width: 170, height: 120, borderRadius: 34, background: '#E50914', display: 'flex', alignItems: 'center',
              justifyContent: 'center', transform: `scale(${pulse})`, boxShadow: '0 10px 40px rgba(0,0,0,0.6)'}}>
              <div style={{width: 0, height: 0, borderTop: '30px solid transparent', borderBottom: '30px solid transparent',
                borderLeft: '52px solid #fff', marginLeft: 10}} />
            </div>
          </div>
          {card.length ? (
            <div style={{position: 'absolute', right: 18, bottom: 16, padding: '6px 14px', borderRadius: 8, background: 'rgba(0,0,0,0.82)',
              fontFamily: FONT, fontWeight: 800, fontSize: 36, color: '#fff'}}>{card.length}</div>
          ) : null}
        </div>
        <div style={{maxWidth: w, textAlign: 'center', fontFamily: FONT, fontWeight: 900, fontSize: size, lineHeight: 1.12, color: '#fff',
          textShadow: '0 6px 24px rgba(0,0,0,0.8)', opacity: Math.min(1, words * 1.5), transform: `translateY(${(1 - words) * 30}px)`}}>
          {card.title}
        </div>
        <div style={{display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, opacity: Math.min(1, arrow * 1.5),
          transform: `translateY(${bob * arrow}px)`}}>
          <div style={{fontFamily: FONT, fontWeight: 900, fontSize: BOX.V ? 50 : 42, color: accent, textShadow: '0 4px 18px rgba(0,0,0,0.8)'}}>
            Watch it · link below
          </div>
          <div style={{fontFamily: FONT, fontWeight: 900, fontSize: BOX.V ? 110 : 80, lineHeight: 0.9, color: accent,
            textShadow: '0 6px 24px rgba(0,0,0,0.8)'}}>↓</div>
        </div>
      </div>
    </div>
  );
};
