import { expect, test } from "vitest";
import { checkSetup, fromPct, toPct } from "./setup";
import type { Setup } from "./types";

const base: Setup = { start: "2026-10-12", learn_reference: true, buyers: [], beds: [],
  crop: { name: "Pakcoy", nursery_days: 15, growth_curve: [[0, 5], [7, 15]], spread_ratio: 0.45, germination: 0.85,
    survival: 0.9, seeds_per_gram: 400, grams_per_teaspoon: 3, max_bed_day: 30, max_seedlings_per_sowing: 3000,
    sow_weekdays: [0, 3], lines: [{ id: "regular", min_g: 100, max_g: 140 }] } };

test("valid setup has no problems", () => expect(checkSetup(base)).toEqual([]));
test("duplicate buyer names and unknown lines", () => {
  const b = { name: "A", type: "business" as const, line: "regular", usual_kg_per_week: 1, weekdays: [], min_kg: 0 };
  expect(checkSetup({ ...base, buyers: [b, b] })).toContain("buyer name A is used twice");
  expect(checkSetup({ ...base, buyers: [{ ...b, line: "x" }] })).toContain("buyer A: unknown line x");
});
test("bed after start", () => {
  expect(checkSetup({ ...base, beds: [{ line: "regular", sown_on: "2026-11-01", seedlings: 5 }] }))
    .toContain("bed sown 2026-11-01 is after the start 2026-10-12");
});
test("stretch limit must not be below max", () => {
  const line = { id: "regular", min_g: 100, max_g: 140, stretch_g: 130 };
  expect(checkSetup({ ...base, crop: { ...base.crop, lines: [line] } }))
    .toContain("line regular: 'up to if short' must be at least max g");
  expect(checkSetup({ ...base, crop: { ...base.crop, lines: [{ ...line, stretch_g: null }] } })).toEqual([]);
});
test("weekday, month and year percentages", () => {
  const b = { name: "A", type: "business" as const, line: "regular", usual_kg_per_week: 1, weekdays: [], min_kg: 0 };
  expect(checkSetup({ ...base, buyers: [{ ...b, week_pct: [10, 10, 10, 10, 15, 25, 20] }] })).toEqual([]);
  expect(checkSetup({ ...base, buyers: [{ ...b, week_pct: [10, 10] }] }))
    .toContain("buyer A: weekday % needs 7 numbers (Mon…Sun) adding up to 100");
  expect(checkSetup({ ...base, month_pct: [30, 30, 30, 30] }))
    .toContain("month % needs 4 numbers (dates 1–7, 8–14, 15–21, 22–end) adding up to 100");
  expect(checkSetup({ ...base, year_index: [100] })).toContain("year index needs 12 numbers (Jan…Dec), 0–500");
});

test("shares are typed as % and stored as 0–1, without float noise", () => {
  expect(toPct(0.45)).toBe(45);
  expect(toPct(0.857)).toBe(85.7);
  expect(fromPct(85)).toBe(0.85);
  expect(fromPct(NaN)).toBeNaN();
});

test("germination, survival and spread out of range are named in %", () => {
  const p = checkSetup({ ...base, crop: { ...base.crop, germination: 0, survival: 1.2, spread_ratio: 2.5 } });
  expect(p).toEqual(expect.arrayContaining(["germination must be 1–100%", "survival must be 1–100%",
    "size spread must be 1–200%"]));
});
test("buyer amounts cannot be negative", () => {
  const b = { name: "A", type: "business" as const, line: "regular", usual_kg_per_week: -2, weekdays: [], min_kg: -1 };
  const p = checkSetup({ ...base, buyers: [b] });
  expect(p).toContain("buyer A: usual kg/week must be 0 or more");
  expect(p).toContain("buyer A: min kg must be 0 or more");
});
