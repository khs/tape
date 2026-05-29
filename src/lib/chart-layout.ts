/**
 * Shared layout constants for the interactive dialog plot (ChartController).
 *
 * Exported so the y-tick-label clipping guard in format.test.ts can measure
 * against the REAL values instead of hardcoding them: if either of these
 * drifts, the test's budget assertions re-evaluate (and an explicit canary
 * fails on purpose), so a margin shrink or font bump that could re-clip a
 * tick label — the bug that turned "3.4 workers" into "4 workers" — gets
 * noticed at test time. See axisTickFormatting in lib/format.ts for the why.
 */

/**
 * Left margin (px) the dialog plot reserves for y-axis tick labels — and the
 * right margin too when a second (dual) axis is shown. A tick label wider
 * than this is clipped by the SVG viewport. wireHoverCard must be passed the
 * same value so the hover math lines up with the plotted frame.
 */
export const AXIS_LABEL_MARGIN_PX = 64;

/** Font size (px) of the dialog plot's axis tick labels. */
export const AXIS_LABEL_FONT_PX = 12;
