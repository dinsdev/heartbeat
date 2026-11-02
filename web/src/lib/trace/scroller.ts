// Drag to scrub (settling 7, design call 7): the paper follows the pointer
// 1:1, coasts on release with the release velocity under exponential
// friction, rubber-bands at the ends of the recording with a critically
// damped spring, and stops at once on any new pointer down. Under reduced
// motion a drag moves by whole 10-second pages and nothing animates.
//
// Positions are the playhead in seconds (the view's right edge), times are
// milliseconds from the caller's clock, so the tests run on a fake one.

import { stepPage } from "../playback/pages";
import { SPAN_S } from "./geometry";

// apple-design: scroll deceleration of 0.998 per millisecond, as a time
// constant: velocity falls by 1/e every 499.5 ms.
export const COAST_TIME_CONSTANT_MS = -1 / Math.log(0.998);
// The spring's response (apple-design: 0.4 s, critically damped).
const SPRING_OMEGA = (2 * Math.PI) / 0.4;
// Release velocity is read over the last 100 ms of pointer samples.
const VELOCITY_WINDOW_MS = 100;
// Motion ends below these, in screen pixels.
const REST_SPEED_PX_S = 5;
const REST_OFFSET_PX = 0.25;
// apple-design's rubber band constant; the band's dimension is the view.
const RUBBER_BAND = 0.55;

export interface ScrollerOptions {
  /** The playhead's range: one span in, to the end of the recording. */
  min: number;
  max: number;
  /** Screen pixels per second of recording (the strip's width over 10 s). */
  pxPerSecond: number;
  reducedMotion: boolean;
}

type Motion =
  | { kind: "rest" }
  | { kind: "drag"; grabX: number; grabPosition: number; x: number }
  | { kind: "coast"; t0: number; p0: number; v0: number }
  | { kind: "spring"; t0: number; bound: number; x0: number; v0: number };

function rubberBand(overshoot: number): number {
  const d = SPAN_S;
  return (
    (overshoot * d * RUBBER_BAND) / (d + RUBBER_BAND * Math.abs(overshoot))
  );
}

export class Scroller {
  #position: number;
  #options: ScrollerOptions;
  #motion: Motion = { kind: "rest" };
  #samples: { t: number; position: number }[] = [];

  constructor(position: number, options: ScrollerOptions) {
    this.#options = { ...options };
    this.#position = this.#clamp(position);
  }

