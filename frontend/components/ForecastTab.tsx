"use client";

import { useMemo, useState } from "react";
import { Area, CartesianGrid, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { Data } from "@/lib/types";
import LinePicker, { firstLine } from "@/components/LinePicker";
import { aggregate, kg, shortDate, weekLabel } from "@/lib/series";

const HISTORY_WEEKS = 16;

export default function ForecastTab({ data }: { data: Data }) {
  const { state, series } = data;
  const [key, setKey] = useState(firstLine(state.crops));
  const [crop, line] = key.split("/");

  const pts = useMemo(() => {
    const all = aggregate(series, crop, line);
    const firstFc = all.findIndex((p) => p.expected !== undefined);
    return all.slice(Math.max(0, firstFc - HISTORY_WEEKS));
  }, [series, crop, line]);
  const fc = pts.filter((p) => p.expected !== undefined);
  const parts = series.filter((s) => s.series.crop === crop && s.series.line === line);

  return (
    <div className="card">
      <LinePicker crops={state.crops} value={key} onChange={setKey} />
      <ResponsiveContainer width="100%" height={340}>
        <ComposedChart data={pts} margin={{ top: 16, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--grid)" vertical={false} />
          <XAxis dataKey="week" tickFormatter={shortDate} minTickGap={24} />
          <YAxis unit=" kg" width={64} />
          <Tooltip formatter={(v) => (Array.isArray(v) ? `${kg(v[0])} – ${kg(v[1])}` : kg(Number(v)))} labelFormatter={weekLabel} />
          <Legend />
          <Area dataKey="band" name="80% band" fill="var(--leaf-soft)" stroke="none" isAnimationActive={false} />
          <Line dataKey="history" name="Ordered" stroke="var(--ink)" dot={false} strokeWidth={1.5} isAnimationActive={false} />
          <Line dataKey="expected" name="Expected" stroke="var(--leaf)" strokeDasharray="5 4" dot={false} strokeWidth={2} isAnimationActive={false} />
          <ReferenceLine x={state.today} stroke="var(--soil)" label={{ value: "today", position: "top", fill: "var(--soil)", fontSize: 12 }} />
        </ComposedChart>
      </ResponsiveContainer>

      <div className="grid two">
        <div>
          <h3>Why these numbers</h3>
          <ul className="small">
            <li>Baseline: weighted recent average, after removing known past effects (so last Lebaran&apos;s dip does not drag the level).</li>
            <li>Band: how far a week usually lands from the baseline; widens slowly with the horizon.</li>
            {[...new Set(fc.flatMap((p) => p.reasons ?? []))].map((r) => <li key={r}>{r}</li>)}
          </ul>
        </div>
        <div>
          <h3>Made of</h3>
          <table className="small">
            <thead><tr><th>Series</th><th className="num">Next week</th><th className="num">Low</th></tr></thead>
            <tbody>
              {parts.map((s) => {
                const p = s.forecast[0];
                const who = s.series.partner_id
                  ? state.partners.find((x) => x.id === s.series.partner_id)?.alias ?? s.series.partner_id
                  : "Households (pooled)";
                return <tr key={s.key}><td>{who}</td><td className="num">{kg(p.expected)}</td><td className="num">{kg(p.low)}</td></tr>;
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
