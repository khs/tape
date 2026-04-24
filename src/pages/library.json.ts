import type { APIRoute } from "astro";
import { getCollection } from "astro:content";

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
    };
  }

  const charts = chartsCol
    // Hide charts tagged deprecated=true without an alias. Aliased ones still
    // expose the redirect so saved dashboards can resolve transparently.
    .filter((c) => !(c.data.deprecated === true && !c.data.aliasOf))
    .map((c) => ({
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
    }));

  const body = JSON.stringify({ charts, sources });
  return new Response(body, {
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "public, max-age=300",
    },
  });
};
