// 🎭 The cast intro's last shot: an action-movie one-sheet, laid out like the user's reference ("this is real one":
// their own picture of 'The Unwritten'). Two 3D layers, as a poster is a montage, not one photograph:
// - behind (PosterScene, the video's main canvas): a stormy evening over a chase: the hero's red car with racing
//   stripes tearing toward us on a wet road with him, his sister and his best friend inside, police cars on both sides,
//   a fire raging on the left, fighter jets crossing the sky top left, a helicopter with its searchlight, a fortress on
//   a cliff, a bridge on arches and snowy mountains on the right;
// - in front (PosterBusts, its own see-through canvas): the three of them chest-up and huge, the hero in front and
//   higher, the others at his shoulders, lit warm from the fire and cold from behind, fading out into the title;
// - then the words (PosterWords): 'A LOW-POLY ACTION FILM', the title in silver with a red slash, the billing
//   'STARRING ETHAN | MIA | SAM', the tagline and a red COMING SOON. Built from the film's own cast, no picture generator.
// Picture only: the intro's score, an impact and the jets' fly-bys play under it (reelgen/lowpoly/timeline.py).
import React, {useMemo} from 'react';
import {interpolate} from 'remotion';
import {ThreeCanvas} from '@remotion/three';
import * as THREE from 'three';
import {BigModel} from './Big';
import {Man, mat} from './Man';
import {face, pose} from './poses';
import type {Design, Expr, LPShot, Poster} from './types';

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

type Plan = {pos: THREE.Vector3; look: THREE.Vector3; up: THREE.Vector3; fov: number; focus: number; aperture: number; near: number};
const planOf = (pos: [number, number, number], look: [number, number, number], fov: number): Plan => ({
  pos: new THREE.Vector3(...pos), look: new THREE.Vector3(...look), up: new THREE.Vector3(0, 1, 0), fov, focus: 6, aperture: 0, near: 0.1,
});

const rng = (seed: number) => {
  let s = seed * 9301 + 49297;
  return () => ((s = (s * 9301 + 49297) % 233280) / 233280);
};

// A stormy evening sky: deep navy overhead to a bruised blue at the horizon.
const SkyDome: React.FC<{top: string; hor: string}> = ({top, hor}) => {
  const g = useMemo(() => {
    const r = 220;
    const geo = new THREE.SphereGeometry(r, 24, 12);
    const a = new THREE.Color(top);
    const b = new THREE.Color(hor);
    const cols: number[] = [];
    const pos = geo.attributes.position;
    for (let i = 0; i < pos.count; i++) {
      const c = b.clone().lerp(a, Math.pow(Math.max(0, pos.getY(i) / r), 0.5));
      cols.push(c.r, c.g, c.b);
    }
    geo.setAttribute('color', new THREE.Float32BufferAttribute(cols, 3));
    return geo;
  }, [top, hor]);
  return (
    <mesh geometry={g}>
      <meshBasicMaterial vertexColors side={THREE.BackSide} toneMapped={false} fog={false} />
    </mesh>
  );
};

// A column of smoke climbing from the city, puffs swelling and drifting with the wind; fire glowing at its foot.
const Smoke: React.FC<{x: number; z: number; top: number; t: number; seed: number; dark?: boolean}> = ({x, z, top, t, seed, dark}) => {
  const puffs = useMemo(() => {
    const r = rng(seed);
    return Array.from({length: 16}, (_, i) => ({k: i / 15, j: r(), s: 0.8 + r() * 0.6}));
  }, [seed]);
  const flick = 0.8 + 0.2 * Math.sin(t * 17 + seed) * Math.sin(t * 5.1);
  return (
    <group position={[x, 0, z]}>
      {puffs.map((p, i) => {
        const k = (p.k + t * 0.06) % 1;
        const y = 2.5 + k * (top - 2.5);
        const r = (0.5 + k * 1.9) * p.s;
        return (
          <mesh key={i} position={[k * k * 4 + (p.j - 0.5) * 1.6, y, (p.j - 0.5) * 1.2]} scale={r}>
            <icosahedronGeometry args={[1, 0]} />
            <meshStandardMaterial color={dark ? '#3b3632' : '#6d655d'} flatShading roughness={1} transparent opacity={0.92 - k * 0.45} />
          </mesh>
        );
      })}
      <mesh position={[0, 2.4, 0]} scale={[1.0 * flick, 0.8 * flick, 0.9]}>
        <icosahedronGeometry args={[1, 0]} />
        <meshBasicMaterial color="#ff8a2a" toneMapped={false} />
      </mesh>
      <pointLight position={[0, 4, 2]} intensity={40 * flick} distance={14} color="#ff8a2a" />
    </group>
  );
};

