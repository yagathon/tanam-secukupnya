"use client";

import type { TabProps } from "@/app/page";
import { int, kg, lineName, shortDate, tsp } from "@/lib/format";
import type { SowLine } from "@/lib/types";

function LineSow({ s }: { s: SowLine }) {
  const ahead = s.shortfall_ahead.reduce((a, r) => a + r.kg, 0);
  return (
    <div className="card">
      <h2>{lineName(s.line)} · sow on {shortDate(s.day)}</h2>
      <div className="kpis">
        <div><span className="small muted">Seedlings</span><strong>{int(s.seedlings)}</strong></div>
        <div><span className="small muted">Seed</span><strong>≈ {s.seeds_g.toFixed(1)} g</strong></div>
        <div><span className="small muted">Measure</span><strong>≈ {tsp(s.teaspoons)}</strong></div>
        <div><span className="small muted">Ready</span><strong>{shortDate(s.ready_from)} – {shortDate(s.covers_until)}</strong></div>
      </div>
      <table>
        <tbody>
          <tr><td>Gap this batch must fill</td><td className="num">{kg(s.gap_kg)}</td></tr>
          <tr><td>Need used</td><td className="num">{s.basis.need}</td></tr>
          <tr><td>Seedlings that make it to harvest</td><td className="num">{Math.round(s.basis.survival * 100)}%</td></tr>
          <tr><td>Seeds that germinate</td><td className="num">{Math.round(s.basis.germination * 100)}%</td></tr>
          <tr><td>Seeds per gram · grams per teaspoon</td><td className="num">{s.basis.seeds_per_gram} · {s.basis.grams_per_teaspoon}</td></tr>
        </tbody>
      </table>
      {s.capped && <p className="bad">Capped at the farm&rsquo;s limit of {int(s.basis.max_seedlings)} seedlings per sowing.</p>}
      {(s.missed.length > 0 || s.postponed.length > 0) && (
        <>
          <h3>Missed sowings</h3>
          <ul>
            {s.postponed.map((p) => <li key={p.day}>{shortDate(p.day)}: postponed ({p.reason})</li>)}
            {s.missed.filter((d) => !s.postponed.some((p) => p.day === d)).map((d) => <li key={d}>{shortDate(d)}: no sowing recorded</li>)}
          </ul>
          <p className="small muted">This sowing grows to cover what the missed batch would have covered.</p>
        </>
      )}
      {ahead > 0.005 && (
        <>
          <h3 className="bad">Short ahead: {kg(ahead)}</h3>
          <p className="small muted">Days no sowing can reach in time any more (even picking 3 days early or late):</p>
          <ul>{s.shortfall_ahead.map((r) => <li key={r.day}>{shortDate(r.day)}: {kg(r.kg)}</li>)}</ul>
        </>
      )}
    </div>
  );
}

export default function SowTab({ data }: TabProps) {
  return (
    <div className="grid">
      <p className="muted small">We sow twice a week, on Mondays and Thursdays. Each sowing covers the days until the next one is ready.</p>
      {data.sow.lines.map((s) => <LineSow key={s.line} s={s} />)}
    </div>
  );
}
