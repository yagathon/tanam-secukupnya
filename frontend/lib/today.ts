import { int, kg, shortDate, tsp } from "./format";
import type { TodayLine } from "./types";

export type ActKind = "harvest" | "sow";
export interface Prefill { label: string; kind: ActKind; form: Record<string, string> }
export interface TodayAction {
  kind: "demand" | "extra" | "short" | "idle" | "sow";
  title: string; lines: string[]; prefill: Prefill[]; done: boolean;
}

const num = (n: number) => String(Math.round(n * 100) / 100);

const EXTRA_MIN_KG = 0.5;

/** One line's day as things to do: tomorrow's demand (harvest follows orders, logged per bed), the extra that
 *  is safe to sell, how short tomorrow is, and sowing. */
export function todayActions(l: TodayLine, today: string): TodayAction[] {
  const out: TodayAction[] = [];
  const done = l.done ?? { sown: false, harvested: false };
  const plan = l.send_kg > 0 ? l.harvest_plan ?? [] : [];
  if (l.need_kg <= 0) {
    out.push({ kind: "idle", title: "Nothing ordered for tomorrow", lines: [], prefill: [], done: false });
  } else out.push({
    kind: "demand", title: `Demand tomorrow ${kg(l.need_kg)}`, done: done.harvested,
    lines: (l.demand ?? []).map((d) => `${d.alias}: ${kg(d.kg)} (${d.known ? "ordered" : "forecast"})`),
    prefill: plan.map((p) => ({ label: p.label, kind: "harvest", form: { batch: p.batch, kg: num(p.kg) } })),
  });
  if ((l.extra_kg ?? 0) >= EXTRA_MIN_KG) out.push({
    kind: "extra", title: `Extra to sell: up to ${kg(l.extra_kg!)}`, prefill: [], done: false,
    lines: ["Not needed for any forecast order before the next bed is ready — sell it or it will outgrow its size."],
  });
  if (l.need_kg > 0 && l.short_kg > 0.005) out.push({
    kind: "short", done: done.harvested, prefill: [],
    title: `Short ${kg(l.short_kg)}: covers ~${l.cover_pct ?? 0}% of tomorrow's orders`,
    lines: [...l.rotated.map((r) => `${r} rotates`), ...(l.sellable_from ? [`Nothing sellable until ${shortDate(l.sellable_from)}`] : [])],
  });
  const s = l.sow;
  const ahead = s.shortfall_ahead_kg > 0 ? [`Still short ${kg(s.shortfall_ahead_kg)} before it is ready`] : [];
  if (s.day === today && s.seedlings <= 0) out.push({ kind: "sow", lines: ahead, prefill: [], done: false,
    title: "No sowing needed today: the beds in the ground cover the orders it would serve" });
  else if (s.day === today) out.push({
    kind: "sow", title: `Sow ${int(s.seedlings)} seedlings`, done: done.sown,
    lines: [`≈ ${s.seeds_g} g seed ≈ ${tsp(s.teaspoons)}`, ...ahead],
    prefill: [{ label: "Log sowing", kind: "sow", form: { line: l.line, seedlings: String(s.seedlings) } }],
  });
  else out.push({ kind: "sow", title: `Next sowing ${shortDate(s.day)}: ~${int(s.seedlings)} seedlings`,
    lines: ahead, prefill: [], done: false });
  return out;
}

/** Which line the Sow form opens on: the one due today, else one with buyers or beds, else the first. */
export function sowLineDefault(lines: string[], due: { line: string; day: string; seedlings: number }[],
  inUse: Set<string>, today: string): string {
  return due.find((d) => d.day === today && d.seedlings > 0 && inUse.has(d.line))?.line
    ?? due.find((d) => d.day === today && d.seedlings > 0)?.line
    ?? lines.find((l) => inUse.has(l)) ?? lines[0] ?? "";
}
