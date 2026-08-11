import type { AudioLifecycleEvent } from "../voice/TutorAudioPlayer";
import type { MultimediaAudioEvent } from "./contracts";

/** Provider-neutral adapter from the browser audio engine into the multimedia runtime. */
export function multimediaAudioEventFromLifecycle(event: AudioLifecycleEvent): MultimediaAudioEvent {
  switch (event.type) {
    case "SOURCE_READY":
      return {
        type: "AUDIO_SOURCE_READY",
        source: { playbackId: event.playbackId, spokenText: event.spokenText },
      };
    case "PLAYBACK_STARTED":
      return { type: "AUDIO_PLAYBACK_STARTED", playbackId: event.playbackId };
    case "PLAYBACK_FRAME":
      return {
        type: "AUDIO_PLAYBACK_FRAME",
        frame: {
          playbackId: event.playbackId,
          amplitude: event.amplitude,
          currentTimeMs: event.currentTimeMs,
          durationMs: event.durationMs,
        },
      };
    case "PLAYBACK_PAUSED":
      return { type: "AUDIO_PLAYBACK_PAUSED", playbackId: event.playbackId };
    case "PLAYBACK_STOPPED":
      return { type: "AUDIO_PLAYBACK_STOPPED", playbackId: event.playbackId };
    case "PLAYBACK_ENDED":
      return { type: "AUDIO_PLAYBACK_ENDED", playbackId: event.playbackId };
    case "PLAYBACK_ERROR":
      return { type: "AUDIO_PLAYBACK_ERROR", playbackId: event.playbackId, errorCode: event.errorCode };
  }
}
