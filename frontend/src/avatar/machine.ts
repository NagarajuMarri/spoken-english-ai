import { mouthShapeAtPlaybackTime, type MouthShape } from "./lip-sync";

export type TutorState = "IDLE" | "LISTENING" | "THINKING" | "SPEAKING" | "ERROR";
export type TutorExpression = "NEUTRAL" | "POSITIVE" | "ENCOURAGING" | "CORRECTIVE";

export interface TutorPresentation {
  state: TutorState;
  expression: TutorExpression;
  mouth: MouthShape;
  activePlaybackId?: string;
  lastCompletedPlaybackId?: string;
  errorCode?: string;
}

export type TutorEvent =
  | { type: "RESET" }
  | { type: "MICROPHONE_STARTED" }
  | { type: "TUTOR_PROCESSING_STARTED" }
  | { type: "TUTOR_RESPONSE_READY"; expression: TutorExpression }
  | { type: "AUDIO_SOURCE_READY"; playbackId: string }
  | { type: "AUDIO_PLAYBACK_STARTED"; playbackId: string }
  | { type: "AUDIO_PLAYBACK_FRAME"; playbackId: string; currentTimeMs: number; durationMs: number }
  | { type: "AUDIO_PLAYBACK_PAUSED"; playbackId: string }
  | { type: "AUDIO_PLAYBACK_STOPPED"; playbackId: string }
  | { type: "AUDIO_PLAYBACK_ENDED"; playbackId: string }
  | { type: "AUDIO_PLAYBACK_ERROR"; playbackId: string; errorCode: string }
  | { type: "FAIL"; errorCode: string }
  | { type: "RECOVER" };

export const initialTutorPresentation: TutorPresentation = {
  state: "IDLE",
  expression: "NEUTRAL",
  mouth: "REST",
};

export function normalizeExpression(value?: string): TutorExpression {
  return value === "POSITIVE" || value === "ENCOURAGING" || value === "CORRECTIVE"
    ? value
    : "NEUTRAL";
}

function idle(presentation: TutorPresentation, completedId?: string): TutorPresentation {
  return {
    state: "IDLE",
    expression: "NEUTRAL",
    mouth: "REST",
    lastCompletedPlaybackId: completedId ?? presentation.lastCompletedPlaybackId,
  };
}

function ownsPlayback(presentation: TutorPresentation, playbackId: string) {
  return presentation.activePlaybackId === playbackId;
}

export function reduceTutorPresentation(
  presentation: TutorPresentation,
  event: TutorEvent,
): TutorPresentation {
  switch (event.type) {
    case "RESET":
    case "RECOVER":
      return idle(presentation);
    case "MICROPHONE_STARTED":
      return { state: "LISTENING", expression: "NEUTRAL", mouth: "REST" };
    case "TUTOR_PROCESSING_STARTED":
      return { state: "THINKING", expression: "NEUTRAL", mouth: "REST" };
    case "TUTOR_RESPONSE_READY":
      return { ...presentation, state: "THINKING", expression: event.expression, mouth: "REST" };
    case "AUDIO_SOURCE_READY":
      return {
        ...presentation,
        state: "THINKING",
        mouth: "REST",
        activePlaybackId: event.playbackId,
        errorCode: undefined,
      };
    case "AUDIO_PLAYBACK_STARTED":
      if (!ownsPlayback(presentation, event.playbackId)) return presentation;
      return { ...presentation, state: "SPEAKING", mouth: "SMALL", errorCode: undefined };
    case "AUDIO_PLAYBACK_FRAME":
      if (!ownsPlayback(presentation, event.playbackId) || presentation.state !== "SPEAKING") {
        return presentation;
      }
      return {
        ...presentation,
        mouth: mouthShapeAtPlaybackTime(event.currentTimeMs, event.durationMs),
      };
    case "AUDIO_PLAYBACK_PAUSED":
    case "AUDIO_PLAYBACK_STOPPED":
      return ownsPlayback(presentation, event.playbackId) ? idle(presentation) : presentation;
    case "AUDIO_PLAYBACK_ENDED":
      return ownsPlayback(presentation, event.playbackId)
        ? idle(presentation, event.playbackId)
        : presentation;
    case "AUDIO_PLAYBACK_ERROR":
      if (!ownsPlayback(presentation, event.playbackId)) return presentation;
      return {
        state: "ERROR",
        expression: "NEUTRAL",
        mouth: "REST",
        errorCode: event.errorCode,
      };
    case "FAIL":
      return {
        state: "ERROR",
        expression: "NEUTRAL",
        mouth: "REST",
        errorCode: event.errorCode,
      };
  }
}
