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
 *   - "ytd" is a CALENDAR window (Jan 1 → today), so we don't thin it
 *     on point count: a sparse ytd early in the year ("YTD on Jan 5th")
 *     reads naturally and stays. The one exception (added May 2026) is
 *     a *zero-point* ytd — if a source has no observation in the current
 *     calendar year (its latest point predates Jan 1, e.g. a stale or
 *     annual series), ytd is genuinely empty, so we drop it and let the
 *     default window escalate to the next-larger one that has data.
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
    /** Latest observation. Used to detect an empty `ytd`: a latest
     *  point that predates Jan 1 of the current year means there is no
     *  current-calendar-year data, so the ytd window is blank. */
    latest?: { t: string } | null;
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
 * Whether a source's `ytd` window has any data — i.e. its latest
 * observation falls on or after Jan 1 of `now`'s calendar year. We key
 * off the latest date (present in both the tile summary and the full
 * points) rather than a point count: ytd has ≥1 point iff the most
 * recent observation is in the current year. When the latest date can't
 * be determined (neither summary nor points loaded), we stay permissive
 * and report `true` so a window we can't measure is never hidden.
 */
function ytdHasData(
  source: SourceForWindowCount,
  startOfYearMs: number,
): boolean {
  const pts = source.data?.points;
  const latestT =
    source.summary?.latest?.t ??
    (pts && pts.length > 0 ? pts[pts.length - 1].t : undefined);
  if (!latestT) return true;
  return new Date(latestT).getTime() >= startOfYearMs;
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
 *
 * `now` is injectable for deterministic tests; production calls let it
 * default to the current date.
 */
export function filterSupportedDeltas(
  effectiveSupported: ReadonlyArray<DeltaWindow>,
  perSource: ReadonlyArray<SourceForWindowCount>,
  minPoints: number = MIN_POINTS_FOR_WINDOW,
  now: Date = new Date(),
): DeltaWindow[] {
  const startOfYearMs = Date.UTC(now.getUTCFullYear(), 0, 1);
  return effectiveSupported.filter((w, i, arr) => {
    // Always keep the longest window — if everything else filters
    // out, the pill row still has at least one entry.
    if (i === arr.length - 1) return true;
    // YTD is a calendar window, so we don't thin it on point count — a
    // sparse ytd early in the year reads naturally. The exception is a
    // *zero-point* ytd (latest observation predates Jan 1): that window
    // is genuinely empty, so drop it and let the default escalate. Kept
    // only when EVERY source has current-year data (shared pill row).
    if (w === "ytd") {
      return perSource.every((ps) => ytdHasData(ps, startOfYearMs));
    }
    return perSource.every((ps) => pointsInDeltaWindow(ps, w) >= minPoints);
  });
}
