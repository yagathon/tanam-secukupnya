"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type ReactNode } from "react";

import type { TabProps } from "@/app/page";
import TodayTab from "@/components/TodayTab";
import BedsTab from "@/components/BedsTab";
import TomorrowTab from "@/components/TomorrowTab";
import SowTab from "@/components/SowTab";
import DemandTab from "@/components/DemandTab";
import ImpactTab from "@/components/sandbox/ImpactTab";
import InputPanel from "@/components/sandbox/InputPanel";
import SetupTab from "@/components/sandbox/SetupTab";
import TrailTab from "@/components/sandbox/TrailTab";
import { makeApi } from "@/lib/api";
import { friendly, loggedToday, shortDate } from "@/lib/format";
import type { Prefill } from "@/lib/today";
import type { Data, SetupDoc, TrailRow } from "@/lib/types";

const sbx = makeApi("/sandbox");

interface Tab { id: string; label: string; hint: string; view: (p: TabProps) => ReactNode }

const VIEWS: Tab[] = [
  { id: "today", label: "Today", hint: "Log what happened today: by form, or as a note Gemini reads", view: (p) => <SandboxToday key={p.data.today.today} {...p} /> },
  { id: "beds", label: "Beds", hint: "What is growing, and how much is ready each day", view: (p) => <BedsTab {...p} /> },
  { id: "tomorrow", label: "Tomorrow", hint: "The most we can safely send, and who gets it", view: (p) => <TomorrowTab {...p} /> },
  { id: "sow", label: "Sow", hint: "How many seedlings on the next sowing day, and why", view: (p) => <SowTab {...p} /> },
  { id: "demand", label: "Demand", hint: "Forecast per day with an honest band, and what moved it", view: (p) => <DemandTab {...p} /> },
  { id: "impact", label: "Impact", hint: "Plants wasted: sowing to demand vs sowing the same amount every week", view: (p) => <ImpactTab {...p} /> },
];
const IDS = ["setup", ...VIEWS.map((v) => v.id), "trail"];

/** Today's buttons ("Log Bed 2", "Log sowing") fill the input panel's form beside them. */
function SandboxToday(p: TabProps) {
  const [prefill, setPrefill] = useState<{ p: Prefill; n: number }>();
  return <TodayTab {...p} onAct={(x) => setPrefill((old) => ({ p: x, n: (old?.n ?? 0) + 1 }))}
    input={<InputPanel {...p} prefill={prefill} />} />;
}

const daysBetween = (a: string, b: string) => Math.round((Date.parse(`${b}T00:00:00Z`) - Date.parse(`${a}T00:00:00Z`)) / 86400000);

/** The visitor's own farm, entered by hand: same engine and views as the demo, a blank start. */
export default function Sandbox() {
  const [tab, setTab] = useState("setup");
  const [doc, setDoc] = useState<SetupDoc | null>(null);
  const [data, setData] = useState<Data | null>(null);
  const [trail, setTrail] = useState<TrailRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const d = await sbx.setup();
      setDoc(d);
      if (!d.saved) {
        setData(null);
        setTab("setup");
        return;
      }
      const [state, today, beds, tomorrow, sow, demand, t] = await Promise.all([
        sbx.state(), sbx.today(), sbx.beds(), sbx.tomorrow(), sbx.sow(), sbx.demand(), sbx.trail(),
      ]);
      setData({ state, today, beds, tomorrow, sow, demand, logged: loggedToday(t.rows) });
      setTrail(t.rows);
    } catch (e) {
      setError(friendly(e));
    }
  }, []);

  useEffect(() => {
    const fromHash = window.location.hash.slice(1);
    if (IDS.includes(fromHash)) setTab(fromHash);
    load();
  }, [load]);

  const go = (id: string) => {
    setTab(id);
    history.replaceState(null, "", `#${id}`);
  };

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await fn();
      await load();
    } catch (e) {
      setError(friendly(e));
    } finally {
      setBusy(false);
    }
  };

  const clear = () => {
    if (window.confirm("Clear every logged day and note? The setup stays.")) act(() => sbx.reset());
  };

  const saved = !!doc?.saved;
  const tabs = saved ? IDS : ["setup"];
  const view = VIEWS.find((v) => v.id === tab);
  const label = (id: string) => (id === "setup" ? "Setup" : id === "trail" ? "Trail" : VIEWS.find((v) => v.id === id)!.label);
  const hint = tab === "setup" ? "Your crop, buyers and beds. Change them any time: every logged day replays on the new setup."
    : tab === "trail" ? "Every day's decision as it stood that morning, with what you logged that day" : view?.hint;

  return (
    <main className="shell">
      <header className="top">
        <div>
          <h1>Tanam Secukupnya · Sandbox</h1>
          <p className="sub">Your own farm, day by day: enter what happens and watch the decision move</p>
        </div>
        <Link className="small" href="/">← Demo farm</Link>
        {data && doc && (
          <div className="clock">
            <span>
              <strong>Day {daysBetween(doc.setup.start, data.today.today) + 1} · {shortDate(data.today.today)}</strong>
            </span>
            <button className="primary" disabled={busy} onClick={() => act(() => sbx.nextDay(data.today.today, 1))}>Next day →</button>
            <button disabled={busy} onClick={() => act(() => sbx.nextDay(data.today.today, 7))}>+7 days</button>
            <button className="ghost" disabled={busy} onClick={clear}>Clear</button>
          </div>
        )}
      </header>

      <nav className="steps" aria-label="Tabs">
        {tabs.map((id, n) => (
          <button key={id} className={`step ${id === tab ? "on" : ""}`} onClick={() => go(id)}>
            <span className="num">{n + 1}</span>
            <span className="label">{label(id)}</span>
          </button>
        ))}
      </nav>
      {hint && <p className="hint">{hint}</p>}

      {error && (
        <div className="card error">
          {error}
          <button onClick={load}>Retry</button>
        </div>
      )}
      {!doc && !error && <div className="card muted">Loading…</div>}
      {doc && (tab === "setup" || !saved) && <SetupTab doc={doc} data={data} api={sbx} reload={load} />}
      {saved && data && tab === "trail" && <TrailTab rows={trail} />}
      {saved && data && view && <section>{view.view({ data, reload: load, api: sbx })}</section>}
    </main>
  );
}
