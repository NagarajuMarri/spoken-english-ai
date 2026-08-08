import { describe, expect, it } from "vitest";
import { approximateLipSync, mouthShapeAtPlaybackTime, mouthShapeFromContract } from "../avatar/lip-sync";

describe("lip sync boundary", () => {
  it("creates bounded deterministic provider-neutral visemes", () => {
    const first = approximateLipSync("audio", 500, 120);
    const second = approximateLipSync("audio", 500, 120);
    expect(first).toEqual(second);
    expect(first.visemes.at(-1)?.end_ms).toBe(500);
  });

  it("classifies the non-phoneme fallback honestly", () => {
    expect(approximateLipSync("audio", 200).status).toBe("APPROXIMATE");
  });

  it("derives mouth shapes from real playback position without timers", () => {
    expect(mouthShapeAtPlaybackTime(0, 1000)).toBe("SMALL");
    expect(mouthShapeAtPlaybackTime(120, 1000)).toBe("MEDIUM");
    expect(mouthShapeAtPlaybackTime(240, 1000)).toBe("WIDE");
    expect(mouthShapeAtPlaybackTime(1000, 1000)).toBe("REST");
  });

  it("can consume provider visemes later without changing the renderer", () => {
    const contract = approximateLipSync("audio", 500, 120);
    expect(mouthShapeFromContract(contract, 240)).toBe("WIDE");
    expect(mouthShapeFromContract(contract, 600)).toBe("REST");
  });
});
