import { shortDate } from "./format";
import type { ImpactBed, ImpactDelivery, ImpactRow } from "./types";

const n = (x: number) => Math.abs(Math.round(x)).toLocaleString("en-US");
const diff = (habit: number, tanam: number, what: string) => `${n(habit - tanam)} ${tanam <= habit ? "fewer" : "more"} ${what}`;

/** One sentence: what Tanam's sizing did against sowing a fixed amount every week, for the same orders. */
export function impactHeadline(rows: { tanam: ImpactRow; habit: ImpactRow }, d: ImpactDelivery, habitLabel: string): string {
  const { tanam, habit } = rows;
  const head = `${d.habit_short_kg > 0 ? "" : "Same "}${tanam.delivered_kg.toFixed(1)} kg delivered with `
    + `${diff(habit.seedlings, tanam.seedlings, "seedlings")} and ${diff(habit.waste_plants, tanam.waste_plants, "plants wasted")} `
    + `than sowing ${habitLabel}`;
  return d.habit_short_kg > 0 ? `${head}; that habit would also have missed ${d.habit_short_kg.toFixed(1)} kg.` : `${head}.`;
}

/** The x label of a bed's bar: setup beds starred; the habit's simulated beds by sowing day (and line when there are several). */
export function bedBarName(b: ImpactBed, lines: number): string {
  if (b.group === "before") return `${b.label}*`;
  if (b.group === "tanam") return b.label;
  const day = shortDate(b.sown_on).split(" ").slice(1).join(" ");
  return lines > 1 ? `${day} ${b.line}` : day;
}
