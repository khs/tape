import { getEntry } from "astro:content";
import type { CollectionEntry } from "astro:content";
import {
  DELTA_WINDOWS,
  closestSupported,
  type DeltaWindow,
} from "./deltas";
import type { InlineChart } from "./composer-state";

export type ResolvedChart = {
  chart: CollectionEntry<"charts">;
  sources: CollectionEntry<"sources">[];
};

export type ResolvedSection = {
  title: string | null;
  description?: string;
  charts: ResolvedChart[];
};

export type DashboardShape = {
  sections?: { title: string; description?: string; charts: string[] }[];
  charts?: string[];
  chartOverrides?: Record<
    string,
    Partial<CollectionEntry<"charts">["data"]>
  >;
  inlineCharts?: Record<string, InlineChart>;
  defaultDelta?: DeltaWindow;
};

export const INLINE_CHART_PREFIX = "inline:";

/**
 * Resolve a chart-by-ID. Follows `aliasOf` once if set (transparent rename support).
 * If `id` starts with `inline:`, looks up the ad-hoc chart in `inlineCharts`
 * and synthesizes a chart entry from that spec plus real source collection entries.
 * Returns null when the chart or any of its sources can't be found.
 */
export async function resolveChart(
  id: string,
  inlineCharts?: Record<string, InlineChart>,
): Promise<ResolvedChart | null> {
  if (id.startsWith(INLINE_CHART_PREFIX)) {
    const spec = inlineCharts?.[id];
    if (!spec) return null;
    const sources = await Promise.all(
      spec.sources.map((sid) => getEntry("sources", sid)),
    );
    const validSources = sources.filter(
      (s): s is CollectionEntry<"sources"> => s !== undefined,
    );
    if (validSources.length === 0) return null;
    // Synthesize a minimal chart entry. Only `id` and `data` are read downstream
    // (see Chart.astro + effectiveChart). Default render to "line" and pick a
    // normalize default. Heuristic: when all sources share the same formatting
    // style + unit (e.g. multiple inflation %s, multiple USD prices) leave
    // them on raw scale; otherwise rebase for legibility. For exactly two
    // mismatched-scale sources the user can still pick dual-axis explicitly.
    const sameScale =
      validSources.length > 1 &&
      validSources.every(
        (s) =>
          s.data.formatting?.style === validSources[0].data.formatting?.style &&
          s.data.unit === validSources[0].data.unit,
      );
    const defaultNormalize: "rebase" | "raw" =
      validSources.length > 1 && !sameScale ? "rebase" : "raw";
    const normalize = spec.normalize ?? defaultNormalize;
    const fakeChart = {
      id,
      data: {
        title: spec.title,
        sources: spec.sources,
        render: spec.render ?? ("line" as const),
        defaultDelta: spec.defaultDelta ?? ("1m" as const),
        normalize,
        blurb: spec.blurb,
        tags: [] as string[],
      },
    } as unknown as CollectionEntry<"charts">;
    return { chart: fakeChart, sources: validSources };
  }
  let chart = await getEntry("charts", id);
  if (!chart) return null;
  // One-hop alias follow. `deprecated` without `aliasOf` still renders (the
  // caller can decide to show a deprecation notice) — we only redirect when an
  // alias is explicitly set.
  if (chart.data.aliasOf) {
    const target = await getEntry("charts", chart.data.aliasOf);
    if (target) chart = target;
  }
  const sources = await Promise.all(
    chart.data.sources.map((sid) => getEntry("sources", sid)),
  );
  const validSources = sources.filter(
    (s): s is CollectionEntry<"sources"> => s !== undefined,
  );
  if (validSources.length === 0) return null;
  return { chart, sources: validSources };
}

/**
 * Normalize a dashboard's sections/charts into a uniform list of sections.
 * Flat `charts` becomes a single unnamed section.
 */
export async function resolveSections(
  dashboard: DashboardShape,
): Promise<ResolvedSection[]> {
  const sectionsRaw = dashboard.sections ?? [
    { title: null as unknown as string, charts: dashboard.charts ?? [] },
  ];
  const out: ResolvedSection[] = [];
  for (const s of sectionsRaw) {
    const resolved = await Promise.all(
      s.charts.map((cid) => resolveChart(cid, dashboard.inlineCharts)),
    );
    const valid = resolved.filter((r): r is ResolvedChart => r !== null);
    if (valid.length > 0) {
      out.push({
        title: s.title ?? null,
        description: s.description,
        charts: valid,
      });
    }
  }
  return out;
}

/**
 * Per-chart effective supported windows (intersection across that chart's sources).
 */
export function perChartSupportedDeltas(
  sections: ResolvedSection[],
): DeltaWindow[][] {
  return sections.flatMap((sec) =>
    sec.charts.map((c) =>
      DELTA_WINDOWS.filter((w) =>
        c.sources.every((s) => s.data.supportedDeltas.includes(w)),
      ),
    ),
  );
}

/**
 * Dashboard-level pill set: union across charts. A window is shown if at least
 * one chart on the dashboard supports it directly (no closestSupported fallback).
 */
export function dashboardSupportedDeltas(
  sections: ResolvedSection[],
): DeltaWindow[] {
  const perChart = perChartSupportedDeltas(sections);
  const supported = DELTA_WINDOWS.filter((w) =>
    perChart.some((sup) => sup.includes(w)),
  );
  return supported.length > 0 ? supported : [...DELTA_WINDOWS];
}

/**
 * Resolve the dashboard's active default delta: preserve the user's requested
 * default if supported, else fall back to the closest-supported window.
 */
export function resolveDashboardDefault(
  requested: DeltaWindow | undefined,
  supported: DeltaWindow[],
): DeltaWindow {
  const want: DeltaWindow = requested ?? "1m";
  if (supported.includes(want)) return want;
  return closestSupported(want, supported);
}

/**
 * Merge a chart's base data with any per-dashboard override from a composed
 * or preset dashboard. Returns the effective ChartData fed into <Chart>.
 */
export function effectiveChart(
  resolved: ResolvedChart,
  override?: Partial<CollectionEntry<"charts">["data"]>,
): CollectionEntry<"charts">["data"] {
  return { ...resolved.chart.data, ...(override ?? {}) };
}
