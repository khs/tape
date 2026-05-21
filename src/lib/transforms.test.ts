import { describe, it, expect } from "vitest";
import {
  applyYoYPercent,
  applyIndex100,
  applyTransform,
  transformFormatting,
  TRANSFORM_LABELS,
} from "./transforms";

// Helper to build a monthly series. value(i) = 100 + i, dates run
// monthly from 2020-01-01 onward.
function monthly(n: number, value: (i: number) => number): { t: string; v: number }[] {
  const pts: { t: string; v: number }[] = [];
  const start = new Date(Date.UTC(2020, 0, 1));
  for (let i = 0; i < n; i++) {
    const d = new Date(start);
    d.setUTCMonth(d.getUTCMonth() + i);
    pts.push({ t: d.toISOString().slice(0, 10), v: value(i) });
  }
  return pts;
}

describe("applyYoYPercent", () => {
  it("returns empty for empty input", () => {
    expect(applyYoYPercent([])).toEqual([]);
  });

  it("drops the first year of points (no prior to compare against)", () => {
    // 18 monthly points: first 12 should be dropped, last 6 kept.
    const pts = monthly(18, (i) => 100 + i);
    const out = applyYoYPercent(pts);
    expect(out.length).toBeLessThanOrEqual(7); // 6 or 7 depending on day-rounding
    expect(out.length).toBeGreaterThanOrEqual(6);
  });

  it("computes 10% YoY when v doubles by 10%", () => {
    // Two points exactly one year apart: 100 -> 110.
    // Use 366 days to be safely over the 365-day threshold.
    const pts: { t: string; v: number }[] = [
      { t: "2020-01-01", v: 100 },
      { t: "2021-01-02", v: 110 },
    ];
    const out = applyYoYPercent(pts);
    expect(out.length).toBe(1);
    expect(out[0].t).toBe("2021-01-02");
    expect(out[0].v).toBeCloseTo(10, 5);
  });

  it("handles negative YoY (contraction)", () => {
    const pts: { t: string; v: number }[] = [
      { t: "2020-01-01", v: 100 },
      { t: "2021-01-02", v: 80 },
    ];
    const out = applyYoYPercent(pts);
    expect(out.length).toBe(1);
    expect(out[0].v).toBeCloseTo(-20, 5);
  });

  it("skips points where prior is zero", () => {
    const pts: { t: string; v: number }[] = [
      { t: "2020-01-01", v: 0 },
      { t: "2021-01-02", v: 50 },
    ];
    expect(applyYoYPercent(pts)).toEqual([]);
  });

  it("uses the latest at-or-before-target prior on irregular series", () => {
    // Sparse: 2020-01, 2020-06, 2021-02. The 2021-02 should compare
    // against 2020-06 (the most recent point at or before 2020-02
    // — wait, 2020-06 is AFTER 2020-02, so it's not eligible. The
    // 2020-01 IS eligible. Let me re-derive.)
    //
    // Target for 2021-02-01 is 365 days prior = 2020-02-02. Latest
    // point at or before that is 2020-01-01. So YoY is computed
    // against 2020-01-01 = 100.
    const pts: { t: string; v: number }[] = [
      { t: "2020-01-01", v: 100 },
      { t: "2020-06-01", v: 110 },
      { t: "2021-02-01", v: 150 },
    ];
    const out = applyYoYPercent(pts);
    expect(out.length).toBe(1);
    expect(out[0].v).toBeCloseTo(50, 5); // (150 - 100) / 100 * 100
  });
});

describe("applyIndex100", () => {
  it("returns empty for empty input", () => {
    expect(applyIndex100([])).toEqual([]);
  });

  it("anchors first point at exactly 100", () => {
    const pts = monthly(6, (i) => 50 + i * 10);
    const out = applyIndex100(pts);
    expect(out[0].v).toBe(100);
  });

  it("scales subsequent points proportionally", () => {
    const pts = [
      { t: "2020-01-01", v: 200 },
      { t: "2020-02-01", v: 220 }, // +10%
      { t: "2020-03-01", v: 180 }, // -10%
    ];
    const out = applyIndex100(pts);
    expect(out[0].v).toBe(100);
    expect(out[1].v).toBeCloseTo(110, 5);
    expect(out[2].v).toBeCloseTo(90, 5);
  });

  it("returns empty when baseline is zero", () => {
    const pts = [
      { t: "2020-01-01", v: 0 },
      { t: "2020-02-01", v: 50 },
    ];
    expect(applyIndex100(pts)).toEqual([]);
  });
});

describe("applyTransform — dispatch", () => {
  const pts = monthly(15, (i) => 100 + i);

  it("level passes points through unchanged", () => {
    expect(applyTransform(pts, "level")).toEqual(pts);
  });

  it("yoy_pct routes to applyYoYPercent", () => {
    expect(applyTransform(pts, "yoy_pct").length).toBe(
      applyYoYPercent(pts).length,
    );
  });

  it("index_100 routes to applyIndex100 with v[0] = 100", () => {
    const out = applyTransform(pts, "index_100");
    expect(out[0].v).toBe(100);
  });
});

describe("transformFormatting", () => {
  const baseCurrency = { style: "currency" as const, decimals: 2 };

  it("level returns the input formatting unchanged", () => {
    expect(transformFormatting(baseCurrency, "level")).toEqual(baseCurrency);
  });

  it("yoy_pct returns percent style regardless of input", () => {
    const fmt = transformFormatting(baseCurrency, "yoy_pct");
    expect(fmt.style).toBe("percent");
    expect(fmt.decimals).toBe(1);
  });

  it("index_100 returns dimensionless 1-decimal number", () => {
    const fmt = transformFormatting(baseCurrency, "index_100");
    expect(fmt.style).toBe("number");
    expect(fmt.decimals).toBe(1);
  });
});

describe("TRANSFORM_LABELS", () => {
  it("has a label for every key", () => {
    expect(TRANSFORM_LABELS.level).toBe("Level");
    expect(TRANSFORM_LABELS.yoy_pct).toBe("YoY %");
    expect(TRANSFORM_LABELS.index_100).toBe("Index = 100");
  });
});
