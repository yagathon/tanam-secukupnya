"use client";

import { useCallback, useEffect, useState } from "react";

import CommitmentsTab from "@/components/CommitmentsTab";
import ForecastTab from "@/components/ForecastTab";
import InputsTab from "@/components/InputsTab";
import PlanTab from "@/components/PlanTab";
import ScenarioTab from "@/components/ScenarioTab";
import { api } from "@/lib/api";
import { shortDate } from "@/lib/series";
import type { Data } from "@/lib/types";

const TABS = [
  { id: "inputs", label: "Inputs", hint: "History and notes from the field" },
  { id: "forecast", label: "Forecast", hint: "Expected demand with an honest band" },
  { id: "commitments", label: "Commitments", hint: "Who is promised what" },
  { id: "plan", label: "Sowing plan", hint: "What to sow, where, by when" },
  { id: "scenario", label: "Harvest scenario", hint: "When the harvest falls short" },
] as const;
type TabId = (typeof TABS)[number]["id"];

export default function Home() {
  const [tab, setTab] = useState<TabId>("inputs");
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [state, fc, plan] = await Promise.all([api.state(), api.forecast(), api.plan()]);
      setData({ state, series: fc.series, plans: plan.plans });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    const fromHash = window.location.hash.slice(1) as TabId;
    if (TABS.some((t) => t.id === fromHash)) setTab(fromHash);
    load();
  }, [load]);

  const go = (id: TabId) => {
    setTab(id);
    history.replaceState(null, "", `#${id}`);
  };

  const i = TABS.findIndex((t) => t.id === tab);

  return (
    <main className="shell">
      <header className="top">
        <div>
          <h1>Tanam Secukupnya</h1>
          <p className="sub">Plant just enough — a sowing planner that breaks the oversupply cycle</p>
        </div>
        {data && (
          <div className="today">
            Today <strong>{shortDate(data.state.today)}</strong>
            {data.state.synthetic && <span className="pill muted">synthetic data</span>}
          </div>
        )}
      </header>

      <nav className="steps" aria-label="Steps">
        {TABS.map((t, n) => (
          <button key={t.id} className={`step ${t.id === tab ? "on" : ""}`} onClick={() => go(t.id)}>
            <span className="num">{n + 1}</span>
            <span className="label">{t.label}</span>
          </button>
        ))}
      </nav>
      <p className="hint">{TABS[i].hint}</p>

      {error && (
        <div className="card error">
          Could not reach the API: {error}
          <button onClick={load}>Retry</button>
        </div>
      )}
      {!data && !error && <div className="card muted">Loading…</div>}

      {data && (
        <section>
          {tab === "inputs" && <InputsTab data={data} onChange={load} />}
          {tab === "forecast" && <ForecastTab data={data} />}
          {tab === "commitments" && <CommitmentsTab data={data} />}
          {tab === "plan" && <PlanTab data={data} />}
          {tab === "scenario" && <ScenarioTab data={data} />}
        </section>
      )}

      {data && (
        <footer className="pager">
          <button disabled={i === 0} onClick={() => go(TABS[i - 1].id)}>
            ← {i > 0 ? TABS[i - 1].label : ""}
          </button>
          <button disabled={i === TABS.length - 1} onClick={() => go(TABS[i + 1].id)}>
            {i < TABS.length - 1 ? TABS[i + 1].label : ""} →
          </button>
        </footer>
      )}
    </main>
  );
}
