"use client";

import { useEffect, useState } from "react";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { TabProps } from "@/app/page";
import { friendly } from "@/lib/format";
import { bedBarName, impactHeadline } from "@/lib/impact";
import type { Impact, ImpactBed, ImpactRow } from "@/lib/types";

const n = (x: number) => Math.round(x).toLocaleString("en-US");
const PARTS = [
  { key: "harvested", name: "harvested for buyers", color: "var(--leaf)" },
  { key: "lost", name: "lost (pest, weather, recount)", color: "var(--soil)" },
  { key: "waste", name: "waste: outgrew, sold cheap to the middleman", color: "var(--bad)" },
  { key: "growing", name: "still growing", color: "var(--line)" },
] as const;

/** One stacked bar per bed. A bed cut in time is all green; red is what it still held the day it outgrew. */
function BedBars({ beds, lines, top }: { beds: ImpactBed[]; lines: number; top: number }) {
  const rows = beds.map((b) => ({ ...b, name: bedBarName(b, lines) }));
  return (
    <div style={{ width: "100%", height: 220 }}>
      <ResponsiveContainer>
        <BarChart data={rows}>
          <XAxis dataKey="name" interval="preserveStartEnd" minTickGap={8} tick={{ fontSize: 11 }} />
          <YAxis width={48} tick={{ fontSize: 11 }} domain={[0, top]} allowDataOverflow />
          <Tooltip formatter={(v, name) => [`${n(Number(v))} plants`, name]} />
          {PARTS.map((p) => (
            <Bar key={p.key} isAnimationActive={false} dataKey={p.key} name={p.name} stackId="bed" fill={p.color} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

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
  if (!d.days) return <div className="card empty">Nothing to compare yet: press <strong>Next day →</strong> to run the farm forward.</div>;

  const habit = d.habit.label;
  const rows: [string, ImpactRow][] = [
    ["Before Tanam (beds from setup)", d.rows.before],
    ["With Tanam", d.rows.tanam],
    [`Old habit: ${habit} (simulated)`, d.rows.habit],
  ];

  const farm = d.beds.filter((b) => b.group !== "habit");
  const sim = d.beds.filter((b) => b.group === "habit");
  const lines = new Set(d.beds.map((b) => b.line)).size;
  const top = Math.max(1, ...d.beds.map((b) => b.harvested + b.lost + b.waste + b.growing));  // same scale both panels

  return (
    <>
      <div className="card">
        <h2>Food loss</h2>
        <p><strong>{impactHeadline(d.rows, d.delivery, habit)}</strong></p>
        <div className="scroll">
          <table>
            <thead>
              <tr><th>Beds</th><th>Count</th><th>Seedlings</th><th>Harvested</th><th>Lost</th><th>Wasted (to middleman)</th>
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
          Plants, not kg. Wasted = still in a bed the morning it outgrew what buyers take. Lost = pest, weather, or gone when you
          looked (Left in bed). Waste % = wasted ÷ (harvested + wasted). Still in field = not decided yet: those plants
          may still sell or still go to waste.
        </p>
      </div>

      <div className="card">
        <h2>Every bed: where its plants went</h2>
        <h3>With Tanam · waste {n(d.rows.tanam.waste_plants)} plants (beds from setup*: {n(d.rows.before.waste_plants)})</h3>
        <BedBars beds={farm} lines={lines} top={top} />
        <h3>Old habit, {habit} · waste {n(d.rows.habit.waste_plants)} plants</h3>
        <BedBars beds={sim} lines={lines} top={top} />
        <div className="legend">
          {PARTS.map((p) => <span key={p.key}><i style={{ background: p.color }} />{p.name}</span>)}
        </div>
        <p className="small muted">
          One bar per bed, in plants. A bed closes the morning its average plant is past the heaviest any buyer takes
          (stretch size): what it still holds goes to the middleman cheap, counted as food waste, and the bed is free
          for a new sowing. A bed cut empty before that wastes nothing. * = beds from setup, before Tanam. The old habit
          is a replay on the same days, orders, harvests (oldest open bed first) and losses as logged.
          {d.delivery.habit_short_kg > 0 && ` It could not cover ${d.delivery.habit_short_kg.toFixed(1)} kg of what you cut.`}
        </p>
      </div>
    </>
  );
}
