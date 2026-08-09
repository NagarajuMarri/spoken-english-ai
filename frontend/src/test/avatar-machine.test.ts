import { describe, expect, it } from "vitest";
import {
  initialTutorPresentation,
  normalizeExpression,
  reduceTutorPresentation,
  type TutorEvent,
} from "../avatar/machine";

function run(...events: TutorEvent[]) {
  return events.reduce(reduceTutorPresentation, initialTutorPresentation);
}

describe("renderer-neutral tutor presentation controller", () => {
  it("moves through listening and thinking without claiming speech", () => {
    expect(run({ type: "MICROPHONE_STARTED" }).state).toBe("LISTENING");
    const thinking = run({ type: "MICROPHONE_STARTED" }, { type: "TUTOR_PROCESSING_STARTED" });
    expect(thinking).toMatchObject({ state: "THINKING", mouth: "REST" });
  });

  it("enters speaking only after the active audio source really starts", () => {
    const ready = run(
      { type: "TUTOR_RESPONSE_READY", expression: "CORRECTIVE" },
      { type: "AUDIO_SOURCE_READY", playbackId: "turn-1" },
    );
    expect(ready).toMatchObject({ state: "THINKING", expression: "CORRECTIVE", mouth: "REST" });
    const speaking = reduceTutorPresentation(ready, { type: "AUDIO_PLAYBACK_STARTED", playbackId: "turn-1" });
    expect(speaking).toMatchObject({ state: "SPEAKING", expression: "CORRECTIVE", mouth: "SMALL" });
  });

  it("moves the mouth from actual playback position and resets on end", () => {
    let presentation = run(
      { type: "TUTOR_RESPONSE_READY", expression: "POSITIVE" },
      { type: "AUDIO_SOURCE_READY", playbackId: "turn-1" },
      { type: "AUDIO_PLAYBACK_STARTED", playbackId: "turn-1" },
    );
    presentation = reduceTutorPresentation(presentation, { type: "AUDIO_PLAYBACK_FRAME", playbackId: "turn-1", currentTimeMs: 240, durationMs: 1000 });
    expect(presentation.mouth).toBe("WIDE");
    presentation = reduceTutorPresentation(presentation, { type: "AUDIO_PLAYBACK_ENDED", playbackId: "turn-1" });
    expect(presentation).toMatchObject({ state: "IDLE", expression: "NEUTRAL", mouth: "REST", activePlaybackId: "turn-1", lastCompletedPlaybackId: "turn-1" });
  });

  it.each([
    { type: "AUDIO_PLAYBACK_PAUSED" as const, label: "pause" },
    { type: "AUDIO_PLAYBACK_STOPPED" as const, label: "stop" },
    { type: "AUDIO_PLAYBACK_ENDED" as const, label: "end" },
  ])("keeps source ownership after $label so replay can synchronize", (resetEvent) => {
    const reset = run(
      { type: "AUDIO_SOURCE_READY", playbackId: "turn-1" },
      { type: "AUDIO_PLAYBACK_STARTED", playbackId: "turn-1" },
      { type: resetEvent.type, playbackId: "turn-1" },
    );
    expect(reset).toMatchObject({ state: "IDLE", mouth: "REST", activePlaybackId: "turn-1" });
    expect(reduceTutorPresentation(reset, { type: "AUDIO_PLAYBACK_STARTED", playbackId: "turn-1" }))
      .toMatchObject({ state: "SPEAKING", mouth: "SMALL", activePlaybackId: "turn-1" });
  });

  it("requires a fresh source before recovering from a browser audio error", () => {
    const failed = run(
      { type: "AUDIO_SOURCE_READY", playbackId: "turn-1" },
      { type: "AUDIO_PLAYBACK_ERROR", playbackId: "turn-1", errorCode: "browser_audio_error" },
    );
    expect(failed).toMatchObject({ state: "ERROR", mouth: "REST", errorCode: "browser_audio_error" });
    expect(failed.activePlaybackId).toBeUndefined();
    expect(reduceTutorPresentation(failed, { type: "AUDIO_PLAYBACK_STARTED", playbackId: "turn-1" }))
      .toBe(failed);
    const reloaded = reduceTutorPresentation(failed, { type: "AUDIO_SOURCE_READY", playbackId: "turn-1" });
    expect(reduceTutorPresentation(reloaded, { type: "AUDIO_PLAYBACK_STARTED", playbackId: "turn-1" }))
      .toMatchObject({ state: "SPEAKING", mouth: "SMALL", activePlaybackId: "turn-1" });
  });

  it("ignores stale events when a second tutor response owns playback", () => {
    let presentation = run(
      { type: "AUDIO_SOURCE_READY", playbackId: "turn-1" },
      { type: "AUDIO_SOURCE_READY", playbackId: "turn-2" },
    );
    expect(reduceTutorPresentation(presentation, { type: "AUDIO_PLAYBACK_ERROR", playbackId: "turn-1", errorCode: "stale_error" }))
      .toBe(presentation);
    presentation = reduceTutorPresentation(presentation, { type: "AUDIO_PLAYBACK_STARTED", playbackId: "turn-1" });
    expect(presentation.state).toBe("THINKING");
    presentation = reduceTutorPresentation(presentation, { type: "AUDIO_PLAYBACK_STARTED", playbackId: "turn-2" });
    expect(presentation.state).toBe("SPEAKING");
  });

  it("stops immediately and recovers safely after errors", () => {
    const stopped = run(
      { type: "AUDIO_SOURCE_READY", playbackId: "turn-1" },
      { type: "AUDIO_PLAYBACK_STARTED", playbackId: "turn-1" },
      { type: "AUDIO_PLAYBACK_STOPPED", playbackId: "turn-1" },
    );
    expect(stopped).toMatchObject({ state: "IDLE", mouth: "REST" });
    const failed = reduceTutorPresentation(stopped, { type: "FAIL", errorCode: "tts_request_failed" });
    expect(failed).toMatchObject({ state: "ERROR", mouth: "REST", errorCode: "tts_request_failed" });
    expect(reduceTutorPresentation(failed, { type: "RECOVER" }).state).toBe("IDLE");
  });

  it("accepts only the four backend expression values", () => {
    expect(normalizeExpression("POSITIVE")).toBe("POSITIVE");
    expect(normalizeExpression("ENCOURAGING")).toBe("ENCOURAGING");
    expect(normalizeExpression("CORRECTIVE")).toBe("CORRECTIVE");
    expect(normalizeExpression("untrusted")).toBe("NEUTRAL");
  });
});
