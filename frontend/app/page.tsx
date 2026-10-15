"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";

import TodayTab from "@/components/TodayTab";
import BedsTab from "@/components/BedsTab";
import TomorrowTab from "@/components/TomorrowTab";
import { api } from "@/lib/api";
import { friendly, shortDate } from "@/lib/format";
import type { Data } from "@/lib/types";

export interface TabProps {
  data: Data;
  reload: () => Promise<void>;
}

interface Tab {
  id: string;
  label: string;
  hint: string;
  view: (p: TabProps) => ReactNode;
}

// Each later task adds its tab here, in spec order: Today, Beds, Tomorrow, Sow, Demand, Season.
const TABS: Tab[] = [
  { id: "today", label: "Today", hint: "The day in one line, and notes from the field", view: (p) => <TodayTab {...p} /> },
  { id: "beds", label: "Beds", hint: "What is growing, and how much is ready each day", view: (p) => <BedsTab {...p} /> },
  { id: "tomorrow", label: "Tomorrow", hint: "The most we can safely send, and who gets it", view: (p) => <TomorrowTab {...p} /> },
];

export default function Home() {
  const [tab, setTab] = useState<string>("today");
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [state, today, beds, tomorrow, sow, demand] = await Promise.all([
        api.state(), api.today(), api.beds(), api.tomorrow(), api.sow(), api.demand(),
      ]);
      setData({ state, today, beds, tomorrow, sow, demand });
    } catch (e) {
      setError(friendly(e));
    }
  }, []);

  useEffect(() => {
    const fromHash = window.location.hash.slice(1);
    if (TABS.some((t) => t.id === fromHash)) setTab(fromHash);
    load();
  }, [load]);

  const go = (id: string) => {
    setTab(id);
    history.replaceState(null, "", `#${id}`);
  };

  // A stale from_day (double click, second browser tab) appends nothing: reloading shows the real day.
  const advance = async (days: number) => {
    if (!data) return;
    setBusy(true);
    try {
      await api.nextDay(data.today.today, days);
      await load();
    } catch (e) {
      setError(friendly(e));
    } finally {
      setBusy(false);
    }
  };

  const reset = async () => {
    if (!window.confirm("Reset your demo farm to day 0? Your notes and simulated days are cleared.")) return;
    setBusy(true);
    try {
      await api.reset();
      await load();
    } catch (e) {
      setError(friendly(e));
    } finally {
      setBusy(false);
    }
  };

  const i = Math.max(0, TABS.findIndex((t) => t.id === tab));
  const current = TABS[i];

  return (
    <main className="shell">
      <header className="top">
        <div>
          <h1>Tanam Secukupnya</h1>
          <p className="sub">Plant just enough: a daily planner that keeps a small farm out of the boom-and-bust cycle</p>
        </div>
        {data && (
          <div className="clock">
            <span>
              <strong>{shortDate(data.today.today)}</strong>
            </span>
            {data.state.synthetic && <span className="pill muted">synthetic data</span>}
            <button className="primary" disabled={busy} onClick={() => advance(1)}>Next day →</button>
            <button disabled={busy} onClick={() => advance(7)}>+7 days</button>
            <button className="ghost" disabled={busy} onClick={reset}>Reset</button>
          </div>
        )}
      </header>

      <nav className="steps" aria-label="Tabs">
        {TABS.map((t, n) => (
          <button key={t.id} className={`step ${t.id === current?.id ? "on" : ""}`} onClick={() => go(t.id)}>
            <span className="num">{n + 1}</span>
            <span className="label">{t.label}</span>
          </button>
        ))}
      </nav>
      {current && <p className="hint">{current.hint}</p>}

      {error && (
        <div className="card error">
          {error}
          <button onClick={load}>Retry</button>
        </div>
      )}
      {!data && !error && <div className="card muted">Loading…</div>}
      {data && current && <section>{current.view({ data, reload: load })}</section>}

      {data && TABS.length > 1 && (
        <footer className="pager">
          <button disabled={i === 0} onClick={() => go(TABS[i - 1].id)}>← {i > 0 ? TABS[i - 1].label : ""}</button>
          <button disabled={i === TABS.length - 1} onClick={() => go(TABS[i + 1].id)}>
            {i < TABS.length - 1 ? TABS[i + 1].label : ""} →
          </button>
        </footer>
      )}
    </main>
  );
}
