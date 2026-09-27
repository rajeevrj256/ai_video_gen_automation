import React, {useEffect, useMemo, useState} from 'react';
import {OffthreadVideo, continueRender, delayRender, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig, Easing} from 'remotion';
import {ThreeCanvas} from '@remotion/three';
import {useThree} from '@react-three/fiber';
import * as THREE from 'three';
import {GLTFLoader} from 'three/examples/jsm/loaders/GLTFLoader.js';
import {COLORS, FONT, clamp, exitProgress} from '../theme';
import {Layer} from '../Layer';
import type {Part, Visual} from './types';

// Full-screen beats: a real stock clip of a place or scene, or a 3D model in its own world
// (a plane flying through clouds, a satellite in space, an object on a turntable).
// Both carry an optional caption at the bottom-left, like a documentary lower third.

export const Footage: React.FC<{v: Visual; frames: number; accent: string}> = ({v, frames, accent}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const seconds = frames / fps;
  // Start inside the clip so the stock intro is skipped, and never run past its end.
  const offset = v.length ? Math.max(0, Math.min(v.length * 0.2, v.length - seconds)) : 0;
  const zoom = interpolate(frame, [0, frames], [1.04, 1.12], clamp);
  const fade = interpolate(frame, [0, 8], [0, 1], clamp) * (1 - exitProgress(frame, frames, 9));
  return (
    <Layer name="footage" style={{opacity: fade, backgroundColor: COLORS.ink}}>
      <OffthreadVideo
        src={staticFile(v.src!)}
        muted
        trimBefore={Math.round(offset * fps)}
        style={{width: '100%', height: '100%', objectFit: 'cover', transform: `scale(${zoom})`}}
      />
      <div style={{position: 'absolute', inset: 0, background: 'linear-gradient(180deg, rgba(0,0,0,0.15) 0%, transparent 35%, transparent 55%, rgba(0,0,0,0.6) 100%)'}} />
      <LowerThird v={v} accent={accent} />
    </Layer>
  );
};

const LowerThird: React.FC<{v: Visual; accent: string}> = ({v, accent}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  if (!v.headline) return null;
  const e = spring({frame: frame - 10, fps, config: {damping: 14, mass: 0.7}});
  const bar = interpolate(frame, [8, 22], [0, 1], {...clamp, easing: Easing.out(Easing.cubic)});
  return (
    <div style={{position: 'absolute', left: 110, top: 90, fontFamily: FONT, color: COLORS.text, opacity: Math.min(1, e), transform: `translateX(${(1 - e) * -40}px)`}}>
      <div style={{width: 120 * bar, height: 7, background: accent, borderRadius: 4, marginBottom: 16, boxShadow: `0 0 18px ${accent}`}} />
      <div style={{fontSize: 64, fontWeight: 900, textShadow: '0 4px 24px rgba(0,0,0,0.7)'}}>{v.headline}</div>
      {v.sub ? <div style={{fontSize: 36, fontWeight: 600, opacity: 0.9, marginTop: 6, textShadow: '0 3px 16px rgba(0,0,0,0.7)'}}>{v.sub}</div> : null}
    </div>
  );
};

// ---------- 3D ----------

// Scales any object to fit a 2-unit box around the origin, so every model frames the same way.
const normalize = (obj: THREE.Object3D) => {
  obj.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(obj);
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  obj.position.sub(center);
  const wrap = new THREE.Group();
  wrap.add(obj);
  wrap.scale.setScalar(2 / Math.max(size.x, size.y, size.z, 1e-6));
  return wrap;
};

// Loads a .glb/.gltf once per beat. The glTF convention is +Y up and the front facing +Z,
// which the flying pose relies on.
const useModel = (src: string | undefined) => {
  const [model, setModel] = useState<THREE.Object3D | null>(null);
  const [handle] = useState(() => (src ? delayRender(`Loading 3D model ${src}`) : null));
  useEffect(() => {
    if (!src || handle === null) return;
    new GLTFLoader().load(
      staticFile(src),
      (gltf) => {
        setModel(normalize(gltf.scene));
        // Let React mount it and the GPU upload its textures before the frame is captured.
        requestAnimationFrame(() => requestAnimationFrame(() => requestAnimationFrame(() => continueRender(handle))));
      },
      undefined,
      (err) => {
        console.error(err);
        continueRender(handle); // a broken file shows the backdrop without a model, not a failed render
      },
    );
  }, [src, handle]);
  return model;
};

