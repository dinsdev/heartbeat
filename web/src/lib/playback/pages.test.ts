import { describe, expect, test } from "vitest";

import { pageEnd, stepPage } from "./pages";

// A 30:05.56 recording, as every MIT-BIH record; the playhead never goes
// below one 10-second span in.
const DURATION = 1805.56;
const MIN = 10;

describe("10-second pages under reduced motion (DEMO-14)", () => {
  test("a page ends on a multiple of 10 seconds at or after the playhead", () => {
    expect(pageEnd(20, MIN, DURATION)).toBe(20);
    expect(pageEnd(20.01, MIN, DURATION)).toBe(30);
    expect(pageEnd(29.99, MIN, DURATION)).toBe(30);
  });

  test("the first page ends at 0:10 and the last at the end of the recording", () => {
    expect(pageEnd(0, MIN, DURATION)).toBe(10);
    expect(pageEnd(1801, MIN, DURATION)).toBe(DURATION);
  });

  test("Next and Previous move by one page, clamped at both ends", () => {
    expect(stepPage(20, 1, MIN, DURATION)).toBe(30);
    expect(stepPage(25, -1, MIN, DURATION)).toBe(20);
    expect(stepPage(10, -1, MIN, DURATION)).toBe(10);
    expect(stepPage(1800, 1, MIN, DURATION)).toBe(DURATION);
    expect(stepPage(DURATION, 1, MIN, DURATION)).toBe(DURATION);
    expect(stepPage(DURATION, -1, MIN, DURATION)).toBe(1800);
  });

  test("whole pages: a step of three moves thirty seconds", () => {
    expect(stepPage(40, 3, MIN, DURATION)).toBe(70);
    expect(stepPage(40, -3, MIN, DURATION)).toBe(10);
  });
});
