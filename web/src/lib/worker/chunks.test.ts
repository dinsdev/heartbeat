import { describe, expect, test } from "vitest";

import { AHEAD_S, beatsToLabel, labelSpan } from "./chunks";

const FS = 360;
// A kept beat every second, from 1 s to 60 s.
const kept = Int32Array.from({ length: 60 }, (_, i) => (i + 1) * FS);

describe("DEMO-03: labeling about 10 seconds ahead of the playhead", () => {
  test("the span is the visible 10 seconds plus 10 ahead", () => {
    expect(AHEAD_S).toBe(10);
    expect(labelSpan(30 * FS, FS)).toEqual([20 * FS, 40 * FS]);
  });

  test("asks for the unlabeled beats in the span, in order", () => {
    const state = new Uint8Array(kept.length);
    const [from, to] = labelSpan(30 * FS, FS);
    expect(beatsToLabel(kept, state, from, to)).toEqual(
      Array.from({ length: 20 }, (_, i) => i + 19),
    );
  });

  test("skips beats already requested or labeled", () => {
    const state = new Uint8Array(kept.length);
    state.fill(1, 19, 25);
    state.fill(2, 30, 35);
    const [from, to] = labelSpan(30 * FS, FS);
    expect(beatsToLabel(kept, state, from, to)).toEqual([
      25, 26, 27, 28, 29, 35, 36, 37, 38,
    ]);
  });

  test("clips at the start and end of the recording", () => {
    const state = new Uint8Array(kept.length);
    expect(beatsToLabel(kept, state, ...labelSpan(0, FS))).toEqual(
      Array.from({ length: 9 }, (_, i) => i),
    );
    const [from, to] = labelSpan(58 * FS, FS);
    expect(beatsToLabel(kept, state, from, to)).toEqual(
      Array.from({ length: 13 }, (_, i) => i + 47),
    );
  });
});
