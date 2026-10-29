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
  ],
  // The tests run against the built page, as it ships.
  webServer: {
    command: `pnpm exec vite build && pnpm exec vite preview --port ${PORT} --strictPort`,
    url: `http://localhost:${PORT}`,
    reuseExistingServer: false,
  },
});
