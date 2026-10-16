"use client";

import { useState } from "react";

import NoteCard from "@/components/NoteCard";
import type { TabProps } from "@/app/page";
import { friendly, lineName } from "@/lib/format";
import type { NoteDoc } from "@/lib/types";

type Kind = "order" | "harvest" | "sow" | "loss" | "signal" | "postpone";
type Form = Record<string, string>;
const KINDS: [Kind, string][] = [
  ["order", "Order"], ["harvest", "Harvest"], ["sow", "Sow"], ["loss", "Loss"], ["signal", "Signal"], ["postpone", "Postpone"],
];

const addDays = (iso: string, n: number) => {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
};

/** The visitor's own day: one small form per event kind, and Gemini notes whose reading can be OK'd or edited. */
export default function InputPanel({ data, reload, api }: TabProps) {
  const { state, today, beds, sow } = data;
  const t = today.today;
  const lines = state.crop.lines.map((l) => l.id);
  const people = [
    ...state.buyers.map((b) => ({ id: b.id, alias: b.alias, line: Object.keys(b.lines)[0] ?? lines[0] })),
    ...state.households.map((h) => ({ id: h.id, alias: `${h.alias} (household)`, line: h.line })),
  ];
  const inGround = beds.lines.flatMap((l) => l.batches.filter((b) => b.stage === "bed" && b.plants_left > 0)
    .map((b) => ({ ...b, line: l.line })));
  const planned = (line: string) => String(sow.lines.find((s) => s.line === line)?.seedlings ?? "");

  const blank = (k: Kind): Form => {
    const line = lines[0] ?? "";
    switch (k) {
      case "order": return { buyer: people[0]?.id ?? "", line: people[0]?.line ?? line, kg: "", day: addDays(t, 1) };
      case "harvest": return { batch: inGround[0]?.id ?? "", kg: "", big5_g: "", small5_g: "" };
      case "sow": return { line, seedlings: planned(line) };
      case "loss": return { line, batch: "", pct: "", cause: "" };
      case "signal": return { scope: "all", line: "", effect_pct: "", date_from: t, date_to: "", cause: "" };
      case "postpone": return { line, reason: "" };
    }
  };

  const [kind, setKind] = useState<Kind>("order");
  const [form, setForm] = useState<Form>(() => blank("order"));
  const [busy, setBusy] = useState<"form" | "note" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [sender, setSender] = useState("farmer");
  const [noteMsg, setNoteMsg] = useState<string | null>(null);

  const pick = (k: Kind, f?: Form) => { setKind(k); setForm(f ?? blank(k)); setError(null); };
  const set = (patch: Form) => setForm({ ...form, ...patch });
  const field = (name: string, label: string, type = "number", extra: Record<string, string> = {}) => (
    <label>{label}<input type={type} step="any" value={form[name] ?? ""} {...extra} onChange={(e) => set({ [name]: e.target.value })} /></label>
  );
  const lineSelect = (name = "line", allowAll = false) => (
    <label>Line
      <select value={form[name]} onChange={(e) => set({ [name]: e.target.value, ...(kind === "sow" ? { seedlings: planned(e.target.value) } : {}),
        ...(kind === "loss" ? { batch: "" } : {}) })}>
        {allowAll && <option value="">all lines</option>}
        {lines.map((l) => <option key={l} value={l}>{lineName(l)}</option>)}
      </select>
    </label>
  );

  const submit = async () => {
    setBusy("form");
    setError(null);
    try {
      await api.event({ kind, ...form }, today.seq);
      setForm(blank(kind));
      await reload();
    } catch (e) {
      setError(friendly(e));
    } finally {
      setBusy(null);
    }
  };

  const read = async () => {
    setBusy("note");
    setNoteMsg(null);
    try {
      const n = await api.readNote(text, sender);
      if (n.status === "proposed") setText("");
      else setNoteMsg(`No farm event in this note: ${n.summary_en}`);
      await reload();
    } catch (e) {
      setNoteMsg(friendly(e));
    } finally {
      setBusy(null);
    }
  };

  // Edit: hand Gemini's first reading to the matching form, then drop the note (the form is now the source).
  const edit = async (note: NoteDoc) => {
    const ev = note.preview_events?.[0];
    if (!ev) return;
    const s = (k: string) => (ev[k] === null || ev[k] === undefined ? "" : String(ev[k]));
    const k = ev.t as Kind;
    const byBatch = inGround.find((b) => b.id === ev.batch)?.line ?? lines[0] ?? "";
    const f: Record<Kind, () => Form> = {
      order: () => ({ buyer: s("buyer"), line: s("line"), kg: s("kg"), day: s("day") }),
      harvest: () => ({ batch: s("batch"), kg: s("kg"), big5_g: s("big5_g"), small5_g: s("small5_g") }),
      sow: () => ({ line: s("line"), seedlings: s("seedlings") }),
      loss: () => ({ line: byBatch, batch: s("batch"), pct: s("pct"), cause: s("cause") }),
      signal: () => ({ scope: s("scope"), line: s("line"), effect_pct: s("effect_pct"), date_from: s("date_from"),
        date_to: s("date_to"), cause: s("cause") }),
      postpone: () => ({ line: s("line"), reason: s("reason") }),
    };
    if (!(k in f)) return;
    pick(k, f[k]());
    try {
      await api.decideNote(note.id, false);
    } finally {
      await reload();
    }
  };

  return (
    <div className="card">
      <h2>Log the day</h2>
      <div className="seg">
        {KINDS.map(([k, label]) => <button key={k} className={k === kind ? "on" : ""} onClick={() => pick(k)}>{label}</button>)}
      </div>
      <div className="form-grid">
        {kind === "order" && <>
          <label>Buyer
            <select value={form.buyer} onChange={(e) => set({ buyer: e.target.value, line: people.find((p) => p.id === e.target.value)?.line ?? form.line })}>
              {people.map((p) => <option key={p.id} value={p.id}>{p.alias}</option>)}
            </select>
          </label>
          {lineSelect()}
          {field("kg", "kg (0 = no order this time)")}
          {field("day", "For day", "date", { min: addDays(t, 1), max: addDays(t, 14) })}
        </>}
        {kind === "harvest" && <>
          <label>Bed
            <select value={form.batch} onChange={(e) => set({ batch: e.target.value })}>
              {inGround.length === 0 && <option value="">no bed in the ground</option>}
              {inGround.map((b) => <option key={b.id} value={b.id}>{b.label} · {b.line}</option>)}
            </select>
          </label>
          {field("kg", "kg harvested")}
          {field("big5_g", "5 biggest, g (optional)")}
          {field("small5_g", "5 smallest, g (optional)")}
        </>}
        {kind === "sow" && <>{lineSelect()}{field("seedlings", "Seedlings")}</>}
        {kind === "loss" && <>
          {lineSelect()}
          <label>Bed
            <select value={form.batch} onChange={(e) => set({ batch: e.target.value })}>
              <option value="">all beds of this line</option>
              {inGround.filter((b) => b.line === form.line).map((b) => <option key={b.id} value={b.id}>{b.label}</option>)}
            </select>
          </label>
          {field("pct", "% lost")}
          {field("cause", "Cause", "text")}
        </>}
        {kind === "signal" && <>
          <label>Who
            <select value={form.scope} onChange={(e) => set({ scope: e.target.value })}>
              <option value="all">everyone</option>
              <option value="channel:B2B">all businesses</option>
              <option value="channel:B2C">all households</option>
              {people.map((p) => <option key={p.id} value={`buyer:${p.id}`}>{p.alias}</option>)}
            </select>
          </label>
          {lineSelect("line", true)}
          {field("effect_pct", "Effect % (−100 … +300)")}
          {field("date_from", "From", "date", { min: t })}
          {field("date_to", "To (empty = open)", "date", { min: form.date_from || t })}
          {field("cause", "Cause", "text")}
        </>}
        {kind === "postpone" && <>{lineSelect()}{field("reason", "Reason", "text")}</>}
      </div>
      <div className="row wrap">
        <button className="primary" disabled={!!busy} onClick={submit}>{busy === "form" ? "Logging…" : "Log it"}</button>
        {kind === "harvest" && <span className="small muted">Not logged by day&apos;s end? The planned send is assumed harvested.</span>}
      </div>
      {error && <p className="small bad">{error}</p>}
      {(data.logged?.length ?? 0) > 0 && <div className="card toast small">
        <strong>Logged today</strong>
        <ul>{data.logged!.map((l, i) => <li key={i}>{l}</li>)}</ul>
      </div>}

      <h3>Or write it as a note</h3>
      <p className="small muted">Gemini reads the note into the same log lines; OK stores them, Edit opens them in the form.</p>
      <div className="row wrap">
        <label className="small">From{" "}
          <select value={sender} onChange={(e) => setSender(e.target.value)}>
            {state.senders.map((s) => <option key={s.id} value={s.id}>{s.alias}</option>)}
          </select>
        </label>
      </div>
      <textarea rows={3} maxLength={1000} value={text} onChange={(e) => setText(e.target.value)}
        placeholder="e.g. panen bed 1 tadi 12 kg, 5 gede 650 gr 5 kecil 330" />
      <button className="primary" disabled={!!busy || !text.trim()} onClick={read}>{busy === "note" ? "Reading…" : "Read with Gemini"}</button>
      {noteMsg && <p className="small muted">{noteMsg}</p>}
      {today.pending.map((n) => <NoteCard key={n.id} note={n} state={state} onDone={reload} api={api} onEdit={edit} />)}
    </div>
  );
}
