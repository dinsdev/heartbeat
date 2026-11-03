import { expect, type APIRequestContext } from "@playwright/test";

import type { Manifest, RecordEntry } from "../src/lib/data/manifest";

// Phase 7 design call 7: specs read their records from the built
// `manifest.json`, so the same suite runs on the DS1 and the DS2 build. Each
// helper fails, never skips, when the manifest has no record that fits, so a
// spec cannot pass quietly on the other split.

/** Records per split, from `manifests/splits.toml` (202 is excluded from DS2). */
export const SPLIT_SIZES = { DS1: 22, DS2: 21 } as const;

export async function demoManifest(
  request: APIRequestContext,
): Promise<Manifest> {
  const response = await request.get("/data/manifest.json");
  expect(response.ok(), "data/manifest.json").toBe(true);
  const manifest = (await response.json()) as Manifest;
  expect(Object.keys(SPLIT_SIZES)).toContain(manifest.split);
  expect(manifest.records).toHaveLength(SPLIT_SIZES[manifest.split]);
  return manifest;
}

export function defaultEntry(manifest: Manifest): RecordEntry {
  const entry = manifest.records.find(
    (r) => r.record === manifest.default.record,
  );
  if (!entry) throw new Error(`default ${manifest.default.record} not listed`);
  return entry;
}

/** The first record in picker order that is not the default. */
export function otherRecord(manifest: Manifest): string {
  const entry = manifest.records.find(
    (r) => r.record !== manifest.default.record,
  );
  if (!entry) throw new Error("the manifest lists only the default record");
  return entry.record;
}

/** The first record whose kept beats include no expert S, V or F. */
export function quietRecord(manifest: Manifest): string {
  const entry = manifest.records.find(
    ({ counts }) => counts.S + counts.V + counts.F === 0,
  );
  if (!entry) throw new Error(`no ${manifest.split} record without S, V or F`);
  return entry.record;
}

/** The picker's text for a record, written out here, not taken from the app. */
export function optionText({ record, counts }: RecordEntry): string {
  const n = (x: number) => x.toLocaleString("en");
  return `Record ${record}: ${n(counts.N)} N, ${n(counts.S)} S, ${n(counts.V)} V, ${n(counts.F)} F`;
}
