import { createRendererFrame } from "../avatar/renderer";
import type { TutorPresentation } from "../avatar/machine";
import type { Tutor } from "../models";

export function Avatar({
  tutor,
  presentation,
  reducedMotion = false,
}: {
  tutor: Tutor;
  presentation: TutorPresentation;
  reducedMotion?: boolean;
}) {
  const frame = createRendererFrame(presentation, reducedMotion);
  const stateLabel = frame.state.toLowerCase();
  const expressionLabel = frame.expression.toLowerCase();
  const learnerState = frame.state === "IDLE" || frame.state === "ERROR" ? "READY" : frame.state;
  return (
    <figure
      className={`avatar ${stateLabel} expression-${expressionLabel} ${reducedMotion ? "reduced-motion" : ""}`}
      data-state={frame.state}
      data-expression={frame.expression}
      data-mouth={frame.mouth}
      data-tutor={tutor.tutor_id}
      aria-label={`${tutor.display_name} tutor status: ${learnerState.toLowerCase()}`}
    >
      <img src={tutor.avatar_profile} alt={`${tutor.display_name}, your interactive Indian-English tutor`} />
      <span className="state-aura" aria-hidden="true" />
      <span className="listening-wave" aria-hidden="true"><i /><i /><i /><i /><i /></span>
      <span className="thinking-dots" aria-hidden="true"><i /><i /><i /></span>
      <i className={`eyelid left ${frame.blinkEnabled ? "blink-enabled" : ""}`} aria-hidden="true" />
      <i className={`eyelid right ${frame.blinkEnabled ? "blink-enabled" : ""}`} aria-hidden="true" />
      <i className="expression-brow left" aria-hidden="true" />
      <i className="expression-brow right" aria-hidden="true" />
      <span className={`mouth mouth-${frame.mouth.toLowerCase()}`} aria-hidden="true" />
      <figcaption aria-live="polite">
        <strong>{learnerState}</strong>
      </figcaption>
    </figure>
  );
}
