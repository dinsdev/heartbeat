import { CLASSES, FS_HZ, type ScoredClass } from "../preprocess/constants";

/** One record's `beats.json`, as `heartbeat build-demo-data` writes it. */
export interface BeatsJson {
  record: string;
  fs_hz: number;
  /** Every annotated beat's sample, the first absolute, then differences. */
  sample_delta: number[];
  /** The expert AAMI class of every annotated beat, one letter each. */
  class: string;
  /** "1" for a kept beat (all but the first and last, DATA-08). */
  kept: string;
  /** The Python seed-0 label of every kept beat. */
  label: string;
  probability_scale: number;
  /** Per class, the Python probability of every kept beat over the scale. */
  probabilities: Record<ScoredClass, number[]>;
}

/** A record's beats, decoded for playback and labeling. */
export interface RecordBeats {
  record: string;
  /** Every annotated beat's sample, Q included (the RR features read them all). */
  samples: Int32Array;
  /** Expert class letters of every annotated beat. */
  classes: string;
  /** For each kept beat, its index into `samples`. */
  keptIndex: Int32Array;
  /** For each kept beat, its sample. */
  keptSamples: Int32Array;
  /** Python seed-0 label of each kept beat. */
  pythonLabels: string;
  /** Python probabilities, four per kept beat in N, S, V, F order. */
  pythonProbabilities: Float64Array;
}

export function decodeBeats(json: BeatsJson): RecordBeats {
  if (json.fs_hz !== FS_HZ) {
    throw new Error(`beats file at ${json.fs_hz} Hz, the model needs ${FS_HZ}`);
  }
  const n = json.sample_delta.length;
  if (json.class.length !== n || json.kept.length !== n) {
    throw new Error(
      `record ${json.record}: ${n} samples, ${json.class.length} classes, ${json.kept.length} kept flags`,
    );
  }
  const samples = new Int32Array(n);
  let sample = 0;
  for (let i = 0; i < n; i++) {
    sample += json.sample_delta[i]!;
    samples[i] = sample;
  }
  const kept: number[] = [];
  for (let i = 0; i < n; i++) if (json.kept[i] === "1") kept.push(i);
  if (json.label.length !== kept.length) {
    throw new Error(
      `record ${json.record}: ${kept.length} kept beats, ${json.label.length} labels`,
    );
  }
  const probabilities = new Float64Array(kept.length * CLASSES.length);
  CLASSES.forEach((cls, k) => {
    const column = json.probabilities[cls];
    if (column.length !== kept.length) {
      throw new Error(`record ${json.record}: ${cls} probabilities`);
    }
    for (let row = 0; row < kept.length; row++) {
      probabilities[row * CLASSES.length + k] =
        column[row]! / json.probability_scale;
    }
  });
  const keptIndex = Int32Array.from(kept);
  return {
    record: json.record,
    samples,
    classes: json.class,
    keptIndex,
    keptSamples: keptIndex.map((i) => samples[i]!),
    pythonLabels: json.label,
    pythonProbabilities: probabilities,
  };
}
