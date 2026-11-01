import type { RecordBeats } from "../data/beats";
import type { LabelStore } from "../parity";
import { pageEnd } from "./pages";

// DEMO-10: "Next irregular beat" goes to beats the experts call S, V or F.
const IRREGULAR = new Set(["S", "V", "F"]);

// A jump leaves the beat this many seconds left of the playhead, so its label
// (which needs the next beat, B3) is known and some context follows it.
export const JUMP_LEAD_S = 3;

function expertOf(beats: RecordBeats, row: number): string {
  return beats.classes[beats.keptIndex[row]!]!;
}

/** The first kept row after `afterSample` that passes `test`, wrapping once. */
function nextRow(
  beats: RecordBeats,
  afterSample: number,
  test: (row: number) => boolean,
): number | undefined {
  const n = beats.keptSamples.length;
  let start = 0;
  while (start < n && beats.keptSamples[start]! <= afterSample) start++;
  for (let k = 0; k < n; k++) {
    const row = (start + k) % n;
    if (test(row)) return row;
  }
  return undefined;
}

/** The next kept beat the experts call irregular; undefined if the record has none. */
export function nextIrregular(
  beats: RecordBeats,
  afterSample: number,
): number | undefined {
  return nextRow(beats, afterSample, (row) =>
    IRREGULAR.has(expertOf(beats, row)),
  );
}

/**
 * The next kept beat where the model and the experts differ. It reads the
 * label the trace shows (the store's); for beats the Worker has not labeled
 * yet it looks ahead through the shipped Python labels, which parity says are
 * the same. Once there, the trace shows whatever the browser computes. Q beats
 * are not scored, so never count.
 */
export function nextDisagreement(
  beats: RecordBeats,
  store: LabelStore,
  afterSample: number,
): number | undefined {
  return nextRow(beats, afterSample, (row) => {
    const expert = expertOf(beats, row);
    if (expert === "Q") return false;
    const label = store.get(row)?.label ?? beats.pythonLabels[row]!;
    return label !== expert;
  });
}

/** The playhead that puts the beat at `sample` in view. */
export function jumpTarget(
  sample: number,
  fs: number,
  reducedMotion: boolean,
  min: number,
  duration: number,
): number {
  const seconds = sample / fs;
  if (reducedMotion) return pageEnd(seconds, min, duration);
  return Math.min(Math.max(seconds + JUMP_LEAD_S, min), duration);
}
