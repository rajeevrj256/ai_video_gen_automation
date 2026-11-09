// 🧪 A character from a real 3D model instead of the code-built body (experiment, branch claude/lowpoly-3d-ethan; the
// user: "lets do for one char and animation ethan ... not delete old code or old style of ethan"). The model is a
// textured mesh made by an image-to-3D generator from an A-pose picture of him (a statue: no skeleton). Here it gets one:
// - SKELETONS[name] lists where its joints are, measured on the mesh (metres, feet at y = 0, facing +z);
// - every vertex is weighted to the bones by region (arms out to the side, legs below the sweater's hem, the head above
//   the collar), blended across each joint, once per model;
// - each frame the bones take the very same Pose the code-built Man takes (poses.ts), so every action, walk, seat, car
//   and camera works unchanged. The model is scaled so its hips are where the Man's are (HIP), so seats, pedals and
//   floors line up. Its face is painted on: it doesn't blink or talk (yet).
// A design with `model` set draws this (Man.tsx hands it over); every other design keeps the code-built body.
import React, {useEffect, useMemo, useState} from 'react';
import {createPortal, useThree} from '@react-three/fiber';
import {continueRender, delayRender, staticFile} from 'remotion';
import * as THREE from 'three';
import {GLTFLoader} from 'three/examples/jsm/loaders/GLTFLoader.js';
import {HIP} from './poses';
import type {Face, Pose} from './poses';
import type {Hold} from './types';

type V3 = [number, number, number];
type Joints = {
  file: string; // under the render's public folder
  shiftY: number; // the mesh's feet are at -shiftY: added so they stand on y = 0
  hip: number; // hip joints' height (the pelvis bone), metres in the model
  hipX: number;
  knee: number;
  ankle: V3; // the bottom of the shin bone (the foot goes with it)
  waist: [number, number]; // the sweater's hem: torso above the first, leg below the second (blended between)
  neck: V3;
  collar: [number, number]; // head above the second, torso below the first
  top: number;
  face: number; // the head's centre (eyes level): where the cameras aim
  shoulder: V3; // the left ones (x < 0); the right side is mirrored
  elbow: V3;
  wrist: V3;
  hand: V3; // the fingertips
  torsoHalf: number; // half the body's width: arms begin outside it
  armFrom: number; // below this height only far-out points are arm (the hands), never the trousers
};

// Ethan, from the A-pose picture (Hyper3D Rodin v2.5 Fast). Measured on the mesh: slices every 5 cm, the gap between the
// legs (crotch at 0.62), the arm's centre line (shoulder to fingertips at 45 degrees).
export const SKELETONS: Record<string, Joints> = {
  ethan: {
    file: 'models/ethan.glb',
    shiftY: 0.857,
    hip: 0.697,
    hipX: 0.11,
    knee: 0.427,
    ankle: [0.12, 0.16, 0.0],
    waist: [0.74, 0.66],
    neck: [0, 1.3, -0.02],
    collar: [1.27, 1.33],
    top: 1.714,
    face: 1.51,
    shoulder: [0.2, 1.177, -0.02],
    elbow: [0.36, 1.03, -0.02],
    wrist: [0.5, 0.877, 0.03],
    hand: [0.66, 0.74, 0.08],
    torsoHalf: 0.21,
    armFrom: 0.84,
  },
};

// The head's centre above the pelvis, in the world, for a design with a model (LowPoly.tsx's cameras aim there; the
// code-built Man's is HEAD_Y): the model is shorter in the body, so its head is lower.
export const modelHead = (model?: string) => {
  const j = model ? SKELETONS[model] : undefined;
  return j ? ((j.face - j.hip) * HIP) / j.hip : undefined;
};

// Bones: 0 pelvis, 1 torso, 2 head, 3/4 left upper/fore arm, 5/6 right, 7/8 left thigh/shin, 9/10 right.
const PARENT = [-1, 0, 1, 1, 3, 1, 5, 0, 7, 0, 9];

const v = (a: V3) => new THREE.Vector3(a[0], a[1], a[2]);
const mirror = (a: V3, s: number): V3 => [a[0] * s, a[1], a[2]];
const smooth = (a: number, b: number, x: number) => {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)));
  return t * t * (3 - 2 * t);
};

// Where each bone starts, in the model (feet at 0); and the direction it points (its rest, measured).
const bonePlaces = (j: Joints) => {
  const at: V3[] = [];
  const dir: THREE.Vector3[] = [];
  at[0] = [0, j.hip, 0];
  at[1] = [0, j.hip, 0];
  at[2] = j.neck;
  for (const [s, u, f] of [[-1, 3, 4], [1, 5, 6]] as const) {
    at[u] = mirror(j.shoulder, s);
    at[f] = mirror(j.elbow, s);
    dir[u] = v(at[f]).sub(v(at[u])).normalize();
    dir[f] = v(mirror(j.wrist, s)).sub(v(at[f])).normalize();
  }
  for (const [s, t, sh] of [[-1, 7, 8], [1, 9, 10]] as const) {
    at[t] = [s * j.hipX, j.hip, 0];
    at[sh] = [s * j.hipX, j.knee, 0];
    dir[t] = v(at[sh]).sub(v(at[t])).normalize();
    dir[sh] = v(mirror(j.ankle, s)).sub(v(at[sh])).normalize();
  }
  return {at, dir};
};

