"use client";

import { useState } from "react";
import { Line, LineChart, ResponsiveContainer, Tooltip, YAxis } from "recharts";

import { api } from "@/lib/api";
import type { Data, NoteDoc, SignalDoc, State } from "@/lib/types";
import { aggregate, kg, shortDate } from "@/lib/series";

const EXAMPLES: { sender: string; text: string }[] = [
  { sender: "operator", text: "bu, resto A minggu depan pakcoy kurangin dulu ya separo, lg renovasi dapur" },
  { sender: "caterer_c", text: "Info ya bu, tgl 2 sampai 13 november sekolah libur UTS jd katering gak masak. pakcoy sama sawi stop dulu 2 minggu itu" },
  { sender: "farmer_c", text: "Punten teh, sawi minggu payun teu tiasa dipanen sadayana, aya hama, kinten-kinten satengahna" },
  { sender: "cafe_d", text: "Halo kak, invoice bulan september udah ditransfer ya" },
];

export function who(state: State, scope: string): string {
  if (scope === "all") return "Everyone";
  if (scope === "channel:B2C") return "Households";
  if (scope === "channel:B2B") return "All partners";
  const id = scope.replace("partner:", "");
  return state.partners.find((p) => p.id === id)?.alias ?? id;
}

const cropName = (state: State, id?: string | null) => (id ? state.crops.find((c) => c.id === id)?.name ?? id : "all crops");
const senderName = (state: State, id: string) =>
  id === "operator" ? "Operator" : state.partners.find((p) => p.id === id)?.alias ?? state.farmers.find((f) => f.id === id)?.alias ?? id;

function SignalLine({ state, s }: { state: State; s: SignalDoc }) {
  return (
    <>
      <span className={`pill ${s.effect_pct < 0 ? "down" : "up"}`}>{s.effect_pct > 0 ? "+" : ""}{s.effect_pct}%</span>{" "}
      {who(state, s.scope)}, {cropName(state, s.crop)}{" "}
      <span className="muted small">
        {shortDate(s.week_from)}{s.open_ended ? " onward" : s.week_to !== s.week_from ? `–${shortDate(s.week_to)}` : ""} · {s.cause}
      </span>
    </>
  );
}

export default function InputsTab({ data, onChange }: { data: Data; onChange: () => void }) {
  const { state, series } = data;
  const [note, setNote] = useState("");
  const [sender, setSender] = useState("operator");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<NoteDoc | null>(null);
  const [ex, setEx] = useState(0);

  const understand = async () => {
    setBusy(true);
    setError(null);
    try {
      setResult(await api.readNote(note, sender));
      onChange();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  const decide = async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
      onChange();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };
  const live = (id: string) => state.signals.find((s) => s.id === id);
  const liveNote = result && state.notes.find((n) => n.id === result.id);

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
        <label className="small">From{" "}
          <select value={sender} onChange={(e) => setSender(e.target.value)}>
            <option value="operator">Operator</option>
            <optgroup label="Partners">{state.partners.map((p) => <option key={p.id} value={p.id}>{p.alias}</option>)}</optgroup>
            <optgroup label="Farmers">{state.farmers.map((f) => <option key={f.id} value={f.id}>{f.alias}</option>)}</optgroup>
          </select>
        </label>
        <textarea rows={4} maxLength={1000} value={note} placeholder={EXAMPLES[0].text} onChange={(e) => setNote(e.target.value)} />
        <div className="row">
          <button disabled={busy || !note.trim()} onClick={understand}>{busy ? "Reading…" : "Understand note"}</button>
          <button className="ghost" onClick={() => { setNote(EXAMPLES[ex].text); setSender(EXAMPLES[ex].sender); setEx((ex + 1) % EXAMPLES.length); }}>
            Try an example
          </button>
        </div>
        {error && <p className="small neg">{error}</p>}

        {result && (
          <div className="proposal">
            <p className="small"><strong>Gemini read:</strong> {result.summary_en}</p>
            {result.kind === "none" && <p className="muted small">Nothing for the planner here, so no action needed.</p>}
            {result.kind === "signals" && (
              <ul className="signals">
                {(result.signals ?? []).map((s0) => {
                  const s = live(s0.id) ?? s0;
                  return (
                    <li key={s.id}>
                      <SignalLine state={state} s={s} />{" "}
                      {s.status ? <span className="pill muted">{s.status}</span> : (
                        <span className="row inline">
                          <button onClick={() => decide(() => api.decideSignal(s.id, true))}>Accept</button>
                          <button className="ghost" onClick={() => decide(() => api.decideSignal(s.id, false))}>Reject</button>
                        </span>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
            {result.kind === "harvest_issue" && result.harvest_issue && (
              <div className="small">
                <span className="pill down">−{result.harvest_issue.loss_pct}%</span>{" "}
                {senderName(state, result.harvest_issue.farmer_id)}, {cropName(state, result.harvest_issue.crop)}
                {result.harvest_issue.delay_days > 0 && `, ${result.harvest_issue.delay_days} days late`}
                {result.harvest_issue.harvest_week && ` (harvest of ${shortDate(result.harvest_issue.harvest_week)})`}{" "}
                <span className="muted">· {result.harvest_issue.cause}</span>{" "}
                {liveNote?.status === "proposed" ? (
                  <span className="row inline">
                    <button onClick={() => decide(() => api.decideNote(result.id, true))}>Accept</button>
                    <button className="ghost" onClick={() => decide(() => api.decideNote(result.id, false))}>Reject</button>
                  </span>
                ) : <span className="pill muted">{liveNote?.status}</span>}
                {liveNote?.status === "accepted" && <p className="muted">Play it out in step 5, Harvest scenario.</p>}
              </div>
            )}
            <p className="muted small">{result.model}{result.cached ? " · cached" : ""}{result.dropped.length ? ` · dropped: ${result.dropped.join("; ")}` : ""}</p>
          </div>
        )}

        <h3>Accepted signals</h3>
        {state.signals.filter((s) => s.accepted).length === 0 ? (
          <p className="muted small">None yet. Accepted signals move the forecast in step 2.</p>
        ) : (
          <ul className="signals">
            {state.signals.filter((s) => s.accepted).map((s) => (
              <li key={s.id}><SignalLine state={state} s={s} /></li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
