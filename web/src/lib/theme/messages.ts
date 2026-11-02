// R37, settling 5: the case study on dins.dev posts the theme it shows so the
// embed matches it. Anything from another origin, or of any other shape, is
// ignored.

export type Theme = "light" | "dark";

export const THEME_ORIGIN = "https://dins.dev";

/** The theme a message asks for, or undefined when it must be ignored. */
export function themeFromMessage(
  origin: string,
  data: unknown,
): Theme | undefined {
  if (origin !== THEME_ORIGIN) return undefined;
  if (typeof data !== "object" || data === null || Array.isArray(data)) {
    return undefined;
  }
  const keys = Object.keys(data);
  if (keys.length !== 2 || !keys.includes("type") || !keys.includes("value")) {
    return undefined;
  }
  const { type, value } = data as { type: unknown; value: unknown };
  if (type !== "theme") return undefined;
  return value === "light" || value === "dark" ? value : undefined;
}

/** Calls `apply` for each accepted message; returns the function that stops. */
export function listenForTheme(
  target: EventTarget,
  apply: (theme: Theme) => void,
): () => void {
  const onMessage = (event: Event) => {
    const { origin, data } = event as MessageEvent<unknown>;
    const theme = themeFromMessage(origin, data);
    if (theme) apply(theme);
  };
  target.addEventListener("message", onMessage);
  return () => target.removeEventListener("message", onMessage);
}
