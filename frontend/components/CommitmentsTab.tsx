"use client";

import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { Data } from "@/lib/types";
import LinePicker, { firstLine } from "@/components/LinePicker";
import { aggregate, kg, round, shortDate, weekLabel } from "@/lib/series";

/** Layered assurance per week (delivery kg): what is contractually promised, what Trusted Farm
 *  guarantees on top, the household floor, and the buffer between the low band and expected. */
export default function CommitmentsTab({ data }: { data: Data }) {
  const { state, series } = data;
  const [key, setKey] = useState(firstLine(state.crops));
  const [crop, line] = key.split("/");

  const rows = useMemo(() => {
    const minimums = state.partners.reduce((s, p) => s + (p.corridor[key]?.min_kg ?? 0), 0);
    const b2b = aggregate(series, crop, line, "B2B").filter((p) => p.expected !== undefined);
    const b2c = aggregate(series, crop, line, "B2C").filter((p) => p.expected !== undefined);
    const weeks = [...new Set([...b2b, ...b2c].map((p) => p.week))].sort();
    return weeks.map((week) => {
      const b = b2b.find((p) => p.week === week);
      const c = b2c.find((p) => p.week === week);
      const contracted = Math.min(minimums, b?.expected ?? 0);
      const guarantee = Math.max(0, (b?.low ?? 0) - contracted);
      const floor = c?.low ?? 0;
      const buffer = Math.max(0, (b?.expected ?? 0) + (c?.expected ?? 0) - contracted - guarantee - floor);
      return { week, contracted: round(contracted), guarantee: round(guarantee), floor: round(floor), buffer: round(buffer) };
    });
  }, [state.partners, series, key, crop, line]);

  const next = rows[0];

  return (
    <div className="card">
      <LinePicker crops={state.crops} value={key} onChange={setKey} />
      <ResponsiveContainer width="100%" height={320}>
        <BarChart data={rows} margin={{ top: 16, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--grid)" vertical={false} />
          <XAxis dataKey="week" tickFormatter={shortDate} minTickGap={16} />
          <YAxis unit=" kg" width={64} />
          <Tooltip formatter={(v) => kg(Number(v))} labelFormatter={weekLabel} />
          <Legend />
          <Bar dataKey="contracted" name="Partner minimums" stackId="a" fill="var(--soil)" isAnimationActive={false} />
          <Bar dataKey="guarantee" name="TF guarantee" stackId="a" fill="var(--leaf)" isAnimationActive={false} />
          <Bar dataKey="floor" name="Household floor" stackId="a" fill="var(--sky)" isAnimationActive={false} />
          <Bar dataKey="buffer" name="Buffer (not promised)" stackId="a" fill="var(--grid)" isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
      {next && (
        <div className="kpis">
          <div><span className="muted small">Partner minimums</span><strong>{kg(next.contracted ?? 0)}</strong></div>
          <div><span className="muted small">TF guarantee on top</span><strong>{kg(next.guarantee ?? 0)}</strong></div>
          <div><span className="muted small">Household floor</span><strong>{kg(next.floor ?? 0)}</strong></div>
          <div><span className="muted small">Buffer</span><strong>{kg(next.buffer ?? 0)}</strong></div>
        </div>
      )}
      <p className="muted small">
        Farmers are guaranteed offtake for their share of everything below the buffer. The buffer is planted for
        but not promised: it is where the forecast is honest about not knowing.
      </p>
    </div>
  );
}
