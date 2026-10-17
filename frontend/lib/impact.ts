import type { ImpactDelivery, ImpactRow } from "./types";

const n = (x: number) => Math.abs(Math.round(x)).toLocaleString("en-US");
const diff = (habit: number, tanam: number, what: string) => `${n(habit - tanam)} ${tanam <= habit ? "fewer" : "more"} ${what}`;

/** One sentence: what Tanam's sizing did against sowing a fixed amount every week, for the same orders. */
export function impactHeadline(rows: { tanam: ImpactRow; habit: ImpactRow }, d: ImpactDelivery, habitSeedlings: number): string {
  const { tanam, habit } = rows;
  const head = `${d.habit_short_kg > 0 ? "" : "Same "}${tanam.delivered_kg.toFixed(1)} kg delivered with `
    + `${diff(habit.seedlings, tanam.seedlings, "seedlings")} and ${diff(habit.waste_plants, tanam.waste_plants, "plants wasted")} `
    + `than sowing ${n(habitSeedlings)} every week`;
  return d.habit_short_kg > 0 ? `${head}; that habit would also have missed ${d.habit_short_kg.toFixed(1)} kg.` : `${head}.`;
}
