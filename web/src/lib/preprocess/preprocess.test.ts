import { describe, expect, test } from "vitest";

import fixturesJson from "../../../../fixtures/parity/fixtures.json";
import {
  adjustLogits,
  calibratedProbabilities,
  labelFromLogits,
} from "./calibration";
import { FS_HZ, WINDOW_BEFORE, WINDOW_SAMPLES } from "./constants";
import { rrFeatures, rrModelInputs } from "./rr";
import { applyScaler } from "./scaler";
import { extractWindow, zscoreWindow } from "./window";

// PARITY-03: features and outputs within 1e-5, labels exact.
const TOLERANCE = 1e-5;

interface Scored {
  logits: number[];
  adjusted: number[];
  probabilities: number[];
  label: string;
}

interface FixtureBeat {
  record: string;
  sample: number;
  rr_beat_samples: number[];
  rr_beat_index: number;
  window_adu: number[];
  window_z: number[];
  rr_s: number[];
  rr_inputs: number[];
  rr_scaled: number[];
  seeds: Record<string, Scored>;
}

interface Fixtures {
  classes: string[];
  scaler: { mean: number[]; std: number[] };
  models: { seed: number; log_class_weights: number[]; temperature: number }[];
  beats: FixtureBeat[];
}

const fixtures = fixturesJson as unknown as Fixtures;

function largestDifference(
  got: ArrayLike<number>,
  expected: ArrayLike<number>,
): number {
  expect(got.length).toBe(expected.length);
  let largest = 0;
  for (let i = 0; i < got.length; i++) {
    largest = Math.max(largest, Math.abs(got[i]! - expected[i]!));
  }
  return largest;
}

describe("R30: TypeScript preprocessing matches Python step by step", () => {
  test("R30: the fixtures are the 50 DS1 beats", () => {
    expect(fixtures.beats).toHaveLength(50);
    expect(fixtures.classes).toEqual(["N", "S", "V", "F"]);
  });

  test("R30: the window is cut 96 before and 160 after, exact int16", () => {
    for (const beat of fixtures.beats) {
      // A trace holding the Python window at the beat, with other values around.
      const trace = new Int16Array(beat.sample + 400).fill(-7);
      trace.set(beat.window_adu, beat.sample - WINDOW_BEFORE);
      const window = extractWindow(trace, beat.sample);
      expect(window).toBeInstanceOf(Int16Array);
      expect(Array.from(window)).toEqual(beat.window_adu);
    }
  });

  test("R30: a window leaving the trace fails loudly", () => {
    const trace = new Int16Array(1000);
    expect(() => extractWindow(trace, 95)).toThrow(/leaves the trace/);
    expect(() => extractWindow(trace, 841)).toThrow(/leaves the trace/);
    expect(extractWindow(trace, 840)).toHaveLength(WINDOW_SAMPLES);
  });

  test("R30: z-score within 1e-5", () => {
    let largest = 0;
    for (const beat of fixtures.beats) {
      const z = zscoreWindow(Int16Array.from(beat.window_adu));
      largest = Math.max(largest, largestDifference(z, beat.window_z));
    }
    expect(largest).toBeLessThanOrEqual(TOLERANCE);
  });

  test("R30: a flat window z-scores to zeros (the floor, R51)", () => {
    const z = zscoreWindow(new Int16Array(WINDOW_SAMPLES).fill(312));
    expect(Array.from(z)).toEqual(new Array<number>(WINDOW_SAMPLES).fill(0));
    // A one-unit step has a population std of 0.5, under the floor of 2.
    const step = new Int16Array(WINDOW_SAMPLES).fill(0);
    step.fill(1, 128);
    const zs = zscoreWindow(step);
    expect(zs[0]).toBeCloseTo(-0.25, 12);
    expect(zs[255]).toBeCloseTo(0.25, 12);
  });

  test("R30: RR seconds within 1e-5 from the annotated beats", () => {
    let largest = 0;
    for (const beat of fixtures.beats) {
      const rr = rrFeatures(
        Int32Array.from(beat.rr_beat_samples),
        beat.rr_beat_index,
      );
      largest = Math.max(largest, largestDifference(rr, beat.rr_s));
    }
    expect(largest).toBeLessThanOrEqual(TOLERANCE);
  });

  test("R30: RR model inputs (log ratios) within 1e-5", () => {
    let largest = 0;
    for (const beat of fixtures.beats) {
      const inputs = rrModelInputs(Float64Array.from(beat.rr_s));
      largest = Math.max(largest, largestDifference(inputs, beat.rr_inputs));
    }
    expect(largest).toBeLessThanOrEqual(TOLERANCE);
  });

  test("R30: the RR scaler within 1e-5", () => {
    let largest = 0;
    for (const beat of fixtures.beats) {
      const scaled = applyScaler(
        Float64Array.from(beat.rr_inputs),
        fixtures.scaler,
      );
      largest = Math.max(largest, largestDifference(scaled, beat.rr_scaled));
    }
    expect(largest).toBeLessThanOrEqual(TOLERANCE);
  });

  test("R30: adjusted logits and probabilities from given logits, every seed", () => {
    let largest = 0;
    for (const model of fixtures.models) {
      for (const beat of fixtures.beats) {
        const scored = beat.seeds[String(model.seed)]!;
        const adjusted = adjustLogits(scored.logits, model.log_class_weights);
        largest = Math.max(
          largest,
          largestDifference(adjusted, scored.adjusted),
        );
        const probs = calibratedProbabilities(adjusted, model.temperature);
        largest = Math.max(
          largest,
          largestDifference(probs, scored.probabilities),
        );
      }
    }
    expect(largest).toBeLessThanOrEqual(TOLERANCE);
  });

  test("R30: the label is the argmax of the raw logits, exact", () => {
    for (const model of fixtures.models) {
      for (const beat of fixtures.beats) {
        const scored = beat.seeds[String(model.seed)]!;
        expect(labelFromLogits(scored.logits)).toBe(scored.label);
      }
    }
  });

  test("R30: the RR feature beat is the one Python numbers", () => {
    // RR features need the beat before and after (DATA-08).
    const samples = Int32Array.from([0, 360, 720]);
    expect(() => rrFeatures(samples, 0)).toThrow(/needs a beat/);
    expect(() => rrFeatures(samples, 2)).toThrow(/needs a beat/);
    expect(Array.from(rrFeatures(samples, 1)).slice(0, 2)).toEqual([
      360 / FS_HZ,
      360 / FS_HZ,
    ]);
  });
});
