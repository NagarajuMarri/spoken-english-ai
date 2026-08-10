import { describe, expect, it, vi } from "vitest";
import {
  AmplitudeLipSyncProvider,
  SpeakMateMultimediaRuntime,
  type MultimediaAnimationClock,
  type MultimediaAudioEvent,
  type MultimediaAudioPort,
  type MultimediaRenderer,
  type MultimediaRuntimeNotification,
} from "../multimedia";

function clockFixture() {
  let listener: ((timestampMs: number) => void) | undefined;
  const stop = vi.fn();
  const clock: MultimediaAnimationClock = {
    start: vi.fn((next) => {
      listener = next;
      return stop;
    }),
  };
  return { clock, stop, tick: (timestampMs: number) => listener?.(timestampMs) };
}

function renderer(id = "model", profile: MultimediaRenderer["profile"] = "MODEL") {
  return { id, profile, render: vi.fn(), dispose: vi.fn() } satisfies MultimediaRenderer;
}

describe("SpeakMate multimedia runtime", () => {
  it("coordinates semantic tutor, audio, expression, and measured lip-sync events", () => {
    const animation = clockFixture();
    const visual = renderer();
    const notifications: MultimediaRuntimeNotification[] = [];
    const runtime = new SpeakMateMultimediaRuntime({
      renderers: [visual],
      lipSyncProvider: new AmplitudeLipSyncProvider(),
      animationClock: animation.clock,
      onNotification: (event) => notifications.push(event),
    });

    runtime.start();
    runtime.handle({ type: "TUTOR_RESPONSE_READY", expression: "POSITIVE" });
    runtime.handle({ type: "AUDIO_SOURCE_READY", source: { playbackId: "turn-1", durationMs: 1_000 } });
    runtime.handle({ type: "AUDIO_PLAYBACK_STARTED", playbackId: "turn-1" });
    runtime.handle({
      type: "AUDIO_PLAYBACK_FRAME",
      frame: { playbackId: "turn-1", amplitude: 0.2, currentTimeMs: 120, durationMs: 1_000 },
    });

    expect(runtime.snapshot()).toMatchObject({
      presentation: { state: "SPEAKING", expression: "POSITIVE", mouth: "WIDE" },
      playback: { playbackId: "turn-1", amplitude: 0.2 },
      lipSync: { mouth: "WIDE", source: "MEASURED_AMPLITUDE" },
      rendererId: "model",
    });
    expect(notifications).toEqual(expect.arrayContaining([
      expect.objectContaining({ type: "TUTOR_STATE_CHANGED", state: "SPEAKING" }),
      expect.objectContaining({ type: "TUTOR_EXPRESSION_CHANGED", expression: "POSITIVE" }),
      expect.objectContaining({ type: "LIP_SYNC_CHANGED", mouth: "WIDE" }),
      expect.objectContaining({ type: "AUDIO_LIFECYCLE", event: "AUDIO_PLAYBACK_STARTED" }),
    ]));

    runtime.handle({
      type: "AUDIO_PLAYBACK_FRAME",
      frame: { playbackId: "stale-turn", amplitude: 1, currentTimeMs: 200, durationMs: 1_000 },
    });
    expect(runtime.snapshot()).toMatchObject({
      presentation: { mouth: "WIDE" },
      playback: { playbackId: "turn-1", amplitude: 0.2 },
    });
  });

  it("falls back deterministically when the preferred renderer fails", () => {
    const preferred = renderer("webgl-model", "MODEL");
    preferred.render.mockImplementation(() => { throw new Error("context lost"); });
    const fallback = renderer("portrait", "PORTRAIT");
    const notifications: MultimediaRuntimeNotification[] = [];
    const runtime = new SpeakMateMultimediaRuntime({
      renderers: [preferred, fallback],
      lipSyncProvider: new AmplitudeLipSyncProvider(),
      animationClock: clockFixture().clock,
      onNotification: (event) => notifications.push(event),
    });

    runtime.start();

    expect(fallback.render).toHaveBeenCalledOnce();
    expect(preferred.dispose).toHaveBeenCalledOnce();
    expect(runtime.snapshot()).toMatchObject({ rendererId: "portrait", rendererProfile: "PORTRAIT" });
    expect(notifications).toContainEqual({
      type: "RENDERER_FALLBACK",
      fromRendererId: "webgl-model",
      toRendererId: "portrait",
      reason: "RENDER_FAILED",
    });
    runtime.dispose();
    expect(preferred.dispose).toHaveBeenCalledOnce();
    expect(fallback.dispose).toHaveBeenCalledOnce();
  });

  it("does not leave an animation clock running when every renderer is unavailable", () => {
    const animation = clockFixture();
    const unavailable = renderer("broken-model", "MODEL");
    unavailable.render.mockImplementation(() => { throw new Error("unavailable"); });
    const runtime = new SpeakMateMultimediaRuntime({
      renderers: [unavailable],
      lipSyncProvider: new AmplitudeLipSyncProvider(),
      animationClock: animation.clock,
    });

    runtime.start();

    expect(animation.clock.start).not.toHaveBeenCalled();
    expect(runtime.snapshot()).toMatchObject({ rendererId: null, rendererProfile: null });
  });

  it("stops continuous animation and freezes the mouth under reduced motion", () => {
    const animation = clockFixture();
    const visual = renderer();
    const runtime = new SpeakMateMultimediaRuntime({
      renderers: [visual],
      lipSyncProvider: new AmplitudeLipSyncProvider(),
      animationClock: animation.clock,
    });
    runtime.start();
    runtime.handle({ type: "AUDIO_SOURCE_READY", source: { playbackId: "turn-2" } });
    runtime.handle({ type: "AUDIO_PLAYBACK_STARTED", playbackId: "turn-2" });
    runtime.handle({ type: "REDUCED_MOTION_CHANGED", reducedMotion: true });
    runtime.handle({
      type: "AUDIO_PLAYBACK_FRAME",
      frame: { playbackId: "turn-2", amplitude: 0.5, currentTimeMs: 80, durationMs: 700 },
    });

    expect(animation.stop).toHaveBeenCalledOnce();
    expect(runtime.snapshot()).toMatchObject({ reducedMotion: true, lipSync: { mouth: "REST" } });
    expect(visual.render).toHaveBeenLastCalledWith(expect.objectContaining({
      reducedMotion: true,
      frame: expect.objectContaining({ mouth: "REST", motionEnabled: false }),
    }));
  });

  it("accepts any replaceable LipSyncProvider without changing audio or renderer contracts", () => {
    const visual = renderer();
    const customProvider = {
      id: "future-provider-visemes",
      reset: vi.fn(),
      sample: vi.fn(() => ({ mouth: "SMALL" as const, confidence: 0.99, source: "PROVIDER_VISEME" as const })),
    };
    const runtime = new SpeakMateMultimediaRuntime({
      renderers: [visual],
      lipSyncProvider: customProvider,
      animationClock: clockFixture().clock,
    });
    runtime.start();
    runtime.handle({ type: "AUDIO_SOURCE_READY", source: { playbackId: "turn-provider" } });
    runtime.handle({ type: "AUDIO_PLAYBACK_STARTED", playbackId: "turn-provider" });
    runtime.handle({
      type: "AUDIO_PLAYBACK_FRAME",
      frame: { playbackId: "turn-provider", amplitude: 0, currentTimeMs: 40, durationMs: 500 },
    });

    expect(customProvider.sample).toHaveBeenCalledOnce();
    expect(runtime.snapshot().lipSync).toEqual({ mouth: "SMALL", confidence: 0.99, source: "PROVIDER_VISEME" });
  });

  it("can attach and detach a provider-neutral audio port", () => {
    let listener: ((event: MultimediaAudioEvent) => void) | undefined;
    const unsubscribe = vi.fn();
    const port: MultimediaAudioPort = {
      subscribe: vi.fn((next) => {
        listener = next;
        return unsubscribe;
      }),
      play: vi.fn(async () => true),
      replay: vi.fn(async () => true),
      pause: vi.fn(),
      stop: vi.fn(),
      setMuted: vi.fn(),
    };
    const runtime = new SpeakMateMultimediaRuntime({
      renderers: [renderer()],
      lipSyncProvider: new AmplitudeLipSyncProvider(),
      animationClock: clockFixture().clock,
    });
    runtime.start();
    const detach = runtime.attachAudio(port);
    listener?.({ type: "AUDIO_SOURCE_READY", source: { playbackId: "port-turn" } });

    expect(runtime.snapshot().playback.playbackId).toBe("port-turn");
    detach();
    expect(unsubscribe).toHaveBeenCalledOnce();
  });

  it("does not let stale terminal events reset a newer playback", () => {
    const runtime = new SpeakMateMultimediaRuntime({
      renderers: [renderer()],
      lipSyncProvider: new AmplitudeLipSyncProvider(),
      animationClock: clockFixture().clock,
    });
    runtime.start();
    runtime.handle({ type: "AUDIO_SOURCE_READY", source: { playbackId: "old-turn" } });
    runtime.handle({ type: "AUDIO_SOURCE_READY", source: { playbackId: "current-turn" } });
    runtime.handle({ type: "AUDIO_PLAYBACK_STARTED", playbackId: "current-turn" });
    runtime.handle({
      type: "AUDIO_PLAYBACK_FRAME",
      frame: { playbackId: "current-turn", amplitude: 0.22, currentTimeMs: 100, durationMs: 800 },
    });

    for (const type of [
      "AUDIO_PLAYBACK_PAUSED",
      "AUDIO_PLAYBACK_STOPPED",
      "AUDIO_PLAYBACK_ENDED",
    ] as const) runtime.handle({ type, playbackId: "old-turn" });
    runtime.handle({ type: "AUDIO_PLAYBACK_ERROR", playbackId: "old-turn", errorCode: "stale" });

    expect(runtime.snapshot()).toMatchObject({
      presentation: { state: "SPEAKING", mouth: "WIDE", activePlaybackId: "current-turn" },
      playback: { playbackId: "current-turn", amplitude: 0.22 },
      lipSync: { mouth: "WIDE" },
    });
  });

  it("a stale detach closure cannot unsubscribe a replacement audio port", () => {
    const firstDetach = vi.fn();
    const secondDetach = vi.fn();
    const port = (detach: () => void): MultimediaAudioPort => ({
      subscribe: vi.fn(() => detach),
      play: vi.fn(async () => true),
      replay: vi.fn(async () => true),
      pause: vi.fn(),
      stop: vi.fn(),
      setMuted: vi.fn(),
    });
    const runtime = new SpeakMateMultimediaRuntime({
      renderers: [renderer()],
      lipSyncProvider: new AmplitudeLipSyncProvider(),
      animationClock: clockFixture().clock,
    });
    runtime.start();
    const detachFirst = runtime.attachAudio(port(firstDetach));
    runtime.attachAudio(port(secondDetach));
    detachFirst();

    expect(firstDetach).toHaveBeenCalledOnce();
    expect(secondDetach).not.toHaveBeenCalled();
    runtime.dispose();
    expect(secondDetach).toHaveBeenCalledOnce();
  });
});
