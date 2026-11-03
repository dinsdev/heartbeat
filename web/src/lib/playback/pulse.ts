/**
 * True when an annotated beat lies in `(fromSample, toSample]`: the playhead
 * passed it since the last frame, so the beat dot pulses once.
 */
export function beatBetween(
  samples: Int32Array,
  fromSample: number,
  toSample: number,
): boolean {
  if (toSample <= fromSample) return false;
  let low = 0;
  let high = samples.length;
  // The first beat after `fromSample`.
  while (low < high) {
    const middle = (low + high) >>> 1;
    if (samples[middle]! <= fromSample) low = middle + 1;
    else high = middle;
  }
  return low < samples.length && samples[low]! <= toSample;
}
