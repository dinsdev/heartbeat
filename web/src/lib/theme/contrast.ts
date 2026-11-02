// WCAG 2.2 relative luminance and contrast ratio, and a reader for the
// custom properties of the light and dark blocks in a token file.

function channel(value: number): number {
  const c = value / 255;
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

function rgb(hex: string): [number, number, number] {
  const match = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex);
  if (!match) throw new Error(`not a #RRGGBB color: ${hex}`);
  return [
    parseInt(match[1]!, 16),
    parseInt(match[2]!, 16),
    parseInt(match[3]!, 16),
  ];
}

export function luminance(hex: string): number {
  const [r, g, b] = rgb(hex);
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

export function contrastRatio(a: string, b: string): number {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (light! + 0.05) / (dark! + 0.05);
}

/** Hue in degrees and HSL saturation from 0 to 1. */
export function hsl(hex: string): { h: number; s: number } {
  const [r, g, b] = rgb(hex).map((v) => v / 255) as [number, number, number];
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;
  const d = max - min;
  if (d === 0) return { h: 0, s: 0 };
  const s = d / (1 - Math.abs(2 * l - 1));
  let h: number;
  if (max === r) h = ((g - b) / d) % 6;
  else if (max === g) h = (b - r) / d + 2;
  else h = (r - g) / d + 4;
  return { h: (h * 60 + 360) % 360, s };
}

type Properties = Record<string, string>;

function properties(block: string): Properties {
  const out: Properties = {};
  for (const match of block.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) {
    out[match[1]!] = match[2]!.trim();
  }
  return out;
}

function blockAfter(css: string, selector: string, from = 0): string {
  const start = css.indexOf(selector, from);
  if (start < 0) throw new Error(`no ${selector} block`);
  const open = css.indexOf("{", start);
  const close = css.indexOf("}", open);
  return css.slice(open + 1, close);
}

/**
 * The light `:root` block, the dark `:root[data-theme="dark"]` block and the
 * dark block inside `@media (prefers-color-scheme: dark)`, as the vendored
 * tokens lay them out.
 */
export function themeBlocks(css: string): {
  light: Properties;
  dark: Properties;
  darkMedia: Properties;
} {
  const media = css.indexOf("@media (prefers-color-scheme: dark)");
  if (media < 0) throw new Error("no prefers-color-scheme block");
  return {
    light: properties(blockAfter(css, ":root {")),
    dark: properties(blockAfter(css, ':root[data-theme="dark"]')),
    darkMedia: properties(
      blockAfter(css, ':root:not([data-theme="light"])', media),
    ),
  };
}
