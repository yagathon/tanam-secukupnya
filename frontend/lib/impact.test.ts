import { expect, test } from "vitest";
import { bedBarName, impactHeadline } from "./impact";

const row = (seedlings: number, waste_plants: number, delivered_kg = 117.3) => ({
  beds: 1, seedlings, harvested_plants: 0, lost_plants: 0, waste_plants, in_field_plants: 0, waste_pct: 0, delivered_kg,
});

// logged_kg also holds what the setup beds gave; the comparison is the beds sown since, so it uses delivered_kg
test("headline compares Tanam with the old habit at the same deliveries", () => {
  expect(impactHeadline({ tanam: row(5050, 0), habit: row(8000, 1014) },
    { logged_kg: 344.5, habit_kg: 344.5, habit_short_kg: 0 }, 1000))
    .toBe("Same 117.3 kg delivered with 2,950 fewer seedlings and 1,014 fewer plants wasted than sowing 1,000 every week.");
});

test("headline says so honestly when Tanam wasted more, and when the habit fell short", () => {
  expect(impactHeadline({ tanam: row(9000, 50, 100), habit: row(8000, 20, 96) },
    { logged_kg: 100, habit_kg: 96, habit_short_kg: 4 }, 1000))
    .toBe("100.0 kg delivered with 1,000 more seedlings and 30 more plants wasted than sowing 1,000 every week; "
      + "that habit would also have missed 4.0 kg.");
});

const bed = (group: "before" | "tanam" | "habit", label: string, line = "baby") => ({
  id: "x", label, line, sown_on: "2026-10-12", group, seedlings: 1000, harvested: 600, lost: 0, waste: 300,
  growing: 0, closed_on: "2026-11-20",
});

// the habit's beds are not the farm's beds: they are named by the Monday they were sown
test("bar names: farm beds by label (setup beds starred), habit beds by sowing day and line", () => {
  expect(bedBarName(bed("tanam", "Bed 6"), 1)).toBe("Bed 6");
  expect(bedBarName(bed("before", "Bed 1"), 1)).toBe("Bed 1*");
  expect(bedBarName(bed("habit", "Bed 9"), 1)).toBe("12 Oct");
  expect(bedBarName(bed("habit", "Bed 9", "regular"), 2)).toBe("12 Oct regular");
});
