/**
 * Geo + tag filter helpers for the source-picker.
 *
 * Lifted from compose.astro's inline closures (and the v1 duplicate
 * in SourcePicker.astro) so the logic has ONE home + can be
 * unit-tested. The composer's Sources tab, the cc-modal chart
 * creator, and the alerts page picker all run the same source-list
 * through these functions; a regression in any of them silently
 * breaks discoverability everywhere.
 *
 * Function shape: pure. Each helper takes the source under
 * consideration + the user's current filter state + (where needed)
 * the library payload. No reads from module scope, no caches that
 * outlive the call — callers that want memoization should layer it
 * outside (e.g., per-instance WeakMap caches in SourcePicker.astro
 * for the unlock helpers).
 *
 * The "unlock" pattern (≥ 4-char query matches a state / metro /
 * country name) lets the user surface geo sources via typing without
 * having to click the chip — typing "Texas" or "Abilene" surfaces
 * TX or Abilene-tagged sources even when the corresponding chip is
 * inactive. The 4-char threshold is a deliberate tradeoff: short
 * substrings ("cars", "tax") would over-match and flood the default
 * list with geographic specificity nobody asked for.
 */
import { METRO_TAG } from "./geographic-regions";
import { COUNTRY_TAG } from "./countries";
import {
  CD_TAG,
  STATE_TAG,
  STATEWIDE_DISTRICT_CODE,
  US_STATES,
  parseCdSourceId,
  parseStateSourceId,
} from "./congressional-districts";
import { COUNTY_TAG, parseCountySourceId } from "./county-sources";

/** Minimum query length that "unlocks" geo sources via name match.
 *  Cross-references: every unlocked* helper below applies this floor. */
export const UNLOCK_QUERY_MIN_CHARS = 4;

/**
 * Library payload shape this module needs. We only use the metros +
 * countries dictionaries (for the unlock-by-name path); the full
 * library payload has more fields irrelevant to filtering.
 */
export interface SourceFiltersLibrary {
  metros?: Record<string, { shortName: string; name: string }>;
  countries?: Record<string, { name: string }>;
}

/**
 * Set of state 2-letter codes whose name contains the query as a
 * substring (case-insensitive), or null when no match / query too
 * short. Pure — call once per (query) and memoize externally if you
 * need to.
 */
export function unlockedStatesForQuery(query: string): Set<string> | null {
  if (query.length < UNLOCK_QUERY_MIN_CHARS) return null;
  const matched = new Set<string>();
  const ql = query.toLowerCase();
  for (const s of US_STATES) {
    if (s.name.toLowerCase().includes(ql)) matched.add(s.code);
  }
  return matched.size > 0 ? matched : null;
}

/**
 * Set of "metro:<cbsa>" tag strings unlocked by the query. Returns
 * tag strings (not bare CBSA codes) so callers can intersect
 * directly against a source's .tags array.
 */
export function unlockedMetrosForQuery(
  query: string,
  lib: SourceFiltersLibrary,
): Set<string> | null {
  if (query.length < UNLOCK_QUERY_MIN_CHARS || !lib.metros) return null;
  const matched = new Set<string>();
  const ql = query.toLowerCase();
  for (const [code, entry] of Object.entries(lib.metros)) {
    const hay = (entry.shortName + " " + entry.name).toLowerCase();
    if (hay.includes(ql)) matched.add(`${METRO_TAG}:${code}`);
  }
  return matched.size > 0 ? matched : null;
}

/**
 * Set of "country-specific:<code>" tag strings unlocked by the
 * query. Same pattern as unlockedMetrosForQuery.
 */
export function unlockedCountriesForQuery(
  query: string,
  lib: SourceFiltersLibrary,
): Set<string> | null {
  if (query.length < UNLOCK_QUERY_MIN_CHARS || !lib.countries) return null;
  const matched = new Set<string>();
  const ql = query.toLowerCase();
  for (const [code, entry] of Object.entries(lib.countries)) {
    if (entry.name.toLowerCase().includes(ql)) {
      matched.add(`${COUNTRY_TAG}:${code}`);
    }
  }
  return matched.size > 0 ? matched : null;
}

/**
 * Does this source pass the metro chip's filter?
 *
 * - Selected CBSA != null → narrow to that CBSA's sources only.
 * - Selected CBSA == null:
 *   - non-metro sources always pass.
 *   - metro sources pass iff the query unlocks the source's CBSA via
 *     name match.
 *
 * "Metro-tagged" means the source carries either the bare METRO_TAG
 * (umbrella, auto-injected by library.json for sources whose IDs
 * parse as metro) OR a specific `metro:<cbsa>` tag declared in YAML.
 * Both are checked — older code missed sources like Zillow's that
 * only declare the per-CBSA tag without the umbrella.
 */
