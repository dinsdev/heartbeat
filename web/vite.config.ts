import { readFileSync } from "node:fs";

import { svelte } from "@sveltejs/vite-plugin-svelte";
import { defineConfig } from "vitest/config";

/**
 * The headers `public/_headers` gives every path (its `/*` rule), so `vite
 * preview`, and with it every Playwright test, runs under the shipped CSP.
 */
function headersForEveryPath(): Record<string, string> {
  const text = readFileSync(
    new URL("public/_headers", import.meta.url),
    "utf8",
  );
  const headers: Record<string, string> = {};
  let inRule = false;
  for (const line of text.split("\n")) {
    if (line.trim() === "" || line.trim().startsWith("#")) continue;
    if (!/^\s/.test(line)) {
      inRule = line.trim() === "/*";
      continue;
    }
    if (!inRule) continue;
    const at = line.indexOf(":");
    headers[line.slice(0, at).trim()] = line.slice(at + 1).trim();
  }
  return headers;
}

export default defineConfig({
  plugins: [svelte()],
  preview: { headers: headersForEveryPath() },
  worker: {
    format: "es",
    rolldownOptions: {
      output: {
        // R39: ONNX Runtime gets its own chunk, ort-<hash>.js, so the size
        // gate can leave it out of the demo's JavaScript by name.
        codeSplitting: {
          groups: [{ name: "ort", test: /node_modules[\\/]onnxruntime-web/ }],
        },
      },
    },
  },
  test: {
    include: ["src/**/*.test.ts"],
    // R34 reads the token files as text; without this Vitest blanks CSS imports.
    css: true,
  },
});
