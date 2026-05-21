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

export type TransformKey = "level" | "yoy_pct" | "index_100";

export const TRANSFORM_LABELS: Record<TransformKey, string> = {
  level: "Level",
  yoy_pct: "YoY %",
  index_100: "Index = 100",
};

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
