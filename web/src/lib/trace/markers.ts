import type { RecordBeats } from "../data/beats";
import type { LabelStore } from "../parity";

export type MarkerKind = "label" | "disagree" | "q" | "pending";

export interface Marker {
  /** The kept beat. */
  row: number;
  sample: number;
  kind: MarkerKind;
  /** The shown model label, once known. */
  label?: string;
  /** The expert label, on a disagreement. */
  expert?: string;
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

/**
 * The marker of every kept beat in `[from, to)` (DEMO-04, DEMO-11): the model
 * letter; a ring with the expert letter on a disagreement; the grey dash for
 * Q ("not scored"); and "pending" while a label is not known. A label is
 * known only once the next beat has played, since post-RR reads it (B3), and
 * once the Worker (or the fallback) has supplied it. The first and last
 * annotated beats are never kept, so they never appear.
 */
export function markersInView(
  beats: RecordBeats,
  store: LabelStore,
  from: number,
  to: number,
  playheadSample: number,
): Marker[] {
  const out: Marker[] = [];
  for (
    let row = firstAtOrAfter(beats.keptSamples, from);
    row < beats.keptSamples.length && beats.keptSamples[row]! < to;
    row++
  ) {
    const sample = beats.keptSamples[row]!;
    const expert = beats.classes[beats.keptIndex[row]!]!;
    const shown = store.get(row);
    if (expert === "Q") {
      out.push(
        shown
          ? { row, sample, kind: "q", label: shown.label }
          : { row, sample, kind: "q" },
      );
      continue;
    }
    const next = beats.samples[beats.keptIndex[row]! + 1]!;
    if (!shown || next > playheadSample) {
      out.push({ row, sample, kind: "pending" });
    } else if (shown.label !== expert) {
      out.push({ row, sample, kind: "disagree", label: shown.label, expert });
    } else {
      out.push({ row, sample, kind: "label", label: shown.label });
    }
  }
  return out;
}
