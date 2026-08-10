import { describe, expect, it, vi } from "vitest";
import {
  AmplitudeLipSyncProvider,
  EventDrivenAnimationClock,
  MultimediaAudioController,
  SpeakMateMultimediaRuntime,
  type MultimediaAudioTransport,
  type MultimediaRenderer,
} from "../multimedia";

describe("production multimedia audio port", () => {
  it("attaches one transport and routes commands plus lifecycle through the runtime", async () => {
    const transport: MultimediaAudioTransport = {
      play: vi.fn(async () => true),
      replay: vi.fn(async () => true),
      pause: vi.fn(),
      stop: vi.fn(),
      setMuted: vi.fn(),
    };
    const audio = new MultimediaAudioController();
    audio.attachTransport(transport);
    const visual: MultimediaRenderer = {
      id: "react",
      profile: "CUSTOM",
      render: vi.fn(),
    };
    const runtime = new SpeakMateMultimediaRuntime({
      renderers: [visual],
      lipSyncProvider: new AmplitudeLipSyncProvider(),
      animationClock: new EventDrivenAnimationClock(),
    });
    runtime.attachAudio(audio);
    runtime.start();

    expect(await runtime.playAudio()).toBe(true);
    expect(await runtime.replayAudio()).toBe(true);
    runtime.pauseAudio();
    runtime.stopAudio();
    runtime.setAudioMuted(true);
    expect(transport.play).toHaveBeenCalledOnce();
    expect(transport.replay).toHaveBeenCalledOnce();
    expect(transport.pause).toHaveBeenCalledOnce();
    expect(transport.stop).toHaveBeenCalledOnce();
    expect(transport.setMuted).toHaveBeenCalledWith(true);

    audio.publish({ type: "AUDIO_SOURCE_READY", source: { playbackId: "controlled-turn" } });
    audio.publish({ type: "AUDIO_PLAYBACK_STARTED", playbackId: "controlled-turn" });
    audio.publish({
      type: "AUDIO_PLAYBACK_FRAME",
      frame: {
        playbackId: "controlled-turn",
        amplitude: 0.2,
        currentTimeMs: 80,
        durationMs: 700,
      },
    });
    expect(runtime.snapshot()).toMatchObject({
      presentation: { state: "SPEAKING", mouth: "WIDE" },
      playback: { playbackId: "controlled-turn" },
    });

    audio.attachTransport(null);
    expect(await runtime.playAudio()).toBe(false);
    runtime.dispose();
  });
});
