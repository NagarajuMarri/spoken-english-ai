import { initialTutorPresentation, reduceTutorPresentation, type TutorEvent } from "../avatar/machine";
import { createRendererFrame } from "../avatar/renderer";
import type { MouthShape } from "../avatar/lip-sync";
import type {
  LipSyncProvider,
  LipSyncSample,
  MultimediaAnimationClock,
  MultimediaAudioEvent,
  MultimediaAudioPort,
  MultimediaRenderer,
  MultimediaRuntimeEvent,
  MultimediaRuntimeNotification,
  MultimediaRuntimeSnapshot,
} from "./contracts";

const REST_SAMPLE: LipSyncSample = { mouth: "REST", confidence: 1, source: "STATIC" };

interface MultimediaRuntimeOptions {
  renderers: MultimediaRenderer[];
  lipSyncProvider: LipSyncProvider;
  animationClock: MultimediaAnimationClock;
  reducedMotion?: boolean;
  onNotification?: (event: MultimediaRuntimeNotification) => void;
}

/**
 * Provider-neutral coordinator for tutor state, animation, audio lifecycle, lip sync,
 * expression, renderer fallback, and reduced-motion behavior.
 */
export class SpeakMateMultimediaRuntime {
  private presentation = initialTutorPresentation;
  private playback = { playbackId: "", amplitude: 0, currentTimeMs: 0, durationMs: 0 };
  private lipSync: LipSyncSample = REST_SAMPLE;
  private rendererIndex = 0;
  private reducedMotion: boolean;
  private running = false;
  private startedAt = 0;
  private stopClock?: () => void;
  private detachAudio?: () => void;
  private audioPort?: MultimediaAudioPort;
  private disposedRenderers = new Set<MultimediaRenderer>();

  constructor(private readonly options: MultimediaRuntimeOptions) {
    if (options.renderers.length === 0) throw new Error("A multimedia renderer is required.");
    this.reducedMotion = Boolean(options.reducedMotion);
  }

  start() {
    if (this.running) return;
    this.running = true;
    this.startedAt = performance.now();
    this.render(this.startedAt);
    const renderer = this.activeRenderer();
    if (renderer) {
      if (!this.reducedMotion) this.startClock();
      this.notify({ type: "RUNTIME_READY", rendererId: renderer.id, rendererProfile: renderer.profile });
    }
  }

  attachAudio(port: MultimediaAudioPort) {
    this.detachAudio?.();
    this.audioPort = port;
    const detach = port.subscribe((event) => this.handle(event));
    let detached = false;
    const detachOnce = () => {
      if (!detached) {
        detached = true;
        detach();
      }
      if (this.detachAudio === detachOnce) this.detachAudio = undefined;
      if (this.audioPort === port) this.audioPort = undefined;
    };
    this.detachAudio = detachOnce;
    return detachOnce;
  }

  playAudio() {
    return this.audioPort?.play() ?? Promise.resolve(false);
  }

  replayAudio() {
    return this.audioPort?.replay() ?? Promise.resolve(false);
  }

  pauseAudio() {
    this.audioPort?.pause();
  }

  stopAudio() {
    this.audioPort?.stop();
  }

  setAudioMuted(muted: boolean) {
    this.audioPort?.setMuted(muted);
  }

  handle(event: MultimediaRuntimeEvent) {
    if (event.type === "REDUCED_MOTION_CHANGED") {
      this.setReducedMotion(event.reducedMotion);
      return;
    }

    const previousState = this.presentation.state;
    const previousExpression = this.presentation.expression;
    const previousMouth = this.lipSync.mouth;
    this.applyEvent(event);

    if (this.presentation.state !== previousState) {
      this.notify({
        type: "TUTOR_STATE_CHANGED",
        state: this.presentation.state,
        previousState,
      });
    }
    if (this.presentation.expression !== previousExpression) {
      this.notify({
        type: "TUTOR_EXPRESSION_CHANGED",
        expression: this.presentation.expression,
        previousExpression,
      });
    }
    if (this.lipSync.mouth !== previousMouth) {
      this.notify({ type: "LIP_SYNC_CHANGED", mouth: this.lipSync.mouth, source: this.lipSync.source });
    }
    if (event.type.startsWith("AUDIO_")) {
      const audioEvent = event as MultimediaAudioEvent;
      const playbackId = audioEvent.type === "AUDIO_SOURCE_READY"
        ? audioEvent.source.playbackId
        : audioEvent.type === "AUDIO_PLAYBACK_FRAME"
          ? audioEvent.frame.playbackId
          : audioEvent.playbackId;
      this.notify({ type: "AUDIO_LIFECYCLE", event: audioEvent.type, playbackId });
    }
    this.render(performance.now());
  }

  snapshot(): MultimediaRuntimeSnapshot {
    const renderer = this.activeRenderer();
    return {
      presentation: { ...this.presentation },
      playback: { ...this.playback },
      lipSync: { ...this.lipSync },
      reducedMotion: this.reducedMotion,
      rendererId: renderer?.id ?? null,
      rendererProfile: renderer?.profile ?? null,
    };
  }

  dispose() {
    this.running = false;
    this.stopClock?.();
    this.stopClock = undefined;
    this.detachAudio?.();
    this.detachAudio = undefined;
    this.options.lipSyncProvider.dispose?.();
    for (const renderer of this.options.renderers) this.disposeRenderer(renderer);
  }

  private activeRenderer() {
    return this.options.renderers[this.rendererIndex];
  }

  private startClock() {
    this.stopClock?.();
    this.stopClock = this.options.animationClock.start((timestampMs) => this.render(timestampMs));
  }

