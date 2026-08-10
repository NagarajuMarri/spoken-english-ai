import { describe, expect, it } from "vitest";
import {
  createNaturalMotionController,
  NEUTRAL_NATURAL_MOTION,
  type NaturalMotionInput,
} from "../multimedia/natural-motion";

const activeInput: Omit<NaturalMotionInput, "elapsedSeconds"> = {
  enabled: true,
  blinkEnabled: true,
  reducedMotion: false,
};

function sampleAt(seed: string, elapsedSeconds: number) {
  return createNaturalMotionController(seed).sample({ ...activeInput, elapsedSeconds });
}

describe("seeded natural motion", () => {
  it("is deterministic for a seed regardless of sampling history", () => {
    const first = createNaturalMotionController("ananya-seed-42");
    const second = createNaturalMotionController("ananya-seed-42");
    const times = [0, 0.7, 2.4, 5.8, 12.25, 31.75];
    expect(times.map((elapsedSeconds) => first.sample({ ...activeInput, elapsedSeconds })))
      .toEqual(times.map((elapsedSeconds) => second.sample({ ...activeInput, elapsedSeconds })));

    const direct = sampleAt("ananya-seed-42", 31.75);
    expect(first.sample({ ...activeInput, elapsedSeconds: 31.75 })).toEqual(direct);
    expect(sampleAt("another-seed", 31.75)).not.toEqual(direct);
  });

  it("produces bounded, irregular blinks and subtle motion channels", () => {
    const controller = createNaturalMotionController("blink-schedule-seed");
    const blinkStarts: number[] = [];
    const maxima = {
      blink: 0,
      gazeX: 0,
      gazeY: 0,
      headPitch: 0,
      headYaw: 0,
      headRoll: 0,
      breath: 0,
    };
    let blinking = false;
    for (let step = 0; step <= 3_000; step += 1) {
      const elapsedSeconds = step / 50;
      const sample = controller.sample({ ...activeInput, elapsedSeconds });
      maxima.blink = Math.max(maxima.blink, Math.abs(sample.blink));
      maxima.gazeX = Math.max(maxima.gazeX, Math.abs(sample.gazeX));
      maxima.gazeY = Math.max(maxima.gazeY, Math.abs(sample.gazeY));
      maxima.headPitch = Math.max(maxima.headPitch, Math.abs(sample.headPitch));
      maxima.headYaw = Math.max(maxima.headYaw, Math.abs(sample.headYaw));
      maxima.headRoll = Math.max(maxima.headRoll, Math.abs(sample.headRoll));
      maxima.breath = Math.max(maxima.breath, Math.abs(sample.breath));
      const nowBlinking = sample.blink > 0.001;
      if (nowBlinking && !blinking) blinkStarts.push(elapsedSeconds);
      blinking = nowBlinking;
    }

    expect(maxima.blink).toBeLessThanOrEqual(1);
    expect(maxima.gazeX).toBeLessThanOrEqual(0.82);
    expect(maxima.gazeY).toBeLessThanOrEqual(0.52);
    expect(maxima.headPitch).toBeLessThanOrEqual(0.62);
    expect(maxima.headYaw).toBeLessThanOrEqual(0.78);
    expect(maxima.headRoll).toBeLessThanOrEqual(0.55);
    expect(maxima.breath).toBeLessThanOrEqual(1);
    expect(maxima.blink).toBeGreaterThan(0.8);
    expect(blinkStarts.length).toBeGreaterThan(8);
    const gaps = blinkStarts.slice(1).map((start, index) => (start - blinkStarts[index]).toFixed(2));
    expect(new Set(gaps).size).toBeGreaterThan(4);
  });

  it("returns neutral motion for reduced motion or a disabled presentation", () => {
    const controller = createNaturalMotionController("neutral-seed");
    const active = controller.sample({ ...activeInput, elapsedSeconds: 9.35 });
    expect(Object.values(active).some((value) => Math.abs(value) > 0.001)).toBe(true);
    expect(controller.sample({
      ...activeInput,
      elapsedSeconds: 9.35,
      reducedMotion: true,
    })).toEqual(NEUTRAL_NATURAL_MOTION);
    expect(controller.sample({
      ...activeInput,
      elapsedSeconds: 9.35,
      enabled: false,
    })).toEqual(NEUTRAL_NATURAL_MOTION);

    const blinkDisabled = controller.sample({
      ...activeInput,
      elapsedSeconds: 9.35,
      blinkEnabled: false,
    });
    expect(blinkDisabled.blink).toBe(0);
    expect(Object.values(blinkDisabled).some((value) => Math.abs(value) > 0.001)).toBe(true);
  });
});
