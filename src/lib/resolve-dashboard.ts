import { getEntry } from "astro:content";
import type { CollectionEntry } from "astro:content";
import {
  DELTA_WINDOWS,
  closestSupported,
  type DeltaWindow,
} from "./deltas";

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
  defaultDelta?: DeltaWindow;
};

/**
 * Resolve a chart-by-ID. Follows `aliasOf` once if set (transparent rename support).
 * Returns null when the chart or any of its sources can't be found.
 */
export async function resolveChart(id: string): Promise<ResolvedChart | null> {
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
    const resolved = await Promise.all(s.charts.map(resolveChart));
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
