import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Locator, type Page } from "@playwright/test";

// R35: axe finds nothing on the full page or the embed, light or dark, with
// reduced motion on or off; the projects add desktop and phone. R36: every
// control is reached and worked by keyboard alone, shows the focus ring, and
// is at least 24 by 24 CSS pixels (WCAG 2.5.8).

const MODES = [
  { name: "full page", path: "/" },
  { name: "embed", path: "/?embed=page" },
] as const;

async function ready(page: Page, path: string) {
  await page.goto(path);
  await expect(
    page.getByText(/Labels match the Python results: [\d,]+ of [\d,]+ beats/),
  ).toBeVisible();
}

for (const mode of MODES) {
  for (const colorScheme of ["light", "dark"] as const) {
    for (const reducedMotion of ["no-preference", "reduce"] as const) {
      test.describe(`${mode.name}, ${colorScheme}, motion ${reducedMotion}`, () => {
        test.use({ colorScheme, reducedMotion });

        test(`R35: axe finds no violations (${mode.name}, ${colorScheme}, motion ${reducedMotion})`, async ({
          page,
        }) => {
          await ready(page, mode.path);
          const { violations } = await new AxeBuilder({ page }).analyze();
          expect(
            violations.map((v) => ({
              id: v.id,
              targets: v.nodes.map((n) => n.target.join(" ")),
            })),
          ).toEqual([]);
        });
      });
    }
  }
}

/**
 * The key that moves focus to the next control. Safari's Tab visits only form
 * fields unless its setting says otherwise; its users reach links and buttons
 * with Option+Tab.
 */
function tabKey(page: Page): string {
  return page.context().browser()!.browserType().name() === "webkit"
    ? "Alt+Tab"
    : "Tab";
}

/** Tab once and expect `target` to hold the focus with a visible ring. */
async function tabTo(page: Page, target: Locator) {
  await page.keyboard.press(tabKey(page));
  await expect(target).toBeFocused();
  const ring = await target.evaluate((el) => {
    const style = getComputedStyle(el);
    return { style: style.outlineStyle, width: parseFloat(style.outlineWidth) };
  });
  expect(ring.style).toBe("solid");
  expect(ring.width).toBeGreaterThanOrEqual(2);
}

async function targetsAreLargeEnough(scope: Locator) {
  const controls = scope.locator("button, select, input, a");
  const n = await controls.count();
  expect(n).toBeGreaterThan(0);
  for (let i = 0; i < n; i++) {
    const control = controls.nth(i);
    const box = (await control.boundingBox())!;
    const name = await control.evaluate(
      (el) => el.getAttribute("aria-label") ?? el.textContent?.trim(),
    );
    expect(box.width, `${name} width`).toBeGreaterThanOrEqual(24);
    expect(box.height, `${name} height`).toBeGreaterThanOrEqual(24);
  }
}

function controls(page: Page, reduced: boolean) {
  return [
    page.getByRole("button", { name: /^(Play|Pause)$/ }),
    ...(reduced
      ? [
          page.getByRole("button", { name: "Previous 10 seconds" }),
          page.getByRole("button", { name: "Next 10 seconds" }),
        ]
      : []),
    page.getByLabel("Speed"),
    page.getByRole("button", { name: "Next irregular beat" }),
    page.getByRole("button", { name: "Next disagreement" }),
  ];
}

for (const reducedMotion of ["no-preference", "reduce"] as const) {
  const reduced = reducedMotion === "reduce";

  test.describe(`motion ${reducedMotion}`, () => {
    test.use({ reducedMotion });

    test(`R36: the full page is walked and worked by keyboard (motion ${reducedMotion})`, async ({
      page,
    }) => {
      await ready(page, "/");
      await tabTo(page, page.getByRole("link", { name: "dins" }).first());
      for (const control of controls(page, reduced)) await tabTo(page, control);
      await tabTo(page, page.getByLabel("Recording"));
      const slider = page.getByRole("slider", { name: "Position" });
      await tabTo(page, slider);
      // Then on through the about text to the footer, with no trap.
      const github = page.getByRole("link", { name: "GitHub" });
      for (let i = 0; i < 12; i++) {
        await page.keyboard.press(tabKey(page));
        if (await github.evaluate((el) => el === document.activeElement)) break;
      }
      await expect(github).toBeFocused();

      // Worked by keyboard alone.
      const play = page.getByRole("button", { name: /^(Play|Pause)$/ });
      await play.focus();
      const before = await play.textContent();
      await page.keyboard.press("Space");
      await expect(play).not.toHaveText(before!);
      if ((await play.textContent())!.includes("Pause")) {
        await page.keyboard.press("Enter");
        await expect(play).toHaveText(/Play/);
      }
      await page.getByRole("button", { name: "Next irregular beat" }).focus();
      await page.keyboard.press("Enter");
      await expect(page.getByTestId("jump-note")).toHaveText(/^Beat at /);
      await slider.focus();
      const at = Number(await slider.inputValue());
      await page.keyboard.press("ArrowRight");
      await expect(slider).toHaveValue(String(at + 5));
      if (reduced) {
        // Next shows the following 10-second page.
        await page.getByRole("button", { name: "Next 10 seconds" }).focus();
        const viewEnd = async () =>
          Number(
            await page.locator("[data-view-end]").getAttribute("data-view-end"),
          );
        // The slider left the playhead mid-page; let that frame draw first.
        const from = Math.ceil((at + 5) / 10) * 10;
        await expect.poll(viewEnd).toBe(from);
        await page.keyboard.press("Enter");
        await expect.poll(viewEnd).toBe(from + 10);
      }
      await targetsAreLargeEnough(page.getByTestId("demo-panel"));
    });

    test(`R36: the embed is walked and worked by keyboard (motion ${reducedMotion})`, async ({
      page,
    }) => {
      await ready(page, "/?embed=page");
      for (const control of controls(page, reduced)) await tabTo(page, control);
      await tabTo(page, page.getByRole("link", { name: "Open the full demo" }));
      await page.getByRole("button", { name: "Next disagreement" }).focus();
      await page.keyboard.press("Enter");
      await expect(page.getByTestId("jump-note")).toHaveText(/^Beat at /);
      await targetsAreLargeEnough(page.getByTestId("demo-panel"));
    });
  });
}
