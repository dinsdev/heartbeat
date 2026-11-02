import { defineConfig, devices } from "@playwright/test";

const PORT = 4173;
// Design call 20: the timings need CPU throttling, which only Chromium has.
// They run once in the chromium project, which emulates the phone itself.
const CHROMIUM_ONLY = /timings\.spec\.ts$/;

export default defineConfig({
  testDir: "e2e",
  forbidOnly: true,
  retries: 0,
  use: { baseURL: `http://localhost:${PORT}` },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    {
      name: "webkit",
      use: { ...devices["Desktop Safari"] },
      testIgnore: CHROMIUM_ONLY,
    },
    // Phase 6 design call 18: the two phone profiles.
    {
      name: "pixel-7",
      use: { ...devices["Pixel 7"] },
      testIgnore: CHROMIUM_ONLY,
    },
    {
      name: "iphone-15",
      use: { ...devices["iPhone 15"] },
      testIgnore: CHROMIUM_ONLY,
    },
  ],
  // The tests run against the built page, as it ships.
  webServer: {
    // With the size gates, as `pnpm run build`; the demo data must be built.
    command: `pnpm run build && pnpm exec vite preview --port ${PORT} --strictPort`,
    url: `http://localhost:${PORT}`,
    reuseExistingServer: false,
  },
});
