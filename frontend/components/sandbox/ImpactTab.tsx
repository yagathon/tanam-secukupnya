"use client";

import { useEffect, useState } from "react";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { TabProps } from "@/app/page";
import { friendly, shortDate } from "@/lib/format";
import { impactHeadline } from "@/lib/impact";
import type { Impact, ImpactRow } from "@/lib/types";

const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const n = (x: number) => Math.round(x).toLocaleString("en-US");

/** Tanam's sizing against the old habit, replayed on the same orders, harvests and losses. */
export default function ImpactTab({ data, api }: TabProps) {
  const [d, setD] = useState<Impact | null>(null);
  const [error, setError] = useState<string | null>(null);
  const key = `${data.today.today}/${data.today.seq}`;          // refetch whenever a day closes or an entry lands

  useEffect(() => {
    let live = true;
    api.impact().then((x) => live && setD(x)).catch((e) => live && setError(friendly(e)));
    return () => { live = false; };
  }, [api, key]);

  if (error) return <div className="card error">{error}</div>;
  if (!d) return <div className="card"><p className="muted">Replaying the old habit…</p></div>;

  const habit = `${n(d.habit.seedlings)} seedlings every ${WEEKDAYS[d.habit.weekday]}`;
  const rows: [string, ImpactRow][] = [
    ["Before Tanam (beds from setup)", d.rows.before],
    ["With Tanam", d.rows.tanam],
    [`Old habit: ${habit} (simulated)`, d.rows.habit],
  ];

  return (
    <>
      <div className="card">
        <h2>Food loss</h2>
        <p><strong>{impactHeadline(d.rows, d.delivery, d.habit.seedlings)}</strong></p>
        <div className="scroll">
          <table>
            <thead>
              <tr><th>Beds</th><th>Count</th><th>Seedlings</th><th>Harvested</th><th>Lost</th><th>Wasted (oversize)</th>
                <th>Still in field</th><th>Waste %</th><th>Delivered</th></tr>
            </thead>
            <tbody>
              {rows.map(([label, r]) => (
                <tr key={label}>
                  <td>{label}</td><td>{r.beds}</td><td>{n(r.seedlings)}</td><td>{n(r.harvested_plants)}</td>
                  <td>{n(r.lost_plants)}</td><td className={r.waste_plants > 0 ? "neg" : ""}>{n(r.waste_plants)}</td>
                  <td>{n(r.in_field_plants)}</td><td>{r.waste_pct.toFixed(1)}%</td><td>{r.delivered_kg.toFixed(1)} kg</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="small muted">
          Plants, not kg. Wasted = grew past selling size before anyone cut it. Lost = pest, weather, or gone when you
          looked (Left in bed). Waste % = wasted ÷ (harvested + wasted). Still in field = not decided yet: those plants
          may still sell or still go to waste.
        </p>
      </div>

      <div className="card">
        <h2>Plants wasted so far</h2>
        <div style={{ width: "100%", height: 240 }}>
          <ResponsiveContainer>
            <LineChart data={d.series.map((s) => ({ ...s, label: shortDate(s.day) }))}>
              <XAxis dataKey="label" interval="preserveStartEnd" minTickGap={28} tick={{ fontSize: 11 }} />
              <YAxis width={48} tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v) => `${n(Number(v))} plants`} />
              <Line isAnimationActive={false} dataKey="habit_waste" name="Old habit" stroke="var(--bad)" dot={false} strokeWidth={2} />
              <Line isAnimationActive={false} dataKey="tanam_waste" name="Tanam" stroke="var(--leaf)" dot={false} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div className="legend">
          <span><i style={{ background: "var(--bad)" }} />old habit ({habit})</span>
          <span><i style={{ background: "var(--leaf)" }} />Tanam</span>
        </div>
        <p className="small muted">
          Both lines start with the beds from setup, so they share that waste; the gap after is the sowing. The old
          habit is a replay, not a guess: the same days, orders, harvests (oldest bed first) and losses you logged, on
          the same growth model, with {habit} instead of Tanam&apos;s amounts.
          {d.delivery.habit_short_kg > 0 && ` It could not cover ${d.delivery.habit_short_kg.toFixed(1)} kg of what you cut.`}
        </p>
      </div>
    </>
  );
}
