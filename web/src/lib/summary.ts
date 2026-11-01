// What the page says about the beats in view, in words: the beat table and
// the polite status line (DEMO-12), the canvas label (D6) and the patient
// picker's options (D4). All of it reads the one label path (LabelStore).

import type { RecordBeats } from "./data/beats";
import type { RecordEntry } from "./data/manifest";
import { clockTenths, clockTime, count } from "./format";
import type { LabelStore } from "./parity";
import { CLASSES } from "./preprocess/constants";

const FLAGGED = new Set(["S", "V", "F"]);

/** Kept rows with `from <= sample < to`: the beats drawn in the view. */
export function rowsInView(
  beats: RecordBeats,
  from: number,
  to: number,
): number[] {
  const rows: number[] = [];
  beats.keptSamples.forEach((sample, row) => {
    if (sample >= from && sample < to) rows.push(row);
  });
  return rows;
}

function expertOf(beats: RecordBeats, row: number): string {
  return beats.classes[beats.keptIndex[row]!]!;
}

export interface BeatRow {
  row: number;
  time: string;
  /** The shown label, or "" while it is pending. */
  model: string;
  /** The estimated probability of the shown label (C4), or "". */
  probability: string;
  expert: string;
  match: "Yes" | "No" | "Not scored" | "Not known yet";
}

function percent(p: number): string {
  const rounded = Math.round(p * 100);
  return rounded < 1 ? "under 1%" : `${rounded}%`;
}

export function beatRows(
  beats: RecordBeats,
  store: LabelStore,
  fs: number,
  from: number,
  to: number,
): BeatRow[] {
  return rowsInView(beats, from, to).map((row) => {
    const expert = expertOf(beats, row);
    const shown = store.get(row);
    const time = clockTenths(beats.keptSamples[row]! / fs);
    if (!shown) {
      return {
        row,
        time,
        model: "",
        probability: "",
        expert,
        match: expert === "Q" ? "Not scored" : "Not known yet",
      };
    }
    const k = CLASSES.indexOf(shown.label as (typeof CLASSES)[number]);
    return {
      row,
      time,
      model: shown.label,
      probability: percent(shown.probabilities[k]!),
      expert,
      match:
        expert === "Q" ? "Not scored" : shown.label === expert ? "Yes" : "No",
    };
  });
}

interface Tally {
  beats: number;
  labeled: number;
  flagged: number;
  differ: number;
}

function tally(
  beats: RecordBeats,
  store: LabelStore,
  from: number,
  to: number,
): Tally {
  const t: Tally = { beats: 0, labeled: 0, flagged: 0, differ: 0 };
  for (const row of rowsInView(beats, from, to)) {
    t.beats++;
    const shown = store.get(row);
    if (!shown) continue;
    t.labeled++;
    if (FLAGGED.has(shown.label)) t.flagged++;
    const expert = expertOf(beats, row);
    if (expert !== "Q" && shown.label !== expert) t.differ++;
  }
  return t;
}

function plural(n: number, one: string, many: string): string {
  return `${count(n)} ${n === 1 ? one : many}`;
}

/** The counts after the beat count, or undefined when there are no beats. */
function describe(t: Tally, flaggedWord: string): string | undefined {
  if (t.beats === 0) return undefined;
  const head = plural(t.beats, "beat", "beats");
  if (t.labeled === 0) return `${head}, labels not known yet`;
  const agreement =
    t.differ === 0
      ? "all agree with the experts"
      : `${count(t.differ)} ${t.differ === 1 ? "differs" : "differ"} from the experts`;
  const pending = t.beats - t.labeled;
  return [
    head,
    `${count(t.flagged)} ${flaggedWord}`,
    agreement,
    ...(pending > 0 ? [`${count(pending)} not labeled yet`] : []),
  ].join(", ");
}

/** D6: "Last 10 seconds: 12 beats, 2 flagged, all agree with the experts". */
export function statusLine(
  beats: RecordBeats,
  store: LabelStore,
  from: number,
  to: number,
): string {
  const words = describe(tally(beats, store, from, to), "flagged");
  return `Last 10 seconds: ${words ?? "no beats"}`;
}

/** D6: the canvas's summary label, set on pause and seek. */
export function traceSummary(
  record: string,
  beats: RecordBeats,
  store: LabelStore,
  fs: number,
  from: number,
  to: number,
): string {
  const words = describe(tally(beats, store, from, to), "flagged by the model");
  const span = `${clockTime(from / fs)} to ${clockTime(to / fs)}`;
  return `ECG trace of record ${record}, ${span}: ${words ?? "no beats"}`;
}

/** D4: the picker shows each record's expert class counts. */
export function recordOption(entry: RecordEntry): string {
  const { N, S, V, F } = entry.counts;
  return `Record ${entry.record}: ${count(N)} N, ${count(S)} S, ${count(V)} V, ${count(F)} F`;
}
