import type { TimeSeriesData, TimeSeriesPoint } from "./data-types";
import type { Formatting } from "./format";

export type CombineOp = "divide" | "sum" | "diff";

const OP_LABELS: Record<CombineOp, string> = {
  divide: "÷",
  sum: "+",
  diff: "−",
};

export function combineOpLabel(op: CombineOp): string {
  return OP_LABELS[op];
}

/**
 * Output-formatting decision for a combineTwo result, plus an optional
 * multiplier applied to the combined values to make the chosen format
 * display sensibly.
 *
 * Two motivating cases the multiplier handles:
 *
 *   1. divide(currency, currency)
 *      Raw output is a unitless ratio (e.g. CA federal $ / US GDP ≈
 *      0.011). Displaying "0.011" forces the reader to mentally
 *      multiply; displaying "1.10%" doesn't. So we pick `percent`
 *      formatting and multiply the data by 100.
 *
 *   2. divide(count, count) / divide(number, number)
 *      Same idea — "ratio of two same-style quantities" reads better
 *      as a percent than as a 4-decimal fraction.
 *
 *  All other op/style combinations (sum, diff, divide across mismatched
 *  styles) fall back to either A's formatting or the existing 4-decimal
 *  number style with no multiplier.
 */
export interface OpFormatting {
  formatting: Formatting;
  /** Scalar applied to combineTwo's output before display. */
  multiplier: number;
}

/**
 * Apply the user's per-chart `percentDisplay` preference to an op
 * formatting decision. Only meaningful when the auto-chosen format is
 * percent (the common "ratio of two same-style quantities" case);
 * everywhere else the input is returned untouched.
 *
 * decimal mode: swap the formatting to a 4-decimal number AND drop the
 * ×100 multiplier the percent style needed, so values display as
 * "1.04" instead of "104%". This is the choice the user will reach for
 * on things like WTI / Brent (cross-commodity multiplier) where the
 * percent reading is technically correct but semantically awkward.
 */
export function applyPercentDisplayOverride(
  opFmt: OpFormatting,
  choice: "percent" | "decimal" | undefined,
): OpFormatting {
  if (choice !== "decimal") return opFmt;
  if (opFmt.formatting.style !== "percent") return opFmt;
  return {
    formatting: { style: "number", decimals: 4 },
    multiplier: 1,
  };
}

export function combineOpFormatting(
  aFmt: Formatting | undefined,
  bFmt: Formatting | undefined,
  op: CombineOp,
): OpFormatting {
  const a: Formatting = aFmt ?? { style: "number", decimals: 2 };
  const b: Formatting = bFmt ?? { style: "number", decimals: 2 };
  if (op === "divide") {
    // Same-style numerator + denominator → unitless ratio → display
    // as percent with a ×100 rescale. Covers the common "share of X"
    // case (currency/currency, count/count, even rate/rate). Side
    // effect: WTI/Brent gives "104%" rather than "1.04", which reads
    // a little weird for cross-commodity pairs but is technically the
    // same number. Acceptable; users can re-format per-chart later.
    if (a.style === b.style && (a.style === "currency" || a.style === "number" || a.style === "percent")) {
      return {
        formatting: { style: "percent", decimals: 2 },
        multiplier: 100,
      };
    }
    // Mixed-style divide: fall back to a generic 4-decimal number.
    // No good general formatter for "$/person" etc. without explicit
    // unit metadata; this at least keeps the value visible.
    return {
      formatting: { style: "number", decimals: 4 },
      multiplier: 1,
    };
  }
  // sum / diff: result is in A's unit if the units match, semantically
  // nonsense if they don't but at least the display is consistent.
  // Don't override formatting; don't rescale data.
  return { formatting: a, multiplier: 1 };
}

/**
 * Combine two time series into one via a per-timestamp arithmetic op.
 *
 * The cadences may differ (daily × monthly, weekly × annual, etc.). We
 * walk the union of timestamps in chronological order, forward-filling
 * each side from its most recent observation, and emit a derived point
 * once both sides have been seen at least once.
 *
 * For "divide", any point where the divisor is zero is skipped (rather
 * than emitting Infinity / NaN).
 */
export function combineTwo(
  a: TimeSeriesData,
  b: TimeSeriesData,
  op: CombineOp,
): TimeSeriesPoint[] {
  const aMap = new Map<string, number>();
  for (const p of a.points) aMap.set(p.t, p.v);
  const bMap = new Map<string, number>();
  for (const p of b.points) bMap.set(p.t, p.v);

  // Union of timestamps, sorted chronologically.
  const all = new Set<string>();
  for (const p of a.points) all.add(p.t);
  for (const p of b.points) all.add(p.t);
  const ordered = [...all].sort();

  const out: TimeSeriesPoint[] = [];
  let lastA: number | null = null;
  let lastB: number | null = null;
  for (const t of ordered) {
    if (aMap.has(t)) lastA = aMap.get(t)!;
    if (bMap.has(t)) lastB = bMap.get(t)!;
    if (lastA === null || lastB === null) continue;
    let v: number;
    if (op === "divide") {
      if (lastB === 0) continue;
      v = lastA / lastB;
    } else if (op === "sum") {
      v = lastA + lastB;
    } else {
      v = lastA - lastB;
    }
    out.push({ t, v });
  }
  return out;
}
