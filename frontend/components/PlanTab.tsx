"use client";

import { useState } from "react";

import type { Data } from "@/lib/types";
import LinePicker, { firstLine } from "@/components/LinePicker";
import { kg, shortDate } from "@/lib/series";

const STATUS_LABEL = {
  covered: "covered",
  sow: "to sow",
  surplus: "surplus",
  bridge: "bridge",
  shortfall: "shortfall",
} as const;

export default function PlanTab({ data }: { data: Data }) {
  const { state, plans } = data;
  const [key, setKey] = useState(firstLine(state.crops));
  const plan = plans.find((p) => `${p.crop}/${p.line}` === key);
  const farmer = (id: string) => state.farmers.find((f) => f.id === id)?.alias ?? id;
  const sowings = plan?.weeks.filter((w) => w.new_batch) ?? [];
  const nextSow = sowings[0];
  const beds = (n: number) => `${n} bed${n === 1 ? "" : "s"}`;

  return (
    <div className="card">
      <LinePicker crops={state.crops} value={key} onChange={setKey} />
      {plan && (
        <>
          <div className="kpis">
            <div>
              <span className="muted small">Next sowing</span>
              <strong>{nextSow?.new_batch ? `${beds(nextSow.new_batch.beds)} by ${shortDate(nextSow.new_batch.seed_by)}` : "—"}</strong>
            </div>
            <div>
              <span className="muted small">Can borrow from next batch?</span>
              <strong>{plan.borrow_interest === null ? "No" : `Yes, +${Math.round(plan.borrow_interest * 100)}%/week`}</strong>
            </div>
            <div>
              <span className="muted small">Recovery week</span>
              <strong>{plan.recovery_week ? shortDate(plan.recovery_week) : "—"}</strong>
            </div>
          </div>
          {plan.warnings.map((w) => <div key={w} className="card warn small">{w}</div>)}

          <div className="scroll">
            <table className="plan small">
              <thead>
                <tr>
                  <th>Harvest week</th><th className="num">Target</th><th className="num">In the ground</th>
                  <th className="num">Net</th><th>Status</th><th>New batch / what happens</th>
                </tr>
              </thead>
              <tbody>
                {plan.weeks.map((w) => (
                  <tr key={w.week} className={w.frozen ? "frozen" : ""}>
                    <td>{shortDate(w.week)}{w.frozen && <span className="muted"> · too late to sow</span>}</td>
                    <td className="num">{kg(w.target_kg)}</td>
                    <td className="num">{kg(w.in_ground_kg)}</td>
                    <td className={`num ${w.net_kg > 0 ? "neg" : ""}`}>{w.net_kg > 0 ? "−" : "+"}{kg(Math.abs(w.net_kg))}</td>
                    <td><span className={`pill st-${w.status}`}>{STATUS_LABEL[w.status]}</span></td>
                    <td>
                      {w.new_batch && (
                        <div>
                          <strong>{beds(w.new_batch.beds)}</strong>: seed by {shortDate(w.new_batch.seed_by)}, transplant{" "}
                          {shortDate(w.new_batch.transplant_on)}, harvest {shortDate(w.new_batch.harvest_on)}
                          <div className="muted">
                            {w.new_batch.farmers.map((f) => `${farmer(f.farmer_id)}: ${beds(f.beds)}, ${kg(f.guaranteed_kg)} guaranteed`).join(" · ")}
                          </div>
                        </div>
                      )}
                      {w.notes.map((n) => <div key={n} className="muted">{n}</div>)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {nextSow?.new_batch && (
            <div className="card message">
              <h3>Message to {farmer(nextSow.new_batch.farmers[0].farmer_id)}</h3>
              <p className="muted small">The WhatsApp message in Bahasa (G3) arrives with the Gemini setup.</p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
