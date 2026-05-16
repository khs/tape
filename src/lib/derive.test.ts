import { describe, it, expect } from "vitest";
import {
  combineTwo,
  combineOpLabel,
  combineOpFormatting,
  inferUnitClassFromFormatting,
  applyPercentDisplayOverride,
} from "./derive";
import type { TimeSeriesData } from "./data-types";
import type { Formatting } from "./format";

const FMT_CURRENCY: Formatting = { style: "currency", currency: "USD", decimals: 0 };
const FMT_PERCENT: Formatting = { style: "percent", decimals: 2 };
const FMT_NUMBER: Formatting = { style: "number", decimals: 2 };
const FMT_INDEX: Formatting = { style: "index", decimals: 1 };

function mkSeries(id: string, points: { t: string; v: number }[]): TimeSeriesData {
  return {
    id,
    name: id,
    kind: "timeseries",
    unit: "",
    lastUpdated: "2025-01-01T00:00:00Z",
    points,
  };
}

describe("combineOpLabel", () => {
  it("maps each op to a UI symbol", () => {
    expect(combineOpLabel("divide")).toBe("÷");
    expect(combineOpLabel("sum")).toBe("+");
    expect(combineOpLabel("diff")).toBe("−");
  });
});

describe("combineOpFormatting", () => {
  // Lock down the cross-unit divide rules — these are the heuristics
  // that translate "CA federal $ / US GDP" (raw ratio 0.011) into the
  // human-friendly "1.10%" displayed in the dashboard tile. If the
  // multiplier or output style changes, this test catches it.

  it("currency / currency → percent with x100 multiplier", () => {
    const r = combineOpFormatting(FMT_CURRENCY, FMT_CURRENCY, "divide");
    expect(r.formatting.style).toBe("percent");
    expect(r.formatting.decimals).toBe(2);
    expect(r.multiplier).toBe(100);
  });

  it("number / number → percent with x100 multiplier (same-style ratio)", () => {
    const r = combineOpFormatting(FMT_NUMBER, FMT_NUMBER, "divide");
    expect(r.formatting.style).toBe("percent");
    expect(r.multiplier).toBe(100);
  });

  it("percent / percent → percent with x100 multiplier (ratio of rates)", () => {
    const r = combineOpFormatting(FMT_PERCENT, FMT_PERCENT, "divide");
    expect(r.formatting.style).toBe("percent");
    expect(r.multiplier).toBe(100);
  });

  it("currency / number → fallback to plain 4-decimal number", () => {
    // Mixed styles (e.g. currency / count): no good general unit,
    // generic numeric ratio with no multiplier.
    const r = combineOpFormatting(FMT_CURRENCY, FMT_NUMBER, "divide");
    expect(r.formatting.style).toBe("number");
    expect(r.formatting.decimals).toBe(4);
    expect(r.multiplier).toBe(1);
  });

  it("currency / index (style-only dispatch) → deflation rule (A's fmt, x100)", () => {
    // Without explicit unitClass, FMT_INDEX has style: "index" which
    // inferUnitClassFromFormatting maps to "index". FMT_CURRENCY maps
    // to "currency". The currency/index rule kicks in.
    const r = combineOpFormatting(FMT_CURRENCY, FMT_INDEX, "divide");
    expect(r.formatting).toEqual(FMT_CURRENCY);
    expect(r.multiplier).toBe(100);
  });

  it("sum/diff → A's formatting, no multiplier", () => {
    const r1 = combineOpFormatting(FMT_CURRENCY, FMT_CURRENCY, "sum");
    expect(r1.formatting.style).toBe("currency");
    expect(r1.multiplier).toBe(1);
    const r2 = combineOpFormatting(FMT_PERCENT, FMT_CURRENCY, "diff");
    expect(r2.formatting.style).toBe("percent");
    expect(r2.multiplier).toBe(1);
  });

  it("handles undefined input formatting (defensive)", () => {
    const r = combineOpFormatting(undefined, undefined, "divide");
    expect(r.formatting.style).toBe("percent");
    expect(r.multiplier).toBe(100);
  });

  // unitClass-aware dispatch — these are the rules combineOpFormatting
  // gains once both sides pass an explicit unitClass alongside their
  // formatting. The old style-based same-class detection still works
  // (currency vs currency via formatting.style) but breaks down on
  // sources that share style "number" while semantically differing
  // (US GDP vs Case-Shiller, etc.).

  it("currency / count → $/unit display with x1e9 multiplier (per-capita)", () => {
    // FRED GDP-as-number + state population-as-count both stored as
    // style: number; the rule fires off the unitClass override.
    const fmt: Formatting = { style: "number", decimals: 0 };
    const r = combineOpFormatting(fmt, fmt, "divide", "currency", "count");
    expect(r.formatting.style).toBe("number");
    expect(r.formatting.prefix).toBe("$");
    expect(r.formatting.notation).toBe("compact");
    // Currency in billions ÷ raw count → multiply back to natural $.
    expect(r.multiplier).toBe(1e9);
  });

  it("currency / count via mixed formatter styles (style: currency + style: number)", () => {
    // Same rule should fire even when only unitClass distinguishes them.
    const aFmt: Formatting = { style: "currency", currency: "USD", decimals: 0 };
    const bFmt: Formatting = { style: "number", decimals: 0 };
    const r = combineOpFormatting(aFmt, bFmt, "divide", "currency", "count");
    expect(r.multiplier).toBe(1e9);
    expect(r.formatting.prefix).toBe("$");
  });

  it("count / count via unitClass → percent (same-class rule)", () => {
    const fmt: Formatting = { style: "number", decimals: 0 };
    const r = combineOpFormatting(fmt, fmt, "divide", "count", "count");
    expect(r.formatting.style).toBe("percent");
    expect(r.multiplier).toBe(100);
  });

  it("count / currency via unitClass → generic fallback (rare mixed-class)", () => {
    // Inverse-per-capita pair, no specialized rule. Falls to the
    // 4-decimal-number branch so the value at least renders.
    const aFmt: Formatting = { style: "number", decimals: 0 };
    const bFmt: Formatting = { style: "number", decimals: 0 };
    const r = combineOpFormatting(aFmt, bFmt, "divide", "count", "currency");
    expect(r.formatting.style).toBe("number");
    expect(r.formatting.decimals).toBe(4);
    expect(r.multiplier).toBe(1);
  });

  it("inferUnitClassFromFormatting maps obvious styles", () => {
    expect(inferUnitClassFromFormatting(FMT_CURRENCY)).toBe("currency");
    expect(inferUnitClassFromFormatting(FMT_PERCENT)).toBe("rate");
    expect(inferUnitClassFromFormatting(FMT_INDEX)).toBe("index");
    expect(inferUnitClassFromFormatting(FMT_NUMBER)).toBe("ratio");
    expect(inferUnitClassFromFormatting(undefined)).toBe("ratio");
  });

  it("currency / index via unitClass → A's formatting, x100 (deflation)", () => {
    // GDP-in-billions ÷ CPI-index, treated as base-100 deflation.
    const aFmt: Formatting = {
      style: "currency",
      currency: "USD",
      decimals: 1,
      suffix: " B",
    };
    const bFmt: Formatting = { style: "number", decimals: 1 };
    const r = combineOpFormatting(aFmt, bFmt, "divide", "currency", "index");
    expect(r.formatting).toEqual(aFmt);
    expect(r.multiplier).toBe(100);
  });
});

