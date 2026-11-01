import { describe, expect, test } from "vitest";

import { decodeBeats } from "./data/beats";
import type { RecordEntry } from "./data/manifest";
import { LabelStore } from "./parity";
import {
  beatRows,
  recordOption,
  rowsInView,
  statusLine,
  traceSummary,
} from "./summary";

const FS = 360;
// Annotated beats every second from 1 s; the first and last are not kept.
// Kept rows 0 to 6 sit at 2 s to 8 s. Experts: N V N Q S N F.
const beats = decodeBeats({
  class: "NNVNQSNFN",
  fs_hz: FS,
  kept: "011111110",
  label: "NVNSNNN",
  probabilities: {
    N: [970000, 20000, 900000, 30000, 600000, 990000, 800000],
    S: [10000, 10000, 50000, 900000, 300000, 4000, 100000],
    V: [10000, 960000, 25000, 40000, 50000, 3000, 50000],
    F: [10000, 10000, 25000, 30000, 50000, 3000, 50000],
  },
  probability_scale: 1000000,
  record: "223",
  sample_delta: Array.from({ length: 9 }, () => FS),
});

/** A store with the Python labels shown, as the fallback does. */
function shown() {
  const store = new LabelStore(beats);
  store.useFallback();
  return store;
}

const ALL = [0, 10 * FS] as const;

test("the beats in view are the kept beats from the left edge up to the playhead", () => {
  expect(rowsInView(beats, ...ALL)).toEqual([0, 1, 2, 3, 4, 5, 6]);
  // The playhead at 5 s: beats at 2, 3 and 4 s, and the one at 5 s is not
  // drawn yet.
  expect(rowsInView(beats, 0, 5 * FS)).toEqual([0, 1, 2]);
  expect(rowsInView(beats, 9 * FS, 19 * FS)).toEqual([]);
});

describe("the beat table (DEMO-12)", () => {
  test("has time, model label, probability, expert label and match per beat", () => {
    const rows = beatRows(beats, shown(), FS, ...ALL);
    expect(rows.map((r) => r.time)).toEqual([
      "0:02.0",
      "0:03.0",
      "0:04.0",
      "0:05.0",
      "0:06.0",
      "0:07.0",
      "0:08.0",
    ]);
    expect(rows[1]).toEqual({
      row: 1,
      time: "0:03.0",
      model: "V",
      probability: "96%",
      expert: "V",
      match: "Yes",
    });
    // The experts' S at 6 s, labeled N by the model at 60%.
    expect(rows[4]).toMatchObject({
      model: "N",
      probability: "60%",
      expert: "S",
      match: "No",
    });
    // Q beats are not scored, whatever the model says.
    expect(rows[3]).toMatchObject({
      model: "S",
      expert: "Q",
      match: "Not scored",
    });
  });

  test("a beat the model has not labeled yet says so", () => {
    const store = new LabelStore(beats);
    store.setBrowser(0, "N", Float64Array.of(0.97, 0.01, 0.01, 0.01));
    const rows = beatRows(beats, store, FS, ...ALL);
    expect(rows[0]).toMatchObject({
      model: "N",
      probability: "97%",
      match: "Yes",
    });
    expect(rows[1]).toEqual({
      row: 1,
      time: "0:03.0",
      model: "",
      probability: "",
      expert: "V",
      match: "Not known yet",
    });
  });

  test("a probability under half a percent reads as under 1%", () => {
    const store = new LabelStore(beats);
    store.setBrowser(0, "F", Float64Array.of(0.996, 0.0, 0.0, 0.004));
    expect(beatRows(beats, store, FS, ...ALL)[0]!.probability).toBe("under 1%");
  });
});

describe("the status line (DEMO-12, D6)", () => {
  test("counts beats, model flags and disagreements with the experts", () => {
    // Shown labels N V N S N N N: V and S are flagged; the experts' S and F
    // beats (6 s and 8 s) are labeled N; the Q beat is not compared.
    expect(statusLine(beats, shown(), ...ALL)).toBe(
      "Last 10 seconds: 7 beats, 2 flagged, 2 differ from the experts",
    );
  });

  test("says when every labeled beat agrees, in the singular when it is one", () => {
    expect(statusLine(beats, shown(), 0, 4.5 * FS)).toBe(
      "Last 10 seconds: 3 beats, 1 flagged, all agree with the experts",
    );
    expect(statusLine(beats, shown(), 0, 6.5 * FS)).toBe(
      "Last 10 seconds: 5 beats, 2 flagged, 1 differs from the experts",
    );
    expect(statusLine(beats, shown(), 0, 2.5 * FS)).toBe(
      "Last 10 seconds: 1 beat, 0 flagged, all agree with the experts",
    );
  });

  test("names the beats still waiting for a label", () => {
    const store = new LabelStore(beats);
    store.setBrowser(0, "N", Float64Array.of(0.97, 0.01, 0.01, 0.01));
    expect(statusLine(beats, store, 0, 4.5 * FS)).toBe(
      "Last 10 seconds: 3 beats, 0 flagged, all agree with the experts, 2 not labeled yet",
    );
    expect(statusLine(beats, new LabelStore(beats), ...ALL)).toBe(
      "Last 10 seconds: 7 beats, labels not known yet",
    );
  });

  test("an empty span says so", () => {
    expect(statusLine(beats, shown(), 9 * FS, 19 * FS)).toBe(
      "Last 10 seconds: no beats",
    );
  });
});

test("the canvas label names the record, span, beat count and flags (D6)", () => {
  expect(traceSummary("223", beats, shown(), FS, ...ALL)).toBe(
    "ECG trace of record 223, 0:00 to 0:10: 7 beats, 2 flagged by the model, 2 differ from the experts",
  );
  expect(traceSummary("223", beats, new LabelStore(beats), FS, ...ALL)).toBe(
    "ECG trace of record 223, 0:00 to 0:10: 7 beats, labels not known yet",
  );
  expect(traceSummary("223", beats, shown(), FS, 9 * FS, 19 * FS)).toBe(
    "ECG trace of record 223, 0:09 to 0:19: no beats",
  );
});

test("the patient picker shows each record with its expert class counts (D4)", () => {
  const entry = {
    record: "223",
    counts: { N: 2029, S: 72, V: 473, F: 14, Q: 0 },
  } as RecordEntry;
  expect(recordOption(entry)).toBe("Record 223: 2,029 N, 72 S, 473 V, 14 F");
});
