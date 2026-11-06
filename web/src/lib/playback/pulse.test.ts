import { describe, expect, test } from "vitest";

import { beatBetween } from "./pulse";

const samples = Int32Array.of(100, 460, 820, 1180);

describe("the beat pulse", () => {
  test("a beat in (from, to] counts; the open end does not", () => {
    expect(beatBetween(samples, 99, 100)).toBe(true);
    expect(beatBetween(samples, 100, 459)).toBe(false);
    expect(beatBetween(samples, 459, 461)).toBe(true);
  });

  test("an empty or backward span holds no beat", () => {
    expect(beatBetween(samples, 820, 820)).toBe(false);
    expect(beatBetween(samples, 900, 100)).toBe(false);
    expect(beatBetween(samples, 1180, 5000)).toBe(false);
    expect(beatBetween(new Int32Array(0), 0, 10)).toBe(false);
  });
});
