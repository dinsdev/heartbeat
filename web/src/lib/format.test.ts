import { expect, test } from "vitest";

import { clockTenths, clockTime, count } from "./format";

test("times read as minutes and seconds", () => {
  expect(clockTime(0)).toBe("0:00");
  expect(clockTime(65.9)).toBe("1:05");
  expect(clockTime(1806)).toBe("30:06");
});

test("counts carry thousands separators", () => {
  expect(count(2603)).toBe("2,603");
});

test("beat times carry tenths of a second", () => {
  expect(clockTenths(0)).toBe("0:00.0");
  expect(clockTenths(65.34)).toBe("1:05.3");
  expect(clockTenths(59.96)).toBe("1:00.0");
});
