// DEMO-10: the speeds the controls offer.
export const SPEEDS = [0.5, 1, 2, 4] as const;
export type Speed = (typeof SPEEDS)[number];

/**
 * Playback time in seconds of the recording, driven by a monotonic clock in
 * milliseconds (`performance.now` in the page). It reads the time when asked,
 * so a hidden tab that skips frames resumes at the right place (PLAN section
 * 7, edge case 5). The position is the playhead, the right edge of the view,
 * kept within `[min, duration]`.
 */
export class PlaybackClock {
  readonly min: number;
  #now: () => number;
  #duration: number;
  #position: number;
  #startedAt: number | undefined;
  #speed: Speed = 1;

  constructor(now: () => number, position: number, duration: number, min = 0) {
    this.#now = now;
    this.#duration = duration;
    this.min = Math.min(min, duration);
    this.#position = this.#clamp(position);
  }

  #clamp(seconds: number): number {
    return Math.min(Math.max(seconds, this.min), this.#duration);
  }

  get playing(): boolean {
    this.position();
    return this.#startedAt !== undefined;
  }

  get duration(): number {
    return this.#duration;
  }

  get speed(): Speed {
    return this.#speed;
  }

  position(): number {
    if (this.#startedAt === undefined) return this.#position;
    const now = this.#now();
    const position =
      this.#position + ((now - this.#startedAt) / 1000) * this.#speed;
    if (position >= this.#duration) {
      this.#position = this.#duration;
      this.#startedAt = undefined;
      return this.#duration;
    }
    return position;
  }

  play(): void {
    if (this.#startedAt !== undefined || this.#position >= this.#duration)
      return;
    this.#startedAt = this.#now();
  }

  pause(): void {
    this.#position = this.position();
    this.#startedAt = undefined;
  }

  setSpeed(speed: number): void {
    if (!(SPEEDS as readonly number[]).includes(speed)) {
      throw new Error(
        `no ${speed}x speed; the speeds are ${SPEEDS.join(", ")}`,
      );
    }
    // Bank the time played so far at the old speed (this stops at the end).
    this.#position = this.position();
    if (this.#startedAt !== undefined) this.#startedAt = this.#now();
    this.#speed = speed as Speed;
  }

  seek(seconds: number): void {
    const wasPlaying = this.#startedAt !== undefined;
    this.#position = this.#clamp(seconds);
    this.#startedAt = wasPlaying ? this.#now() : undefined;
  }
}
