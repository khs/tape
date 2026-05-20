import { describe, it, expect } from "vitest";
import { formatValue, formatDelta, magnitudeFromFormatting } from "./format";

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

describe("formatValue — scaleFactor", () => {
  // scaleFactor lets a series stored in billions render as raw
  // dollars under compact notation, so 1631 (billions of dollars)
  // becomes "$1.63T" via scaleFactor: 1e9 instead of the wrong
  // "$1.63K" you'd get without scaling.

  it("multiplies before compact formatting (billions stored → trillions displayed)", () => {
    expect(
      formatValue(1631, {
        style: "currency",
        decimals: 1,
        notation: "compact",
        scaleFactor: 1e9,
      }),
    ).toBe("$1.63T");
  });

  it("applies scaleFactor to non-currency styles too", () => {
    // 5.5 (count, in millions) × 1e6 → 5,500,000 → "5.50M" (the
    // smart-decimal rule picks 2 dp because the leading-digit count
    // is 1).
    expect(
      formatValue(5.5, {
        style: "number",
        decimals: 1,
        notation: "compact",
        scaleFactor: 1e6,
      }),
    ).toBe("5.50M");
  });

  it("treats missing scaleFactor as 1 (no scaling)", () => {
    expect(
      formatValue(456_000_000_000, {
        style: "currency",
        decimals: 2,
        notation: "compact",
      }),
    ).toBe("$456B");
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

describe("magnitudeFromFormatting", () => {
  // Reads the suffix to infer how many raw base units a stored value
  // represents. ChartController uses this to rescale mixed-magnitude
  // series onto a common axis (e.g. raw share price + market cap in
  // billions). Per-suffix mapping below; everything else returns 1.

  it("' B' suffix → 1e9 (billions)", () => {
    expect(
      magnitudeFromFormatting({
        style: "currency",
        decimals: 1,
        suffix: " B",
      }),
    ).toBe(1e9);
  });

  it("' M' suffix → 1e6 (millions)", () => {
    expect(
      magnitudeFromFormatting({
        style: "number",
        decimals: 1,
        suffix: " M",
      }),
    ).toBe(1e6);
  });

  it("' T' suffix → 1e12 (trillions)", () => {
    expect(
      magnitudeFromFormatting({
        style: "currency",
        decimals: 2,
        suffix: " T",
      }),
    ).toBe(1e12);
  });

  it("no suffix → 1 (raw)", () => {
    expect(
      magnitudeFromFormatting({
        style: "currency",
        decimals: 2,
      }),
    ).toBe(1);
  });

  it("falls back to scaleFactor when notation=compact", () => {
    // Compact-notation series that store in billions but render via
    // Intl's compact suffix-picker still need a magnitude. scaleFactor
    // IS the storage magnitude in that case.
    expect(
      magnitudeFromFormatting({
        style: "currency",
        decimals: 1,
        notation: "compact",
        scaleFactor: 1e9,
      }),
    ).toBe(1e9);
  });

  it("unknown suffix (' bps') → 1 (treat as raw)", () => {
    expect(
      magnitudeFromFormatting({
        style: "bps",
        decimals: 0,
        suffix: " bps",
      }),
    ).toBe(1);
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
