// 🎭 The cast intro's last shot: one action-movie poster with the whole cast (the user: "create one poster just like
// movie, so i can use at end of intro short. using all char in one image, not stand one by one, show like images, add
// car on background, some action movie type"). A one-sheet's composition, not a line-up: the hero front and centre,
// two crouched beside him, the rest stacked behind on broken ledges at rising heights, a sports car slewed across
// behind them with its lights on, a giant face looming over a city skyline, coloured rim lights, haze; over it a
// tagline, the title slammed on, a billing block and a date line. Built from the film's own 3D cast, no picture
// generator. Picture only: the intro's score and an impact play under it (reelgen/lowpoly/timeline.py).
import React, {useMemo} from 'react';
import {interpolate} from 'remotion';
import * as THREE from 'three';
import {BigModel} from './Big';
import {Man, mat} from './Man';
import {face, pose} from './poses';
import type {Action, Design, Expr, LPShot, Poster} from './types';

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

type Slot = {x: number; y: number; z: number; action: Action; expr: Expr; turn: number};

// Where everyone stands, front to back: 1 hero, 2 crouched flankers, then rows of up to 4 on rising ledges.
export const posterSlots = (n: number, tall: boolean): Slot[] => {
  const out: Slot[] = [{x: 0, y: 0, z: 2.2, action: 'stand', expr: 'determined', turn: 0}];
  const w = tall ? 0.85 : 1.25;
  const exprs: Expr[] = ['angry', 'determined', 'happy', 'neutral', 'surprised', 'annoyed'];
  if (n > 1) out.push({x: -w * 1.15, y: 0, z: 1.6, action: 'crouch', expr: 'determined', turn: 0.25});
  if (n > 2) out.push({x: w * 1.15, y: 0, z: 1.6, action: 'crouch', expr: 'angry', turn: -0.25});
  let row = 0;
  while (out.length < n) {
    const left = n - out.length;
    const k = Math.min(left, row === 0 ? 4 : 5);
    const z = 0.2 - row * 1.5;
    const y = 0.55 + row * 0.75;
    const span = (k - 1) * w * (row === 0 ? 0.95 : 0.85);
    for (let i = 0; i < k; i++) {
      const x = k === 1 ? 0 : -span / 2 + (span * i) / (k - 1);
      out.push({x: x + (i % 2 ? 0.12 : -0.12), y, z: z + (i % 2 ? -0.25 : 0), action: i % 3 === 1 ? 'point' : 'stand',
        expr: exprs[(out.length + row) % exprs.length], turn: -x * 0.08});
    }
    row++;
  }
  return out.slice(0, n);
};

// The camera: low and looking up a little, so the cast towers like a poster's; a slow push over the shot.
export const posterCam = (tall: boolean, t: number, dur: number) => {
  const p = interpolate(t, [0, dur], [0, 1], clamp);
  // aimed low, so the cast stands in the upper half and the title has the ground under them
  const pos = tall ? new THREE.Vector3(0, 0.9, 9.4 - 0.8 * p) : new THREE.Vector3(0, 1.0, 8.6 - 0.7 * p);
  const look = tall ? new THREE.Vector3(0, 0.25, -1) : new THREE.Vector3(0, 0.6, -1);
  return {pos, look, up: new THREE.Vector3(0, 1, 0), fov: tall ? 52 : 34, focus: pos.distanceTo(new THREE.Vector3(0, 1.4, 2.2)), aperture: 0.004, near: 0.1};
};

const Ledge: React.FC<{x: number; y: number; z: number; w: number}> = ({x, y, z, w}) =>
  y <= 0.01 ? null : (
    <mesh position={[x, y / 2, z]} receiveShadow castShadow>
      <boxGeometry args={[w, y, 1.3]} />
      <primitive object={mat('#5a534c')} attach="material" />
    </mesh>
  );

