/**
 * County/city name disambiguation for the choropleth renderer.
 *
 * The us-counties topology carries 6 known collisions where a county
 * and an independent city share the same NAME within the same state.
 * Without disambiguation the choropleth tooltip just says "Fairfax"
 * for both, and the reader can't tell which one's lit up. This module
 * computes per-GEOID name overrides — " (county)" / " (city)" suffixes
 * — that the renderer applies to feature properties before drawing.
 *
 * The 6 collisions (state FIPS, name, county-FIPS / city-FIPS):
 *
 *   24 Baltimore (24005 county / 24510 city)
 *   29 St. Louis (29189 county / 29510 city)
 *   51 Fairfax   (51059 county / 51600 city)
 *   51 Franklin  (51067 county / 51620 city)
 *   51 Richmond  (51159 county / 51760 city) — Richmond city is the capital
 *   51 Roanoke   (51161 county / 51770 city)
 *
 * Virginia is over-represented because it's the only state with a
 * large number of independent cities (cities that aren't part of any
 * county). Maryland (Baltimore), Missouri (St. Louis), and Nevada
 * (Carson City, but no collision) have small numbers of independent
 * cities; everywhere else, cities are nested in counties and the
 * county GEOID is enough to identify them.
 *
 * Independent-city detection: 5-digit county-FIPS GEOIDs format as
 * state(2) + county-FIPS(3). Independent cities in this topology have
 * county-FIPS values in the 510-840 range (per Census FIPS conventions).
 * The full-county FIPS namespace tops out below 510.
 *
 * Single-occurrence places (e.g., Falls Church City — the only one) do
 * NOT receive a suffix. The rule is: only add the parenthetical when
 * a same-name peer is also in the feature list. That keeps the common
 * case clean.
 */

/**
 * Independent-city county-FIPS lower bound. The Census assigns these
 * to "county-equivalent" cities — places that exist outside any
 * county's jurisdiction (mostly Virginia).
 */
const INDEPENDENT_CITY_FIPS_MIN = "510";
/** Independent-city county-FIPS upper bound (inclusive). */
const INDEPENDENT_CITY_FIPS_MAX = "840";

/** A feature entry the disambiguator needs to look at. The choropleth
 *  renderer's feature properties carry more than this; only these two
 *  fields drive the disambiguation. */
export interface DisambiguationEntry {
  /** GEOID (5-digit county/city or longer for tracts). Tracts are
   *  filtered out internally. */
  id: string;
  /** Current display name (e.g. "Fairfax", "Baltimore"). */
  name: string;
}

/**
 * Return true if a 5-digit county-FIPS GEOID points at an independent
 * city (county-equivalent) rather than a true county. Exposed for the
 * one-off renderer call sites that need to label a single feature.
 */
export function isIndependentCityGeoid(geoid: string): boolean {
  if (geoid.length !== 5) return false;
  const countyFips = geoid.slice(2, 5);
  return (
    countyFips >= INDEPENDENT_CITY_FIPS_MIN &&
    countyFips <= INDEPENDENT_CITY_FIPS_MAX
  );
}

/**
 * Given a list of feature entries (id + current name), return a map
 * from GEOID to the disambiguated name. Only GEOIDs that collide with
 * a same-state peer of the same name appear in the result — every
 * other GEOID keeps its original name and is absent from the map.
 *
 * Suffix rules:
 *   - independent city → " (city)"
 *   - everything else  → " (county)"
 *
 * Names that already end with ")" (e.g., pre-suffixed from an earlier
 * pass, or names that legitimately contain a parenthetical) are not
 * modified, so this function is idempotent under repeated calls.
 *
 * Only 5-digit GEOIDs are considered. Tract-level GEOIDs (11 digits)
 * are filtered out — tract names like "1.01" appear in every county
 * and would generate false-positive "collisions."
 */
export function disambiguateCountyCityNames(
  entries: ReadonlyArray<DisambiguationEntry>,
): Map<string, string> {
  // Bucket entries by "<stateFips>|<name>" so we only suffix names
  // that have ≥2 same-state peers.
  const buckets = new Map<string, DisambiguationEntry[]>();
  for (const e of entries) {
    if (!e.name || !e.id || e.id.length !== 5) continue;
    const stateFips = e.id.slice(0, 2);
    const key = `${stateFips}|${e.name}`;
    const bucket = buckets.get(key);
    if (bucket) bucket.push(e);
    else buckets.set(key, [e]);
  }
  const overrides = new Map<string, string>();
  for (const bucket of buckets.values()) {
    if (bucket.length < 2) continue;
    for (const entry of bucket) {
      // Idempotent guard: don't re-suffix something that already has
      // a parenthetical. Lets the renderer call this twice on the
      // same feature collection without doubling " (county) (county)".
      if (entry.name.endsWith(")")) continue;
      const suffix = isIndependentCityGeoid(entry.id)
        ? " (city)"
        : " (county)";
      overrides.set(entry.id, entry.name + suffix);
    }
  }
  return overrides;
}
