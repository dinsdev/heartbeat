import { describe, expect, test } from "vitest";

import { decodeBeats } from "../data/beats";
import { LabelStore } from "../parity";
import { markersInView } from "./markers";

const FS = 360;
// Annotated beats every second; the first and last are not kept.
// Expert classes:   N N V N Q S N
// Python labels per kept beat (5): N V N N N
const beats = decodeBeats({
  class: "NNVNQSN",
  fs_hz: FS,
  kept: "0111110",
  label: "NVNNN",
  probabilities: {
    N: [990000, 10000, 990000, 990000, 900000],
    S: [5000, 10000, 5000, 5000, 90000],
    V: [5000, 970000, 5000, 5000, 5000],
    F: [0, 10000, 0, 0, 5000],
  },
  probability_scale: 1000000,
  record: "223",
  sample_delta: [FS, FS, FS, FS, FS, FS, FS],
});
const p = (n: number) =>
  Float64Array.of(n, (1 - n) / 3, (1 - n) / 3, (1 - n) / 3);

describe("beat markers (DEMO-04, DEMO-11)", () => {
  test("a beat shows its model letter once its label is known", () => {
    const store = new LabelStore(beats);
    store.setBrowser(0, "N", p(0.99));
    const [first] = markersInView(beats, store, 0, 3 * FS, 10 * FS);
    expect(first).toEqual({
      row: 0,
      sample: 2 * FS,
      kind: "label",
      label: "N",
    });
  });

  test("a disagreement carries the expert letter for beneath the ring", () => {
    const store = new LabelStore(beats);
    store.setBrowser(4, "N", p(0.9)); // the expert says S
    const marker = markersInView(beats, store, 6 * FS, 7 * FS, 10 * FS)[0];
    expect(marker).toEqual({
      row: 4,
      sample: 6 * FS,
      kind: "disagree",
      label: "N",
      expert: "S",
    });
  });

  test("a Q beat shows the not-scored dash whatever the model says", () => {
    const store = new LabelStore(beats);
    store.setBrowser(3, "N", p(0.99));
    const marker = markersInView(beats, store, 5 * FS, 6 * FS, 10 * FS)[0];
    expect(marker).toMatchObject({ row: 3, kind: "q" });
  });

  test("a beat is pending until the next beat has arrived (the one-beat lag)", () => {
    const store = new LabelStore(beats);
    store.setBrowser(1, "V", p(0.97));
    // Kept beat 1 is at 3 s; its post-RR needs the beat at 4 s.
    expect(
      markersInView(beats, store, 3 * FS, 4 * FS, 4 * FS - 1)[0],
    ).toMatchObject({
      kind: "pending",
    });
    expect(
      markersInView(beats, store, 3 * FS, 4 * FS, 4 * FS)[0],
    ).toMatchObject({
      kind: "label",
      label: "V",
    });
  });

  test("a beat without a label yet is pending, never a guessed class", () => {
    const store = new LabelStore(beats);
    expect(
      markersInView(beats, store, 0, 10 * FS, 10 * FS).map((m) => m.kind),
    ).toEqual(["pending", "pending", "pending", "q", "pending"]);
  });

  test("the fallback shows the Python labels, marked the same way", () => {
    const store = new LabelStore(beats);
    store.useFallback();
    expect(
      markersInView(beats, store, 0, 10 * FS, 10 * FS).map(
        (m) => `${m.kind}:${m.label}`,
      ),
    ).toEqual(["label:N", "label:V", "label:N", "q:N", "disagree:N"]);
  });

  test("the first and last annotated beats are absent by design (B3)", () => {
    const store = new LabelStore(beats);
    const rows = markersInView(beats, store, 0, 100 * FS, 100 * FS).map(
      (m) => m.sample,
    );
    expect(rows).not.toContain(FS);
    expect(rows).not.toContain(7 * FS);
  });
});
