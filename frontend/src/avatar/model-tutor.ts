import * as THREE from "three";
import {
  ANANYA_NATURAL_MOTION_SEED,
  createNaturalMotionController,
  type NaturalMotionController,
} from "../multimedia/natural-motion";
import { mouthPoseFromShape, type TutorPlaybackSignal, type TutorRendererFrame } from "./renderer";

interface MorphBinding {
  dictionary: Record<string, number>;
  influences: number[];
}

export interface ModelTutorRig {
  root: THREE.Object3D;
  height: number;
  head?: THREE.Object3D;
  neck?: THREE.Object3D;
  spine?: THREE.Object3D;
  leftArm?: THREE.Object3D;
  rightArm?: THREE.Object3D;
  leftForeArm?: THREE.Object3D;
  rightForeArm?: THREE.Object3D;
  morphs: Map<string, MorphBinding[]>;
  baseHead?: THREE.Euler;
  baseNeck?: THREE.Euler;
  baseSpine?: THREE.Euler;
  baseLeftArm?: THREE.Euler;
  baseRightArm?: THREE.Euler;
  baseLeftForeArm?: THREE.Euler;
  baseRightForeArm?: THREE.Euler;
  naturalMotion: NaturalMotionController;
}

type MorphMesh = THREE.Mesh & {
  morphTargetDictionary?: Record<string, number>;
  morphTargetInfluences?: number[];
};

function materialList(material: THREE.Material | THREE.Material[]) {
  return Array.isArray(material) ? material : [material];
}

function tuneAppearance(mesh: THREE.Mesh) {
  const materials = materialList(mesh.material);
  for (const material of materials) {
    if (!(material instanceof THREE.MeshStandardMaterial)) continue;
    if (mesh.name === "Human") {
      material.color.set(0xd5a087);
      material.roughness = 0.68;
    } else if (mesh.name.includes("female_casualsuit01")) {
      material.map = null;
      material.color.set(0x244f63);
      material.roughness = 0.78;
    }
    material.needsUpdate = true;
  }
}

export function createModelTutorRig(
  root: THREE.Object3D,
  motionSeed: string | number = ANANYA_NATURAL_MOTION_SEED,
): ModelTutorRig {
  const morphs = new Map<string, MorphBinding[]>();
  root.traverse((object) => {
    if (!(object instanceof THREE.Mesh)) return;
    object.castShadow = true;
    object.receiveShadow = true;
    tuneAppearance(object);
    const mesh = object as MorphMesh;
    if (!mesh.morphTargetDictionary || !mesh.morphTargetInfluences) return;
    const binding: MorphBinding = {
      dictionary: mesh.morphTargetDictionary,
      influences: mesh.morphTargetInfluences,
    };
    for (const name of Object.keys(binding.dictionary)) {
      const existing = morphs.get(name) ?? [];
      existing.push(binding);
      morphs.set(name, existing);
    }
  });

  root.updateWorldMatrix(true, true);
  const bounds = new THREE.Box3().setFromObject(root);
  const size = bounds.getSize(new THREE.Vector3());
  const center = bounds.getCenter(new THREE.Vector3());
  root.position.x -= center.x;
  root.position.y -= bounds.min.y;
  root.updateWorldMatrix(true, true);

  const head = root.getObjectByName("Head");
  const neck = root.getObjectByName("Neck");
  const spine = root.getObjectByName("Spine2") ?? root.getObjectByName("Spine");
  const leftArm = root.getObjectByName("LeftArm");
  const rightArm = root.getObjectByName("RightArm");
  const leftForeArm = root.getObjectByName("LeftForeArm");
  const rightForeArm = root.getObjectByName("RightForeArm");
  return {
    root,
    height: Math.max(1, size.y),
    head,
    neck,
    spine,
    leftArm,
    rightArm,
    leftForeArm,
    rightForeArm,
    morphs,
    baseHead: head?.rotation.clone(),
    baseNeck: neck?.rotation.clone(),
    baseSpine: spine?.rotation.clone(),
    baseLeftArm: leftArm?.rotation.clone(),
    baseRightArm: rightArm?.rotation.clone(),
    baseLeftForeArm: leftForeArm?.rotation.clone(),
    baseRightForeArm: rightForeArm?.rotation.clone(),
    naturalMotion: createNaturalMotionController(motionSeed),
  };
}

function setMorph(rig: ModelTutorRig, name: string, value: number) {
  for (const binding of rig.morphs.get(name) ?? []) {
    const index = binding.dictionary[name];
    if (index !== undefined) binding.influences[index] = THREE.MathUtils.clamp(value, 0, 1);
  }
}

function resetBone(object: THREE.Object3D | undefined, base: THREE.Euler | undefined) {
  if (object && base) object.rotation.copy(base);
}