// Distance from p to the segment a-b, and how far along it (0..1).
const along = (p: THREE.Vector3, a: THREE.Vector3, b: THREE.Vector3) => {
  const ab = b.clone().sub(a);
  const t = Math.min(1, Math.max(0, p.clone().sub(a).dot(ab) / ab.lengthSq()));
  return {t, d: a.clone().addScaledVector(ab, t).distanceTo(p)};
};

// The skin: up to four bones per vertex, by region, blended across the joints.
const skinWeights = (pos: THREE.BufferAttribute, j: Joints) => {
  const n = pos.count;
  const idx = new Uint16Array(n * 4);
  const wt = new Float32Array(n * 4);
  const p = new THREE.Vector3();
  const L = (s: number, a: V3) => v(mirror(a, s));
  for (let i = 0; i < n; i++) {
    p.fromBufferAttribute(pos, i);
    const w = new Map<number, number>();
    const add = (b: number, x: number) => x > 1e-4 && w.set(b, (w.get(b) ?? 0) + x);
    const s = p.x < 0 ? -1 : 1;
    const ax = Math.abs(p.x);
    // an arm: outside the body's width, high enough (or far enough out to be a hand); blended over 6 cm at the shoulder
    const arm = (p.y > j.armFrom || ax > 0.4) && p.y > j.wrist[1] - 0.25 ? smooth(j.torsoHalf - 0.01, j.torsoHalf + 0.06, ax) : 0;
    const rest = 1 - arm;
    if (arm > 0) {
      const [u, f] = s < 0 ? [3, 4] : [5, 6];
      const sh = L(s, j.shoulder);
      const el = L(s, j.elbow);
      const up = along(p, sh, el);
      const lo = along(p, el, L(s, j.hand));
      // which side of the elbow: by distance, blended where the two segments meet
      const fore = up.t > 0.85 || lo.d < up.d ? smooth(-0.05, 0.05, up.d - lo.d + (up.t - 0.9) * 0.2) : 0;
      add(u, arm * (1 - fore));
      add(f, arm * fore);
    }
    if (rest > 0) {
      const head = smooth(j.collar[0], j.collar[1], p.y);
      const leg = 1 - smooth(j.waist[1], j.waist[0], p.y);
      const body = (1 - head) * (1 - leg);
      add(2, rest * head);
      add(1, rest * body);
      if (leg > 0) {
        const [t, sh] = s < 0 ? [7, 8] : [9, 10];
        const shin = 1 - smooth(j.knee - 0.05, j.knee + 0.05, p.y);
        add(t, rest * leg * (1 - shin));
        add(sh, rest * leg * shin);
      }
    }
    const top = [...w.entries()].sort((a, b) => b[1] - a[1]).slice(0, 4);
    const sum = top.reduce((a, [, x]) => a + x, 0) || 1;
    top.forEach(([b, x], k) => {
      idx[i * 4 + k] = b;
      wt[i * 4 + k] = x / sum;
    });
    if (!top.length) {
      idx[i * 4] = 1;
      wt[i * 4] = 1;
    }
  }
  return {idx, wt};
};

type Loaded = {geometry: THREE.BufferGeometry; material: THREE.Material};
const cache = new Map<string, Promise<Loaded>>();
const loadModel = (name: string, j: Joints) => {
  let pr = cache.get(name);
  if (!pr) {
    pr = new Promise<Loaded>((ok, no) =>
      new GLTFLoader().load(
        staticFile(j.file),
        (gltf) => {
          let mesh: THREE.Mesh | null = null;
          gltf.scene.traverse((o) => {
            if (!mesh && (o as THREE.Mesh).isMesh) mesh = o as THREE.Mesh;
          });
          if (!mesh) return no(new Error(`no mesh in ${j.file}`));
          const m = mesh as THREE.Mesh;
          const geometry = m.geometry.clone();
          geometry.translate(0, j.shiftY, 0);
          const {idx, wt} = skinWeights(geometry.getAttribute('position') as THREE.BufferAttribute, j);
          geometry.setAttribute('skinIndex', new THREE.Uint16BufferAttribute(idx, 4));
          geometry.setAttribute('skinWeight', new THREE.Float32BufferAttribute(wt, 4));
          const material = (m.material as THREE.MeshStandardMaterial).clone();
          material.metalness = 0; // no environment to reflect: a metal surface would go black
          material.roughness = 1;
          ok({geometry, material});
        },
        undefined,
        no,
      ),
    );
    cache.set(name, pr);
  }
  return pr;
};

