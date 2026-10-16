import { expect, test } from "vitest";
import { bedsFromSheet, buyersFromSheet, curveFromSheet, parseSheet, parseWeekdays, toNumber, toSheet } from "./sheet";

test("parses TSV and CSV, strips BOM, drops blank lines", () => {
  expect(parseSheet("﻿day\tgrams\n0\t5\n\n7\t15\n")).toEqual([["day", "grams"], ["0", "5"], ["7", "15"]]);
  expect(parseSheet("0,5\r\n7,15")).toEqual([["0", "5"], ["7", "15"]]);
});

test("comma decimals", () => {                                   // Review Focus 1
  expect(toNumber("12,5")).toBe(12.5);
  expect(toNumber("1.234,5")).toBe(1234.5);
  expect(toNumber(" 7 ")).toBe(7);
  expect(toNumber("abc")).toBeNull();
});

test("curve: header skipped, comma decimals, row errors name the row", () => {
  expect(curveFromSheet("day\tgrams\n0\t5\n7\t15,5")).toEqual({ points: [[0, 5], [7, 15.5]] });
  expect(curveFromSheet("0\t5\n7\tx")).toEqual({ error: "row 2: grams is not a number" });
  expect(curveFromSheet("0\t5\n7\t4")).toEqual({ error: "row 2: days and grams must both increase" });
});

test("semicolon CSV from an Indonesian-locale sheet", () => {
  expect(curveFromSheet("0;5\n7;15,5")).toEqual({ points: [[0, 5], [7, 15.5]] });
});

test("buyers: weekdays and defaults", () => {
  const r = buyersFromSheet("Restaurant A\tbusiness\tregular\t30\tTue Fri\t5\nH1\thousehold\tbaby\t1", ["regular", "baby"]);
  expect(r).toEqual({ buyers: [
    { name: "Restaurant A", type: "business", line: "regular", usual_kg_per_week: 30, weekdays: [1, 4], min_kg: 5 },
    { name: "H1", type: "household", line: "baby", usual_kg_per_week: 1, weekdays: [], min_kg: 0 },
  ] });
  expect(buyersFromSheet("A\tshop\tregular\t1", ["regular"])).toEqual({ error: "row 1: type must be business or household" });
});

test("beds", () => {
  expect(bedsFromSheet("regular\t2026-09-20\t800", ["regular"])).toEqual({ beds: [{ line: "regular", sown_on: "2026-09-20", seedlings: 800 }] });
  expect(bedsFromSheet("regular\t20/09/2026\t800", ["regular"])).toEqual({ error: "row 1: sown on must be YYYY-MM-DD" });
});

test("weekdays and copy-back", () => {
  expect(parseWeekdays("tue, FRI")).toEqual([1, 4]);
  expect(parseWeekdays("")).toEqual([]);
  expect(toSheet([["day", "grams"], [0, 5]])).toBe("day\tgrams\n0\t5");
});

test("a header is recognised by its column, not by a word anywhere in the row", () => {
  const r = buyersFromSheet("Day Spa\tbusiness\tregular\t3", ["regular"]);
  expect(r).toEqual({ buyers: [{ name: "Day Spa", type: "business", line: "regular", usual_kg_per_week: 3, weekdays: [], min_kg: 0 }] });
  expect(buyersFromSheet("name\ttype\tline\tusual kg/week\nA\tbusiness\tregular\t3", ["regular"]))
    .toEqual({ buyers: [{ name: "A", type: "business", line: "regular", usual_kg_per_week: 3, weekdays: [], min_kg: 0 }] });
  expect(bedsFromSheet("line\tsown on\tseedlings\nregular\t2026-09-20\t800", ["regular"]))
    .toEqual({ beds: [{ line: "regular", sown_on: "2026-09-20", seedlings: 800 }] });
});
