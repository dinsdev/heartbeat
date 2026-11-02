import { expect, test, type Page } from "@playwright/test";

// DEMO-14: the full page autoplays on load. Under reduced motion it does not,
// the paper never scrolls, and the view moves in fixed 10-second pages with
// Previous and Next; playing swaps pages every 10 seconds of recording.

async function seconds(page: Page): Promise<number> {
  return Number(
    await page.getByTestId("playhead").getAttribute("data-seconds"),
  );
}

/** Every right edge the view shows over `ms` of playback, in whole seconds. */
async function viewEnds(page: Page, ms: number): Promise<number[]> {
  await page.evaluate(() => {
    const strip = document.querySelector("[data-view-end]")!;
    const w = window as unknown as { __ends: number[] };
    w.__ends = [Number(strip.getAttribute("data-view-end"))];
    new MutationObserver(() =>
      w.__ends.push(Number(strip.getAttribute("data-view-end"))),
    ).observe(strip, { attributes: true, attributeFilter: ["data-view-end"] });
  });
  await page.waitForTimeout(ms);
  return page.evaluate(
    () => (window as unknown as { __ends: number[] }).__ends,
  );
}

test("the full page autoplays on load and offers no page buttons", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Pause" })).toBeVisible();
  const start = await seconds(page);
  await expect.poll(() => seconds(page)).toBeGreaterThan(start);
  await expect(
    page.getByRole("button", { name: "Next 10 seconds" }),
  ).toHaveCount(0);
  // With motion the paper scrolls: the view's edge passes whole seconds.
  await page.getByLabel("Speed").selectOption("4");
  const ends = await viewEnds(page, 3000);
  expect(ends.some((end) => end % 10 !== 0)).toBe(true);
});

test.describe("under reduced motion", () => {
  test.use({ reducedMotion: "reduce" });

  test("nothing plays until asked", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("button", { name: "Play" })).toBeVisible();
    const start = await seconds(page);
    await page.waitForTimeout(1500);
    expect(await seconds(page)).toBe(start);
  });

  test("Previous and Next move by whole 10-second pages", async ({ page }) => {
    await page.goto("/");
    const next = page.getByRole("button", { name: "Next 10 seconds" });
    const previous = page.getByRole("button", { name: "Previous 10 seconds" });
    await expect(next).toHaveText("Next");
    await expect(previous).toHaveText("Previous");
    const start = await seconds(page);
    await next.click();
    await expect.poll(() => seconds(page)).toBe(start + 10);
    await next.click();
    await expect.poll(() => seconds(page)).toBe(start + 20);
    await previous.click();
    await expect.poll(() => seconds(page)).toBe(start + 10);
    // The view and its words follow the page.
    await expect(
      page.getByRole("img", { name: /ECG trace/ }),
    ).toHaveAccessibleName(new RegExp(`, 0:${start} to 0:${start + 10}:`));
  });

  test("Previous stops at the first page of the recording", async ({
    page,
  }) => {
    await page.goto("/");
    await page.getByLabel("Recording").selectOption("115");
    await expect(page.getByRole("img", { name: /record 115/ })).toBeVisible();
    await expect.poll(() => seconds(page)).toBe(10);
    await page.getByRole("button", { name: "Previous 10 seconds" }).click();
    await page.waitForTimeout(300);
    expect(await seconds(page)).toBe(10);
  });

  test("playing swaps whole pages and never scrolls the paper", async ({
    page,
  }) => {
    await page.goto("/");
    await page.getByLabel("Speed").selectOption("4");
    await page.getByRole("button", { name: "Play" }).click();
    // 6 seconds at 4x is 24 seconds of recording: two or three page swaps.
    const ends = await viewEnds(page, 6000);
    expect(ends.every((end) => end % 10 === 0)).toBe(true);
    expect(new Set(ends).size).toBeGreaterThanOrEqual(2);
  });
});
