import type { Channel, SeriesView } from "./types";

export interface LinePoint {
  week: string;
  history?: number;
  expected?: number;
  low?: number;
  high?: number;
  band?: [number, number];
  reasons?: string[];
}

export const lineKey = (crop: string, line: string) => `${crop}/${line}`;

/** Sum the series of one crop × line (optionally one channel) into a single chart series.
 *  History adds up; forecast bands combine in quadrature (partners' bad weeks are independent). */
export function aggregate(series: SeriesView[], crop: string, line: string, channel?: Channel): LinePoint[] {
  const picked = series.filter(
    (s) => s.series.crop === crop && s.series.line === line && (!channel || s.series.channel === channel),
  );
  const byWeek = new Map<string, LinePoint & { varLow: number; varHigh: number }>();
  const row = (week: string) => {
    let r = byWeek.get(week);
    if (!r) byWeek.set(week, (r = { week, varLow: 0, varHigh: 0 }));
    return r;
  };
  for (const s of picked) {
    for (const h of s.history) {
      const r = row(h.week);
      r.history = (r.history ?? 0) + h.kg;
    }
    for (const p of s.forecast) {
      const r = row(p.week);
      r.expected = (r.expected ?? 0) + p.expected;
      r.varLow += (p.expected - p.low) ** 2;
      r.varHigh += (p.high - p.expected) ** 2;
      r.reasons = [...new Set([...(r.reasons ?? []), ...p.reasons.filter((x) => !x.startsWith("baseline"))])];
    }
  }
  return [...byWeek.values()]
    .sort((a, b) => a.week.localeCompare(b.week))
    .map(({ varLow, varHigh, ...r }) => {
      if (r.expected === undefined) return { ...r, history: r.history === undefined ? undefined : round(r.history) };
      const low = Math.max(0, r.expected - Math.sqrt(varLow));
      const high = r.expected + Math.sqrt(varHigh);
      return { ...r, expected: round(r.expected), low: round(low), high: round(high), band: [round(low), round(high)] };
    });
}

export const round = (x: number, d = 1) => Math.round(x * 10 ** d) / 10 ** d;
export const kg = (x: number) => `${x.toLocaleString("en-US", { maximumFractionDigits: 1 })} kg`;
export const shortDate = (iso: string) =>
  new Date(iso + "T00:00:00").toLocaleDateString("en-GB", { day: "numeric", month: "short" });
/** Recharts hands labels over as ReactNode; ours are ISO week strings. */
export const weekLabel = (label: unknown) => shortDate(String(label));
