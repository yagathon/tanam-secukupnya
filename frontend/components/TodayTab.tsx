"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

import type { TabProps } from "@/app/page";
import { daySentence, friendly, lineName, sowDays } from "@/lib/format";
import { todayActions, type Prefill } from "@/lib/today";

/** `input` is the right-hand card: the sandbox's input panel, or the demo's read-only log. `onAct` (the
 *  sandbox) turns each line into things to do, whose buttons fill that panel's form. */
export default function TodayTab({ data, api, input, onAct }: TabProps & { input: ReactNode; onAct?: (p: Prefill) => void }) {
  const { state, today } = data;
  const [why, setWhy] = useState<{ text: string; failed: boolean } | null>(null);
  const [asking, setAsking] = useState(false);
  const day = useRef(today.today);

  // An explanation belongs to one day: drop it (and any answer still in flight) when the day moves.
  useEffect(() => {
    day.current = today.today;
    setWhy(null);
  }, [today.today]);

  const explain = async () => {
    const asked = today.today;
    setAsking(true);
    setWhy(null);
    try {
      const r = await api.why();
      if (day.current === asked) setWhy({ text: r.text, failed: false });
    } catch (e) {
      if (day.current === asked) setWhy({ text: friendly(e), failed: true });
    } finally {
      setAsking(false);
    }
  };

  return (
    <div className="grid two">
      <div className="card">
        <h2>{today.weekday}</h2>
        {today.lines.map((l) => (
          <div key={l.line} className="card">
            <h3>{lineName(l.line)}</h3>
            {!onAct && <p className={`sentence ${l.short_kg > 0.005 ? "bad" : ""}`}>{daySentence(l)}</p>}
            {onAct && todayActions(l, today.today).map((a) => (
              <div key={a.kind} className={`act ${a.kind} ${a.prefill.length === 0 && a.kind === "sow" ? "info" : ""} ${a.done ? "done" : ""}`}>
                <p className="act-title">{a.done ? "✓ " : ""}{a.title}</p>
                {a.lines.length > 0 && <ul className="small">{a.lines.map((t) => <li key={t}>{t}</li>)}</ul>}
                {!a.done && a.prefill.length > 0 && <div className="row wrap">
                  {a.prefill.map((p) => <button key={p.label} className="small" onClick={() => onAct(p)}>
                    {p.kind === "harvest" ? `Log ${p.label}` : p.label}</button>)}
                </div>}
              </div>
            ))}
          </div>
        ))}
        <div className="row wrap">
          <button disabled={asking} onClick={explain}>{asking ? "Asking Gemini…" : "Why?"}</button>
          <span className="small muted">Gemini explains today&apos;s numbers in plain words. The engine decides; Gemini only explains.</span>
        </div>
        {why && <p className={`small ${why.failed ? "bad" : "why"}`}>{why.text}</p>}
        {onAct && <p className="small muted">Looking back? <strong>Trail</strong> shows every earlier day: what was advised that
          morning and what you logged.</p>}
        {!onAct && <p className="small muted">
          Press <strong>Next day →</strong> to let the farm live one day: orders arrive, the farmer harvests and samples, and
          sowing happens {sowDays(state.crop.sow_weekdays ?? [0, 3])}.
        </p>}
      </div>

      {input}
    </div>
  );
}
