/**
 * Deterministic palette for multi-series charts. Index-based; wraps for >10 series.
 *
 * Colors chosen to be readable on a light background and reasonably distinct under
 * common color-vision deficiencies. The first 6 are the original palette and are
 * preserved in order so existing curated charts don't change colors when a new
 * series is added — only charts with 7+ sources benefit from the extension.
 *
 * Stress-tested by building a custom 10-rate chart in the composer; before the
 * extension, 4 of 10 series collided with earlier colors (teal/teal, ochre/ochre,
 * violet/violet, blue/blue), making the legend and chart misleading.
 *
 * Beyond 10 series, the palette wraps. If you genuinely need more lines on one
 * axis, rebase or use the dual-axis mode — color encoding stops being a useful
 * channel past ~10 series regardless of palette.
 */
export const SERIES_COLORS: readonly string[] = [
  "#0F766E", // 1 — teal (matches site accent)
  "#B45309", // 2 — ochre
  "#7C3AED", // 3 — violet
  "#0284C7", // 4 — blue
  "#DB2777", // 5 — magenta
  "#65A30D", // 6 — olive
  "#B91C1C", // 7 — dark red (distinct from magenta + ochre)
  "#0E7490", // 8 — dark cyan (distinct from teal + blue)
  "#92400E", // 9 — chestnut brown (distinct from ochre)
  "#4338CA", // 10 — indigo (distinct from violet + blue)
];

export function seriesColor(i: number): string {
  return SERIES_COLORS[i % SERIES_COLORS.length];
}
