import type { APIRoute } from "astro";
import { getCollection } from "astro:content";
import { loadSourceData } from "../lib/load-data";

/**
 * Chart-library manifest consumed by the composer (/compose/) and the
 * client-side /custom/ renderer. Contains metadata only — no time-series data.
 * Points data is fetched on-demand from public/data/<pipeline>/<id>.json.
 *
 * Shape:
 *   {
 *     charts: [{ id, title, tags, sources, defaultDelta, normalize, blurb, deprecated, aliasOf }],
 *     sources: { [id]: { name, shortName, kind, supportedDeltas, emphasis, dataFile, formatting, provenance } }
 *   }
 */
export const prerender = true;

export const GET: APIRoute = async () => {
  const [chartsCol, sourcesCol] = await Promise.all([
    getCollection("charts"),
    getCollection("sources"),
  ]);

  const sources: Record<string, unknown> = {};
  for (const s of sourcesCol) {
    // Read first / last observation dates from the source's data file at
    // build time so the composer can flag charts whose data doesn't cover
    // a fixed-range request without having to fetch each JSON itself.
    let firstObservation: string | undefined;
    let lastObservation: string | undefined;
    try {
      const data = loadSourceData(s.data.dataFile);
      if (data.kind === "timeseries" && data.points.length > 0) {
        firstObservation = data.points[0].t;
        lastObservation = data.points[data.points.length - 1].t;
      }
    } catch {
      // Missing data file; leave first/last undefined so callers know.
    }
    sources[s.id] = {
      id: s.id,
      name: s.data.name,
      shortName: s.data.shortName,
      description: s.data.description,
      kind: s.data.kind,
      pipeline: s.data.pipeline,
      dataFile: s.data.dataFile,
      supportedDeltas: s.data.supportedDeltas,
      unit: s.data.unit,
      formatting: s.data.formatting,
      emphasis: s.data.emphasis,
      provenance: s.data.provenance,
      firstObservation,
      lastObservation,
    };
  }

  const charts = chartsCol
    // Hide charts tagged deprecated=true without an alias. Aliased ones still
    // expose the redirect so saved dashboards can resolve transparently.
    .filter((c) => !(c.data.deprecated === true && !c.data.aliasOf))
    .map((c) => {
      // Build a single concatenated `searchText` field on the server to keep
      // client-side search cheap and consistent. Includes title, id, tags,
      // and each linked source's name/shortName/description.
      const sourceText = (c.data.sources ?? [])
        .map((sid) => {
          const s = (sources as Record<string, { name?: string; shortName?: string; description?: string }>)[sid];
          if (!s) return "";
          return [s.name, s.shortName, s.description].filter(Boolean).join(" ");
        })
        .join(" ");
      const searchText = [
        c.data.title,
        c.id,
        (c.data.tags ?? []).join(" "),
        c.data.blurb ?? "",
        sourceText,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return {
        id: c.id,
        title: c.data.title,
        tags: c.data.tags ?? [],
        sources: c.data.sources,
        render: c.data.render,
        defaultDelta: c.data.defaultDelta,
        normalize: c.data.normalize,
        seriesLabels: c.data.seriesLabels,
        blurb: c.data.blurb,
        emphasis: c.data.emphasis,
        deprecated: c.data.deprecated,
        aliasOf: c.data.aliasOf,
        searchText,
      };
    });

  const body = JSON.stringify({ charts, sources });
  return new Response(body, {
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "public, max-age=300",
    },
  });
};