const MATERIALS: Record<string, (color: string) => THREE.Material> = {
  matte: (c) => new THREE.MeshStandardMaterial({color: c, roughness: 0.8, metalness: 0}),
  glossy: (c) => new THREE.MeshStandardMaterial({color: c, roughness: 0.25, metalness: 0.05}),
  metal: (c) => new THREE.MeshStandardMaterial({color: c, roughness: 0.3, metalness: 0.9}),
  glass: (c) => new THREE.MeshStandardMaterial({color: c, roughness: 0.05, metalness: 0, transparent: true, opacity: 0.45}),
  glow: (c) => new THREE.MeshStandardMaterial({color: c, emissive: c, emissiveIntensity: 1.2}),
};

// An object Claude designed from simple shapes, for things no ready-made model exists for.
const buildParts = (parts: Part[]) => {
  const group = new THREE.Group();
  for (const p of parts) {
    const [a = 1, b = a, c = a] = p.size;
    let geometry: THREE.BufferGeometry;
    let scale: [number, number, number] = [1, 1, 1];
    switch (p.shape) {
      case 'box':
        geometry = new THREE.BoxGeometry(a, b, c);
        break;
      case 'sphere':
        geometry = new THREE.SphereGeometry(0.5, 48, 32);
        scale = [a, p.size.length > 1 ? b : a, p.size.length > 2 ? c : a];
        break;
      case 'cylinder':
        geometry = new THREE.CylinderGeometry(0.5, 0.5, 1, 48);
        scale = [a, b, p.size.length > 2 ? c : a];
        break;
      case 'cone':
        geometry = new THREE.ConeGeometry(0.5, 1, 48);
        scale = [a, b, p.size.length > 2 ? c : a];
        break;
      case 'torus':
        geometry = new THREE.TorusGeometry(a / 2, Math.max(0.001, (p.size[1] ?? a * 0.2) / 2), 24, 64);
        break;
      default:
        geometry = new THREE.CapsuleGeometry(a / 2, Math.max(0, b - a), 8, 24);
    }
    const mesh = new THREE.Mesh(geometry, (MATERIALS[p.material ?? 'matte'] ?? MATERIALS.matte)(p.color || '#cccccc'));
    mesh.scale.set(...scale);
    mesh.position.set(p.position[0] ?? 0, p.position[1] ?? 0, p.position[2] ?? 0);
    const r = (p.rotation ?? [0, 0, 0]).map((d) => (d * Math.PI) / 180);
    mesh.rotation.set(r[0] ?? 0, r[1] ?? 0, r[2] ?? 0);
    group.add(mesh);
  }
  group.updateMatrixWorld(true);
  return normalize(group);
};

export const Model3D: React.FC<{v: Visual; frames: number; accent: string}> = ({v, frames, accent}) => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const loaded = useModel(v.src);
  const built = useMemo(() => (!v.src && v.parts?.length ? buildParts(v.parts) : null), [v.src, v.parts]);
  const model = loaded ?? built;
  const scene = v.scene ?? 'studio';
  const fade = interpolate(frame, [0, 8], [0, 1], clamp) * (1 - exitProgress(frame, frames, 9));
  const t = frame / fps;
  const enter = spring({frame, fps, config: {damping: 16, mass: 1.1}});

  // Pose per world: flying right through the sky, drifting in space, turning on a turntable.
  const pose = (() => {
    if (scene === 'sky') {
      return {
        x: interpolate(enter, [0, 1], [-5.5, -0.4]) + t * 0.05,
        y: 0.15 * Math.sin(t * 1.4),
        z: 0,
        rx: 0.06 * Math.sin(t * 1.1), // pitch
        ry: Math.PI / 2 - 0.45, // nose right, turned a little toward the camera
        rz: -0.12 + 0.08 * Math.sin(t * 0.9), // gentle bank
        scale: 1.25,
      };
    }
    if (scene === 'space') {
      return {x: 0, y: 0.1 * Math.sin(t * 0.6), z: 0, rx: 0.3 + 0.05 * t, ry: 0.25 * t, rz: 0.1, scale: 1.2 * enter};
    }
    return {x: 0, y: -0.1, z: 0, rx: 0.25, ry: -0.6 + 0.45 * t, rz: 0, scale: 1.25 * enter};
  })();

  return (
    <Layer name={`3d ${scene}`} style={{opacity: fade}}>
      {scene === 'sky' ? <Sky frame={frame} back /> : scene === 'space' ? <Space frame={frame} /> : <Studio accent={accent} />}
      <ThreeCanvas width={width} height={height} camera={{fov: 35, position: [0, 0.4, 7]}} gl={{alpha: true, antialias: true}}>
        <ambientLight intensity={scene === 'space' ? 0.5 : 1.0} />
        <hemisphereLight args={['#dff1ff', '#6b7b8c', scene === 'space' ? 0.4 : 1.1]} />
        <directionalLight position={[4, 6, 5]} intensity={scene === 'space' ? 3 : 2.2} />
        <directionalLight position={[-5, 2, -3]} intensity={0.6} color={accent} />
        <Redraw dep={model} />
        {model ? (
          <group position={[pose.x, pose.y, pose.z]} rotation={[pose.rx, pose.ry, pose.rz]} scale={pose.scale}>
            <primitive object={model} />
          </group>
        ) : null}
      </ThreeCanvas>
      {scene === 'sky' ? <Sky frame={frame} /> : null}
      <LowerThird v={v} accent={accent} />
    </Layer>
  );
};

