import type { APIRoute } from "astro";
import {
  buildLibraryManifest,
  buildGeoBuckets,
  isGeoHidden,
  stripGeoUmbrellaTags,
} from "../lib/build-library-manifest";

/**
 * Chart-library manifest consumed by the composer (/compose/), the alerts
 * page, and the SourcePicker islands. Contains metadata only — no time-series
 * data. Points data is fetched on-demand from public/data/<pipeline>/<id>.json.
 *
 * This endpoint emits the LEAN slice: charts + every visible-by-default source
 * + hint cards + the metro/country lookups + tagCountsByGeo. The ~28.9k
 * hidden-by-default geo sources (CD / state / metro / county / country, ~37 MB)
 * ship separately from /library-geo.json and are lazy-loaded by the client
 * only when a geo chip is engaged or a >=4-char query unlocks them. The split
 * cut this payload from ~40 MB to ~2 MB. See src/lib/build-library-manifest.ts
 * (the shared builder + the isGeoHidden partition predicate) and
 * src/lib/library-loader.ts (the client-side shared cache + lazy geo merge).
 *
 * Shape:
 *   {
 *     charts:  [...],
 *     sources: { [id]: { name, shortName, ..., tags, searchText } },  // lean
 *     metros, metroTag, countries, countryTag, tagCountsByGeo,
 *     geoSplit: true   // signals the client to lazy-load /library-geo.json
 *   }
 */
export const prerender = true;

export const GET: APIRoute = async () => {
  const [manifest, geo] = await Promise.all([
    buildLibraryManifest(),
    // Also runs the misc-growth guard (throws if an unplaceable geo source
    // appears that isn't allowlisted) before this lean payload is emitted.
    buildGeoBuckets(),
  ]);
  const miscIds = new Set(Object.keys(geo.misc));

  // Lean partition: keep hint cards + every source that is NOT hidden behind a
  // geo chip. Unplaceable geo sources (the `misc` bucket — declare a geo tag
  // but no entity parser placed them) are ALSO emitted here, with their hiding
  // umbrella tag stripped, so they're visible in the default list + search
  // rather than silently unreachable. Real per-entity geo sources are the only
  // ones excluded — they ship in their /library-geo/<kind>/<...> slice.
  // tagCountsByGeo (computed over the full set) ships here so chip counts stay
  // correct without the geo block.
  const sources: Record<string, unknown> = {};
  for (const [id, s] of Object.entries(manifest.sources)) {
    if (s.kind === "hint" || !isGeoHidden(s.tags)) {
      sources[id] = s;
    } else if (miscIds.has(id)) {
      sources[id] = { ...s, tags: stripGeoUmbrellaTags(s.tags ?? []) };
    }
  }

  const body = JSON.stringify({
    charts: manifest.charts,
    sources,
    metros: manifest.metros,
    metroTag: manifest.metroTag,
    countries: manifest.countries,
    countryTag: manifest.countryTag,
    tagCountsByGeo: manifest.tagCountsByGeo,
    geoSplit: true,
  });
  return new Response(body, {
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "public, max-age=300",
    },
  });
};
