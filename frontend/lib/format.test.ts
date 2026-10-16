import { describe, expect, it } from "vitest";

import { ApiError } from "./api";
import { daySentence, friendly, int, kg, lineName, loggedToday, proposalLines, scopeName, shortDate, sowDays, tsp } from "./format";
import type { Proposal, State, TodayLine, TrailRow } from "./types";

const state = {
  today: "2026-10-12",
  synthetic: true,
  buyers: [{ id: "resto_a", alias: "Restaurant A", segment: "restaurant", weekdays: [], lines: {} }],
  households: [],
  senders: [],
} as unknown as State;

const empty: Proposal = { kind: "none", summary_en: "", orders: [], harvest: null, sowing: null, loss: null, signals: [] };

describe("numbers and dates", () => {
  it("kg keeps 1 decimal from 10 kg up, 2 below, and plain 0", () => {
    expect(kg(37.17)).toBe("37.2 kg");
    expect(kg(1.76)).toBe("1.76 kg");
    expect(kg(0)).toBe("0 kg");
    expect(kg(0.004)).toBe("0 kg");
  });
  it("int groups thousands", () => expect(int(1350)).toBe("1,350"));
  it("shortDate reads like a calendar, in UTC (no timezone drift)", () => {
    expect(shortDate("2026-10-13")).toBe("Tue 13 Oct");
  });
  it("tsp rounds to kitchen fractions", () => {
    expect(tsp(4 / 3)).toBe("1⅓ tsp");
    expect(tsp(0.5)).toBe("½ tsp");
    expect(tsp(2)).toBe("2 tsp");
    expect(tsp(0.1)).toBe("<¼ tsp");
  });
  it("lineName", () => {
    expect(lineName("regular")).toBe("Pakcoy regular");
    expect(lineName("baby")).toBe("Pakcoy baby");
  });
});

describe("daySentence", () => {
  const base: TodayLine = {
    line: "regular", need_kg: 47, ceiling_kg: 42, send_kg: 42, short_kg: 5, rotated: ["Household 03"],
    sow: { day: "2026-10-15", weekday: "Thu", seedlings: 1350, seeds_g: 4.0, teaspoons: 4 / 3, shortfall_ahead_kg: 0 },
  };
  it("says who rotates when short", () => {
    expect(daySentence(base)).toBe(
      "Max safe tomorrow 42.0 kg · need 47.0 kg · short 5.00 kg → Household 03 rotates · Thu: sow 1,350 seedlings ≈ 4.0 g ≈ 1⅓ tsp",
    );
  });
  it("says send when nothing is short", () => {
    const ok = { ...base, need_kg: 37.17, ceiling_kg: 108.39, send_kg: 37.17, short_kg: 0, rotated: [] };
    expect(daySentence(ok)).toBe(
      "Send 37.2 kg tomorrow (max safe 108.4 kg) · Thu: sow 1,350 seedlings ≈ 4.0 g ≈ 1⅓ tsp",
    );
  });
  it("handles a day with no need", () => {
    const zero = { ...base, need_kg: 0, send_kg: 0, short_kg: 0, rotated: [] };
    expect(daySentence(zero)).toMatch(/^Nothing to send tomorrow · Thu: sow/);
  });
  it("mentions shortfall ahead", () => {
    const ahead = { ...base, short_kg: 0, rotated: [], sow: { ...base.sow, shortfall_ahead_kg: 12.5 } };
    expect(daySentence(ahead)).toMatch(/ · 12\.5 kg short ahead$/);
  });
});

