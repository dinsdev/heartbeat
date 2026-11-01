import { expect, test, type Page } from "@playwright/test";

// Settling 7, design call 7: dragging the paper scrubs the recording on the
// full page. The physics is unit tested in scroller.test.ts; this checks the
// wiring in a real browser: pointer events reach the scroller, the playhead
// follows, and reduced motion moves by whole pages.

async function seconds(page: Page): Promise<number> {
  return Number(await page.getByTestId("playhead").getAttribute("data-seconds"));
}

async function dragTrace(page: Page, dx: number) {
  const box = (await page.getByRole("img", { name: /ECG trace/ }).boundingBox())!;
  const y = box.y + box.height / 2;
  const x = box.x + box.width / 2 - dx / 2;
  await page.mouse.move(x, y);
  await page.mouse.down();
  // Slow enough that the release carries no coasting velocity.
  await page.mouse.move(x + dx, y, { steps: 20 });
  await page.waitForTimeout(200);
  await page.mouse.up();
  return box.width;
}

test("dragging right while paused brings earlier paper into view", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Pause" }).click();
  const before = await seconds(page);
  const width = await dragTrace(page, 300);
  await expect
    .poll(() => seconds(page))
    .toBeLessThanOrEqual(Math.ceil(before - (300 / width) * 10) + 1);
  expect(await seconds(page)).toBeGreaterThanOrEqual(
    Math.floor(before - (300 / width) * 10) - 1,
  );
  // Still paused: a drag does not start playback.
  await expect(page.getByRole("button", { name: "Play" })).toBeVisible();
});

test("playback resumes once a drag comes to rest", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Pause" })).toBeVisible();
  await dragTrace(page, 200);
  await expect(page.getByRole("button", { name: "Pause" })).toBeVisible();
  const settled = await seconds(page);
  await expect.poll(() => seconds(page)).toBeGreaterThan(settled);
});

test.describe("under reduced motion", () => {
  test.use({ reducedMotion: "reduce" });

  test("a drag moves back one whole 10-second page", async ({ page }) => {
    await page.goto("/");
    // No autoplay under reduced motion (DEMO-14).
    await expect(page.getByRole("button", { name: "Play" })).toBeVisible();
    const before = await seconds(page);
    const width = await dragTrace(page, 0);
    expect(width).toBeGreaterThan(0);
    expect(await seconds(page)).toBe(before);
    await dragTrace(page, 200);
    await expect.poll(() => seconds(page)).toBe(before - 10);
  });
});
