import { svelte } from "@sveltejs/vite-plugin-svelte";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [svelte()],
  test: {
    include: ["src/**/*.test.ts"],
    // R34 reads the token files as text; without this Vitest blanks CSS imports.
    css: true,
  },
});
