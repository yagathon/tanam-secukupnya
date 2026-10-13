import type { Plan, Scenario, SeriesView, State } from "./types";

async function call<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: body === undefined ? undefined : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path}: ${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}

export const api = {
  state: () => call<State>("/state"),
  forecast: (horizon_weeks?: number) =>
    call<{ today: string; series: SeriesView[] }>("/forecast/run", { horizon_weeks }),
  plan: (horizon_weeks?: number) => call<{ today: string; plans: Plan[] }>("/plan/run", { horizon_weeks }),
  scenario: (crop: string, week: string, harvest_pct: number) =>
    call<Scenario>("/scenario", { crop, week, harvest_pct }),
  reset: () => call<{ ok: boolean }>("/demo/reset", {}),
};
