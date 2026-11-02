export interface FrameHost {
  request(callback: () => void): number;
  cancel(id: number): void;
  hidden(): boolean;
}

/**
 * The trace's animation loop (design call 6). A frame runs on request and
 * asks for the next one only while it returns true (playing or coasting) and
 * the page is visible. A hidden page gets no frames; the playback clock reads
 * real time, so the first frame after it is shown lands at the right place
 * (PLAN section 7, edge case 5).
 */
export class FrameLoop {
  #host: FrameHost;
  #frame: () => boolean;
  #pending = 0;
  #stopped = false;

  constructor(host: FrameHost, frame: () => boolean) {
    this.#host = host;
    this.#frame = frame;
  }

  wake(): void {
    if (this.#pending || this.#stopped || this.#host.hidden()) return;
    this.#pending = this.#host.request(() => {
      this.#pending = 0;
      if (this.#frame()) this.wake();
    });
  }

  visibilityChanged(): void {
    this.wake();
  }

  stop(): void {
    this.#stopped = true;
    if (this.#pending) this.#host.cancel(this.#pending);
    this.#pending = 0;
  }
}
