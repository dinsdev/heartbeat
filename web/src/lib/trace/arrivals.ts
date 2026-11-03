import type { Marker } from "./markers";

/** How long a label takes to land on its beat. */
export const ARRIVAL_MS = 260;

/**
 * When each beat's label arrived, for the landing motion on the trace. Only a
 * beat seen pending and then labeled lands; labels already known when a beat
 * comes into view (a seek, a new record) are drawn settled. Beats that leave
 * the view are forgotten, so the maps stay as small as the view.
 */
export class LabelArrivals {
  /** Off under reduced motion: every label is drawn settled. */
  enabled = true;
  #pending = new Set<number>();
  #landed = new Map<number, number>();

  observe(markers: readonly Marker[], nowMs: number): void {
    const inView = new Set<number>();
    for (const marker of markers) {
      inView.add(marker.row);
      if (marker.kind === "pending") {
        this.#pending.add(marker.row);
      } else if (this.#pending.delete(marker.row) && this.enabled) {
        if (marker.kind !== "q") this.#landed.set(marker.row, nowMs);
      }
    }
    for (const row of this.#pending) {
      if (!inView.has(row)) this.#pending.delete(row);
    }
    for (const row of this.#landed.keys()) {
      if (!inView.has(row)) this.#landed.delete(row);
    }
  }

  /** 0 when the label just arrived, 1 once it has settled. */
  progress(row: number, nowMs: number): number {
    const at = this.#landed.get(row);
    if (at === undefined) return 1;
    return Math.min(1, Math.max(0, (nowMs - at) / ARRIVAL_MS));
  }

  /** True while any label is still landing. */
  animating(nowMs: number): boolean {
    for (const at of this.#landed.values()) {
      if (nowMs - at < ARRIVAL_MS) return true;
    }
    return false;
  }
}
