import type { MultimediaAnimationClock } from "./contracts";

export class BrowserAnimationClock implements MultimediaAnimationClock {
  constructor(private readonly maximumFramesPerSecond = 30) {}

  start(onFrame: (timestampMs: number) => void) {
    let animationFrame = 0;
    let active = true;
    let lastFrameAt = -Infinity;
    const minimumFrameInterval = 1_000 / Math.max(1, this.maximumFramesPerSecond);
    const tick = (timestampMs: number) => {
      if (!active) return;
      if (timestampMs - lastFrameAt >= minimumFrameInterval) {
        lastFrameAt = timestampMs;
        onFrame(timestampMs);
      }
      animationFrame = window.requestAnimationFrame(tick);
    };
    animationFrame = window.requestAnimationFrame(tick);
    return () => {
      active = false;
      window.cancelAnimationFrame(animationFrame);
    };
  }
}
