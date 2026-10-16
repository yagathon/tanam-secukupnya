import { numbersFromRow } from "./sheet";

/** A spreadsheet row pasted into one cell of a pattern fills all cells, if it has exactly one number per cell. */
export function pasteRow(text: string, n: number): number[] | null {
  const v = numbersFromRow(text);
  return v && v.length === n && n > 1 ? v : null;
}

/** 100 spread evenly over the order days (all days if none), to 0.1; the last day takes the rounding. */
export function evenWeek(days: number[]): number[] {
  const on = days.length ? days : [0, 1, 2, 3, 4, 5, 6];
  const each = Math.round((100 / on.length) * 10) / 10;
  const out = Array(7).fill(0);
  on.forEach((d) => { out[d] = each; });
  out[on[on.length - 1]] = Math.round((100 - each * (on.length - 1)) * 10) / 10;
  return out;
}
