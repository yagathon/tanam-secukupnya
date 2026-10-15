import { ApiError } from "./api";
import type { LineId, Proposal, State, TodayLine } from "./types";

const DAY = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** 37.17 → "37.2 kg", 1.76 → "1.76 kg", 0 → "0 kg". */
export function kg(n: number): string {
  if (Math.abs(n) < 0.005) return "0 kg";
  return `${n.toFixed(Math.abs(n) >= 10 ? 1 : 2)} kg`;
}

export const int = (n: number) => Math.round(n).toLocaleString("en-US");

/** "2026-10-13" → "Tue 13 Oct". Parsed as UTC so the viewer's timezone never shifts the day. */
export function shortDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  return `${DAY[d.getUTCDay()]} ${d.getUTCDate()} ${MON[d.getUTCMonth()]}`;
}

const FRACTIONS: [number, string][] = [[0, ""], [1 / 4, "¼"], [1 / 3, "⅓"], [1 / 2, "½"], [2 / 3, "⅔"], [3 / 4, "¾"], [1, ""]];

/** Teaspoons as a kitchen measure: 1.333 → "1⅓ tsp". Below ⅛ tsp → "<¼ tsp". */
export function tsp(x: number): string {
  if (x < 0.125) return "<¼ tsp";
  let whole = Math.floor(x);
  const [f, sym] = FRACTIONS.reduce((best, cur) => (Math.abs(cur[0] - (x - whole)) < Math.abs(best[0] - (x - whole)) ? cur : best));
  if (f === 1) whole += 1;
  return `${whole > 0 ? whole : ""}${f === 1 ? "" : sym}`.trim() + " tsp";
}

export const lineName = (id: LineId) => `Pakcoy ${id}`;

/** The one-line day summary from spec §10, per line. */
export function daySentence(l: TodayLine): string {
  const s = l.sow;
  const sow = `${s.weekday}: sow ${int(s.seedlings)} seedlings ≈ ${s.seeds_g.toFixed(1)} g ≈ ${tsp(s.teaspoons)}`;
  let head: string;
  if (l.need_kg < 0.005) head = "Nothing to send tomorrow";
  else if (l.short_kg > 0.005) {
    head = `Max safe tomorrow ${l.ceiling_kg.toFixed(1)} kg · need ${l.need_kg.toFixed(1)} kg · short ${kg(l.short_kg)}`;
    if (l.rotated.length) head += ` → ${l.rotated.join(", ")} ${l.rotated.length === 1 ? "rotates" : "rotate"}`;
  } else head = `Send ${kg(l.send_kg)} tomorrow (max safe ${kg(l.ceiling_kg)})`;
  const ahead = s.shortfall_ahead_kg > 0.005 ? ` · ${kg(s.shortfall_ahead_kg)} short ahead` : "";
  return `${head} · ${sow}${ahead}`;
}

export function scopeName(scope: string, state: State): string {
  if (scope === "all") return "Everyone";
  if (scope === "channel:B2B") return "Restaurants & caterers";
  if (scope === "channel:B2C") return "Households";
  const id = scope.replace(/^buyer:/, "");
  return state.buyers.find((b) => b.id === id)?.alias ?? id;
}

const pct = (n: number) => `${n > 0 ? "+" : n < 0 ? "−" : ""}${Math.abs(n)}%`;

/** One plain line per proposed event. Unknown or partial (legacy) proposals give [] and the card
 *  falls back to the note's own summary. */
export function proposalLines(p: Proposal | undefined, state: State): string[] {
  if (!p) return [];
  const alias = (id: string) => state.buyers.find((b) => b.id === id)?.alias ?? id;
  switch (p.kind) {
    case "orders":
      return (p.orders ?? []).map((o) => `${alias(o.buyer)} orders ${kg(o.kg)} ${lineName(o.line)} for ${shortDate(o.day)}`);
    case "harvest": {
      const h = p.harvest;
      if (!h) return [];
      const sample = h.big5_g != null && h.small5_g != null
        ? `5 biggest ${h.big5_g} g, 5 smallest ${h.small5_g} g` : "no size sample";
      return [`${h.bed}: harvested ${kg(h.kg)} · ${sample}`];
    }
    case "sowing": {
      const s = p.sowing;
      if (!s) return [];
      return [s.postponed ? `Sowing of ${lineName(s.line)} postponed: ${s.reason || "no reason given"}`
        : `Sowed ${int(s.seedlings ?? 0)} seedlings of ${lineName(s.line)} today`];
    }
    case "loss": {
      const l = p.loss;
      return l ? [`${l.bed}: ${l.pct}% of the plants lost (${l.cause_category}: ${l.cause})`] : [];
    }
    case "signal":
      return (p.signals ?? []).map((s) => {
        const when = s.open_ended ? `from ${shortDate(s.date_from)} onward`
          : `from ${shortDate(s.date_from)} to ${shortDate(s.date_to)}`;
        return `${scopeName(s.scope, state)}, ${s.line ? lineName(s.line) : "all lines"}: ${pct(s.effect_pct)} ${when} (${s.cause})`;
      });
    default:
      return [];
  }
}

const sentence = (s: string) => {
  const t = s.trim();
  return t.charAt(0).toUpperCase() + t.slice(1) + (/[.!?]$/.test(t) ? "" : ".");
};

/** One sentence a visitor can act on, for any error the UI catches. */
export function friendly(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 401) return "Your demo session expired. Reload the page.";
    if (e.status === 429) return "Today's Gemini budget for this demo is used up. Try again tomorrow.";
    if (e.status === 502) return "Gemini could not read the note just now. Try again in a moment.";
    if (e.status >= 500 || e.detail.trimStart().startsWith("<")) return "The server had a problem. Try again in a moment.";
    return sentence(e.detail);
  }
  const offline = "Could not reach the server. Check the connection and retry.";
  if (e instanceof TypeError) return offline;
  if ((e as { code?: unknown } | null)?.code === "auth/network-request-failed") return offline;
  console.error(e);
  return "Something went wrong. Reload the page and try again.";
}
