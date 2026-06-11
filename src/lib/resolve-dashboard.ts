import { getEntry } from "astro:content";
import type { CollectionEntry } from "astro:content";
import {
  DELTA_WINDOWS,
  closestSupported,
  type DeltaWindow,
} from "./deltas";
import type { InlineChart, InlineMap, InlineSource } from "./composer-state";
import {
  combineTwo,
  combineOpFormatting,
  multiplyRebuildNumerator,
  type CombineOp,
  type DerivedFromMeta,
} from "./derive";
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
  // Section-as-markdown body — safe-subset markdown rendered between
  // the description and the chart grid. When charts.length === 0 the
  // section is markdown-only (no chart grid below). See
  // src/lib/markdown.ts for the supported syntax.
  markdown?: string;
  // Section-level time-window overrides. When set, override the
  // dashboard-level pill for charts inside. See sectionSchema in
  // src/content/config.ts + src/lib/composer-state.ts for the source
  // shapes. fixedRange wins over defaultDelta if both present.
  defaultDelta?: DeltaWindow;
  fixedRange?: { start: string; end: string };
};

export type DashboardShape = {
  sections?: {
    title: string;
    description?: string;
    charts: string[];
    markdown?: string;
    defaultDelta?: DeltaWindow;
    fixedRange?: { start: string; end: string };
  }[];
  charts?: string[];
  chartOverrides?: Record<
    string,
    Partial<CollectionEntry<"charts">["data"]>
  >;
  inlineCharts?: Record<string, InlineChart>;
  inlineSources?: Record<string, InlineSource>;
  inlineMaps?: Record<string, InlineMap>;
  defaultDelta?: DeltaWindow;
};