const rng = (seed: number) => {
  let s = seed * 9301 + 49297;
  return () => ((s = (s * 9301 + 49297) % 233280) / 233280);
};

// A daylight sky: deep blue overhead, a dusty smoke-stained haze at the horizon.
const SkyDome: React.FC = () => {
  const g = useMemo(() => {
    const r = 160;
    const geo = new THREE.SphereGeometry(r, 24, 12);
    const top = new THREE.Color('#3f7fca');
    const hor = new THREE.Color('#e6d6bd');
    const cols: number[] = [];
    const pos = geo.attributes.position;
    for (let i = 0; i < pos.count; i++) {
      const c = hor.clone().lerp(top, Math.pow(Math.max(0, pos.getY(i) / r), 0.45));
      cols.push(c.r, c.g, c.b);
    }
    geo.setAttribute('color', new THREE.Float32BufferAttribute(cols, 3));
    return geo;
  }, []);
  return (
    <mesh geometry={g}>
      <meshBasicMaterial vertexColors side={THREE.BackSide} toneMapped={false} fog={false} />
    </mesh>
  );
};

// A city skyline in daylight, behind the cast; a few windows burning.
const Skyline: React.FC<{seed: number; z: number; tall: number}> = ({seed, z, tall}) => {
  const blocks = useMemo(() => {
    const r = rng(seed);
    return Array.from({length: 26}, (_, i) => ({x: -40 + i * 3.2 + r() * 1.5, w: 2.2 + r() * 2.4, h: (2.6 + r() * 2.2) * tall, c: r(), fire: r()}));
  }, [seed]);
  return (
    <group position={[0, 0, z]}>
      {blocks.map((b, i) => (
        <group key={i}>
          <mesh position={[b.x, b.h / 2, -(i % 3) * 1.4]} castShadow receiveShadow>
            <boxGeometry args={[b.w, b.h, 2]} />
            <primitive object={mat(b.c < 0.33 ? '#7d8796' : b.c < 0.66 ? '#958f86' : '#6c7380')} attach="material" />
          </mesh>
          {Array.from({length: Math.floor(b.h / 1.3)}, (_, j) => (
            <mesh key={j} position={[b.x + ((j % 2) - 0.5) * b.w * 0.4, 0.9 + j * 1.25, 1.01 - (i % 3) * 1.4]}>
              <planeGeometry args={[0.4, 0.5]} />
              <meshBasicMaterial color={b.fire > 0.8 && j % 2 === 0 ? '#ff7a1f' : '#3a4452'} toneMapped={b.fire <= 0.8} />
            </mesh>
          ))}
        </group>
      ))}
    </group>
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

// Fighter jets streaking across the sky in formation (the user: "not dog fight, i say fighter plane (aircraft)"):
// side-on, banked a little, contrails behind them; never flying at the camera, no gunfire.
const flights = (tall: boolean): {f: Flight; trail?: 'contrail' | 'smoke'; guns?: boolean}[] => {
  const lead = tall ? {x: -2.6, y: 8.4, vx: 2.0} : {x: -9.5, y: 6.6, vx: 3.0};
  const vee = [[0, 0, 0], [-3.2, -1.0, -2.4], [-3.2, 1.0, 1.2], [-6.4, -2.0, -4.8]].slice(0, tall ? 3 : 4);
  const four: {f: Flight}[] = vee.map(([dx, dy, dz], i) => ({
    f: {from: [lead.x + dx, lead.y + dy * 0.35 + dz * 0.0, (tall ? -24 : -30) + dz], v: [lead.vx, 0.25, 0], curve: 0, roll: -0.35, c: i ? '#7b8592' : '#8e98a6', scale: tall ? 0.6 : 0.85},
  }));
  const pair: {f: Flight}[] = [0, 1].map((i) => ({
    f: {from: [(tall ? 7 : 13) + i * 2.4, (tall ? 10.8 : 7.6) + i * 0.4, (tall ? -36 : -40) - i * 1.5], v: [-2.2, -0.1, 0], curve: 0, roll: 0.3, c: '#6c7480', scale: tall ? 0.6 : 0.8},
  }));
  return [...four, ...pair];
};

export const PosterScene: React.FC<{
  shot: LPShot;
  t: number;
  cast: Record<string, Design>;
  tall: boolean;
  CamRig: React.FC<{plan: ReturnType<typeof posterCam>; exposure: number}>;
}> = ({shot, t, cast, tall, CamRig}) => {
  const pp = shot.poster!;
  const who = pp.people.filter((k) => cast[k]);
  const slots = posterSlots(who.length, tall);
  const plan = posterCam(tall, t, shot.duration);
  const seed = (shot.seed ?? 1) % 97;
  // a blast flaring up behind the city now and then
  const blast = Math.max(0, 1 - Math.abs(((t + 0.4) % 2.6) - 0.35) * 2.2);
  return (
    <>
      {/* daylight over a city at war (the user: "background must be action things, and daylight and fighter plane at
          sky, not pointing to screen, look like they fight on sky") */}
      <color attach="background" args={['#b9cde0']} />
      <fogExp2 attach="fog" args={['#d9d0c0', 0.011]} />
      <CamRig plan={plan} exposure={1.0} />
      <SkyDome />
      <hemisphereLight args={['#eef3fa', '#7a6e5e', 1.25]} />
      <directionalLight position={[-7, 12, 10]} intensity={2.6} color="#fff1dc" castShadow shadow-mapSize={[2048, 2048]}
        shadow-camera-left={-8} shadow-camera-right={8} shadow-camera-top={8} shadow-camera-bottom={-4} />
      {/* the fires behind them light their backs orange */}
      <pointLight position={[-4, 3.5, -3]} intensity={26} distance={12} decay={1.4} color="#ff8a3a" />
      <pointLight position={[4.5, 3.5, -3]} intensity={18} distance={12} decay={1.4} color="#ffa04a" />
      {/* the ground: a scorched road */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, -10]} receiveShadow>
        <planeGeometry args={[160, 90]} />
        <meshStandardMaterial color="#5e5b58" roughness={0.9} />
      </mesh>
      <Skyline seed={seed} z={tall ? -20 : -24} tall={tall ? 1.15 : 0.85} />
      <Smoke x={tall ? -5.2 : -12} z={tall ? -21 : -25} top={tall ? 12 : 8.5} t={t} seed={seed + 1} dark />
      <Smoke x={tall ? 4.6 : 9.5} z={tall ? -22 : -26} top={tall ? 11 : 8} t={t} seed={seed + 2} />
      {tall ? null : <Smoke x={-3} z={-28} top={7.5} t={t} seed={seed + 3} dark />}
      {/* an explosion flaring over the rooftops: a white-hot core in an orange fireball, gone between blasts */}
      {blast > 0.06 ? (
        <group position={[tall ? -2.6 : 4.5, tall ? 5.6 : 4.0, tall ? -21 : -25]} scale={0.4 + blast * 1.4}>
          <mesh scale={0.55}>
            <icosahedronGeometry args={[1, 1]} />
            <meshBasicMaterial color="#fff1a8" toneMapped={false} />
          </mesh>
          <mesh>
            <icosahedronGeometry args={[1, 0]} />
            <meshBasicMaterial color="#ff6a1a" toneMapped={false} transparent opacity={0.75 * blast} />
          </mesh>
        </group>
      ) : null}
      {flights(tall).map((j, i) => (
        <JetView key={i} f={j.f} t={t} trail={j.trail} guns={j.guns} />
      ))}
      {/* two sports cars, one each side behind them, noses angled out toward us */}
      {[-1, 1].map((side) => (
        <group key={side} position={[side * (tall ? 2.25 : 3.5), 0, -1.6]} rotation={[0, side * 0.6, 0]}>
          <BigModel kind="car" color={side < 0 ? pp.car2 || '#1d2433' : pp.car || '#c1121f'} seed={side < 0 ? 5 : 3} speed={0} />
        </group>
      ))}
      {slots.map((s, i) => (
        <Ledge key={`l${i}`} x={s.x} y={s.y} z={s.z} w={1.05} />
      ))}
      {slots.map((s, i) => {
        const key = who[i];
        const ps = pose({action: s.action, t: 0.6 + i * 0.13, dur: 3, seat: null, k: i * 1.7, at: 0.6});
        const ry = Math.atan2(plan.pos.x - s.x, plan.pos.z - s.z) + s.turn;
        return (
          <Man key={key} design={cast[key]} pose={ps} face={face(s.expr, t, i + 3)} root={[s.x, s.y, s.z]} ry={ry} seed={key === 'hero' ? 7 : 20 + i} />
        );
      })}
    </>
  );
};

// The words: a tagline at the top, the title slammed on low, the billing block and the date line under it.
export const PosterWords: React.FC<{p: Poster; t: number; tall: boolean; width: number}> = ({p, t, tall, width}) => {
  const tag = interpolate(t, [0.15, 0.6], [0, 1], clamp);
  const slam = interpolate(t, [0.45, 0.6], [0, 1], {...clamp, easing: (x) => 1 - (1 - x) ** 3});
  const bill = interpolate(t, [1.0, 1.5], [0, 1], clamp);
  const words = p.title.toUpperCase().split(/\s+/);
  const lines = words.length > 2 ? [words.slice(0, Math.ceil(words.length / 2)).join(' '), words.slice(Math.ceil(words.length / 2)).join(' ')] : [words.join(' ')];
  const longest = Math.max(...lines.map((l) => l.length));
  const size = Math.min(tall ? 170 : 150, (width * (tall ? 0.9 : 0.62)) / Math.max(4, longest * 0.5));
  return (
    <>
      <div style={{display: p.tagline ? 'block' : 'none', position: 'absolute', top: tall ? 210 : 150, left: 0, right: 0, textAlign: 'center', opacity: tag, fontFamily: 'Inter, sans-serif',
        fontWeight: 700, fontSize: tall ? 34 : 26, letterSpacing: tall ? 9 : 12, color: '#f3e9ff', textShadow: '0 0 18px rgba(200,80,255,0.7)'}}>
        {p.tagline.toUpperCase()}
      </div>
      <div style={{position: 'absolute', bottom: tall ? 250 : 150, left: 0, right: 0, textAlign: 'center'}}>
        <div style={{opacity: slam, transform: `scale(${1.8 - 0.8 * slam})`, fontFamily: 'Anton, Impact, sans-serif', fontSize: size, lineHeight: 0.95,
          letterSpacing: 3, color: '#fff', textShadow: '0 0 30px rgba(255,46,154,0.75), 0 0 60px rgba(41,211,255,0.45), 6px 6px 0 #000'}}>
          {lines.map((l, i) => (
            <div key={i}>{l}</div>
          ))}
        </div>
        <div style={{opacity: bill, marginTop: 18, padding: `0 ${tall ? 70 : 380}px`, fontFamily: 'Inter, sans-serif', fontWeight: 500,
          fontSize: tall ? 24 : 18, lineHeight: 1.35, letterSpacing: 4, color: 'rgba(255,255,255,0.78)', textTransform: 'uppercase'}}>
          {p.credits}
        </div>
        <div style={{opacity: bill, marginTop: 14, fontFamily: 'Anton, Impact, sans-serif', fontSize: tall ? 44 : 34, letterSpacing: 10, color: '#29d3ff',
          textShadow: '0 0 16px rgba(41,211,255,0.8)'}}>
          {p.date.toUpperCase()}
        </div>
      </div>
    </>
  );
};
