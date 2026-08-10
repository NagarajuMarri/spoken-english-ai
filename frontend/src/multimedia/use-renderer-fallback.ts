import { useCallback, useEffect, useRef, useState } from "react";

export type ActiveTutorRenderer = "loading" | "three" | "portrait";
export type ActiveTutorRendererProfile = "model" | "lite" | "portrait";

/** React adapter for the multimedia layer's model -> lite -> portrait fallback contract. */
export function useTutorRendererFallback({
  threeDimensionsEnabled,
  onReady,
}: {
  threeDimensionsEnabled: boolean;
  onReady?: (profile: ActiveTutorRendererProfile, initializationMs: number) => void;
}) {
  const [renderer, setRenderer] = useState<ActiveTutorRenderer>(
    threeDimensionsEnabled ? "loading" : "portrait",
  );
  const [profile, setProfile] = useState<ActiveTutorRendererProfile>(
    threeDimensionsEnabled ? "lite" : "portrait",
  );
  const readinessReported = useRef(false);
  const permanentlyUnavailable = useRef(false);

  useEffect(() => {
    if (threeDimensionsEnabled || readinessReported.current) return;
    readinessReported.current = true;
    onReady?.("portrait", 0);
  }, [onReady, threeDimensionsEnabled]);

  const rendererReady = useCallback((initializationMs: number, nextProfile: "model" | "lite") => {
    if (permanentlyUnavailable.current) return;
    setProfile(nextProfile);
    setRenderer("three");
    if (readinessReported.current) return;
    readinessReported.current = true;
    onReady?.(nextProfile, initializationMs);
  }, [onReady]);

  const rendererUnavailable = useCallback(() => {
    permanentlyUnavailable.current = true;
    setProfile("portrait");
    setRenderer("portrait");
    if (readinessReported.current) return;
    readinessReported.current = true;
    onReady?.("portrait", 0);
  }, [onReady]);

  return { renderer, profile, rendererReady, rendererUnavailable };
}
