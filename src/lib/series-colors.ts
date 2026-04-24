/**
 * Deterministic palette for multi-series charts. Index-based; wraps for >6 series.
 * Colors chosen to be readable on a light background and reasonably distinct under
 * common color-vision deficiencies.
 */
export const SERIES_COLORS: readonly string[] = [
  "#0F766E", // teal (matches site accent)
  "#B45309", // ochre
  "#7C3AED", // violet
  "#0284C7", // blue
  "#DB2777", // magenta
  "#65A30D", // olive
];

export function seriesColor(i: number): string {
  return SERIES_COLORS[i % SERIES_COLORS.length];
}
