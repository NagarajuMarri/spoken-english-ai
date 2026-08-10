import { mouthShapeFromAmplitude } from "../avatar/lip-sync";
import type {
  LipSyncProvider,
  LipSyncSample,
  MultimediaAudioFrame,
  MultimediaAudioSource,
} from "./contracts";

const STATIC_SAMPLE: LipSyncSample = { mouth: "REST", confidence: 1, source: "STATIC" };

/** Default fallback when a speech provider supplies audio but no timed visemes. */
export class AmplitudeLipSyncProvider implements LipSyncProvider {
  readonly id = "measured-amplitude";
  private playbackId = "";

  reset(source?: MultimediaAudioSource) {
    this.playbackId = source?.playbackId ?? "";
  }

  sample(frame: MultimediaAudioFrame): LipSyncSample {
    if (!this.playbackId || frame.playbackId !== this.playbackId) return STATIC_SAMPLE;
    const amplitude = Number.isFinite(frame.amplitude) ? Math.max(0, Math.min(1, frame.amplitude)) : 0;
    return {
      mouth: mouthShapeFromAmplitude(amplitude),
      confidence: amplitude > 0 ? 0.75 : 1,
      source: "MEASURED_AMPLITUDE",
    };
  }
}

/** Accessibility and capability fallback that deliberately performs no mouth animation. */
export class StaticLipSyncProvider implements LipSyncProvider {
  readonly id = "static";

  reset() {
    // No provider state is retained.
  }

  sample(_frame: MultimediaAudioFrame) {
    return STATIC_SAMPLE;
  }
}
