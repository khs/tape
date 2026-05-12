import { describe, it, expect } from "vitest";
import { combineTwo, combineOpLabel } from "./derive";
import type { TimeSeriesData } from "./data-types";

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
