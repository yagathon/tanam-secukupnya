import { api, ApiError } from "./api";
import type { NoteDoc } from "./types";

/** The three 409s from accept: the day moved on (read it again), already decided elsewhere, or a race (try again). */
export type Conflict = "stale" | "decided" | "retry" | null;

export function conflict(e: unknown): Conflict {
  if (!(e instanceof ApiError) || e.status !== 409) return null;
  if (e.detail.includes("read it again")) return "stale";
  if (e.detail.includes("already")) return "decided";
  return "retry";
}

/** Read a stale note's text again. The old note is rejected only once the new reading is a proposal,
 *  so a Gemini refusal or an empty reading never loses the farmer's message. */
export async function readAgain(note: NoteDoc, a: Pick<typeof api, "readNote" | "decideNote"> = api): Promise<NoteDoc> {
  const n = await a.readNote(note.text, note.sender);
  if (n.status === "proposed") await a.decideNote(note.id, false);
  return n;
}
