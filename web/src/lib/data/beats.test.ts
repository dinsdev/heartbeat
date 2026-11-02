import { describe, expect, test } from "vitest";

import { decodeBeats, type BeatsJson } from "./beats";

// The format `heartbeat.demo.build.encode_beats` writes (design call 2).
const PAYLOAD: BeatsJson = {
  class: "NNVQN",
  fs_hz: 360,
  kept: "01110",
  label: "NVN",
  probabilities: {
    F: [20000, 0, 0],
    N: [900000, 0, 500000],
    S: [50000, 250000, 500000],
    V: [30000, 750000, 0],
  },
  probability_scale: 1000000,
  record: "223",
  sample_delta: [100, 288, 288, 200, 288],
};

describe("the beats file", () => {
  test("decodes delta samples, classes and the kept beats", () => {
    const beats = decodeBeats(PAYLOAD);
    expect(beats.record).toBe("223");
    expect(Array.from(beats.samples)).toEqual([100, 388, 676, 876, 1164]);
    expect(beats.classes).toBe("NNVQN");
    expect(Array.from(beats.keptIndex)).toEqual([1, 2, 3]);
    expect(Array.from(beats.keptSamples)).toEqual([388, 676, 876]);
    expect(beats.pythonLabels).toBe("NVN");
  });

  test("decodes the Python probabilities per kept beat in class order", () => {
    const beats = decodeBeats(PAYLOAD);
    expect(Array.from(beats.pythonProbabilities.subarray(0, 4))).toEqual([
      0.9, 0.05, 0.03, 0.02,
    ]);
    expect(Array.from(beats.pythonProbabilities.subarray(4, 8))).toEqual([
      0, 0.25, 0.75, 0,
    ]);
  });

  test("refuses a file whose columns disagree", () => {
    expect(() => decodeBeats({ ...PAYLOAD, label: "NV" })).toThrow(/label/);
    expect(() => decodeBeats({ ...PAYLOAD, kept: "0111" })).toThrow(/kept/);
    expect(() => decodeBeats({ ...PAYLOAD, fs_hz: 250 })).toThrow(/360/);
  });
});