describe("applyPercentDisplayOverride", () => {
  // Each mode is a transformation of the same baseline percent
  // formatting. Locks down the percent/decimal/ratio dispatch and
  // the "no-op when output isn't percent" guard.
  const PERCENT_BASELINE = {
    formatting: { style: "percent", decimals: 2 } as Formatting,
    multiplier: 100,
  };

  it("'percent' or undefined → returns input unchanged", () => {
    expect(applyPercentDisplayOverride(PERCENT_BASELINE, undefined))
      .toEqual(PERCENT_BASELINE);
    expect(applyPercentDisplayOverride(PERCENT_BASELINE, "percent"))
      .toEqual(PERCENT_BASELINE);
  });

  it("'decimal' → 4-decimal number, multiplier 1", () => {
    const r = applyPercentDisplayOverride(PERCENT_BASELINE, "decimal");
    expect(r.formatting.style).toBe("number");
    expect(r.formatting.decimals).toBe(4);
    expect(r.multiplier).toBe(1);
  });

  it("'ratio' → 2-decimal number with ':1' suffix, multiplier 1", () => {
    const r = applyPercentDisplayOverride(PERCENT_BASELINE, "ratio");
    expect(r.formatting.style).toBe("number");
    expect(r.formatting.decimals).toBe(2);
    expect(r.formatting.suffix).toBe(":1");
    expect(r.multiplier).toBe(1);
  });

  it("any choice on non-percent input → returns input unchanged", () => {
    const nonPercent = {
      formatting: { style: "currency", currency: "USD", decimals: 0 } as Formatting,
      multiplier: 1,
    };
    expect(applyPercentDisplayOverride(nonPercent, "decimal")).toEqual(nonPercent);
    expect(applyPercentDisplayOverride(nonPercent, "ratio")).toEqual(nonPercent);
  });
});

