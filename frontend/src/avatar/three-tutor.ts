import * as THREE from "three";
import {
  ANANYA_NATURAL_MOTION_SEED,
  createNaturalMotionController,
  type NaturalMotionController,
} from "../multimedia/natural-motion";
import { mouthPoseFromShape, type TutorPlaybackSignal, type TutorRendererFrame } from "./renderer";

export interface ThreeTutorRig {
  root: THREE.Group;
  head: THREE.Group;
  torso: THREE.Group;
  leftEye: THREE.Group;
  rightEye: THREE.Group;
  leftLid: THREE.Mesh;
  rightLid: THREE.Mesh;
  leftBrow: THREE.Mesh;
  rightBrow: THREE.Mesh;
  mouthInterior: THREE.Mesh;
  upperLip: THREE.Mesh;
  lowerLip: THREE.Mesh;
  naturalMotion: NaturalMotionController;
}

function physical(color: THREE.ColorRepresentation, roughness = 0.72, metalness = 0) {
  return new THREE.MeshPhysicalMaterial({ color, roughness, metalness });
}

function mesh(
  geometry: THREE.BufferGeometry,
  material: THREE.Material,
  name: string,
) {
  const result = new THREE.Mesh(geometry, material);
  result.name = name;
  result.userData.role = name;
  result.castShadow = true;
  result.receiveShadow = true;
  return result;
}

function faceCurve(
  points: readonly [number, number, number][],
  material: THREE.Material,
  name: string,
  radius: number,
) {
  const path = new THREE.CatmullRomCurve3(points.map(([x, y, z]) => new THREE.Vector3(x, y, z)));
  return mesh(new THREE.TubeGeometry(path, 24, radius, 10, false), material, name);
}

function addEye(parent: THREE.Group, x: number, skin: THREE.Material, white: THREE.Material) {
  const eye = new THREE.Group();
  eye.position.set(x, 0.2, 0.68);
  eye.name = x < 0 ? "left-eye" : "right-eye";

  const sclera = mesh(new THREE.SphereGeometry(0.12, 32, 20), white, `${eye.name}-sclera`);
  sclera.scale.set(1.18, 0.78, 0.52);
  eye.add(sclera);

  const iris = mesh(new THREE.CircleGeometry(0.062, 32), physical(0x3f2f28, 0.48), `${eye.name}-iris`);
  iris.position.z = 0.069;
  eye.add(iris);

  const pupil = mesh(new THREE.CircleGeometry(0.027, 24), physical(0x11100f, 0.42), `${eye.name}-pupil`);
  pupil.position.z = 0.071;
  eye.add(pupil);

  const highlight = mesh(new THREE.CircleGeometry(0.009, 16), physical(0xffffff, 0.2), `${eye.name}-highlight`);
  highlight.position.set(-0.017, 0.02, 0.073);
  eye.add(highlight);

  const lid = mesh(new THREE.CircleGeometry(0.145, 40), skin, `${eye.name}-lid`);
  lid.position.z = 0.078;
  lid.scale.set(1, 0.02, 1);
  eye.add(lid);
  return { eye, lid };
}

