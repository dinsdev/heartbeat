import { SPAN_S } from "../trace/geometry";

// DEMO-14: under reduced motion the trace shows fixed 10-second pages, the
// same span as the view, so a page is the view with its right edge on a
// multiple of 10 seconds (or the end of the recording).
export const PAGE_S = SPAN_S;

function clamp(seconds: number, min: number, duration: number): number {
  return Math.min(Math.max(seconds, min), duration);
}

/** The right edge of the page holding the playhead. */
export function pageEnd(position: number, min: number, duration: number): number {
  return clamp(Math.ceil(position / PAGE_S) * PAGE_S, min, duration);
}

/** The right edge `pages` pages after (or, negative, before) the current one. */
export function stepPage(
  position: number,
  pages: number,
  min: number,
  duration: number,
): number {
  const current = pageEnd(position, min, duration);
  return pageEnd(current + pages * PAGE_S, min, duration);
}
