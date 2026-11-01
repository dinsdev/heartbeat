import {
  WINDOW_AFTER,
  WINDOW_BEFORE,
  WINDOW_SAMPLES,
  ZSCORE_STD_FLOOR_ADU,
} from "./constants";

/** The beat's window, `trace[sample - 96, sample + 160)`, with no realignment (R7). */
export function extractWindow(trace: Int16Array, sample: number): Int16Array {
  const start = sample - WINDOW_BEFORE;
  const stop = sample + WINDOW_AFTER;
  if (start < 0 || stop > trace.length) {
    throw new RangeError(
      `beat at sample ${sample}: window [${start}, ${stop}) leaves the trace of ${trace.length} samples`,
    );
  }
  return trace.subarray(start, stop);
}

/**
 * Z-score a window as `(x - mean) / max(std, 2)` with the population std
 * (DATA-06, R51), in float64 like NumPy. A flat window becomes all zeros.
 */
export function zscoreWindow(window: Int16Array): Float64Array {
  if (window.length !== WINDOW_SAMPLES) {
    throw new RangeError(
      `a window has ${WINDOW_SAMPLES} samples, got ${window.length}`,
    );
  }
  let sum = 0;
  for (const x of window) sum += x;
  const mean = sum / window.length;
  let squares = 0;
  for (const x of window) squares += (x - mean) * (x - mean);
  const std = Math.sqrt(squares / window.length);
  const scale = Math.max(std, ZSCORE_STD_FLOOR_ADU);
  const z = new Float64Array(window.length);
  for (let i = 0; i < window.length; i++) z[i] = (window[i]! - mean) / scale;
  return z;
}
