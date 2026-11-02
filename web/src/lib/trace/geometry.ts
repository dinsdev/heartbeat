import { ADU_PER_MV } from "../preprocess/constants";

// Settling 2, design call 5: ECG paper at the standard 25 mm/s and 10 mm/mV,
// ten seconds across the width at every size.
export const SPAN_S = 10;
export const MM_PER_S = 25;
export const MM_PER_MV = 10;
// The strip is 5 mV tall at nominal scale, the baseline 60% down, so a tall R
// wave and a deep V beat both fit, with room above for the beat letters.
export const PAPER_HEIGHT_MM = 50;
const BASELINE_FRACTION = 0.6;

export interface Geometry {
  widthPx: number;
  heightPx: number;
  /** CSS pixels per nominal millimetre. */
  pxPerMm: number;
  /** Where 0 mV sits, from the top. */
  baselinePx: number;
}

export function paperGeometry(widthPx: number, minHeightPx: number): Geometry {
  const pxPerMm = widthPx / (SPAN_S * MM_PER_S);
  const heightPx = Math.max(minHeightPx, PAPER_HEIGHT_MM * pxPerMm);
  return {
    widthPx,
    heightPx,
    pxPerMm,
    baselinePx: heightPx * BASELINE_FRACTION,
  };
}

/** X of a sample in a view starting at `startSample` (the playhead is the right edge). */
export function xForSample(
  sample: number,
  startSample: number,
  fs: number,
  geo: Geometry,
): number {
  return ((sample - startSample) / fs) * MM_PER_S * geo.pxPerMm;
}

/** Y of a trace value in int16 units (200 per mV). */
export function yForAdu(adu: number, geo: Geometry): number {
  return geo.baselinePx - (adu / ADU_PER_MV) * MM_PER_MV * geo.pxPerMm;
}

/**
 * The min and max of the samples falling in each of `columns` equal columns
 * of `[startSample, endSample)`, as `[min0, max0, min1, max1, ...]`. Columns
 * with no sample inside the trace are NaN.
 */
export function columnExtents(
  trace: Int16Array,
  startSample: number,
  endSample: number,
  columns: number,
  out = new Float32Array(columns * 2),
): Float32Array {
  const perColumn = (endSample - startSample) / columns;
  for (let c = 0; c < columns; c++) {
    const from = Math.max(0, Math.floor(startSample + c * perColumn));
    const to = Math.min(
      trace.length,
      Math.floor(startSample + (c + 1) * perColumn),
    );
    let min = Infinity;
    let max = -Infinity;
    for (let i = from; i < to; i++) {
      const v = trace[i]!;
      if (v < min) min = v;
      if (v > max) max = v;
    }
    out[2 * c] = to > from ? min : Number.NaN;
    out[2 * c + 1] = to > from ? max : Number.NaN;
  }
  return out;
}
