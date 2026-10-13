"use client";

import { useState } from "react";
import { Line, LineChart, ResponsiveContainer, Tooltip, YAxis } from "recharts";

import type { Data } from "@/lib/types";
import { aggregate, kg, shortDate } from "@/lib/series";

const EXAMPLE = "bu, resto A minggu depan pakcoy kurangin dulu ya separo, lg renovasi dapur";

export default function InputsTab({ data }: { data: Data }) {
  const { state, series } = data;
  const [note, setNote] = useState("");

  return (
    <div className="grid two">
      <div className="card">
        <h2>Demand history</h2>
        <p className="muted small">Weekly kg ordered, last {state.crops.length && series[0]?.history.length} weeks</p>
        <div className="sparks">
          {state.crops.flatMap((c) =>
            c.demand_lines.map((l) => {
              const pts = aggregate(series, c.id, l.id).filter((p) => p.history !== undefined);
              const last4 = pts.slice(-4).reduce((s, p) => s + (p.history ?? 0), 0) / 4;
              return (
                <div key={`${c.id}/${l.id}`} className="spark">
                  <div>
                    <strong>{c.name}</strong> <span className="muted">{l.id}</span>
                    <div className="muted small">{kg(last4)}/week (last 4)</div>
                  </div>
                  <ResponsiveContainer width="100%" height={48}>
                    <LineChart data={pts}>
                      <YAxis hide domain={[0, "auto"]} />
                      <Tooltip formatter={(v) => kg(Number(v))} labelFormatter={(_, p) => shortDate(p[0]?.payload.week ?? "")} />
                      <Line dataKey="history" stroke="var(--leaf)" dot={false} strokeWidth={1.5} isAnimationActive={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              );
            }),
          )}
        </div>
      </div>

      <div className="card">
        <h2>Notes inbox</h2>
        <p className="muted small">
          Paste a WhatsApp note from a partner or farmer, in Bahasa as it was written. Gemini turns it into a
          demand signal or a harvest issue, with its reason, for you to accept.
        </p>
        <textarea rows={4} value={note} placeholder={EXAMPLE} onChange={(e) => setNote(e.target.value)} />
        <div className="row">
          <button disabled title="Arrives with the Gemini setup (G1)">Understand note</button>
          <button className="ghost" onClick={() => setNote(EXAMPLE)}>Use example</button>
        </div>
        <p className="muted small">Note understanding (G1) arrives with the Gemini setup.</p>

        <h3>Signals</h3>
        {state.signals.length === 0 ? (
          <p className="muted small">No signals yet. Accepted notes and calendar events show up here.</p>
        ) : (
          <ul className="signals">
            {state.signals.map((s) => (
              <li key={s.id}>
                <span className={`pill ${s.effect_pct < 0 ? "down" : "up"}`}>{s.effect_pct > 0 ? "+" : ""}{s.effect_pct}%</span>{" "}
                {s.cause} <span className="muted small">({s.scope}, {shortDate(s.week_from)}–{shortDate(s.week_to)}, {s.source})</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