const useLoaded = (name: string, j: Joints) => {
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [handle] = useState(() => delayRender(`Loading the 3D model ${name}`, {timeoutInMilliseconds: 120000}));
  useEffect(() => {
    let live = true;
    loadModel(name, j)
      .then((l) => live && setLoaded(l))
      .catch((e) => console.error(e))
      .finally(() => requestAnimationFrame(() => requestAnimationFrame(() => continueRender(handle))));
    return () => {
      live = false;
    };
  }, [name, j, handle]);
  return loaded;
};

// The rig for one instance: its bones (identity rotations at rest), its skinned mesh, and the alignments that turn
// "hanging straight down" (how the Man's limbs rest) into the model's own rest directions.
const buildRig = (l: Loaded, j: Joints) => {
  const {at, dir} = bonePlaces(j);
  const bones = at.map(() => new THREE.Bone());
  bones.forEach((b, i) => {
    const pa = PARENT[i];
    const here = v(at[i]);
    b.position.copy(pa < 0 ? here : here.sub(v(at[pa])));
    if (pa >= 0) bones[pa].add(b);
  });
  const mesh = new THREE.SkinnedMesh(l.geometry, l.material);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  mesh.frustumCulled = false;
  mesh.add(bones[0]);
  mesh.updateMatrixWorld(true);
  mesh.bind(new THREE.Skeleton(bones));
  const down = new THREE.Vector3(0, -1, 0);
  const align = dir.map((d) => (d ? new THREE.Quaternion().setFromUnitVectors(d, down) : new THREE.Quaternion()));
  return {mesh, bones, align, at};
};

const q = (x: number, y: number, z: number) => new THREE.Quaternion().setFromEuler(new THREE.Euler(x, y, z));

// Pose the bones exactly as Man.tsx poses its groups: the pelvis at p.y, the body [rx, 0, rz], the torso
// [lean, twist, side], each limb [x, 0, ±z] from its socket and its middle joint bent [bend, 0, 0], the head p.head.
const applyPose = (r: ReturnType<typeof buildRig>, p: Pose, scale: number) => {
  const {bones, align} = r;
  bones[0].position.set(0, p.y / scale, 0);
  bones[0].quaternion.copy(q(p.rx, 0, p.rz));
  bones[1].quaternion.copy(q(p.lean, p.twist, p.side));
  bones[2].quaternion.copy(q(p.head[0], p.head[1], p.head[2]));
  const limb = (a: number, b: number, l: Pose['armL'], s: number) => {
    bones[a].quaternion.copy(q(l.x, 0, s * l.z).multiply(align[a]));
    bones[b].quaternion.copy(align[a].clone().invert().multiply(q(l.bend, 0, 0)).multiply(align[b]));
  };
  limb(3, 4, p.armL, -1);
  limb(5, 6, p.armR, 1);
  limb(7, 8, p.legL, -1);
  limb(9, 10, p.legR, 1);
};

export const ModelMan: React.FC<{
  model: string;
  pose: Pose;
  face: Face;
  root: V3;
  ry: number;
  hold?: Hold;
  height?: number;
  Held?: React.FC<{hold: Hold}>;
}> = ({model, pose: p, root, ry, hold = 'none', height = 1, Held}) => {
  const j = SKELETONS[model];
  const loaded = useLoaded(model, j);
  const rig = useMemo(() => (loaded ? buildRig(loaded, j) : null), [loaded, j]);
  const scale = HIP / j.hip; // the model's hips where the Man's are
  // the canvas draws only when the frame changes: draw once more when the model arrives (as long/Media.tsx's Redraw)
  const advance = useThree((s) => s.advance);
  useEffect(() => {
    if (rig) advance(performance.now());
  }, [rig, advance]);
  if (rig) {
    applyPose(rig, p, scale);
    rig.mesh.updateMatrixWorld(true);
  }
  // the right hand's frame, as the Man's (the forearm hanging along -y), for what he holds
  const hand = useMemo(() => {
    if (!rig) return null;
    const g = new THREE.Group();
    g.position.copy(v(mirror(j.wrist, 1)).sub(v(mirror(j.elbow, 1))));
    g.quaternion.copy(rig.align[6].clone().invert());
    rig.bones[6].add(g);
    return g;
  }, [rig, j]);
  return (
    <group position={root} rotation={[0, ry, 0]} scale={scale * height}>
      {rig ? <primitive object={rig.mesh} /> : null}
      {hand && hold !== 'none' && Held
        ? createPortal(
            <group position={[0, -0.09, 0]}>
              <Held hold={hold} />
            </group>,
            hand,
          )
        : null}
    </group>
  );
};
