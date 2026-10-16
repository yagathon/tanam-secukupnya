import { expect, test } from "vitest";
import { yearCurve } from "./season";
import type { Setup } from "./types";

// Expected values come from the engine: app.demand.season_factor × app.sandbox._week (Python).
const setup = {
  start: "2026-10-12", month_pct: [32, 27, 22, 19], year_index: [115, 100, 100, 100, 100, 100, 85, 85, 100, 100, 100, 115],
  buyers: [
    { name: "A", type: "business", line: "regular", usual_kg_per_week: 70, week_pct: [10, 10, 10, 10, 15, 25, 20], weekdays: [], min_kg: 0 },
    { name: "H", type: "household", line: "baby", usual_kg_per_week: 3, weekdays: [1, 4], min_kg: 0 },
  ],
} as unknown as Setup;

test("a year of days from the start, the three patterns multiplied as the engine does", () => {
  const rows = yearCurve(setup);
  expect(rows).toHaveLength(365);
  expect(rows[0].day).toBe("2026-10-12");
  const at = (d: string) => rows.find((r) => r.day === d) ?? yearCurve({ ...setup, start: "2026-07-01" }).find((r) => r.day === d)!;
  expect(at("2026-10-13").kg).toEqual({ regular: 7.56, baby: 1.62 });
  expect(at("2026-12-05").kg).toEqual({ regular: 25.76, baby: 0 });
  expect(at("2026-07-23").kg.regular).toBe(4.522);
});

test("no season set = flat month and year", () => {
  const rows = yearCurve({ ...setup, month_pct: undefined, year_index: undefined });
  expect(rows[5].kg.regular).toBe(17.5);              // Sat 17 Oct: 70 × 25%
});
