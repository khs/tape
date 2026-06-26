/**
 * Resolve a dashboard tile's REAL default title + whether it's a map, for the
 * composer's per-tile note/override modal ("Edit chart note").
 *
 * The bug this fixes: the modal only looked tiles up in the library catalog, so
 * an INLINE tile (a map built in the Maps tab, or a custom inline chart) — which
 * lives in `inlineMaps` / `inlineCharts`, not the catalog — fell through to
 * showing its raw ref ("inlinemap:cr451EKd") as the "default title", and the
 * modal copy always said "chart" even for a map.
 *
 * Ref conventions (see composer-state.ts):
 *   inlinemap:<id>  → a map,   title in inlineMaps[<id>]
 *   inline:<id>     → a chart,  title in inlineCharts[<id>]
 *   anything else   → a library chart, title in the catalog
 *
 * In the composer every map tile is an `inlinemap:` ref (library map charts
 * aren't in the catalog), so the prefix is the reliable map signal.
 */

interface TitledEntry {
  title: string;
}

export interface TileNoteMeta {
  /** The tile's real default title — NEVER the raw `inline…:` ref when the
   *  referenced entry exists. */
  title: string;
  isMap: boolean;
  /** Noun for the modal copy: "map" for map tiles, otherwise "chart". */
  noun: "map" | "chart";
}

export const INLINE_MAP_PREFIX = "inlinemap:";
export const INLINE_CHART_PREFIX = "inline:";

export function resolveTileNoteMeta(
  chartId: string,
  ctx: {
    inlineMaps?: Record<string, TitledEntry> | undefined;
    inlineCharts?: Record<string, TitledEntry> | undefined;
    libraryCharts?: ReadonlyArray<{ id: string; title: string }> | undefined;
  },
): TileNoteMeta {
  if (chartId.startsWith(INLINE_MAP_PREFIX)) {
    const m = ctx.inlineMaps?.[chartId.slice(INLINE_MAP_PREFIX.length)];
    return { title: m?.title ?? chartId, isMap: true, noun: "map" };
  }
  if (chartId.startsWith(INLINE_CHART_PREFIX)) {
    const c = ctx.inlineCharts?.[chartId.slice(INLINE_CHART_PREFIX.length)];
    return { title: c?.title ?? chartId, isMap: false, noun: "chart" };
  }
  const lib = ctx.libraryCharts?.find((c) => c.id === chartId);
  return { title: lib?.title ?? chartId, isMap: false, noun: "chart" };
}
