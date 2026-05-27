/**
 * Infer a source's observation cadence from its summary sparks.
 *
 * Used on /alerts/ when the user picks the "absolute change >"
 * condition — that condition compares each new observation to the
 * PRIOR observation, so the user needs to know whether prior means
 * "yesterday" (daily series), "last week" (weekly), or "the previous
 * release ~30 days ago" (monthly) before they pick a meaningful
 * threshold.
 *
 * Inference strategy: pull the largest spark window whose point
 * count is below the downsample cap (sparks cap at 30 points; a
 * 30-count window is downsampled and would give a misleading median
 * spacing). Compute the median day gap between consecutive points,
 * then bucket into a friendly cadence label.
 *
 * Why median over mean: missing observations (holiday gaps in a
 * daily series, skipped quarterly releases) introduce outliers that
 * a mean would smear. Median absorbs the gap cleanly.
 *
 * Returns null when no spark has enough raw points — the caller
 * should hide the hint rather than show "unknown".
 */

/** Approximate spark-downsampling cap shipped by build_summaries.py.
 *  A window whose point count exactly equals or exceeds this is
 *  treated as downsampled; we skip those because the median spacing
 *  won't reflect the source's true cadence. */
const SPARK_DOWNSAMPLE_CAP = 30;

/** Minimum point count to compute a meaningful median. 2 points
 *  give exactly one gap; 3+ start to average out noise. */
const MIN_RAW_POINTS = 3;

/** Window keys in priority order — largest first. A longer window
 *  with raw resolution gives a better median estimate than a short
 *  one. Mirrors the build_summaries.py emit order. */
const WINDOW_PRIORITY: ReadonlyArray<string> = [
  "50y",
  "30y",
  "10y",
  "5y",
  "1y",
  "ytd",
  "1m",
  "1w",
];

export interface SparkPoint {
  t: string; // ISO date
  v: number;
}

/**
 * Bucket a median day-gap into a friendly cadence label. Boundaries
 * are deliberately generous: weekends + missing readings should not
 * push a daily series into "weekly", and a missed monthly release
 * should not push monthly into "quarterly".
 */
export function frequencyBucket(days: number): string {
  if (!Number.isFinite(days) || days <= 0) return "unknown";
  if (days <= 2) return "daily";
  if (days <= 9) return "weekly";
  if (days <= 80) return "monthly";
  if (days <= 180) return "quarterly";
  if (days <= 400) return "annual";
  return "multi-year";
}

/**
 * Pick the best spark window for frequency inference + return its
 * points. Returns null when no window has enough raw resolution.
 */
export function selectFrequencySpark(
  sparks: Record<string, SparkPoint[]> | undefined,
): SparkPoint[] | null {
  if (!sparks) return null;
  for (const w of WINDOW_PRIORITY) {
    const arr = sparks[w];
    if (!arr || arr.length < MIN_RAW_POINTS) continue;
    if (arr.length >= SPARK_DOWNSAMPLE_CAP) continue;
    return arr;
  }
  return null;
}

/**
 * Median day-spacing between consecutive points. Sorted internally
 * so outliers (gaps from holidays, missed releases) don't skew.
 */
export function medianSpacingDays(points: ReadonlyArray<SparkPoint>): number | null {
  if (points.length < 2) return null;
  const diffs: number[] = [];
  for (let i = 1; i < points.length; i++) {
    const d0 = new Date(points[i - 1].t).getTime();
    const d1 = new Date(points[i].t).getTime();
    if (!Number.isFinite(d0) || !Number.isFinite(d1)) continue;
    const days = (d1 - d0) / (1000 * 60 * 60 * 24);
    if (days > 0) diffs.push(days);
  }
  if (diffs.length === 0) return null;
  diffs.sort((a, b) => a - b);
  return diffs[Math.floor(diffs.length / 2)];
}

/**
 * Full pipeline: sparks → bucket label + median day count.
 * Returns null when inference isn't possible — caller hides the hint.
 *
 * The `days` field is rounded to the nearest day for display; the
 * unrounded median lives in `daysExact` for callers that want to
 * apply different rounding.
 */
export interface FrequencyInference {
  /** Friendly bucket: "daily" | "weekly" | "monthly" | "quarterly"
   *  | "annual" | "multi-year". */
  bucket: string;
  /** Median day spacing, rounded to the nearest integer day. */
  days: number;
  /** Median day spacing as the raw float. */
  daysExact: number;
}

export function inferFrequency(
  sparks: Record<string, SparkPoint[]> | undefined,
): FrequencyInference | null {
  const spark = selectFrequencySpark(sparks);
  if (!spark) return null;
  const days = medianSpacingDays(spark);
  if (days === null) return null;
  return {
    bucket: frequencyBucket(days),
    days: Math.round(days),
    daysExact: days,
  };
}