// A fighter jet, nose along +x: fuselage, nose cone, canopy, delta wings, twin tails, the afterburner.
const wingGeo = (pts: [number, number][], depth: number) => {
  const sh = new THREE.Shape();
  sh.moveTo(...pts[0]);
  pts.slice(1).forEach((p) => sh.lineTo(...p));
  const g = new THREE.ExtrudeGeometry(sh, {depth, bevelEnabled: false});
  g.translate(0, 0, -depth / 2);
  return g;
};
const Jet: React.FC<{c: string; burn: number}> = ({c, burn}) => {
  const parts = useMemo(() => {
    const m = new THREE.MeshStandardMaterial({color: c, flatShading: true, roughness: 0.55, metalness: 0.35, side: THREE.DoubleSide});
    return {
      m,
      wing: wingGeo([[0.9, 0], [-1.1, 2.1], [-1.55, 2.1], [-1.4, 0]], 0.07),
      stab: wingGeo([[-1.2, 0], [-1.85, 0.85], [-2.1, 0.85], [-2.05, 0]], 0.05),
      fin: wingGeo([[-1.0, 0], [-1.75, 1.0], [-2.05, 1.0], [-2.05, 0]], 0.05),
    };
  }, [c]);
  return (
    <group>
      <mesh rotation={[0, 0, -Math.PI / 2]} material={parts.m}>
        <cylinderGeometry args={[0.26, 0.32, 3.6, 7]} />
      </mesh>
      <mesh position={[2.35, 0, 0]} rotation={[0, 0, -Math.PI / 2]} material={parts.m}>
        <coneGeometry args={[0.26, 1.1, 7]} />
      </mesh>
      <mesh position={[1.05, 0.27, 0]} scale={[0.75, 0.3, 0.24]}>
        <sphereGeometry args={[1, 10, 6]} />
        <meshStandardMaterial color="#1c2a3c" roughness={0.25} metalness={0.6} />
      </mesh>
      {/* wings and stabilisers: the shapes lie in x/y, turned flat so their span runs out along z */}
      {[1, -1].map((side) => (
        <group key={side} scale={[1, 1, side]}>
          <mesh geometry={parts.wing} material={parts.m} rotation={[Math.PI / 2, 0, 0]} position={[0, -0.05, 0.2]} />
          <mesh geometry={parts.stab} material={parts.m} rotation={[Math.PI / 2, 0, 0]} position={[0, 0, 0.2]} />
          <mesh geometry={parts.fin} material={parts.m} rotation={[-0.32, 0, 0]} position={[0, 0.2, 0.16]} />
        </group>
      ))}
      <mesh position={[-1.95, 0, 0]} rotation={[0, 0, -Math.PI / 2]}>
        <cylinderGeometry args={[0.24, 0.24, 0.12, 8]} />
        <meshBasicMaterial color="#ffb04a" toneMapped={false} />
      </mesh>
      <mesh position={[-2.35 - 0.3 * burn, 0, 0]} rotation={[0, 0, Math.PI / 2]} scale={[1, 0.6 + 0.4 * burn, 1]}>
        <coneGeometry args={[0.2, 1.0, 8]} />
        <meshBasicMaterial color="#ff7b2e" toneMapped={false} transparent opacity={0.85} />
      </mesh>
    </group>
  );
};

// Where a jet is at time t, which way it points, and how it banks: flying across the sky, never at the camera.
type Flight = {from: [number, number, number]; v: [number, number, number]; curve: number; roll: number; c: string; scale: number};
const flightAt = (f: Flight, t: number) => {
  const p: [number, number, number] = [f.from[0] + f.v[0] * t, f.from[1] + f.v[1] * t + f.curve * t * t, f.from[2] + f.v[2] * t];
  const vy = f.v[1] + 2 * f.curve * t;
  const yaw = Math.atan2(-f.v[2], f.v[0]);
  const pitch = Math.atan2(vy, Math.hypot(f.v[0], f.v[2])) * (f.v[0] < 0 ? -1 : 1);
  return {p, yaw, pitch};
};

