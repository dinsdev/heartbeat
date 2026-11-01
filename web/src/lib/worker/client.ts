import type { LabelerReply, LabelerRequest, LabelsReply } from "./messages";

export interface ModelUrls {
  model: string;
  scaler: string;
  calibration: string;
}

/**
 * The page's side of the labeler Worker. `ready` settles once the model is
 * loaded; any Worker or model failure rejects it and every pending request,
 * so the page can switch to the labeled fallback (DEMO-05).
 */
export class Labeler {
  readonly ready: Promise<number>;
  #worker: Worker;
  #nextId = 1;
  #pending = new Map<
    number,
    { resolve: (reply: LabelsReply) => void; reject: (error: Error) => void }
  >();
  #failed: Error | undefined;

  constructor(urls: ModelUrls, worker?: Worker) {
    this.#worker =
      worker ??
      new Worker(new URL("./labeler.worker.ts", import.meta.url), {
        type: "module",
        name: "labeler",
      });
    this.ready = new Promise<number>((resolve, reject) => {
      this.#worker.onmessage = (event: MessageEvent<LabelerReply>) => {
        const reply = event.data;
        if (reply.type === "ready") resolve(reply.loadMs);
        else if (reply.type === "labels") {
          this.#pending.get(reply.id)?.resolve(reply);
          this.#pending.delete(reply.id);
        } else if (reply.id !== undefined) {
          this.#pending.get(reply.id)?.reject(new Error(reply.message));
          this.#pending.delete(reply.id);
        } else {
          this.#fail(new Error(reply.message));
          reject(this.#failed!);
        }
      };
      this.#worker.onerror = (event) => {
        event.preventDefault();
        this.#fail(new Error(event.message || "the labeler Worker failed"));
        reject(this.#failed!);
      };
    });
    this.#post({ type: "init", ...urls });
  }

  #fail(error: Error): void {
    this.#failed ??= error;
    for (const { reject } of this.#pending.values()) reject(error);
    this.#pending.clear();
  }

  #post(request: LabelerRequest, transfer: Transferable[] = []): void {
    this.#worker.postMessage(request, transfer);
  }

  /** Send a record's trace and annotated samples (copies; the page keeps its own). */
  sendRecord(record: string, trace: Int16Array, samples: Int32Array): void {
    const traceCopy = trace.slice();
    const samplesCopy = samples.slice();
    this.#post(
      {
        type: "record",
        record,
        trace: traceCopy.buffer,
        samples: samplesCopy.buffer,
      },
      [traceCopy.buffer, samplesCopy.buffer],
    );
  }

  /** Label beats by their index into the record's annotated samples. */
  label(record: string, beats: Int32Array): Promise<LabelsReply> {
    if (this.#failed) return Promise.reject(this.#failed);
    const id = this.#nextId++;
    const promise = new Promise<LabelsReply>((resolve, reject) => {
      this.#pending.set(id, { resolve, reject });
    });
    this.#post({ type: "label", id, record, beats });
    return promise;
  }

  terminate(): void {
    this.#worker.terminate();
    this.#fail(new Error("the labeler was stopped"));
  }
}
