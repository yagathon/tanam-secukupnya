import { describe, expect, it } from "vitest";
import { bedLeftText } from "./bedLeft";

describe("bedLeftText", () => {
  it("gives plants, % of a full bed and kg at today's size", () => {
    // 1000 seedlings × 0.9 survival = 900 plants when full; 100 left at 89 g
    expect(bedLeftText({ label: "Bed 9", seedlings: 1000, plants_left: 100, avg_g: 89 }, 0.9))
      .toBe("App estimate for Bed 9: ~100 plants left (~11% of full) ≈ 8.9 kg at ~89 g a plant.");
  });
  it("says empty when the app counts nothing left", () => {
    expect(bedLeftText({ label: "Bed 2", seedlings: 500, plants_left: 0, avg_g: 90 }, 0.9))
      .toBe("App estimate for Bed 2: empty.");
  });
  it("leaves out kg while the size is unknown", () => {
    expect(bedLeftText({ label: "Bed 3", seedlings: 200, plants_left: 180, avg_g: null }, 0.9))
      .toBe("App estimate for Bed 3: ~180 plants left (~100% of full).");
  });
});
