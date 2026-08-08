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
    expect(presentation).toMatchObject({ state: "IDLE", expression: "NEUTRAL", mouth: "REST", lastCompletedPlaybackId: "turn-1" });
  });

  it("ignores stale events when a second tutor response owns playback", () => {
    let presentation = run(
      { type: "AUDIO_SOURCE_READY", playbackId: "turn-1" },
      { type: "AUDIO_SOURCE_READY", playbackId: "turn-2" },
    );
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
