"use client";

import { Area, Bar, BarChart, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { TabProps } from "@/app/page";
import { kg, lineName, scopeName, shortDate } from "@/lib/format";
import type { Season } from "@/lib/types";

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

      {demand.season && <SeasonCard season={demand.season} today={demand.today} />}

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
            <span><i style={{ background: "var(--sky)" }} />sowing target (expected orders, no buffer)</span>
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

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const BLOCKS = ["1–7", "8–14", "15–21", "22–end"];

function Bars({ data, now }: { data: { label: string; x: number }[]; now: string }) {
  return (
    <div style={{ width: "100%", height: 150 }}>
      <ResponsiveContainer>
        <BarChart data={data}>
          <XAxis dataKey="label" tick={{ fontSize: 11 }} interval={0} />
          <YAxis width={36} tick={{ fontSize: 11 }} />
          <Tooltip formatter={(v) => `×${Number(v).toFixed(2)}`} />
          <ReferenceLine y={1} stroke="var(--muted)" strokeDasharray="3 3" />
          <Bar dataKey="x" name="factor" isAnimationActive={false} fill="var(--leaf)"
            shape={(p: { x?: number; y?: number; width?: number; height?: number; payload?: { label: string } }) => (
              <rect x={p.x} y={p.y} width={p.width} height={p.height}
                fill={p.payload?.label === now ? "var(--sky)" : "var(--leaf)"} />)} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/** The setup's season: what the forecast multiplies today's level by, month block × month of the year. */
function SeasonCard({ season, today }: { season: Season; today: string }) {
  const d = new Date(`${today}T00:00:00Z`);
  const block = Math.min(Math.floor((d.getUTCDate() - 1) / 7), 3);
  const now = season.month_pct[block] / 25 * season.year_index[d.getUTCMonth()] / 100;
  return (
    <div className="card">
      <h2>Season</h2>
      <p>Today&apos;s season factor: <strong>×{now.toFixed(2)}</strong>{" "}
        <span className="small muted">({BLOCKS[block]} of the month × {MONTHS[d.getUTCMonth()]})</span></p>
      <div className="grid two">
        <div><p className="small muted">Within a month</p>
          <Bars data={season.month_pct.map((x, i) => ({ label: BLOCKS[i], x: x / 25 }))} now={BLOCKS[block]} /></div>
        <div><p className="small muted">Through the year</p>
          <Bars data={season.year_index.map((x, i) => ({ label: MONTHS[i], x: x / 100 }))} now={MONTHS[d.getUTCMonth()]} /></div>
      </div>
      <p className="small muted">Set in Setup. Orders are divided by this before the level learns, and forecasts multiply it back.</p>
    </div>
  );
}
