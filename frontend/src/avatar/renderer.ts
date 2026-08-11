import type { MouthShape } from "./lip-sync";
import type { TutorExpression, TutorPresentation, TutorState } from "./machine";

export interface TutorRendererFrame {
  state: TutorState;
  expression: TutorExpression;
  mouth: MouthShape;
  blinkEnabled: boolean;
  motionEnabled: boolean;
}

export interface TutorPlaybackSignal {
  playbackId: string;
  amplitude: number;
  currentTimeMs: number;
  durationMs: number;
}

export interface TutorMouthPose {
  openness: number;
  width: number;
  funnel: number;
}

/** Renderer-neutral rig values selected by the active LipSyncProvider upstream. */
export function mouthPoseFromShape(mouth: MouthShape): TutorMouthPose {
  switch (mouth) {
    case "MBP":
      return { openness: 0.015, width: 0.12, funnel: 0.04 };
    case "FV":
      return { openness: 0.12, width: 0.48, funnel: 0.02 };
    case "L":
      return { openness: 0.38, width: 0.42, funnel: 0.04 };
    case "EE":
      return { openness: 0.3, width: 0.9, funnel: 0.02 };
    case "OH":
      return { openness: 0.58, width: 0.22, funnel: 0.72 };
    case "OO":
      return { openness: 0.32, width: 0.12, funnel: 0.9 };
    case "AH":
      return { openness: 0.78, width: 0.56, funnel: 0.08 };
    case "SMALL":
      return { openness: 0.3, width: 0.2, funnel: 0.45 };
    case "MEDIUM":
      return { openness: 0.62, width: 0.6, funnel: 0.16 };
    case "WIDE":
      return { openness: 1, width: 1, funnel: 0.05 };
    case "REST":
      return { openness: 0, width: 0, funnel: 0 };
  }
}

/**
 * Renderer-neutral presentation contract. The model, lightweight 3D, and portrait
 * renderers consume the same frame without owning microphone, LLM, or audio logic.
 */
export function createRendererFrame(
  presentation: TutorPresentation,
  reducedMotion: boolean,
): TutorRendererFrame {
  return {
    state: presentation.state,
    expression: presentation.expression,
    mouth: reducedMotion ? "REST" : presentation.mouth,
    blinkEnabled: !reducedMotion && presentation.state !== "ERROR",
    motionEnabled: !reducedMotion,
  };
}
