import { describe, it, expect } from "vitest";
import { combineTwo, combineOpLabel, combineOpFormatting } from "./derive";
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

  it("currency / index → fallback (mixed styles)", () => {
    const r = combineOpFormatting(FMT_CURRENCY, FMT_INDEX, "divide");
    expect(r.formatting.style).toBe("number");
    expect(r.multiplier).toBe(1);
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
