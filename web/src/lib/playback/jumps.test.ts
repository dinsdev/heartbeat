import { describe, expect, test } from "vitest";

import { decodeBeats } from "../data/beats";
import { LabelStore } from "../parity";
import {
  jumpTarget,
  JUMP_LEAD_S,
  nextDisagreement,
  nextIrregular,
  searchFrom,
} from "./jumps";

const FS = 360;
// Annotated beats every second; the first and last are not kept.
// Kept rows 0 to 6 sit at 2 s to 8 s.
// Expert class per kept row: N V N Q S N F
// Python label per kept row: N V N S N N N
function record(classes: string, labels: string) {
  const n = classes.length;
  const kept = "0" + "1".repeat(n - 2) + "0";
  const column = (v: number) => Array.from({ length: n - 2 }, () => v);
  return decodeBeats({
    class: classes,
    fs_hz: FS,
    kept,
    label: labels,
    probabilities: {
      N: column(970000),
      S: column(10000),
      V: column(10000),
      F: column(10000),
    },
    probability_scale: 1000000,
    record: "223",
    sample_delta: Array.from({ length: n }, () => FS),
  });
}
const beats = record("NNVNQSNFN", "NVNSNNN");
const p = Float64Array.of(0.97, 0.01, 0.01, 0.01);

describe("Next irregular beat (DEMO-10)", () => {
  test("finds the next kept beat the experts call S, V or F", () => {
    expect(nextIrregular(beats, 0)).toBe(1);
    expect(nextIrregular(beats, 3 * FS)).toBe(4); // S at 6 s
    expect(nextIrregular(beats, 6 * FS)).toBe(6); // F at 8 s
  });

  test("wraps to the first one once none is left ahead", () => {
    expect(nextIrregular(beats, 8 * FS)).toBe(1);
  });

  test("is undefined on a record with none (the 'none' message)", () => {
    expect(nextIrregular(record("NNNQNN", "NNNN"), 0)).toBeUndefined();
  });
});

describe("Next disagreement (DEMO-10)", () => {
  test("reads the shown label, so it finds what the trace marks", () => {
    const store = new LabelStore(beats);
    store.setBrowser(0, "V", p); // the experts say N at 2 s
    expect(nextDisagreement(beats, store, 0)).toBe(0);
  });

  test("ahead of the browser labels it looks through the Python labels", () => {
    // Python says N for the experts' S at 6 s, then N for the F at 8 s.
    const store = new LabelStore(beats);
    expect(nextDisagreement(beats, store, 0)).toBe(4);
    expect(nextDisagreement(beats, store, 6 * FS)).toBe(6);
  });

  test("never counts a Q beat, which is not scored", () => {
    // Row 3 at 5 s is Q with the Python label S: not a disagreement.
    const store = new LabelStore(beats);
    expect(nextDisagreement(beats, store, 4 * FS)).toBe(4);
  });

  test("a browser label that agrees hides the Python disagreement", () => {
    const store = new LabelStore(beats);
    store.setBrowser(4, "S", p);
    expect(nextDisagreement(beats, store, 0)).toBe(6);
  });

  test("wraps, and is undefined when model and experts agree throughout", () => {
    const store = new LabelStore(beats);
    expect(nextDisagreement(beats, store, 8 * FS)).toBe(4);
    const agreeing = record("NNVNN", "NVN");
    expect(
      nextDisagreement(agreeing, new LabelStore(agreeing), 0),
    ).toBeUndefined();
  });
});

describe("where a jump puts the beat", () => {
  test("scrolling: the beat sits a few seconds left of the playhead", () => {
    expect(jumpTarget(6 * FS, FS, false, 10, 1805)).toBe(10);
    expect(jumpTarget(600 * FS, FS, false, 10, 1805)).toBe(600 + JUMP_LEAD_S);
    expect(jumpTarget(1804 * FS, FS, false, 10, 1805)).toBe(1805);
  });

  test("reduced motion: the page that holds the beat", () => {
    expect(jumpTarget(603.5 * FS, FS, true, 10, 1805)).toBe(610);
    expect(jumpTarget(610 * FS, FS, true, 10, 1805)).toBe(610);
  });
});

describe("where the search for the next beat starts", () => {
  test("scrolling: from the beat a jump would have left a few seconds back", () => {
    expect(searchFrom(600, 600, FS, false)).toBe((600 - JUMP_LEAD_S) * FS);
  });

  test("under reduced motion: after the page in view", () => {
    expect(searchFrom(610, 610, FS, true)).toBe(610 * FS);
  });

  test("right after the last jump's beat while it is still in view", () => {
    // Pressed again at once: the search goes past the beat just shown, even
    // where float rounding or the end of the recording moved the playhead.
    expect(searchFrom(603, 603, FS, false, 600 * FS)).toBe(600 * FS);
    expect(searchFrom(1805, 1805, FS, false, 1804 * FS)).toBe(1804 * FS);
    // Under reduced motion the beat can sit anywhere on its page.
    expect(searchFrom(610, 610, FS, true, 601 * FS)).toBe(601 * FS);
  });

  test("a last jump out of view no longer counts", () => {
    expect(searchFrom(900, 900, FS, false, 600 * FS)).toBe(897 * FS);
    expect(searchFrom(900, 900, FS, true, 600 * FS)).toBe(900 * FS);
  });
});
