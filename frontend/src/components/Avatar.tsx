import {
  Component,
  lazy,
  Suspense,
  useRef,
  type MutableRefObject,
  type ReactNode,
} from "react";
import { createRendererFrame, type TutorPlaybackSignal } from "../avatar/renderer";
import type { TutorPresentation } from "../avatar/machine";
import type { Tutor } from "../models";
import { selectTutorRenderTier, useTutorRendererFallback } from "../multimedia";

const ThreeAvatar = lazy(() => import("./ThreeAvatar"));

class AvatarErrorBoundary extends Component<{
  children: ReactNode;
  fallback: ReactNode;
  onError: () => void;
}, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch() {
    this.props.onError();
  }

  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

function PortraitVisual({ tutor, frame }: { tutor: Tutor; frame: ReturnType<typeof createRendererFrame> }) {
  return <>
    <img src={tutor.avatar_profile} alt={`${tutor.display_name}, your interactive Indian-English tutor`} />
    <span className="state-aura" aria-hidden="true" />
    <span className="listening-wave" aria-hidden="true"><i /><i /><i /><i /><i /></span>
    <span className="thinking-dots" aria-hidden="true"><i /><i /><i /></span>
    <i className={`eyelid left ${frame.blinkEnabled ? "blink-enabled" : ""}`} aria-hidden="true" />
    <i className={`eyelid right ${frame.blinkEnabled ? "blink-enabled" : ""}`} aria-hidden="true" />
    <i className="expression-brow left" aria-hidden="true" />
    <i className="expression-brow right" aria-hidden="true" />
    <span className={`mouth mouth-${frame.mouth.toLowerCase()}`} aria-hidden="true" />
  </>;
}

export function Avatar({
  tutor,
  presentation,
  reducedMotion = false,
  playbackSignal,
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
  const localSignal = useRef<TutorPlaybackSignal>({ playbackId: "", amplitude: 0, currentTimeMs: 0, durationMs: 0 });
  const signal = playbackSignal ?? localSignal;
  const renderTier = selectTutorRenderTier(tutor.tutor_id);
  const supportsThreeDimensions = renderTier !== "STATIC_FALLBACK";
  const {
    renderer,
    profile: rendererProfile,
    rendererReady: handleReady,
    rendererUnavailable: handleUnavailable,
  } = useTutorRendererFallback({ threeDimensionsEnabled: supportsThreeDimensions, onReady });
  const learnerState = frame.state === "IDLE" ? "READY" : frame.state === "ERROR" ? "RETRY" : frame.state;
  return (
    <figure
      className={`avatar avatar-stage ${stateLabel} expression-${expressionLabel} ${reducedMotion ? "reduced-motion" : ""}`}
      data-state={frame.state}
      data-expression={frame.expression}
      data-mouth={frame.mouth}
      data-tutor={tutor.tutor_id}
      data-renderer={renderer}
      data-renderer-profile={rendererProfile}
      aria-label={`${tutor.display_name} tutor status: ${learnerState.toLowerCase()}`}
    >
      {renderer === "portrait" ? (
        <PortraitVisual tutor={tutor} frame={frame} />
      ) : (
        <AvatarErrorBoundary fallback={<PortraitVisual tutor={tutor} frame={frame} />} onError={handleUnavailable}>
          <Suspense fallback={<PortraitVisual tutor={tutor} frame={frame} />}>
            <ThreeAvatar
              frame={frame}
              playbackSignal={signal}
              reducedMotion={reducedMotion}
              onReady={handleReady}
              onUnavailable={handleUnavailable}
            />
          </Suspense>
        </AvatarErrorBoundary>
      )}
      <figcaption aria-live="polite">
        <strong>{learnerState}</strong>
      </figcaption>
    </figure>
  );
}
