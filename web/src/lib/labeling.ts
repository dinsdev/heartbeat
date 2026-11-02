import type { RecordBeats } from "./data/beats";
import { LabelStore } from "./parity";
import { CLASSES } from "./preprocess/constants";
import {
  beatsToLabel,
  LABELED,
  labelSpan,
  REQUESTED,
  UNLABELED,
} from "./worker/chunks";
import type { LabelsReply } from "./worker/messages";

/** The part of the Worker client a session uses. */
export interface BeatLabeler {
  label(record: string, beats: Int32Array): Promise<LabelsReply>;
}

/**
 * Labels one record's beats around the playhead with the Worker and writes
 * them to the record's label store. A Worker failure switches the store to
 * the labeled fallback (DEMO-05).
 */
export class LabelingSession {
  readonly store: LabelStore;
  readonly state: Uint8Array;
  /** Inference milliseconds and beats per Worker batch, for the timing report. */
  readonly timings: { ms: number; beats: number }[] = [];
  #beats: RecordBeats;
  #labeler: BeatLabeler;
  #onChange: () => void;

  constructor(beats: RecordBeats, labeler: BeatLabeler, onChange: () => void) {
    this.#beats = beats;
    this.#labeler = labeler;
    this.#onChange = onChange;
    this.store = new LabelStore(beats);
    this.state = new Uint8Array(beats.keptIndex.length);
  }

  fail(): void {
    if (this.store.fallback) return;
    this.store.useFallback();
    this.#onChange();
  }

  /** Ask for the unlabeled beats in the visible span and the next 10 seconds. */
  fill(playheadSample: number, fsHz: number): void {
    if (this.store.fallback) return;
    const [from, to] = labelSpan(playheadSample, fsHz);
    const rows = beatsToLabel(this.#beats.keptSamples, this.state, from, to);
    if (rows.length === 0) return;
    for (const row of rows) this.state[row] = REQUESTED;
    const indices = Int32Array.from(rows, (row) => this.#beats.keptIndex[row]!);
    this.#labeler.label(this.#beats.record, indices).then(
      (reply) => {
        this.timings.push({ ms: reply.inferenceMs, beats: rows.length });
        rows.forEach((row, k) => {
          this.store.setBrowser(
            row,
            CLASSES[reply.labels[k]!]!,
            reply.probabilities.slice(
              k * CLASSES.length,
              (k + 1) * CLASSES.length,
            ),
          );
          this.state[row] = LABELED;
        });
        this.#onChange();
      },
      () => {
        for (const row of rows) this.state[row] = UNLABELED;
        this.fail();
      },
    );
  }
}
