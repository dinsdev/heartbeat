import { describe, expect, test } from "vitest";

import { decodeBeats } from "./data/beats";
import { LabelingSession } from "./labeling";
import { LABELED, REQUESTED, UNLABELED } from "./worker/chunks";
import type { LabelsReply } from "./worker/messages";

const FS = 360;
// 40 annotated beats one second apart; 38 kept, all N in Python at 0.97.
const n = 40;
const beats = decodeBeats({
  class: "N".repeat(n),
  fs_hz: FS,
  kept: "0" + "1".repeat(n - 2) + "0",
  label: "N".repeat(n - 2),
  probabilities: {
    N: new Array<number>(n - 2).fill(970000),
    S: new Array<number>(n - 2).fill(10000),
    V: new Array<number>(n - 2).fill(10000),
    F: new Array<number>(n - 2).fill(10000),
  },
  probability_scale: 1000000,
  record: "223",
  sample_delta: [FS, ...new Array<number>(n - 1).fill(FS)],
});

class FakeLabeler {
  calls: { record: string; beats: number[] }[] = [];
  #replies: {
    resolve: (r: LabelsReply) => void;
    reject: (e: Error) => void;
  }[] = [];

  label(record: string, indices: Int32Array): Promise<LabelsReply> {
    this.calls.push({ record, beats: Array.from(indices) });
    return new Promise((resolve, reject) =>
      this.#replies.push({ resolve, reject }),
    );
  }

  answer(k: number, probabilityN = 0.97): void {
    const call = this.calls[k]!;
    const m = call.beats.length;
    const probabilities = new Float64Array(m * 4);
    for (let i = 0; i < m; i++) {
      probabilities.set(
        [probabilityN, 0.01, 0.01, 1 - probabilityN - 0.02],
        i * 4,
      );
    }
    this.#replies[k]!.resolve({
      type: "labels",
      id: k,
      record: call.record,
      beats: Int32Array.from(call.beats),
      labels: new Uint8Array(m),
      probabilities,
      logits: new Float32Array(m * 4),
      inferenceMs: 1,
    });
  }

  failCall(k: number): void {
    this.#replies[k]!.reject(new Error("model failed"));
  }
}

describe("the labeling session", () => {
  test("asks for the annotated indices of the beats around the playhead", () => {
    const labeler = new FakeLabeler();
    const session = new LabelingSession(beats, labeler, () => undefined);
    session.fill(20 * FS, FS);
    // Kept beat r is annotated beat r + 1 at (r + 2) s; span [10 s, 30 s).
    expect(labeler.calls).toEqual([
      { record: "223", beats: Array.from({ length: 20 }, (_, i) => i + 9) },
    ]);
    expect(session.state[8]).toBe(REQUESTED);
    // Asking again before the reply sends nothing new.
    session.fill(20 * FS, FS);
    expect(labeler.calls).toHaveLength(1);
  });

  test("writes the replies to the store, where the counter reads them", async () => {
    const labeler = new FakeLabeler();
    let changes = 0;
    const session = new LabelingSession(beats, labeler, () => changes++);
    session.fill(20 * FS, FS);
    labeler.answer(0);
    await Promise.resolve();
    expect(changes).toBe(1);
    expect(session.state[8]).toBe(LABELED);
    expect(session.store.counts()).toEqual({
      compared: 20,
      matched: 20,
      total: 38,
    });
  });

  test("a mismatch from the Worker is counted, not hidden", async () => {
    const labeler = new FakeLabeler();
    const session = new LabelingSession(beats, labeler, () => undefined);
    session.fill(20 * FS, FS);
    labeler.answer(0, 0.9);
    await Promise.resolve();
    expect(session.store.counts()).toEqual({
      compared: 20,
      matched: 0,
      total: 38,
    });
  });

  test("a failed request switches to the labeled fallback", async () => {
    const labeler = new FakeLabeler();
    const session = new LabelingSession(beats, labeler, () => undefined);
    session.fill(20 * FS, FS);
    labeler.failCall(0);
    await Promise.resolve();
    await Promise.resolve();
    expect(session.store.fallback).toBe(true);
    expect(session.state[8]).toBe(UNLABELED);
    expect(session.store.get(0)).toMatchObject({
      label: "N",
      source: "python",
    });
    session.fill(30 * FS, FS);
    expect(labeler.calls).toHaveLength(1);
  });
});
