import { describe, it, expect } from "vitest";
import {
  bandsFor,
  SHADING_LABELS,
  SHADING_DESCRIPTIONS,
  SHADING_FILL_OPACITY,
  type ShadingKey,
} from "./shading-presets";

describe("bandsFor", () => {
  it("returns NBER recessions including the 2020 COVID band", () => {
    const bands = bandsFor("recessions");
    // 13 NBER-dated cycles since 1945 (1945, '48-49, '53-54, '57-58,
    // '60-61, '69-70, '73-75, 1980, '81-82, '90-91, 2001, '07-09, 2020).
    expect(bands.length).toBe(13);
    const covid = bands.find((b) => b.start === "2020-02-01");
    expect(covid).toBeDefined();
    expect(covid!.end).toBe("2020-04-30");
  });

  it("returns 8 S&P 500 bear markets including the 2022 inflation bear", () => {
    const bands = bandsFor("bear_markets");
    expect(bands.length).toBe(8);
    const inflation22 = bands.find((b) => b.start === "2022-01-03");
    expect(inflation22).toBeDefined();
    expect(inflation22!.label).toContain("2022");
  });

  it("tags presidential terms with party-coded fills", () => {
    const bands = bandsFor("president_party");
    // FDR is the first; Trump (2nd) is the most recent. 16 entries.
    expect(bands.length).toBe(16);
    const fdr = bands[0];
    expect(fdr.label).toContain("FDR");
    // FDR was Democratic; fill should match the blue.
    expect(fdr.fill).toBe("#3B82F6");
    // GHW Bush was Republican.
    const ghwb = bands.find((b) => b.label.includes("G.H.W. Bush"));
    expect(ghwb).toBeDefined();
    expect(ghwb!.fill).toBe("#EF4444");
  });

  it("Senate majority covers 80th Congress onward and includes the 2001 Jeffords switch", () => {
    const bands = bandsFor("senate_majority");
    // The Jeffords switch (Republican Sen. Jeffords becoming independent
    // and caucusing with Democrats on 2001-06-06) splits the 107th
    // Congress into two consecutive bands at that date.
    const jeffords = bands.find((b) => b.start === "2001-06-06");
    expect(jeffords).toBeDefined();
    expect(jeffords!.label).toContain("Democratic");
  });

  it("Fed Chair tenures alternate fills for visual contrast", () => {
    const bands = bandsFor("fed_chairs");
    // Volcker through Powell — 5 chairs.
    expect(bands.length).toBe(5);
    // Even-indexed (Volcker, Bernanke, Powell) share one fill; odd-
    // indexed (Greenspan, Yellen) share the other.
    expect(bands[0].fill).not.toBe(bands[1].fill);
    expect(bands[0].fill).toBe(bands[2].fill);
  });

  it("returns an empty list for unknown keys (forward-compat)", () => {
    const bands = bandsFor("not_a_real_preset" as unknown as ShadingKey);
    expect(bands).toEqual([]);
  });
});

describe("SHADING_LABELS and SHADING_DESCRIPTIONS", () => {
  it("has a label + description for every preset key", () => {
    // Every key in LABELS should appear in DESCRIPTIONS and vice versa.
    // The keys also need to match what bandsFor() handles.
    const keys = Object.keys(SHADING_LABELS) as ShadingKey[];
    expect(keys.length).toBe(6);
    for (const k of keys) {
      expect(SHADING_DESCRIPTIONS[k]).toBeTruthy();
      expect(bandsFor(k).length).toBeGreaterThan(0);
    }
  });
});

describe("SHADING_FILL_OPACITY", () => {
  it("is low enough that the underlying line stays readable", () => {
    // Tuned to keep bands as background context, not foreground.
    // 0.5 would be too dominant; anything below 0.05 is invisible.
    expect(SHADING_FILL_OPACITY).toBeGreaterThan(0.05);
    expect(SHADING_FILL_OPACITY).toBeLessThanOrEqual(0.25);
  });
});
