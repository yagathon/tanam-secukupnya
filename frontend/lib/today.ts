import { int, kg, shortDate, tsp } from "./format";
import type { TodayLine } from "./types";

export type ActKind = "harvest" | "sow";
export interface Prefill { label: string; kind: ActKind; form: Record<string, string> }
export interface TodayAction {
  kind: "harvest" | "short" | "idle" | "sow";
  title: string; lines: string[]; prefill: Prefill[]; done: boolean;
}

const num = (n: number) => String(Math.round(n * 100) / 100);

/** One line's day as things to do: harvest (per bed), how short tomorrow is, and sowing. */
export function todayActions(l: TodayLine, today: string): TodayAction[] {
  const out: TodayAction[] = [];
  const done = l.done ?? { sown: false, harvested: false };
  const plan = l.harvest_plan ?? [];
  if (l.need_kg <= 0) {
    out.push({ kind: "idle", title: "Nothing ordered for tomorrow", lines: [], prefill: [], done: false });
  } else {
    if (l.send_kg > 0 && plan.length > 0) out.push({
      kind: "harvest", title: `Harvest ${kg(l.send_kg)} for tomorrow`, done: done.harvested,
      lines: plan.map((p) => `${p.label}: ${kg(p.kg)} · ~${int(p.avg_g)} g a plant (${p.sampled ? "your sample" : "growth curve"})`),
      prefill: plan.map((p) => ({ label: p.label, kind: "harvest", form: { batch: p.batch, kg: num(p.kg) } })),
    });
    if (l.short_kg > 0.005) out.push({
      kind: "short", done: done.harvested, prefill: [],
      title: `Short ${kg(l.short_kg)}: covers ~${l.cover_pct ?? 0}% of tomorrow's orders`,
      lines: [...l.rotated.map((r) => `${r} rotates`), ...(l.sellable_from ? [`Nothing sellable until ${shortDate(l.sellable_from)}`] : [])],
    });
  }
  const s = l.sow;
  const ahead = s.shortfall_ahead_kg > 0 ? [`Still short ${kg(s.shortfall_ahead_kg)} before it is ready`] : [];
  if (s.day === today) out.push({
    kind: "sow", title: `Sow ${int(s.seedlings)} seedlings`, done: done.sown,
    lines: [`≈ ${s.seeds_g} g seed ≈ ${tsp(s.teaspoons)}`, ...ahead],
    prefill: [{ label: "Log sowing", kind: "sow", form: { line: l.line, seedlings: String(s.seedlings) } }],
  });
  else out.push({ kind: "sow", title: `Next sowing ${shortDate(s.day)}: ~${int(s.seedlings)} seedlings`,
    lines: ahead, prefill: [], done: false });
  return out;
}
