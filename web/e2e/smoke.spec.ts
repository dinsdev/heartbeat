import { expect, test } from "@playwright/test";

test("smoke: the built page shows the heading", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { level: 1, name: "Heartbeat" }),
  ).toBeVisible();
});
