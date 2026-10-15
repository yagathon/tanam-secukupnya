import { afterEach, expect, test, vi } from "vitest";
vi.mock("./firebase", () => ({ idToken: async () => "t" }));
import { makeApi } from "./api";

afterEach(() => vi.restoreAllMocks());

test("sandbox api prefixes its base and PUTs the setup", async () => {
  const f = vi.spyOn(globalThis, "fetch").mockImplementation(async () => new Response("{}", { status: 200 }));
  const a = makeApi("/sandbox");
  await a.today();
  await a.saveSetup({ start: "2026-10-12" } as never);
  expect(f.mock.calls[0][0]).toBe("/api/sandbox/today");
  expect(f.mock.calls[1][0]).toBe("/api/sandbox/setup");
  expect((f.mock.calls[1][1] as RequestInit).method).toBe("PUT");
});

test("the demo api keeps its paths and resets the demo", async () => {
  const f = vi.spyOn(globalThis, "fetch").mockImplementation(async () => new Response("{}", { status: 200 }));
  await makeApi("").today();
  await makeApi("").reset();
  await makeApi("/sandbox").reset();
  expect(f.mock.calls.map((c) => c[0])).toEqual(["/api/today", "/api/demo/reset", "/api/sandbox/clear"]);
});
