import { expect, test } from "vitest";

import { clockTime, count } from "./format";

test("times read as minutes and seconds", () => {
  expect(clockTime(0)).toBe("0:00");
  expect(clockTime(65.9)).toBe("1:05");
  expect(clockTime(1806)).toBe("30:06");
});

test("counts carry thousands separators", () => {
  expect(count(2603)).toBe("2,603");
});
