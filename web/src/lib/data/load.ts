import { decodeBeats, type BeatsJson, type RecordBeats } from "./beats";
import type { FileEntry, Manifest } from "./manifest";

/** The demo data folder, beside the page (design call 2). */
export const DATA_BASE = new URL("data/", document.baseURI);

export function dataUrl(entry: FileEntry | string): string {
  return new URL(typeof entry === "string" ? entry : entry.name, DATA_BASE)
    .href;
}

async function fetchOk(url: string): Promise<Response> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`);
  return response;
}

export async function fetchManifest(): Promise<Manifest> {
  return (await (await fetchOk(dataUrl("manifest.json"))).json()) as Manifest;
}

const LITTLE_ENDIAN = new Uint8Array(Uint16Array.of(1).buffer)[0] === 1;

/** A record's trace: little-endian int16 at 360 Hz, 200 units per mV. */
export async function fetchTrace(entry: FileEntry): Promise<Int16Array> {
  const buffer = await (await fetchOk(dataUrl(entry))).arrayBuffer();
  if (buffer.byteLength !== entry.bytes) {
    throw new Error(
      `${entry.name}: ${buffer.byteLength} bytes, manifest ${entry.bytes}`,
    );
  }
  if (LITTLE_ENDIAN) return new Int16Array(buffer);
  const view = new DataView(buffer);
  return Int16Array.from({ length: buffer.byteLength / 2 }, (_, i) =>
    view.getInt16(2 * i, true),
  );
}

export async function fetchBeats(entry: FileEntry): Promise<RecordBeats> {
  return decodeBeats(
    (await (await fetchOk(dataUrl(entry))).json()) as BeatsJson,
  );
}
