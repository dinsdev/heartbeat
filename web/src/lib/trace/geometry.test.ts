import { describe, expect, test } from "vitest";

import {
  columnExtents,
  MM_PER_MV,
  MM_PER_S,
  paperGeometry,
  PAPER_HEIGHT_MM,
  SPAN_S,
  xForSample,
  yForAdu,
} from "./geometry";

describe("the paper: 25 mm/s and 10 mm/mV at any width (design call 5)", () => {
  test("ten seconds fill the width, so one millimetre is width / 250", () => {
    expect(SPAN_S).toBe(10);
    expect(MM_PER_S).toBe(25);
    expect(MM_PER_MV).toBe(10);
    const geo = paperGeometry(1000, 0);
    expect(geo.pxPerMm).toBe(4);
    expect(geo.heightPx).toBe(PAPER_HEIGHT_MM * 4);
  });

  test("a narrow phone keeps the proportions and gets a minimum height", () => {
    const geo = paperGeometry(343, 200);
    expect(geo.pxPerMm).toBeCloseTo(343 / 250, 12);
    expect(geo.heightPx).toBe(Math.max(200, PAPER_HEIGHT_MM * geo.pxPerMm));
    expect(geo.heightPx).toBe(200);
  });

  test("time maps left to right, the playhead at the right edge", () => {
    const geo = paperGeometry(1000, 0);
    const fs = 360;
    const start = 20 * fs;
    expect(xForSample(start, start, fs, geo)).toBe(0);
    expect(xForSample(start + 10 * fs, start, fs, geo)).toBe(1000);
    expect(xForSample(start + fs, start, fs, geo)).toBe(100);
  });

  test("1 mV is 10 mm up from the baseline; 200 units are 1 mV", () => {
    const geo = paperGeometry(1000, 0);
    expect(yForAdu(0, geo)).toBe(geo.baselinePx);
    expect(yForAdu(200, geo)).toBeCloseTo(geo.baselinePx - 40, 12);
    expect(yForAdu(-100, geo)).toBeCloseTo(geo.baselinePx + 20, 12);
  });
});

describe("the trace drawn from a min and max per pixel column (design call 6)", () => {
  test("each column holds the extremes of its samples", () => {
    const trace = Int16Array.from([0, 5, -3, 2, 9, 1, -8, 4]);
    expect(Array.from(columnExtents(trace, 0, 8, 2))).toEqual([-3, 5, -8, 9]);
  });

  test("columns before the start or past the end are left empty (NaN)", () => {
    const trace = Int16Array.from([1, 2, 3, 4]);
    const out = columnExtents(trace, -4, 4, 2);
    expect(Number.isNaN(out[0])).toBe(true);
    expect(Array.from(out.subarray(2))).toEqual([1, 4]);
  });
});
