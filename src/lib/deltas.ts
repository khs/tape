// Window ordering matters for the pill row UI: it's the left-to-right order
// users see. YTD slots between 1m and 1y because its effective length is
// "January 1 to today" — somewhere between 1 day and 365 days, depending
// on what day of the year it is.
export const DELTA_WINDOWS = [
  "1w",
  "1m",
  "ytd",
  "1y",
  "5y",
  "10y",
  "30y",
  "50y",
  "max",
] as const;
export type DeltaWindow = (typeof DELTA_WINDOWS)[number];

export const DELTA_LABELS: Record<DeltaWindow, string> = {
  "1w": "1 week",
  "1m": "1 month",
  ytd: "year to date",
  "1y": "1 year",
  "5y": "5 years",
  "10y": "10 years",
  "30y": "30 years",
  "50y": "50 years",
  max: "all time",
};

/**
 * "Over the {past week | past month | past five years | past ten years}" — used
 * in the descriptor sentence and tile caption. Numbers < 10 spelled out (AP style).
 */
export const DELTA_LABELS_PAST: Record<DeltaWindow, string> = {
  "1w": "past week",
  "1m": "past month",
  ytd: "year to date",
  "1y": "past year",
  "5y": "past five years",
  "10y": "past ten years",
  "30y": "past 30 years",
  "50y": "past 50 years",
  max: "full history",
};

export const DELTA_LABELS_SHORT: Record<DeltaWindow, string> = {
  "1w": "1W",
  "1m": "1M",
  ytd: "YTD",
  "1y": "1Y",
  "5y": "5Y",
  "10y": "10Y",
  "30y": "30Y",
  "50y": "50Y",
  max: "MAX",
};

/**
 * Nominal duration in days. Used as a stable proxy for the `closestSupported`
 * ranking and for trailing-window math on fixed-length windows. YTD's true
 * duration varies day-by-day (Jan 2 = 1 day; Dec 31 ≈ 365); its nominal
 * value here is the mid-year average, which is close enough for ranking
 * but should not be used to compute a real window start — call `deltaPrior`
 * or `windowStartMs` for that, which special-cases YTD.
 */
export const DELTA_DAYS: Record<DeltaWindow, number> = {
  "1w": 7,
  "1m": 30,
  ytd: 183,
  "1y": 365,
  "5y": 365 * 5,
  "10y": 365 * 10,
  "30y": 365 * 30,
  "50y": 365 * 50,
  // "all time" sentinel: finite + large (200y), kept > 50y for the ascending-
  // order invariant and away from Infinity so closestSupported's Math.log and
  // trim math stay valid. The actual "all points" behavior comes from the
  // windowStartMs floor below, not this number.
  max: 365 * 200,
};

/**
 * The actual day count between the start of the given window and `now`. For
 * fixed-length windows this is just `DELTA_DAYS[window]`. For YTD it's the
 * days elapsed since January 1 of the reference date's year.
 */
export function windowDays(window: DeltaWindow, now: Date = new Date()): number {
  if (window === "ytd") {
    const startMs = Date.UTC(now.getUTCFullYear(), 0, 1);
    return Math.max(1, Math.floor((now.getTime() - startMs) / 86400000));
  }
  return DELTA_DAYS[window];
}

/**
 * Start-of-window timestamp in milliseconds, anchored at `refMs`. For
 * trailing windows this is `refMs - days*86400000`; for YTD it's the UTC
 * January 1 of the reference date's year regardless of refMs's exact value.
 */
export function windowStartMs(refMs: number, window: DeltaWindow): number {
  // "all time": floor at the minimum valid JS Date (−8.64e15 ms) so every
  // point passes the `t >= start` filter, regardless of how old the series is.
  // new Date(-8.64e15) is valid (not NaN), so all downstream `new Date()` uses
  // stay safe. The dialog x-domain is hand-fitted to the first real point
  // separately (see ChartController dialogPlotPoints) so the axis isn't padded
  // back to year −271821.
  if (window === "max") return -8.64e15;
  if (window === "ytd") {
    return Date.UTC(new Date(refMs).getUTCFullYear(), 0, 1);
  }
  return refMs - DELTA_DAYS[window] * 86400000;
}

export function deltaPrior(now: Date, window: DeltaWindow): Date {
  return new Date(windowStartMs(now.getTime(), window));
}

/**
 * Return the window in `supported` that's closest (on a log-day scale) to
 * `want`. Used when a dashboard asks for a window that a specific chart's
 * source doesn't support — we fall back to the nearest available bucket.
 */
export function closestSupported(
  want: DeltaWindow,
  supported: readonly DeltaWindow[],
): DeltaWindow {
  if (supported.length === 0) return want;
  // "max" (all time) is universal — every source can show all of its own
  // points — so it's always "supported" even though no source declares it.
  // Without this, dual-axis (which maps the window per-source via
  // closestSupported against declared deltas) would collapse max to 50y.
  if (want === "max") return "max";
  if (supported.includes(want)) return want;
  const wantLog = Math.log(DELTA_DAYS[want]);
  let best = supported[0];
  let bestDist = Math.abs(Math.log(DELTA_DAYS[best]) - wantLog);
  for (const s of supported) {
    const d = Math.abs(Math.log(DELTA_DAYS[s]) - wantLog);
    if (d < bestDist) {
      best = s;
      bestDist = d;
    }
  }
  return best;
}
