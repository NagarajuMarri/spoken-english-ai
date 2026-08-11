export { BrowserAnimationClock } from "./browser-animation-clock";
export { MultimediaAudioController } from "./audio-controller";
export { multimediaAudioEventFromLifecycle } from "./audio-lifecycle-adapter";
export { selectTutorRenderTier, type TutorRenderTier } from "./device-fallback";
export { EventDrivenAnimationClock } from "./event-driven-animation-clock";
export { AmplitudeLipSyncProvider, PhonemeLipSyncProvider, StaticLipSyncProvider } from "./lip-sync-providers";
export {
  ANANYA_NATURAL_MOTION_SEED,
  createNaturalMotionController,
  NEUTRAL_NATURAL_MOTION,
  type NaturalMotionController,
  type NaturalMotionInput,
  type NaturalMotionSample,
} from "./natural-motion";
export { SpeakMateMultimediaRuntime, createStaticMouthSample } from "./runtime";
export {
  useSpeakMateMultimediaRuntime,
  type SpeakMateMultimediaBridge,
  type SpeakMateMultimediaBridgeOptions,
} from "./use-multimedia-runtime";
export {
  useTutorRendererFallback,
  type ActiveTutorRenderer,
  type ActiveTutorRendererProfile,
} from "./use-renderer-fallback";
export type {
  LipSyncProvider,
  LipSyncSample,
  MultimediaAnimationClock,
  MultimediaAudioEvent,
  MultimediaAudioFrame,
  MultimediaAudioPort,
  MultimediaAudioSource,
  MultimediaAudioTransport,
  MultimediaRenderer,
  MultimediaRenderOutput,
  MultimediaRuntimeEvent,
  MultimediaRuntimeNotification,
  MultimediaRuntimeSnapshot,
} from "./contracts";
