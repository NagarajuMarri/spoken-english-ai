export type SyncStatus = "NOT_AVAILABLE" | "APPROXIMATE" | "VISEME_TIMED" | "SYNCHRONIZED" | "FAILED";
export type MouthShape =
  | "REST"
  | "SMALL"
  | "MEDIUM"
  | "WIDE"
  | "AH"
  | "EE"
  | "OH"
  | "OO"
  | "MBP"
  | "FV"
  | "L";

export interface VisemeEvent {
  identifier: MouthShape;
  start_ms: number;
  end_ms: number;
  confidence?: number;
}

export interface LipSyncContract {
  audio_reference: string;
  duration_ms: number;
  timing_source: "PROVIDER" | "APPROXIMATE" | "NONE";
  visemes: VisemeEvent[];
  fallback_mode: "APPROXIMATE" | "STATIC";
  status: SyncStatus;
}

const APPROXIMATE_CYCLE: readonly MouthShape[] = ["SMALL", "MEDIUM", "WIDE", "MEDIUM"];

export function approximateLipSync(
  audioReference: string,
  durationMs: number,
  stepMs = 120,
): LipSyncContract {
  const boundedDuration = Math.max(0, durationMs);
  const visemes: VisemeEvent[] = [];
  for (let start = 0; start < boundedDuration; start += stepMs) {
    visemes.push({
      identifier: APPROXIMATE_CYCLE[Math.floor(start / stepMs) % APPROXIMATE_CYCLE.length],
      start_ms: start,
      end_ms: Math.min(boundedDuration, start + stepMs),
      confidence: 0.5,
    });
  }
  return {
    audio_reference: audioReference,
    duration_ms: boundedDuration,
    timing_source: "APPROXIMATE",
    visemes,
    fallback_mode: "APPROXIMATE",
    status: "APPROXIMATE",
  };
}

export function mouthShapeAtPlaybackTime(currentTimeMs: number, durationMs: number): MouthShape {
  if (!Number.isFinite(currentTimeMs) || currentTimeMs < 0) return "REST";
  if (Number.isFinite(durationMs) && durationMs > 0 && currentTimeMs >= durationMs) return "REST";
  return APPROXIMATE_CYCLE[Math.floor(currentTimeMs / 120) % APPROXIMATE_CYCLE.length];
}

/**
 * Maps a normalized Web Audio RMS amplitude to the small set of renderer-neutral
 * mouth poses. Runtime playback uses this signal when provider visemes are not
 * available, so silence stays still instead of advancing an arbitrary timer.
 */
export function mouthShapeFromAmplitude(amplitude: number): MouthShape {
  if (!Number.isFinite(amplitude) || amplitude < 0.025) return "REST";
  if (amplitude < 0.075) return "SMALL";
  if (amplitude < 0.16) return "MEDIUM";
  return "WIDE";
}

export function mouthShapeFromContract(contract: LipSyncContract, currentTimeMs: number): MouthShape {
  const event = contract.visemes.find(
    (candidate) => currentTimeMs >= candidate.start_ms && currentTimeMs < candidate.end_ms,
  );
  return event?.identifier ?? "REST";
}
