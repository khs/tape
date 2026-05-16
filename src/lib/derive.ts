import type { TimeSeriesData, TimeSeriesPoint } from "./data-types";
import type { Formatting } from "./format";

export type CombineOp = "divide" | "sum" | "diff";

/**
 * Coarse semantic classification of a source's values. Distinct from
 * Formatting.style because two sources can share a style ("number")
 * but mean different things (US GDP in billions vs Case-Shiller HPI
 * as an index).
 *
 *   currency — denominated in $/€/etc.
 *   count    — discrete (people, jobs, claims, homes sold, …)
 *   rate     — percentage or basis-point rate
 *   index    — unitless level (CPI, Nasdaq composite, …)
 *   ratio    — unitless ratio (default for derived sources)
 *
 * Populated on every source by pipelines/backfill_unit_class.py;
 * inferUnitClassFromFormatting below is the fallback when callers
 * don't have a unitClass to pass through.
 */
export type UnitClass = "currency" | "count" | "rate" | "index" | "ratio";

export function inferUnitClassFromFormatting(
  fmt: Formatting | undefined,
): UnitClass {
  if (!fmt) return "ratio";
  if (fmt.style === "currency") return "currency";
  if (fmt.style === "percent" || fmt.style === "bps") return "rate";
  if (fmt.style === "index") return "index";
  // style "number" — too vague to nail down without an explicit
  // unitClass field. Treat as ratio so the same-class divide rule
  // doesn't accidentally trigger between, say, a currency and an
  // index (both stored as style: number).
  return "ratio";
}

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
 * Three modes:
 *   percent (default) — "104%". Multiplier ×100, percent style.
 *   decimal           — "1.04". Multiplier ×1, 4-decimal number.
 *   ratio             — "1.04:1". Multiplier ×1, 2-decimal with
 *                       ":1" suffix; reads as "1.04 to 1." Useful
 *                       when the proportion is the natural framing
 *                       (e.g. debt-to-equity, P/E).
 */
export type PercentDisplay = "percent" | "decimal" | "ratio";

export function applyPercentDisplayOverride(
  opFmt: OpFormatting,
  choice: PercentDisplay | undefined,
): OpFormatting {
  if (!choice || choice === "percent") return opFmt;
  if (opFmt.formatting.style !== "percent") return opFmt;
  if (choice === "decimal") {
    return {
      formatting: { style: "number", decimals: 4 },
      multiplier: 1,
    };
  }
  // ratio
  return {
    formatting: { style: "number", decimals: 2, suffix: ":1" },
    multiplier: 1,
  };
}

export function combineOpFormatting(
  aFmt: Formatting | undefined,
  bFmt: Formatting | undefined,
  op: CombineOp,
  aUnitClass?: UnitClass,
  bUnitClass?: UnitClass,
): OpFormatting {
  const a: Formatting = aFmt ?? { style: "number", decimals: 2 };
  const aClass: UnitClass = aUnitClass ?? inferUnitClassFromFormatting(aFmt);
  const bClass: UnitClass = bUnitClass ?? inferUnitClassFromFormatting(bFmt);

  if (op === "divide") {
    // Rule 1 — Same unitClass numerator + denominator → unitless
    // ratio → display as percent with ×100 rescale. Covers the
    // common "share of X" case across every class (currency/currency,
    // count/count, rate/rate, index/index, ratio/ratio). Side effect:
    // WTI/Brent gives "104%" rather than "1.04"; chart-level
    // percentDisplay:"decimal" flips that back.
    if (aClass === bClass) {
      return {
        formatting: { style: "percent", decimals: 2 },
        multiplier: 100,
      };
    }

    // Rule 2 — currency / count → "$ per unit" display. Counts on
    // the books are raw (post pipelines/rescale_counts_to_raw.py);
    // currency on the books is billions (post
    // pipelines/rescale_currency_to_billions.py). So the raw divide
    // is "billions of $ per unit"; multiplying by 1e9 yields raw $
    // per unit, which is what people read off the screen
    // ("$1,463 per person"). Compact notation handles K/M magnitudes
    // for densely-populated denominators without per-source decimals
    // tweaking.
    if (aClass === "currency" && bClass === "count") {
      return {
        formatting: {
          style: "number",
          decimals: 1,
          prefix: "$",
          notation: "compact",
        },
        multiplier: 1e9,
      };
    }

    // Rule 3 — currency / index → deflated currency. Indices in this
    // codebase are conventionally base 100 (CPI, Case-Shiller, etc.);
    // dividing nominal currency by such an index and multiplying by
    // 100 gives the "real" magnitude in the same base-year units.
    // Reuse A's formatter so the deflated value reads in the same
    // band as the nominal input ("$24,000 B" nominal → "$7,550 B"
    // deflated by CPI ≈ 320). Caveat: indices that are NOT base-100
    // (e.g. an absolute-level composite) produce a meaningless
    // multiplier; user can override via the chart's percentDisplay
    // logic doesn't apply here, but they can re-do the math with a
    // different op or live with the caveat.
    if (aClass === "currency" && bClass === "index") {
      return {
        formatting: a,
        multiplier: 100,
      };
    }

    // Rule 4 — Everything else mixed: fall back to a 4-decimal
    // number. No good general formatter for currency/rate,
    // count/currency, count/index, etc. without per-pair semantics
    // — at least the value is numerically visible.
    return {
      formatting: { style: "number", decimals: 4 },
      multiplier: 1,
    };
  }

  // sum / diff: result inherits A's formatting (units typically match
  // for a sensible sum/diff anyway; mixed-class is the user's problem
  // to interpret). No multiplier rescale.
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
