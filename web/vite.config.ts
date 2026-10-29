import { svelte } from "@sveltejs/vite-plugin-svelte";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [svelte()],
  test: {
    include: ["src/**/*.test.ts"],
    // Phase 1 only: there is no code to test yet, and a placeholder test would
    // be worse. Phase 6 removes this once real tests exist.
    passWithNoTests: true,
  },
});