const JetView: React.FC<{f: Flight; t: number; trail?: 'contrail' | 'smoke'; guns?: boolean}> = ({f, t, trail = 'contrail', guns}) => {
  const {p, yaw, pitch} = flightAt(f, t);
  const roll = f.roll + 0.08 * Math.sin(t * 2.3 + f.from[0]);
  return (
    <>
      <group position={p} scale={f.scale}>
        <group rotation={[0, yaw, 0]}>
          <group rotation={[0, 0, f.v[0] < 0 ? -pitch : pitch]}>
            <group rotation={[roll, 0, 0]}>
              <Jet c={f.c} burn={0.6 + 0.4 * Math.sin(t * 31 + f.from[1])} />
              {/* wingtip vortices: two white threads streaming back from the tips */}
              {trail === 'contrail'
                ? [1, -1].map((side) =>
                    [0, 1, 2, 3, 4].map((i) => (
                      <mesh key={`${side}${i}`} position={[-1.6 - 1.4 - i * 2.8, 0, side * 2.05]}>
                        <boxGeometry args={[2.8, 0.05, 0.05]} />
                        <meshBasicMaterial color="#ffffff" transparent opacity={0.55 - i * 0.1} toneMapped={false} />
                      </mesh>
                    )),
                  )
                : null}
              {/* cannon fire: bright tracer rounds racing ahead of the nose */}
              {guns
                ? [0, 1, 2, 3, 4, 5].map((i) => {
                    const d = 3 + (((t * 9 + i * 1.35) % 8.1) + 8.1) % 8.1;
                    return (
                      <mesh key={i} position={[d, 0.05, i % 2 ? 0.25 : -0.25]}>
                        <boxGeometry args={[0.9, 0.06, 0.06]} />
                        <meshBasicMaterial color="#ffe36b" toneMapped={false} />
                      </mesh>
                    );
                  })
                : null}
            </group>
          </group>
        </group>
      </group>
      {/* a hit jet trails black smoke and fire along where it has been */}
      {trail === 'smoke'
        ? Array.from({length: 14}, (_, i) => {
            const q = flightAt(f, t - 0.09 * (i + 1)).p;
            const s = f.scale * (0.35 + i * 0.12);
            return (
              <mesh key={i} position={[q[0], q[1] + i * 0.03, q[2]]} scale={s}>
                <icosahedronGeometry args={[1, 0]} />
                {i < 2 ? (
                  <meshBasicMaterial color="#ff8a2a" toneMapped={false} />
                ) : (
                  <meshStandardMaterial color="#2e2b29" flatShading roughness={1} transparent opacity={0.9 - i * 0.055} />
                )}
              </mesh>
            );
          })
        : null}
    </>
  );
};

// Storm clouds: big flat faceted banks drifting in the upper sky.
const Clouds: React.FC<{t: number; seed: number}> = ({t, seed}) => {
  const banks = useMemo(() => {
    const r = rng(seed);
    return Array.from({length: 9}, () => ({x: -70 + r() * 140, y: 48 + r() * 30, z: -110 - r() * 40, s: 9 + r() * 9, c: r()}));
  }, [seed]);
  return (
    <>
      {banks.map((b, i) => (
        <mesh key={i} position={[b.x + t * 0.6, b.y, b.z]} scale={[b.s * 1.8, b.s * 0.55, b.s]}>
          <icosahedronGeometry args={[1, 0]} />
          <meshStandardMaterial color={b.c > 0.5 ? '#3b4a6c' : '#53648a'} flatShading roughness={1} fog={false} transparent opacity={0.55} />
        </mesh>
      ))}
    </>
  );
};

// A blaze: a heap of fireballs, white-hot to deep orange, flickering, under a rolling smoke column; lights the road.
const Blaze: React.FC<{p: [number, number, number]; size: number; t: number; seed: number}> = ({p, size, t, seed}) => {
  const balls = useMemo(() => {
    const r = rng(seed);
    return Array.from({length: 18}, () => ({x: (r() - 0.5) * 2.4, y: r() * 2.2, z: (r() - 0.5) * 1.6, s: 0.4 + r() * 0.8, c: r(), ph: r() * 6}));
  }, [seed]);
  const fl = 0.85 + 0.15 * Math.sin(t * 13 + seed) * Math.sin(t * 4.3);
  return (
    <group position={p} scale={size}>
      {balls.map((b, i) => (
        <mesh key={i} position={[b.x, b.y + 0.2 * Math.sin(t * 3 + b.ph), b.z]} scale={b.s * (0.9 + 0.15 * Math.sin(t * 7 + b.ph))}>
          <icosahedronGeometry args={[1, 0]} />
          <meshBasicMaterial color={b.c < 0.25 ? '#fff0b0' : b.c < 0.6 ? '#ffa030' : '#e8481a'} toneMapped={false} transparent opacity={0.92} />
        </mesh>
      ))}
      <pointLight position={[0, 1.5, 2]} intensity={90 * fl} distance={24} decay={1.3} color="#ff8a30" />
    </group>
  );
};

