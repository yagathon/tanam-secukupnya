import { expect, test } from "vitest";
import { evenWeek, pasteRow } from "./pattern";

test("a pasted row fills every cell only when the count matches", () => {
  expect(pasteRow("32\t27\t22\t19", 4)).toEqual([32, 27, 22, 19]);
  expect(pasteRow("32 27", 4)).toBeNull();
  expect(pasteRow("12", 4)).toBeNull();          // one number = a normal single-cell paste
});
test("an even week spreads 100 over the order days", () => {
  expect(evenWeek([0, 3])).toEqual([50, 0, 0, 50, 0, 0, 0]);
  expect(evenWeek([])).toEqual([14.3, 14.3, 14.3, 14.3, 14.3, 14.3, 14.2]);
});
