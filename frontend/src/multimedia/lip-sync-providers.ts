import { mouthShapeFromAmplitude } from "../avatar/lip-sync";
import type {
  LipSyncProvider,
  LipSyncSample,
  MultimediaAudioFrame,
  MultimediaAudioSource,
} from "./contracts";

const STATIC_SAMPLE: LipSyncSample = { mouth: "REST", confidence: 1, source: "STATIC" };

type VisemeMouth = Exclude<LipSyncSample["mouth"], "SMALL" | "MEDIUM" | "WIDE">;

const PAUSE = /[\s.,!?;:—–-]/u;
const TELUGU_EE = "ఇఈిీేై";
const TELUGU_OO = "ఉఊుూొోౌ";
const TELUGU_REST = "్";

/**
 * Selects a renderer-neutral viseme from the accepted tutor text. This is a
 * local grapheme-to-viseme estimate, not a claim of provider-supplied timing.
 */
export function mouthShapeFromGrapheme(grapheme: string): VisemeMouth {
  if (!grapheme || PAUSE.test(grapheme) || TELUGU_REST.includes(grapheme)) return "REST";
  const value = grapheme.toLocaleLowerCase("en-US");
  if (/[mbp]/u.test(value)) return "MBP";
  if (/[fv]/u.test(value)) return "FV";
  if (/[l]/u.test(value)) return "L";
  if (/[ie]/u.test(value) || TELUGU_EE.includes(value)) return "EE";
  if (/[o]/u.test(value)) return "OH";
  if (/[uwq]/u.test(value) || TELUGU_OO.includes(value)) return "OO";
  return "AH";
}

function speakableGraphemes(text: string) {
  return Array.from(text.normalize("NFC")).filter((value, index, all) => {
    if (!PAUSE.test(value)) return true;
    return index === 0 || !PAUSE.test(all[index - 1]);
  });
}

/**
 * Primary browser lip sync: derives useful phoneme-family poses from the exact
 * spoken text and aligns them across media playback time. Measured amplitude is
 * retained as the fallback for sources that do not carry text.
 */
export class PhonemeLipSyncProvider implements LipSyncProvider {
  readonly id = "text-derived-phoneme-visemes";
  private playbackId = "";
  private graphemes: string[] = [];
  private readonly amplitudeFallback = new AmplitudeLipSyncProvider();

  reset(source?: MultimediaAudioSource) {
    this.playbackId = source?.playbackId ?? "";
    this.graphemes = speakableGraphemes(source?.spokenText?.trim() ?? "");
    this.amplitudeFallback.reset(source);
  }

  sample(frame: MultimediaAudioFrame): LipSyncSample {
    if (!this.playbackId || frame.playbackId !== this.playbackId) return STATIC_SAMPLE;
    if (this.graphemes.length === 0) return this.amplitudeFallback.sample(frame);
    const duration = Number.isFinite(frame.durationMs) && frame.durationMs > 0
      ? frame.durationMs
      : Math.max(240, this.graphemes.length * 90);
    if (!Number.isFinite(frame.currentTimeMs) || frame.currentTimeMs < 0 || frame.currentTimeMs >= duration) {
      return STATIC_SAMPLE;
    }
    const progress = Math.max(0, Math.min(0.999999, frame.currentTimeMs / duration));
    const grapheme = this.graphemes[Math.floor(progress * this.graphemes.length)];
    return { mouth: mouthShapeFromGrapheme(grapheme), confidence: 0.68, source: "PHONEME_VISEME" };
  }
}

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