// A low-poly helicopter, nose toward -x, rotor spinning, its searchlight on the road.
const Helicopter: React.FC<{t: number}> = ({t}) => {
  const body = mat('#3a4232');
  const dark = mat('#16181b');
  return (
    <group>
      <mesh scale={[1.25, 0.62, 0.62]} material={body}>
        <icosahedronGeometry args={[1, 1]} />
      </mesh>
      <mesh position={[-0.75, 0.12, 0]} scale={[0.5, 0.36, 0.48]}>
        <icosahedronGeometry args={[1, 1]} />
        <meshStandardMaterial color="#1c2a3a" roughness={0.2} metalness={0.6} />
      </mesh>
      <mesh position={[1.9, 0.2, 0]} rotation={[0, 0, Math.PI / 2 + 0.08]} material={body}>
        <cylinderGeometry args={[0.1, 0.2, 2.0, 6]} />
      </mesh>
      <mesh position={[2.85, 0.55, 0]} material={body}>
        <boxGeometry args={[0.3, 0.75, 0.06]} />
      </mesh>
      <mesh position={[2.85, 0.5, 0.1]} rotation={[0, 0, t * 40]} material={dark}>
        <boxGeometry args={[0.06, 0.8, 0.02]} />
      </mesh>
      <mesh position={[0, 0.66, 0]} material={dark}>
        <cylinderGeometry args={[0.08, 0.08, 0.2, 6]} />
      </mesh>
      {[0, 1].map((k) => (
        <mesh key={k} position={[0, 0.78, 0]} rotation={[0, t * 26 + k * Math.PI / 2, 0]} material={dark}>
          <boxGeometry args={[4.6, 0.03, 0.16]} />
        </mesh>
      ))}
      <mesh position={[0, 0.78, 0]}>
        <cylinderGeometry args={[2.3, 2.3, 0.01, 24]} />
        <meshBasicMaterial color="#9aa6b8" transparent opacity={0.12} />
      </mesh>
      {[-1, 1].map((s) => (
        <mesh key={s} position={[0, -0.72, s * 0.42]} material={dark}>
          <boxGeometry args={[1.9, 0.05, 0.05]} />
        </mesh>
      ))}
      {/* the searchlight: a lamp under the nose and its beam slanting down to the road */}
      <mesh position={[-1.0, -0.45, 0]}>
        <sphereGeometry args={[0.12, 8, 6]} />
        <meshBasicMaterial color="#fff6d0" toneMapped={false} />
      </mesh>
      <mesh position={[-1.9, -3.2, 0.6]} rotation={[0.18, 0, -0.32]}>
        <coneGeometry args={[1.5, 5.6, 16, 1, true]} />
        <meshBasicMaterial color="#fff2c0" transparent opacity={0.13} side={THREE.DoubleSide} depthWrite={false} toneMapped={false} />
      </mesh>
    </group>
  );
};

// A fortress on a sheer cliff: dark rock, a keep and towers with lit windows, red banners, a dish on the roof.
const Fortress: React.FC = () => {
  const rock = mat('#262a33');
  const wall = mat('#1b1e26');
  const r = rng(41);
  const windows = Array.from({length: 26}, () => [(r() - 0.5) * 9, 28 + r() * 7, 3.05] as [number, number, number]);
  return (
    <group>
      {[[0, 13, 0, 9, 26], [-4, 10, 2, 6, 20], [4.5, 11, -1, 6.5, 22], [-1, 7, 4, 8, 14]].map(([x, y, z, w, h], i) => (
        <mesh key={i} position={[x, y, z]} material={rock} rotation={[0, i * 0.7, 0]}>
          <cylinderGeometry args={[w * 0.55, w, h, 6]} />
        </mesh>
      ))}
      <mesh position={[0, 29.5, 0]} material={wall}>
        <boxGeometry args={[10, 5, 6]} />
      </mesh>
      {[[-4.2, 0], [4.2, 0], [0, -1.5]].map(([x, z], i) => (
        <group key={i} position={[x, 33.5, z]}>
          <mesh material={wall}>
            <boxGeometry args={[2.2, i === 2 ? 9 : 6, 2.2]} />
          </mesh>
          <mesh position={[0, i === 2 ? 5.6 : 4.1, 0]} material={wall}>
            <coneGeometry args={[1.6, 2.4, 4]} />
          </mesh>
        </group>
      ))}
      {windows.map((w, i) => (
        <mesh key={i} position={w}>
          <planeGeometry args={[0.35, 0.55]} />
          <meshBasicMaterial color="#ffbe6a" toneMapped={false} />
        </mesh>
      ))}
      {[-2.3, 2.3].map((x) => (
        <group key={x} position={[x, 29.3, 3.06]}>
          <mesh>
            <planeGeometry args={[1.3, 3.4]} />
            <meshBasicMaterial color="#c3121e" />
          </mesh>
          <mesh position={[0, 0.5, 0.01]}>
            <circleGeometry args={[0.38, 3]} />
            <meshBasicMaterial color="#f2efe9" />
          </mesh>
        </group>
      ))}
      <group position={[-4.2, 37.6, 0.4]} rotation={[0.6, 0.3, 0]}>
        <mesh material={mat('#9aa0a8')}>
          <sphereGeometry args={[1.3, 12, 6, 0, Math.PI * 2, 0, Math.PI / 2.6]} />
        </mesh>
      </group>
    </group>
  );
};

// A long bridge on stone arches across the valley.
const Bridge: React.FC = () => {
  const stone = mat('#3a3f4a');
  return (
    <group>
      <mesh position={[0, 7, 0]} material={stone}>
        <boxGeometry args={[34, 0.9, 2.2]} />
      </mesh>
      {Array.from({length: 7}, (_, i) => -15 + i * 5).map((x) => (
        <group key={x}>
          <mesh position={[x, 3.2, 0]} material={stone}>
            <boxGeometry args={[1.0, 7, 2]} />
          </mesh>
          <mesh position={[x + 2.5, 5.0, 0]} material={stone}>
            <torusGeometry args={[2.0, 0.42, 4, 10, Math.PI]} />
          </mesh>
        </group>
      ))}
      {Array.from({length: 12}, (_, i) => (
        <mesh key={i} position={[-16 + i * 2.9, 7.7, 1.15]}>
          <sphereGeometry args={[0.12, 6, 4]} />
          <meshBasicMaterial color="#ffd38a" toneMapped={false} />
        </mesh>
      ))}
    </group>
  );
};

