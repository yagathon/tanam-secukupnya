"use client";

import { useState } from "react";

import { api, ApiError } from "@/lib/api";
import { friendly, proposalLines, shortDate } from "@/lib/format";
import type { NoteDoc, State } from "@/lib/types";

/** A proposed note: what Gemini read, what was dropped, and Accept / Reject. If the farm moved on
 *  since it was read (409), offer to read the same text again. */
export default function NoteCard({ note, state, onDone }: { note: NoteDoc; state: State; onDone: () => Promise<void> }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ text: string; stale: boolean } | null>(null);
  const lines = proposalLines(note.proposal, state);
  const sender = state.senders.find((s) => s.id === note.sender)?.alias ?? note.sender;

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await onDone();
    } catch (e) {
      setError({ text: friendly(e), stale: e instanceof ApiError && e.status === 409 });
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
      {note.dropped?.length > 0 && <p className="small muted">Ignored: {note.dropped.join("; ")}</p>}
      {error && <p className="small bad">{error.text}</p>}
      <div className="row">
        {error?.stale ? (
          <button className="primary" disabled={busy}
            onClick={() => run(async () => {
              await api.decideNote(note.id, false);
              await api.readNote(note.text, note.sender);
            })}>
            Read again
          </button>
        ) : (
          <button className="primary" disabled={busy} onClick={() => run(() => api.decideNote(note.id, true))}>Accept</button>
        )}
        <button disabled={busy} onClick={() => run(() => api.decideNote(note.id, false))}>Reject</button>
      </div>
    </div>
  );
}
