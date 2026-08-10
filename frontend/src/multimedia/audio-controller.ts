import type {
  MultimediaAudioEvent,
  MultimediaAudioPort,
  MultimediaAudioTransport,
} from "./contracts";

/**
 * Stable production audio port between the multimedia runtime and the active
 * browser/native audio transport. Lifecycle events and commands share one
 * ownership boundary, while a player may mount or unmount independently.
 */
export class MultimediaAudioController implements MultimediaAudioPort {
  private readonly listeners = new Set<(event: MultimediaAudioEvent) => void>();
  private transport: MultimediaAudioTransport | null = null;

  subscribe(listener: (event: MultimediaAudioEvent) => void) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  attachTransport(transport: MultimediaAudioTransport | null) {
    this.transport = transport;
  }

  publish(event: MultimediaAudioEvent) {
    for (const listener of this.listeners) listener(event);
  }

  play() {
    return this.transport?.play() ?? Promise.resolve(false);
  }

  replay() {
    return this.transport?.replay() ?? Promise.resolve(false);
  }

  pause() {
    this.transport?.pause();
  }

  stop() {
    this.transport?.stop();
  }

  setMuted(muted: boolean) {
    this.transport?.setMuted(muted);
  }
}
