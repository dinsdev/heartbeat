// R39: measure dist/ after `vite build` and fail on any size gate (D5).
// The rules live in src/lib/gates.ts, which Node 24 imports as TypeScript.
import { readdirSync, readFileSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";

import { sizeProblems } from "../src/lib/gates.ts";

const dist = fileURLToPath(new URL("../dist/", import.meta.url));

function walk(folder) {
  return readdirSync(folder, { withFileTypes: true }).flatMap((entry) => {
    const path = join(folder, entry.name);
    return entry.isDirectory() ? walk(path) : [path];
  });
}

const files = walk(dist).map((path) => {
  const data = readFileSync(path);
  return {
    path: relative(dist, path).split(sep).join("/"),
    bytes: data.length,
    // zlib's default level, as most servers compress.
    gzipBytes: gzipSync(data).length,
  };
});

const show = (pattern) =>
  files
    .filter((f) => pattern.test(f.path))
    .map((f) => `  ${f.path}: ${f.bytes} bytes, ${f.gzipBytes} gzip`)
    .join("\n");
console.log(`size gates on ${dist}`);
console.log(show(/^assets\/.+\.m?js$|^data\/model\./));
const beats = files.filter((f) => f.path.endsWith(".beats.json"));
const largest = beats.reduce(
  (a, b) => (b.bytes > (a?.bytes ?? -1) ? b : a),
  undefined,
);
if (largest)
  console.log(`  largest beats file: ${largest.path}, ${largest.bytes} bytes`);

const problems = sizeProblems(files);
for (const problem of problems) console.error(`size gate failed: ${problem}`);
if (problems.length > 0) process.exit(1);
console.log("size gates passed");
