export const ANANYA_NATURAL_MOTION_SEED = "speakmate-ananya-natural-motion-v1";

export interface NaturalMotionSample {
  blink: number;
  gazeX: number;
  gazeY: number;
  headPitch: number;
  headYaw: number;
  headRoll: number;
  breath: number;
}

export interface NaturalMotionInput {
  elapsedSeconds: number;
  enabled: boolean;
  blinkEnabled: boolean;
  reducedMotion: boolean;
}

export interface NaturalMotionController {
  sample: (input: NaturalMotionInput) => Readonly<NaturalMotionSample>;
}

export const NEUTRAL_NATURAL_MOTION: Readonly<NaturalMotionSample> = Object.freeze({
  blink: 0,
  gazeX: 0,
  gazeY: 0,
  headPitch: 0,
  headYaw: 0,
  headRoll: 0,
  breath: 0,
});

interface VectorSample {
  x: number;
  y: number;
  z: number;
}

interface TargetSegment {
  start: number;
  transitionEnd: number;
  end: number;
  from: VectorSample;
  to: VectorSample;
}

interface TargetTrackOptions {
  initialHold: readonly [number, number];
  transition: readonly [number, number];
  hold: readonly [number, number];
  scale: VectorSample;
  centerBias: number;
}

interface BlinkEvent {
  start: number;
  end: number;
}

interface BreathCycle {
  start: number;
  end: number;
  amplitude: number;
}

