import { describe, expect, it } from "vitest";
import { AmplitudeLipSyncProvider, PhonemeLipSyncProvider, StaticLipSyncProvider } from "../multimedia";
import { mouthShapeFromGrapheme } from "../multimedia/lip-sync-providers";

describe("provider-neutral lip-sync adapters", () => {
  it("uses measured amplitude only for the active playback source", () => {
    const provider = new AmplitudeLipSyncProvider();
    provider.reset({ playbackId: "active" });

    expect(provider.sample({ playbackId: "active", amplitude: 0.12, currentTimeMs: 10, durationMs: 100 }).mouth).toBe("MEDIUM");
    expect(provider.sample({ playbackId: "stale", amplitude: 1, currentTimeMs: 10, durationMs: 100 })).toMatchObject({
      mouth: "REST",
      source: "STATIC",
    });
  });

  it("provides an explicit static fallback", () => {
    const provider = new StaticLipSyncProvider();
    expect(provider.sample({ playbackId: "any", amplitude: 1, currentTimeMs: 10, durationMs: 100 })).toEqual({
      mouth: "REST",
      confidence: 1,
      source: "STATIC",
    });
  });

  it("maps useful English and Telugu sound families to distinct visemes", () => {
    expect(mouthShapeFromGrapheme("m")).toBe("MBP");
    expect(mouthShapeFromGrapheme("f")).toBe("FV");
    expect(mouthShapeFromGrapheme("l")).toBe("L");
    expect(mouthShapeFromGrapheme("e")).toBe("EE");
    expect(mouthShapeFromGrapheme("o")).toBe("OH");
    expect(mouthShapeFromGrapheme("ూ")).toBe("OO");
    expect(mouthShapeFromGrapheme(" ")).toBe("REST");
  });

  it("uses the spoken text timeline before measured-amplitude fallback", () => {
    const provider = new PhonemeLipSyncProvider();
    provider.reset({ playbackId: "turn", spokenText: "ma" });
    expect(provider.sample({ playbackId: "turn", amplitude: 0, currentTimeMs: 10, durationMs: 1_000 })).toMatchObject({
      mouth: "MBP",
      source: "PHONEME_VISEME",
    });
    expect(provider.sample({ playbackId: "turn", amplitude: 0, currentTimeMs: 700, durationMs: 1_000 })).toMatchObject({
      mouth: "AH",
      source: "PHONEME_VISEME",
    });
    expect(provider.sample({ playbackId: "turn", amplitude: 1, currentTimeMs: 1_000, durationMs: 1_000 })).toEqual({
      mouth: "REST",
      confidence: 1,
      source: "STATIC",
    });
  });

  it("falls back to the real audio amplitude when source text is unavailable", () => {
    const provider = new PhonemeLipSyncProvider();
    provider.reset({ playbackId: "audio-only" });
    expect(provider.sample({ playbackId: "audio-only", amplitude: 0.2, currentTimeMs: 10, durationMs: 100 })).toMatchObject({
      mouth: "WIDE",
      source: "MEASURED_AMPLITUDE",
    });
  });
});
