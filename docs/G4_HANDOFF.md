# G4 handoff: the Heartbeat demo on dins.dev

For the dins.dev repo (PUB-08, Heartbeat Phase 6 task B7). Din carries this note to that repo; nothing here is applied from the Heartbeat side. It describes what Heartbeat ships and what the site needs so the Heartbeat case study can show the live demo in an iframe. File names on the site side follow the site plans as of dins.dev `d75677f` (`docs/site/plans/M1-pages.md`, `README.md`); the site code does not exist yet, so treat them as pointers.

## What Heartbeat ships

- The full demo at `https://heartbeat.dins.dev/` (Phase 8 adds the custom domain; until then it runs on Worker Preview URLs only, see the last section).
- The embed at `https://heartbeat.dins.dev/?embed=page`: no header, footer, recording picker, position slider, 10-second summary or beat table. It keeps the trace, Play or Pause (plus Previous and Next under reduced motion), Speed, Next irregular beat, Next disagreement, the record and time, the line comparing the browser's labels with the Python results, the legend, the disclaimer line, and "Open the full demo", which opens the full page in a new tab (`target="_blank" rel="noopener"`), so the case study stays open.
- The embed fills whatever box it is given (container queries) and fetches nothing (manifest, trace, ONNX Runtime, model) until it scrolls into view (design call 12). Then it plays, unless the visitor has reduced motion set, where it waits on Play and moves 10 seconds at a time. It has no sound.
- Every response carries this CSP (`web/public/_headers`, checked by `web/e2e/headers.spec.ts`):

  ```
  frame-ancestors 'self' https://dins.dev https://*.dineshddawo.workers.dev
  ```

  and no `X-Frame-Options`, so only dins.dev, Heartbeat itself and Workers on this account's workers.dev subdomain (`dineshddawo`) may frame it. That covers the site's previews (`<branch>-dins-site.dineshddawo.workers.dev`) and its production before launch (`dins-site.dineshddawo.workers.dev`), as the site's M0 plan lays them out.

## 1. Let `demo.src` take the Heartbeat origin

M1's project schema has `demo: { type: "live" | "chart" | "video", src: sitePath }`, and its test rejects outside URLs. Keep that rule and add one exact allowlist for live demos:

```ts
// The only outside origins a live demo may come from (PUB-08).
export const LIVE_DEMO_ORIGINS = ["https://heartbeat.dins.dev"] as const;

const liveDemoSrc = z.url({ protocol: /^https$/ }).refine((value) => {
  const url = new URL(value);
  return (LIVE_DEMO_ORIGINS as readonly string[]).includes(url.origin);
}, "a live demo must be a site path or an allowlisted origin");

demo: z
  .discriminatedUnion("type", [
    z.object({ type: z.literal("live"), src: z.union([sitePath, liveDemoSrc]) }),
    z.object({ type: z.enum(["chart", "video"]), src: sitePath }),
  ])
  .optional(),
```

Tests to add next to the existing `https://evil.test` case: `https://heartbeat.dins.dev/` passes for `live`; `http://heartbeat.dins.dev/`, `https://heartbeat.dins.dev.evil.test/`, `https://evil.test/?u=https://heartbeat.dins.dev` and a `video` with the Heartbeat origin all fail.

Heartbeat's entry: `demo: { type: "live", src: "https://heartbeat.dins.dev/" }`. The case study builds the iframe URL from it by adding `?embed=page`; the "Open the live demo" button keeps the plain URL.

## 2. The iframe on the case study

```astro
<figure class="live-demo">
  <iframe
    src={`${demo.src}?embed=page`}
    title="Heartbeat live demo: a model labels heartbeats from a recording"
    loading="lazy"
    referrerpolicy="strict-origin-when-cross-origin"
  ></iframe>
</figure>
```

```css
.live-demo iframe {
  display: block;
  inline-size: 100%;
  aspect-ratio: 4 / 5;
  border: 0;
}
@media (min-width: 640px) {
  .live-demo iframe {
    aspect-ratio: 16 / 10;
  }
}
```

