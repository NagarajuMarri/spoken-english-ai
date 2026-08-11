import type { MouthShape } from "../avatar/lip-sync";
import type { TutorExpression, TutorPresentation, TutorState } from "../avatar/machine";
import type { TutorPlaybackSignal, TutorRendererFrame } from "../avatar/renderer";

export interface MultimediaAudioSource {
  playbackId: string;
  durationMs?: number;
  spokenText?: string;
}

export interface MultimediaAudioFrame extends TutorPlaybackSignal {
  amplitude: number;
}

export interface LipSyncSample {
  mouth: MouthShape;
  confidence: number;
  source: "PHONEME_VISEME" | "MEASURED_AMPLITUDE" | "PROVIDER_VISEME" | "STATIC";
}

/** Replaceable, provider-neutral translation from playback evidence to a mouth pose. */
export interface LipSyncProvider {
  readonly id: string;
  reset(source?: MultimediaAudioSource): void;
  sample(frame: MultimediaAudioFrame): LipSyncSample;
  dispose?(): void;
}

export interface MultimediaRenderOutput {
  presentation: TutorPresentation;
  frame: TutorRendererFrame;
  playback: TutorPlaybackSignal;
  lipSync: LipSyncSample;
  reducedMotion: boolean;
  elapsedMs: number;
}

/** Adapter implemented by WebGL, lite, portrait, native, or future renderers. */
export interface MultimediaRenderer {
  readonly id: string;
  readonly profile: "MODEL" | "LITE" | "PORTRAIT" | "CUSTOM";
  render(output: MultimediaRenderOutput): void;
  dispose?(): void;
}

/** Injectable animation source so the runtime is deterministic in tests and portable off-browser. */
export interface MultimediaAnimationClock {
  start(onFrame: (timestampMs: number) => void): () => void;
}

export type MultimediaAudioEvent =
  | { type: "AUDIO_SOURCE_READY"; source: MultimediaAudioSource }
  | { type: "AUDIO_PLAYBACK_STARTED"; playbackId: string }
  | { type: "AUDIO_PLAYBACK_FRAME"; frame: MultimediaAudioFrame }
  | { type: "AUDIO_PLAYBACK_PAUSED"; playbackId: string }
  | { type: "AUDIO_PLAYBACK_STOPPED"; playbackId: string }
  | { type: "AUDIO_PLAYBACK_ENDED"; playbackId: string }
  | { type: "AUDIO_PLAYBACK_ERROR"; playbackId: string; errorCode: string };

export type MultimediaRuntimeEvent = MultimediaAudioEvent
  | { type: "RESET" }
  | { type: "RECOVER" }
  | { type: "FAIL"; errorCode: string }
  | { type: "MICROPHONE_STARTED" }
  | { type: "TUTOR_PROCESSING_STARTED" }
  | { type: "TUTOR_RESPONSE_READY"; expression: TutorExpression }
  | { type: "REDUCED_MOTION_CHANGED"; reducedMotion: boolean };

/** Commands implemented by a browser/native audio engine without exposing its media element. */
export interface MultimediaAudioTransport {
  play(): Promise<boolean>;
  replay(): Promise<boolean>;
  pause(): void;
  stop(): void;
  setMuted(muted: boolean): void;
}

/** Audio implementations publish lifecycle events; the runtime never depends on a TTS vendor. */
export interface MultimediaAudioPort extends MultimediaAudioTransport {
  subscribe(listener: (event: MultimediaAudioEvent) => void): () => void;
}

export type MultimediaRuntimeNotification =
  | { type: "RUNTIME_READY"; rendererId: string; rendererProfile: MultimediaRenderer["profile"] }
  | { type: "TUTOR_STATE_CHANGED"; state: TutorState; previousState: TutorState }
  | { type: "TUTOR_EXPRESSION_CHANGED"; expression: TutorExpression; previousExpression: TutorExpression }
  | { type: "AUDIO_LIFECYCLE"; event: MultimediaAudioEvent["type"]; playbackId: string }
  | { type: "LIP_SYNC_CHANGED"; mouth: MouthShape; source: LipSyncSample["source"] }
  | { type: "REDUCED_MOTION_CHANGED"; reducedMotion: boolean }
  | { type: "RENDERER_FALLBACK"; fromRendererId: string; toRendererId: string; reason: "RENDER_FAILED" }
  | { type: "RENDERER_UNAVAILABLE"; failedRendererId: string; reason: "RENDER_FAILED" };

export interface MultimediaRuntimeSnapshot {
  presentation: TutorPresentation;
  playback: TutorPlaybackSignal;
  lipSync: LipSyncSample;
  reducedMotion: boolean;
  rendererId: string | null;
  rendererProfile: MultimediaRenderer["profile"] | null;
}