export function createThreeTutorRig(
  motionSeed: string | number = ANANYA_NATURAL_MOTION_SEED,
): ThreeTutorRig {
  const skin = physical(0xa96f55, 0.68);
  const skinHighlight = physical(0xbd8064, 0.64);
  const hair = physical(0x1c1517, 0.74);
  const blazer = physical(0x183d59, 0.8);
  const blouse = physical(0xf3eee5, 0.84);
  const teal = physical(0x0f786f, 0.72);
  const lip = physical(0x8e3f46, 0.56);
  const mouth = physical(0x2b1014, 0.92);
  const eyeWhite = physical(0xf3eee8, 0.46);
  const gold = physical(0xc79c46, 0.35, 0.72);

  const root = new THREE.Group();
  root.name = "ananya-three-dimensional-tutor";
  root.userData.renderer = "genuine-webgl-geometry";

  const torso = new THREE.Group();
  torso.name = "upper-body-rig";
  torso.position.y = -1.18;
  root.add(torso);

  const jacket = mesh(new THREE.SphereGeometry(1.28, 56, 36), blazer, "teacher-blazer");
  jacket.scale.set(1.04, 0.96, 0.5);
  torso.add(jacket);

  const shirt = mesh(new THREE.CapsuleGeometry(0.4, 0.82, 12, 32), blouse, "teacher-blouse");
  shirt.position.set(0, 0.18, 0.55);
  shirt.scale.set(1, 1, 0.36);
  torso.add(shirt);

  const leftShoulder = mesh(new THREE.CapsuleGeometry(0.26, 0.7, 10, 28), blazer, "left-shoulder");
  leftShoulder.position.set(-0.96, -0.04, 0.03);
  leftShoulder.rotation.z = -0.72;
  torso.add(leftShoulder);
  const rightShoulder = leftShoulder.clone();
  rightShoulder.name = "right-shoulder";
  rightShoulder.userData.role = "right-shoulder";
  rightShoulder.position.x = 0.96;
  rightShoulder.rotation.z = 0.72;
  torso.add(rightShoulder);

  const leftDrape = mesh(new THREE.CapsuleGeometry(0.075, 1.18, 8, 20), teal, "left-dupatta-drape");
  leftDrape.position.set(-0.47, 0.05, 0.63);
  leftDrape.rotation.z = -0.12;
  torso.add(leftDrape);
  const rightDrape = leftDrape.clone();
  rightDrape.name = "right-dupatta-drape";
  rightDrape.userData.role = "right-dupatta-drape";
  rightDrape.position.x = 0.47;
  rightDrape.rotation.z = 0.12;
  torso.add(rightDrape);

  const neck = mesh(new THREE.CylinderGeometry(0.24, 0.3, 0.54, 36), skin, "neck");
  neck.position.y = -0.34;
  root.add(neck);

  const head = new THREE.Group();
  head.name = "head-rig";
  head.position.y = 0.45;
  root.add(head);

  const hairBack = mesh(new THREE.SphereGeometry(0.83, 64, 44), hair, "hair-volume");
  hairBack.scale.set(0.94, 1.13, 0.9);
  hairBack.position.set(0, 0.03, -0.08);
  head.add(hairBack);

  const face = mesh(new THREE.SphereGeometry(0.73, 64, 48), skin, "face");
  face.scale.set(0.87, 1.08, 0.84);
  face.position.z = 0.1;
  head.add(face);

  const jaw = mesh(new THREE.SphereGeometry(0.56, 48, 32), skinHighlight, "jaw-and-cheeks");
  jaw.scale.set(0.88, 0.58, 0.82);
  jaw.position.set(0, -0.32, 0.26);
  head.add(jaw);

  const hairCap = mesh(
    new THREE.SphereGeometry(0.755, 64, 32, 0, Math.PI * 2, 0, Math.PI * 0.48),
    hair,
    "hair-cap",
  );
  hairCap.scale.set(0.9, 1.12, 0.9);
  hairCap.position.set(0, 0.12, 0.13);
  head.add(hairCap);

  for (const side of [-1, 1] as const) {
    const lock = mesh(new THREE.CapsuleGeometry(0.105, 0.92, 10, 24), hair, `${side < 0 ? "left" : "right"}-hair-lock`);
    lock.position.set(side * 0.59, -0.17, 0.18);
    lock.rotation.z = side * 0.12;
    head.add(lock);
    const ear = mesh(new THREE.SphereGeometry(0.12, 30, 20), skinHighlight, `${side < 0 ? "left" : "right"}-ear`);
    ear.scale.set(0.55, 1, 0.42);
    ear.position.set(side * 0.66, 0.01, 0.12);
    head.add(ear);
    const earring = mesh(new THREE.TorusGeometry(0.048, 0.012, 12, 28), gold, `${side < 0 ? "left" : "right"}-earring`);
    earring.position.set(side * 0.67, -0.14, 0.18);
    head.add(earring);
  }

  const left = addEye(head, -0.255, skin, eyeWhite);
  const right = addEye(head, 0.255, skin, eyeWhite);

  const browMaterial = physical(0x2b1c1b, 0.78);
  const leftBrow = faceCurve([[-0.39, 0.38, 0.72], [-0.26, 0.42, 0.76], [-0.12, 0.38, 0.73]], browMaterial, "left-brow", 0.024);
  const rightBrow = faceCurve([[0.12, 0.38, 0.73], [0.26, 0.42, 0.76], [0.39, 0.38, 0.72]], browMaterial, "right-brow", 0.024);
  head.add(leftBrow, rightBrow);

  const nose = mesh(new THREE.ConeGeometry(0.095, 0.3, 32), skinHighlight, "nose");
  nose.rotation.x = Math.PI / 2;
  nose.position.set(0, 0.03, 0.75);
  head.add(nose);

  const mouthInterior = mesh(new THREE.CircleGeometry(0.17, 40), mouth, "mouth-interior");
  mouthInterior.position.set(0, -0.22, 0.805);
  mouthInterior.scale.set(1, 0.08, 1);
  head.add(mouthInterior);

  const teethMaterial = physical(0xf7f2e8, 0.5);
  const upperTeeth = mesh(new THREE.PlaneGeometry(0.22, 0.032), teethMaterial, "upper-teeth");
  upperTeeth.position.set(0, -0.205, 0.815);
  head.add(upperTeeth);
  const lowerTeeth = mesh(new THREE.PlaneGeometry(0.18, 0.024), teethMaterial, "lower-teeth");
  lowerTeeth.position.set(0, -0.235, 0.814);
  head.add(lowerTeeth);

  const upperLip = faceCurve([[-0.16, -0.2, 0.82], [0, -0.17, 0.84], [0.16, -0.2, 0.82]], lip, "upper-lip", 0.026);
  const lowerLip = faceCurve([[-0.16, -0.22, 0.82], [0, -0.255, 0.84], [0.16, -0.22, 0.82]], lip, "lower-lip", 0.028);
  head.add(upperLip, lowerLip);

  const bindi = mesh(new THREE.SphereGeometry(0.025, 24, 16), physical(0x8a2430, 0.5), "bindi");
  bindi.scale.z = 0.25;
  bindi.position.set(0, 0.47, 0.69);
  head.add(bindi);

  return {
    root,
    head,
    torso,
    leftEye: left.eye,
    rightEye: right.eye,
    leftLid: left.lid,
    rightLid: right.lid,
    leftBrow,
    rightBrow,
    mouthInterior,
    upperLip,
    lowerLip,
    naturalMotion: createNaturalMotionController(motionSeed),
  };
}

