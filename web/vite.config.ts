import { svelte } from "@sveltejs/vite-plugin-svelte";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [svelte()],
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
