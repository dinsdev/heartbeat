/**
 * Playback time in seconds of the recording, driven by a monotonic clock in
 * milliseconds (`performance.now` in the page). It reads the time when asked,
 * so a hidden tab that skips frames resumes at the right place (PLAN section
 * 7, edge case 5). Speeds other than 1x arrive in Goal B.
 */
export class PlaybackClock {
  #now: () => number;
  #duration: number;
  #position: number;
  #startedAt: number | undefined;

  constructor(now: () => number, position: number, duration: number) {
    this.#now = now;
    this.#duration = duration;
    this.#position = Math.min(Math.max(position, 0), duration);
  }

  get playing(): boolean {
    this.position();
    return this.#startedAt !== undefined;
  }

  get duration(): number {
    return this.#duration;
  }

  position(): number {
    if (this.#startedAt === undefined) return this.#position;
    const now = this.#now();
    const position = this.#position + (now - this.#startedAt) / 1000;
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

  seek(seconds: number): void {
    const wasPlaying = this.#startedAt !== undefined;
    this.#position = Math.min(Math.max(seconds, 0), this.#duration);
    this.#startedAt = wasPlaying ? this.#now() : undefined;
  }
}
