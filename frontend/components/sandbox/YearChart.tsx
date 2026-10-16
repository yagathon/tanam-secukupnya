"use client";

import { Area, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { lineName } from "@/lib/format";
import { yearCurve } from "@/lib/season";
import type { Setup } from "@/lib/types";

const COLORS = ["var(--leaf)", "var(--sky)", "var(--soil)", "var(--warn)"];
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** The three patterns put together: kg per day for a year from the start, stacked per line,
 *  with the 7-day average so the month and year waves show through the weekly one. */
export default function YearChart({ setup }: { setup: Setup }) {
  const rows = yearCurve(setup);
  const lines = Object.keys(rows[0]?.kg ?? {});
  if (!lines.length) return <p className="small muted">Add a buyer to see the year.</p>;
  const total = rows.map((r) => lines.reduce((a, l) => a + r.kg[l], 0));
  const data = rows.map((r, i) => {
    const w = total.slice(Math.max(0, i - 3), i + 4);
    return { day: r.day, ...r.kg, avg: Math.round((w.reduce((a, b) => a + b, 0) / w.length) * 10) / 10 };
  });
  const ticks = rows.filter((r) => r.day.endsWith("-01")).map((r) => r.day);
  const peak = Math.max(...total);
  const low = Math.min(...total.filter((x) => x > 0));
  return (
    <>
      <ResponsiveContainer width="100%" height={240}>
        <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -8 }}>
          <XAxis dataKey="day" ticks={ticks} tickFormatter={(d: string) => MON[Number(d.slice(5, 7)) - 1]} fontSize={12} />
          <YAxis unit=" kg" fontSize={12} />
          <Tooltip labelFormatter={(d) => new Date(`${d}T00:00:00Z`).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", year: "numeric", timeZone: "UTC" })}
            formatter={(v, name) => [`${Number(v).toFixed(1)} kg`, name === "avg" ? "7-day average" : lineName(String(name))]} />
          {lines.map((l, i) => (
            <Area key={l} dataKey={l} stackId="kg" type="stepAfter" stroke="none" fill={COLORS[i % COLORS.length]}
              fillOpacity={0.45} isAnimationActive={false} />
          ))}
          <Line dataKey="avg" stroke="var(--ink)" dot={false} strokeWidth={1.5} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
      <p className="small muted">
        Busiest day {Math.round(peak * 10) / 10} kg, quietest order day {Number.isFinite(low) ? Math.round(low * 10) / 10 : 0} kg.
        Colours: {lines.map((l) => lineName(l)).join(", ")}; dark line = 7-day average.
      </p>
    </>
  );
}
