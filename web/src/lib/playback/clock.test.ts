import { describe, expect, test } from "vitest";

import { PlaybackClock, SPEEDS } from "./clock";

function fake() {
  let ms = 1000;
  return { now: () => ms, advance: (by: number) => (ms += by) };
}

describe("the playback clock", () => {
  test("advances in real time at 1x only while playing", () => {
    const time = fake();
    const clock = new PlaybackClock(time.now, 20, 60);
    expect(clock.position()).toBe(20);
    clock.play();
    time.advance(1500);
    expect(clock.position()).toBeCloseTo(21.5, 12);
    clock.pause();
    time.advance(5000);
    expect(clock.position()).toBeCloseTo(21.5, 12);
    expect(clock.playing).toBe(false);
  });

  test("stops at the end of the recording", () => {
    const time = fake();
    const clock = new PlaybackClock(time.now, 55, 60);
    clock.play();
    time.advance(9000);
    expect(clock.position()).toBe(60);
    expect(clock.playing).toBe(false);
  });

  test("seeking keeps playing from the new time, clamped to the recording", () => {
    const time = fake();
    const clock = new PlaybackClock(time.now, 0, 60);
    clock.play();
    time.advance(1000);
    clock.seek(30);
    time.advance(500);
    expect(clock.position()).toBeCloseTo(30.5, 12);
    clock.seek(-5);
    expect(clock.position()).toBe(0);
  });
});

describe("playback speeds (DEMO-10)", () => {
  test("the four speeds are 0.5x, 1x, 2x and 4x", () => {
    expect(SPEEDS).toEqual([0.5, 1, 2, 4]);
  });

  test("4x covers four seconds of recording per second", () => {
    const time = fake();
    const clock = new PlaybackClock(time.now, 10, 600);
    clock.setSpeed(4);
    clock.play();
    time.advance(2500);
    expect(clock.position()).toBeCloseTo(20, 12);
  });

  test("changing speed while playing keeps the position continuous", () => {
    const time = fake();
    const clock = new PlaybackClock(time.now, 10, 600);
    clock.play();
    time.advance(1000);
    clock.setSpeed(0.5);
    expect(clock.position()).toBeCloseTo(11, 12);
    time.advance(1000);
    expect(clock.position()).toBeCloseTo(11.5, 12);
    expect(clock.speed).toBe(0.5);
  });

  test("an unknown speed is refused", () => {
    const clock = new PlaybackClock(fake().now, 10, 600);
    expect(() => clock.setSpeed(3)).toThrow(/speed/);
  });

  test("a lower bound keeps the playhead at least a span in", () => {
    const time = fake();
    const clock = new PlaybackClock(time.now, 2, 60, 10);
    expect(clock.position()).toBe(10);
    clock.seek(4);
    expect(clock.position()).toBe(10);
    expect(clock.min).toBe(10);
  });

  test("a long gap between reads, as in a hidden tab, lands at the right time", () => {
    // PLAN section 7, edge case 5: the clock reads time, not frames.
    const time = fake();
    const clock = new PlaybackClock(time.now, 10, 1800);
    clock.setSpeed(2);
    clock.play();
    time.advance(45_000);
    expect(clock.position()).toBeCloseTo(100, 9);
  });
});
