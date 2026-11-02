import { describe, expect, test } from "vitest";

import { canRunModel } from "./support";

describe("DEMO-05: the model needs WebAssembly and Workers", () => {
  test("both present", () => {
    const scope = {
      WebAssembly: { instantiate: () => undefined },
      Worker: class {},
    };
    expect(canRunModel(scope as unknown as typeof globalThis)).toBe(true);
  });

  test("no WebAssembly, or no Worker, means the fallback", () => {
    expect(
      canRunModel({ Worker: class {} } as unknown as typeof globalThis),
    ).toBe(false);
    expect(
      canRunModel({
        WebAssembly: { instantiate: () => undefined },
      } as unknown as typeof globalThis),
    ).toBe(false);
  });
});