const Mountains: React.FC = () => {
  const r = rng(17);
  const peaks = Array.from({length: 8}, (_, i) => ({x: 4 + i * 9 + r() * 4, h: 18 + r() * 16, w: 10 + r() * 6}));
  return (
    <group position={[0, 0, -95]}>
      {peaks.map((m, i) => (
        <group key={i} position={[m.x, 0, -r() * 10]}>
          <mesh position={[0, m.h / 2, 0]} material={mat('#2c3446')}>
            <coneGeometry args={[m.w, m.h, 5]} />
          </mesh>
          <mesh position={[0, m.h * 0.86, 0]} material={mat('#d9dee8')}>
            <coneGeometry args={[m.w * 0.14 + 0.2, m.h * 0.28, 5]} />
          </mesh>
        </group>
      ))}
    </group>
  );
};

// White racing stripes over the bonnet, roof and tail of the coupe, following its side profile (Big.tsx CAR_BODY/ROOF).
// over the bonnet, then the roof and the tail (never across the windscreen)
const STRIPE_PATHS: [number, number][][] = [[[2.2, 0.68], [1.2, 0.86], [0.66, 0.93]], [[-0.1, 1.53], [-0.8, 1.56], [-1.5, 1.24]], [[-1.62, 0.99], [-2.3, 0.99]]];
const Stripes: React.FC = () => {
  const white = mat('#f1f1ee');
  return (
    <>
      {[-0.2, 0.2].flatMap((x) =>
        STRIPE_PATHS.flatMap((path, pi) => path.slice(1).map((b, i) => {
          const a = path[i];
          const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
          return (
            <mesh key={`${x}${pi}${i}`} material={white} position={[x, (a[1] + b[1]) / 2, (a[0] + b[0]) / 2]} rotation={[-Math.atan2(b[1] - a[1], b[0] - a[0]), 0, 0]}>
              <boxGeometry args={[0.24, 0.02, len + 0.04]} />
            </mesh>
          );
        })),
      )}
    </>
  );
};

// A police car: the same coupe in black and white with a light bar flashing red and blue.
const Police: React.FC<{t: number; k: number}> = ({t, k}) => {
  const on = Math.sin(t * 15 + k) > 0;
  return (
    <group>
      <BigModel kind="car" color="#15181e" seed={7 + k} speed={20} />
      <mesh position={[0, 1.57, -0.45]}>
        <boxGeometry args={[1.3, 0.12, 0.3]} />
        <meshBasicMaterial color="#222" />
      </mesh>
      <mesh position={[-0.35, 1.66, -0.45]}>
        <boxGeometry args={[0.55, 0.1, 0.26]} />
        <meshBasicMaterial color={on ? '#ff2a2a' : '#5a1010'} toneMapped={false} />
      </mesh>
      <mesh position={[0.35, 1.66, -0.45]}>
        <boxGeometry args={[0.55, 0.1, 0.26]} />
        <meshBasicMaterial color={on ? '#1a2a60' : '#3a6bff'} toneMapped={false} />
      </mesh>
      <pointLight position={[0, 2.2, 0]} intensity={on ? 16 : 0} distance={8} color="#ff3030" />
      <pointLight position={[0, 2.2, 0]} intensity={on ? 0 : 16} distance={8} color="#3a6bff" />
      {[-0.62, 0.62].map((x) => (
        <spotLight key={x} position={[x, 0.65, 2.3]} target-position={[x * 3, 0, 12]} angle={0.45} penumbra={0.6} intensity={18} distance={16} color="#fff2d8" />
      ))}
    </group>
  );
};

// Who rides in the hero's car, side by side behind the windscreen (him in the middle), in the car's own frame.
const RIDE_SCALE = 0.62;
const riders = (n: number) => (n >= 3 ? [-0.5, 0, 0.5] : n === 2 ? [-0.38, 0.38] : [0]);

// The poster's backdrop and the chase, seen from low on the road.
export const posterCam = (tall: boolean, t: number, dur: number): Plan => {
  const p = interpolate(t, [0, dur], [0, 1], clamp);
  return tall ? planOf([0, 4.0, 8.0 - 0.5 * p], [0, -1.95, -20], 56) : planOf([0, 1.25, 8.2 - 0.5 * p], [2.0, 2.6, -20], 36);
};

