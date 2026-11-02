import { expect, type FrameLocator, type Page } from "@playwright/test";

// A stand-in for the case study: a page at `origin` that frames the embed.
// Playwright's router serves the page and proxies https://heartbeat.test to
// the local preview, so both are https (browsers block a public page framing
// localhost), frame-ancestors sees a real origin, and nothing leaves the
// machine.

export const APP = "https://heartbeat.test";

interface Options {
  /** Page height above the iframe, to start it below the fold. */
  above?: number;
  /** More markup after the iframe. */
  after?: string;
}

export async function hostAt(
  page: Page,
  origin: string,
  baseURL: string,
  { above = 0, after = "" }: Options = {},
): Promise<FrameLocator> {
  await page.context().route(`${APP}/**`, async (route) => {
    const url = route.request().url().replace(APP, baseURL);
    await route.fulfill({ response: await route.fetch({ url }) });
  });
  await page.route(`${origin}/case`, (route) =>
    route.fulfill({
      contentType: "text/html",
      body: `<!doctype html><body style="margin:0">
        <div style="height:${above}px">Case study text</div>
        <iframe id="demo" title="Heartbeat demo" src="${APP}/?embed=page"
          style="display:block;width:800px;height:500px;border:0"></iframe>
        ${after}
        <div style="height:400px"></div>
      </body>`,
    }),
  );
  await page.goto(`${origin}/case`);
  return page.frameLocator("#demo");
}

/**
 * Drops the proxy route when a test ends. Without it, a request still in
 * flight (the 14 MB runtime, say) fails the test after its checks passed
 * (`route.fetch: Test ended`). Call it from `test.afterEach`.
 */
export async function unhost(page: Page) {
  await page.context().unrouteAll({ behavior: "ignoreErrors" });
}

/** The case study on dins.dev with the embed in view, playing. */
export async function caseStudy(
  page: Page,
  baseURL: string,
  options?: Options,
) {
  const demo = await hostAt(page, "https://dins.dev", baseURL, options);
  await expect(demo.getByRole("button", { name: "Pause" })).toBeVisible();
  return demo;
}
