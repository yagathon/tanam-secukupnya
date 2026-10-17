import { int } from "./format";
import type { PastBeds, SandboxLog } from "./types";

/** One line for the beds that left the Batches table (past their window), so their waste stays visible. */
export function pastBedsText(p: PastBeds | undefined): string | null {
  if (!p || p.beds === 0) return null;
  return `Earlier beds (${p.beds}, no longer listed): ${int(p.harvested_plants)} plants harvested · ` +
    `${int(p.lost_plants)} lost · ${int(p.waste_plants)} wasted`;
}

export const logFileName = (start: string, today: string) => `tanam-sandbox-${start}_to_${today}.json`;

/** A downloaded log, checked enough to give a clear message; the server replays it and stays the judge. */
export function readLogFile(text: string): SandboxLog | { error: string } {
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch {
    return { error: "That file is not JSON; choose a file from Download my log." };
  }
  const r = raw as Partial<SandboxLog>;
  if (r?.format !== "tanam-sandbox-log" || !Array.isArray(r.log) || typeof r.setup !== "object")
    return { error: "That file is not a sandbox log; choose a file from Download my log." };
  return r as SandboxLog;
}