export const PosterScene: React.FC<{
  shot: LPShot;
  t: number;
  cast: Record<string, Design>;
  tall: boolean;
  CamRig: React.FC<{plan: Plan; exposure: number}>;
}> = ({shot, t, cast, tall, CamRig}) => {
  const pp = shot.poster!;
  const who = pp.people.filter((k) => cast[k]).slice(0, 3);
  const plan = posterCam(tall, t, shot.duration);
  const seed = (shot.seed ?? 1) % 97;
  const carX = tall ? 0 : 3.4;
  const carZ = tall ? -0.45 + 0.3 * t : -1.2 + 0.3 * t;
  const xs = riders(who.length);
  // the order in the car: sister on the left, him in the middle, his friend on the right
  const order = who.length >= 3 ? [who[1], who[0], who[2]] : who;
  return (
    <>
      <color attach="background" args={['#1a2440']} />
      <fogExp2 attach="fog" args={['#24304c', 0.0095]} />
      <CamRig plan={plan} exposure={1.05} />
      <SkyDome top="#0b1530" hor="#4a5d86" />
      <Clouds t={t} seed={seed} />
      <hemisphereLight args={['#8ea6d8', '#2a1a14', 0.75]} />
      {/* warm from the fire on the left, cold moonlight from the right and behind */}
      <directionalLight position={[-8, 6, 7]} intensity={1.7} color="#ffb070" castShadow shadow-mapSize={[2048, 2048]}
        shadow-camera-left={-8} shadow-camera-right={8} shadow-camera-top={6} shadow-camera-bottom={-4} />
      <directionalLight position={[7, 9, -6]} intensity={1.3} color="#8ab4ff" />
      {/* the wet road with its lane lines rushing past */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, -40]} receiveShadow>
        <planeGeometry args={[60, 140]} />
        <meshStandardMaterial color="#14171d" roughness={0.28} metalness={0.55} />
      </mesh>
      {[-3.4, 3.4].map((x) =>
        Array.from({length: 14}, (_, i) => (
          <mesh key={`${x}${i}`} rotation={[-Math.PI / 2, 0, 0]} position={[x * (1 + i * 0.02), 0.01, 4 - ((i * 5 + t * 30) % 70)]}>
            <planeGeometry args={[0.18, 2.4]} />
            <meshBasicMaterial color="#d8d8d0" />
          </mesh>
        )),
      )}
      <Mountains />
      <group position={tall ? [15, 0, -60] : [34, 0, -70]} scale={tall ? 0.5 : 1}>
        <Fortress />
      </group>
      <group position={tall ? [17, 0, -48] : [26, 0, -52]} scale={tall ? 0.8 : 1}>
        <Bridge />
      </group>
      {/* the blaze on the left and its smoke */}
      <Blaze p={tall ? [-6.2, 0, -9] : [-9, 0, -10]} size={1.6} t={t} seed={seed + 4} />
      <Blaze p={tall ? [-8.5, 0, -17] : [-14, 0, -18]} size={2.4} t={t} seed={seed + 5} />
      <Smoke x={tall ? -7 : -12} z={-18} top={tall ? 8 : 22} t={t} seed={seed + 1} dark />
      <Smoke x={tall ? -5.5 : -8} z={-10} top={tall ? 6 : 14} t={t} seed={seed + 2} dark />
      {/* fighter jets climbing away across the top left */}
      {(tall
        ? [[4, 11.2, -45], [0.5, 9.9, -46], [6.6, 9.1, -44]]
        : [[-12, 13.5, -40], [-16, 12.2, -41], [-9.5, 11.2, -39]]
      ).map((p, i) => (
        <JetView key={i} t={t} f={{from: p as [number, number, number], v: [-3.2, 1.1, 0], curve: 0, roll: 0.35, c: '#8a94a3', scale: tall ? 1.0 : 0.8}} />
      ))}
      <group position={tall ? [5.2, 2.8, -14] : [10.5, 5.2, -14]} rotation={[0.1, 0.25, 0.08]}>
        <Helicopter t={t} />
      </group>
      {/* the chase: police cars on both sides behind */}
      {(tall ? [[-3.6, -4.5, 0.18], [3.9, -7.5, -0.15], [6.2, -14, -0.1]] : [[-1.2, -6, 0.12], [8.2, -5, -0.2], [10.5, -12, -0.1]]).map(([x, z, ry], i) => (
        <group key={i} position={[x, 0, z + 0.3 * t]} rotation={[0, ry, 0]}>
          <Police t={t} k={i * 1.3} />
        </group>
      ))}
      {/* the hero's car, the three of them inside, headlights blazing, spray off the wheels */}
      <group position={[carX, 0, carZ]} rotation={[0, tall ? 0.08 : -0.12, 0]}>
        <BigModel kind="car" color={pp.car || '#c1121f'} seed={3} speed={30} />
        <Stripes />
        {order.map((key, i) => (
          <group key={key} position={[xs[i], 0, -0.35]} scale={RIDE_SCALE}>
            <Man design={cast[key]} pose={pose({action: 'ride', t: 0.8 + i, dur: 3, seat: 0.4 / RIDE_SCALE, k: i})} face={face(key === who[0] ? 'determined' : 'angry', t, i + 7)}
              root={[0, 0, 0]} ry={0} seed={key === 'hero' ? 7 : 20 + i} />
          </group>
        ))}
        {[-0.68, 0.68].map((x) => (
          <group key={x}>
            <spotLight position={[x, 0.65, 2.4]} target-position={[x * 2, 0, 14]} angle={0.5} penumbra={0.5} intensity={30} distance={14} color="#fff4d6" />
          </group>
        ))}
        {[-0.85, 0.85].map((x) =>
          [0, 1, 2, 3, 4, 5].map((i) => (
            <mesh key={`${x}${i}`} position={[x * (1.1 + i * 0.12), 0.15 + i * 0.07, -1.5 - i * 0.45]} scale={0.18 + i * 0.07}>
              <icosahedronGeometry args={[1, 0]} />
              <meshBasicMaterial color="#c9d4e4" transparent opacity={0.4 - i * 0.055} depthWrite={false} />
            </mesh>
          )),
        )}
      </group>
    </>
  );
};

