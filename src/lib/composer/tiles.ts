/**
 * Composition tile previews (Plan 2d) -- the small chart sparklines + mini-map
 * silhouettes painted into each tile of the composed dashboard (and the
 * library result cards). renderTilePreview dispatches to renderTileSparkline
 * (inline/library charts -> a multi-series Plot.lineY, capped at 4 series) or
 * renderTileMapPreview (inline maps -> a static d3-geo + topojson choropleth
 * silhouette, tinted from the indicator data when present, hatched where not).
 *
 * Extracted from compose.astro via createTiles(ctx). Pulls the heavy d3-geo /
 * topojson-client / @observablehq/plot deps out of the page core. The shared
 * source-series fetcher (fetchSourceSeries, series.ts) + the topojson cache
 * (mapBboxTopoCache, shared with the Maps-tab bbox preview) come in via ctx.
 * library is read via getLibrary() per fn. renderTilePreview is the only entry;
 * renderComposition (which stays in compose) calls it per tile.
 */
import { isInlineId, isInlineMapId } from "./ids";
import { CC_COLORS, type FetchedSeries } from "./series";
import { combineTwo, type CombineOp } from "../derive";
import type { TimeSeriesData } from "../data-types";
import * as Plot from "@observablehq/plot";
import { geoAlbers, geoPath } from "d3-geo";
import { feature as topoFeature } from "topojson-client";
import type { UIState } from "./state";
import type { LibraryPayload } from "./library";

export interface TilesContext {
  state: UIState;
  getLibrary: () => LibraryPayload | null;
  baseUrl: string;
  fetchSourceSeries: (sourceId: string) => Promise<FetchedSeries | null>;
  mapBboxTopoCache: Map<string, unknown>;
}