export function updateThreeTutorRig(
  rig: ThreeTutorRig,
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
  rig.mouthInterior.scale.y = 0.08 + mouthOpen * 1.7;
  rig.mouthInterior.scale.x = 1 - mouthPose.funnel * 0.26 + mouthPose.width * 0.08;
  rig.upperLip.position.y = mouthOpen * 0.035;
  rig.lowerLip.position.y = -mouthOpen * 0.055;

  const smile = frame.expression === "POSITIVE" || frame.expression === "ENCOURAGING" ? 1 : 0;
  rig.upperLip.rotation.z = smile * -0.025;
  rig.lowerLip.rotation.z = smile * 0.025;
  rig.leftBrow.rotation.z = frame.expression === "CORRECTIVE" ? -0.1 : -0.025 * smile;
  rig.rightBrow.rotation.z = frame.expression === "CORRECTIVE" ? 0.1 : 0.025 * smile;

  rig.leftLid.scale.y = 0.02 + naturalMotion.blink * 0.96;
  rig.rightLid.scale.y = 0.02 + naturalMotion.blink * 0.96;

  const eyeTravelX = naturalMotion.gazeX * 0.012;
  const eyeTravelY = naturalMotion.gazeY * 0.008;
  rig.leftEye.position.set(-0.255 + eyeTravelX, 0.2 + eyeTravelY, 0.68);
  rig.rightEye.position.set(0.255 + eyeTravelX, 0.2 + eyeTravelY, 0.68);

  const breath = naturalMotion.breath * 0.008;
  rig.torso.scale.set(1 + breath * 0.22, 1 + breath, 1 + breath * 0.12);

  let targetX = naturalMotion.headPitch * 0.012;
  let targetY = naturalMotion.headYaw * 0.018;
  let targetZ = naturalMotion.headRoll * 0.01;
  if (moving && frame.state === "LISTENING") {
    targetY = naturalMotion.headYaw * 0.025;
    targetZ = -0.025 + naturalMotion.headRoll * 0.007;
  } else if (moving && frame.state === "THINKING") {
    targetY = 0.1 + naturalMotion.headYaw * 0.008;
    targetZ = -0.045 + naturalMotion.headRoll * 0.006;
  } else if (moving && frame.state === "SPEAKING") {
    targetX = naturalMotion.headPitch * 0.022;
    targetY = naturalMotion.headYaw * 0.03;
  } else if (moving && frame.state === "SUCCESS") {
    targetX = -0.018 + naturalMotion.headPitch * 0.022;
  } else if (moving && frame.state === "RETRY") {
    targetZ = 0.055 + naturalMotion.headRoll * 0.006;
    targetY = -0.045 + naturalMotion.headYaw * 0.006;
  }
  if (!moving) {
    rig.head.rotation.set(0, 0, 0);
    return;
  }
  rig.head.rotation.x = THREE.MathUtils.lerp(rig.head.rotation.x, targetX, 0.08);
  rig.head.rotation.y = THREE.MathUtils.lerp(rig.head.rotation.y, targetY, 0.08);
  rig.head.rotation.z = THREE.MathUtils.lerp(rig.head.rotation.z, targetZ, 0.08);
}

export function disposeThreeTutorRig(rig: ThreeTutorRig) {
  rig.root.traverse((child) => {
    if (!(child instanceof THREE.Mesh)) return;
    child.geometry.dispose();
    const materials = Array.isArray(child.material) ? child.material : [child.material];
    for (const material of materials) material.dispose();
  });
}
