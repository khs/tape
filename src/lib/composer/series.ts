/**
 * Shared source-series fetcher + the chart-tile color palette (Plan 2d).
 *
 * Extracted from compose.astro because BOTH the tile-preview thumbnails
 * (renderTileSparkline) and the custom-chart modal preview
 * (renderCustomChartPreview) fetch + cache source data and color series the
 * same way. fetchSourceSeries resolves derived sources (A op B) recursively.
 *
 * SeriesPoint / FetchedSeries / CC_COLORS are static module exports. The
 * fetcher is a factory (createSeriesFetcher) so the per-page cache + the
 * library/baseUrl/state deps stay encapsulated; build ONE instance and share it.
 */
import { isDerivedId } from "./ids";
import { ensureGeoForSourceId } from "../library-loader";
import type { SharedLibraryPayload } from "../library-loader";
import type { UIState } from "./state";
import type { LibraryPayload } from "./library";

export type SeriesPoint = { t: string; v: number };
export type FetchedSeries = {
  id: string;
  name: string;
  points: SeriesPoint[];
};

/** Modest palette echoing the chart-tile colors. Cycles for >8 sources. */
export const CC_COLORS = [
  "#2563eb",
  "#dc2626",
  "#16a34a",
  "#9333ea",
  "#ea580c",
  "#0891b2",
  "#db2777",
  "#65a30d",
];

export interface SeriesFetcherContext {
  getLibrary: () => LibraryPayload | null;
  baseUrl: string;
  /** For state.inlineSources (derived-source A/B resolution). */
  state: UIState;
}

export function createSeriesFetcher(ctx: SeriesFetcherContext) {
  const { getLibrary, baseUrl, state } = ctx;
  // Cache fetched source-data JSON by source ID so toggling sources doesn't
  // refetch. Page-scoped, lives in this factory instance.
  const sourceDataCache: Map<string, Promise<FetchedSeries | null>> = new Map();
  async function fetchSourceSeries(sourceId: string): Promise<FetchedSeries | null> {
    if (sourceDataCache.has(sourceId)) return sourceDataCache.get(sourceId)!;
    const promise = (async () => {
      // Derived path: recursively fetch A and B, combine via op.
      if (isDerivedId(sourceId)) {
        const spec = state.inlineSources[sourceId];
        if (!spec) return null;
        const [a, b] = await Promise.all([
          fetchSourceSeries(spec.a),
          fetchSourceSeries(spec.b),
        ]);
        if (!a || !b) return null;
        const aMap = new Map<string, number>();
        for (const p of a.points) aMap.set(p.t, p.v);
        const bMap = new Map<string, number>();
        for (const p of b.points) bMap.set(p.t, p.v);
        const all = new Set<string>();
        for (const p of a.points) all.add(p.t);
        for (const p of b.points) all.add(p.t);
        const ordered = [...all].sort();
        let lastA: number | null = null;
        let lastB: number | null = null;
        const out: SeriesPoint[] = [];
        for (const t of ordered) {
          if (aMap.has(t)) lastA = aMap.get(t)!;
          if (bMap.has(t)) lastB = bMap.get(t)!;
          if (lastA === null || lastB === null) continue;
          let v: number;
          if (spec.op === "divide") {
            if (lastB === 0) continue;
            v = lastA / lastB;
          } else if (spec.op === "sum") {
            v = lastA + lastB;
          } else {
            v = lastA - lastB;
          }
          out.push({ t, v });
        }
        if (out.length === 0) return null;
        return { id: sourceId, name: spec.name, points: out };
      }
      const lib = getLibrary();
      let meta = lib?.sources[sourceId];
      // Geo-hidden sources (CD / state / metro / county / country) live in lazy
      // /library-geo/* slices, not the lean manifest. A chart can reference one
      // before its slice has loaded — e.g. editing a pregen multi-state chart
      // like "NAEP grade 8 math: selected states" — so pull the slice on demand
      // instead of silently dropping the series (the bug where a 6-line chart
      // rendered as "1 series", inconsistently, as slices raced to load).
      if (lib && !meta) {
        await ensureGeoForSourceId(lib as SharedLibraryPayload, sourceId);
        meta = lib.sources[sourceId];
      }
      if (!lib || !meta) return null;
      const rawPath = (meta as any).dataFile as string | undefined;
      if (!rawPath) return null;
      const url = `${baseUrl}/${rawPath.replace(/^\//, "")}`;
      try {
        const r = await fetch(url);
        if (!r.ok) return null;
        const json = await r.json();
        const points: SeriesPoint[] = Array.isArray(json?.points)
          ? (json.points as SeriesPoint[]).filter(
              (p) => p && typeof p.t === "string" && typeof p.v === "number",
            )
          : [];
        if (points.length === 0) return null;
        return { id: sourceId, name: meta.shortName ?? meta.name, points };
      } catch {
        return null;
      }
    })();
    sourceDataCache.set(sourceId, promise);
    // Don't let a transient null (a geo slice that hadn't loaded yet, or a
    // one-off fetch error) poison the cache and permanently drop the series —
    // evict it so a later render can retry and succeed.
    void promise.then((res) => {
      if (res === null) sourceDataCache.delete(sourceId);
    });
    return promise;
  }

  return { fetchSourceSeries };
}