/**
 * Render-type helpers shared by the chart-embed + dashboard renderers.
 *
 * The dialog/tile hydration is split across three client islands:
 *   - ChartController  → LINE charts (the heavy island: imports Plot, PostHog
 *                        via track.ts, composer-state, supabase-session …).
 *   - ChartBar         → bar snapshots; self-wires its own tile + dialog.
 *   - ChartMap         → choropleths; self-wires its own tile + dialog.
 *
 * Because ChartBar and ChartMap self-wire, mounting ChartController alongside a
 * bar or map embed ships ~290KB of dead JS for zero output (the perf bug behind
 * the slow welcome-page "Real GDP by country" tile and every map embed). The
 * embed page gates ChartController on `embedNeedsController(render)`.
 */

/**
 * Render types whose tile + dialog wire themselves and therefore do NOT need
 * the line-chart ChartController island. Keep in sync with SectionChart's
 * dispatch (render === "map" → ChartMap, "bar" → ChartBar, else → Chart).
 */
export const SELF_WIRING_RENDERS: ReadonlySet<string> = new Set(["bar", "map"]);

/**
 * Whether an embed (or any host) of this render type needs the ChartController
 * island mounted. Line charts (render "line", or unset → treated as line) do;
 * the self-wiring render types (bar, map) do not.
 *
 * Deny-list by design: an unknown/future render type defaults to TRUE (gets the
 * controller) — the safe-but-wasteful direction. A new SELF-WIRING render type
 * must be added to SELF_WIRING_RENDERS so it skips the controller.
 */
export function embedNeedsController(render: string | null | undefined): boolean {
  return !SELF_WIRING_RENDERS.has(render ?? "line");
}
