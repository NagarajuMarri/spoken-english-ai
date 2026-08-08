import type { MouthShape } from "./lip-sync";
import type { TutorExpression, TutorPresentation, TutorState } from "./machine";

export interface TutorRendererFrame {
  state: TutorState;
  expression: TutorExpression;
  mouth: MouthShape;
  blinkEnabled: boolean;
  motionEnabled: boolean;
}

/**
 * Renderer-neutral presentation contract. The current 2D renderer and a future
 * 3D renderer consume the same frame without owning microphone, LLM, or audio logic.
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
