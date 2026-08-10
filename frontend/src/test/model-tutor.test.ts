import * as THREE from "three";
import { describe, expect, it } from "vitest";
import { createModelTutorRig, disposeModelTutorRig, updateModelTutorRig } from "../avatar/model-tutor";
import type { TutorPlaybackSignal, TutorRendererFrame } from "../avatar/renderer";

function modelFixture() {
  const root = new THREE.Group();
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(1, 2, 0.5), new THREE.MeshStandardMaterial());
  mesh.name = "Human";
  mesh.morphTargetDictionary = {
    jawOpen: 0,
    viseme_aa: 1,
    eyeBlinkLeft: 2,
    eyeBlinkRight: 3,
    mouthSmileLeft: 4,
    mouthSmileRight: 5,
  };
  mesh.morphTargetInfluences = [0, 0, 0, 0, 0, 0];
  root.add(mesh);
  const head = new THREE.Bone();
  head.name = "Head";
  root.add(head);
  const leftArm = new THREE.Bone();
  leftArm.name = "LeftArm";
  leftArm.rotation.set(0.45, 0.08, 0.09);
  root.add(leftArm);
  const rightArm = new THREE.Bone();
  rightArm.name = "RightArm";
  rightArm.rotation.set(0.45, -0.08, -0.09);
  root.add(rightArm);
  return { root, mesh, leftArm, rightArm };
}

const speaking: TutorRendererFrame = {
  state: "SPEAKING",
  expression: "NEUTRAL",
  mouth: "WIDE",
  blinkEnabled: true,
  motionEnabled: true,
};

const signal: TutorPlaybackSignal = {
  playbackId: "audio",
  amplitude: 0.2,
  currentTimeMs: 100,
  durationMs: 1_000,
};

describe("rigged natural tutor model controls", () => {
  it("drives facial blend shapes from the selected provider pose and stops outside speaking", () => {
    const fixture = modelFixture();
    const rig = createModelTutorRig(fixture.root);
    updateModelTutorRig(rig, speaking, { ...signal, amplitude: 0 }, 1, false);
    expect(fixture.mesh.morphTargetInfluences?.[0]).toBeGreaterThan(0.6);
    updateModelTutorRig(rig, { ...speaking, mouth: "SMALL" }, { ...signal, amplitude: 1 }, 1.5, false);
    expect(fixture.mesh.morphTargetInfluences?.[0]).toBeCloseTo(0.216);
    updateModelTutorRig(rig, { ...speaking, state: "LISTENING" }, signal, 2, false);
    expect(fixture.mesh.morphTargetInfluences?.[0]).toBe(0);
    disposeModelTutorRig(rig);
  });

  it("uses expression targets while reduced motion keeps the head still", () => {
    const fixture = modelFixture();
    const rig = createModelTutorRig(fixture.root);
    updateModelTutorRig(
      rig,
      { ...speaking, state: "SUCCESS", expression: "ENCOURAGING", motionEnabled: false },
      { ...signal, amplitude: 0 },
      4.8,
      true,
    );
    expect(fixture.mesh.morphTargetInfluences?.[4]).toBeGreaterThan(0.4);
    expect(rig.head?.rotation.x).toBe(0);
    disposeModelTutorRig(rig);
  });

  it("preserves the model-authored relaxed arm pose during natural motion", () => {
    const fixture = modelFixture();
    const leftBase = fixture.leftArm.rotation.clone();
    const rightBase = fixture.rightArm.rotation.clone();
    const rig = createModelTutorRig(fixture.root);

    updateModelTutorRig(rig, speaking, signal, 2.4, false);
    expect(fixture.leftArm.rotation.toArray()).toEqual(leftBase.toArray());
    expect(fixture.rightArm.rotation.toArray()).toEqual(rightBase.toArray());

    updateModelTutorRig(
      rig,
      { ...speaking, state: "LISTENING", motionEnabled: false },
      { ...signal, amplitude: 0 },
      4.8,
      true,
    );
    expect(fixture.leftArm.rotation.toArray()).toEqual(leftBase.toArray());
    expect(fixture.rightArm.rotation.toArray()).toEqual(rightBase.toArray());
    disposeModelTutorRig(rig);
  });
});
