// The trace on ECG paper (settling 2; design calls 5 and 6): Canvas 2D at the
// device pixel ratio, the grid rendered once per size and theme, the trace
// from a min and max per device pixel column, the beat markers on top, and
// the pen tip at the playhead.

import {
  columnExtents,
  type Geometry,
  MM_PER_S,
  paperGeometry,
  SPAN_S,
  xForSample,
  yForAdu,
} from "./geometry";
import type { Marker } from "./markers";

export interface TraceColors {
  trace: string;
  gridMinor: string;
  gridMajor: string;
  muted: string;
  accent: string;
  classes: Record<"N" | "S" | "V" | "F" | "Q", string>;
  font: string;
}

/** Read the colors from the custom properties on `element` (they follow the theme). */
export function readColors(element: Element): TraceColors {
  const style = getComputedStyle(element);
  const get = (name: string) => style.getPropertyValue(name).trim();
  return {
    trace: get("--hb-trace"),
    gridMinor: get("--hb-grid-minor"),
    gridMajor: get("--hb-grid-major"),
    muted: get("--color-muted"),
    accent: get("--color-accent"),
    classes: {
      N: get("--hb-class-n"),
      S: get("--hb-class-s"),
      V: get("--hb-class-v"),
      F: get("--hb-class-f"),
      Q: get("--hb-class-q"),
    },
    font: get("--font-mono"),
  };
}

export interface Frame {
  trace: Int16Array;
  fs: number;
  /** The sample at the left edge; the right edge is ten seconds later. */
  startSample: number;
  markers: readonly Marker[];
  /** Where the pen tip sits; left out, no pen tip. */
  cursorSample?: number;
  /** How far each beat's label has landed, 0 to 1 (1 when left out). */
  landed?: (row: number) => number;
}

/** A strong ease-out: the letter arrives fast and settles. */
function easeOut(t: number): number {
  return 1 - Math.pow(1 - t, 3);
}

export class TraceRenderer {
  readonly canvas: HTMLCanvasElement;
  #context: CanvasRenderingContext2D;
  #grid: HTMLCanvasElement | undefined;
  #geometry: Geometry | undefined;
  #colors: TraceColors | undefined;
  #dpr = 1;
  #extents = new Float32Array(0);
  #minHeightPx: number;

  constructor(canvas: HTMLCanvasElement, minHeightPx: number) {
    this.canvas = canvas;
    this.#minHeightPx = minHeightPx;
    const context = canvas.getContext("2d", { alpha: false });
    if (!context) throw new Error("no 2D canvas");
    this.#context = context;
  }

  /** The same renderer with another minimum height (the embed fills its box). */
  withMinHeight(minHeightPx: number): this {
    this.#minHeightPx = minHeightPx;
    return this;
  }

  get geometry(): Geometry | undefined {
    return this.#geometry;
  }

  /** Size the canvas to a CSS width and redraw the grid. Returns the CSS height. */
  resize(widthPx: number, dpr: number): number {
    const geometry = paperGeometry(widthPx, this.#minHeightPx);
    this.#geometry = geometry;
    this.#dpr = dpr;
    this.canvas.width = Math.round(widthPx * dpr);
    this.canvas.height = Math.round(geometry.heightPx * dpr);
    this.canvas.style.height = `${geometry.heightPx}px`;
    this.#extents = new Float32Array(this.canvas.width * 2);
    this.#grid = undefined;
    return geometry.heightPx;
  }

  setColors(colors: TraceColors): void {
    this.#colors = colors;
    this.#grid = undefined;
  }

  /** The paper and its grid, 5 mm wider than the canvas so it can scroll. */
  #renderGrid(
    geometry: Geometry,
    colors: TraceColors,
    paper: string,
  ): HTMLCanvasElement {
    const dpr = this.#dpr;
    const mm = geometry.pxPerMm * dpr;
    const grid = document.createElement("canvas");
    grid.width = this.canvas.width + Math.ceil(5 * mm) + 1;
    grid.height = this.canvas.height;
    const g = grid.getContext("2d")!;
    g.fillStyle = paper;
    g.fillRect(0, 0, grid.width, grid.height);
    const line = (major: boolean) => {
      g.strokeStyle = major ? colors.gridMajor : colors.gridMinor;
      g.lineWidth = major ? Math.max(1, dpr) : Math.max(1, dpr * 0.5);
    };
    // Below about 2 CSS px per mm the 1 mm lines turn into a haze; keep the 5 mm ones.
    const minor = geometry.pxPerMm >= 2;
    const baseline = geometry.baselinePx * dpr;
    for (const major of minor ? [false, true] : [true]) {
      line(major);
      const step = major ? 5 * mm : mm;
      g.beginPath();
      for (let x = 0; x <= grid.width; x += step) {
        const px = Math.round(x) + 0.5;
        g.moveTo(px, 0);
        g.lineTo(px, grid.height);
      }
      // Horizontal lines run from the baseline, so 0 mV sits on a major line.
      for (let y = baseline % step; y <= grid.height; y += step) {
        const py = Math.round(y) + 0.5;
        g.moveTo(0, py);
        g.lineTo(grid.width, py);
      }
      g.stroke();
    }
    return grid;
  }

