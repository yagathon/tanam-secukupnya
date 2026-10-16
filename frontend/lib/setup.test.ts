import { expect, test } from "vitest";
import { checkSetup } from "./setup";
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
