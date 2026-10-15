import { idToken } from "./firebase";
import type { Beds, Demand, NoteDoc, Season, Sow, State, Today, Tomorrow } from "./types";

/** A non-2xx answer. `detail` is FastAPI's error text (plain English, written for people). */
export class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(`${status} ${detail}`);
  }
}

async function call<T>(path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { authorization: `Bearer ${await idToken()}` };
  if (body !== undefined) headers["content-type"] = "application/json";
  const res = await fetch(`/api${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    let detail = text;
    try {
      const d = JSON.parse(text).detail;
      detail = typeof d === "string" ? d : JSON.stringify(d);
    } catch {
      /* not JSON: keep the raw text */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  state: () => call<State>("/state"),
  today: () => call<Today>("/today"),
  beds: () => call<Beds>("/beds"),
  tomorrow: () => call<Tomorrow>("/tomorrow"),
  sow: () => call<Sow>("/sow"),
  demand: () => call<Demand>("/demand"),
  season: () => call<Season>("/season"),
  readNote: (text: string, sender: string) => call<NoteDoc>("/notes", { text, sender }),
  decideNote: (id: string, accept: boolean) => call<NoteDoc>(`/notes/${id}/${accept ? "accept" : "reject"}`, {}),
  nextDay: (from_day: string, days = 1) => call<{ today: string; appended: number }>("/day/next", { from_day, days }),
  reset: () => call<{ ok: boolean }>("/demo/reset", {}),
};
