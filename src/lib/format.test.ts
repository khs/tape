import { describe, it, expect } from "vitest";
import {
  formatValue,
  formatDelta,
  formatDeltaDisplay,
  formatSignedValue,
  formatDate,
  formatTimestamp,
  magnitudeFromFormatting,
} from "./format";

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

  it("uses the Unicode minus on the pct string for negative deltas", () => {
    // Same legibility rationale as formatValue — chart axes use the
    // typographic minus so the sign doesn't visually disappear.
    const out = formatDelta(95, 100, { style: "percent", decimals: 2 });
    expect(out.pct).toMatch(/^−/); // U+2212
    expect(out.pct).not.toMatch(/^-/); // U+002D
  });

  it("returns 0 pct when prior is zero (avoids divide-by-zero NaN)", () => {
    // Guard from the implementation: prior === 0 short-circuits to
    // pct = 0 rather than emitting NaN%/Infinity%.
    const out = formatDelta(5, 0, { style: "decimal", decimals: 2 });
    expect(out.pct).toContain("0.0%");
    expect(out.direction).toBe("up");
  });
});

describe("formatSignedValue", () => {
  // Used in headline-delta callouts on tile readouts; the leading sign
  // is mandatory regardless of sign (positive gets "+", negative gets
  // the Unicode minus).

  it("prefixes positive values with +", () => {
    expect(formatSignedValue(3.5, { style: "decimal", decimals: 2 })).toBe(
      "+3.50",
    );
  });

  it("prefixes zero with + (treated as non-negative)", () => {
    expect(formatSignedValue(0, { style: "decimal", decimals: 2 })).toBe(
      "+0.00",
    );
  });

  it("uses Unicode minus (U+2212), not ASCII hyphen, for negatives", () => {
    const out = formatSignedValue(-3.5, { style: "decimal", decimals: 2 });
    expect(out.startsWith("−")).toBe(true);
    expect(out.startsWith("-")).toBe(false);
    expect(out).toBe("−3.50");
  });

  it("respects the underlying formatter's style (percent / currency)", () => {
    expect(
      formatSignedValue(2.5, { style: "percent", decimals: 1 }),
    ).toBe("+2.5%");
    // Currency: USD prefix lives inside the formatted value, after the
    // explicit +.
    const dollars = formatSignedValue(100, {
      style: "currency",
      decimals: 0,
    });
    expect(dollars.startsWith("+")).toBe(true);
    expect(dollars).toContain("$100");
  });
});

describe("formatDeltaDisplay", () => {
  // The dual-mode display: percent style shows "+X% (+Y%)" because the
  // absolute and relative change are both informative; non-percent
  // styles show only "+X%".

  it("emits 'pct (abs)' for percent-style sources", () => {
    // unemployment 3.5 → 3.7: pct ≈ +5.7%, abs = +0.2%
    const out = formatDeltaDisplay(3.7, 3.5, {
      style: "percent",
      decimals: 1,
    });
    expect(out.text).toMatch(/^\+\d+\.\d%/); // starts with the relative
    expect(out.text).toContain("(");
    expect(out.text).toContain("+0.2");
  });

  it("emits just 'pct' for non-percent sources (decimal / currency)", () => {
    // GDP $100B → $105B: pct = +5.0%, no parens.
    const out = formatDeltaDisplay(105, 100, {
      style: "decimal",
      decimals: 0,
    });
    expect(out.text).toContain("%");
    expect(out.text).not.toContain("(");
  });

  it("carries direction through", () => {
    expect(
      formatDeltaDisplay(105, 100, { style: "decimal", decimals: 0 }).direction,
    ).toBe("up");
    expect(
      formatDeltaDisplay(95, 100, { style: "decimal", decimals: 0 }).direction,
    ).toBe("down");
    expect(
      formatDeltaDisplay(100, 100, { style: "decimal", decimals: 0 }).direction,
    ).toBe("flat");
  });

  it("exposes pct and abs as separate fields too", () => {
    // The tile renderer reads .pct directly for the colored badge and
    // .abs for the hover-card detail.
    const out = formatDeltaDisplay(105, 100, {
      style: "percent",
      decimals: 2,
    });
    expect(out.pct).toMatch(/%$/);
    expect(out.abs).toMatch(/^\+/);
  });
});

describe("formatDate", () => {
  // en-US locale, "MMM d, yyyy" — used for tile date labels and the
  // "as of <date>" copy under tiles.
  //
  // formatDate calls toLocaleDateString in local time, so test inputs
  // use local-time ISO strings (no Z) at midday to avoid timezone-
  // boundary drift between machines / CI runners.

  it("renders an ISO date+time string in 'MMM d, yyyy' form", () => {
    expect(formatDate("2024-01-15T12:00:00")).toBe("Jan 15, 2024");
    expect(formatDate("2024-06-30T12:00:00")).toBe("Jun 30, 2024");
    expect(formatDate("2024-12-31T12:00:00")).toBe("Dec 31, 2024");
  });

  it("renders single-digit days without zero-padding", () => {
    // "Jan 5, 2024" — not "Jan 05, 2024" — per en-US norms.
    expect(formatDate("2024-01-05T12:00:00")).toBe("Jan 5, 2024");
  });

  it("uses en-US month abbreviations (3-letter month form)", () => {
    // Lockdown: the locale must stay en-US. A drift to e.g. "en-GB"
    // would re-order the fields ("15 Jan 2024"); to "fr-FR" would
    // change the month spelling.
    const out = formatDate("2024-09-15T12:00:00");
    expect(out).toContain("Sep");
    expect(out).toContain("2024");
    expect(out).toContain("15");
  });
});

describe("formatTimestamp", () => {
  // Same locale, includes the time portion. Used in chart annotations
  // and pipeline-last-run displays.

  it("includes both date and a time portion", () => {
    // Format is locale-dependent in punctuation; assert the structural
    // parts rather than exact whitespace.
    const out = formatTimestamp("2024-01-15T14:30:00Z");
    expect(out).toContain("2024");
    expect(out).toMatch(/Jan(?:uary)?\s+15/);
    // Hour should appear somewhere (the actual value depends on the
    // test runner's timezone, so just check that a digit + colon pair
    // is present — that's the hour:minute separator).
    expect(out).toMatch(/\d:\d/);
  });
});
