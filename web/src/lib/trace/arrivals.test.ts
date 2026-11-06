import { describe, expect, test } from "vitest";

import { ARRIVAL_MS, LabelArrivals } from "./arrivals";
import type { Marker } from "./markers";

const pending = (row: number): Marker => ({
  row,
  sample: row * 360,
  kind: "pending",
});
const label = (row: number): Marker => ({
  row,
  sample: row * 360,
  kind: "label",
  label: "N",
});

describe("label arrivals (the landing motion on the trace)", () => {
  test("a beat seen pending lands when its label arrives", () => {
    const arrivals = new LabelArrivals();
    arrivals.observe([pending(1)], 0);
    expect(arrivals.progress(1, 0)).toBe(1);
    arrivals.observe([label(1)], 100);
    expect(arrivals.progress(1, 100)).toBe(0);
    expect(arrivals.progress(1, 100 + ARRIVAL_MS / 2)).toBeCloseTo(0.5, 6);
    expect(arrivals.animating(100 + ARRIVAL_MS / 2)).toBe(true);
    expect(arrivals.progress(1, 100 + ARRIVAL_MS)).toBe(1);
    expect(arrivals.animating(100 + ARRIVAL_MS)).toBe(false);
  });

  test("labels already known when first seen do not animate (a seek)", () => {
    const arrivals = new LabelArrivals();
    arrivals.observe([label(4), label(5)], 0);
    expect(arrivals.progress(4, 0)).toBe(1);
    expect(arrivals.animating(0)).toBe(false);
  });

  test("a disagreement lands like a label; a Q dash never animates", () => {
    const arrivals = new LabelArrivals();
    arrivals.observe([pending(1), { row: 2, sample: 720, kind: "q" }], 0);
    arrivals.observe(
      [
        { row: 1, sample: 360, kind: "disagree", label: "V", expert: "N" },
        { row: 2, sample: 720, kind: "q", label: "N" },
      ],
      10,
    );
    expect(arrivals.progress(1, 10)).toBe(0);
    expect(arrivals.progress(2, 10)).toBe(1);
  });

  test("a beat that leaves the view is forgotten", () => {
    const arrivals = new LabelArrivals();
    arrivals.observe([pending(1)], 0);
    arrivals.observe([], 10);
    arrivals.observe([label(1)], 20);
    expect(arrivals.progress(1, 20)).toBe(1);
  });

  test("turned off (reduced motion), every label is settled at once", () => {
    const arrivals = new LabelArrivals();
    arrivals.enabled = false;
    arrivals.observe([pending(1)], 0);
    arrivals.observe([label(1)], 10);
    expect(arrivals.progress(1, 10)).toBe(1);
    expect(arrivals.animating(10)).toBe(false);
  });
});
