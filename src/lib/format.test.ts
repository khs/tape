import { describe, it, expect } from "vitest";
import { formatValue, formatDelta } from "./format";

describe("formatValue — basic styles", () => {
  it("renders percent values with explicit %", () => {
    expect(formatValue(4.42, { style: "percent", decimals: 2 })).toBe("4.42%");
  });

  it("renders currency in USD by default", () => {
    expect(formatValue(123.45, { style: "currency", decimals: 2 })).toBe(
      "$123.45",
    );
  });

  it("renders bps with explicit suffix", () => {
    expect(formatValue(75, { style: "bps", decimals: 0 })).toBe("75 bps");
  });

  it("respects prefix and suffix overrides", () => {
    expect(
      formatValue(42, {
        style: "number",
        decimals: 0,
        prefix: ">",
        suffix: "x",
      }),
    ).toBe(">42x");
  });
});

describe("formatValue — compact notation smart decimals", () => {
  // The smart-decimal rule for compact notation: 3 leading digits → 0 decimals,
  // 2 → 1, 1 → 2. Goal is ~3 significant figures in the rendered string.

  it("3 leading digits → 0 decimals (no '$456.78B' garbage)", () => {
    expect(
      formatValue(456_000_000_000, {
        style: "currency",
        decimals: 2, // user-requested decimals are *ignored* in compact mode
        notation: "compact",
      }),
    ).toBe("$456B");
  });

  it("2 leading digits → 1 decimal", () => {
    expect(
      formatValue(45_600_000_000, {
        style: "currency",
        decimals: 2,
        notation: "compact",
      }),
    ).toBe("$45.6B");
  });

  it("1 leading digit → 2 decimals", () => {
    expect(
      formatValue(3_410_000_000_000, {
        style: "currency",
        decimals: 0,
        notation: "compact",
      }),
    ).toBe("$3.41T");
  });

  it("handles values below 1K without trillions/billions suffix", () => {
    // 42.5 → 2 leading digits → 1 decimal → "$42.5" (no T/B/M/K suffix
    // because the value is below the smallest band).
    const out = formatValue(42.5, {
      style: "currency",
      decimals: 2,
      notation: "compact",
    });
    expect(out).toMatch(/^\$42\.5/);
    expect(out).not.toMatch(/[TBMK]$/);
  });
});

describe("formatDelta", () => {
  it("returns + sign on the abs string for positive deltas", () => {
    // formatDelta(current, prior, fmt) — current > prior means positive delta.
    const out = formatDelta(105, 100, { style: "percent", decimals: 2 });
    expect(out.abs).toMatch(/^\+/);
    expect(out.direction).toBe("up");
  });

  it("returns - (or −) on the abs string for negative deltas", () => {
    const out = formatDelta(95, 100, { style: "percent", decimals: 2 });
    expect(out.abs).toMatch(/^[−-]/);
    expect(out.direction).toBe("down");
  });

  it("flags direction='flat' when delta is effectively zero", () => {
    const out = formatDelta(100, 100, { style: "percent", decimals: 2 });
    expect(out.direction).toBe("flat");
  });
});
