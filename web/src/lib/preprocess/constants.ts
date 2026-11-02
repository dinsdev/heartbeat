// The Python pipeline's fixed values (src/heartbeat/constants.py), which the
// browser must use unchanged for parity (PARITY-03).

// B3, D4: 360 Hz; the trace is int16 at 200 units per mV.
export const FS_HZ = 360;
export const ADU_PER_MV = 200;

// B3: a 256-sample window, 96 before the annotation and 160 after.
export const WINDOW_BEFORE = 96;
export const WINDOW_AFTER = 160;
export const WINDOW_SAMPLES = WINDOW_BEFORE + WINDOW_AFTER;

// B3 amendment, DATA-06: z = (x - mean) / max(std, 2), in int16 units.
export const ZSCORE_STD_FLOOR_ADU = 2;

// DATA-07: the local average spans the last 10 intervals, the long average
// every interval ending at most 5 minutes (108,000 samples) before the beat.
export const RR_LOCAL_INTERVALS = 10;
export const RR_LONG_WINDOW_SAMPLES = 5 * 60 * FS_HZ;
export const RR_FEATURES = 6;

// B4, DATA-10: the scored classes, in the model's output order.
export const CLASSES = ["N", "S", "V", "F"] as const;
export type ScoredClass = (typeof CLASSES)[number];