export function passesMetroFilter(
  sourceTags: readonly string[],
  selectedCbsa: string | null,
  query: string,
  lib: SourceFiltersLibrary,
): boolean {
  if (selectedCbsa) {
    return sourceTags.includes(`${METRO_TAG}:${selectedCbsa}`);
  }
  const hasMetroTag = sourceTags.some(
    (t) => t === METRO_TAG || t.startsWith(`${METRO_TAG}:`),
  );
  if (!hasMetroTag) return true;
  const unlock = unlockedMetrosForQuery(query, lib);
  if (!unlock) return false;
  for (const t of sourceTags) {
    if (unlock.has(t)) return true;
  }
  return false;
}

/**
 * Does this source pass the country chip's filter?
 *
 * - Selected country != null → narrow to that country/region's
 *   sources only.
 * - Selected country == null:
 *   - non-country sources always pass.
 *   - country sources pass iff the query unlocks the source's
 *     country via name match.
 */
export function passesCountryFilter(
  sourceTags: readonly string[],
  selectedCountryCode: string | null,
  query: string,
  lib: SourceFiltersLibrary,
): boolean {
  if (selectedCountryCode) {
    return sourceTags.includes(`${COUNTRY_TAG}:${selectedCountryCode}`);
  }
  if (!sourceTags.includes(COUNTRY_TAG)) return true;
  const unlock = unlockedCountriesForQuery(query, lib);
  if (!unlock) return false;
  for (const t of sourceTags) {
    if (unlock.has(t)) return true;
  }
  return false;
}

/**
 * Does this source pass the CD chip's filter?
 *
 * The CD chip has a two-step drill-down: state, then district. The
 * function's logic encodes the matrix of (chip-state, district-state):
 *
 *   cdState == null:
 *     - Non-geo sources pass.
 *     - Geo sources pass only if the query unlocks the source's
 *       state via name match (≥ 4-char unlock pattern).
 *
 *   cdState set:
 *     - Non-geo sources fail (the chip's active, only geo is
 *       relevant).
 *     - cdDistrict == STATEWIDE_DISTRICT_CODE: only state-level
 *       sources for that state.
 *     - cdDistrict == specific CD: only sources for that exact CD.
 *     - cdDistrict == null ("any district"): both state-level + CDs
 *       of that state.
 */
export function passesCdFilter(
  sourceId: string,
  sourceTags: readonly string[],
  cdState: string | null,
  cdDistrict: string | null,
  query: string,
): boolean {
  const isCd = sourceTags.includes(CD_TAG);
  const isStateLevel = sourceTags.includes(STATE_TAG);
  const isGeo = isCd || isStateLevel;
  if (!cdState) {
    if (!isGeo) return true;
    const unlock = unlockedStatesForQuery(query);
    if (!unlock) return false;
    const parsed = isCd ? parseCdSourceId(sourceId) : parseStateSourceId(sourceId);
    return !!parsed && unlock.has(parsed.state);
  }
  // Chip active.
  if (!isGeo) return false;
  if (cdDistrict === STATEWIDE_DISTRICT_CODE) {
    if (!isStateLevel) return false;
    return parseStateSourceId(sourceId)?.state === cdState;
  }
  if (cdDistrict) {
    if (!isCd) return false;
    const parsed = parseCdSourceId(sourceId);
    return parsed?.state === cdState && parsed?.district === cdDistrict;
  }
  // District unset = "Any": both state-level + CDs of that state.
  if (isStateLevel) return parseStateSourceId(sourceId)?.state === cdState;
  if (isCd) return parseCdSourceId(sourceId)?.state === cdState;
  return false;
}

/**
 * Does this source pass the county-source filter?
 *
 * Counties are HIDDEN by default — there's no county drill-down
 * chip yet (only ~8 counties ship, mostly DMV-area BLS
 * unemployment) — so the only way to surface them is to type a
 * ≥ 4-char query that matches the county's NAME portion of the
 * source-ID slug. The slug-match (not name-match) is deliberate:
 * the source's display name + searchText already power the global
 * text filter; this gate just enforces the "don't show every
 * county in the default list" rule.
 *
 * Why slug-match against county NAME only (not full slug): a query
 * for the series name ("unemployment") would otherwise match every
 * county source ("unemployment_alexandria"), defeating the chip's
 * hide-by-default intent. Locked down in county-sources.test.ts.
 */
export function passesCountyFilter(
  sourceId: string,
  sourceTags: readonly string[],
  query: string,
): boolean {
  if (!sourceTags.includes(COUNTY_TAG)) return true;
  if (query.length < UNLOCK_QUERY_MIN_CHARS) return false;
  const parsed = parseCountySourceId(sourceId);
  if (!parsed) return false; // defensive — should never happen given the COUNTY_TAG check
  return parsed.countyName.toLowerCase().includes(query.toLowerCase());
}
