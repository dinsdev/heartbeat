// D5, R39: the build's size gates. `scripts/size-gates.js` measures `dist/`
// and runs these after `vite build`; any problem fails the build.

export const GATES = {
  // R25: the model file under 1 MB.
  modelBytes: 1_000_000,
  // The demo's JavaScript, excluding ONNX Runtime, under 60 KB gzip in all.
  javascriptGzipBytes: 60_000,
  // Each beats file under 100 KB uncompressed.
  beatsBytes: 100_000,
} as const;

/** One file of the built `dist/`, with its path relative to it. */
export interface DistFile {
  path: string;
  bytes: number;
  gzipBytes: number;
}

// The Worker's ONNX Runtime chunk, split out by name in vite.config.ts.
const RUNTIME_CHUNK = /^assets\/ort-[\w-]+\.js$/;
const JAVASCRIPT = /^assets\/.+\.m?js$/;
const MODEL = /^data\/model\.[0-9a-f]{8}\.onnx$/;
const BEATS = /^data\/.+\.beats\.json$/;

export function sizeProblems(files: readonly DistFile[]): string[] {
  const problems: string[] = [];
  const models = files.filter((f) => MODEL.test(f.path));
  if (models.length !== 1) {
    problems.push(`expected one model file in data/, found ${models.length}`);
  }
  for (const model of models) {
    if (model.bytes >= GATES.modelBytes) {
      problems.push(
        `${model.path}: ${model.bytes} bytes, the gate is under ${GATES.modelBytes}`,
      );
    }
  }

  const beats = files.filter((f) => BEATS.test(f.path));
  if (beats.length === 0)
    problems.push("no beats files in data/; build the demo data first");
  for (const file of beats) {
    if (file.bytes >= GATES.beatsBytes) {
      problems.push(
        `${file.path}: ${file.bytes} bytes, the gate is under ${GATES.beatsBytes}`,
      );
    }
  }

  const runtime = files.filter((f) => RUNTIME_CHUNK.test(f.path));
  if (runtime.length !== 1) {
    problems.push(
      `expected one ONNX Runtime chunk (assets/ort-*.js), found ${runtime.length}`,
    );
  }
  const demo = files.filter(
    (f) => JAVASCRIPT.test(f.path) && !RUNTIME_CHUNK.test(f.path),
  );
  const gzip = demo.reduce((sum, f) => sum + f.gzipBytes, 0);
  if (gzip >= GATES.javascriptGzipBytes) {
    problems.push(
      `demo JavaScript without ONNX Runtime: ${gzip} bytes gzip, the gate is under ${GATES.javascriptGzipBytes}`,
    );
  }
  return problems;
}
