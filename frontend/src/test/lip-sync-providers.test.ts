import { describe, expect, it } from "vitest";
import { AmplitudeLipSyncProvider, StaticLipSyncProvider } from "../multimedia";

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
});
