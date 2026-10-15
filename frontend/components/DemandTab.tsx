"use client";

import { Area, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { TabProps } from "@/app/page";
import { kg, lineName, scopeName, shortDate } from "@/lib/format";

export default function DemandTab({ data }: TabProps) {
  const { demand, state } = data;
  return (
    <div className="grid">
      <div className="card">
        <h2>Market</h2>
        <p className={demand.market.factor !== 1 ? "bad" : ""}>{demand.market.text}</p>
        <p className="small muted">
          Recomputed every day from the last 7 days of restaurant orders. It moves every forecast, including buyers who haven&rsquo;t
          ordered yet and households.
        </p>
      </div>

      {demand.lines.map((l) => (
        <div key={l.line} className="card">
          <h2>{lineName(l.line)}: next {l.days.length} days</h2>
          <div style={{ width: "100%", height: 220 }}>
            <ResponsiveContainer>
              <ComposedChart data={l.days.map((d) => ({ ...d, label: shortDate(d.day), band: [d.low, d.high] }))}>
                <XAxis dataKey="label" interval="preserveStartEnd" minTickGap={28} tick={{ fontSize: 11 }} />
                <YAxis width={40} tick={{ fontSize: 11 }} />
                <Tooltip formatter={(v) => (Array.isArray(v) ? `${kg(Number(v[0]))} – ${kg(Number(v[1]))}` : kg(Number(v)))} />
                <Area dataKey="band" name="Low–high" fill="var(--leaf-soft)" stroke="none" isAnimationActive={false} />
                <Line dataKey="expected" name="Expected" stroke="var(--leaf)" dot={false} strokeWidth={2} isAnimationActive={false} />
                <Line dataKey="target" name="Sowing target" stroke="var(--sky)" dot={false} strokeDasharray="4 3" isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <div className="legend">
            <span><i style={{ background: "var(--leaf-soft)" }} />band (80%)</span>
            <span><i style={{ background: "var(--leaf)" }} />expected</span>
            <span><i style={{ background: "var(--sky)" }} />sowing target (B2B high + households high)</span>
          </div>
        </div>
      ))}

      <div className="card">
        <h2>Buyers: usual vs. now</h2>
        <p className="small muted">The weekday shape is fixed; only the level moves. Three orders in a row on the same side move it fast.</p>
        <div className="scroll">
          <table>
            <thead><tr><th>Series</th><th>Line</th><th className="num">Usual / day</th><th className="num">Now / day</th></tr></thead>
            <tbody>
              {demand.series.map((s) => {
                const d = s.level_kg - s.usual_kg;
                const moved = Math.abs(d) > 0.1 * Math.max(s.usual_kg, 0.01);
                return (
                  <tr key={s.key}>
                    <td className="wrap">{s.label}</td>
                    <td>{s.line}</td>
                    <td className="num">{kg(s.usual_kg)}</td>
                    <td className={`num ${moved && d < 0 ? "neg" : ""}`}>{kg(s.level_kg)} {moved ? (d < 0 ? "↓" : "↑") : ""}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <h2>Accepted signals</h2>
        {demand.signals.length === 0 ? <p className="empty">None yet. A note like “bulan depan pesanan dobel” becomes one.</p> : (
          <ul className="signals">
            {demand.signals.map((s, i) => (
              <li key={i}>
                <span className={`pill ${s.effect_pct < 0 ? "down" : "up"}`}>{s.effect_pct > 0 ? "+" : ""}{s.effect_pct}%</span>{" "}
                {scopeName(s.scope, state)}, {s.line ? lineName(s.line) : "all lines"}{" "}
                <span className="muted small">{shortDate(s.date_from)} – {shortDate(s.date_to)} · {s.cause}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
