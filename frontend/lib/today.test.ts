import { expect, test } from "vitest";
import { sowLineDefault, todayActions } from "./today";
import type { TodayLine } from "./types";

const sow = { day: "2026-10-12", weekday: "Mon", seedlings: 900, seeds_g: 2.6, teaspoons: 0.9, shortfall_ahead_kg: 0 };
const base: TodayLine = { line: "regular", need_kg: 10, ceiling_kg: 10, send_kg: 10, short_kg: 0, rotated: [], sow,
  done: { sown: false, harvested: false }, cover_pct: 100, sellable_from: null,
  harvest_plan: [{ batch: "regular-2026-09-01-1", label: "Bed 1", kg: 6, avg_g: 128, sampled: true },
    { batch: "regular-2026-09-05-2", label: "Bed 2", kg: 4, avg_g: 104, sampled: false }] };

test("harvest action names each bed, its predicted size and basis, and prefills the form", () => {
  const h = todayActions(base, "2026-10-12").find((a) => a.kind === "harvest")!;
  expect(h.title).toBe("Harvest 10.0 kg for tomorrow");
  expect(h.lines).toEqual(["Bed 1: 6.00 kg · ~128 g a plant (your sample)", "Bed 2: 4.00 kg · ~104 g a plant (growth curve)"]);
  expect(h.prefill).toEqual([{ label: "Bed 1", kind: "harvest", form: { batch: "regular-2026-09-01-1", kg: "6" } },
    { label: "Bed 2", kind: "harvest", form: { batch: "regular-2026-09-05-2", kg: "4" } }]);
  expect(h.done).toBe(false);
});

test("sow on a sowing day prefills seedlings; otherwise it says when", () => {
  const s = todayActions(base, "2026-10-12").find((a) => a.kind === "sow")!;
  expect(s.title).toBe("Sow 900 seedlings");
  expect(s.prefill).toEqual([{ label: "Log sowing", kind: "sow", form: { line: "regular", seedlings: "900" } }]);
  const later = todayActions({ ...base, sow: { ...sow, day: "2026-10-15", weekday: "Thu" } }, "2026-10-12")
    .find((a) => a.kind === "sow")!;
  expect(later.title).toBe("Next sowing Thu 15 Oct: ~900 seedlings");
  expect(later.prefill).toEqual([]);
  expect(todayActions({ ...base, done: { sown: true, harvested: true } }, "2026-10-12").every((a) => a.done)).toBe(true);
});

test("a shortage says how much of the orders it covers, or when anything is sellable again", () => {
  const short = todayActions({ ...base, send_kg: 3.7, short_kg: 6.3, cover_pct: 37, rotated: ["Bu Sari"] }, "2026-10-12");
  expect(short.find((a) => a.kind === "short")!.title).toBe("Short 6.30 kg: covers ~37% of tomorrow's orders");
  expect(short.find((a) => a.kind === "short")!.lines).toEqual(["Bu Sari rotates"]);
  const none = todayActions({ ...base, send_kg: 0, short_kg: 10, cover_pct: 0, harvest_plan: [],
    sellable_from: "2026-10-20" }, "2026-10-12");
  expect(none.find((a) => a.kind === "harvest")).toBeUndefined();
  expect(none.find((a) => a.kind === "short")!.lines).toContain("Nothing sellable until Tue 20 Oct");
});

test("nothing ordered: no harvest, no shortage", () => {
  const a = todayActions({ ...base, need_kg: 0, send_kg: 0, cover_pct: null, harvest_plan: [] }, "2026-10-12");
  expect(a.map((x) => x.kind)).toEqual(["idle", "sow"]);
});

test("the Sow form opens on the line due today, else a line that is in use", () => {
  const due = (line: string, day: string, seedlings = 500) => ({ line, day, seedlings });
  expect(sowLineDefault(["regular", "baby"], [due("regular", "2026-10-15"), due("baby", "2026-10-12")],
    new Set(["regular", "baby"]), "2026-10-12")).toBe("baby");
  expect(sowLineDefault(["regular", "baby"], [due("regular", "2026-10-15"), due("baby", "2026-10-15")],
    new Set(["baby"]), "2026-10-12")).toBe("baby");
  expect(sowLineDefault(["regular", "baby"], [due("regular", "2026-10-12", 0), due("baby", "2026-10-15")],
    new Set(["baby"]), "2026-10-12")).toBe("baby");
  expect(sowLineDefault(["regular"], [], new Set(), "2026-10-12")).toBe("regular");
});

test("a sowing day that needs no seedlings says so instead of 'Sow 0'", () => {
  const s = todayActions({ ...base, sow: { ...sow, seedlings: 0, seeds_g: 0, teaspoons: 0 } }, "2026-10-12")
    .find((a) => a.kind === "sow")!;
  expect(s.title).toBe("No sowing needed today: the beds in the ground cover the orders it would serve");
  expect(s.prefill).toEqual([]);
});
