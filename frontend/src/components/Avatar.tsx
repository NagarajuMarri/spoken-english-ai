import { useEffect, type MutableRefObject } from "react";
import { createRendererFrame, type TutorPlaybackSignal } from "../avatar/renderer";
import type { TutorPresentation } from "../avatar/machine";
import type { Tutor } from "../models";

const ANANYA_PORTRAIT = "/tutors/ananya-2d-v2.png";

function PortraitVisual({ tutor }: { tutor: Tutor }) {
  const source = tutor.tutor_id === "ananya" ? ANANYA_PORTRAIT : tutor.avatar_profile;
  return <>
    <div className="portrait-motion">
      <img src={source} alt={`${tutor.display_name}, your friendly Indian-English tutor`} />
    </div>
    <span className="state-aura" aria-hidden="true" />
    <span className="listening-wave" aria-hidden="true"><i /><i /><i /><i /><i /></span>
    <span className="thinking-dots" aria-hidden="true"><i /><i /><i /></span>
    <span className="speaking-wave" aria-hidden="true"><i /><i /><i /><i /><i /></span>
  </>;
}

export function Avatar({
  tutor,
  presentation,
  reducedMotion = false,
  playbackSignal: _playbackSignal,
  onReady,
}: {
  tutor: Tutor;
  presentation: TutorPresentation;
  reducedMotion?: boolean;
  playbackSignal?: MutableRefObject<TutorPlaybackSignal>;
  onReady?: (profile: "model" | "lite" | "portrait", initializationMs: number) => void;
}) {
  const frame = createRendererFrame(presentation, reducedMotion);
  const stateLabel = frame.state.toLowerCase();
  const expressionLabel = frame.expression.toLowerCase();
  const learnerState = frame.state === "IDLE" ? "READY" : frame.state === "ERROR" ? "RETRY" : frame.state;

  useEffect(() => {
    const startedAt = performance.now();
    onReady?.("portrait", performance.now() - startedAt);
  }, [onReady]);

  return (
    <figure
      className={`avatar avatar-stage ${stateLabel} expression-${expressionLabel} ${reducedMotion ? "reduced-motion" : ""}`}
      data-state={frame.state}
      data-expression={frame.expression}
      data-mouth={frame.mouth}
      data-tutor={tutor.tutor_id}
      data-renderer="portrait"
      data-renderer-profile="portrait"
      aria-label={`${tutor.display_name} tutor status: ${learnerState.toLowerCase()}`}
    >
      <PortraitVisual tutor={tutor} />
      <figcaption aria-live="polite"><strong>{learnerState}</strong></figcaption>
    </figure>
  );
}