export const INLINE_CHART_PREFIX = "inline:";
export const INLINE_MAP_PREFIX = "inlinemap:";
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
    // Exact-rebuild substitution: when this is rate × its-own-denominator,
    // the product is just the numerator count — show that source directly
    // rather than recomputing it from the display-rounded rate (see
    // multiplyRebuildNumerator). Carries the numerator's own formatting +
    // provenance, but keeps the derived source's chosen name. Falls through
    // to the computed product if the numerator can't be resolved.
    const subId = multiplyRebuildNumerator(
      spec.a,
      (a.entry.data as { derivedFrom?: DerivedFromMeta }).derivedFrom,
      spec.b,
      (b.entry.data as { derivedFrom?: DerivedFromMeta }).derivedFrom,
      spec.op as CombineOp,
    );
    if (subId && subId !== id) {
      const sub = await resolveSourceById(subId, inlineSources, visited);
      if (sub) {
        const subEntry = {
          ...sub.entry,
          id,
          data: { ...sub.entry.data, name: spec.name, shortName: spec.name },
        } as unknown as CollectionEntry<"sources">;
        return {
          entry: subEntry,
          points: { ...sub.points, id, name: spec.name },
        };
      }
    }
    // Pick output formatting + an optional ×N rescale so e.g.
    // currency/currency divides render as "1.10%" instead of "0.011",
    // and currency/count divides render as "$X /person" instead of a
    // tiny 4-decimal number. See combineOpFormatting in lib/derive.ts.
    const opFmt = combineOpFormatting(
      a.entry.data.formatting,
      b.entry.data.formatting,
      spec.op as CombineOp,
      (a.entry.data as { unitClass?: import("./derive").UnitClass }).unitClass,
      (b.entry.data as { unitClass?: import("./derive").UnitClass }).unitClass,
    );
    const rawPoints = combineTwo(a.points, b.points, spec.op as CombineOp);
    if (rawPoints.length === 0) return null;
    const points = opFmt.multiplier === 1
      ? rawPoints
      : rawPoints.map((p) => ({ t: p.t, v: p.v * opFmt.multiplier }));
    const fmt = opFmt.formatting;
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
        // Unit derived from the chosen op-formatting. Percent style (the
        // common currency/currency-divide case) advertises "%"; the
        // mixed-style fallback keeps the older generic "ratio" label.
        unit:
          spec.op === "divide"
            ? fmt.style === "percent"
              ? "%"
              : "ratio"
            : a.entry.data.unit,
        formatting: fmt,
        emphasis: "change" as const,
        provenance: {
          provider: "Derived",
          notes: `${a.entry.data.shortName ?? a.entry.data.name} ${spec.op === "divide" ? "÷" : spec.op === "sum" ? "+" : spec.op === "multiply" ? "×" : "−"} ${b.entry.data.shortName ?? b.entry.data.name}`,
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
    const raw = await loadSourceData(entry.data.dataFile);
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
  inlineMaps?: Record<string, InlineMap>,
): Promise<ResolvedChart | null> {
  if (id.startsWith(INLINE_MAP_PREFIX)) {
    const spec = inlineMaps?.[id];
    if (!spec) return null;
    // Synthesize a CollectionEntry-shaped chart object so the
    // downstream render dispatch (Chart.astro for line, ChartMap
    // for "map") can treat inline maps identically to library
    // map charts. Only `data.render` + the geo/indicator/vintage
    // fields are read by ChartMap.
    const fakeChart = {
      id,
      data: {
        title: spec.title,
        render: "map" as const,
        geo: spec.geo,
        indicator: spec.indicator,
        vintage: spec.vintage,
        state: spec.state,
        states: spec.states,
        bbox: spec.bbox,
        boundaryFile: spec.boundaryFile,
        colorScheme: spec.colorScheme,
        colorScale: spec.colorScale,
        blurb: spec.blurb,
        defaultDelta: "1m" as const,
        tags: [] as string[],
      },
    } as unknown as CollectionEntry<"charts">;
    return { chart: fakeChart, sources: [] };
  }
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
    // Exact-rebuild substitution (see multiplyRebuildNumerator): a 2-source
    // `rate × its-own-denominator` multiply renders the exact numerator
    // count source instead of the rounding-drifted product. Collapses to a
    // single source with no op, so Chart.astro plots it directly.
    let renderValid = valid;
    let effSources: string[] = spec.sources;
    let effOp = spec.op;
    if (spec.op === "multiply" && valid.length === 2 && spec.sources.length === 2) {
      const subId = multiplyRebuildNumerator(
        spec.sources[0],
        (valid[0].entry.data as { derivedFrom?: DerivedFromMeta }).derivedFrom,
        spec.sources[1],
        (valid[1].entry.data as { derivedFrom?: DerivedFromMeta }).derivedFrom,
        "multiply",
      );
      if (subId) {
        const sub = await resolveSourceById(subId, inlineSources, new Set());
        if (sub) {
          renderValid = [sub];
          effSources = [subId];
          effOp = undefined;
        }
      }
    }
    const validSources = renderValid.map((v) => v.entry);
    const preloaded: Record<string, TimeSeriesData> = {};
    for (const v of renderValid) {
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
        sources: effSources,
        render: spec.render ?? ("line" as const),
        defaultDelta: spec.defaultDelta ?? ("1m" as const),
        normalize,
        // Log scale is meaningless when combined with dual-axis (one log axis
        // + one linear axis is misleading). Strip it here so a stale state
        // can't smuggle it past the composer's UI guard.
        scale: normalize === "dual-axis" ? undefined : spec.scale,
        rightAxisSources: spec.rightAxisSources,
        op: effOp,
        blurb: spec.blurb,
        // Visual + presentation fields. These existed on the inline-chart
        // spec since their respective features shipped, but were dropped
        // here — so a user could pick "NBER recessions" shading, set a
        // YoY default transform, type an annotation, or pick percent vs.
        // decimal divide display in the composer, and none of it would
        // render. Chart.astro reads these straight off chart.data
        // (see the payload assembly there), so the renderer had no
        // chance once they were gone. Carry every visual field through.
        shading: spec.shading,
        transform: spec.transform,
        annotations: spec.annotations,
        percentDisplay: spec.percentDisplay,
        // Bar-snapshot fields (only honored when render === "bar"; the
        // inline-bar path needs these to round-trip).
        barOrientation: spec.barOrientation,
        barSort: spec.barSort,
        barAsOf: spec.barAsOf,
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
  // Map charts don't reference time-series sources — they bind
  // to a (geo, indicator, vintage) tuple and load a cross-sectional
  // snapshot at render time. Return them with an empty sources array;
  // ChartMap.astro handles the rest. The renderer call site
  // dispatches on chart.data.render and never reads sources for
  // map, so an empty list is safe.
  if (chart.data.render === "map") {
    return { chart, sources: [] };
  }
  const sources = await Promise.all(
    (chart.data.sources ?? []).map((sid) => getEntry("sources", sid)),
  );
  const validSources = sources.filter(
    (s): s is CollectionEntry<"sources"> => s !== undefined,
  );
  if (validSources.length === 0) return null;
  // Inherit a source's defaultAnnotations onto a curated chart that
  // defines none of its own — so the usaspending partial-FY "annualized"
  // marker (audit new-#2) appears on dashboard charts too, the same way
  // compose.astro seeds it for composer-added inline charts. A
  // chart-authored `annotations` field always wins.
  if (!chart.data.annotations?.length) {
    const seed = validSources.find(
      (s) => s.data.defaultAnnotations?.length,
    )?.data.defaultAnnotations;
    if (seed) {
      chart = { ...chart, data: { ...chart.data, annotations: seed } };
    }
  }
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
      (s.charts ?? []).map((cid) =>
        resolveChart(
          cid,
          dashboard.inlineCharts,
          dashboard.inlineSources,
          dashboard.inlineMaps,
        ),
      ),
    );
    const valid = resolved.filter((r): r is ResolvedChart => r !== null);
    const hasMarkdown = !!(s.markdown && s.markdown.trim().length > 0);
    // Markdown-only section: emit it even though charts is empty, so
    // narrative blocks render between chart sections. Otherwise keep
    // the existing "drop sections that resolved to zero valid charts"
    // behavior — a section whose charts all failed to load shouldn't
    // surface as an empty heading.
    if (valid.length > 0 || hasMarkdown) {
      out.push({
        title: s.title ?? null,
        description: s.description,
        charts: valid,
        markdown: s.markdown,
        defaultDelta: s.defaultDelta,
        fixedRange: s.fixedRange,
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
    sec.charts.map((c) => {
      // Map charts are a snapshot — no time-window selector
      // applies. Return an empty list so the dashboard-level pill
      // computation correctly excludes them from the union.
      if (c.chart.data.render === "map") return [];
      return DELTA_WINDOWS.filter((w) =>
        c.sources.every((s) => s.data.supportedDeltas.includes(w)),
      );
    }),
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

/**
 * "Visible" chart filter: drops deprecated charts that aren't aliased to
 * a successor. The chart-ID stability contract says `deprecated: true`
 * keeps a slug reserved (no other chart can claim it), but the chart
 * itself shouldn't appear in catalogs / library exports / per-source
 * "charts using this source" lists. A `deprecated` chart with an
 * `aliasOf` IS still visible — the slug stays alive so old saved-
 * dashboard URLs keep working, but it resolves to its successor.
 *
 * Used by chart/[...id].astro, source/[...id].astro, library.json.ts,
 * and any future surface that lists charts to a human. Three call
 * sites previously inlined the same predicate; one place reduces the
 * risk of drift when the contract evolves.
 */
export function isVisibleChart(
  chart: CollectionEntry<"charts">,
): boolean {
  return !(chart.data.deprecated === true && !chart.data.aliasOf);
}
