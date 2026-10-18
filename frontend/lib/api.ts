import { idToken } from "./firebase";
import type {
  Beds, Demand, DemoSetup, Impact, NoteDoc, SandboxLog, Setup, SimReport, SetupDoc, Sow, State, Today, Tomorrow, TrailRow,
} from "./types";

/** A non-2xx answer. `detail` is FastAPI's error text (plain English, written for people). */
export class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(`${status} ${detail}`);
  }
}

async function call<T>(path: string, body?: unknown, method?: string): Promise<T> {
  const headers: Record<string, string> = { authorization: `Bearer ${await idToken()}` };
  if (body !== undefined) headers["content-type"] = "application/json";
  const res = await fetch(`/api${path}`, {
    method: method ?? (body === undefined ? "GET" : "POST"),
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

/** The demo farm (base "") or the visitor's own sandbox (base "/sandbox"): same views, other reference. */
export function makeApi(base: "" | "/sandbox") {
  const p = (s: string) => `${base}${s}`;
  return {
    state: () => call<State>(p("/state")),
    today: () => call<Today>(p("/today")),
    beds: () => call<Beds>(p("/beds")),
    tomorrow: () => call<Tomorrow>(p("/tomorrow")),
    sow: () => call<Sow>(p("/sow")),
    demand: () => call<Demand>(p("/demand")),
    season: () => call<SimReport>("/season"),
    demoSetup: () => call<DemoSetup>("/setup"),
    readNote: (text: string, sender: string) => call<NoteDoc>(p("/notes"), { text, sender }),
    why: () => call<{ text: string; model: string; cached: boolean }>(p("/today/why"), {}),
    decideNote: (id: string, accept: boolean) => call<NoteDoc>(p(`/notes/${id}/${accept ? "accept" : "reject"}`), {}),
    nextDay: (from_day: string, days = 1) => call<{ today: string; appended: number }>(p("/day/next"), { from_day, days }),
    reset: (setup = false) => call<{ ok: boolean }>(base ? "/sandbox/clear" : "/demo/reset", setup ? { setup } : {}),
    example: () => call<Setup>("/sandbox/example"),
    setup: () => call<SetupDoc>("/sandbox/setup"),
    saveSetup: (s: Setup) => call<SetupDoc>("/sandbox/setup", s, "PUT"),
    event: (form: Record<string, unknown>, seq: number) =>
      call<{ events: unknown[]; lines: string[]; warnings: string[] }>("/sandbox/events", { form, seq }),
    exportLog: () => call<SandboxLog>("/sandbox/export"),
    importLog: (log: SandboxLog) => call<{ days: number; entries: number }>("/sandbox/import", log),
    trail: () => call<{ rows: TrailRow[] }>(p("/trail")),
    impact: () => call<Impact>(p("/impact")),
    removeEntry: (id: string) => call<{ removed: number }>(`/sandbox/events/${encodeURIComponent(id)}`, undefined, "DELETE"),
    resetToday: () => call<{ removed: number }>("/sandbox/today/reset", {}),
  };
}

export type Api = ReturnType<typeof makeApi>;
export const api = makeApi("");
