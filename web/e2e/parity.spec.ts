import { expect, test } from "@playwright/test";

import fixturesJson from "../../fixtures/parity/fixtures.json" with { type: "json" };

// PARITY-03: within 1e-5, labels exact.
const TOLERANCE = 1e-5;
const CLASSES = ["N", "S", "V", "F"];

interface FixtureBeat {
  rr_beat_samples: number[];
  rr_beat_index: number;
  window_adu: number[];
  seeds: Record<
    string,
    { logits: number[]; probabilities: number[]; label: string }
  >;
}

const beats = (fixturesJson as unknown as { beats: FixtureBeat[] }).beats;

test("R29: the browser Worker matches Python ONNX Runtime on the 50 DS1 fixture beats", async ({
  page,
}) => {
  // The page starts the shipped labeler Worker; take its URL from it.
  const started = page.waitForEvent("worker");
  await page.goto("/");
  const workerUrl = (await started).url();
  expect(workerUrl).toContain("labeler");

  const results = await page.evaluate(
    async ({ workerUrl, beats }) => {
      const manifest = (await (await fetch("data/manifest.json")).json()) as {
        model: Record<"model" | "scaler" | "calibration", { name: string }>;
      };
      const url = (name: string) =>
        new URL(`data/${name}`, document.baseURI).href;
      const worker = new Worker(workerUrl, { type: "module" });
      const replies: unknown[] = [];
      const wanted = beats.length;
      const done = new Promise<void>((resolve, reject) => {
        worker.onmessage = (
          event: MessageEvent<{ type: string; message?: string }>,
        ) => {
          if (event.data.type === "error")
            reject(new Error(event.data.message));
          if (event.data.type === "labels") {
            replies.push(event.data);
            if (replies.length === wanted) resolve();
          }
        };
      });
      worker.postMessage({
        type: "init",
        model: url(manifest.model.model.name),
        scaler: url(manifest.model.scaler.name),
        calibration: url(manifest.model.calibration.name),
      });
      beats.forEach((beat, k) => {
        // A record holding the fixture's annotated beats, shifted so the first
        // sits at 200, and the Python window at the fixture beat. RR features
        // read only differences, and the window only the trace around the beat.
        const shift = 200 - beat.rr_beat_samples[0]!;
        const samples = Int32Array.from(beat.rr_beat_samples, (s) => s + shift);
        const at = samples[beat.rr_beat_index]!;
        const trace = new Int16Array(at + 160 + 1);
        trace.set(beat.window_adu, at - 96);
        worker.postMessage({
          type: "record",
          record: `fixture-${k}`,
          trace: trace.buffer,
          samples: samples.buffer,
        });
        worker.postMessage({
          type: "label",
          id: k,
          record: `fixture-${k}`,
          beats: Int32Array.of(beat.rr_beat_index),
        });
      });
      await done;
      worker.terminate();
      return (
        replies as {
          id: number;
          labels: Uint8Array;
          probabilities: Float64Array;
          logits: Float32Array;
        }[]
      ).map((r) => ({
        id: r.id,
        label: r.labels[0]!,
        probabilities: Array.from(r.probabilities),
        logits: Array.from(r.logits),
      }));
    },
    { workerUrl, beats },
  );

  expect(results).toHaveLength(beats.length);
  let largest = 0;
  for (const result of results) {
    const expected = beats[result.id]!.seeds["0"]!;
    expect(CLASSES[result.label]).toBe(expected.label);
    for (let k = 0; k < 4; k++) {
      largest = Math.max(
        largest,
        Math.abs(result.logits[k]! - expected.logits[k]!),
        Math.abs(result.probabilities[k]! - expected.probabilities[k]!),
      );
    }
  }
  test.info().annotations.push({
    type: "largest difference",
    description: largest.toExponential(3),
  });
  console.log(
    `R29 ${test.info().project.name}: largest difference ${largest.toExponential(3)}`,
  );
  expect(largest).toBeLessThanOrEqual(TOLERANCE);
});