function seedHash(seed: string | number) {
  const source = String(seed);
  let hash = 2166136261;
  for (let index = 0; index < source.length; index += 1) {
    hash ^= source.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function randomUnit(seed: number, stream: number, index: number) {
  let value = seed ^ Math.imul(stream + 1, 0x9e3779b1) ^ Math.imul(index + 1, 0x85ebca77);
  value ^= value >>> 16;
  value = Math.imul(value, 0x7feb352d);
  value ^= value >>> 15;
  value = Math.imul(value, 0x846ca68b);
  value ^= value >>> 16;
  return (value >>> 0) / 0x1_0000_0000;
}

function between(minimum: number, maximum: number, unit: number) {
  return minimum + (maximum - minimum) * unit;
}

function signed(unit: number) {
  return unit * 2 - 1;
}

function smoothstep(progress: number) {
  const bounded = Math.min(1, Math.max(0, progress));
  return bounded * bounded * (3 - 2 * bounded);
}

function mix(from: number, to: number, amount: number) {
  return from + (to - from) * amount;
}

class SeededTargetTrack {
  private readonly segments: TargetSegment[] = [];
  private nextStart: number;
  private target: VectorSample = { x: 0, y: 0, z: 0 };
  private segmentIndex = 0;

  constructor(
    private readonly seed: number,
    private readonly stream: number,
    private readonly options: TargetTrackOptions,
  ) {
    this.nextStart = between(
      options.initialHold[0],
      options.initialHold[1],
      randomUnit(seed, stream, 0),
    );
  }

  sample(elapsedSeconds: number): VectorSample {
    while (this.nextStart <= elapsedSeconds) this.appendSegment();
    let active: TargetSegment | undefined;
    for (let index = this.segments.length - 1; index >= 0; index -= 1) {
      if (this.segments[index].start <= elapsedSeconds) {
        active = this.segments[index];
        break;
      }
    }
    if (!active) return { x: 0, y: 0, z: 0 };
    if (elapsedSeconds >= active.transitionEnd) return active.to;
    const progress = smoothstep(
      (elapsedSeconds - active.start) / (active.transitionEnd - active.start),
    );
    return {
      x: mix(active.from.x, active.to.x, progress),
      y: mix(active.from.y, active.to.y, progress),
      z: mix(active.from.z, active.to.z, progress),
    };
  }

  private appendSegment() {
    const index = this.segmentIndex;
    const randomIndex = index * 8 + 1;
    const transitionDuration = between(
      this.options.transition[0],
      this.options.transition[1],
      randomUnit(this.seed, this.stream, randomIndex),
    );
    const holdDuration = between(
      this.options.hold[0],
      this.options.hold[1],
      randomUnit(this.seed, this.stream, randomIndex + 1),
    );
    const centerScale = randomUnit(this.seed, this.stream, randomIndex + 2) < this.options.centerBias
      ? 0.24
      : 1;
    const nextTarget = {
      x: signed(randomUnit(this.seed, this.stream, randomIndex + 3)) * this.options.scale.x * centerScale,
      y: signed(randomUnit(this.seed, this.stream, randomIndex + 4)) * this.options.scale.y * centerScale,
      z: signed(randomUnit(this.seed, this.stream, randomIndex + 5)) * this.options.scale.z * centerScale,
    };
    const segment: TargetSegment = {
      start: this.nextStart,
      transitionEnd: this.nextStart + transitionDuration,
      end: this.nextStart + transitionDuration + holdDuration,
      from: this.target,
      to: nextTarget,
    };
    this.segments.push(segment);
    this.target = nextTarget;
    this.nextStart = segment.end;
    this.segmentIndex += 1;
  }
}

class SeededNaturalMotionController implements NaturalMotionController {
  private readonly seed: number;
  private readonly gaze: SeededTargetTrack;
  private readonly head: SeededTargetTrack;
  private readonly blinks: BlinkEvent[] = [];
  private readonly breaths: BreathCycle[] = [];
  private nextBlinkStart: number;
  private nextBreathStart = 0;
  private blinkIndex = 0;
  private breathIndex = 0;

  constructor(seed: string | number) {
    this.seed = seedHash(seed);
    this.nextBlinkStart = between(1.8, 3.9, randomUnit(this.seed, 11, 0));
    this.gaze = new SeededTargetTrack(this.seed, 23, {
      initialHold: [0.7, 1.8],
      transition: [0.16, 0.42],
      hold: [1.25, 3.6],
      scale: { x: 0.82, y: 0.52, z: 0 },
      centerBias: 0.24,
    });
    this.head = new SeededTargetTrack(this.seed, 37, {
      initialHold: [0.9, 2.2],
      transition: [0.75, 1.65],
      hold: [1.4, 3.9],
      scale: { x: 0.62, y: 0.78, z: 0.55 },
      centerBias: 0.16,
    });
  }

  sample(input: NaturalMotionInput): Readonly<NaturalMotionSample> {
    if (input.reducedMotion || !input.enabled) return NEUTRAL_NATURAL_MOTION;
    const elapsedSeconds = Number.isFinite(input.elapsedSeconds)
      ? Math.max(0, input.elapsedSeconds)
      : 0;
    const gaze = this.gaze.sample(elapsedSeconds);
    const head = this.head.sample(elapsedSeconds);
    return {
      blink: input.blinkEnabled ? this.sampleBlink(elapsedSeconds) : 0,
      gazeX: gaze.x,
      gazeY: gaze.y,
      headPitch: head.x,
      headYaw: head.y,
      headRoll: head.z,
      breath: this.sampleBreath(elapsedSeconds),
    };
  }

  private sampleBlink(elapsedSeconds: number) {
    while (this.nextBlinkStart <= elapsedSeconds) this.appendBlink();
    let active: BlinkEvent | undefined;
    for (let index = this.blinks.length - 1; index >= 0; index -= 1) {
      const event = this.blinks[index];
      if (event.start <= elapsedSeconds && event.end >= elapsedSeconds) {
        active = event;
        break;
      }
      if (event.end < elapsedSeconds) break;
    }
    if (!active) return 0;
    const progress = (elapsedSeconds - active.start) / (active.end - active.start);
    return Math.pow(Math.sin(progress * Math.PI), 0.7);
  }

  private appendBlink() {
    const index = this.blinkIndex;
    const randomIndex = index * 4 + 1;
    const duration = between(0.14, 0.23, randomUnit(this.seed, 11, randomIndex));
    const event = { start: this.nextBlinkStart, end: this.nextBlinkStart + duration };
    this.blinks.push(event);
    const doubleBlink = randomUnit(this.seed, 11, randomIndex + 1) < 0.12;
    const rest = doubleBlink
      ? between(0.12, 0.2, randomUnit(this.seed, 11, randomIndex + 2))
      : between(2.35, 5.65, randomUnit(this.seed, 11, randomIndex + 2));
    this.nextBlinkStart = event.end + rest;
    this.blinkIndex += 1;
  }

  private sampleBreath(elapsedSeconds: number) {
    while (this.nextBreathStart <= elapsedSeconds) this.appendBreath();
    let active = this.breaths[this.breaths.length - 1];
    for (let index = this.breaths.length - 1; index >= 0; index -= 1) {
      if (this.breaths[index].start <= elapsedSeconds) {
        active = this.breaths[index];
        break;
      }
    }
    if (!active) return 0;
    const progress = (elapsedSeconds - active.start) / (active.end - active.start);
    return Math.sin(progress * Math.PI * 2) * active.amplitude;
  }

  private appendBreath() {
    const index = this.breathIndex;
    const duration = between(3.25, 5.05, randomUnit(this.seed, 53, index * 2));
    const amplitude = between(0.72, 1, randomUnit(this.seed, 53, index * 2 + 1));
    const cycle = {
      start: this.nextBreathStart,
      end: this.nextBreathStart + duration,
      amplitude,
    };
    this.breaths.push(cycle);
    this.nextBreathStart = cycle.end;
    this.breathIndex += 1;
  }
}

export function createNaturalMotionController(
  seed: string | number = ANANYA_NATURAL_MOTION_SEED,
): NaturalMotionController {
  return new SeededNaturalMotionController(seed);
}
