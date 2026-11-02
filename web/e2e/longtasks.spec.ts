import { expect, test } from "@playwright/test";

// R38, D5: no main-thread task over 50 ms during playback, measured at 4x
// for 30 seconds in Chromium and WebKit (review focus 7: not only at 1x, not
// only in Chromium), on the phone profiles as well as the two desktop ones.
// Chromium reports long tasks itself; WebKit has no Long Tasks API, so a
// chain of zero-delay timers runs in both engines: a gap over 50 ms between
// two of them means the main thread was busy that long. The probe is the
// stricter of the two, since a gap can span several tasks.
// The probe also counts time the page waits for a CPU, so the test runs on
// its own (tag `@alone`: `pnpm run e2e` runs it after everything else, with
// one worker). On CI's 4 vCPU runner, running beside the other tests (the
// parity survey among them) put every project near the limit (ledger,
// 2026-11-02).
const LIMIT_MS = 50;
const PLAY_MS = 30_000;

interface Probe {
  __longTasks: number[];
  __gaps: number[];
  __gapEnds: number[];
  __probe: boolean;
}

test.describe("R38: long tasks during playback", { tag: "@alone" }, () => {
  test.setTimeout(PLAY_MS + 30_000);

  test("R38: no main-thread task over 50 ms in 30 seconds at 4x", async ({
    page,
  }, testInfo) => {
    await page.addInitScript(() => {
      const w = window as unknown as Probe;
      w.__longTasks = [];
      w.__gaps = [];
      w.__gapEnds = [];
      w.__probe = false;
      if (PerformanceObserver.supportedEntryTypes.includes("longtask")) {
        new PerformanceObserver((list) => {
          if (!w.__probe) return;
          for (const entry of list.getEntries())
            w.__longTasks.push(entry.duration);
        }).observe({ type: "longtask" });
      }
      let last = 0;
      const tick = () => {
        const now = performance.now();
        if (w.__probe && last) {
          w.__gaps.push(now - last);
          w.__gapEnds.push(now);
        }
        last = now;
        setTimeout(tick, 0);
      };
      setTimeout(tick, 0);
    });
    await page.goto("/");
    // Playback with live labels: the model is in and the counter shows.
    await expect(
      page.getByText(/Labels match the Python results: [\d,]+ of [\d,]+ beats/),
    ).toBeVisible();
    await page.getByLabel("Speed").selectOption("4");
    const playhead = page.getByTestId("playhead");
    const before = Number(await playhead.getAttribute("data-seconds"));
    await page.evaluate(() => {
      (window as unknown as Probe).__probe = true;
    });
    await page.waitForTimeout(PLAY_MS);
    const result = await page.evaluate(() => {
      const w = window as unknown as Probe;
      w.__probe = false;
      const gaps = w.__gaps.slice().sort((a, b) => a - b);
      // The five longest gaps and when each ended, in seconds into the probe,
      // so a log shows whether a failure is one spike or a pattern.
      const start = (w.__gapEnds[0] ?? 0) - (w.__gaps[0] ?? 0);
      const worst = w.__gaps
        .map((gap, i) => ({
          ms: Math.round(gap),
          atS: Math.round(((w.__gapEnds[i] ?? 0) - start) / 100) / 10,
        }))
        .sort((a, b) => b.ms - a.ms)
        .slice(0, 5);
      return {
        longTasks: w.__longTasks,
        gapCount: gaps.length,
        worstGap: gaps[gaps.length - 1] ?? 0,
        medianGap: gaps[Math.floor(gaps.length / 2)] ?? 0,
        worst,
      };
    });
    const after = Number(await playhead.getAttribute("data-seconds"));
    await testInfo.attach("long-tasks.json", {
      body: JSON.stringify(
        { project: testInfo.project.name, ...result, before, after },
        null,
        2,
      ),
      contentType: "application/json",
    });
    console.log(
      `R38 ${testInfo.project.name}: worst gap ${result.worstGap.toFixed(1)} ms, ` +
        `median ${result.medianGap.toFixed(1)} ms, ${result.gapCount} gaps, ` +
        `long tasks over ${LIMIT_MS} ms ${result.longTasks.filter((d) => d > LIMIT_MS).length}; ` +
        `longest ${result.worst.map((g) => `${g.ms} ms at ${g.atS} s`).join(", ")}`,
    );
    // Playback really ran at 4x: about 120 seconds of recording in 30.
    expect(after - before).toBeGreaterThan(100);
    expect(result.gapCount).toBeGreaterThan(1000);
    expect(result.longTasks.filter((d) => d > LIMIT_MS)).toEqual([]);
    expect(result.worstGap).toBeLessThanOrEqual(LIMIT_MS);
  });
});
