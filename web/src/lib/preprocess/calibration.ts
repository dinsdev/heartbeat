import { CLASSES, type ScoredClass } from "./constants";

/** The shipped `calibration.json` (EVAL-11). */
export interface Calibration {
  log_class_weights: readonly number[];
  temperature: number;
}

/** Logit adjustment: the raw logits minus the log class weights. */
export function adjustLogits(
  logits: ArrayLike<number>,
  logClassWeights: readonly number[],
): Float64Array {
  const out = new Float64Array(CLASSES.length);
  for (let k = 0; k < CLASSES.length; k++) {
    out[k] = logits[k]! - logClassWeights[k]!;
  }
  return out;
}

/** Softmax of the adjusted logits over the temperature, max-shifted as SciPy does. */
export function calibratedProbabilities(
  adjusted: ArrayLike<number>,
  temperature: number,
): Float64Array {
  let largest = -Infinity;
  for (let k = 0; k < CLASSES.length; k++) {
    largest = Math.max(largest, adjusted[k]! / temperature);
  }
  const out = new Float64Array(CLASSES.length);
  let sum = 0;
  for (let k = 0; k < CLASSES.length; k++) {
    out[k] = Math.exp(adjusted[k]! / temperature - largest);
    sum += out[k]!;
  }
  for (let k = 0; k < CLASSES.length; k++) out[k] = out[k]! / sum;
  return out;
}

/** The label: the argmax of the raw logits, first on a tie as NumPy (R20). */
export function labelFromLogits(logits: ArrayLike<number>): ScoredClass {
  let best = 0;
  for (let k = 1; k < CLASSES.length; k++) {
    if (logits[k]! > logits[best]!) best = k;
  }
  return CLASSES[best]!;
}
