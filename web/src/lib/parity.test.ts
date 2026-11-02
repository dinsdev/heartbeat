import { describe, expect, test } from "vitest";

import { decodeBeats } from "./data/beats";
import { LabelStore, matchesPython, PARITY_TOLERANCE } from "./parity";

const PYTHON = Float64Array.of(0.9, 0.05, 0.03, 0.02);

function store(): LabelStore {
  return new LabelStore(
    decodeBeats({
      class: "NNVNN",
      fs_hz: 360,
      kept: "01110",
      label: "NVN",
      probabilities: {
        N: [900000, 10000, 990000],
        S: [50000, 10000, 5000],
        V: [30000, 970000, 5000],
        F: [20000, 10000, 0],
      },
      probability_scale: 1000000,
      record: "223",
      sample_delta: [100, 288, 288, 200, 288],
    }),
  );
}

describe("the parity rule (DEMO-04)", () => {
  test("a beat matches with the same label and every probability within 1e-5", () => {
    expect(PARITY_TOLERANCE).toBe(1e-5);
    const near = Float64Array.of(0.9 + 9e-6, 0.05 - 9e-6, 0.03, 0.02);
    expect(matchesPython("N", near, "N", PYTHON)).toBe(true);
  });

  test("a different label never matches", () => {
    expect(matchesPython("S", PYTHON, "N", PYTHON)).toBe(false);
  });

  test("one probability past 1e-5 does not match", () => {
    const off = Float64Array.of(0.9, 0.05, 0.03 + 1.1e-5, 0.02);
    expect(matchesPython("N", off, "N", PYTHON)).toBe(false);
  });

  test("a NaN probability does not match", () => {
    const bad = Float64Array.of(Number.NaN, 0.05, 0.03, 0.02);
    expect(matchesPython("N", bad, "N", PYTHON)).toBe(false);
  });
});

describe("the label store and its counter", () => {
  test("counts browser labels against the stored Python values", () => {
    const labels = store();
    expect(labels.counts()).toEqual({ compared: 0, matched: 0, total: 3 });
    labels.setBrowser(0, "N", Float64Array.of(0.9, 0.05, 0.03, 0.02));
    labels.setBrowser(1, "V", Float64Array.of(0.01, 0.01, 0.97, 0.01));
    expect(labels.counts()).toEqual({ compared: 2, matched: 2, total: 3 });
    expect(labels.get(1)).toMatchObject({ label: "V", source: "browser" });
    expect(labels.get(2)).toBeUndefined();
  });

  test("shows a mismatch, and relabeling a beat compares it to Python again", () => {
    const labels = store();
    labels.setBrowser(2, "S", Float64Array.of(0.99, 0.005, 0.005, 0));
    expect(labels.counts()).toEqual({ compared: 1, matched: 0, total: 3 });
    // The second result is compared with Python, never with the first.
    labels.setBrowser(2, "N", Float64Array.of(0.99, 0.005, 0.005, 0));
    expect(labels.counts()).toEqual({ compared: 1, matched: 1, total: 3 });
  });

  test("the fallback plays the Python labels and is never counted", () => {
    const labels = store();
    labels.setBrowser(0, "N", Float64Array.of(0.9, 0.05, 0.03, 0.02));
    labels.useFallback();
    expect(labels.fallback).toBe(true);
    expect(labels.get(1)).toMatchObject({ label: "V", source: "python" });
    expect(labels.get(0)).toMatchObject({ label: "N", source: "python" });
    expect(labels.counts()).toEqual({ compared: 0, matched: 0, total: 3 });
    labels.setBrowser(2, "N", Float64Array.of(0.99, 0.005, 0.005, 0));
    expect(labels.counts()).toEqual({ compared: 0, matched: 0, total: 3 });
  });
});
