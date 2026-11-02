import { RR_FEATURES } from "./constants";

/** The shipped `scaler.json`: per-column mean and population std. */
export interface Scaler {
  mean: readonly number[];
  std: readonly number[];
}

/** Standardize the RR inputs as `(x - mean) / std`. */
export function applyScaler(
  inputs: Float64Array,
  scaler: Scaler,
): Float64Array {
  if (
    inputs.length !== RR_FEATURES ||
    scaler.mean.length !== RR_FEATURES ||
    scaler.std.length !== RR_FEATURES
  ) {
    throw new RangeError(`the scaler and inputs have ${RR_FEATURES} columns`);
  }
  const out = new Float64Array(RR_FEATURES);
  for (let k = 0; k < RR_FEATURES; k++) {
    out[k] = (inputs[k]! - scaler.mean[k]!) / scaler.std[k]!;
  }
  return out;
}
