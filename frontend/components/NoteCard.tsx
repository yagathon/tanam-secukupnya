"use client";

import { useState } from "react";

import type { Api } from "@/lib/api";
import { friendly, proposalLines, shortDate } from "@/lib/format";
import { conflict, editable, readAgain } from "@/lib/notes";
import type { NoteDoc, State } from "@/lib/types";

/** A proposed note: what Gemini read, what was dropped, and Accept / Reject. If the farm moved on
 *  since it was read (409), offer to read the same text again. With `onEdit` (the sandbox), the card also
 *  shows the exact log lines OK would store, and an Edit button that hands the reading to the form. */
export default function NoteCard({ note, state, onDone, api, onEdit }: {
  note: NoteDoc; state: State; onDone: () => Promise<void>; api: Api; onEdit?: (note: NoteDoc) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ text: string; stale: boolean } | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const lines = proposalLines(note.proposal, state);
  const sender = state.senders.find((s) => s.id === note.sender)?.alias ?? note.sender;

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      if ((await fn()) === "keep") return;
      await onDone();
    } catch (e) {
      const c = conflict(e);
      // decided in another tab: nothing left to do here, the reload drops the card
      if (c === "decided") return void (await onDone());
      setError({ text: friendly(e), stale: c === "stale" });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="proposal">
      <p className="small muted">
        {sender} · {shortDate(note.received_on)} · <span className="pill">{note.kind}</span>
        {note.cached && <span className="pill muted">cached</span>}
      </p>
      <p className="small">“{note.text}”</p>
      {lines.length ? (
        <ul>{lines.map((l) => <li key={l}>{l}</li>)}</ul>
      ) : (
        <p>{note.summary_en}</p>
      )}
      {note.preview?.length ? (
        <ul className="preview">{note.preview.map((l) => <li key={l}>{l}</li>)}</ul>
      ) : null}
      {note.dropped?.length > 0 && <p className="small muted">Ignored: {note.dropped.join("; ")}</p>}
      {error?.text && <p className="small bad">{error.text}</p>}
      {info && <p className="small muted">{info}</p>}
      <div className="row">
        {error?.stale ? (
          <button className="primary" disabled={busy}
            onClick={() => run(async () => {
              const n = await readAgain(note, api);
              if (n.status === "proposed") return;
              setInfo(`Read again: ${n.summary_en} Nothing to apply; reject this note if it is no longer needed.`);
              setError({ text: "", stale: true });
              return "keep";
            })}>
            Read again
          </button>
        ) : (
          <button className="primary" disabled={busy} onClick={() => run(() => api.decideNote(note.id, true))}>
            {onEdit ? "OK" : "Accept"}
          </button>
        )}
        {onEdit && editable(note) && <button disabled={busy} onClick={() => onEdit(note)}>Edit</button>}
        <button disabled={busy} onClick={() => run(() => api.decideNote(note.id, false))}>
          {onEdit ? "Discard" : "Reject"}
        </button>
      </div>
    </div>
  );
}