- `title` is required (axe, WCAG 4.1.2); any wording that says what the frame holds works, within D7's list (no "diagnose", "detects arrhythmia" and so on).
- `loading="lazy"` keeps the document itself from loading early; the embed adds its own wait for the heavy files on top.
- The breakpoint follows Heartbeat settling 5: 16:10 from 640 px, about 4:5 below. The embed was checked in both boxes in the Goal A probe; in a 4:5 box at phone width the trace strip is about 85 px tall (a probe measurement, not a test).
- No `sandbox` is needed. If the site adds one, the demo needs `allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox` (the Worker, the WebAssembly runtime and the new-tab link); that combination is untested.
- Keep the existing "Open the live demo" link under the frame, so a visitor without frames still gets the demo.

## 3. `frame-src` in the site CSP

The site plans use Astro's `security.csp`. Add the origin to `frame-src` (and keep `frame-ancestors` as the site has it; framing dins.dev is a separate question):

```js
// astro.config.mjs, security.csp directives
"frame-src 'self' https://heartbeat.dins.dev",
```

If M3's Turnstile entry already sets `frame-src https://challenges.cloudflare.com`, merge the two into one directive. To try the case study against a Heartbeat preview before Phase 8, a site preview build can add `https://*.dineshddawo.workers.dev` to `frame-src`; production should list only `https://heartbeat.dins.dev`.

## 4. Post the theme to the iframe

The embed follows `prefers-color-scheme` until the site tells it otherwise. It accepts a message only when `event.origin` is exactly `https://dins.dev` and the data is exactly `{ type: "theme", value: "light" | "dark" }`, two keys and nothing else; anything else is ignored (R37, `web/src/lib/theme/messages.ts`).

Post it when the iframe loads and whenever the toggle changes the theme, always to the iframe's own origin, never `"*"`:

```ts
// site/src/lib/theme.ts (next to initThemeToggle)
export function postThemeToFrames(
  theme: "light" | "dark",
  root: ParentNode = document,
) {
  for (const frame of root.querySelectorAll<HTMLIFrameElement>(
    "iframe[data-theme-sync]",
  )) {
    const origin = new URL(frame.src).origin;
    frame.contentWindow?.postMessage({ type: "theme", value: theme }, origin);
  }
}
```

```astro
<iframe data-theme-sync ... ></iframe>
<script>
  import { currentTheme, postThemeToFrames } from "../lib/theme";
  for (const frame of document.querySelectorAll<HTMLIFrameElement>("iframe[data-theme-sync]")) {
    frame.addEventListener("load", () => postThemeToFrames(currentTheme(document)));
  }
</script>
```

and call `postThemeToFrames(next)` from the toggle after it sets `html[data-theme]`. If the visitor never touched the toggle and the site has no `data-theme`, posting the resolved system theme is fine; both sides follow the same media query anyway.

A site preview, or the site's production before launch, runs on `*.dineshddawo.workers.dev`, a different origin, so the embed ignores its messages and follows the system theme there. That is expected; the theme sync starts working at launch on `https://dins.dev`.

## 5. Preview origins

Heartbeat's `frame-ancestors` allows `https://*.dineshddawo.workers.dev`, the account's workers.dev subdomain (checked on Heartbeat's first preview, 2026-11-02): Heartbeat's own Version Preview URLs (`<version>-heartbeat.dineshddawo.workers.dev`, `pr-<number>-heartbeat.dineshddawo.workers.dev`), the site's previews (`<branch>-dins-site.dineshddawo.workers.dev`) and `dins-site.dineshddawo.workers.dev` before launch. A CSP wildcard covers whole labels only, so it cannot be narrowed to `dins-site` previews; every Worker on the subdomain is Din's. If the subdomain is ever renamed in the Cloudflare dashboard, or the site's previews run somewhere else (Pages, another account), tell Din: the pattern lives in `web/public/_headers` and its test, and changing it is a Heartbeat commit.

## How to check it on the site

1. The case study page has no axe violations in light and dark with the iframe present.
2. Below 640 px the frame is about 4:5, from 640 px it is 16:10; the controls inside stay reachable by keyboard (Tab moves from the page into the frame and out again).
3. With the theme toggled, the trace paper switches within a frame or two; toggling back switches it back.
4. In the network panel, nothing from `heartbeat.dins.dev` past the page and its own script and styles (no `manifest.json`, `.wasm`, `.onnx` or `.i16`) loads before the frame scrolls into view.
5. "Open the full demo" opens a new tab and the case study stays where it was.
