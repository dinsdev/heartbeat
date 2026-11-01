import { describe, expect, test } from "vitest";

import { COAST_TIME_CONSTANT_MS, Scroller } from "./scroller";

// A 1280 px wide strip shows 10 seconds: 128 px per second.
const PPS = 128;
const MIN = 10;
const MAX = 1805;

function scroller(position = 100, reducedMotion = false) {
  return new Scroller(position, {
    min: MIN,
    max: MAX,
    pxPerSecond: PPS,
    reducedMotion,
  });
}

/** Drag from x0 by `dx` px over `ms` ms in 8 ms steps, starting at time t0. */
function drag(s: Scroller, x0: number, dx: number, ms: number, t0 = 0) {
  s.down(x0, t0);
  const steps = Math.round(ms / 8);
  for (let k = 1; k <= steps; k++) s.move(x0 + (dx * k) / steps, t0 + 8 * k);
  return t0 + 8 * steps;
}

/** Step the motion until it settles; returns the time it took. */
function settle(s: Scroller, from: number, limit = 10_000) {
  let t = from;
  while (s.active && t - from < limit) {
    t += 16;
    s.step(t);
  }
  return t - from;
}

describe("drag to scrub (settling 7, design call 7)", () => {
  test("the paper tracks the pointer 1:1, and grabbing it does not move it", () => {
    const s = scroller(100);
    s.down(400, 0);
    expect(s.step(0)).toBe(100);
    // Dragging right pulls earlier paper into view: 128 px is one second.
    s.move(528, 16);
    expect(s.step(16)).toBeCloseTo(99, 12);
    s.move(272, 32);
    expect(s.step(32)).toBeCloseTo(101, 12);
    expect(s.dragging).toBe(true);
  });

  test("on release it coasts on with the release velocity, slowing exponentially", () => {
    const s = scroller(100);
    // 614.4 px left in 96 ms: 6,400 px/s, 50 seconds of recording per second.
    const up = drag(s, 800, -614.4, 96);
    const released = s.step(up);
    s.up(up);
    expect(s.dragging).toBe(false);
    expect(s.active).toBe(true);
    const v = 50;
    const tau = COAST_TIME_CONSTANT_MS / 1000;
    for (const after of [100, 400, 1000]) {
      const expected = released + v * tau * (1 - Math.exp(-after / 1000 / tau));
      expect(s.step(up + after)).toBeCloseTo(expected, 3);
    }
    settle(s, up + 1000);
    expect(s.active).toBe(false);
    expect(s.step(up + 20_000)).toBeCloseTo(released + v * tau, 1);
  });

  test("velocity comes from the last 100 ms only: a pause before release means no coast", () => {
    const s = scroller(100);
    let t = drag(s, 800, -640, 100);
    const held = s.step(t);
    // Holding still for 150 ms, then letting go.
    s.move(160, t + 75);
    t += 150;
    s.move(160, t);
    s.up(t);
    expect(s.active).toBe(false);
    expect(s.step(t + 1000)).toBe(held);
  });

  test("past either end the paper follows less and less (rubber band)", () => {
    const s = scroller(MIN);
    s.down(100, 0);
    const overshoots = [128, 640, 1280, 6400].map((dx, k) => {
      s.move(100 + dx, 16 * (k + 1));
      return MIN - s.step(16 * (k + 1));
    });
    // Dragged 1, 5, 10 and 50 seconds past the start.
    overshoots.forEach((o, k) => {
      expect(o).toBeGreaterThan(0);
      expect(o).toBeLessThan([1, 5, 10, 50][k]!);
      if (k > 0) expect(o).toBeGreaterThan(overshoots[k - 1]!);
    });
  });

  test("released past an end it springs back to the end without passing it", () => {
    const s = scroller(MIN);
    s.down(100, 0);
    s.move(740, 16);
    s.move(740, 200);
    s.up(200);
    expect(s.active).toBe(true);
    let t = 200;
    let last = s.step(t);
    while (s.active) {
      t += 16;
      const now = s.step(t);
      expect(now).toBeLessThanOrEqual(MIN + 1e-9);
      expect(now).toBeGreaterThanOrEqual(last - 1e-9);
      last = now;
    }
    expect(t - 200).toBeLessThan(1500);
    expect(s.step(t)).toBe(MIN);
  });

  test("a fling into the end overshoots, then settles exactly on the end", () => {
    const s = scroller(MAX - 2);
    const up = drag(s, 800, -640, 100);
    s.up(up);
    let peak = 0;
    let t = up;
    while (s.active && t < up + 10_000) {
      t += 16;
      peak = Math.max(peak, s.step(t));
    }
    expect(peak).toBeGreaterThan(MAX);
    expect(s.active).toBe(false);
    expect(s.step(t)).toBe(MAX);
  });

  test("any pointer down stops the motion at once, where it is on screen", () => {
    const s = scroller(100);
    const up = drag(s, 800, -640, 100);
    s.up(up);
    const there = s.step(up + 200);
    s.down(500, up + 200);
    expect(s.active).toBe(true); // held, not moving
    expect(s.step(up + 600)).toBe(there);
    s.up(up + 600);
    expect(s.active).toBe(false);
    expect(s.step(up + 2000)).toBe(there);
  });

  test("a seek from outside (the slider, a jump) cancels any motion", () => {
    const s = scroller(100);
    const up = drag(s, 800, -640, 100);
    s.up(up);
    s.jumpTo(400);
    expect(s.active).toBe(false);
    expect(s.step(up + 500)).toBe(400);
  });

  test("a new strip width changes how far a pixel moves the paper", () => {
    const s = scroller(100);
    s.setPxPerSecond(34.3); // a 343 px phone strip
    s.down(100, 0);
    s.move(134.3, 16);
    expect(s.step(16)).toBeCloseTo(99, 12);
  });
});

describe("drag under reduced motion (settling 7)", () => {
  test("the paper does not move during the drag, and nothing coasts", () => {
    const s = scroller(100, true);
    const up = drag(s, 800, -900, 100);
    expect(s.step(up)).toBe(100);
    s.up(up);
    expect(s.active).toBe(false);
  });

  test("a drag moves by whole 10-second pages", () => {
    const one = scroller(100, true);
    one.up(drag(one, 800, -700, 100)); // about half the strip
    expect(one.step(1000)).toBe(110);
    const two = scroller(100, true);
    two.up(drag(two, 100, 2600, 100)); // about two strips back
    expect(two.step(1000)).toBe(80);
  });

  test("a small drag, under a quarter of the strip, does nothing", () => {
    const s = scroller(100, true);
    s.up(drag(s, 800, -40, 100));
    expect(s.step(1000)).toBe(100);
  });

  test("pages stop at both ends", () => {
    const s = scroller(MIN, true);
    s.up(drag(s, 100, 2600, 100));
    expect(s.step(1000)).toBe(MIN);
  });
});
