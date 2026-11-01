import { defineConfig, devices } from "@playwright/test";

const PORT = 4173;

export default defineConfig({
  testDir: "e2e",
  forbidOnly: true,
  retries: 0,
  use: { baseURL: `http://localhost:${PORT}` },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
    // Phase 6 design call 18: the two phone profiles.
    { name: "pixel-7", use: { ...devices["Pixel 7"] } },
    { name: "iphone-15", use: { ...devices["iPhone 15"] } },
  ],
  // The tests run against the built page, as it ships.
  webServer: {
    // With the size gates, as `pnpm run build`; the demo data must be built.
    command: `pnpm run build && pnpm exec vite preview --port ${PORT} --strictPort`,
    url: `http://localhost:${PORT}`,
    reuseExistingServer: false,
  },
});
