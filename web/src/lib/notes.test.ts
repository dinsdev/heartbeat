import { describe, expect, it } from "vitest";

import type { Manifest } from "./data/manifest";
import { CHOSEN_NOTE, splitNotes, TRAINING_NOTE } from "./notes";

// Phase 7 design call 7: the notes follow the manifest's split. DS1 shows the
// training-patient note only; DS2 shows DEMO-09's line only, naming the
// default record from the manifest.

function planted(split: "DS1" | "DS2", record: string): Manifest {
  return {
    split,
    default: { record, start_s: 20 },
  } as unknown as Manifest;
}

describe("splitNotes", () => {
  it("shows the training-patient note on DS1, and no DEMO-09 line", () => {
    const notes = splitNotes(planted("DS1", "223"));
    expect(notes).toEqual([{ kind: "training", text: TRAINING_NOTE }]);
  });

  it("shows DEMO-09's line on DS2, and no training-patient note", () => {
    const notes = splitNotes(planted("DS2", "200"));
    expect(notes).toEqual([{ kind: "chosen", text: CHOSEN_NOTE("200") }]);
    expect(notes.map((n) => n.text).join(" ")).not.toContain(TRAINING_NOTE);
  });

  it("names the manifest's default record, not a fixed one", () => {
    const [note] = splitNotes(planted("DS2", "212"));
    expect(note!.text).toMatch(/^Record 212 /);
    expect(note!.text).not.toContain("200");
  });

  it("says the record was picked before testing for its irregular beats (DEMO-09)", () => {
    const text = CHOSEN_NOTE("200");
    expect(text).toContain("before");
    expect(text).toContain("irregular beats");
  });

  it("refuses a split it does not know", () => {
    expect(() => splitNotes(planted("DS3" as unknown as "DS1", "200"))).toThrow(
      /DS3/,
    );
  });
});
