import { expect, test, type Page } from "@playwright/test";

// DEMO-10 to DEMO-12, D6: every control works, the table lists the beats in
// view, the status line summarizes every 10 seconds of playback, and the
// canvas label changes on pause and seek, not per frame.

async function seconds(page: Page): Promise<number> {
  return Number(
    await page.getByTestId("playhead").getAttribute("data-seconds"),
  );
}

async function ready(page: Page) {
  await page.goto("/");
  await expect(
    page.getByText(/Labels match the Python results: [\d,]+ of [\d,]+ beats/),
  ).toBeVisible();
}

async function pause(page: Page) {
  await page.getByRole("button", { name: "Pause" }).click();
  await expect(page.getByRole("button", { name: "Play" })).toBeVisible();
}

const trace = (page: Page) => page.getByRole("img", { name: /ECG trace/ });
const table = (page: Page) =>
  page.getByRole("table", { name: /Beats in view/ });

test("play and pause stop and start the playhead", async ({ page }) => {
  await ready(page);
  await pause(page);
  const paused = await seconds(page);
  await page.waitForTimeout(1500);
  expect(await seconds(page)).toBe(paused);
  await page.getByRole("button", { name: "Play" }).click();
  await expect.poll(() => seconds(page)).toBeGreaterThan(paused);
});

test("speed: 0.5x to 4x, and at 4x the playhead runs four times as fast", async ({
  page,
}) => {
  await ready(page);
  const speed = page.getByLabel("Speed");
  await expect(speed.locator("option")).toHaveText(["0.5x", "1x", "2x", "4x"]);
  await pause(page);
  await speed.selectOption("4");
  const before = await seconds(page);
  await page.getByRole("button", { name: "Play" }).click();
  await page.waitForTimeout(2000);
  await pause(page);
  const moved = (await seconds(page)) - before;
  expect(moved).toBeGreaterThanOrEqual(6);
  expect(moved).toBeLessThanOrEqual(10);
});

test("the scrub slider moves in 5-second steps with the time as text", async ({
  page,
}) => {
  await ready(page);
  await pause(page);
  const slider = page.getByRole("slider", { name: "Position" });
  await expect(slider).toHaveAttribute("step", "5");
  await slider.fill("600");
  await expect.poll(() => seconds(page)).toBe(600);
  await expect(slider).toHaveAttribute("aria-valuetext", "10:00 of 30:05");
  await expect(page.getByTestId("playhead")).toHaveText("10:00 of 30:05");
  await slider.press("ArrowRight");
  await expect.poll(() => seconds(page)).toBe(605);
});

test("the patient picker lists the 22 records with class counts and switches", async ({
  page,
}) => {
  await ready(page);
  const picker = page.getByLabel("Recording");
  await expect(picker.locator("option")).toHaveCount(22);
  await expect(picker.locator("option:checked")).toHaveText(
    "Record 223: 2,043 N, 73 S, 473 V, 14 F",
  );
  await picker.selectOption("115");
  await expect(trace(page)).toHaveAccessibleName(/record 115/);
  await expect.poll(() => seconds(page)).toBeGreaterThanOrEqual(10);
  await expect(page.getByTestId("playhead")).toHaveText(/ of 30:05$/);
});

test("Next irregular beat brings a beat the experts call S, V or F into view", async ({
  page,
}) => {
  await ready(page);
  await pause(page);
  const button = page.getByRole("button", { name: "Next irregular beat" });
  await button.click();
  const note = page.getByTestId("jump-note");
  await expect(note).toHaveText(/^Beat at \d+:\d\d\.\d: experts [SVF]$/);
  const first = await note.textContent();
  const expert = first!.slice(-1);
  await expect(
    table(page)
      .getByRole("row")
      .filter({ has: page.getByRole("cell", { name: expert, exact: true }) }),
  ).not.toHaveCount(0);
  // A second press always moves on.
  await button.click();
  await expect(note).not.toHaveText(first!);
});

test("Next disagreement brings a beat where model and experts differ into view", async ({
  page,
}) => {
  await ready(page);
  await pause(page);
  await page.getByRole("button", { name: "Next disagreement" }).click();
  await expect(page.getByTestId("jump-note")).toHaveText(
    /^Beat at \d+:\d\d\.\d: model [NSVF], experts [NSVF]$/,
  );
  await expect(
    table(page)
      .getByRole("row")
      .filter({ has: page.getByRole("cell", { name: "No", exact: true }) }),
  ).not.toHaveCount(0);
});

