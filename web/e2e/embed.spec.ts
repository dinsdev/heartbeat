import { expect, test, type Page, type Request } from "@playwright/test";

// Settling 5, design call 12: `?embed=page` is the case study's iframe. It
// shows the compact control set, fetches nothing heavy (the runtime, the
// model, a trace) until it is on screen, then autoplays (DEMO-14) unless
// reduced motion is set.

const HEAVY = /\.(wasm|onnx|i16)(\?|$)|worker/;

/** A host page with the embed far below the fold, as the case study has it. */
async function host(page: Page, baseURL: string) {
  await page.setContent(
    `<!doctype html><body style="margin:0">
      <div style="height:3000px">Case study text</div>
      <iframe id="demo" title="Heartbeat demo" src="${baseURL}/?embed=page"
        style="display:block;width:800px;height:500px;border:0"></iframe>
      <div style="height:400px"></div>
    </body>`,
  );
  return page.frameLocator("#demo");
}

test("the embed shows the compact set and links to the full demo", async ({
  page,
}) => {
  await page.goto("/?embed=page");
  await expect(page.getByRole("button", { name: "Pause" })).toBeVisible();
  for (const name of ["Next irregular beat", "Next disagreement"]) {
    await expect(page.getByRole("button", { name })).toBeVisible();
  }
  await expect(page.getByLabel("Speed")).toBeVisible();
  await expect(page.getByTestId("playhead")).toBeVisible();
  await expect(page.getByText("Record 223")).toBeVisible();
  await expect(
    page.getByText("Research demo, not medical advice.", { exact: false }),
  ).toBeVisible();
  // Left out: the page chrome, the picker, the slider, the status line and
  // the table.
  await expect(page.getByRole("banner")).toHaveCount(0);
  await expect(page.getByRole("contentinfo")).toHaveCount(0);
  await expect(page.getByLabel("Recording")).toHaveCount(0);
  await expect(page.getByRole("slider")).toHaveCount(0);
  await expect(page.getByTestId("summary")).toHaveCount(0);
  await expect(page.getByRole("table")).toHaveCount(0);
  const link = page.getByRole("link", { name: "Open the full demo" });
  await expect(link).toHaveAttribute("target", "_blank");
  await expect(link).toHaveAttribute("rel", "noopener");
  expect(new URL((await link.getAttribute("href"))!).search).toBe("");
});

test("the embed fetches nothing heavy until it scrolls into view, then plays", async ({
  page,
  baseURL,
}) => {
  const heavy: string[] = [];
  const note = (request: Request) => {
    if (HEAVY.test(request.url())) heavy.push(request.url());
  };
  page.on("request", note);
  page.on("worker", () => heavy.push("a Worker started"));
  const demo = await host(page, baseURL!);
  // The embed's page itself is loaded and waiting.
  await expect(demo.locator("main")).toBeAttached();
  await page.waitForTimeout(1500);
  expect(heavy).toEqual([]);
  await expect(demo.getByRole("button", { name: /Play|Pause/ })).toHaveCount(0);

  await page.locator("#demo").scrollIntoViewIfNeeded();
  await expect(demo.getByRole("button", { name: "Pause" })).toBeVisible();
  expect(heavy.some((url) => url.endsWith(".trace.i16"))).toBe(true);
});

test.describe("under reduced motion", () => {
  test.use({ reducedMotion: "reduce" });

  test("the embed loads when seen but does not play", async ({
    page,
    baseURL,
  }) => {
    const demo = await host(page, baseURL!);
    await page.locator("#demo").scrollIntoViewIfNeeded();
    await expect(demo.getByRole("button", { name: "Play" })).toBeVisible();
    await expect(
      demo.getByRole("button", { name: "Next 10 seconds" }),
    ).toBeVisible();
  });
});
