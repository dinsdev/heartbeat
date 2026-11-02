import { expect, test, type Page } from "@playwright/test";

import { CHOSEN_NOTE, TRAINING_NOTE } from "../src/lib/notes";
import { demoManifest } from "./manifest";

// Phase 7 design call 7, in both page modes: a DS1 build shows the
// training-patient note and never DEMO-09's line; a DS2 build shows DEMO-09's
// line naming its default record and never the training-patient note.

async function expectNotes(page: Page, split: "DS1" | "DS2", record: string) {
  await expect(page.getByRole("button", { name: "Pause" })).toBeVisible();
  const training = page.getByTestId("training-note");
  const chosen = page.getByTestId("chosen-note");
  if (split === "DS1") {
    await expect(training).toHaveText(TRAINING_NOTE);
    await expect(chosen).toHaveCount(0);
  } else {
    await expect(chosen).toHaveText(CHOSEN_NOTE(record));
    await expect(training).toHaveCount(0);
  }
}

for (const [mode, path] of [
  ["full page", "/"],
  ["embed", "/?embed=page"],
] as const) {
  test(`the ${mode} shows the notes its split calls for`, async ({
    page,
    request,
  }) => {
    const manifest = await demoManifest(request);
    await page.goto(path);
    await expectNotes(page, manifest.split, manifest.default.record);
  });
}
