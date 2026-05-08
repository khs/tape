export const DELTA_WINDOWS = ["1w", "1m", "1y", "5y", "10y", "30y"] as const;
export type DeltaWindow = (typeof DELTA_WINDOWS)[number];

export const DELTA_LABELS: Record<DeltaWindow, string> = {
  "1w": "1 week",
  "1m": "1 month",
  "1y": "1 year",
  "5y": "5 years",
  "10y": "10 years",
  "30y": "30 years",
};

/**
 * "Over the {past week | past month | past five years | past ten years}" — used
 * in the descriptor sentence and tile caption. Numbers < 10 spelled out (AP style).
 */
export const DELTA_LABELS_PAST: Record<DeltaWindow, string> = {
  "1w": "past week",
  "1m": "past month",
  "1y": "past year",
  "5y": "past five years",
  "10y": "past ten years",
  "30y": "past 30 years",
};

export const DELTA_LABELS_SHORT: Record<DeltaWindow, string> = {
  "1w": "1W",
  "1m": "1M",
  "1y": "1Y",
  "5y": "5Y",
  "10y": "10Y",
  "30y": "30Y",
};

export const DELTA_DAYS: Record<DeltaWindow, number> = {
  "1w": 7,
  "1m": 30,
  "1y": 365,
  "5y": 365 * 5,
  "10y": 365 * 10,
  "30y": 365 * 30,
};

export function deltaPrior(now: Date, window: DeltaWindow): Date {
  const d = new Date(now);
  d.setUTCDate(d.getUTCDate() - DELTA_DAYS[window]);
  return d;
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
