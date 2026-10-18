"use client";

import SheetBox from "@/components/sandbox/SheetBox";
import { shortDate } from "@/lib/format";
import { toSheet } from "@/lib/sheet";
import type { TrailLine, TrailRow } from "@/lib/types";

const f1 = (n: number | null | undefined) => (n === null || n === undefined ? "—" : n.toFixed(1));
const COLS: [string, (l: TrailLine | undefined) => string][] = [
  ["forecast", (l) => (l ? `${f1(l.low)}–${f1(l.high)}` : "")],
  ["ready", (l) => f1(l?.ready)],
  ["ceiling", (l) => f1(l?.ceiling)],
  ["send", (l) => f1(l?.send)],
  ["short", (l) => f1(l?.short)],
  ["sow", (l) => (l?.sow_day ? `${shortDate(l.sow_day)} · ${l.sow_seedlings}` : "—")],
];

/** One row per day, newest first: what the engine decided, and what was logged that day. */
export default function TrailTab({ rows, emptyHint }: { rows: TrailRow[]; emptyHint?: boolean }) {
  if (emptyHint && !rows.some((r) => !r.live))
    return <div className="card empty">No closed days yet: press <strong>Next day →</strong> to run the farm forward.</div>;
  const sorted = [...rows].sort((a, b) => (a.day < b.day ? 1 : a.day > b.day ? -1 : 0));
  const lines = [...new Set(rows.flatMap((r) => Object.keys(r.lines)))];
  const cells = (r: TrailRow) => [
    ...lines.flatMap((ln) => COLS.map(([, fn]) => fn(r.lines[ln]))), r.inputs.join("\n"), r.ref.join("\n"),
  ];
  const header = [...lines.flatMap((ln) => COLS.map(([c]) => `${ln} ${c}`)), "inputs", "reference"];
  const table = sorted.map((r) => ({ r, c: cells(r) }));

  if (!rows.length) return <div className="card muted">No days yet.</div>;
  return (
    <div className="card">
      <p className="small muted">
        Each closed day keeps what the engine said that morning, before the dayEach closed day freezes what the engine said that day. Highlightedapos;s entries; today shows the plan as it stands now. Highlighted cells moved since the day before. kg throughout.
      </p>
      <SheetBox copy={() => toSheet([["day", ...header], ...table.map(({ r, c }) => [r.day, ...c.map((x) => x.replace(/\n/g, " | "))])])} />
      <div className="scroll">
        <table className="trail">
          <thead>
            <tr><th rowSpan={2}>Day</th>{lines.map((ln) => <th key={ln} colSpan={COLS.length}>{ln}</th>)}<th rowSpan={2}>Inputs</th><th rowSpan={2}>Reference</th></tr>
            <tr>{lines.flatMap((ln) => COLS.map(([c]) => <th key={`${ln}${c}`}>{c}</th>))}</tr>
          </thead>
          <tbody>
            {table.map(({ r, c }, i) => {
              const below = table[i + 1]?.c;
              const last = c.length - 2;
              return (
                <tr key={r.day} className={r.live ? "live" : ""}>
                  <td>{r.live ? "today (not closed)" : shortDate(r.day)}</td>
                  {c.map((x, j) => (
                    <td key={j} className={[j >= last ? "inputs" : "num", below && j < last && below[j] !== x ? "changed" : ""].join(" ")}>{x}</td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
