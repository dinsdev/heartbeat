import { describe, expect, test } from "vitest";

import { type DistFile, GATES, sizeProblems } from "./gates";

function files(
  overrides: Partial<Record<string, Partial<DistFile>>> = {},
): DistFile[] {
  const base: DistFile[] = [
    { path: "index.html", bytes: 900, gzipBytes: 400 },
    { path: "assets/index-a1.js", bytes: 70_000, gzipBytes: 25_000 },
    { path: "assets/labeler.worker-b2.js", bytes: 9_000, gzipBytes: 3_500 },
    { path: "assets/ort-c3.js", bytes: 400_000, gzipBytes: 120_000 },
    {
      path: "assets/ort-wasm-simd-threaded-d4.wasm",
      bytes: 14_000_000,
      gzipBytes: 3_700_000,
    },
    { path: "data/model.6e523798.onnx", bytes: 210_503, gzipBytes: 190_000 },
    { path: "data/215.aaaaaaaa.beats.json", bytes: 98_213, gzipBytes: 30_000 },
    { path: "data/223.bbbbbbbb.beats.json", bytes: 77_214, gzipBytes: 25_000 },
    {
      path: "data/223.cccccccc.trace.i16",
      bytes: 1_300_000,
      gzipBytes: 900_000,
    },
  ];
  return base.map((f) => ({ ...f, ...overrides[f.path] }));
}

describe("R39: model under 1 MB, demo JS under 60 KB gzip, beats JSON under 100 KB", () => {
  test("R39: the limits are D5's", () => {
    expect(GATES).toEqual({
      modelBytes: 1_000_000,
      javascriptGzipBytes: 60_000,
      beatsBytes: 100_000,
    });
  });

  test("R39: a build within every gate passes", () => {
    expect(sizeProblems(files())).toEqual([]);
  });

  test("R39: a model of 1 MB fails", () => {
    const problems = sizeProblems(
      files({ "data/model.6e523798.onnx": { bytes: 1_000_000 } }),
    );
    expect(problems).toEqual([
      expect.stringMatching(/model\.6e523798\.onnx.*1000000/),
    ]);
  });

  test("R39: demo JavaScript of 60 KB gzip fails, ONNX Runtime not counted", () => {
    expect(
      sizeProblems(files({ "assets/index-a1.js": { gzipBytes: 56_500 } })),
    ).toEqual([expect.stringMatching(/JavaScript.*60000/)]);
    // The runtime chunk can be any size.
    expect(
      sizeProblems(files({ "assets/ort-c3.js": { gzipBytes: 900_000 } })),
    ).toEqual([]);
  });

  test("R39: a beats file of 100 KB fails and is named", () => {
    const problems = sizeProblems(
      files({ "data/215.aaaaaaaa.beats.json": { bytes: 100_000 } }),
    );
    expect(problems).toEqual([
      expect.stringMatching(/215\.aaaaaaaa\.beats\.json.*100000/),
    ]);
  });

  test("R39: a build with no model, no beats files or no separate runtime fails", () => {
    const without = (prefix: string) =>
      files().filter((f) => !f.path.startsWith(prefix));
    expect(sizeProblems(without("data/model."))).toEqual([
      expect.stringMatching(/model/),
    ]);
    expect(sizeProblems(without("data/2"))).toEqual([
      expect.stringMatching(/beats/),
    ]);
    expect(sizeProblems(without("assets/ort-c3"))).toEqual([
      expect.stringMatching(/ONNX Runtime/),
    ]);
  });
});
