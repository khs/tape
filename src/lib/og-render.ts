/**
 * Pure helpers for building OG-image data — separated from the endpoint so the
 * SVG-path math and rebasing are unit-testable / reusable. Satori does not run
 * Observable Plot, so we hand-emit polyline paths from the raw point arrays.
 */
export type OgSeries = {
  name: string;
  color: string;
  points: { t: string; v: number }[];
};

// A muted palette that reads well at 1200×630 print size and on light & dark
// social-card backgrounds. First color is the brand teal; the rest are a
// distinguishable but harmonious follow-set.
export const OG_COLORS = [
  "#0d7a6a",
  "#dc6b2f",
  "#3b6cb3",
  "#9333ea",
  "#16a34a",
  "#dc2626",
  "#0891b2",
  "#db2777",
];

/**
 * Truncate a series to the trailing N days from its last point. When
 * window is undefined, returns the full series. We pick the OG window
 * separately from the chart's saved defaultDelta — the goal is "an evocative
 * thumbnail" not "the chart's literal current view", so 5y is a good
 * thumbnail default for most series.
 */
export function windowPoints(
  points: { t: string; v: number }[],
  trailingDays?: number,
): { t: string; v: number }[] {
  if (!trailingDays || points.length === 0) return points;
  const lastMs = new Date(points[points.length - 1].t).getTime();
  const cutoff = lastMs - trailingDays * 24 * 60 * 60 * 1000;
  return points.filter((p) => new Date(p.t).getTime() >= cutoff);
}

/** Rebase a points list to 100 at its first point (ignores zero/negative bases). */
export function rebaseTo100(
  points: { t: string; v: number }[],
): { t: string; v: number }[] {
  if (points.length === 0) return [];
  const base = points[0].v;
  if (!base || !Number.isFinite(base)) return points;
  return points.map((p) => ({ t: p.t, v: (p.v / base) * 100 }));
}

/**
 * Convert N parallel series into an SVG path-string per series, scaled into a
 * shared viewbox. Returns paths plus the axis ranges for callers that want to
 * draw a baseline. Skips series with <2 points.
 */
export function buildSvgPaths(
  seriesIn: OgSeries[],
  width: number,
  height: number,
  padTop = 4,
  padBottom = 4,
): {
  paths: { d: string; color: string; name: string }[];
  yMin: number;
  yMax: number;
} {
  const series = seriesIn.filter((s) => s.points.length >= 2);
  if (series.length === 0) return { paths: [], yMin: 0, yMax: 1 };
  const allXs = series.flatMap((s) => s.points.map((p) => new Date(p.t).getTime()));
  const allYs = series.flatMap((s) => s.points.map((p) => p.v));
  const xMin = Math.min(...allXs);
  const xMax = Math.max(...allXs);
  const yMin = Math.min(...allYs);
  const yMax = Math.max(...allYs);
  const xRange = xMax - xMin || 1;
  const yRange = yMax - yMin || 1;
  const inner = height - padTop - padBottom;
  const paths = series.map((s) => {
    let d = "";
    for (let i = 0; i < s.points.length; i++) {
      const p = s.points[i];
      const xMs = new Date(p.t).getTime();
      const x = ((xMs - xMin) / xRange) * width;
      const y = padTop + (1 - (p.v - yMin) / yRange) * inner;
      d += (i === 0 ? "M" : "L") + x.toFixed(1) + "," + y.toFixed(1);
    }
    return { d, color: s.color, name: s.name };
  });
  return { paths, yMin, yMax };
}
