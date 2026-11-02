import { describe, expect, test } from "vitest";

import { listenForTheme, themeFromMessage } from "./messages";

// R37, settling 5: the case study on dins.dev tells the embed which theme it
// shows. Only that origin and only the exact message shape change anything.

const DINS = "https://dins.dev";

describe("R37: theme messages", () => {
  test("R37: a well-formed message from https://dins.dev sets the theme", () => {
    expect(themeFromMessage(DINS, { type: "theme", value: "dark" })).toBe(
      "dark",
    );
    expect(themeFromMessage(DINS, { type: "theme", value: "light" })).toBe(
      "light",
    );
  });

  test("R37: messages from any other origin are ignored", () => {
    for (const origin of [
      "https://evil.example",
      "http://dins.dev",
      "https://www.dins.dev",
      "https://dins.dev.evil.example",
      "https://heartbeat.dins.dev",
      "null",
      "",
    ]) {
      expect(themeFromMessage(origin, { type: "theme", value: "dark" })).toBe(
        undefined,
      );
    }
  });

  test("R37: malformed messages are ignored", () => {
    for (const data of [
      undefined,
      null,
      "dark",
      42,
      [],
      { type: "theme" },
      { type: "theme", value: "blue" },
      { type: "theme", value: "Dark" },
      { type: "Theme", value: "dark" },
      { type: "color", value: "dark" },
      { value: "dark" },
      { type: "theme", value: "dark", extra: 1 },
      { type: "theme", value: ["dark"] },
    ]) {
      expect(themeFromMessage(DINS, data)).toBe(undefined);
    }
  });

  test("R37: the listener applies only accepted messages, and stops when removed", () => {
    const target = new EventTarget();
    const applied: string[] = [];
    const stop = listenForTheme(target, (theme) => applied.push(theme));
    const send = (origin: string, data: unknown) =>
      target.dispatchEvent(new MessageEvent("message", { origin, data }));
    send("https://evil.example", { type: "theme", value: "dark" });
    send(DINS, { type: "theme", value: "sepia" });
    send(DINS, { type: "theme", value: "dark" });
    send(DINS, { type: "theme", value: "light" });
    stop();
    send(DINS, { type: "theme", value: "dark" });
    expect(applied).toEqual(["dark", "light"]);
  });
});
