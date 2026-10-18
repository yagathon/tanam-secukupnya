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
import { SHARED_HINT, TAB_LABEL, TAB_ORDER } from "@/lib/tabs";
import { friendly, loggedToday, shortDate } from "@/lib/format";
import type { Prefill } from "@/lib/today";
import type { Data, SetupDoc, TrailRow } from "@/lib/types";

const sbx = makeApi("/sandbox");

interface Tab { id: string; label: string; hint: string; view: (p: TabProps) => ReactNode }

const VIEWS: Tab[] = [
  { id: "today", label: "Today", hint: "Log what happened today: by form, or as a note Gemini reads", view: (p) => <SandboxToday key={p.data.today.today} {...p} /> },
  { id: "beds", label: "Beds", hint: SHARED_HINT.beds, view: (p) => <BedsTab {...p} /> },
  { id: "tomorrow", label: "Tomorrow", hint: SHARED_HINT.tomorrow, view: (p) => <TomorrowTab {...p} /> },
  { id: "sow", label: "Sow", hint: SHARED_HINT.sow, view: (p) => <SowTab {...p} /> },
  { id: "demand", label: "Demand", hint: SHARED_HINT.demand, view: (p) => <DemandTab {...p} /> },
  { id: "impact", label: "Impact", hint: "Plants wasted: sowing to demand vs sowing the same amount every week", view: (p) => <ImpactTab {...p} /> },
];
const IDS: string[] = [...TAB_ORDER];

/** The Simulation report needs a known future (the demo's synthetic world); a sandbox only has its past. */
function ReportElsewhere() {
  return (
    <div className="card empty">
      <p>The Simulation report runs three strategies through months of a synthetic world whose demand is known in advance.
        Your sandbox only knows the days you logged, so the report lives on the demo farm.</p>
      <p><Link href="/#report">Open the Simulation report on the demo farm →</Link></p>
    </div>
  );
}

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
  const label = (id: string) => TAB_LABEL[id as keyof typeof TAB_LABEL];
  const hint = tab === "setup" ? "Your crop, buyers and beds. Change them any time: every logged day replays on the new setup."
    : tab === "trail" ? "Every day's decision as it stood that morning, with what you logged that day"
    : tab === "report" ? "Demo farm only: it needs a known future" : view?.hint;

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
          <button key={id} className={`step ${id === tab ? "on" : ""} ${id === "report" ? "off" : ""}`} onClick={() => go(id)}
            title={id === "report" ? "Demo farm only" : undefined}>
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
      {saved && data && tab === "report" && <ReportElsewhere />}
      {saved && data && view && <section>{view.view({ data, reload: load, api: sbx })}</section>}
    </main>
  );
}
