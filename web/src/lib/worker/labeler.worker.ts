// The labeler Worker (D3, DEMO-02): ONNX Runtime Web on WebAssembly, one
// thread, running the shipped seed-0 model on windows and RR features the
// browser computes from the shipped trace and beat positions.

import * as ort from "onnxruntime-web/wasm";
import wasmUrl from "onnxruntime-web/ort-wasm-simd-threaded.wasm?url";

import {
  adjustLogits,
  calibratedProbabilities,
  type Calibration,
} from "../preprocess/calibration";
import { CLASSES, RR_FEATURES, WINDOW_SAMPLES } from "../preprocess/constants";
import { rrFeatures, rrModelInputs } from "../preprocess/rr";
import { applyScaler, type Scaler } from "../preprocess/scaler";
import { extractWindow, zscoreWindow } from "../preprocess/window";
import type { LabelerReply, LabelerRequest, LabelRequest } from "./messages";

// No SharedArrayBuffer, so no COOP and COEP headers (D3); served from this origin.
ort.env.wasm.numThreads = 1;
ort.env.wasm.proxy = false;
ort.env.wasm.wasmPaths = { wasm: wasmUrl };

interface WorkerScope {
  onmessage: ((event: MessageEvent<LabelerRequest>) => void) | null;
  postMessage(message: LabelerReply, transfer?: Transferable[]): void;
}
const scope = self as unknown as WorkerScope;

interface Model {
  session: ort.InferenceSession;
  scaler: Scaler;
  calibration: Calibration;
}

let model: Promise<Model> | undefined;
const records = new Map<string, { trace: Int16Array; samples: Int32Array }>();

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`);
  return (await response.json()) as T;
}

async function load(
  model: string,
  scaler: string,
  calibration: string,
): Promise<Model> {
  const response = await fetch(model);
  if (!response.ok) throw new Error(`${model}: HTTP ${response.status}`);
  const bytes = new Uint8Array(await response.arrayBuffer());
  const [session, scalerJson, calibrationJson] = await Promise.all([
    ort.InferenceSession.create(bytes, {
      executionProviders: ["wasm"],
      graphOptimizationLevel: "all",
    }),
    fetchJson<Scaler>(scaler),
    fetchJson<Calibration>(calibration),
  ]);
  return { session, scaler: scalerJson, calibration: calibrationJson };
}

async function label(request: LabelRequest, loaded: Model): Promise<void> {
  const record = records.get(request.record);
  if (!record) throw new Error(`record ${request.record} was not sent`);
  const n = request.beats.length;
  const windows = new Float32Array(n * WINDOW_SAMPLES);
  const rr = new Float32Array(n * RR_FEATURES);
  request.beats.forEach((beat, row) => {
    const sample = record.samples[beat]!;
    windows.set(
      zscoreWindow(extractWindow(record.trace, sample)),
      row * WINDOW_SAMPLES,
    );
    rr.set(
      applyScaler(
        rrModelInputs(rrFeatures(record.samples, beat)),
        loaded.scaler,
      ),
      row * RR_FEATURES,
    );
  });
  const started = performance.now();
  const output = await loaded.session.run({
    window: new ort.Tensor("float32", windows, [n, 1, WINDOW_SAMPLES]),
    rr: new ort.Tensor("float32", rr, [n, RR_FEATURES]),
  });
  const inferenceMs = performance.now() - started;
  const logits = Float32Array.from(output.logits!.data as Float32Array);
  const labels = new Uint8Array(n);
  const probabilities = new Float64Array(n * CLASSES.length);
  for (let row = 0; row < n; row++) {
    const raw = logits.subarray(
      row * CLASSES.length,
      (row + 1) * CLASSES.length,
    );
    let best = 0;
    for (let k = 1; k < CLASSES.length; k++) if (raw[k]! > raw[best]!) best = k;
    labels[row] = best;
    probabilities.set(
      calibratedProbabilities(
        adjustLogits(raw, loaded.calibration.log_class_weights),
        loaded.calibration.temperature,
      ),
      row * CLASSES.length,
    );
  }
  const beats = Int32Array.from(request.beats);
  scope.postMessage(
    {
      type: "labels",
      id: request.id,
      record: request.record,
      beats,
      labels,
      probabilities,
      logits,
      inferenceMs,
    },
    [beats.buffer, labels.buffer, probabilities.buffer, logits.buffer],
  );
}

function fail(error: unknown, id?: number): void {
  const message = error instanceof Error ? error.message : String(error);
  scope.postMessage(
    id === undefined
      ? { type: "error", message }
      : { type: "error", message, id },
  );
}

scope.onmessage = (event) => {
  const request = event.data;
  switch (request.type) {
    case "init": {
      const started = performance.now();
      model = load(request.model, request.scaler, request.calibration);
      model.then(
        () => {
          scope.postMessage({
            type: "ready",
            loadMs: performance.now() - started,
          });
        },
        (error: unknown) => {
          fail(error);
        },
      );
      break;
    }
    case "record":
      records.set(request.record, {
        trace: new Int16Array(request.trace),
        samples: new Int32Array(request.samples),
      });
      break;
    case "label":
      if (!model) {
        fail(new Error("label before init"), request.id);
        break;
      }
      model
        .then((loaded) => label(request, loaded))
        .catch((error: unknown) => {
          fail(error, request.id);
        });
      break;
  }
};
