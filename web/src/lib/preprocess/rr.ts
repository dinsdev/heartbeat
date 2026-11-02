import {
  FS_HZ,
  RR_FEATURES,
  RR_LOCAL_INTERVALS,
  RR_LONG_WINDOW_SAMPLES,
} from "./constants";

/** First index `k` with `samples[k] >= value`, as NumPy's `searchsorted(side="left")`. */
function searchLeft(samples: Int32Array, value: number): number {
  let low = 0;
  let high = samples.length;
  while (low < high) {
    const middle = (low + high) >>> 1;
    if (samples[middle]! < value) low = middle + 1;
    else high = middle;
  }
  return low;
}

/**
 * The six RR features of beat `i` (DATA-07), in the Python column order:
 * pre-RR, post-RR, local average, long average (seconds), pre over local,
 * post over pre. `samples` holds every annotated beat of the record, Q
 * included, strictly increasing; only post-RR looks ahead (R8).
 */
export function rrFeatures(samples: Int32Array, i: number): Float64Array {
  if (i < 1 || i > samples.length - 2) {
    throw new RangeError(
      `beat ${i} of ${samples.length}: RR features needs a beat before and after`,
    );
  }
  // rr(k) is the interval ending at beat k, in seconds.
  const rr = (k: number) => (samples[k]! - samples[k - 1]!) / FS_HZ;
  const pre = rr(i);
  const post = rr(i + 1);
  const firstLocal = Math.max(1, i - RR_LOCAL_INTERVALS + 1);
  let localSum = 0;
  for (let k = firstLocal; k <= i; k++) localSum += rr(k);
  const local = localSum / (i - firstLocal + 1);
  const firstLong = Math.max(
    1,
    searchLeft(samples, samples[i]! - RR_LONG_WINDOW_SAMPLES),
  );
  let longSum = 0;
  for (let k = firstLong; k <= i; k++) longSum += rr(k);
  const long = longSum / (i - firstLong + 1);
  return Float64Array.of(pre, post, local, long, pre / local, post / pre);
}

/** The model's RR inputs: the four intervals, then the log of each ratio (C2). */
export function rrModelInputs(rr: Float64Array): Float64Array {
  if (rr.length !== RR_FEATURES) {
    throw new RangeError(`RR features have ${RR_FEATURES} values`);
  }
  const out = Float64Array.from(rr);
  for (const column of [4, 5]) {
    const ratio = out[column]!;
    if (!(ratio > 0)) {
      throw new RangeError(`ratio column ${column} is not positive: ${ratio}`);
    }
    out[column] = Math.log(ratio);
  }
  return out;
}