export function updateModelTutorRig(
  rig: ModelTutorRig,
  frame: TutorRendererFrame,
  _signal: TutorPlaybackSignal,
  elapsedSeconds: number,
  reducedMotion: boolean,
) {
  const moving = frame.motionEnabled && !reducedMotion;
  const naturalMotion = rig.naturalMotion.sample({
    elapsedSeconds,
    enabled: frame.motionEnabled,
    blinkEnabled: frame.blinkEnabled,
    reducedMotion,
  });
  const selectedMouth = moving && frame.state === "SPEAKING" ? frame.mouth : "REST";
  const mouthPose = mouthPoseFromShape(selectedMouth);
  const mouthOpen = mouthPose.openness;
  setMorph(rig, "jawOpen", mouthOpen * 0.72);
  setMorph(rig, "viseme_aa", mouthOpen * (0.28 + mouthPose.width * 0.24));
  setMorph(rig, "mouthFunnel", mouthPose.funnel);
  setMorph(rig, "mouthPucker", mouthPose.funnel * 0.72);
  setMorph(rig, "mouthClose", selectedMouth === "MBP" ? 0.88 : 0);
  setMorph(rig, "mouthLowerDownLeft", selectedMouth === "FV" ? 0.18 : 0);
  setMorph(rig, "mouthLowerDownRight", selectedMouth === "FV" ? 0.18 : 0);

  const success = frame.state === "SUCCESS" || frame.expression === "POSITIVE" || frame.expression === "ENCOURAGING";
  const retry = frame.state === "RETRY" || frame.expression === "CORRECTIVE";
  setMorph(rig, "mouthSmileLeft", success ? 0.42 : 0);
  setMorph(rig, "mouthSmileRight", success ? 0.42 : 0);
  setMorph(rig, "mouthFrownLeft", retry ? 0.15 : 0);
  setMorph(rig, "mouthFrownRight", retry ? 0.15 : 0);
  setMorph(rig, "browInnerUp", retry ? 0.32 : 0);
  setMorph(rig, "browDownLeft", frame.state === "THINKING" ? 0.12 : 0);
  setMorph(rig, "browDownRight", frame.state === "THINKING" ? 0.12 : 0);

  setMorph(rig, "eyeBlinkLeft", naturalMotion.blink);
  setMorph(rig, "eyeBlinkRight", naturalMotion.blink);
  const eyeTravel = naturalMotion.gazeX * 0.12;
  setMorph(rig, "eyeLookInLeft", Math.max(0, eyeTravel));
  setMorph(rig, "eyeLookOutLeft", Math.max(0, -eyeTravel));
  setMorph(rig, "eyeLookInRight", Math.max(0, -eyeTravel));
  setMorph(rig, "eyeLookOutRight", Math.max(0, eyeTravel));
  const verticalEyeTravel = naturalMotion.gazeY * 0.08;
  setMorph(rig, "eyeLookUpLeft", Math.max(0, verticalEyeTravel));
  setMorph(rig, "eyeLookUpRight", Math.max(0, verticalEyeTravel));
  setMorph(rig, "eyeLookDownLeft", Math.max(0, -verticalEyeTravel));
  setMorph(rig, "eyeLookDownRight", Math.max(0, -verticalEyeTravel));

  resetBone(rig.head, rig.baseHead);
  resetBone(rig.neck, rig.baseNeck);
  resetBone(rig.spine, rig.baseSpine);
  resetBone(rig.leftArm, rig.baseLeftArm);
  resetBone(rig.rightArm, rig.baseRightArm);
  resetBone(rig.leftForeArm, rig.baseLeftForeArm);
  resetBone(rig.rightForeArm, rig.baseRightForeArm);
  if (!moving) return;

  let pitch = naturalMotion.headPitch * 0.007;
  let yaw = naturalMotion.headYaw * 0.012;
  let roll = naturalMotion.headRoll * 0.006;
  if (frame.state === "LISTENING") {
    yaw = naturalMotion.headYaw * 0.022;
    roll = -0.018 + naturalMotion.headRoll * 0.005;
  } else if (frame.state === "THINKING") {
    yaw = 0.075 + naturalMotion.headYaw * 0.006;
    roll = -0.025 + naturalMotion.headRoll * 0.004;
  } else if (frame.state === "SPEAKING") {
    pitch = naturalMotion.headPitch * 0.014;
    yaw = naturalMotion.headYaw * 0.025;
  } else if (frame.state === "SUCCESS") {
    pitch = -0.009 + naturalMotion.headPitch * 0.015;
  } else if (frame.state === "RETRY") {
    yaw = -0.035 + naturalMotion.headYaw * 0.005;
    roll = 0.026 + naturalMotion.headRoll * 0.004;
  }
  if (rig.head && rig.baseHead) {
    rig.head.rotation.set(rig.baseHead.x + pitch, rig.baseHead.y + yaw, rig.baseHead.z + roll, rig.baseHead.order);
  }
  if (rig.neck && rig.baseNeck) {
    rig.neck.rotation.set(
      rig.baseNeck.x + pitch * 0.35,
      rig.baseNeck.y + yaw * 0.3,
      rig.baseNeck.z + roll * 0.25,
      rig.baseNeck.order,
    );
  }
  if (rig.spine && rig.baseSpine) {
    const breath = naturalMotion.breath * 0.004;
    rig.spine.rotation.set(
      rig.baseSpine.x + breath,
      rig.baseSpine.y,
      rig.baseSpine.z,
      rig.baseSpine.order,
    );
  }
}

export function disposeModelTutorRig(rig: ModelTutorRig) {
  const geometries = new Set<THREE.BufferGeometry>();
  const materials = new Set<THREE.Material>();
  const textures = new Set<THREE.Texture>();
  rig.root.traverse((object) => {
    if (!(object instanceof THREE.Mesh)) return;
    geometries.add(object.geometry);
    for (const material of materialList(object.material)) {
      materials.add(material);
      for (const value of Object.values(material)) {
        if (value instanceof THREE.Texture) textures.add(value);
      }
    }
  });
  for (const texture of textures) texture.dispose();
  for (const geometry of geometries) geometry.dispose();
  for (const material of materials) material.dispose();
  rig.root.removeFromParent();
}
