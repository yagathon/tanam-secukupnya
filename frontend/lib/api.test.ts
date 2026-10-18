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

test("sandbox reset can take the setup too, and the example farm is a GET", async () => {
  const f = vi.spyOn(globalThis, "fetch").mockImplementation(async () => new Response("{}", { status: 200 }));
  const a = makeApi("/sandbox");
  await a.reset(true);
  await a.example();
  expect(f.mock.calls[0][0]).toBe("/api/sandbox/clear");
  expect(JSON.parse((f.mock.calls[0][1] as RequestInit).body as string)).toEqual({ setup: true });
  expect(f.mock.calls[1][0]).toBe("/api/sandbox/example");
  expect((f.mock.calls[1][1] as RequestInit | undefined)?.method ?? "GET").toBe("GET");
});

test("a GET that loses the connection is retried once", async () => {
  vi.useFakeTimers();
  const f = vi.spyOn(globalThis, "fetch")
    .mockRejectedValueOnce(new TypeError("Failed to fetch"))
    .mockResolvedValueOnce(new Response('{"rows":[]}', { status: 200 }));
  const got = makeApi("").trail();
  await vi.runAllTimersAsync();
  expect(await got).toEqual({ rows: [] });
  expect(f).toHaveBeenCalledTimes(2);
  vi.useRealTimers();
});

test("a GET that fails twice reports the lost connection", async () => {
  vi.useFakeTimers();
  const f = vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
  const got = makeApi("").trail();
  const caught = got.catch((e) => e);
  await vi.runAllTimersAsync();
  expect(await caught).toBeInstanceOf(TypeError);
  expect(f).toHaveBeenCalledTimes(2);
  vi.useRealTimers();
});

test("a POST is never retried: the request may already have landed", async () => {
  const f = vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
  await expect(makeApi("/sandbox").readNote("panen 12 kg", "me")).rejects.toBeInstanceOf(TypeError);
  expect(f).toHaveBeenCalledTimes(1);
});
