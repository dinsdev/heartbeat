/** One file the manifest lists: hashed name, size and SHA256 (DEMO-08). */
export interface FileEntry {
  name: string;
  bytes: number;
  sha256: string;
}

export interface RecordEntry {
  record: string;
  /** Expert class counts of the kept beats. */
  counts: Record<"N" | "S" | "V" | "F" | "Q", number>;
  duration_s: number;
  trace: FileEntry;
  beats: FileEntry;
}

/** `manifest.json`, written by `heartbeat build-demo-data`. */
export interface Manifest {
  /** "DS1" until the sealed run is logged (DEMO-17); drives the training-patient note. */
  split: "DS1" | "DS2";
  fs_hz: number;
  adu_per_mv: number;
  probability_scale: number;
  classes: string[];
  default: { record: string; start_s: number };
  attribution: string;
  attribution_file: FileEntry;
  model: {
    version: string;
    seed: number;
    sha256: string;
    model: FileEntry;
    scaler: FileEntry;
    calibration: FileEntry;
    notice: FileEntry;
  };
  records: RecordEntry[];
}
