/**
 * Y-axis transformations applied at render time to a time series.
 *
 * Users invoke these from a pill row in the chart dialog:
 *
 *   Level         — raw stored values (no transform). The default.
 *   YoY %         — at each date t, (v[t] - v[t-1y]) / v[t-1y] * 100.
 *                   Points without a 1-year prior are dropped.
 *   Index = 100   — divide every visible point by the first visible
 *                   point and multiply by 100. Shape-preserving rebase.
 *
 * Chart-spec field `transform` (chart YAML + inlineChart) carries
 * the default; pill clicks override per-session without touching
 * the saved chart.
 *
 * Returns a fresh point array so the caller can mutate / annotate
 * without affecting the input. Always preserves chronological order.
 */
import type { TimeSeriesPoint } from "./data-types";
import type { Formatting } from "./format";
import type { UnitClass } from "./derive";

export type TransformKey = "level" | "yoy_pct" | "index_100";

export const TRANSFORM_LABELS: Record<TransformKey, string> = {
  level: "Level",
  yoy_pct: "YoY %",
  index_100: "Index = 100",
};

/**
 * Which y-axis transforms make sense for a chart, given the unit classes
 * of the series it plots.
 *
 * "Level" is always available. "YoY %" and "Index = 100" are level-shape
 * transforms: they only make sense on level-like series (currency / count
 * / index). They're meaningless — and numerically explosive — on a *rate*
 * series (a percent/rate that crosses or sits near zero). A year-over-year
 * of a year-over-year divides by a near-zero denominator and blows up to
 * tens of thousands of percent (the CPI-YoY "74% / +25,000%" artifact at
 * the 2009 zero-crossings), and an index-rebase of a zero-crossing series
 * is equally meaningless. So we drop both whenever ANY plotted series is
 * unitClass "rate" — unemployment rate, fed funds, CPI YoY, any `%` source.
 *
 * Unknown / absent unitClass is treated as level-like (kept): most legacy
 * sources don't carry the field and shouldn't lose the pills. The
 * near-zero-denominator backstop in applyYoYPercent covers any zero-
 * crossing series (e.g. a derived ratio) that still reaches the transform.
 */
export function availableTransforms(
  unitClasses: ReadonlyArray<UnitClass | null | undefined>,
): TransformKey[] {
  const hasRate = unitClasses.some((u) => u === "rate");
  return hasRate ? ["level"] : ["level", "yoy_pct", "index_100"];
}

/**
 * Compute YoY % change at each date. For each point at time t, looks
 * up the latest observation at or before t - 365 days; if found and
 * non-zero, emits (v_t - v_prior) / v_prior * 100. Points without an
 * eligible prior are dropped from the output (typically the first
 * year of any series).
 *
 * Uses 365 days rather than calendar-year math because:
 *   - Many series are not calendar-aligned (daily yields, weekly
 *     unemployment claims).
 *   - 365 vs 366 in leap years is a sub-percent effect on most
 *     series; for series where it matters (quarterly GDP), the
 *     closest-prior lookup naturally lands on the same fiscal
 *     quarter a year before.
 */
export function applyYoYPercent(points: TimeSeriesPoint[]): TimeSeriesPoint[] {
  if (points.length === 0) return [];
  // Near-zero-denominator backstop. YoY % divides by the value one year
  // prior; when that prior sits at or near zero the ratio explodes (a
  // rate series crossing zero produced +25,000% spikes on CPI-YoY before
  // rate series were gated out of this transform — see availableTransforms).
  // We treat a prior as unusable when its magnitude is below 0.5% of the
  // series' typical magnitude (median |v|), and drop that point rather
  // than emit a meaningless tens-of-thousands-of-percent value. For a
  // normal level series (currency / count / index) every prior is far
  // from zero, so nothing is dropped and behavior is unchanged; this only
  // bites zero-crossing series (rates, some derived ratios).
  const finiteAbs = points
    .map((p) => Math.abs(p.v))
    .filter((v) => Number.isFinite(v) && v > 0)
    .sort((a, b) => a - b);
  const medianAbs =
    finiteAbs.length > 0 ? finiteAbs[Math.floor(finiteAbs.length / 2)] : 0;
  const nearZeroPrior = medianAbs > 0 ? medianAbs * 0.005 : 0;

  const out: TimeSeriesPoint[] = [];
  // Walk in sorted-time order; maintain a pointer into the prior-
  // year position for O(N) overall instead of O(N^2) re-search.
  let priorIdx = 0;
  for (let i = 0; i < points.length; i++) {
    const cur = points[i];
    const curMs = new Date(cur.t).getTime();
    const targetPriorMs = curMs - 365 * 86_400_000;
    // Advance priorIdx forward while points[priorIdx + 1] is still
    // at or before the target. Leaves priorIdx at the latest point
    // with t <= targetPriorMs.
    while (
      priorIdx + 1 < points.length &&
      new Date(points[priorIdx + 1].t).getTime() <= targetPriorMs
    ) {
      priorIdx += 1;
    }
    const prior = points[priorIdx];
    const priorMs = new Date(prior.t).getTime();
    // No eligible prior yet — entire series is younger than 1 year
    // at this index. Skip.
    if (priorMs > targetPriorMs) continue;
    if (prior.v === 0 || !Number.isFinite(prior.v)) continue;
    // Near-zero prior → ratio not meaningful; skip rather than explode.
    if (Math.abs(prior.v) < nearZeroPrior) continue;
    const yoy = ((cur.v - prior.v) / prior.v) * 100;
    if (!Number.isFinite(yoy)) continue;
    out.push({ t: cur.t, v: yoy });
  }
  return out;
}

/**
 * Rebase every point to 100 at the first point. Caller is responsible
 * for filtering `points` to the visible window first (so the rebase
 * baseline matches the chart's left edge, not the data file's first
 * observation).
 *
 * Points with a non-finite or zero baseline silently fall through as
 * the empty list — there's nothing to index against.
 */
export function applyIndex100(points: TimeSeriesPoint[]): TimeSeriesPoint[] {
  if (points.length === 0) return [];
  const baseline = points[0].v;
  if (!Number.isFinite(baseline) || baseline === 0) return [];
  return points.map((p) => ({ t: p.t, v: (p.v / baseline) * 100 }));
}

/**
 * Apply the given transform to a points array. Pure dispatch helper —
 * keeps the rest of the rendering code free of inline switch statements.
 */
export function applyTransform(
  points: TimeSeriesPoint[],
  transform: TransformKey,
): TimeSeriesPoint[] {
  switch (transform) {
    case "yoy_pct":
      return applyYoYPercent(points);
    case "index_100":
      return applyIndex100(points);
    case "level":
    default:
      return points;
  }
}

/**
 * Return the Formatting that should be used to display transformed
 * values. Level retains the source's native formatting. YoY % uses a
 * percent formatter regardless of input unit. Index = 100 uses a
 * dimensionless 1-decimal number formatter.
 *
 * Used for: y-axis tick labels, tooltip readouts, the headline value
 * in the chart dialog when the transform is active.
 */
export function transformFormatting(
  base: Formatting,
  transform: TransformKey,
): Formatting {
  switch (transform) {
    case "yoy_pct":
      return { style: "percent", decimals: 1 };
    case "index_100":
      return { style: "number", decimals: 1 };
    case "level":
    default:
      return base;
  }
}
