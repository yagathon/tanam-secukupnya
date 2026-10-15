import { describe, expect, it } from "vitest";

import { ApiError } from "./api";
import { conflict, readAgain } from "./notes";
import type { NoteDoc } from "./types";

const old = { id: "n1", text: "besok 15 kg", sender: "resto_a" } as NoteDoc;

function fakeApi(read: () => Promise<Partial<NoteDoc>>) {
  const decided: string[] = [];
  return {
    decided,
    readNote: async () => (await read()) as NoteDoc,
    decideNote: async (id: string, accept: boolean) => {
      decided.push(`${id}:${accept}`);
      return {} as NoteDoc;
    },
  };
}

describe("readAgain", () => {
  it("rejects the old note only after the new read succeeded", async () => {
    const a = fakeApi(async () => ({ id: "n2", status: "proposed" }));
    expect((await readAgain(old, a)).id).toBe("n2");
    expect(a.decided).toEqual(["n1:false"]);
  });
  it("keeps the old note when Gemini refuses", async () => {
    const a = fakeApi(async () => { throw new ApiError(429, "x"); });
    await expect(readAgain(old, a)).rejects.toThrow();
    expect(a.decided).toEqual([]);
  });
  it("keeps the old note when the new read finds nothing to do", async () => {
    const a = fakeApi(async () => ({ id: "n2", status: "no_action", summary_en: "just a greeting" }));
    expect((await readAgain(old, a)).status).toBe("no_action");
    expect(a.decided).toEqual([]);
  });
});

describe("conflict", () => {
  it("tells the three 409s apart", () => {
    expect(conflict(new ApiError(409, "the farm has moved on since this note was read; read it again"))).toBe("stale");
    expect(conflict(new ApiError(409, "note is already accepted"))).toBe("decided");
    expect(conflict(new ApiError(409, "the farm changed while accepting this note; try again"))).toBe("retry");
    expect(conflict(new ApiError(429, "x"))).toBeNull();
    expect(conflict(new TypeError("x"))).toBeNull();
  });
});