// The canvas only draws when the frame changes; a model that finishes loading later needs a draw of its own.
const Redraw: React.FC<{dep: unknown}> = ({dep}) => {
  const advance = useThree((s) => s.advance);
  useEffect(() => {
    advance(performance.now());
  }, [dep, advance]);
  return null;
};

// Soft clouds made of blurred ellipses. The back layer is the sky with slow clouds; the front
// layer has a few big, fast, faint clouds passing in front of the model, so it feels like flight.
const CLOUDS = Array.from({length: 14}, (_, i) => ({
  y: (i * 37) % 90,
  w: 380 + ((i * 131) % 420),
  h: 110 + ((i * 53) % 90),
  speed: 2.2 + ((i * 7) % 5) * 0.9,
  start: (i * 283) % 2400,
}));

const Sky: React.FC<{frame: number; back?: boolean}> = ({frame, back}) => {
  const {width} = useVideoConfig();
  const clouds = back ? CLOUDS : CLOUDS.filter((_, i) => i % 4 === 0);
  const speed = back ? 1 : 5;
  return (
    <Layer name={back ? 'sky' : 'near clouds'} style={back ? {background: 'linear-gradient(180deg, #4d8fd6 0%, #86bff0 55%, #d8ecfb 100%)'} : {}}>
      {back ? <div style={{position: 'absolute', right: 180, top: 90, width: 260, height: 260, borderRadius: '50%', background: 'radial-gradient(circle, rgba(255,250,220,0.95), rgba(255,240,200,0) 70%)'}} /> : null}
      {clouds.map((c, i) => {
        const span = width + c.w * 2;
        const x = span - ((c.start + frame * c.speed * speed) % span) - c.w;
        return (
          <div
            key={i}
            style={{
              position: 'absolute',
              left: x,
              top: `${back ? c.y : 60 + (c.y % 30)}%`,
              width: c.w * (back ? 1 : 2.2),
              height: c.h * (back ? 1 : 2),
              borderRadius: '50%',
              background: 'radial-gradient(ellipse, rgba(255,255,255,0.95) 0%, rgba(255,255,255,0.6) 45%, rgba(255,255,255,0) 72%)',
              filter: `blur(${back ? 6 : 18}px)`,
              opacity: back ? 0.85 : 0.55,
            }}
          />
        );
      })}
    </Layer>
  );
};

const STARS = Array.from({length: 160}, (_, i) => ({x: (i * 73.3) % 100, y: (i * 41.7) % 100, r: 1 + (i % 3), tw: i % 7}));

const Space: React.FC<{frame: number}> = ({frame}) => (
  <Layer name="space" style={{background: 'radial-gradient(ellipse at 70% 30%, #1b2a55 0%, #070b1a 60%, #02030a 100%)'}}>
    {STARS.map((s, i) => (
      <div
        key={i}
        style={{
          position: 'absolute',
          left: `${(s.x + frame * 0.01 * (1 + s.r)) % 100}%`,
          top: `${s.y}%`,
          width: s.r * 2,
          height: s.r * 2,
          borderRadius: '50%',
          background: 'white',
          opacity: 0.4 + 0.5 * Math.abs(Math.sin(frame / 20 + s.tw)),
        }}
      />
    ))}
  </Layer>
);

const Studio: React.FC<{accent: string}> = ({accent}) => (
  <Layer name="studio" style={{background: `radial-gradient(ellipse at 50% 45%, ${accent}33 0%, ${COLORS.ink} 65%)`}}>
    <div style={{position: 'absolute', left: '50%', top: '72%', width: 900, height: 140, transform: 'translate(-50%, -50%)', borderRadius: '50%', background: 'radial-gradient(ellipse, rgba(0,0,0,0.55), transparent 70%)'}} />
  </Layer>
);
