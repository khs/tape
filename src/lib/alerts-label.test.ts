/**
 * Lockdown tests for the alerts default-label composer.
 *
 * Copy changes here ship to every user's alert email subject line +
 * UI list — exercising the branches in tests means a typo or
 * accidental rephrase shows up in CI rather than in production.
 */
import { describe, test, expect } from "vitest";
import {
  composeDefaultLabel,
  conditionPhrase,
  type AlertCondition,
} from "./alerts-label";

describe("conditionPhrase", () => {
  test("emits math symbols for simple comparisons", () => {
    expect(conditionPhrase("gt")).toBe(">");
    expect(conditionPhrase("gte")).toBe("≥");
    expect(conditionPhrase("lt")).toBe("<");
    expect(conditionPhrase("lte")).toBe("≤");
  });
  test("emits words for cross + change ops", () => {
    expect(conditionPhrase("crosses_above")).toBe("crosses above");
    expect(conditionPhrase("crosses_below")).toBe("crosses below");
    expect(conditionPhrase("change_above")).toBe("changes by more than");
  });
});

describe("composeDefaultLabel — basic shape", () => {
  test("produces 'name op threshold' for the user-quoted CPI example", () => {
    // The example the user gave when speccing this feature; locks the
    // exact phrasing down so casual edits to conditionPhrase don't
    // silently change the demo.
    expect(
      composeDefaultLabel({
        sourceName: "CPI year-over-year (US, all urban consumers)",
        condition: "gt",
        thresholdRaw: "4",
        formatting: { style: "percent", decimals: 1 },
      }),
    ).toBe("CPI year-over-year (US, all urban consumers) > 4.0%");
  });
  test("falls back to bare number when no formatting is provided", () => {
    expect(
      composeDefaultLabel({
        sourceName: "VIX",
        condition: "gte",
        thresholdRaw: "30",
      }),
    ).toBe("VIX ≥ 30");
  });
});

describe("composeDefaultLabel — unit handling", () => {
  test("percent style adds %", () => {
    expect(
      composeDefaultLabel({
        sourceName: "10-year Treasury yield",
        condition: "gte",
        thresholdRaw: "5",
        formatting: { style: "percent", decimals: 2 },
      }),
    ).toBe("10-year Treasury yield ≥ 5.00%");
  });
  test("currency style adds $", () => {
    expect(
      composeDefaultLabel({
        sourceName: "S&P 500",
        condition: "gte",
        thresholdRaw: "5000",
        formatting: { style: "currency", decimals: 0 },
      }),
    ).toBe("S&P 500 ≥ $5,000");
  });
  test("currency compact + scaleFactor renders trillion suffix", () => {
    // Mirrors the marketcap pattern: stored in billions, displayed
    // compact-with-T-suffix when over a trillion.
    expect(
      composeDefaultLabel({
        sourceName: "XOM market cap",
        condition: "gt",
        thresholdRaw: "500",
        formatting: {
          style: "currency",
          decimals: 0,
          notation: "compact",
          scaleFactor: 1e9,
        },
      }),
    ).toBe("XOM market cap > $500B");
  });
  test("bps style adds ' bps' suffix", () => {
    expect(
      composeDefaultLabel({
        sourceName: "10Y-2Y spread",
        condition: "crosses_below",
        thresholdRaw: "0",
        formatting: { style: "bps", decimals: 0 },
      }),
    ).toBe("10Y-2Y spread crosses below 0 bps");
  });
  test("index style renders no unit", () => {
    expect(
      composeDefaultLabel({
        sourceName: "Some index",
        condition: "lt",
        thresholdRaw: "100",
        formatting: { style: "index", decimals: 0 },
      }),
    ).toBe("Some index < 100");
  });
});

describe("composeDefaultLabel — incomplete inputs", () => {
  test.each<[string, AlertCondition, string]>([
    ["", "gt", "4"], // missing name
    ["VIX", "gt", ""], // missing threshold
    ["VIX", "gt", "  "], // whitespace-only threshold
    ["VIX", "gt", "not-a-number"], // unparseable threshold
    ["   ", "gt", "4"], // whitespace-only name
  ])(
    "returns '' for incomplete input (name=%s threshold=%s)",
    (sourceName, condition, thresholdRaw) => {
      expect(
        composeDefaultLabel({ sourceName, condition, thresholdRaw }),
      ).toBe("");
    },
  );
});

describe("composeDefaultLabel — cross + change phrasing", () => {
  test("crosses_above renders 'crosses above'", () => {
    expect(
      composeDefaultLabel({
        sourceName: "Spread",
        condition: "crosses_above",
        thresholdRaw: "0",
      }),
    ).toBe("Spread crosses above 0");
  });
  test("crosses_below renders 'crosses below'", () => {
    expect(
      composeDefaultLabel({
        sourceName: "Curve",
        condition: "crosses_below",
        thresholdRaw: "0",
      }),
    ).toBe("Curve crosses below 0");
  });
  test("change_above renders 'changes by more than'", () => {
    expect(
      composeDefaultLabel({
        sourceName: "GDP",
        condition: "change_above",
        thresholdRaw: "100",
        formatting: { style: "currency", decimals: 0 },
      }),
    ).toBe("GDP changes by more than $100");
  });
});

describe("composeDefaultLabel — derived-source labels", () => {
  test("composed 'A ÷ B' name passes through verbatim", () => {
    // Derived alerts use a composed source label like "CPI YoY ÷ 10Y
    // Treasury". The composer just treats it as the name string and
    // appends condition + threshold; no special handling needed.
    expect(
      composeDefaultLabel({
        sourceName: "CPI YoY ÷ 10-year Treasury",
        condition: "gt",
        thresholdRaw: "0.5",
      }),
    ).toBe("CPI YoY ÷ 10-year Treasury > 0.5");
  });
});
