/**
 * Maps a hidden-by-default geo source id to the single per-entity bucket it
 * belongs to. Used on BOTH sides of the lazy-loaded geo split so they agree:
 *   - server (src/lib/build-library-manifest.ts → buildGeoBuckets) groups
 *     sources into /library-geo/<kind>/<code>.json files;
 *   - client (src/lib/library-loader.ts → ensureGeoForSourceId) resolves a
 *     referenced-but-missing source (a saved composition / alert) to the one
 *     entity file it needs to fetch.
 *
 * Pure (no node/astro deps) so the client can import it. Priority matters:
 * metro → country → county → CD → statewide. County is checked before
 * CD/state because a county-equivalent id like `bls/qcew_..._va` can also
 * parse as a state. Returns null when no parser claims the id — the server
 * routes those to the `misc` bucket and the client falls back to it.
 */
import { parseMetroSourceId } from "./geographic-regions";
import { parseCdSourceId, parseStateSourceId } from "./congressional-districts";
import { parseCountrySourceId } from "./countries";
import { parseCountySourceId, parseQcewSourceId } from "./county-sources";

export type GeoEntityKind = "state" | "metro" | "country" | "county";

export interface GeoEntity {
  kind: GeoEntityKind;
  /** CBSA code (metro), ISO3/region code (country), 2-letter state (state).
   *  Empty string for the county / misc singletons. */
  code: string;
}

export function geoEntityForSourceId(id: string): GeoEntity | null {
  const metro = parseMetroSourceId(id);
  if (metro) return { kind: "metro", code: metro.cbsa };
  const country = parseCountrySourceId(id);
  if (country) return { kind: "country", code: country.code };
  if (parseCountySourceId(id) || parseQcewSourceId(id)) {
    return { kind: "county", code: "" };
  }
  const cd = parseCdSourceId(id);
  if (cd) return { kind: "state", code: cd.state };
  const st = parseStateSourceId(id);
  if (st) return { kind: "state", code: st.state };
  return null;
}
