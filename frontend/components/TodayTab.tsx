"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import NoteCard from "@/components/NoteCard";
import type { TabProps } from "@/app/page";
import { daySentence, friendly, lineName } from "@/lib/format";
import type { NoteDoc } from "@/lib/types";

export default function TodayTab({ data, reload, api }: TabProps) {
  const { state, today, beds } = data;
  const [text, setText] = useState("");
  const [sender, setSender] = useState("farmer");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [last, setLast] = useState<NoteDoc | null>(null);
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

  const examples = useMemo(() => {
    const inBed = beds.lines[0]?.batches.filter((b) => b.stage === "bed" && b.plants_left > 0) ?? [];
    const ripe = inBed[0]?.label ?? "Bed 1";
    const young = inBed[inBed.length - 1]?.label ?? ripe;
    return [
      { sender: "resto_a", text: "Kak besok pakcoy 9 kilo ya, rabu 7 aja" },
      { sender: "farmer", text: `panen ${ripe.toLowerCase()} td pagi 11,5 kg. timbang 5 gede 620gr 5 kecil 310` },
      { sender: "farmer", text: `ulat nyerang ${young.toLowerCase()}, kira2 40% rusak` },
      { sender: "farmer", text: "hujan gede dr subuh, semai hari ini ga jadi bu" },
      { sender: "operator", text: "resto A mulai senin depan kurangi separo dulu, dapurnya renovasi 2 minggu" },
      { sender: "caterer_c", text: "makasih kak, transferan udah masuk ya" },
    ].filter((e) => state.senders.some((s) => s.id === e.sender));
  }, [beds, state.senders]);

  const read = async () => {
    setBusy(true);
    setError(null);
    setLast(null);
    try {
      const n = await api.readNote(text, sender);
      setLast(n);
      if (n.status === "proposed") setText("");
      await reload();
    } catch (e) {
      setError(friendly(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid two">
      <div className="card">
        <h2>{today.weekday}</h2>
        {today.lines.map((l) => (
          <div key={l.line} className="card">
            <h3>{lineName(l.line)}</h3>
            <p className={`sentence ${l.short_kg > 0.005 ? "bad" : ""}`}>{daySentence(l)}</p>
          </div>
        ))}
        <div className="row wrap">
          <button disabled={asking} onClick={explain}>{asking ? "Asking Gemini…" : "Why?"}</button>
          <span className="small muted">Gemini explains today&apos;s numbers in plain words. The engine decides; Gemini only explains.</span>
        </div>
        {why && <p className={`small ${why.failed ? "bad" : "why"}`}>{why.text}</p>}
        <p className="small muted">
          Press <strong>Next day →</strong> to let the farm live one day: orders arrive, the farmer harvests and samples, and
          sowing happens on Mondays and Thursdays.
        </p>
      </div>

      <div className="card">
        <h2>Note from the field</h2>
        <p className="muted small">
          Paste a WhatsApp-style message. Gemini reads it into one farm event; nothing changes until you accept it.
        </p>
        <div className="row wrap">
          <label className="small">
            From{" "}
            <select value={sender} onChange={(e) => setSender(e.target.value)}>
              {state.senders.map((s) => <option key={s.id} value={s.id}>{s.alias}</option>)}
            </select>
          </label>
        </div>
        <textarea rows={3} maxLength={1000} value={text} onChange={(e) => setText(e.target.value)}
          placeholder="e.g. panen bed 31 tadi 12 kg, 5 gede 650 gr 5 kecil 330" />
        <div className="row wrap">
          <button className="primary" disabled={busy || !text.trim()} onClick={read}>
            {busy ? "Reading…" : "Read with Gemini"}
          </button>
          <span className="small muted">Try:</span>
          {examples.map((e) => (
            <button key={e.text} className="ghost small" onClick={() => { setText(e.text); setSender(e.sender); }}>
              {e.text.length > 28 ? `${e.text.slice(0, 28)}…` : e.text}
            </button>
          ))}
        </div>
        {error && <p className="small bad">{error}</p>}
        {last && last.status === "no_action" && (
          <p className="small muted">No farm event in this note: {last.summary_en}</p>
        )}

        <h3>Waiting for you ({today.pending.length})</h3>
        {today.pending.length === 0 && <p className="empty">No notes waiting.</p>}
        {today.pending.map((n) => <NoteCard key={n.id} note={n} state={state} onDone={reload} api={api} />)}
      </div>
    </div>
  );
}
