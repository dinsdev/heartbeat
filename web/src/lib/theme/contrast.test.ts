import { describe, expect, test } from "vitest";

import brandCss from "../../../vendor/brand/tokens.css?raw";
import heartbeatCss from "../../styles/heartbeat-tokens.css?raw";
import { contrastRatio, hsl, themeBlocks } from "./contrast";

// D6, WCAG 1.4.11: class marks at least 3:1 against the paper.
const MIN_CONTRAST = 3;
const CLASS_TOKENS = [
  "--hb-class-n",
  "--hb-class-s",
  "--hb-class-v",
  "--hb-class-f",
  "--hb-class-q",
];

const brand = themeBlocks(brandCss);
const heartbeat = themeBlocks(heartbeatCss);

describe("R34: class colors at least 3:1 in light and dark", () => {
  test("R34: the contrast formula gives WCAG's known values", () => {
    expect(contrastRatio("#000000", "#FFFFFF")).toBeCloseTo(21, 6);
    expect(contrastRatio("#FFFFFF", "#FFFFFF")).toBeCloseTo(1, 6);
    // BRAND.md: light ink 15.9, muted 6.8, accent 5.6, amber 2.0 on paper.
    expect(contrastRatio("#12181C", "#F4F1EA")).toBeCloseTo(15.9, 1);
    expect(contrastRatio("#4A555C", "#F4F1EA")).toBeCloseTo(6.8, 1);
    expect(contrastRatio("#E0A04A", "#F4F1EA")).toBeCloseTo(2.0, 1);
  });

  test("R34: the token blocks are read per theme", () => {
    expect(brand.light["--color-paper"]?.toUpperCase()).toBe("#F4F1EA");
    expect(brand.dark["--color-paper"]?.toUpperCase()).toBe("#1F1E1C");
    expect(heartbeat.light["--hb-class-n"]).not.toBe(
      heartbeat.dark["--hb-class-n"],
    );
  });

  for (const theme of ["light", "dark"] as const) {
    test(`R34: every class color passes 3:1 on the ${theme} paper`, () => {
      const paper = brand[theme]["--color-paper"]!;
      expect(paper).toMatch(/^#[0-9A-Fa-f]{6}$/);
      for (const token of CLASS_TOKENS) {
        const color = heartbeat[theme][token];
        expect(color, `${token} in ${theme}`).toMatch(/^#[0-9A-Fa-f]{6}$/);
        expect(
          contrastRatio(color!, paper),
          `${token} ${color} in ${theme}`,
        ).toBeGreaterThanOrEqual(MIN_CONTRAST);
      }
    });

    test(`R34: teal is never a class color (${theme})`, () => {
      const accent = brand[theme]["--color-accent"]!.toLowerCase();
      for (const token of CLASS_TOKENS) {
        const color = heartbeat[theme][token]!;
        expect(color.toLowerCase()).not.toBe(accent);
        const { h, s } = hsl(color);
        // A saturated color in the teal hues would read as interactive.
        expect(s < 0.25 || h < 150 || h > 210, `${token} ${color}`).toBe(true);
      }
    });
  }

  test("R34: the media query and the data-theme block give the same dark colors", () => {
    expect(heartbeat.darkMedia).toEqual(heartbeat.dark);
    expect(brand.darkMedia).toEqual(brand.dark);
  });
});
