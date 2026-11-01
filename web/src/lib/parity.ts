import type { RecordBeats } from "./data/beats";
import { CLASSES } from "./preprocess/constants";

// E5, PARITY-03: probabilities within 1e-5, labels exact.
export const PARITY_TOLERANCE = 1e-5;

/** DEMO-04's rule: the same label and all four probabilities within 1e-5. */
export function matchesPython(
  label: string,
  probabilities: ArrayLike<number>,
  pythonLabel: string,
  pythonProbabilities: ArrayLike<number>,
): boolean {
  if (label !== pythonLabel) return false;
  for (let k = 0; k < CLASSES.length; k++) {
    // Written so a NaN fails.
    if (
      !(
        Math.abs(probabilities[k]! - pythonProbabilities[k]!) <=
        PARITY_TOLERANCE
      )
    ) {
      return false;
    }
  }
  return true;
}

export interface ShownLabel {
  label: string;
  probabilities: Float64Array;
  /** "browser" for the Worker's label, "python" for the labeled fallback. */
  source: "browser" | "python";
}

export interface ParityCounts {
  /** Browser labels compared with Python so far. */
  compared: number;
  /** Of those, how many match. */
  matched: number;
  /** Kept beats in the record. */
  total: number;
}

/**
 * The one label path the trace, the table and the counter read (review focus
 * 2). Browser labels are compared with the stored Python values as they
 * arrive, never with an earlier browser result. Once the fallback is on, every
 * beat shows its Python label and nothing more is counted.
 */
export class LabelStore {
  readonly beats: RecordBeats;
  #browser = new Map<number, ShownLabel>();
  #matches = new Map<number, boolean>();
  #fallback = false;

  constructor(beats: RecordBeats) {
    this.beats = beats;
  }

  get fallback(): boolean {
    return this.#fallback;
  }

  #python(row: number): ShownLabel {
    const start = row * CLASSES.length;
    return {
      label: this.beats.pythonLabels[row]!,
      probabilities: this.beats.pythonProbabilities.slice(
        start,
        start + CLASSES.length,
      ),
      source: "python",
    };
  }

  /** Record the Worker's label for kept beat `row`. Ignored in the fallback. */
  setBrowser(row: number, label: string, probabilities: Float64Array): void {
    if (this.#fallback) return;
    const python = this.#python(row);
    this.#browser.set(row, { label, probabilities, source: "browser" });
    this.#matches.set(
      row,
      matchesPython(label, probabilities, python.label, python.probabilities),
    );
  }

  /** DEMO-05: show the precomputed labels from now on. */
  useFallback(): void {
    this.#fallback = true;
    this.#browser.clear();
    this.#matches.clear();
  }

  /** The label to show for kept beat `row`, or undefined while it is pending. */
  get(row: number): ShownLabel | undefined {
    return this.#fallback ? this.#python(row) : this.#browser.get(row);
  }

  /** Whether kept beat `row`'s browser label matches Python, if it has one. */
  matches(row: number): boolean | undefined {
    return this.#matches.get(row);
  }

  counts(): ParityCounts {
    let matched = 0;
    for (const ok of this.#matches.values()) if (ok) matched++;
    return {
      compared: this.#matches.size,
      matched,
      total: this.beats.keptIndex.length,
    };
  }
}
