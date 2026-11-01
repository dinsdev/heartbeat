// DEMO-03: the Worker labels the visible 10 seconds and about the next 10.
export const AHEAD_S = 10;
export const VISIBLE_S = 10;

/** Label states per kept beat. */
export const UNLABELED = 0;
export const REQUESTED = 1;
export const LABELED = 2;

/** The sample range `[from, to)` to have labeled around the playhead. */
export function labelSpan(
  playheadSample: number,
  fsHz: number,
): [number, number] {
  return [playheadSample - VISIBLE_S * fsHz, playheadSample + AHEAD_S * fsHz];
}

function firstAtOrAfter(samples: Int32Array, value: number): number {
  let low = 0;
  let high = samples.length;
  while (low < high) {
    const middle = (low + high) >>> 1;
    if (samples[middle]! < value) low = middle + 1;
    else high = middle;
  }
  return low;
}

/** Kept beats in `[from, to)` still unlabeled and not yet asked for, in order. */
export function beatsToLabel(
  keptSamples: Int32Array,
  state: Uint8Array,
  from: number,
  to: number,
): number[] {
  const out: number[] = [];
  for (
    let row = firstAtOrAfter(keptSamples, from);
    row < keptSamples.length && keptSamples[row]! < to;
    row++
  ) {
    if (state[row] === UNLABELED) out.push(row);
  }
  return out;
}
