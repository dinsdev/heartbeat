import type { Manifest } from "./data/manifest";

/** Shown on DS1 builds only: these patients trained the model (DEMO-17). */
export const TRAINING_NOTE =
  "Development build: these are training patients the model has already seen, so its labels here look better than they would on new patients.";

/**
 * DEMO-09, shown on DS2 builds only (Phase 7 design call 7). Drafted in Din's
 * voice for Din's review in the pull request.
 */
export const CHOSEN_NOTE = (record: string) =>
  `Record ${record} opens first. I picked it before testing, with a rule that reads only the expert labels, because it has many irregular beats.`;

export interface Note {
  kind: "training" | "chosen";
  text: string;
}

/** The notes the manifest's split calls for, in both page modes. */
export function splitNotes(
  manifest: Pick<Manifest, "split" | "default">,
): Note[] {
  switch (manifest.split) {
    case "DS1":
      return [{ kind: "training", text: TRAINING_NOTE }];
    case "DS2":
      return [{ kind: "chosen", text: CHOSEN_NOTE(manifest.default.record) }];
    default:
      throw new Error(`unknown split ${String(manifest.split)}`);
  }
}
