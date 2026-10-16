import type { Setup } from "./types";

/** The server's setup rules, client-side, so problems show while typing (the server stays the judge). */
export function checkSetup(s: Setup): string[] {
  const p: string[] = [];
  const c = s.crop;
  if (c.growth_curve.length < 2 || c.growth_curve.length > 30) p.push("growth curve needs 2 to 30 points");
  c.growth_curve.forEach(([d, g], i) => {
    if (i && (d <= c.growth_curve[i - 1][0] || g <= c.growth_curve[i - 1][1]))
      p.push(`curve point ${i + 1}: days and grams must both increase`);
  });
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
  }
  if (s.beds.length > 50) p.push("at most 50 beds");
  for (const b of s.beds) {
    if (!lines.has(b.line)) p.push(`bed: unknown line ${b.line}`);
    if (b.sown_on > s.start) p.push(`bed sown ${b.sown_on} is after the start ${s.start}`);
  }
  return p;
}
