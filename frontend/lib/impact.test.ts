import { expect, test } from "vitest";
import { impactHeadline } from "./impact";

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
