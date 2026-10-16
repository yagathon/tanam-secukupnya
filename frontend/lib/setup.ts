import type { Setup } from "./types";

const sums100 = (v: number[], n: number) =>
  v.length === n && v.every((x) => x >= 0) && Math.abs(v.reduce((a, b) => a + b, 0) - 100) <= 0.5;

/** Shares are typed as % (85) and stored as 0–1 (0.85); rounded so 0.45 shows as 45, not 45.00000000000001. */
export const toPct = (x: number) => Math.round(x * 1e4) / 100;
export const fromPct = (x: number) => Math.round(x * 100) / 1e4;

const inPct = (x: number, hi: number) => x > 0 && x <= hi;

/** The server's setup rules, client-side, so problems show while typing (the server stays the judge). */
export function checkSetup(s: Setup): string[] {
  const p: string[] = [];
  const c = s.crop;
  if (c.growth_curve.length < 2 || c.growth_curve.length > 30) p.push("growth curve needs 2 to 30 points");
  c.growth_curve.forEach(([d, g], i) => {
    if (i && (d <= c.growth_curve[i - 1][0] || g <= c.growth_curve[i - 1][1]))
      p.push(`curve point ${i + 1}: days and grams must both increase`);
  });
  if (!inPct(c.germination, 1)) p.push("germination must be 1–100%");
  if (!inPct(c.survival, 1)) p.push("survival must be 1–100%");
  if (!inPct(c.spread_ratio, 2)) p.push("size spread must be 1–200%");
  if (!c.sow_weekdays.length) p.push("pick at least one sowing weekday");
  const lines = new Set(c.lines.map((l) => l.id));
  for (const l of c.lines) {
    if (l.min_g >= l.max_g) p.push(`line ${l.id}: min g must be below max g`);
    if (l.stretch_g != null && l.stretch_g < l.max_g) p.push(`line ${l.id}: 'up to if short' must be at least max g`);
  }
  const names = new Set<string>();
  if (s.buyers.length > 50) p.push("at most 50 buyers");
  for (const b of s.buyers) {
    if (names.has(b.name)) p.push(`buyer name ${b.name} is used twice`);
    names.add(b.name);
    if (!lines.has(b.line)) p.push(`buyer ${b.name}: unknown line ${b.line}`);
    if (b.week_pct?.length && !sums100(b.week_pct, 7)) p.push(`buyer ${b.name}: weekday % needs 7 numbers (Mon…Sun) adding up to 100`);
  }
  if (s.month_pct && !sums100(s.month_pct, 4)) p.push("month % needs 4 numbers (dates 1–7, 8–14, 15–21, 22–end) adding up to 100");
  if (s.year_index && (s.year_index.length !== 12 || s.year_index.some((x) => !(x >= 0 && x <= 500))))
    p.push("year index needs 12 numbers (Jan…Dec), 0–500");
  if (s.beds.length > 50) p.push("at most 50 beds");
  for (const b of s.beds) {
    if (!lines.has(b.line)) p.push(`bed: unknown line ${b.line}`);
    if (b.sown_on > s.start) p.push(`bed sown ${b.sown_on} is after the start ${s.start}`);
  }
  return p;
}
