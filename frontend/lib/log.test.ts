import { expect, test } from "vitest";
import { logFileName, pastBedsText, readLogFile } from "./log";

test("past beds summarize what left the table, or nothing when none did", () => {
  expect(pastBedsText({ beds: 5, harvested_plants: 2943, lost_plants: 239, waste_plants: 1318 }))
    .toBe("Earlier beds (5, no longer listed): 2,943 plants harvested · 239 lost · 1,318 wasted");
  expect(pastBedsText({ beds: 0, harvested_plants: 0, lost_plants: 0, waste_plants: 0 })).toBeNull();
  expect(pastBedsText(undefined)).toBeNull();
});

test("a log file is named by the farm's start and the day it was downloaded", () => {
  expect(logFileName("2026-10-17", "2026-12-04")).toBe("tanam-sandbox-2026-10-17_to_2026-12-04.json");
});

test("reading a log file accepts a downloaded log and says why anything else is refused", () => {
  const ok = { format: "tanam-sandbox-log", version: 1, setup: {}, log: [] };
  expect(readLogFile(JSON.stringify(ok))).toEqual(ok);
  expect(readLogFile("not json")).toEqual({ error: "That file is not JSON; choose a file from Download my log." });
  expect(readLogFile(JSON.stringify({ a: 1 }))).toEqual({ error: "That file is not a sandbox log; choose a file from Download my log." });
});
