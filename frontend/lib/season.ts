import type { Setup } from "./types";

type Buyer = Setup["buyers"][number];
const r4 = (x: number) => Math.round(x * 1e4) / 1e4;

/** kg per weekday (Mon…Sun) from the setup, as app.sandbox._week. */
export function buyerWeek(b: Buyer): number[] {
  if (b.week_pct?.length === 7) return b.week_pct.map((p) => r4((b.usual_kg_per_week * p) / 100));
  const days = b.weekdays.length ? b.weekdays : [0, 1, 2, 3, 4, 5, 6];
  return [0, 1, 2, 3, 4, 5, 6].map((d) => (days.includes(d) ? r4(b.usual_kg_per_week / days.length) : 0));
}

/** Month block × year index for one day, as app.demand.season_factor. */
export function seasonFactor(month: number[], year: number[], iso: string): number {
  const d = new Date(`${iso}T00:00:00Z`);
  const block = Math.min(Math.floor((d.getUTCDate() - 1) / 7), 3);
  return ((month[block] ?? 25) / 25) * ((year[d.getUTCMonth()] ?? 100) / 100);
}

export interface YearRow { day: string; kg: Record<string, number> }

/** The starting forecast for 365 days from the setup's start: weekday × month × year patterns multiplied,
 *  summed per line. What the engine expects before any order teaches it otherwise. */
export function yearCurve(s: Setup): YearRow[] {
  const month = s.month_pct ?? [25, 25, 25, 25];
  const year = s.year_index ?? Array(12).fill(100);
  const weeks = s.buyers.map((b) => ({ line: b.line, w: buyerWeek(b) }));
  const lines = [...new Set(s.buyers.map((b) => b.line))];
  const t0 = Date.parse(`${s.start}T00:00:00Z`);
  return Array.from({ length: 365 }, (_, i) => {
    const day = new Date(t0 + i * 86400000).toISOString().slice(0, 10);
    const wd = (new Date(`${day}T00:00:00Z`).getUTCDay() + 6) % 7;
    const f = seasonFactor(month, year, day);
    const kg: Record<string, number> = Object.fromEntries(lines.map((l) => [l, 0]));
    for (const { line, w } of weeks) kg[line] += w[wd] * f;
    for (const l of lines) kg[l] = r4(kg[l]);
    return { day, kg };
  });
}
