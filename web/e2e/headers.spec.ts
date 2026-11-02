import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

import { hostAt, unhost } from "./host";

test.afterEach(({ page }) => unhost(page));

// R40, design call 16: the built `dist/_headers` that Cloudflare applies to
// every response. The webServer builds `dist/` before these run.

const DIST = fileURLToPath(new URL("../dist/", import.meta.url));

const CSP = [
  "default-src 'self'",
  "script-src 'self' 'wasm-unsafe-eval'",
  "worker-src 'self'",
  "connect-src 'self'",
  "img-src 'self' data:",
  "style-src 'self'",
  "font-src 'self'",
  "object-src 'none'",
  "base-uri 'none'",
  "form-action 'none'",
  "frame-ancestors 'self' https://dins.dev https://*.dineshddawo.workers.dev",
].join("; ");

const IMMUTABLE = "public, max-age=31536000, immutable";

type Rules = Map<string, Map<string, string>>;

/** The `_headers` rules: URL pattern to header name (lower case) and value. */
function parse(text: string): Rules {
  const rules: Rules = new Map();
  let current: Map<string, string> | undefined;
  for (const line of text.split("\n")) {
    if (line.trim() === "" || line.trim().startsWith("#")) continue;
    if (!/^\s/.test(line)) {
      current = new Map();
      rules.set(line.trim(), current);
      continue;
    }
    const at = line.indexOf(":");
    current!.set(
      line.slice(0, at).trim().toLowerCase(),
      line.slice(at + 1).trim(),
    );
  }
  return rules;
}

/** Cloudflare's matching: `*` takes anything, `:name` anything but `/`. */
function matches(pattern: string, path: string): boolean {
  const source = pattern
    .split(/(\*|:[A-Za-z]\w*)/)
    .map((part) =>
      part === "*"
        ? ".*"
        : part.startsWith(":")
          ? "[^/]+"
          : part.replace(/[.+?^${}()|[\]\\]/g, "\\$&"),
    )
    .join("");
  return new RegExp(`^${source}$`).test(path);
}

function files(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) =>
    entry.isDirectory()
      ? files(join(dir, entry.name))
      : ["/" + relative(DIST, join(dir, entry.name))],
  );
}

const rules = () => parse(readFileSync(join(DIST, "_headers"), "utf8"));

test("R40: every response carries the CSP with frame-ancestors and 'wasm-unsafe-eval'", () => {
  const all = rules().get("/*")!;
  expect(all.get("content-security-policy")).toBe(CSP);
  expect(all.get("content-security-policy")).toContain(
    "frame-ancestors 'self' https://dins.dev https://*.dineshddawo.workers.dev",
  );
  expect(all.get("content-security-policy")).toContain("'wasm-unsafe-eval'");
  expect(all.get("x-content-type-options")).toBe("nosniff");
  expect(all.get("referrer-policy")).toBe("strict-origin-when-cross-origin");
});

test("R40: no rule sets X-Frame-Options, which would block the case study", () => {
  for (const headers of rules().values()) {
    expect(headers.has("x-frame-options")).toBe(false);
  }
});

test("R40: only content-hashed files are cached as immutable", () => {
  const immutable = [...rules()]
    .filter(([, headers]) => headers.get("cache-control") === IMMUTABLE)
    .map(([pattern]) => pattern);
  expect(immutable.length).toBeGreaterThan(0);
  const built = files(DIST).filter((path) => path !== "/_headers");
  // Vite's `name-HASH.ext` and the demo data's `name.HASH.ext`.
  const hashed = /[-.][A-Za-z0-9_-]{8}\.[a-z0-9]+(\.[a-z0-9]+)?$/;
  const cached = built.filter((path) =>
    immutable.some((pattern) => matches(pattern, path)),
  );
  for (const path of cached) expect(path).toMatch(hashed);
  for (const path of ["/index.html", "/data/manifest.json", "/"]) {
    expect(cached).not.toContain(path);
    expect(immutable.some((pattern) => matches(pattern, path))).toBe(false);
  }
  // Every hashed file is cached: the runtime, model, traces and beats.
  for (const path of built.filter(
    (p) => hashed.test(p) && p !== "/index.html",
  )) {
    expect(cached).toContain(path);
  }
});

test("the preview serves the same policy, and the page runs under it with no violation", async ({
  page,
}) => {
  const violations: string[] = [];
  await page.exposeFunction("__violation", (text: string) =>
    violations.push(text),
  );
  await page.addInitScript(() => {
    document.addEventListener("securitypolicyviolation", (event) => {
      (window as unknown as { __violation: (t: string) => void }).__violation(
        `${event.violatedDirective} ${event.blockedURI}`,
      );
    });
  });
  const response = await page.goto("/");
  expect(response!.headers()["content-security-policy"]).toBe(CSP);
  // The model runs in the Worker: the labels match the Python results.
  await expect(
    page.getByText(/Labels match the Python results: [\d,]+ of [\d,]+ beats/),
  ).toBeVisible();
  await expect(page.getByTestId("demo")).toHaveAttribute(
    "data-label-source",
    "browser",
  );
  await page.getByRole("button", { name: "Next irregular beat" }).click();
  await page.waitForTimeout(500);
  expect(violations).toEqual([]);
});

// The site's previews and its production before launch run on this account's
// workers.dev subdomain (dins.dev M0 plan: <branch>-dins-site.<subdomain>).
for (const origin of [
  "https://dins.dev",
  "https://feat-case-study-dins-site.dineshddawo.workers.dev",
]) {
  test(`R40: ${origin} may frame the demo`, async ({ page, baseURL }) => {
    const allowed = await hostAt(page, origin, baseURL!);
    await expect(allowed.locator("main")).toBeAttached();
  });
}

// Another site, and the `din` subdomain design call 16 first assumed, which
// belongs to some other account.
for (const origin of [
  "https://evil.example",
  "https://dins-site.din.workers.dev",
]) {
  test(`R40: ${origin} may not frame the demo`, async ({ page, baseURL }) => {
    const blocked = await hostAt(page, origin, baseURL!);
    await page.waitForTimeout(1500);
    await expect(blocked.locator("main")).toHaveCount(0);
  });
}
