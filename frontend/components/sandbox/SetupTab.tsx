"use client";

import { Fragment, useEffect, useRef, useState } from "react";

import CurveChart from "@/components/sandbox/CurveChart";
import PatternEditor, { MiniBars } from "@/components/sandbox/PatternEditor";
import YearChart from "@/components/sandbox/YearChart";
import SheetBox from "@/components/sandbox/SheetBox";
import type { Api } from "@/lib/api";
import { friendly } from "@/lib/format";
import { logFileName, readLogFile } from "@/lib/log";
import { evenWeek } from "@/lib/pattern";
import { checkSetup, fromPct, toPct } from "@/lib/setup";
import { bedsFromSheet, buyersFromSheet, curveFromSheet, toSheet, WEEKDAYS } from "@/lib/sheet";
import type { Data, Setup, SetupCrop, SetupDoc } from "@/lib/types";

function Num({ value, onChange, step = "any", disabled }: {
  value: number; onChange: (n: number) => void; step?: string; disabled?: boolean;
}) {
  return <input type="number" step={step} value={Number.isFinite(value) ? value : ""} disabled={disabled}
    onChange={(e) => onChange(e.target.value === "" ? NaN : Number(e.target.value))} />;
}

function Days({ value, onChange }: { value: number[]; onChange: (d: number[]) => void }) {
  return (
    <div className="chips">
      {WEEKDAYS.map((w, i) => (
        <button key={w} type="button" className={value.includes(i) ? "on" : ""}
          onClick={() => onChange(value.includes(i) ? value.filter((x) => x !== i) : [...value, i].sort((a, b) => a - b))}>
          {w}
        </button>
      ))}
    </div>
  );
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** [field, label, step, typed as %] */
const CROP_FIELDS: [keyof SetupCrop, string, string?, boolean?][] = [
  ["nursery_days", "Nursery days", "1"], ["max_bed_day", "Last bed day", "1"], ["spread_ratio", "Size spread, %", "any", true],
  ["germination", "Germination, %", "any", true], ["survival", "Survival to harvest, %", "any", true],
  ["seeds_per_gram", "Seeds per gram"], ["grams_per_teaspoon", "Grams per teaspoon"],
  ["max_seedlings_per_sowing", "Max seedlings per sowing", "1"],
];

/** The visitor's farm: crop, curve, buyers, beds. Nothing is logged until Save. */
export default function SetupTab({ doc, data, api, reload }: {
  doc: SetupDoc; data: Data | null; api: Api; reload: () => Promise<void>;
}) {
  const [s, setS] = useState<Setup>(doc.setup);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [weekOpen, setWeekOpen] = useState<number | null>(null);
  const logInput = useRef<HTMLInputElement>(null);
  useEffect(() => setS(doc.setup), [doc.setup]);

  const crop = (patch: Partial<SetupCrop>) => setS({ ...s, crop: { ...s.crop, ...patch } });
  const lineIds = s.crop.lines.map((l) => l.id);
  const problems = checkSetup(s);
  const dirty = JSON.stringify(s) !== JSON.stringify(doc.setup);
  const ref = data?.state.reference;
  const learned = ref && JSON.stringify(ref.now) !== JSON.stringify(ref.start);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.saveSetup(s);
      await reload();
    } catch (e) {
      setError(friendly(e));
    } finally {
      setBusy(false);
    }
  };

  const loadExample = async () => {
    if ((s.buyers.length || s.beds.length) && !window.confirm("Replace this form with the example farm? Nothing is saved until you press Save.")) return;
    setError(null);
    try {
      setS(await api.example());
    } catch (e) {
      setError(friendly(e));
    }
  };

  const resetSetup = async () => {
    if (!window.confirm("Delete the setup and every logged day and note? The sandbox starts blank.")) return;
    setBusy(true);
    try {
      await api.reset(true);
      await reload();
    } catch (e) {
      setError(friendly(e));
    } finally {
      setBusy(false);
    }
  };

  const resetReference = async () => {
    if (!data || !window.confirm("Put the reference curve back to the starting curve? Samples so far stop counting.")) return;
    setBusy(true);
    try {
      await api.event({ kind: "reference_reset" }, data.today.seq);
      await reload();
    } catch (e) {
      setError(friendly(e));
    } finally {
      setBusy(false);
    }
  };

  const downloadLog = async () => {
    setBusy(true);
    setError(null);
    try {
      const log = await api.exportLog();
      const url = URL.createObjectURL(new Blob([JSON.stringify(log, null, 1)], { type: "application/json" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = logFileName(doc.setup.start, data?.today.today ?? doc.setup.start);
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(friendly(e));
    } finally {
      setBusy(false);
    }
  };

  const loadLog = async (file: File | undefined) => {
    if (!file) return;
    setError(null);
    const log = readLogFile(await file.text());
    if ("error" in log) return setError(log.error);
    if (!window.confirm("Load this log? It replaces your sandbox: its setup and every logged day.")) return;
    setBusy(true);
    try {
      await api.importLog(log);
      await reload();
    } catch (e) {
      setError(friendly(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid">
      {!doc.saved && <div className="card banner">Set up your farm first — nothing is logged until you save.</div>}

      <div className="card">
        <h2>Crop</h2>
        <div className="form-grid">
          <label>Name<input value={s.crop.name} onChange={(e) => crop({ name: e.target.value })} /></label>
          <label>
            Start date
            <input type="date" value={s.start} disabled={doc.locked_start} onChange={(e) => setS({ ...s, start: e.target.value })} />
          </label>
          {CROP_FIELDS.map(([k, label, step, pct]) => (
            <label key={k}>{label}<Num value={pct ? toPct(s.crop[k] as number) : s.crop[k] as number} step={step}
              onChange={(n) => crop({ [k]: pct ? fromPct(n) : n })} /></label>
          ))}
        </div>
        <p className="small muted">Size spread: weigh the 5 biggest and the 5 smallest plants of one bed; the gap between their
          averages as % of the bed&apos;s average plant. 45% = when the average is 100 g, the bed runs from ~78 g to ~122 g.
          Each harvest sample measures it again per bed.</p>
        {doc.locked_start && <p className="small muted">Locked — clear the sandbox to change the start.</p>}
        <p className="small muted">Sowing days</p>
        <Days value={s.crop.sow_weekdays} onChange={(d) => crop({ sow_weekdays: d })} />

        <h3>Lines (size grades)</h3>
        <table className="edit">
          <thead><tr><th>Line</th><th>Min g</th><th>Max g</th><th title="Buyers still take plants up to this weight when stock is short">Up to if short, g</th><th /></tr></thead>
          <tbody>
            {s.crop.lines.map((l, i) => (
              <tr key={i}>
                <td>
                  <input value={l.id} disabled={s.buyers.some((b) => b.line === l.id) || s.beds.some((b) => b.line === l.id)}
                    onChange={(e) => crop({ lines: s.crop.lines.map((x, j) => (j === i ? { ...x, id: e.target.value } : x)) })} />
                </td>
                <td><Num value={l.min_g} onChange={(n) => crop({ lines: s.crop.lines.map((x, j) => (j === i ? { ...x, min_g: n } : x)) })} /></td>
                <td><Num value={l.max_g} onChange={(n) => crop({ lines: s.crop.lines.map((x, j) => (j === i ? { ...x, max_g: n } : x)) })} /></td>
                <td><Num value={l.stretch_g ?? NaN} onChange={(n) => crop({ lines: s.crop.lines.map((x, j) =>
                  (j === i ? { ...x, stretch_g: Number.isFinite(n) ? n : null } : x)) })} /></td>
                <td>
                  <button className="ghost small" disabled={s.crop.lines.length < 2}
                    onClick={() => crop({ lines: s.crop.lines.filter((_, j) => j !== i) })}>✕</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <button className="ghost small" onClick={() => crop({ lines: [...s.crop.lines, { id: `line${s.crop.lines.length + 1}`, min_g: 100, max_g: 200 }] })}>
          + line
        </button>
        <p className="small muted">Up to if short: when there isn&apos;t enough for everyone, buyers still take slightly bigger plants up to
          this weight, so stock left in the bed can serve the next days. Empty = only up to max g.</p>
      </div>

      <div className="card">
        <h2>Growth curve</h2>
        <p className="small muted">Average grams per plant by day in the bed (after the nursery).</p>
        <div className="grid two">
          <div>
            <table className="edit">
              <thead><tr><th>Bed day</th><th>Grams</th><th /></tr></thead>
              <tbody>
                {s.crop.growth_curve.map(([d, g], i) => (
                  <tr key={i}>
                    <td><Num value={d} step="1" onChange={(n) => crop({ growth_curve: s.crop.growth_curve.map((p, j) => (j === i ? [n, p[1]] : p)) })} /></td>
                    <td><Num value={g} onChange={(n) => crop({ growth_curve: s.crop.growth_curve.map((p, j) => (j === i ? [p[0], n] : p)) })} /></td>
                    <td><button className="ghost small" onClick={() => crop({ growth_curve: s.crop.growth_curve.filter((_, j) => j !== i) })}>✕</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <button className="ghost small" onClick={() => {
              const last = s.crop.growth_curve[s.crop.growth_curve.length - 1] ?? [0, 0];
              crop({ growth_curve: [...s.crop.growth_curve, [last[0] + 7, last[1] + 10]] });
            }}>+ point</button>
            <SheetBox example={"0\t5\n7\t15,5\n14\t45"}
              copy={() => toSheet([["day", "grams"], ...s.crop.growth_curve])}
              parse={(t) => { const r = curveFromSheet(t); if ("error" in r) return r.error; crop({ growth_curve: r.points }); return null; }} />
          </div>
          <div>
            <CurveChart start={s.crop.growth_curve} reference={doc.saved ? ref : undefined} />
            <label className="small">
              <input type="checkbox" checked={s.learn_reference} onChange={(e) => setS({ ...s, learn_reference: e.target.checked })} />{" "}
              Learn the reference curve from samples
            </label>
            {learned && <div><button className="ghost small" disabled={busy} onClick={resetReference}>Reset reference</button></div>}
          </div>
        </div>
      </div>

      <div className="card">
        <h2>Buyers ({s.buyers.length})</h2>
        <table className="edit">
          <thead><tr><th>Name</th><th>Type</th><th>Line</th><th>Usual kg/week</th><th>Order days</th><th title="Share of the week's kg per day, Mon…Sun, adding up to 100. Empty = even over the order days.">Weekday pattern</th><th>Min kg</th><th /></tr></thead>
          <tbody>
            {s.buyers.map((b, i) => {
              const set = (patch: Partial<typeof b>) => setS({ ...s, buyers: s.buyers.map((x, j) => (j === i ? { ...x, ...patch } : x)) });
              return (
                <Fragment key={b.id ?? `new${i}`}>
                <tr>
                  <td><input value={b.name} onChange={(e) => set({ name: e.target.value })} /></td>
                  <td>
                    <select value={b.type} onChange={(e) => set({ type: e.target.value as typeof b.type })}>
                      <option value="business">business</option><option value="household">household</option>
                    </select>
                  </td>
                  <td><select value={b.line} onChange={(e) => set({ line: e.target.value })}>{lineIds.map((l) => <option key={l}>{l}</option>)}</select></td>
                  <td><Num value={b.usual_kg_per_week} onChange={(n) => set({ usual_kg_per_week: n })} /></td>
                  <td>{b.week_pct?.length === 7
                    ? <span className="small muted">{b.weekdays.map((d) => WEEKDAYS[d]).join(" ")} (from %)</span>
                    : <Days value={b.weekdays} onChange={(d) => set({ weekdays: d })} />}</td>
                  <td><span className="weekpat">
                    {b.week_pct?.length === 7 ? <MiniBars value={b.week_pct} /> : <span className="small muted">even</span>}
                    <button className="ghost small" onClick={() => setWeekOpen(weekOpen === i ? null : i)}>
                      {weekOpen === i ? "Close" : b.week_pct?.length === 7 ? "Edit" : "Set pattern"}</button>
                  </span></td>
                  <td><Num value={b.min_kg} onChange={(n) => set({ min_kg: n })} /></td>
                  <td><button className="ghost small" onClick={() => setS({ ...s, buyers: s.buyers.filter((_, j) => j !== i) })}>✕</button></td>
                </tr>
                {weekOpen === i && <tr><td colSpan={8}>
                  <p className="small muted">{b.name}: share of the week&apos;s kg per day (adds up to 100). Days above 0 become the
                    order days. Paste a spreadsheet row of 7 numbers into any cell to fill all.</p>
                  <PatternEditor labels={WEEKDAYS} value={b.week_pct?.length === 7 ? b.week_pct : evenWeek(b.weekdays)} flat={100 / 7}
                    target={100} onChange={(v) => set({ week_pct: v, weekdays: v.flatMap((x, d) => (x > 0 ? [d] : [])) })} />
                  {b.week_pct?.length === 7 && <button className="ghost small" onClick={() => set({ week_pct: undefined })}>
                    Back to even over the order days</button>}
                </td></tr>}
                </Fragment>
              );
            })}
          </tbody>
        </table>
        <button className="ghost small" onClick={() => setS({ ...s, buyers: [...s.buyers, {
          name: `Buyer ${s.buyers.length + 1}`, type: "business", line: lineIds[0] ?? "", usual_kg_per_week: 0, weekdays: [], min_kg: 0,
        }] })}>+ buyer</button>
        <p className="small muted">A household has no usual amount: the forecast starts from a small prior and learns from its orders.
          Weekday pattern: empty = even over the order days; &quot;Set pattern&quot; to give some days more, e.g. a weekend peak.</p>
        <SheetBox example={"name\ttype\tline\tusual kg/week\torder days\tmin kg\nResto A\tbusiness\tregular\t20\tMon Thu\t2"}
          copy={() => toSheet([["name", "type", "line", "usual kg/week", "order days", "min kg"],
            ...s.buyers.map((b) => [b.name, b.type, b.line, b.usual_kg_per_week, b.weekdays.map((d) => WEEKDAYS[d]).join(" "), b.min_kg])])}
          parse={(t) => { const r = buyersFromSheet(t, lineIds); if ("error" in r) return r.error; setS({ ...s, buyers: r.buyers }); return null; }} />
      </div>

      <div className="card">
        <h2>Season (whole farm)</h2>
        <p className="small muted">The forecast is today&apos;s level × weekday % × these. The level still learns from real orders; a peak
          set here is expected, so it doesn&apos;t count as a surprise.</p>
        <h3>Month: % of the month&apos;s kg per week of the month</h3>
        <PatternEditor labels={["1–7", "8–14", "15–21", "22–end"]} value={s.month_pct ?? [25, 25, 25, 25]} flat={25} target={100}
          onChange={(v) => setS({ ...s, month_pct: v })} />
        <h3>Year: index per month (100 = normal)</h3>
        <PatternEditor labels={MONTHS} value={s.year_index ?? Array(12).fill(100)} flat={100} unit=""
          onChange={(v) => setS({ ...s, year_index: v })} />
        <p className="small muted">e.g. month <code>32 27 22 19</code> (payday at the start); year with Dec and Jan up, Jul and Aug down:{" "}
          <code>115 100 100 100 100 100 85 85 100 100 100 120</code>. Paste a row into any cell to fill all.</p>
        <h3>The year, all three together</h3>
        <p className="small muted">Every buyer&apos;s week × the month pattern × the year index, day by day from the start: the
          starting forecast before real orders teach it. It moves as you type, before Save.</p>
        <YearChart setup={s} />
      </div>

      <div className="card">
        <h2>Beds already in the ground ({s.beds.length})</h2>
        <table className="edit">
          <thead><tr><th>Line</th><th>Sown on</th><th>Seedlings</th><th /></tr></thead>
          <tbody>
            {s.beds.map((b, i) => {
              const set = (patch: Partial<typeof b>) => setS({ ...s, beds: s.beds.map((x, j) => (j === i ? { ...x, ...patch } : x)) });
              return (
                <tr key={i}>
                  <td><select value={b.line} onChange={(e) => set({ line: e.target.value })}>{lineIds.map((l) => <option key={l}>{l}</option>)}</select></td>
                  <td><input type="date" value={b.sown_on} max={s.start} onChange={(e) => set({ sown_on: e.target.value })} /></td>
                  <td><Num value={b.seedlings} step="1" onChange={(n) => set({ seedlings: n })} /></td>
                  <td><button className="ghost small" onClick={() => setS({ ...s, beds: s.beds.filter((_, j) => j !== i) })}>✕</button></td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <button className="ghost small" onClick={() => setS({ ...s, beds: [...s.beds, { line: lineIds[0] ?? "", sown_on: s.start, seedlings: 500 }] })}>
          + bed
        </button>
        <SheetBox example={"line\tsown on\tseedlings\nregular\t2026-09-20\t800"}
          copy={() => toSheet([["line", "sown on", "seedlings"], ...s.beds.map((b) => [b.line, b.sown_on, b.seedlings])])}
          parse={(t) => { const r = bedsFromSheet(t, lineIds); if ("error" in r) return r.error; setS({ ...s, beds: r.beds }); return null; }} />
      </div>

      <div className="card">
        {problems.length > 0 && <ul className="bad small">{problems.map((p) => <li key={p}>{p}</li>)}</ul>}
        {error && <p className="small bad">{error}</p>}
        <div className="row wrap">
          <button className="primary" disabled={busy || problems.length > 0 || (doc.saved && !dirty)} onClick={save}>
            {busy ? "Saving…" : doc.saved ? "Save changes" : "Save and start"}
          </button>
          {dirty && <button className="ghost" disabled={busy} onClick={() => setS(doc.setup)}>Undo changes</button>}
          {doc.saved && <span className="small muted">Saving replays every logged day on the new setup.</span>}
        </div>
        <div className="row wrap">
          {!doc.locked_start && <button className="ghost" disabled={busy} onClick={loadExample}>Load example farm</button>}
          {doc.saved && <button className="ghost" disabled={busy} onClick={resetSetup}>Reset setup</button>}
          <span className="small muted">Example farm: 3 businesses, 3 households and a bed per past sowing day, ready to save.
            Reset setup: back to a blank sandbox.</span>
        </div>
        <div className="row wrap">
          {doc.saved && <button className="ghost" disabled={busy} onClick={downloadLog}>Download my log</button>}
          <button className="ghost" disabled={busy} onClick={() => logInput.current?.click()}>Load my log</button>
          <input ref={logInput} type="file" accept="application/json,.json" hidden
            onChange={(e) => { void loadLog(e.target.files?.[0]); e.target.value = ""; }} />
          <span className="small muted">Your setup and every logged day in one file: keep it, and load it back after a reset
            or on another device.</span>
        </div>
      </div>
    </div>
  );
}
