/**
 * Whether this page can run the model at all: WebAssembly and module Workers.
 * Without them the demo goes straight to the labeled fallback (DEMO-05).
 */
export function canRunModel(scope: typeof globalThis = globalThis): boolean {
  const wasm = (scope as { WebAssembly?: { instantiate?: unknown } })
    .WebAssembly;
  return (
    typeof wasm === "object" &&
    typeof wasm.instantiate === "function" &&
    typeof (scope as { Worker?: unknown }).Worker === "function"
  );
}
