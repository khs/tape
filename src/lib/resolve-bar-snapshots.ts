/**
 * Bar-snapshot resolution: builds the per-chart, per-source snapshot
 * data that `ChartBar.astro` needs.
 *
 * Used by page renderers ([...slug].astro, custom.astro, u/[slug].astro,
 * embed/chart/[...id].astro) which iterate over resolved sections,
 * filter the bar charts, and need a Map<chartId, BarSnapshot[]> in
 * sync so the JSX can pluck the right snapshot for each chart
 * without inline `await`. Keeping the load-fan-out here means the
 * filesystem fetch dedupes naturally when two bar charts on the same
 * dashboard reference the same source.
 *
 * Snapshot semantics: each entry = the latest observation at or
 * before the chart's `barAsOf` date (or the source's own latest when
 * `barAsOf` is undefined). Sources that fail to load OR whose
 * earliest observation post-dates the anchor drop out silently —
 * better a 9-bar chart than a render error.
 */
import { loadSourceData, snapshotAt } from "./load-data";

export interface BarSnapshotEntry {
  sourceId: string;
  value: number;
  date: string;
}

/**
 * Resolve snapshots for one chart. Returns an array parallel-ish to
 * the chart's sources list, minus any that failed to load.
 */
export async function resolveBarSnapshot(
  sources: Array<{ id: string; data: { dataFile: string } }>,
  barAsOf?: string,
): Promise<BarSnapshotEntry[]> {
  const out = await Promise.all(
    sources.map(async (s) => {
      try {
        const data = await loadSourceData(s.data.dataFile);
        // Bar charts only make sense for timeseries sources. Curve
        // data (forward futures curves, yield curves) is a snapshot
        // shape that doesn't have a "latest value" in the same way;
        // skip cleanly so the bar chart renders without that bar
        // rather than crashing the page.
        if (data.kind !== "timeseries") return null;
        const pt = snapshotAt(data, barAsOf);
        return pt
          ? ({ sourceId: s.id, value: pt.v, date: pt.t } as BarSnapshotEntry)
          : null;
      } catch {
        return null;
      }
    }),
  );
  return out.filter((x): x is BarSnapshotEntry => x !== null);
}

/**
 * Resolve snapshots for many charts in parallel. Returns a Map
 * keyed by chart ID. Inputs that don't have render === "bar" are
 * silently skipped — callers can pass their full resolved-chart
 * list without filtering first.
 */
export async function resolveBarSnapshots(
  resolvedCharts: Array<{
    chart: { id: string; data: { render?: string; barAsOf?: string } };
    sources: Array<{ id: string; data: { dataFile: string } }>;
  }>,
): Promise<Map<string, BarSnapshotEntry[]>> {
  const barCharts = resolvedCharts.filter(
    (c) => c.chart.data.render === "bar",
  );
  const pairs = await Promise.all(
    barCharts.map(async (c) => {
      const snap = await resolveBarSnapshot(c.sources, c.chart.data.barAsOf);
      return [c.chart.id, snap] as const;
    }),
  );
  return new Map(pairs);
}