// The three of them chest-up and huge over the backdrop, in their own see-through canvas: the hero in front and
// higher, his sister on the left and his best friend on the right a step behind, each turned in and looking into the
// lens (the user: "why sis and his best friend look below?"), close-up eyes (Man detail).
type Bust = {x: number; y: number; z: number; turn: number; expr: Expr};
const BUSTS: Bust[] = [
  {x: 0, y: 0, z: 0.6, turn: 0, expr: 'determined'},
  {x: -1.0, y: -0.25, z: -0.5, turn: 0.42, expr: 'determined'},
  {x: 1.0, y: -0.3, z: -0.5, turn: -0.42, expr: 'angry'},
];
const bustPose = (b: Bust, t: number, k: number) => {
  const p = pose({action: 'stand', t, dur: 3, seat: null, k, at: 0.6});
  p.armL = {x: -0.15, z: 0.1, bend: -0.5};
  p.armR = {x: -0.15, z: 0.1, bend: -0.5};
  p.lean = 0.04;
  p.head = [-0.04, -b.turn * 0.75, 0];
  return p;
};
export const bustCam = (tall: boolean, t: number, dur: number): Plan => {
  const p = interpolate(t, [0, dur], [0, 1], clamp);
  return tall ? planOf([0, 0.75, 9.2 - 0.5 * p], [0, 0.5, 0], 30) : planOf([1.6, 0.75, 7.4 - 0.5 * p], [1.6, 0.55, 0], 30);
};
export const PosterBusts: React.FC<{p: Poster; t: number; dur: number; cast: Record<string, Design>; tall: boolean; width: number; height: number;
  CamRig: React.FC<{plan: Plan; exposure: number}>}> = ({p, t, dur, cast, tall, width, height, CamRig}) => {
  const who = p.people.filter((k) => cast[k]).slice(0, 3);
  const rise = interpolate(t, [0, 0.9], [0.25, 0], {...clamp, easing: (x) => 1 - (1 - x) ** 3});
  return (
    <div style={{position: 'absolute', inset: 0, WebkitMaskImage: `linear-gradient(to bottom, black 0%, black ${tall ? 33 : 44}%, transparent ${tall ? 46 : 62}%)`,
      maskImage: `linear-gradient(to bottom, black 0%, black ${tall ? 33 : 44}%, transparent ${tall ? 46 : 62}%)`}}>
      <ThreeCanvas width={width} height={height} gl={{antialias: true, alpha: true}} camera={{fov: 30, near: 0.1, far: 100, position: [0, 1, 10]}}>
        <CamRig plan={bustCam(tall, t, dur)} exposure={1.1} />
        <hemisphereLight args={['#a9bde6', '#3a2416', 0.9]} />
        <directionalLight position={[-5, 3, 6]} intensity={2.4} color="#ffc28a" />
        <directionalLight position={[5, 4, -4]} intensity={3.2} color="#78a8ff" />
        <directionalLight position={[0, 1, 8]} intensity={0.6} color="#ffffff" />
        {who.map((key, i) => {
          const b = BUSTS[i];
          return (
            <Man key={key} design={cast[key]} pose={bustPose(b, 0.6 + i * 0.4 + t * 0.2, i * 1.7)} face={face(b.expr, t, i + 3)} detail
              root={[b.x, b.y - rise * (i + 1) * 0.4, b.z]} ry={b.turn} seed={key === 'hero' ? 7 : 20 + i} />
          );
        })}
      </ThreeCanvas>
    </div>
  );
};

