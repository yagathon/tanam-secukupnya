"use client";

import { Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { Reference } from "@/lib/types";

/** The growth curve as entered, and the reference the samples have moved it to (model B: per node). */
export default function CurveChart({ start, reference }: { start: [number, number][]; reference?: Reference }) {
  const rows = new Map<number, { day: number; start?: number; now?: number; samples?: number }>();
  for (const [d, g] of start) rows.set(d, { day: d, start: g });
  reference?.now.forEach(([d, g], i) => rows.set(d, { ...rows.get(d), day: d, now: g, samples: reference.samples[i] ?? 0 }));
  const data = [...rows.values()].sort((a, b) => a.day - b.day);
  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -8 }}>
        <XAxis dataKey="day" type="number" domain={["dataMin", "dataMax"]} unit=" d" fontSize={12} />
        <YAxis unit=" g" fontSize={12} />
        <Tooltip formatter={(v, name, item) => {
          const s = (item?.payload as { samples?: number } | undefined)?.samples;
          return [`${Number(v).toFixed(1)} g${name === "learned now" && s !== undefined ? ` · ${s} samples` : ""}`, name];
        }} labelFormatter={(d) => `bed day ${d}`} />
        <Legend />
        <Line dataKey="start" name="starting curve" stroke="var(--muted)" strokeDasharray="4 3" dot connectNulls isAnimationActive={false} />
        {reference && <Line dataKey="now" name="learned now" stroke="var(--leaf)" dot connectNulls isAnimationActive={false} />}
      </LineChart>
    </ResponsiveContainer>
  );
}
