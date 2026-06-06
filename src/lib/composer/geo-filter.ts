/**
 * Composer-facing geo/tag filters.
 *
 * The composer's Sources tab, cc-modal, and ds-modal each filter the full
 * ~20k-source library on every keystroke. The actual matching logic lives in
 * `src/lib/source-filters.ts` (pure, unit-tested, shared with SourcePicker +
 * the alerts page). Those helpers are deliberately memo-free — calling them
 * per-source would recompute each "unlock" set ~20k times per keystroke and
 * freeze the UI. This factory wraps them with a per-query memo (held in the
 * returned closure) and adapts them to the composer's call shape:
 *
 *   - The CD chip's active flag is `selectedTags.has(CD_TAG)` (the chip is a
 *     toggle, not a literal tag a source must carry), and there's a gate
 *     state: chip ON but no state picked yet → show nothing ("Pick a state
 *     above…"). `source-filters.ts` folds chip-active into `cdState != null`
 *     and has no gate, so `passesCdFilter` here keeps the chip flag + the gate
 *     and delegates ONLY the chip-on-with-state district matrix to the lib —
 *     so the composer's behavior (and its empty-state copy) is unchanged.
 *   - `library` (the metros/countries dictionaries that power the name-unlock
 *     path) loads async, so callers pass a getter; each call reads the current
 *     value.
 *
 * Call `createComposerGeoFilters` once and reuse the returned object — the
 * memo caches live in its closure. Previously these were module-scope closures
 * + caches inside compose.astro's inline <script> (see Plan 2b).
 */
import {
  CD_TAG,
  STATE_TAG,
  parseCdSourceId,
  parseStateSourceId,
} from "../congressional-districts";
import { METRO_TAG } from "../geographic-regions";
import { COUNTRY_TAG } from "../countries";
import {
  passesCdFilter as libPassesCdFilter,
  passesCountyFilter as libPassesCountyFilter,
  unlockedStatesForQuery,
  unlockedMetrosForQuery,
  unlockedCountriesForQuery,
  type SourceFiltersLibrary,
} from "../source-filters";

export interface ComposerGeoFilters {
  /** CD chip: `selectedTags.has(CD_TAG)` is the chip's active flag; chip-on
   *  with no `cdState` yet is the "pick a state" gate (returns false for all
   *  sources, i.e. an empty list). */
  passesCdFilter(
    id: string,
    tags: string[],
    selectedTags: Set<string>,
    cdState: string | null,
    cdDistrict: string | null,
    query?: string,
  ): boolean;
  passesMetroFilter(
    tags: string[],
    selectedCbsa: string | null,
    query: string,
  ): boolean;
  passesCountryFilter(
    tags: string[],
    selectedCountryCode: string | null,
    query?: string,
  ): boolean;
  passesCountyFilter(id: string, tags: string[], query?: string): boolean;
}

export function createComposerGeoFilters(
  getLibrary: () => SourceFiltersLibrary | null | undefined,
): ComposerGeoFilters {
  // Per-query memo for each unlock set, keyed by the exact query string
  // (recomputed when the query changes). The passes* filters run once per
  // source per render; without these a 4-char query rebuilt the unlock set
  // ~20k times per keystroke and froze the UI.
  let stateCache: { q: string; result: Set<string> | null } | null = null;
  let metroCache: { q: string; result: Set<string> | null } | null = null;
  let countryCache: { q: string; result: Set<string> | null } | null = null;

  function memoStates(q: string): Set<string> | null {
    if (stateCache && stateCache.q === q) return stateCache.result;
    const result = unlockedStatesForQuery(q);
    stateCache = { q, result };
    return result;
  }
  function memoMetros(q: string): Set<string> | null {
    if (metroCache && metroCache.q === q) return metroCache.result;
    const result = unlockedMetrosForQuery(q, getLibrary() ?? {});
    metroCache = { q, result };
    return result;
  }
  function memoCountries(q: string): Set<string> | null {
    if (countryCache && countryCache.q === q) return countryCache.result;
    const result = unlockedCountriesForQuery(q, getLibrary() ?? {});
    countryCache = { q, result };
    return result;
  }

  return {
    passesCdFilter(id, tags, selectedTags, cdState, cdDistrict, query = "") {
      const isCd = tags.includes(CD_TAG);
      const isStateLevel = tags.includes(STATE_TAG);
      const isGeo = isCd || isStateLevel;
      if (!selectedTags.has(CD_TAG)) {
        // Chip off: non-geo always passes; a geo source surfaces only via a
        // 4-char state-name unlock (typing "Texas" shows TX series).
        if (!isGeo) return true;
        const unlock = memoStates(query);
        if (!unlock) return false;
        const parsed = isCd ? parseCdSourceId(id) : parseStateSourceId(id);
        return !!parsed && unlock.has(parsed.state);
      }
      // Chip on: only geo sources, and only once a state is picked (the gate —
      // chip-on + no state shows the "Pick a state above…" empty state).
      if (!isGeo) return false;
      if (!cdState) return false;
      // Chip on + state: the state/district matrix is identical to the lib's
      // cdState-set path, so delegate it (single home for that logic).
      return libPassesCdFilter(id, tags, cdState, cdDistrict, query);
    },

    passesMetroFilter(tags, selectedCbsa, query) {
      if (selectedCbsa) {
        return tags.includes(`${METRO_TAG}:${selectedCbsa}`);
      }
      const hasMetroTag = tags.some(
        (t) => t === METRO_TAG || t.startsWith(`${METRO_TAG}:`),
      );
      if (!hasMetroTag) return true;
      const unlock = memoMetros(query);
      if (!unlock) return false;
      for (const t of tags) {
        if (unlock.has(t)) return true;
      }
      return false;
    },

    passesCountryFilter(tags, selectedCountryCode, query = "") {
      if (selectedCountryCode) {
        return tags.includes(`${COUNTRY_TAG}:${selectedCountryCode}`);
      }
      if (!tags.includes(COUNTRY_TAG)) return true;
      const unlock = memoCountries(query);
      if (!unlock) return false;
      for (const t of tags) {
        if (unlock.has(t)) return true;
      }
      return false;
    },

    passesCountyFilter(id, tags, query = "") {
      // No unlock set to memoize — parseCountySourceId is cheap and the lib's
      // logic is already self-contained per source, so delegate directly.
      return libPassesCountyFilter(id, tags, query);
    },
  };
}
