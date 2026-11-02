// Messages between the page and the labeler Worker (design call 8).

export interface InitRequest {
  type: "init";
  /** Same-origin URLs of the shipped model files (hashed names). */
  model: string;
  scaler: string;
  calibration: string;
}

export interface RecordRequest {
  type: "record";
  record: string;
  /** The int16 trace, little-endian, 360 Hz. */
  trace: ArrayBuffer;
  /** Every annotated beat's sample as int32. */
  samples: ArrayBuffer;
}

export interface LabelRequest {
  type: "label";
  id: number;
  record: string;
  /** Indices into the record's annotated samples of the beats to label. */
  beats: Int32Array;
}

export type LabelerRequest = InitRequest | RecordRequest | LabelRequest;

export interface ReadyReply {
  type: "ready";
  /** Milliseconds from `init` to a ready session. */
  loadMs: number;
}

export interface ErrorReply {
  type: "error";
  message: string;
  /** The label request that failed, if one did. */
  id?: number;
}

export interface LabelsReply {
  type: "labels";
  id: number;
  record: string;
  beats: Int32Array;
  /** Class index (0 N, 1 S, 2 V, 3 F) per beat. */
  labels: Uint8Array;
  /** Calibrated probabilities, four per beat. */
  probabilities: Float64Array;
  /** Raw logits, four per beat, as the model returned them. */
  logits: Float32Array;
  /** Milliseconds in the model call for this batch, and its beats. */
  inferenceMs: number;
}

export type LabelerReply = ReadyReply | ErrorReply | LabelsReply;
