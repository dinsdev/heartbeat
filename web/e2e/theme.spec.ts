import { expect, test, type Page } from "@playwright/test";

import { caseStudy, unhost } from "./host";

test.afterEach(({ page }) => unhost(page));

// R37 end to end (the rule's own test is the unit test in
// src/lib/theme/messages.test.ts): the case study on https://dins.dev posts
// `{type: "theme", value}` to the iframe.

test.use({ colorScheme: "light" });

function post(page: Page, data: unknown) {
  return page.evaluate((message) => {
    const frame = document.getElementById("demo") as HTMLIFrameElement;
    frame.contentWindow!.postMessage(message, "*");
  }, data);
}

/** The trace canvas's mean brightness, 0 to 255. */
function brightness(page: Page) {
  return page
    .frames()
    .find((f) => f.url().includes("embed=page"))!
    .evaluate(() => {
      const canvas = document.querySelector("canvas")!;
      const { data } = canvas
        .getContext("2d")!
        .getImageData(0, 0, canvas.width, canvas.height);
      let sum = 0;
      for (let i = 0; i < data.length; i += 4) {
        sum += (data[i]! + data[i + 1]! + data[i + 2]!) / 3;
      }
      return sum / (data.length / 4);
    });
}

test("R37: the embed takes the theme dins.dev posts, page and trace", async ({
  page,
  baseURL,
}) => {
  const demo = await caseStudy(page, baseURL!);
  const html = demo.locator("html");
  // A blank canvas reads 0: wait for the first frame on light paper.
  await expect.poll(() => brightness(page)).toBeGreaterThan(128);
  const light = await brightness(page);
  await post(page, { type: "theme", value: "dark" });
  await expect(html).toHaveAttribute("data-theme", "dark");
  // The paper follows: the canvas is drawn again in the dark colors.
  await expect.poll(() => brightness(page)).toBeLessThan(light / 2);
  await post(page, { type: "theme", value: "light" });
  await expect(html).toHaveAttribute("data-theme", "light");
  await expect.poll(() => brightness(page)).toBeGreaterThan(light * 0.9);
  // Malformed messages change nothing.
  await post(page, { type: "theme", value: "sepia" });
  await post(page, "dark");
  await page.waitForTimeout(300);
  await expect(html).toHaveAttribute("data-theme", "light");
});

test("R37: a theme message from any other site is ignored", async ({
  page,
  baseURL,
}) => {
  // Another site's frame on the case study page posts to the demo.
  await page.route("https://evil.example/frame", (route) =>
    route.fulfill({ contentType: "text/html", body: "<!doctype html>" }),
  );
  const demo = await caseStudy(page, baseURL!, {
    after: `<iframe id="other" src="https://evil.example/frame"></iframe>`,
  });
  const other = page.frame({ url: "https://evil.example/frame" })!;
  await other.evaluate(() =>
    window.parent.frames[0]!.postMessage({ type: "theme", value: "dark" }, "*"),
  );
  await page.waitForTimeout(300);
  const html = demo.locator("html");
  await expect(html).not.toHaveAttribute("data-theme", /./);
  // The demo was listening all along: dins.dev's own message lands.
  await post(page, { type: "theme", value: "dark" });
  await expect(html).toHaveAttribute("data-theme", "dark");
});
