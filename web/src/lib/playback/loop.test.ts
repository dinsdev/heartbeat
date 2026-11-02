import { describe, expect, test } from "vitest";

import { FrameLoop } from "./loop";

/** A fake requestAnimationFrame and visibility. */
function host() {
  const queue = new Map<number, () => void>();
  let id = 0;
  const state = { hidden: false };
  return {
    state,
    pending: () => queue.size,
    flush() {
      const callbacks = [...queue.values()];
      queue.clear();
      for (const cb of callbacks) cb();
    },
    deps: {
      request: (cb: () => void) => {
        queue.set(++id, cb);
        return id;
      },
      cancel: (n: number) => void queue.delete(n),
      hidden: () => state.hidden,
    },
  };
}

describe("the frame loop (design call 6, PLAN section 7 edge case 5)", () => {
  test("runs one frame per wake while nothing moves", () => {
    const h = host();
    let frames = 0;
    const loop = new FrameLoop(h.deps, () => {
      frames++;
      return false;
    });
    loop.wake();
    loop.wake();
    expect(h.pending()).toBe(1);
    h.flush();
    expect(frames).toBe(1);
    expect(h.pending()).toBe(0);
  });

  test("keeps going while the frame says so (playing or coasting)", () => {
    const h = host();
    let frames = 0;
    const loop = new FrameLoop(h.deps, () => ++frames < 3);
    loop.wake();
    h.flush();
    h.flush();
    h.flush();
    expect(frames).toBe(3);
    expect(h.pending()).toBe(0);
  });

  test("stops while the page is hidden and resumes when it is shown", () => {
    const h = host();
    let frames = 0;
    const loop = new FrameLoop(h.deps, () => {
      frames++;
      return true;
    });
    loop.wake();
    h.flush();
    h.state.hidden = true;
    h.flush(); // the frame already asked for runs, but asks for no more
    expect(h.pending()).toBe(0);
    loop.wake();
    expect(h.pending()).toBe(0);
    h.state.hidden = false;
    loop.visibilityChanged();
    expect(h.pending()).toBe(1);
    h.flush();
    expect(frames).toBe(3);
  });

  test("stop cancels the pending frame", () => {
    const h = host();
    const loop = new FrameLoop(h.deps, () => true);
    loop.wake();
    loop.stop();
    expect(h.pending()).toBe(0);
    loop.wake();
    expect(h.pending()).toBe(0);
  });
});
