"use client";

import { useEffect, useState } from "react";
import { Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { api } from "@/lib/api";
import { friendly, int, shortDate } from "@/lib/format";
import type { Season, SeasonMetrics, Strategy } from "@/lib/types";

const NAMES: Record<Strategy, string> = { cobweb: "Cobweb farmer", fixed: "Fixed farmer", tanam: "Tanam Secukupnya" };
const RULES: Record<Strategy, string> = {
  cobweb: "Sows more after a short week, less after a surplus week",
  fixed: "The same seedlings every Monday and Thursday",
  tanam: "This app: sows to the forecast, harvests up to the safe maximum",
};
const COLORS: Record<Strategy, string> = { cobweb: "var(--bad)", fixed: "var(--warn)", tanam: "var(--leaf)" };
const ORDER: Strategy[] = ["cobweb", "fixed", "tanam"];
const METRICS: { key: keyof SeasonMetrics; label: string; better: "low" | "high"; fmt: (n: number) => string }[] = [
  { key: "waste_pct", label: "Waste", better: "low", fmt: (n) => `${n.toFixed(1)}%` },
  { key: "b2b_fill_pct", label: "Restaurant orders filled", better: "high", fmt: (n) => `${n.toFixed(1)}%` },
  { key: "hh_fill_pct", label: "Household orders filled", better: "high", fmt: (n) => `${n.toFixed(1)}%` },
  { key: "sowing_cv", label: "Swing in sowing (CV)", better: "low", fmt: (n) => n.toFixed(2) },
];

export default function SeasonTab() {
  const [s, setS] = useState<Season | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.season().then(setS).catch((e) => setError(friendly(e)));
  }, []);
  if (error) return <div className="card error">{error}</div>;
  if (!s) return <div className="card muted">Loading the season…</div>;
  if (!s.runs.length) return <div className="card empty">The season comparison has not been computed (run `just season`).</div>;

  const range = (st: Strategy, k: keyof SeasonMetrics) => {
    const v = s.runs.filter((r) => r.strategy === st).map((r) => r[k]);
    return [Math.min(...v), Math.max(...v)] as const;
  };
  const days = Array.from(new Set(ORDER.flatMap((st) => s.sowings[st].filter((x) => x.line === "regular").map((x) => x.day)))).sort();
  const chart = days.map((d) => {
    const row: Record<string, string | number> = { day: shortDate(d) };
    for (const st of ORDER) {
      const hit = s.sowings[st].find((x) => x.line === "regular" && x.day === d);
      if (hit) row[st] = hit.seedlings;
    }
    return row;
  });

  return (
    <div className="grid">
      <div className="card">
        <h2>{Math.round(s.days / 7)} weeks, three ways to farm</h2>
        <p className="small muted">
          The same simulated farm and buyers, run {s.seeds.length} times with different random seeds. Mean shown, range across
          runs below. Synthetic data; Gemini is not in this loop.
        </p>
        <div className="scroll">
          <table>
            <thead>
              <tr><th>Strategy</th>{METRICS.map((m) => <th key={m.key} className="num">{m.label}</th>)}</tr>
            </thead>
            <tbody>
              {ORDER.map((st) => (
                <tr key={st}>
                  <td className="wrap"><strong style={{ color: COLORS[st] }}>{NAMES[st]}</strong><br /><span className="small muted">{RULES[st]}</span></td>
                  {METRICS.map((m) => {
                    const [lo, hi] = range(st, m.key);
                    return (
                      <td key={m.key} className="num">
                        <strong>{m.fmt(s.summary[st][m.key])}</strong><br />
                        <span className="small muted">{m.fmt(lo)}–{m.fmt(hi)}</span>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="card">
        <h2>Seedlings per sowing (pakcoy regular, seed {s.main_seed})</h2>
        <p className="small muted">The cobweb farmer swings; the fixed farmer never adapts; Tanam follows demand.</p>
        <div style={{ width: "100%", height: 260 }}>
          <ResponsiveContainer>
            <LineChart data={chart}>
              <XAxis dataKey="day" interval="preserveStartEnd" minTickGap={28} tick={{ fontSize: 11 }} />
              <YAxis width={48} tick={{ fontSize: 11 }} tickFormatter={(v: number) => int(v)} />
              <Tooltip formatter={(v) => int(Number(v))} />
              <Legend />
              {ORDER.map((st) => (
                <Line key={st} dataKey={st} name={NAMES[st]} stroke={COLORS[st]} dot={false} strokeWidth={2} connectNulls isAnimationActive={false} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
