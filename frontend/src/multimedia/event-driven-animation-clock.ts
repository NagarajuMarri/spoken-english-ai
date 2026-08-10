import type { MultimediaAnimationClock } from "./contracts";

/** React/Three adapters render on semantic events and their own capped renderer loop. */
export class EventDrivenAnimationClock implements MultimediaAnimationClock {
  start() {
    return () => undefined;
  }
}
