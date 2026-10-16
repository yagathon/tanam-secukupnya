import type { SetupBed, SetupBuyer } from "./types";

/** Paste from / copy to a spreadsheet: tab-separated (what Sheets and Excel copy), or CSV with , or ;. */

export const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export function parseSheet(text: string): string[][] {
  const lines = text.replace(/^﻿/, "").split(/\r?\n/).filter((l) => l.trim() !== "");
  const sep = lines.some((l) => l.includes("\t")) ? "\t" : lines.some((l) => l.includes(";")) ? ";" : ",";
  return lines.map((l) => l.split(sep).map((c) => c.trim()));
}

/** "12,5" and "1.234,5" (Indonesian locale) as well as "12.5"; empty or not a number → null. */
export function toNumber(s: string): number | null {
  let t = s.trim().replace(/\s/g, "");
  if (t === "") return null;
  if (t.includes(",") && t.includes(".")) t = t.replace(/\./g, "").replace(",", ".");
  else if (t.includes(",")) t = t.replace(",", ".");
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}

/** One pasted spreadsheet row (tabs) or typed numbers (spaces/semicolons); [] if empty, null if any cell isn't a number. */
export function numbersFromRow(text: string): number[] | null {
  const cells = text.trim() === "" ? [] : text.trim().split(/[\t;]|\s+/).filter((c) => c !== "");
  const out = cells.map(toNumber);
  return out.some((n) => n === null) ? null : (out as number[]);
}

export function toSheet(rows: (string | number)[][]): string {
  return rows.map((r) => r.join("\t")).join("\n");
}

export function parseWeekdays(s: string): number[] {
  const out = new Set<number>();
  for (const w of s.split(/[\s,;/]+/).filter(Boolean)) {
    const i = WEEKDAYS.findIndex((d) => d.toLowerCase() === w.slice(0, 3).toLowerCase());
    if (i >= 0) out.add(i);
  }
  return [...out].sort((a, b) => a - b);
}

/** Drop the first row when it is a header: `isHeader` looks at a column that must hold data. */
function body(rows: string[][], isHeader: (r: string[]) => boolean): string[][] {
  return rows.length && isHeader(rows[0]) ? rows.slice(1) : rows;
}

export function curveFromSheet(text: string): { points: [number, number][] } | { error: string } {
  const rows = body(parseSheet(text), (r) => toNumber(r[0] ?? "") === null);
  const pts: [number, number][] = [];
  for (const [i, r] of rows.entries()) {
    const d = toNumber(r[0] ?? ""), g = toNumber(r[1] ?? "");
    if (d === null) return { error: `row ${i + 1}: day is not a number` };
    if (g === null) return { error: `row ${i + 1}: grams is not a number` };
    if (pts.length && (d <= pts[pts.length - 1][0] || g <= pts[pts.length - 1][1]))
      return { error: `row ${i + 1}: days and grams must both increase` };
    pts.push([d, g]);
  }
  return { points: pts };
}

export function buyersFromSheet(text: string, lines: string[]): { buyers: SetupBuyer[] } | { error: string } {
  const out: SetupBuyer[] = [];
  const rows = body(parseSheet(text), (r) => (r[1] ?? "").toLowerCase() === "type");
  for (const [i, r] of rows.entries()) {
    const [name, type, line, usual = "", wd = "", min = ""] = r;
    if (!name) return { error: `row ${i + 1}: name is empty` };
    if (type !== "business" && type !== "household") return { error: `row ${i + 1}: type must be business or household` };
    if (!lines.includes(line)) return { error: `row ${i + 1}: unknown line ${line}` };
    const u = usual === "" ? 0 : toNumber(usual), m = min === "" ? 0 : toNumber(min);
    if (u === null || u < 0) return { error: `row ${i + 1}: usual kg/week is not a number` };
    if (m === null || m < 0) return { error: `row ${i + 1}: min kg is not a number` };
    out.push({ name, type, line, usual_kg_per_week: u, weekdays: parseWeekdays(wd), min_kg: m });
  }
  return { buyers: out };
}

export function bedsFromSheet(text: string, lines: string[]): { beds: SetupBed[] } | { error: string } {
  const out: SetupBed[] = [];
  const rows = body(parseSheet(text), (r) => toNumber(r[2] ?? "") === null && !/\d/.test(r[1] ?? ""));
  for (const [i, r] of rows.entries()) {
    const [line, sown, n] = r;
    if (!lines.includes(line)) return { error: `row ${i + 1}: unknown line ${line}` };
    if (!/^\d{4}-\d{2}-\d{2}$/.test(sown ?? "")) return { error: `row ${i + 1}: sown on must be YYYY-MM-DD` };
    const s = toNumber(n ?? "");
    if (s === null || s <= 0 || !Number.isInteger(s)) return { error: `row ${i + 1}: seedlings must be a whole number above 0` };
    out.push({ line, sown_on: sown, seedlings: s });
  }
  return { beds: out };
}