  draw(frame: Frame, paper: string): void {
    const geometry = this.#geometry;
    const colors = this.#colors;
    if (!geometry || !colors) return;
    const c = this.#context;
    const dpr = this.#dpr;
    this.#grid ??= this.#renderGrid(geometry, colors, paper);

    // The grid moves with the paper: offset by the time at the left edge.
    const mm = geometry.pxPerMm * dpr;
    const travelled = (frame.startSample / frame.fs) * MM_PER_S * mm;
    const offset = travelled % (5 * mm);
    c.drawImage(this.#grid, -offset, 0);

    // The trace: per device column, from the column's min to its max.
    const columns = this.canvas.width;
    const end = frame.startSample + SPAN_S * frame.fs;
    const extents = columnExtents(
      frame.trace,
      frame.startSample,
      end,
      columns,
      this.#extents,
    );
    c.save();
    c.scale(dpr, dpr);
    c.strokeStyle = colors.trace;
    c.lineWidth = 1.25;
    c.lineJoin = "round";
    c.lineCap = "round";
    c.beginPath();
    let drawing = false;
    for (let col = 0; col < columns; col++) {
      const min = extents[2 * col]!;
      const max = extents[2 * col + 1]!;
      if (Number.isNaN(min)) {
        drawing = false;
        continue;
      }
      const x = (col + 0.5) / dpr;
      const yTop = yForAdu(max, geometry);
      const yBottom = yForAdu(min, geometry);
      if (!drawing) c.moveTo(x, yTop);
      else c.lineTo(x, yTop);
      c.lineTo(x, yBottom);
      drawing = true;
    }
    c.stroke();
    this.#drawMarkers(frame, geometry, colors);
    this.#drawPen(frame, geometry, colors, paper);
    c.restore();
  }

  /** The pen tip: a teal dot where the trace is being written, on a faint rule. */
  #drawPen(
    frame: Frame,
    geometry: Geometry,
    colors: TraceColors,
    paper: string,
  ): void {
    const sample = frame.cursorSample;
    if (sample === undefined) return;
    const value = frame.trace[Math.min(sample, frame.trace.length - 1)];
    if (value === undefined) return;
    const c = this.#context;
    const radius = 3.5;
    const x = Math.min(
      geometry.widthPx - radius - 1.5,
      Math.max(
        radius + 1.5,
        xForSample(sample, frame.startSample, frame.fs, geometry),
      ),
    );
    const y = yForAdu(value, geometry);
    c.globalAlpha = 0.28;
    c.strokeStyle = colors.accent;
    c.lineWidth = 1;
    c.beginPath();
    c.moveTo(Math.round(x) + 0.5, 0);
    c.lineTo(Math.round(x) + 0.5, geometry.heightPx);
    c.stroke();
    c.globalAlpha = 1;
    c.fillStyle = colors.accent;
    c.strokeStyle = paper;
    c.lineWidth = 2;
    c.beginPath();
    c.arc(x, y, radius, 0, 2 * Math.PI);
    c.stroke();
    c.fill();
  }

  #drawMarkers(frame: Frame, geometry: Geometry, colors: TraceColors): void {
    const c = this.#context;
    const size = Math.round(Math.min(15, Math.max(11, geometry.pxPerMm * 3.2)));
    const top = Math.max(6, geometry.pxPerMm * 2);
    const y = top + size / 2;
    c.textAlign = "center";
    c.textBaseline = "middle";
    for (const marker of frame.markers) {
      const x = xForSample(
        marker.sample,
        frame.startSample,
        frame.fs,
        geometry,
      );
      switch (marker.kind) {
        case "pending": {
          // A small open mark: this beat's label is not known yet.
          c.strokeStyle = colors.muted;
          c.globalAlpha = 0.6;
          c.lineWidth = 1;
          c.beginPath();
          c.arc(x, y, size * 0.18, 0, 2 * Math.PI);
          c.stroke();
          c.globalAlpha = 1;
          break;
        }
        case "q": {
          // The grey "not scored" dash.
          c.strokeStyle = colors.classes.Q;
          c.lineWidth = 2;
          c.beginPath();
          c.moveTo(x - size * 0.35, y);
          c.lineTo(x + size * 0.35, y);
          c.stroke();
          break;
        }
        case "label":
        case "disagree": {
          // A new label lands: it grows and drops into place as it fades in.
          const t = easeOut(frame.landed?.(marker.row) ?? 1);
          c.save();
          if (t < 1) {
            c.globalAlpha = t;
            c.translate(x, y - (1 - t) * size * 0.5);
            c.scale(0.6 + 0.4 * t, 0.6 + 0.4 * t);
            c.translate(-x, -y);
          }
          const label = marker.label as keyof TraceColors["classes"];
          c.font = `600 ${size}px ${colors.font}`;
          c.fillStyle = colors.classes[label] ?? colors.trace;
          c.fillText(marker.label ?? "", x, y + 0.5);
          if (marker.kind === "disagree") {
            // The ring around the model's letter, the expert's letter beneath.
            c.strokeStyle = c.fillStyle;
            c.lineWidth = 1.5;
            c.beginPath();
            c.arc(x, y, size * 0.72, 0, 2 * Math.PI);
            c.stroke();
            const expert = marker.expert as keyof TraceColors["classes"];
            const small = Math.round(size * 0.8);
            c.font = `500 ${small}px ${colors.font}`;
            c.fillStyle = colors.classes[expert] ?? colors.muted;
            c.fillText(marker.expert ?? "", x, y + size * 0.72 + small * 0.75);
          }
          c.restore();
          break;
        }
      }
    }
  }
}
