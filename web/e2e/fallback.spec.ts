import { expect, test, type Page } from "@playwright/test";

// DEMO-05, DEMO-06, R33: the fallback and the loading state are labeled,
// never silent.
const FALLBACK = "Showing precomputed labels; in-browser model unavailable";
const LOADING = "Model loading";

async function expectFallback(page: Page): Promise<void> {
  const demo = page.getByTestId("demo");
  await expect(page.getByText(FALLBACK)).toBeVisible();
  await expect(demo).toHaveAttribute("data-label-source", "python");
  // The Python labels play: the visible span shows labeled beats.
  await expect(demo).not.toHaveAttribute("data-labels-shown", "0");
  await expect(page.getByText(/Labels match the Python results/)).toHaveCount(
    0,
  );
}

test("R33: with WebAssembly blocked the Python labels play with the fallback note", async ({
  page,
}) => {
  await page.addInitScript(() => {
    // As a page whose policy or browser has no WebAssembly.
    Reflect.deleteProperty(globalThis, "WebAssembly");
  });
  await page.goto("/");
  await expectFallback(page);
});

test("R33: with the runtime's .wasm file blocked the fallback is labeled", async ({
  page,
  context,
}) => {
  await context.route("**/*.wasm", (route) => route.abort());
  await page.goto("/");
  await expectFallback(page);
});

test("R33: a failing model URL shows the fallback note and Python labels", async ({
  page,
  context,
}) => {
  await context.route("**/data/model.*.onnx", (route) =>
    route.fulfill({ status: 404, body: "" }),
  );
  await page.goto("/");
  await expectFallback(page);
});

test("the loading note shows until the Worker is ready, then the counter", async ({
  page,
  context,
}) => {
  let release: () => void = () => undefined;
  const held = new Promise<void>((resolve) => (release = resolve));
  await context.route("**/data/model.*.onnx", async (route) => {
    await held;
    await route.continue();
  });
  await page.goto("/");
  const demo = page.getByTestId("demo");
  await expect(page.getByText(LOADING)).toBeVisible();
  // The trace and expert labels arrive before the model (DEMO-06).
  await expect(demo).toHaveAttribute("data-trace", "ready");
  await expect(demo).toHaveAttribute("data-label-source", "none");
  release();
  await expect(
    page.getByText(/Labels match the Python results: [\d,]+ of [\d,]+ beats/),
  ).toBeVisible();
  await expect(page.getByText(LOADING)).toHaveCount(0);
  await expect(demo).toHaveAttribute("data-label-source", "browser");
});
