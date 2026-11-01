import { describe, expect, test } from "vitest";

import { PlaybackClock } from "./clock";

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
