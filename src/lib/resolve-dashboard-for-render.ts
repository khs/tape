import type { CollectionEntry } from "astro:content";
import type { DeltaWindow } from "./deltas";
import {
  resolveSections,
  dashboardSupportedDeltas,
  resolveDashboardDefault,
  type DashboardShape,
  type ResolvedSection,
} from "./resolve-dashboard";
import {
  resolveBarSnapshots,
  type BarSnapshotEntry,
} from "./resolve-bar-snapshots";

/**
 * The bundle every dashboard-rendering page needs once it has a dashboard
 * shape in hand: resolved sections, the window-pill set, the resolved default
 * window, pre-fetched bar-snapshots, plus the telemetry totals. Echoes
 * `chartOverrides` and `fixedRange` straight back so the grid can apply them.
 */
export interface DashboardForRender {
  sections: ResolvedSection[];
  supportedDeltas: DeltaWindow[];
  defaultDelta: DeltaWindow;
  fixedRange?: { start: string; end: string };
  chartOverrides?: Record<string, Partial<CollectionEntry<"charts">["data"]>>;
  barSnapshots: Map<string, BarSnapshotEntry[]>;
  viewedSourceIds: string[];
  viewedChartCount: number;
}

/**
 * Shared "resolve a dashboard for rendering" pipeline.
 *
 * `[...slug].astro` (preset), `custom.astro` (composed `?d=` state), and
 * `index.astro` (featured) each independently re-implemented this exact
 * sequence. Centralizing it here keeps the three (drift-prone) copies in sync.
 * Page-specific concerns stay on the page: input acquisition (collection entry
 * vs decoded state vs featured pick), the fork/share-URL (each builds it
 * differently — preset re-encodes, custom reuses the raw `?d=`), SEO/OG, and
 * all page chrome.
 *
 * The function is intentionally free of `astro:content` entry / SSR coupling —
 * callers project their input into the plain `DashboardShape` first. Inline
 * registries (composer charts/sources/maps) flow through `DashboardShape`;
 * preset/featured pages simply leave them undefined.
 */
export async function resolveDashboardForRender(
  shape: DashboardShape & { fixedRange?: { start: string; end: string } },
): Promise<DashboardForRender> {
  const sections = await resolveSections(shape);
  const supportedDeltas = dashboardSupportedDeltas(sections);
  const defaultDelta = resolveDashboardDefault(shape.defaultDelta, supportedDeltas);
  // Wide fan-out, parallel; a no-op when the dashboard has no bar charts.
  const barSnapshots = await resolveBarSnapshots(
    sections.flatMap((s) => s.charts),
  );
  // Deduped source list for the dashboard_viewed telemetry event.
  const viewedSourceIds = Array.from(
    new Set(
      sections.flatMap((sec) => sec.charts.flatMap((c) => c.sources.map((s) => s.id))),
    ),
  );
  const viewedChartCount = sections.reduce((acc, sec) => acc + sec.charts.length, 0);
  return {
    sections,
    supportedDeltas,
    defaultDelta,
    fixedRange: shape.fixedRange,
    chartOverrides: shape.chartOverrides,
    barSnapshots,
    viewedSourceIds,
    viewedChartCount,
  };
}
