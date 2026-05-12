import { getEntry } from "astro:content";
import type { CollectionEntry } from "astro:content";
import {
  DELTA_WINDOWS,
  closestSupported,
  type DeltaWindow,
} from "./deltas";
import type { InlineChart, InlineSource } from "./composer-state";
import { combineTwo, type CombineOp } from "./derive";
import type { TimeSeriesData } from "./data-types";
import { loadSourceData } from "./load-data";

export type ResolvedChart = {
  chart: CollectionEntry<"charts">;
  sources: CollectionEntry<"sources">[];
  // Side-channel: when a chart's source list includes a `derived:` ID,
  // the resolved data is pre-computed and stashed here keyed by source ID.
  // Chart.astro consults this map before falling back to loadSourceData.
  preloaded?: Record<string, TimeSeriesData>;
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
  inlineSources?: Record<string, InlineSource>;
  defaultDelta?: DeltaWindow;
};

export const INLINE_CHART_PREFIX = "inline:";
export const DERIVED_SOURCE_PREFIX = "derived:";

/**
 * Recursively resolve a source ID into (CollectionEntry, points). Real
 * source IDs go through getEntry + loadSourceData. Derived source IDs
 * (prefix `derived:`) look up a spec in `inlineSources`, recursively
 * resolve A and B, and combine via the chosen op. Cycles are detected
 * via a `visited` set.
 *
 * Returns null if any leaf is missing or a cycle is encountered.
 */
async function resolveSourceById(
  id: string,
  inlineSources: Record<string, InlineSource> | undefined,
  visited: Set<string>,
): Promise<{ entry: CollectionEntry<"sources">; points: TimeSeriesData } | null> {
  if (id.startsWith(DERIVED_SOURCE_PREFIX)) {
    if (visited.has(id)) return null; // cycle
    const spec = inlineSources?.[id];
    if (!spec) return null;
    visited.add(id);
    const a = await resolveSourceById(spec.a, inlineSources, visited);
    const b = await resolveSourceById(spec.b, inlineSources, visited);
    visited.delete(id);
    if (!a || !b) return null;
    const points = combineTwo(a.points, b.points, spec.op as CombineOp);
    if (points.length === 0) return null;
    // Pick formatting: divide → unitless 4-decimal; sum/diff → A's
    // formatting (units typically match).
    const baseFmt = a.entry.data.formatting;
    const fmt =
      spec.op === "divide"
        ? { ...baseFmt, style: "number" as const, decimals: 4 }
        : baseFmt;
    // Synthetic CollectionEntry shape carrying the derived metadata.
    // Source-level supportedDeltas: intersection of A and B (so the chart
    // window picker correctly limits the available windows).
    const aSupp = a.entry.data.supportedDeltas as DeltaWindow[];
    const bSupp = b.entry.data.supportedDeltas as DeltaWindow[];
    const supp = aSupp.filter((d) => bSupp.includes(d));
    const synthEntry = {
      id,
      collection: "sources" as const,
      data: {
        name: spec.name,
        shortName: spec.name,
        kind: "timeseries" as const,
        pipeline: "derived",
        dataFile: `__derived__/${id}.json`,
        supportedDeltas: supp.length > 0 ? supp : aSupp,
        unit: spec.op === "divide" ? "ratio" : a.entry.data.unit,
        formatting: fmt,
        emphasis: "change" as const,
        provenance: {
          provider: "Derived",
          notes: `${a.entry.data.shortName ?? a.entry.data.name} ${spec.op === "divide" ? "÷" : spec.op === "sum" ? "+" : "−"} ${b.entry.data.shortName ?? b.entry.data.name}`,
        },
      },
    } as unknown as CollectionEntry<"sources">;
    const ts: TimeSeriesData = {
      id,
      name: spec.name,
      kind: "timeseries",
      unit: synthEntry.data.unit,
      lastUpdated:
        a.points.lastUpdated > b.points.lastUpdated
          ? a.points.lastUpdated
          : b.points.lastUpdated,
      points,
    };
    return { entry: synthEntry, points: ts };
  }
  const entry = await getEntry("sources", id);
  if (!entry) return null;
  let points: TimeSeriesData;
  try {
    const raw = loadSourceData(entry.data.dataFile);
    if (raw.kind !== "timeseries") return null;
    points = raw;
  } catch {
    return null;
  }
  return { entry, points };
}

/**
 * Resolve a chart-by-ID. Follows `aliasOf` once if set (transparent rename support).
 * If `id` starts with `inline:`, looks up the ad-hoc chart in `inlineCharts`
 * and synthesizes a chart entry from that spec plus real source collection entries.
 * Returns null when the chart or any of its sources can't be found.
 */
export async function resolveChart(
  id: string,
  inlineCharts?: Record<string, InlineChart>,
  inlineSources?: Record<string, InlineSource>,
): Promise<ResolvedChart | null> {
  if (id.startsWith(INLINE_CHART_PREFIX)) {
    const spec = inlineCharts?.[id];
    if (!spec) return null;
    // Resolve every source — real or derived. For derived, we keep its
    // pre-computed TimeSeriesData on the side so Chart.astro can pick it
    // up without trying to read a non-existent JSON file.
    const resolvedSources = await Promise.all(
      spec.sources.map((sid) => resolveSourceById(sid, inlineSources, new Set())),
    );
    const valid = resolvedSources.filter(
      (r): r is { entry: CollectionEntry<"sources">; points: TimeSeriesData } =>
        r !== null,
    );
    if (valid.length === 0) return null;
    const validSources = valid.map((v) => v.entry);
    const preloaded: Record<string, TimeSeriesData> = {};
    for (const v of valid) {
      // Always preload — for real sources this is harmless duplication;
      // for derived sources it's required.
      preloaded[v.entry.id] = v.points;
    }
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
        // Log scale is meaningless when combined with dual-axis (one log axis
        // + one linear axis is misleading). Strip it here so a stale state
        // can't smuggle it past the composer's UI guard.
        scale: normalize === "dual-axis" ? undefined : spec.scale,
        rightAxisSources: spec.rightAxisSources,
        op: spec.op,
        blurb: spec.blurb,
        tags: [] as string[],
      },
    } as unknown as CollectionEntry<"charts">;
    return { chart: fakeChart, sources: validSources, preloaded };
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
      s.charts.map((cid) =>
        resolveChart(cid, dashboard.inlineCharts, dashboard.inlineSources),
      ),
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