describe("proposalLines", () => {
  it("orders", () => {
    const p = { ...empty, kind: "orders", orders: [{ buyer: "resto_a", line: "regular", kg: 15, day: "2026-10-13" }] } as Proposal;
    expect(proposalLines(p, state)).toEqual(["Restaurant A orders 15.0 kg Pakcoy regular for Tue 13 Oct"]);
  });
  it("harvest with and without sample", () => {
    const h = { ...empty, kind: "harvest", harvest: { bed: "Bed 41", batch: "b", kg: 11.5, big5_g: 620, small5_g: 310 } } as Proposal;
    expect(proposalLines(h, state)).toEqual(["Bed 41: harvested 11.5 kg · 5 biggest 620 g, 5 smallest 310 g"]);
    const h2 = { ...h, harvest: { ...h.harvest!, big5_g: null, small5_g: null } };
    expect(proposalLines(h2, state)).toEqual(["Bed 41: harvested 11.5 kg · no size sample"]);
  });
  it("sowing done and postponed", () => {
    const s = { ...empty, kind: "sowing", sowing: { line: "regular", postponed: false, seedlings: 1200, reason: "" } } as Proposal;
    expect(proposalLines(s, state)).toEqual(["Sowed 1,200 seedlings of Pakcoy regular today"]);
    const p = { ...s, sowing: { line: "baby", postponed: true, seedlings: null, reason: "heavy rain" } };
    expect(proposalLines(p, state)).toEqual(["Sowing of Pakcoy baby postponed: heavy rain"]);
  });
  it("loss", () => {
    const l = { ...empty, kind: "loss", loss: { bed: "Bed 2", batch: "b", pct: 30, cause: "caterpillars", cause_category: "pest" } } as Proposal;
    expect(proposalLines(l, state)).toEqual(["Bed 2: 30% of the plants lost (pest: caterpillars)"]);
  });
  it("signal", () => {
    const g = {
      ...empty, kind: "signal",
      signals: [{ scope: "buyer:resto_a", line: null, effect_pct: -50, date_from: "2026-10-19", date_to: "2026-10-25",
        open_ended: false, cause: "kitchen renovation", cause_category: "renovation" }],
    } as Proposal;
    expect(proposalLines(g, state)).toEqual(["Restaurant A, all lines: −50% from Mon 19 Oct to Sun 25 Oct (kitchen renovation)"]);
    const open = { ...g, signals: [{ ...g.signals[0], scope: "channel:B2C", effect_pct: 100, open_ended: true }] };
    expect(proposalLines(open, state)).toEqual(["Households, all lines: +100% from Mon 19 Oct onward (kitchen renovation)"]);
  });
  it("none and legacy/partial notes fall back to nothing (the card shows the summary)", () => {
    expect(proposalLines(empty, state)).toEqual([]);
    expect(proposalLines({ kind: "signal" } as unknown as Proposal, state)).toEqual([]);
    expect(proposalLines(undefined as unknown as Proposal, state)).toEqual([]);
  });
});

describe("scopeName", () => {
  it("names every scope", () => {
    expect(scopeName("all", state)).toBe("Everyone");
    expect(scopeName("channel:B2B", state)).toBe("Restaurants & caterers");
    expect(scopeName("channel:B2C", state)).toBe("Households");
    expect(scopeName("buyer:resto_a", state)).toBe("Restaurant A");
    expect(scopeName("buyer:ghost", state)).toBe("ghost");
  });
});

describe("friendly", () => {
  it("passes the API's own sentence through for 409 and 422", () => {
    expect(friendly(new ApiError(409, "the farm has moved on since this note was read; read it again")))
      .toBe("The farm has moved on since this note was read; read it again.");
    expect(friendly(new ApiError(422, "cannot apply this note (unknown batch)"))).toBe("Cannot apply this note (unknown batch).");
  });
  it("explains Gemini limits and failures", () => {
    expect(friendly(new ApiError(429, "x"))).toBe("Today's Gemini budget for this demo is used up. Try again tomorrow.");
    expect(friendly(new ApiError(502, "x"))).toBe("Gemini could not read the note just now. Try again in a moment.");
  });
  it("explains auth and network trouble", () => {
    expect(friendly(new ApiError(401, "x"))).toBe("Your demo session expired. Reload the page.");
    expect(friendly(new TypeError("Failed to fetch"))).toBe("Could not reach the server. Check the connection and retry.");
    expect(friendly("weird")).toBe("Something went wrong. Reload the page and try again.");
  });
  it("never shows raw codes or server pages", () => {
    const fb = Object.assign(new Error("Firebase: Error (auth/network-request-failed)."), { code: "auth/network-request-failed" });
    expect(friendly(fb)).toBe("Could not reach the server. Check the connection and retry.");
    expect(friendly(new Error("Firebase: Error (auth/internal-error)."))).toBe("Something went wrong. Reload the page and try again.");
    expect(friendly(new ApiError(503, "<html><body>Service Unavailable</body></html>")))
      .toBe("The server had a problem. Try again in a moment.");
    expect(friendly(new ApiError(500, "Internal Server Error"))).toBe("The server had a problem. Try again in a moment.");
  });
});

describe("sowDays", () => {
  it("names the setup's sowing weekdays (0 = Monday) and how often", () => {
    expect(sowDays([0, 3])).toBe("twice a week, on Mondays and Thursdays");
    expect(sowDays([2])).toBe("once a week, on Wednesdays");
    expect(sowDays([4, 0, 2])).toBe("3 times a week, on Mondays, Wednesdays and Fridays");
    expect(sowDays([0, 1, 2, 3, 4, 5, 6])).toBe("every day");
  });
});

describe("loggedToday", () => {
  const row = (live: boolean, inputs: string[]) => ({ day: "2026-10-12", live, lines: {}, inputs, ref: [] }) as TrailRow;
  it("is everything logged on the open day, in order, not only the last entry", () => {
    expect(loggedToday([row(true, ["ORDER · A", "HARVEST · Bed 1"]), row(false, ["SOW · regular"])]))
      .toEqual(["ORDER · A", "HARVEST · Bed 1"]);
    expect(loggedToday([])).toEqual([]);
  });
});
