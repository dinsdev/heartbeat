import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { devices, expect, test } from "@playwright/test";

// Phase 6 design call 20, D5: reported timings, not a gate. Chromium only
// (WebKit has no CPU throttling; `playwright.config.ts` keeps this file to the
// chromium project), 4x CPU slowdown, the phone profile on fast 4G. Writes
// `test-results/timings.json`; the ledger records the numbers.
//
// The slowdown reaches the main thread only: Chromium refuses CPU throttling
// on a Worker target ("Operation is only supported for pages, not workers",
// Chromium 156), so the Worker's inference runs at the machine's full speed.
//
// The local preview serves files uncompressed, where Cloudflare sends Brotli,
// so the phone's load times over fast 4G are an upper bound. The report keeps
// the bytes transferred (the page's and the Worker's requests) next to them.

const OUT = fileURLToPath(new URL("../test-results/", import.meta.url));
const CPU_SLOWDOWN = 4;
const PACING_MS = 10_000;

// Chrome DevTools' "Fast 4G" preset (devtools-frontend
// `front_end/core/sdk/NetworkManager.ts`, Fast4GConditions): bytes per second
// and milliseconds.
const FAST_4G = {
  offline: false,
  downloadThroughput: ((9 * 1000 * 1000) / 8) * 0.9,
  uploadThroughput: ((1.5 * 1000 * 1000) / 8) * 0.9,
  latency: 60 * 2.75,
};

const RUNS = [
  { name: "desktop", device: devices["Desktop Chrome"], network: undefined },
  { name: "phone", device: devices["Pixel 7"], network: FAST_4G },
] as const;

interface Spy {
  __t: {
    firstTrace?: number;
    firstLabel?: number;
    batches: { ms: number; beats: number }[];
    frames: number[];
    pacing: boolean;
  };
}

function median(values: number[]): number {
  const sorted = values.slice().sort((a, b) => a - b);
  return sorted[Math.floor(sorted.length / 2)] ?? Number.NaN;
}

function percentile(values: number[], p: number): number {
  const sorted = values.slice().sort((a, b) => a - b);
  return sorted[Math.min(sorted.length - 1, Math.floor(p * sorted.length))]!;
}

test("timings at 4x CPU slowdown: desktop, and the phone on fast 4G", async ({
  browser,
  baseURL,
}, testInfo) => {
  test.setTimeout(240_000);
  const report: Record<string, unknown> = {
    browser: `Chromium ${browser.version()}`,
    cpuSlowdown: CPU_SLOWDOWN,
    cpuSlowdownReachesWorker: false,
    server: "vite preview, uncompressed",
  };
  for (const run of RUNS) {
    const context = await browser.newContext({
      ...run.device,
      baseURL: baseURL!,
    });
    const page = await context.newPage();
    const cdp = await context.newCDPSession(page);
    await cdp.send("Emulation.setCPUThrottlingRate", { rate: CPU_SLOWDOWN });
    if (run.network) {
      await cdp.send("Network.enable");
      await cdp.send("Network.emulateNetworkConditions", run.network);
    }
    const sizes: Promise<number>[] = [];
    page.on("requestfinished", (request) =>
      sizes.push(request.sizes().then((s) => s.responseBodySize)),
    );
    await page.addInitScript(() => {
      const t: Spy["__t"] = { batches: [], frames: [], pacing: false };
      (window as unknown as Spy).__t = t;
      // Worker replies as the page receives them: inference time per batch.
      const Base = window.Worker;
      window.Worker = class extends Base {
        constructor(url: string | URL, options?: WorkerOptions) {
          super(url, options);
          this.addEventListener("message", (event: MessageEvent<unknown>) => {
            const data = event.data as {
              type?: string;
              inferenceMs?: number;
              labels?: Uint8Array;
            };
            if (data.type !== "labels") return;
            t.firstLabel ??= performance.now();
            t.batches.push({
              ms: data.inferenceMs!,
              beats: data.labels!.length,
            });
          });
        }
      };
      let last = 0;
      const frame = (now: number) => {
        if (
          t.firstTrace === undefined &&
          document.querySelector(".trace canvas")
        )
          t.firstTrace = now;
        if (t.pacing && last) t.frames.push(now - last);
        last = now;
        requestAnimationFrame(frame);
      };
      requestAnimationFrame(frame);
    });
    await page.goto("/");
    await page.waitForFunction(
      () => (window as unknown as Spy).__t.firstLabel !== undefined,
      null,
      { timeout: 180_000 },
    );
    // The full page autoplays at 1x: frame pacing over 10 seconds of it.
    await expect(page.getByRole("button", { name: "Pause" })).toBeVisible();
    await page.evaluate(() => ((window as unknown as Spy).__t.pacing = true));
    await page.waitForTimeout(PACING_MS);
    const t = await page.evaluate(() => {
      const spy = (window as unknown as Spy).__t;
      spy.pacing = false;
      const memory = (
        performance as unknown as { memory?: { usedJSHeapSize: number } }
      ).memory;
      return { ...spy, heapBytes: memory?.usedJSHeapSize };
    });
    const bodyBytes = (await Promise.all(sizes)).reduce((a, b) => a + b, 0);
    const perBeat = t.batches.map((b) => b.ms / b.beats);
    const beats = t.batches.reduce((sum, b) => sum + b.beats, 0);
    const inferenceMs = t.batches.reduce((sum, b) => sum + b.ms, 0);
    report[run.name] = {
      device: run.name === "desktop" ? "Desktop Chrome" : "Pixel 7",
      network: run.network ? "fast 4G" : "none",
      firstTraceMs: Math.round(t.firstTrace!),
      firstLiveLabelMs: Math.round(t.firstLabel!),
      workerBatches: t.batches.length,
      medianBeatsPerBatch: median(t.batches.map((b) => b.beats)),
      medianInferenceMsPerBeat: Number(median(perBeat).toFixed(3)),
      pooledInferenceMsPerBeat: Number((inferenceMs / beats).toFixed(3)),
      frames: t.frames.length,
      medianFrameMs: Number(median(t.frames).toFixed(2)),
      p95FrameMs: Number(percentile(t.frames, 0.95).toFixed(2)),
      framesOver20Ms: t.frames.filter((ms) => ms > 20).length,
      jsHeapMB: Number((t.heapBytes! / 1e6).toFixed(1)),
      responseBodyMB: Number((bodyBytes / 1e6).toFixed(2)),
    };
    // Sanity, not a gate: every number was measured.
    expect(t.firstTrace).toBeGreaterThan(0);
    expect(t.firstLabel).toBeGreaterThan(0);
    expect(perBeat.length).toBeGreaterThan(0);
    expect(t.frames.length).toBeGreaterThan(0);
    expect(t.heapBytes).toBeGreaterThan(0);
    await context.close();
  }
  mkdirSync(OUT, { recursive: true });
  const body = JSON.stringify(report, null, 2);
  writeFileSync(join(OUT, "timings.json"), body + "\n");
  await testInfo.attach("timings.json", {
    body,
    contentType: "application/json",
  });
});
