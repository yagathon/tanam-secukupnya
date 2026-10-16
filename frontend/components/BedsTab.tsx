"use client";

import { Area, Bar, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { TabProps } from "@/app/page";
import { int, kg, lineName, shortDate } from "@/lib/format";
import type { BedsLine } from "@/lib/types";

function LineBeds({ l }: { l: BedsLine }) {
  const shortDays = l.chart.filter((d) => d.short_kg > 0.005);
  const rows = l.batches.filter((b) => b.stage === "nursery" || b.plants_left > 0 || b.waste_plants > 0);
  return (
    <div className="card">
      <h2>{lineName(l.line)} <span className="muted small">sells at {l.min_g}–{l.max_g} g a plant{l.stretch_g && l.stretch_g > l.max_g ? ` (up to ${l.stretch_g} g if short)` : ""}</span></h2>
      <p className="small muted">
        Next 40 days: kg ready in range each day vs. the need we protect (B2B expected + households low).
        {shortDays.length > 0 && <span className="bad"> {shortDays.length} day(s) short.</span>}
      </p>
      <div style={{ width: "100%", height: 220 }}>
        <ResponsiveContainer>
          <ComposedChart data={l.chart.map((d) => ({ ...d, label: shortDate(d.day) }))}>
            <XAxis dataKey="label" interval="preserveStartEnd" minTickGap={28} tick={{ fontSize: 11 }} />
            <YAxis width={40} tick={{ fontSize: 11 }} />
            <Tooltip formatter={(v) => kg(Number(v))} />
            <Area isAnimationActive={false} dataKey="available_kg" name="Ready" fill="var(--leaf-soft)" stroke="var(--leaf)" />
            <Line isAnimationActive={false} dataKey="need_kg" name="Need" stroke="var(--soil)" dot={false} strokeWidth={2} />
            <Bar isAnimationActive={false} dataKey="short_kg" name="Short" fill="var(--bad)" />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div className="legend">
        <span><i style={{ background: "var(--leaf)" }} />ready</span>
        <span><i style={{ background: "var(--soil)" }} />need</span>
        <span><i style={{ background: "var(--bad)" }} />short</span>
      </div>

      <h3>Batches ({rows.length})</h3>
      {rows.length === 0 ? (
        <p className="empty">Nothing in the nursery or the beds for this line.</p>
      ) : (
        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th>Bed</th><th>Sown</th><th className="num">Bed day</th><th className="num">Plants left</th>
                <th className="num">Avg g</th><th className="num">Size</th><th>Ready</th>
                <th className="num">Tomorrow</th><th className="num">Wasted</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((b) => (
                <tr key={b.id}>
                  <td>{b.label}{b.stage === "nursery" && <span className="pill muted">nursery</span>}</td>
                  <td>{shortDate(b.sown_on)}</td>
                  <td className="num">{b.bed_day}</td>
                  <td className="num">{int(b.plants_left)}</td>
                  <td className="num">{b.avg_g ?? "—"}</td>
                  <td className="num" title={b.sampled ? "from the farmer's 5+5 sample" : "crop default"}>
                    {b.size_pct}%{b.sampled ? " ✓" : ""}
                  </td>
                  <td>{shortDate(b.ready_from)} – {shortDate(b.until)}</td>
                  <td className="num">{kg(b.available_tomorrow_kg)}</td>
                  <td className={`num ${b.waste_plants > 0 ? "neg" : ""}`}>{int(b.waste_plants)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="small muted">
        Size: this bed’s plants vs the reference curve (100% = on curve, lower = stunted or crowded); ✓ = corrected by a harvest sample. Quick field estimate: assumes
        sizes spread evenly between the small and big groups.
      </p>
    </div>
  );
}

export default function BedsTab({ data }: TabProps) {
  return <div className="grid">{data.beds.lines.map((l) => <LineBeds key={l.line} l={l} />)}</div>;
}