describe("combineTwo — aligned timestamps", () => {
  const a = mkSeries("a", [
    { t: "2024-01-01", v: 100 },
    { t: "2024-02-01", v: 110 },
  ]);
  const b = mkSeries("b", [
    { t: "2024-01-01", v: 50 },
    { t: "2024-02-01", v: 55 },
  ]);

  it("divides element-wise", () => {
    expect(combineTwo(a, b, "divide")).toEqual([
      { t: "2024-01-01", v: 2 },
      { t: "2024-02-01", v: 2 },
    ]);
  });

  it("sums element-wise", () => {
    expect(combineTwo(a, b, "sum")).toEqual([
      { t: "2024-01-01", v: 150 },
      { t: "2024-02-01", v: 165 },
    ]);
  });

  it("differences element-wise (A minus B, not commutative)", () => {
    expect(combineTwo(a, b, "diff")).toEqual([
      { t: "2024-01-01", v: 50 },
      { t: "2024-02-01", v: 55 },
    ]);
  });
});

describe("combineTwo — mixed cadences (forward-fill)", () => {
  // Daily A vs monthly B. B's Jan-1 value forward-fills through Jan-15 and
  // Feb-1 updates it. Output has all union timestamps once both sides have
  // seen at least one point.
  const a = mkSeries("a", [
    { t: "2024-01-01", v: 100 },
    { t: "2024-01-15", v: 200 },
    { t: "2024-02-01", v: 300 },
  ]);
  const b = mkSeries("b", [
    { t: "2024-01-01", v: 10 },
    { t: "2024-02-01", v: 20 },
  ]);

  it("forward-fills the slower series", () => {
    expect(combineTwo(a, b, "divide")).toEqual([
      { t: "2024-01-01", v: 10 }, // 100 / 10
      { t: "2024-01-15", v: 20 }, // 200 / 10 (B forward-filled)
      { t: "2024-02-01", v: 15 }, // 300 / 20
    ]);
  });
});

describe("combineTwo — divide-by-zero handling", () => {
  it("skips points where B is zero (avoids Infinity/NaN)", () => {
    const a = mkSeries("a", [
      { t: "2024-01-01", v: 100 },
      { t: "2024-02-01", v: 200 },
    ]);
    const b = mkSeries("b", [
      { t: "2024-01-01", v: 0 },
      { t: "2024-02-01", v: 4 },
    ]);
    expect(combineTwo(a, b, "divide")).toEqual([{ t: "2024-02-01", v: 50 }]);
  });
});

describe("combineTwo — leading edge alignment", () => {
  it("waits for both sides to have seen a point before emitting", () => {
    const a = mkSeries("a", [
      { t: "2024-01-01", v: 1 },
      { t: "2024-02-01", v: 2 },
      { t: "2024-03-01", v: 3 },
    ]);
    const b = mkSeries("b", [{ t: "2024-02-15", v: 10 }]);
    // Jan-1 and Feb-1 have no B yet → skipped. Feb-15 onwards: B = 10.
    // Mar-1: A = 3 (latest), B = 10 (forward-filled) → 30.
    // Feb-15 itself emits only if A has been seen — it has (Feb-1 = 2).
    expect(combineTwo(a, b, "sum")).toEqual([
      { t: "2024-02-15", v: 12 },
      { t: "2024-03-01", v: 13 },
    ]);
  });
});
