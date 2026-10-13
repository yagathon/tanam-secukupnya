"use client";

import { useEffect, useState } from "react";

import type { Data } from "@/lib/types";
import { api } from "@/lib/api";
import { kg, shortDate } from "@/lib/series";
import type { HarvestIssue, Scenario } from "@/lib/types";

export default function ScenarioTab({ data }: { data: Data }) {
  const { state, plans } = data;
  const [crop, setCrop] = useState(state.crops[0].id);
  const weeks = [...new Set(plans.filter((p) => p.crop === crop).flatMap((p) => p.weeks.filter((w) => w.frozen).map((w) => w.week)))].sort();
  const [picked, setWeek] = useState<string>();
  const week = picked && weeks.includes(picked) ? picked : weeks[0];
  const [pct, setPct] = useState(70);
  const [result, setResult] = useState<Scenario | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!week) return;
    const t = setTimeout(() => {
      api.scenario(crop, week, pct).then(setResult, (e) => setError(String(e)));
    }, 200);
    return () => clearTimeout(t);
  }, [crop, week, pct]);

  // A farmer's loss hits only their share; the scenario slider is the whole crop's harvest that week.
  const issues = state.notes.filter((n) => n.kind === "harvest_issue" && n.accepted && n.harvest_issue);
  const applyIssue = (h: HarvestIssue) => {
    const total = state.farmers.reduce((t, f) => t + (f.beds[h.crop] ?? 0), 0);
    const mine = state.farmers.find((f) => f.id === h.farmer_id)?.beds[h.crop] ?? 0;
    setCrop(h.crop);
    const cw = [...new Set(plans.filter((p) => p.crop === h.crop).flatMap((p) => p.weeks.filter((w) => w.frozen).map((w) => w.week)))].sort();
    setWeek(h.harvest_week && cw.includes(h.harvest_week) ? h.harvest_week : cw[0]);
    setPct(Math.max(0, Math.round((100 - (h.loss_pct * mine) / Math.max(1, total)) / 5) * 5));
  };

  const name = (id: string) =>
    state.partners.find((p) => p.id === id)?.alias ?? state.households.find((h) => h.id === id)?.alias ?? id;
  const short = (r: { ordered_kg: number; served_kg: number }) => Math.round((r.ordered_kg - r.served_kg) * 100) / 100;

  return (
    <div className="card">
      <div className="row wrap">
        <label>Crop{" "}
          <select value={crop} onChange={(e) => setCrop(e.target.value)}>
            {state.crops.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </label>
        <label>Harvest week{" "}
          <select value={week} onChange={(e) => setWeek(e.target.value)}>
            {weeks.map((w) => <option key={w} value={w}>{shortDate(w)}</option>)}
          </select>
        </label>
        <label className="grow">Harvest comes in at <strong>{pct}%</strong> of expected
          <input type="range" min={0} max={130} step={5} value={pct} onChange={(e) => setPct(Number(e.target.value))} />
        </label>
      </div>
      {issues.length === 0 ? (
        <p className="muted small">Or accept a farmer&apos;s harvest note in step 1 and play it out here.</p>
      ) : (
        <div className="row wrap small">
          <span className="muted">From accepted farmer notes:</span>
          {issues.map((n) => (
            <button key={n.id} className="ghost" onClick={() => applyIssue(n.harvest_issue!)}>
              {n.harvest_issue!.crop === "pakcoy" ? "Pakcoy" : "Sawi putih"} −{n.harvest_issue!.loss_pct}% ({n.harvest_issue!.cause})
            </button>
          ))}
        </div>
      )}
      {error && <div className="card error">{error}</div>}

      {result && (
        <>
          <div className="kpis">
            <div><span className="muted small">Harvested</span><strong>{kg(result.harvested_kg)}</strong></div>
            <div><span className="muted small">Orders served</span><strong>{result.served_pct}%</strong></div>
            <div><span className="muted small">Surplus</span><strong>{kg(result.surplus_kg)}</strong></div>
            <div><span className="muted small">Waste</span><strong>{kg(result.waste_kg)}</strong></div>
            <div><span className="muted small">Different size than asked</span><strong>{kg(result.preference_miss_kg)}</strong></div>
          </div>

          <div className="grid two">
            <div>
              <h3>Partners (B2B)</h3>
              <table className="small">
                <thead><tr><th>Partner</th><th>Line</th><th className="num">Ordered</th><th className="num">Served</th><th className="num">Short</th></tr></thead>
                <tbody>
                  {result.partners.map((r) => (
                    <tr key={r.customer_id + r.line}>
                      <td>{name(r.customer_id)}</td><td>{r.line}</td><td className="num">{kg(r.ordered_kg)}</td>
                      <td className="num">{kg(r.served_kg)}</td><td className={`num ${short(r) > 0 ? "neg" : ""}`}>{short(r) > 0 ? kg(short(r)) : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div>
              <h3>Households (B2C)</h3>
              {result.shorted_households.length === 0 ? (
                <p className="muted small">Every household gets its full basket.</p>
              ) : (
                <>
                  <p className="small">
                    Shorted this week, in rotation (nobody two weeks in a row when it can be avoided):
                  </p>
                  <ul className="small">
                    {result.households.filter((h) => short(h) > 0).map((h) => (
                      <li key={h.customer_id + h.line}>{name(h.customer_id)} — {h.line}, short {kg(short(h))} of {kg(h.ordered_kg)}</li>
                    ))}
                  </ul>
                  <p className="muted small">Apology messages in Bahasa (G4) arrive with the Gemini setup.</p>
                </>
              )}
              {result.cross_fills.length > 0 && (
                <>
                  <h3>Adjustments</h3>
                  <ul className="small">{result.cross_fills.map((c) => <li key={c.from_line + c.to_line + c.channel}>{kg(c.kg)}: {c.reason}</li>)}</ul>
                </>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
