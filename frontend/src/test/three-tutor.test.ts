import { describe, expect, it } from "vitest";
import type { TutorPlaybackSignal, TutorRendererFrame } from "../avatar/renderer";
import { createThreeTutorRig, disposeThreeTutorRig, updateThreeTutorRig } from "../avatar/three-tutor";

const baseFrame: TutorRendererFrame = {
  state: "SPEAKING",
  expression: "NEUTRAL",
  mouth: "REST",
  blinkEnabled: true,
  motionEnabled: true,
};

const signal: TutorPlaybackSignal = {
  playbackId: "turn-3d",
  amplitude: 0,
  currentTimeMs: 250,
  durationMs: 1000,
};

describe("genuine Three.js tutor rig", () => {
  it("builds volumetric head, upper-body, face, and teaching-attire geometry", () => {
    const rig = createThreeTutorRig();
    const roles = new Set<string>();
    let meshCount = 0;
    rig.root.traverse((child) => {
      if (child.userData.role) roles.add(String(child.userData.role));
      if (child.type === "Mesh") meshCount += 1;
    });
    expect(rig.root.userData.renderer).toBe("genuine-webgl-geometry");
    expect(meshCount).toBeGreaterThan(25);
    expect(roles.has("face")).toBe(true);
    expect(roles.has("teacher-blazer")).toBe(true);
    expect(roles.has("left-dupatta-drape")).toBe(true);
    expect(roles.has("mouth-interior")).toBe(true);
    disposeThreeTutorRig(rig);
  });

  it("drives real 3D mouth geometry from the selected provider pose, not raw amplitude", () => {
    const rig = createThreeTutorRig();
    updateThreeTutorRig(rig, baseFrame, { ...signal, amplitude: 1 }, 1, false);
    const silentScale = rig.mouthInterior.scale.y;
    updateThreeTutorRig(rig, { ...baseFrame, mouth: "WIDE" }, { ...signal, amplitude: 0 }, 1.1, false);
    expect(rig.mouthInterior.scale.y).toBeGreaterThan(silentScale + 1);
    updateThreeTutorRig(rig, { ...baseFrame, state: "LISTENING", mouth: "WIDE" }, { ...signal, amplitude: 1 }, 1.2, false);
    expect(rig.mouthInterior.scale.y).toBeCloseTo(0.08);
    disposeThreeTutorRig(rig);
  });

  it("supports listening, thinking, success, and retry posture while reduced motion stays still", () => {
    const rig = createThreeTutorRig();
    updateThreeTutorRig(rig, { ...baseFrame, state: "THINKING" }, signal, 2, false);
    expect(rig.head.rotation.y).toBeGreaterThan(0);
    updateThreeTutorRig(rig, { ...baseFrame, state: "RETRY", expression: "CORRECTIVE" }, signal, 3, false);
    expect(rig.head.rotation.z).toBeGreaterThan(0);
    const reducedRig = createThreeTutorRig();
    updateThreeTutorRig(
      reducedRig,
      { ...baseFrame, state: "SPEAKING", motionEnabled: false, blinkEnabled: false },
      { ...signal, amplitude: 0.8 },
      4.8,
      true,
    );
    expect([
      reducedRig.head.rotation.x,
      reducedRig.head.rotation.y,
      reducedRig.head.rotation.z,
    ]).toEqual([0, 0, 0]);
    expect(reducedRig.leftLid.scale.y).toBeCloseTo(0.02);
    expect(reducedRig.mouthInterior.scale.y).toBeCloseTo(0.08);
    disposeThreeTutorRig(rig);
    disposeThreeTutorRig(reducedRig);
  });
});