  private setReducedMotion(reducedMotion: boolean) {
    if (this.reducedMotion === reducedMotion) return;
    this.reducedMotion = reducedMotion;
    if (reducedMotion) {
      this.lipSync = REST_SAMPLE;
      this.presentation = { ...this.presentation, mouth: "REST" };
    }
    if (this.running) {
      if (reducedMotion) {
        this.stopClock?.();
        this.stopClock = undefined;
      } else if (this.activeRenderer()) {
        this.startClock();
      }
      this.render(performance.now());
    }
    this.notify({ type: "REDUCED_MOTION_CHANGED", reducedMotion });
  }

  private applyEvent(event: Exclude<MultimediaRuntimeEvent, { type: "REDUCED_MOTION_CHANGED" }>) {
    if (event.type === "AUDIO_SOURCE_READY") {
      this.playback = {
        playbackId: event.source.playbackId,
        amplitude: 0,
        currentTimeMs: 0,
        durationMs: event.source.durationMs ?? 0,
      };
      this.lipSync = REST_SAMPLE;
      this.options.lipSyncProvider.reset(event.source);
      this.presentation = reduceTutorPresentation(this.presentation, {
        type: "AUDIO_SOURCE_READY",
        playbackId: event.source.playbackId,
      });
      return;
    }
    if (event.type === "AUDIO_PLAYBACK_FRAME") {
      if (
        this.presentation.state !== "SPEAKING"
        || this.presentation.activePlaybackId !== event.frame.playbackId
      ) return;
      this.playback = { ...event.frame };
      const sample = this.reducedMotion ? REST_SAMPLE : this.options.lipSyncProvider.sample(event.frame);
      const next = reduceTutorPresentation(this.presentation, {
        type: "AUDIO_PLAYBACK_FRAME",
        playbackId: event.frame.playbackId,
        currentTimeMs: event.frame.currentTimeMs,
        durationMs: event.frame.durationMs,
        amplitude: event.frame.amplitude,
      });
      this.lipSync = sample;
      this.presentation = { ...next, mouth: sample.mouth };
      return;
    }

    const terminalPlaybackId = event.type === "AUDIO_PLAYBACK_PAUSED"
      || event.type === "AUDIO_PLAYBACK_STOPPED"
      || event.type === "AUDIO_PLAYBACK_ENDED"
      || event.type === "AUDIO_PLAYBACK_ERROR"
      ? event.playbackId
      : undefined;
    const ownsActivePlayback = terminalPlaybackId !== undefined
      && this.presentation.activePlaybackId === terminalPlaybackId;
    const tutorEvent = this.toTutorEvent(event);
    this.presentation = reduceTutorPresentation(this.presentation, tutorEvent);
    if (
      ownsActivePlayback
      || event.type === "RESET"
      || event.type === "RECOVER"
    ) {
      this.playback = { ...this.playback, amplitude: 0 };
      this.lipSync = REST_SAMPLE;
      this.options.lipSyncProvider.reset(
        this.playback.playbackId ? { playbackId: this.playback.playbackId, durationMs: this.playback.durationMs } : undefined,
      );
    }
  }

  private toTutorEvent(event: Exclude<MultimediaRuntimeEvent,
    { type: "REDUCED_MOTION_CHANGED" | "AUDIO_SOURCE_READY" | "AUDIO_PLAYBACK_FRAME" }>): TutorEvent {
    switch (event.type) {
      case "AUDIO_PLAYBACK_STARTED":
      case "AUDIO_PLAYBACK_PAUSED":
      case "AUDIO_PLAYBACK_STOPPED":
      case "AUDIO_PLAYBACK_ENDED":
        return { type: event.type, playbackId: event.playbackId };
      case "AUDIO_PLAYBACK_ERROR":
        return { type: event.type, playbackId: event.playbackId, errorCode: event.errorCode };
      case "TUTOR_RESPONSE_READY":
        return event;
      case "FAIL":
        return event;
      case "MICROPHONE_STARTED":
      case "TUTOR_PROCESSING_STARTED":
      case "RESET":
      case "RECOVER":
        return event;
    }
  }

  private render(timestampMs: number) {
    if (!this.running || this.rendererIndex >= this.options.renderers.length) return;
    const output = {
      presentation: this.presentation,
      frame: createRendererFrame(this.presentation, this.reducedMotion),
      playback: this.playback,
      lipSync: this.reducedMotion ? REST_SAMPLE : this.lipSync,
      reducedMotion: this.reducedMotion,
      elapsedMs: Math.max(0, timestampMs - this.startedAt),
    };

    while (this.rendererIndex < this.options.renderers.length) {
      const renderer = this.options.renderers[this.rendererIndex];
      try {
        renderer.render(output);
        return;
      } catch {
        const failedRendererId = renderer.id;
        this.disposeRenderer(renderer);
        this.rendererIndex += 1;
        const fallback = this.activeRenderer();
        if (fallback) {
          this.notify({
            type: "RENDERER_FALLBACK",
            fromRendererId: failedRendererId,
            toRendererId: fallback.id,
            reason: "RENDER_FAILED",
          });
        } else {
          this.notify({ type: "RENDERER_UNAVAILABLE", failedRendererId, reason: "RENDER_FAILED" });
          this.stopClock?.();
          this.stopClock = undefined;
        }
      }
    }
  }

  private notify(event: MultimediaRuntimeNotification) {
    this.options.onNotification?.(event);
  }

  private disposeRenderer(renderer: MultimediaRenderer) {
    if (this.disposedRenderers.has(renderer)) return;
    this.disposedRenderers.add(renderer);
    try {
      renderer.dispose?.();
    } catch {
      // Renderer cleanup cannot prevent fallback or runtime teardown.
    }
  }
}

export function createStaticMouthSample(mouth: MouthShape = "REST"): LipSyncSample {
  return { mouth, confidence: 1, source: "STATIC" };
}