  #clamp(position: number): number {
    return Math.min(Math.max(position, this.#options.min), this.#options.max);
  }

  /** Dragging, or moving on its own after a release. */
  get active(): boolean {
    return this.#motion.kind !== "rest";
  }

  get dragging(): boolean {
    return this.#motion.kind === "drag";
  }

  setPxPerSecond(pxPerSecond: number): void {
    this.#options.pxPerSecond = pxPerSecond;
  }

  setBounds(min: number, max: number): void {
    this.#options.min = min;
    this.#options.max = max;
    if (!this.active) this.#position = this.#clamp(this.#position);
  }

  /** Put the playhead somewhere else (slider, jump, playback), stopping any motion. */
  jumpTo(position: number): void {
    this.#motion = { kind: "rest" };
    this.#position = this.#clamp(position);
  }

  /** A pointer goes down: stop where the paper is on screen and hold it. */
  down(x: number, t: number): void {
    const here = this.step(t);
    this.#motion = { kind: "drag", grabX: x, grabPosition: here, x };
    this.#samples = [{ t, position: here }];
  }

  move(x: number, t: number): void {
    if (this.#motion.kind !== "drag") return;
    this.#motion.x = x;
    if (this.#options.reducedMotion) return;
    const position = this.#dragPosition(this.#motion);
    this.#position = position;
    this.#samples.push({ t, position });
    while (this.#samples.length > 2 && this.#samples[0]!.t < t - 1000) {
      this.#samples.shift();
    }
  }

  up(t: number): void {
    const motion = this.#motion;
    if (motion.kind !== "drag") return;
    if (this.#options.reducedMotion) {
      this.#motion = { kind: "rest" };
      this.#pageBy(motion.x - motion.grabX);
      return;
    }
    const position = this.#dragPosition(motion);
    const velocity = this.#releaseVelocity(t);
    const bound = this.#boundBeyond(position);
    if (bound !== undefined) {
      this.#motion = {
        kind: "spring",
        t0: t,
        bound,
        x0: position - bound,
        v0: velocity,
      };
    } else if (
      Math.abs(velocity) * this.#options.pxPerSecond >
      REST_SPEED_PX_S
    ) {
      this.#motion = { kind: "coast", t0: t, p0: position, v0: velocity };
    } else {
      this.#motion = { kind: "rest" };
    }
    this.#position = position;
  }

  /** Advance any motion to time `t` and return the playhead. */
  step(t: number): number {
    const motion = this.#motion;
    if (motion.kind === "coast") this.#stepCoast(motion, t);
    else if (motion.kind === "spring") this.#stepSpring(motion, t);
    return this.#position;
  }

  #dragPosition(motion: Extract<Motion, { kind: "drag" }>): number {
    // Dragging right brings earlier paper into view.
    const raw =
      motion.grabPosition -
      (motion.x - motion.grabX) / this.#options.pxPerSecond;
    const bound = this.#boundBeyond(raw);
    return bound === undefined ? raw : bound + rubberBand(raw - bound);
  }

  #boundBeyond(position: number): number | undefined {
    if (position < this.#options.min) return this.#options.min;
    if (position > this.#options.max) return this.#options.max;
    return undefined;
  }

  #releaseVelocity(t: number): number {
    const recent = this.#samples.filter((s) => s.t >= t - VELOCITY_WINDOW_MS);
    if (recent.length < 2) return 0;
    const first = recent[0]!;
    const last = recent[recent.length - 1]!;
    if (last.t <= first.t) return 0;
    return ((last.position - first.position) / (last.t - first.t)) * 1000;
  }

  #pageBy(dx: number): void {
    const width = this.#options.pxPerSecond * SPAN_S;
    const threshold = Math.min(48, width / 4);
    if (Math.abs(dx) < threshold) return;
    const pages =
      -Math.sign(dx) * Math.max(1, Math.round(Math.abs(dx) / width));
    this.#position = stepPage(
      this.#position,
      pages,
      this.#options.min,
      this.#options.max,
    );
  }

  #stepCoast(motion: Extract<Motion, { kind: "coast" }>, t: number): void {
    const tau = COAST_TIME_CONSTANT_MS / 1000;
    const { p0, v0 } = motion;
    const dt = Math.max(0, t - motion.t0) / 1000;
    const position = p0 + v0 * tau * (1 - Math.exp(-dt / tau));
    const bound = this.#boundBeyond(position);
    if (bound !== undefined) {
      // The paper reaches an end mid-coast: the spring takes over there,
      // carrying the velocity it had at that moment.
      const remaining = 1 - (bound - p0) / (v0 * tau);
      const hit = remaining > 0 ? -tau * Math.log(remaining) : 0;
      this.#motion = {
        kind: "spring",
        t0: motion.t0 + hit * 1000,
        bound,
        x0: 0,
        v0: v0 * Math.exp(-hit / tau),
      };
      this.#stepSpring(this.#motion, t);
      return;
    }
    this.#position = position;
    const velocity = v0 * Math.exp(-dt / tau);
    if (Math.abs(velocity) * this.#options.pxPerSecond < REST_SPEED_PX_S) {
      this.#motion = { kind: "rest" };
    }
  }

  #stepSpring(motion: Extract<Motion, { kind: "spring" }>, t: number): void {
    // Critically damped: x(t) = (x0 + (v0 + w x0) t) e^(-w t).
    const w = SPRING_OMEGA;
    const { x0, v0 } = motion;
    const dt = Math.max(0, t - motion.t0) / 1000;
    const b = v0 + w * x0;
    const decay = Math.exp(-w * dt);
    const x = (x0 + b * dt) * decay;
    const v = (v0 - w * b * dt) * decay;
    const pps = this.#options.pxPerSecond;
    if (
      dt > 0 &&
      Math.abs(x) * pps < REST_OFFSET_PX &&
      Math.abs(v) * pps < REST_SPEED_PX_S
    ) {
      this.#motion = { kind: "rest" };
      this.#position = motion.bound;
      return;
    }
    this.#position = motion.bound + x;
  }
}
