/**
 * Window-thinning helpers for the chart pill row.
 *
 * Author rule (May 2026): "stop giving one month as an option when
 * there are 1 or 2 datapoints in that time frame, particularly with
 * 1Y and YTD I don't see the need for it." A 1M pill on a monthly
 * series renders as a single dot or a 2-point line — adds nothing,
 * and breaks YoY% (which needs >2 points to compute from a sliced
 * window).
 *
 * The rule that's locked in:
 *   - Drop any window where ANY source has ≤2 points in it AND a
 *     longer window in supportedDeltas exists.
 *   - Always keep the longest available window so the pill row
 *     never empties out.
 *   - "ytd" is excluded from the filter — it's a CALENDAR window
 *     (Jan 1 → today), so its point count varies wildly through the
 *     year and dropping it mid-year would confuse the reader. The
 *     fact that YTD might also have only ≤2 points in January is
 *     fine; "YTD on Jan 5th" reads naturally.
 *
 * Pure + extracted from Chart.astro so the rules above can be tested
 * without rendering a chart. The renderer imports and uses both
 * functions in its `effectiveSupported` -> `filteredSupported` step.
 */
import { DELTA_DAYS, type DeltaWindow } from "./deltas";

/** Minimum points a window must have for its pill to stay on the row.
 *  3 is the threshold because YoY%-on-window needs a head + a tail +
 *  at least one observation in between to draw a meaningful curve. */
export const MIN_POINTS_FOR_WINDOW = 3;

/**
 * Minimal source shape this module needs. The renderer's `perSource`
 * objects have many more fields; we only look at the summary sparks
 * (preferred, cheaper) and the full data points (fallback).
 *
 * `null` is accepted on summary/data because the renderer's PerSource
 * type uses `T | null` (not `T | undefined`) to express "didn't load".
 * We tolerate either to stay invariant-friendly with both callers.
 */
export interface SourceForWindowCount {
  summary?: {
    sparks?: Partial<Record<string, ReadonlyArray<unknown> | undefined>>;
  } | null;
  data?: {
    points?: ReadonlyArray<{ t: string }>;
  } | null;
}

/**
 * Count the points a given source has in the trailing window. Used
 * by `filterSupportedDeltas` to decide which pills survive. Returns
 * `Infinity` to mean "don't filter" — for YTD (special-case) and for
 * sources whose data hasn't loaded yet (be permissive; the renderer
 * will fall back to whatever's available).
 *
 * Preference order:
 *   1. `summary.sparks[win]` length — already downsampled, cheapest
 *      to count, ships in the tile summary payload.
 *   2. `data.points` filtered by window-start — when the full data is
 *      loaded but the summary spark isn't.
 *   3. `Infinity` — no data of either shape; don't filter.
 */
export function pointsInDeltaWindow(
  source: SourceForWindowCount,
  win: DeltaWindow,
): number {
  // Trailing windows only — `ytd` keys aren't precomputed by the
  // summary sparks pipeline, and the filter caller skips ytd anyway.
  if (win === "ytd") return Infinity;
  const spark = source.summary?.sparks?.[win];
  if (spark) return spark.length;
  const pts = source.data?.points;
  if (pts && pts.length > 0) {
    const lastMs = new Date(pts[pts.length - 1].t).getTime();
    const startMs = lastMs - DELTA_DAYS[win] * 86_400_000;
    let count = 0;
    for (const p of pts) {
      if (new Date(p.t).getTime() >= startMs) count++;
    }
    return count;
  }
  return Infinity;
}

/**
 * Filter `effectiveSupported` down to the windows whose pills should
 * actually render. Rule summary at the top of the file. Returns a new
 * array; input is not mutated.
 *
 * Multi-source rule: a window is kept only if EVERY source has ≥
 * `minPoints` in it. The pill row is shared across all of the chart's
 * lines, so a window that's blank for one source would render an
 * obviously-broken view.
 */
export function filterSupportedDeltas(
  effectiveSupported: ReadonlyArray<DeltaWindow>,
  perSource: ReadonlyArray<SourceForWindowCount>,
  minPoints: number = MIN_POINTS_FOR_WINDOW,
): DeltaWindow[] {
  return effectiveSupported.filter((w, i, arr) => {
    // Always keep the longest window — if everything else filters
    // out, the pill row still has at least one entry.
    if (i === arr.length - 1) return true;
    // YTD is a calendar window; never filter it on point count.
    if (w === "ytd") return true;
    return perSource.every((ps) => pointsInDeltaWindow(ps, w) >= minPoints);
  });
}