test("a record with no irregular beats says so (DS1 record 115)", async ({
  page,
}) => {
  await ready(page);
  await page.getByLabel("Recording").selectOption("115");
  await expect(trace(page)).toHaveAccessibleName(/record 115/);
  await page.getByRole("button", { name: "Next irregular beat" }).click();
  await expect(page.getByTestId("jump-note")).toHaveText(
    "No irregular beats in this recording",
  );
});

test("the table lists the beats in view with five columns", async ({
  page,
}) => {
  await ready(page);
  await pause(page);
  const t = table(page);
  await expect(t.getByRole("columnheader")).toHaveText([
    "Time",
    "Model",
    "Estimated probability",
    "Experts",
    "Match",
  ]);
  // The canvas label and the table count the same beats.
  const name = (await trace(page).getAttribute("aria-label"))!;
  const beats = Number(/: (\d+) beats?/.exec(name)![1]);
  expect(beats).toBeGreaterThan(5);
  await expect(t.locator("tbody tr")).toHaveCount(beats);
  await expect(
    page.getByText(/first and last beats of each recording have no label/),
  ).toBeVisible();
});

test("the status line summarizes every 10 seconds of playback", async ({
  page,
}) => {
  await ready(page);
  const status = page.getByTestId("summary");
  await expect(status).toHaveAttribute("role", "status");
  await expect(status).toHaveText(/^Last 10 seconds: \d+ beats?, /);
  await page.getByLabel("Speed").selectOption("4");
  await page.evaluate(() => {
    const el = document.querySelector("[data-testid=summary]")!;
    const w = window as unknown as { __changes: number };
    w.__changes = 0;
    new MutationObserver(() => w.__changes++).observe(el, {
      characterData: true,
      childList: true,
      subtree: true,
    });
  });
  // 10 seconds at 4x is 40 seconds of recording: about four summaries.
  await page.waitForTimeout(10_000);
  const changes = await page.evaluate(
    () => (window as unknown as { __changes: number }).__changes,
  );
  expect(changes).toBeGreaterThanOrEqual(2);
  expect(changes).toBeLessThanOrEqual(6);
});

test("the canvas label changes on pause and seek, never while playing", async ({
  page,
}) => {
  await ready(page);
  await page.getByLabel("Speed").selectOption("4");
  await page.evaluate(() => {
    const el = document.querySelector("[role=img][aria-label^='ECG trace']")!;
    const w = window as unknown as { __labels: string[] };
    w.__labels = [];
    new MutationObserver(() =>
      w.__labels.push(el.getAttribute("aria-label")!),
    ).observe(el, { attributes: true, attributeFilter: ["aria-label"] });
  });
  await page.waitForTimeout(3000);
  const whilePlaying = await page.evaluate(
    () => (window as unknown as { __labels: string[] }).__labels.length,
  );
  expect(whilePlaying).toBe(0);
  await pause(page);
  await expect(trace(page)).toHaveAccessibleName(
    /^ECG trace of record 223, \d+:\d\d to \d+:\d\d: \d+ beats/,
  );
  const atPause = await trace(page).getAttribute("aria-label");
  await page.getByRole("slider", { name: "Position" }).fill("900");
  await expect(trace(page)).toHaveAccessibleName(/15:00:/);
  expect(await trace(page).getAttribute("aria-label")).not.toBe(atPause);
});

test("the legend explains every mark in one line each (DEMO-11)", async ({
  page,
}) => {
  await ready(page);
  const legend = page.getByRole("list", { name: "What the marks mean" });
  for (const line of [
    "N Normal",
    "S Supraventricular early beat",
    "V Ventricular early beat",
    "F Fusion beat",
    "Not scored",
    "Model and experts disagree",
  ]) {
    await expect(legend.getByText(line, { exact: false })).toBeVisible();
  }
});

test("using every control raises no page error", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await ready(page);
  await page.getByLabel("Speed").selectOption("2");
  await page.getByRole("button", { name: "Next irregular beat" }).click();
  await page.getByRole("button", { name: "Next disagreement" }).click();
  await pause(page);
  await page.getByRole("slider", { name: "Position" }).fill("300");
  await page.getByLabel("Recording").selectOption("201");
  await expect(trace(page)).toHaveAccessibleName(/record 201/);
  await page.waitForTimeout(1000);
  expect(errors).toEqual([]);
});