// The words, as on the reference: a kicker over the top, the title in silver with a red slash, the billing, then the
// tagline and a red COMING SOON at the foot.
export const PosterWords: React.FC<{p: Poster; t: number; tall: boolean; width: number}> = ({p, t, tall, width}) => {
  const top = interpolate(t, [0.1, 0.6], [0, 1], clamp);
  const slam = interpolate(t, [0.45, 0.62], [0, 1], {...clamp, easing: (x) => 1 - (1 - x) ** 3});
  const slash = interpolate(t, [0.62, 0.85], [0, 1], clamp);
  const bill = interpolate(t, [0.95, 1.45], [0, 1], clamp);
  const foot = interpolate(t, [1.3, 1.8], [0, 1], clamp);
  const words = p.title.toUpperCase().split(/\s+/);
  const small = words.length > 1 && ['THE', 'A', 'AN'].includes(words[0]) ? words[0] : '';
  const main = (small ? words.slice(1) : words).join(' ');
  const size = Math.min(tall ? 210 : 150, (width * (tall ? 0.94 : 0.5)) / Math.max(4, main.length * 0.52));
  const names = (p.names && p.names.length ? p.names : []).map((n) => n.toUpperCase());
  const line = (w: number) => <span style={{display: 'inline-block', width: w, height: 2, background: 'linear-gradient(90deg, transparent, #e3262f, transparent)', verticalAlign: 'middle', margin: '0 22px'}} />;
  const silver: React.CSSProperties = {
    background: 'linear-gradient(180deg, #ffffff 0%, #dfe2e7 38%, #8b9099 52%, #c9cdd3 70%, #f4f5f7 100%)',
    WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent',
    filter: 'drop-shadow(0 6px 0 #1a1c22) drop-shadow(0 0 22px rgba(0,0,0,0.7))',
  };
  const block = tall ? {left: 0, right: 0, top: 830} : {left: '50%', right: 0, top: 300};
  return (
    <>
      {/* the poster's foot: the road under the words darkened */}
      <div style={{position: 'absolute', left: 0, right: 0, bottom: 0, height: tall ? '16%' : '22%', background: 'linear-gradient(to bottom, rgba(6,8,14,0), rgba(6,8,14,0.85))'}} />
      <div style={{position: 'absolute', left: 0, right: 0, top: tall ? 34 : 26, textAlign: 'center', opacity: top, fontFamily: 'Inter, sans-serif', fontWeight: 600,
        fontSize: tall ? 26 : 20, letterSpacing: tall ? 8 : 7, color: '#f2f2f2', textShadow: '0 2px 10px #000'}}>
        {line(tall ? 110 : 140)}
        {(p.kicker || 'A low-poly action film').toUpperCase()}
        {line(tall ? 110 : 140)}
      </div>
      <div style={{position: 'absolute', ...block, textAlign: 'center'}}>
        {small ? (
          <div style={{...silver, opacity: slam, fontFamily: 'Anton, Impact, sans-serif', fontStyle: 'italic', fontSize: size * 0.42, lineHeight: 1, letterSpacing: 4,
            transform: `skewX(-10deg) scale(${1.6 - 0.6 * slam})`}}>
            {small}
          </div>
        ) : null}
        <div style={{position: 'relative', display: 'inline-block'}}>
          <div style={{...silver, opacity: slam, fontFamily: 'Anton, Impact, sans-serif', fontStyle: 'italic', fontSize: size, lineHeight: 1.02, letterSpacing: 2,
            transform: `skewX(-12deg) scale(${1.8 - 0.8 * slam})`}}>
            {main}
          </div>
          {/* the red slash cut through the title */}
          <div style={{position: 'absolute', left: '8%', width: `${84 * slash}%`, top: '50%', height: tall ? 7 : 5, transform: 'rotate(-9deg)', transformOrigin: 'left center',
            background: 'linear-gradient(90deg, rgba(255,40,40,0), #ff2a2a 25%, #ffd0c0 60%, rgba(255,40,40,0))', boxShadow: '0 0 18px 4px rgba(255,30,30,0.75)', borderRadius: 4}} />
        </div>
        <div style={{opacity: bill, marginTop: tall ? 22 : 14, fontFamily: 'Inter, sans-serif', fontWeight: 600, fontSize: tall ? 22 : 16, letterSpacing: 8, color: '#e8e8e8'}}>STARRING</div>
        <div style={{opacity: bill, marginTop: 8, fontFamily: 'Inter, sans-serif', fontWeight: 700, fontSize: tall ? 40 : 28, letterSpacing: 6, color: '#fff', textShadow: '0 2px 12px #000'}}>
          {names.map((n, i) => (
            <span key={n}>
              {i ? <span style={{color: '#e3262f', margin: '0 26px'}}>|</span> : null}
              {n}
            </span>
          ))}
        </div>
      </div>
      <div style={{position: 'absolute', left: 0, right: 0, bottom: tall ? 128 : 74, textAlign: 'center', opacity: foot, fontFamily: 'Inter, sans-serif', fontWeight: 600,
        fontSize: tall ? 24 : 18, letterSpacing: tall ? 7 : 8, color: '#f0f0f0', display: p.tagline ? 'block' : 'none', textShadow: '0 2px 10px #000'}}>
        {p.tagline.toUpperCase()}
      </div>
      <div style={{position: 'absolute', left: 0, right: 0, bottom: tall ? 40 : 18, textAlign: 'center', opacity: foot, fontFamily: 'Anton, Impact, sans-serif', fontStyle: 'italic',
        fontSize: tall ? 60 : 44, letterSpacing: 12, color: '#e3262f', textShadow: '0 0 18px rgba(227,38,47,0.6)'}}>
        {line(tall ? 150 : 200)}
        {p.date.toUpperCase()}
        {line(tall ? 150 : 200)}
      </div>
    </>
  );
};
