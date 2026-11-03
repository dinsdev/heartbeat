import { expect, test } from "@playwright/test";

import { demoManifest } from "./manifest";

// Phase 6 design call 9: label every kept beat of every shipped record (DS1,
// or DS2 once the sealed run is logged; Phase 7 design call 7) in the browser
// and compare with the stored Python labels and probabilities.
// Any mismatch is a stop for Din. The stored probabilities are millionths, so
// the largest difference includes up to 5e-7 of rounding.
const TOLERANCE = 1e-5;
const BATCH = 1024;

interface RecordResult {
  record: string;
  beats: number;
  labelMismatches: number;
  overTolerance: number;
  largest: number;
  inferenceMs: number;
}

test("every kept beat of every shipped record matches the Python labels", async ({
  page,
  request,
}) => {
  test.setTimeout(240_000);
  const manifest = await demoManifest(request);
  const started = page.waitForEvent("worker");
  await page.goto("/");
  const workerUrl = (await started).url();

  const results = await page.evaluate(
    async ({ workerUrl, BATCH }) => {
      interface Entry {
        name: string;
      }
      const manifest = (await (await fetch("data/manifest.json")).json()) as {
        split: string;
        model: Record<"model" | "scaler" | "calibration", Entry>;
        records: { record: string; trace: Entry; beats: Entry }[];
      };
      const url = (name: string) =>
        new URL(`data/${name}`, document.baseURI).href;
      const worker = new Worker(workerUrl, { type: "module" });
      let nextId = 0;
      const waiting = new Map<
        number,
        (reply: Record<string, unknown>) => void
      >();
      const ready = new Promise<void>((resolve, reject) => {
        worker.onmessage = (event: MessageEvent<Record<string, unknown>>) => {
          const reply = event.data;
          if (reply.type === "ready") resolve();
          else if (reply.type === "error")
            reject(new Error(String(reply.message)));
          else waiting.get(reply.id as number)?.(reply);
        };
      });
      worker.postMessage({
        type: "init",
        model: url(manifest.model.model.name),
        scaler: url(manifest.model.scaler.name),
        calibration: url(manifest.model.calibration.name),
      });
      await ready;
      const classes = ["N", "S", "V", "F"];
      const out = [];
      for (const entry of manifest.records) {
        const trace = await (await fetch(url(entry.trace.name))).arrayBuffer();
        const beats = (await (await fetch(url(entry.beats.name))).json()) as {
          sample_delta: number[];
          kept: string;
          label: string;
          probability_scale: number;
          probabilities: Record<string, number[]>;
        };
        const samples = new Int32Array(beats.sample_delta.length);
        let s = 0;
        beats.sample_delta.forEach((d, i) => (samples[i] = s += d));
        const kept: number[] = [];
        for (let i = 0; i < beats.kept.length; i++)
          if (beats.kept[i] === "1") kept.push(i);
        worker.postMessage({
          type: "record",
          record: entry.record,
          trace,
          samples: samples.buffer.slice(0),
        });
        let labelMismatches = 0;
        let overTolerance = 0;
        let largest = 0;
        let inferenceMs = 0;
        for (let start = 0; start < kept.length; start += BATCH) {
          const rows = kept.slice(start, start + BATCH);
          const id = nextId++;
          const reply = await new Promise<Record<string, unknown>>(
            (resolve) => {
              waiting.set(id, resolve);
              worker.postMessage({
                type: "label",
                id,
                record: entry.record,
                beats: Int32Array.from(rows),
              });
            },
          );
          inferenceMs += reply.inferenceMs as number;
          const labels = reply.labels as Uint8Array;
          const probabilities = reply.probabilities as Float64Array;
          rows.forEach((_, k) => {
            const row = start + k;
            if (classes[labels[k]!] !== beats.label[row]) labelMismatches++;
            let worst = 0;
            classes.forEach((cls, c) => {
              const python =
                beats.probabilities[cls]![row]! / beats.probability_scale;
              worst = Math.max(
                worst,
                Math.abs(probabilities[k * 4 + c]! - python),
              );
            });
            if (!(worst <= 1e-5)) overTolerance++;
            largest = Math.max(largest, worst);
          });
        }
        out.push({
          record: entry.record,
          beats: kept.length,
          labelMismatches,
          overTolerance,
          largest,
          inferenceMs,
        });
      }
      worker.terminate();
      return { split: manifest.split, records: out };
    },
    { workerUrl, BATCH },
  );

  expect(results.split).toBe(manifest.split);
  const records: RecordResult[] = results.records;
  expect(records.map((r) => r.record)).toEqual(
    manifest.records.map((r) => r.record),
  );
  const total = records.reduce((n, r) => n + r.beats, 0);
  const largest = Math.max(...records.map((r) => r.largest));
  const ms = records.reduce((n, r) => n + r.inferenceMs, 0);
  const summary =
    `survey ${test.info().project.name}: ${total} beats in ` +
    `${records.length} ${manifest.split} records, ` +
    `label mismatches ${records.reduce((n, r) => n + r.labelMismatches, 0)}, ` +
    `over 1e-5 ${records.reduce((n, r) => n + r.overTolerance, 0)}, ` +
    `largest probability difference ${largest.toExponential(3)}, ` +
    `model time ${(ms / total).toFixed(4)} ms per beat in batches of ${BATCH}`;
  console.log(summary);
  for (const r of records) {
    console.log(
      `  ${r.record}: ${r.beats} beats, largest ${r.largest.toExponential(3)}, label mismatches ${r.labelMismatches}`,
    );
  }
  test.info().annotations.push({ type: "survey", description: summary });
  for (const r of records) {
    expect(r.labelMismatches, `record ${r.record}`).toBe(0);
    expect(r.overTolerance, `record ${r.record}`).toBe(0);
  }
  expect(largest).toBeLessThanOrEqual(TOLERANCE);
});