export function createTiles(ctx: TilesContext) {
  const { state, getLibrary, baseUrl, fetchSourceSeries, mapBboxTopoCache } = ctx;
  function renderTilePreview(host: HTMLElement, chartId: string): void {
    if (isInlineMapId(chartId)) {
      void renderTileMapPreview(host, chartId);
    } else {
      void renderTileSparkline(host, chartId);
    }
  }

  async function renderTileSparkline(
    host: HTMLElement,
    chartId: string,
  ): Promise<void> {
    const library = getLibrary();
    // Resolve source IDs from inline or library chart.
    let sourceIds: string[] = [];
    let op: CombineOp | undefined;
    if (isInlineId(chartId)) {
      sourceIds = state.inlineCharts[chartId]?.sources ?? [];
      op = state.inlineCharts[chartId]?.op as CombineOp | undefined;
    } else {
      const c = library?.charts.find((x) => x.id === chartId);
      sourceIds = c?.sources ?? [];
      op = (c as { op?: CombineOp } | undefined)?.op;
    }
    if (sourceIds.length === 0) return;
    // Cap at 4 series so a multi-source comparison tile doesn't try
    // to draw 12 overlapping lines in a 64px preview.
    const showIds = sourceIds.slice(0, 4);
    const seriesList = await Promise.all(
      showIds.map((id) => fetchSourceSeries(id)),
    );
    const valid = seriesList.filter((s): s is FetchedSeries => s !== null);
    if (valid.length === 0) return;
    const width = host.clientWidth || 200;
    const height = 64;
    try {
      // An op'd 2-source tile (e.g. a divided / summed derived source) renders
      // as a SINGLE combined line — matching the full chart — not its two raw
      // inputs. combineTwo only reads .points, so the fetched series feed it
      // directly.
      const marks =
        op && valid.length === 2
          ? [
              Plot.lineY(
                combineTwo(
                  valid[0] as unknown as TimeSeriesData,
                  valid[1] as unknown as TimeSeriesData,
                  op,
                ).map((p) => ({ t: new Date(p.t), v: p.v })),
                { x: "t", y: "v", stroke: CC_COLORS[0], strokeWidth: 1.2 },
              ),
            ]
          : valid.map((s, i) =>
              Plot.lineY(
                s.points.map((p) => ({ t: new Date(p.t), v: p.v })),
                {
                  x: "t",
                  y: "v",
                  stroke: CC_COLORS[i % CC_COLORS.length],
                  strokeWidth: 1.2,
                },
              ),
            );
      const plot = Plot.plot({
        width,
        height,
        marginLeft: 2,
        marginRight: 2,
        marginTop: 4,
        marginBottom: 2,
        style: { background: "transparent" },
        x: { axis: null },
        y: { axis: null },
        marks,
      }) as HTMLElement;
      host.replaceChildren(plot);
    } catch {
      // Render failure — leave the host empty. The tile already shows
      // title + meta + (optional) coverage warning, so an empty
      // preview area is acceptable graceful degradation.
    }
  }

  // Mini-map preview for inline maps. Loads the same TopoJSON
  // the full /custom/ render uses, then paints a static silhouette
  // tinted by the data values (if available). When the data file
  // isn't present (newer indicator, narrower state set), falls back
  // to an outline-only render so the user still sees the geographic
  // shape of what they're about to compose.
  async function renderTileMapPreview(
    host: HTMLElement,
    mapId: string,
  ): Promise<void> {
    const spec = state.inlineMaps[mapId];
    if (!spec) return;
    let boundaryUrl: string;
    let layerName: string;
    if (spec.geo === "state") {
      // Same-origin local topology (the CDN copy is CSP connect-src
      // blocked in prod). Matches ChartMap.astro's STATES_BOUNDARY_URL.
      boundaryUrl = `${baseUrl}/maps/us-states-10m.json`;
      layerName = "states";
    } else if (spec.geo === "county") {
      boundaryUrl = `${baseUrl}/maps/us-counties-10m.json`;
      layerName = "counties";
    } else if (spec.boundaryFile) {
      boundaryUrl = `${baseUrl}${spec.boundaryFile.startsWith("/") ? "" : "/"}${spec.boundaryFile}`;
      layerName = spec.geo === "block-group" ? "block_groups" : "tracts";
    } else if (spec.states && spec.states.length > 0) {
      // Multi-state inline map (no pre-built boundaryFile). Handled in
      // the multi-fetch branch below — set layerName here and a
      // placeholder boundaryUrl just so the single-fetch code path
      // (which the boundaryFile case still uses) compiles cleanly.
      boundaryUrl = "";
      layerName = spec.geo === "block-group" ? "block_groups" : "tracts";
    } else if (spec.state) {
      const seg = spec.geo === "block-group" ? "block-groups" : "tracts";
      boundaryUrl = `${baseUrl}/maps/${spec.state.toLowerCase()}-${seg}-topo.json`;
      layerName = spec.geo === "block-group" ? "block_groups" : "tracts";
    } else {
      return;
    }
    // Boundary fetch: single file in the common case, parallel multi-
    // fetch + merge for the multi-state Maps-tab spec. Used to be
    // single-fetch-only with the first state's silhouette serving as
    // a stand-in — but that was confusing to users who'd selected 4
    // states and only saw MA's outline (Keller, 2026-05-30). The
    // ~500KB-1MB per-state files are CDN-cached after first load, so
    // the worst-case multi-state preview adds 1-3 cached fetches on
    // subsequent renders.
    const isMultiState = !!(spec.states && spec.states.length > 0);
    // IMPORTANT: include `type: "FeatureCollection"`. d3's
    // geoAlbers().fitSize() reads the type tag to decide how to walk
    // the input — without it, fitSize silently produces NaN for the
    // projected scale + translate, and every path's `d` comes out as
    // "MNaN,NaN…", rendering an empty SVG. The pre-refactor code got
    // this for free because topojson.feature() returned a properly
    // tagged FeatureCollection; the refactor that introduced the
    // multi-state branch constructed `fc` as a bare { features: [] }
    // object and lost the tag.
    const fc: {
      type: "FeatureCollection";
      features: { id?: string | number; properties?: Record<string, unknown> }[];
    } = {
      type: "FeatureCollection",
      features: [],
    };
    if (isMultiState) {
      const seg = spec.geo === "block-group" ? "block-groups" : "tracts";
      const urls = spec.states!.map(
        (st) => `${baseUrl}/maps/${st.toLowerCase()}-${seg}-topo.json`,
      );
      const topos = await Promise.all(urls.map(async (u) => {
        try {
          if (mapBboxTopoCache.has(u)) {
            return mapBboxTopoCache.get(u) as { objects: Record<string, unknown> };
          }
          const r = await fetch(u);
          if (!r.ok) return null;
          const j = (await r.json()) as { objects: Record<string, unknown> };
          mapBboxTopoCache.set(u, j);
          return j;
        } catch {
          return null;
        }
      }));
      for (const t of topos) {
        if (!t) continue;
        const obj = (t.objects ?? {})[layerName];
        if (!obj) continue;
        const shard = topoFeature(t as never, obj as never) as unknown as {
          features: { id?: string | number; properties?: Record<string, unknown> }[];
        };
        fc.features.push(...shard.features);
      }
      if (fc.features.length === 0) return;
    } else {
      let topo: { objects: Record<string, unknown> } | null = null;
      try {
        if (mapBboxTopoCache.has(boundaryUrl)) {
          topo = mapBboxTopoCache.get(boundaryUrl) as typeof topo;
        } else {
          const r = await fetch(boundaryUrl);
          if (!r.ok) return;
          topo = await r.json();
          mapBboxTopoCache.set(boundaryUrl, topo);
        }
      } catch {
        return;
      }
      if (!topo) return;
      const obj = (topo.objects ?? {})[layerName];
      if (!obj) return;
      const single = topoFeature(topo as never, obj as never) as unknown as {
        features: typeof fc.features;
      };
      fc.features = single.features;
    }

    // Try to load the data file(s) so the preview can paint values,
    // not just outlines. Same path scheme ChartMap.astro uses.
    // Multi-state previews merge values from all state shards so the
    // tint is consistent across the displayed region — matches the
    // /custom/ + /u/<slug>/ behavior.
    const dataDirSeg =
      spec.geo === "block-group" ? "acs_block_group" : `acs_${spec.geo}`;
    const dataStates =
      spec.geo === "state" || spec.geo === "county"
        ? null
        : isMultiState
          ? spec.states!.map((s) => s.toLowerCase())
          : spec.state
            ? [spec.state.toLowerCase()]
            : null;
    let values: Record<string, number> = {};
    if (spec.geo === "state" || spec.geo === "county") {
      try {
        const r = await fetch(
          `${baseUrl}/data/${dataDirSeg}/${spec.indicator}_${spec.vintage}.json`,
        );
        if (r.ok) {
          const j = (await r.json()) as { values?: Record<string, number> };
          values = j.values ?? {};
        }
      } catch {
        // ignore — outline-only render
      }
    } else if (dataStates) {
      const shards = await Promise.all(dataStates.map(async (st) => {
        try {
          const r = await fetch(
            `${baseUrl}/data/${dataDirSeg}/${st}/${spec.indicator}_${spec.vintage}.json`,
          );
          if (!r.ok) return null;
          return (await r.json()) as { values?: Record<string, number> };
        } catch {
          return null;
        }
      }));
      for (const s of shards) {
        if (s?.values) Object.assign(values, s.values);
      }
    }

    const width = host.clientWidth || 200;
    const height = 110;
    const projection = geoAlbers().fitSize([width, height], fc as never);
    const pathGen = geoPath(projection);

    // Build a single-hue tint scale on log-or-linear by-extent.
    const vs: number[] = [];
    for (const f of fc.features) {
      const id = String(f.id ?? "");
      const v = values[id];
      if (typeof v === "number" && Number.isFinite(v)) vs.push(v);
    }
    const tintFor = (v: number | undefined): string => {
      if (v === undefined || !Number.isFinite(v) || vs.length === 0) {
        return "rgba(15, 118, 110, 0.10)"; // outline-only fallback
      }
      const min = Math.min(...vs);
      const max = Math.max(...vs);
      const t = max === min ? 0.5 : (v - min) / (max - min);
      // 0.15 -> 0.85 opacity range so even low values are visible and
      // high values don't fully saturate (preview, not the real chart).
      const alpha = 0.15 + 0.7 * t;
      return `rgba(15, 118, 110, ${alpha.toFixed(3)})`;
    };

    const svgNS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("width", String(width));
    svg.setAttribute("height", String(height));
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    // Diagonal-stripe pattern for no-data regions. Same visual
    // language as the full ChartMap view's `map-no-data-*`
    // pattern, scaled down for the thumbnail (smaller tile = smaller
    // stripe gap). Distinguishes "no data published for this
    // polygon" from "valid data at the low end of the color ramp",
    // which the previous outline-only-faint-teal fallback didn't.
    // patternUnits=userSpaceOnUse keeps the stripes stable when the
    // tile re-renders at a different width.
    const patternId = `compose-no-data-${mapId.replace(/[^a-z0-9-]/gi, "-")}`;
    const defs = document.createElementNS(svgNS, "defs");
    const pattern = document.createElementNS(svgNS, "pattern");
    pattern.setAttribute("id", patternId);
    pattern.setAttribute("width", "5");
    pattern.setAttribute("height", "5");
    pattern.setAttribute("patternUnits", "userSpaceOnUse");
    pattern.setAttribute("patternTransform", "rotate(45)");
    const bg = document.createElementNS(svgNS, "rect");
    bg.setAttribute("width", "5");
    bg.setAttribute("height", "5");
    bg.setAttribute("fill", "#ececec");
    pattern.appendChild(bg);
    const stripe = document.createElementNS(svgNS, "line");
    stripe.setAttribute("x1", "0");
    stripe.setAttribute("y1", "0");
    stripe.setAttribute("x2", "0");
    stripe.setAttribute("y2", "5");
    stripe.setAttribute("stroke", "#bababa");
    stripe.setAttribute("stroke-width", "1.5");
    stripe.setAttribute("vector-effect", "non-scaling-stroke");
    pattern.appendChild(stripe);
    defs.appendChild(pattern);
    svg.appendChild(defs);
    let noDataPaths = 0;
    for (const f of fc.features) {
      const d = pathGen(f as never);
      if (!d) continue;
      const id = String(f.id ?? "");
      const v = values[id];
      const hasData = typeof v === "number" && Number.isFinite(v);
      if (!hasData) noDataPaths += 1;
      const p = document.createElementNS(svgNS, "path");
      p.setAttribute("d", d);
      p.setAttribute(
        "fill",
        hasData ? tintFor(v) : `url(#${patternId})`,
      );
      p.setAttribute("stroke", "rgba(15, 118, 110, 0.45)");
      p.setAttribute("stroke-width", "0.4");
      svg.appendChild(p);
    }
    // Replace the preview pane. If any regions came back hatched,
    // pin a short legend below the map so the reader knows what the
    // stripes mean. Hidden when every polygon has data (the most
    // common case) to keep the tile chrome-free.
    host.replaceChildren(svg);
    if (noDataPaths > 0) {
      const note = document.createElement("p");
      note.className = "comp-tile-preview-nodata-note";
      note.style.cssText =
        "margin: 4px 0 0; font-size: 10.5px; color: var(--color-neutral-500); display: flex; align-items: center; gap: 5px;";
      const swatch = document.createElement("span");
      swatch.style.cssText =
        "display: inline-block; width: 10px; height: 10px; border: 1px solid #bababa; background: repeating-linear-gradient(45deg, #ececec 0 1.5px, #bababa 1.5px 3px);";
      note.appendChild(swatch);
      const text = document.createElement("span");
      text.textContent = `${noDataPaths.toLocaleString()} region${noDataPaths === 1 ? "" : "s"} have no published data for this indicator + vintage`;
      note.appendChild(text);
      host.appendChild(note);
    }
  }


  return { renderTilePreview };
}