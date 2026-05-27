/**
 * Build-time precomputation of filter-aware topical-tag counts for
 * the SourcePicker's chip strip.
 *
 * Why: the chip strip used to show GLOBAL tag counts that didn't
 * react to geo-chip state — when the user picked "Virginia" from the
 * CD chip, "agriculture (12)" stayed at 12 even though zero VA
 * sources carried that tag. The fix is a contingency table:
 * per-geo-filter-state tag counts emitted in library.json so the
 * picker can look up the right bucket without per-render walks.
 *
 * Why precompute at build time vs. runtime: library.json is already
 * fetched once per session + cached (300s). Sticking ~2-5 KB of
 * precomputed counts in it is essentially free, and avoids
 * re-walking ~20k sources on every chip click.
 *
 * Bucket keys mirror the SourcePicker's chip state:
 *   __all                  - no geo filter (default landing view)
 *   metro:<cbsa>           - metro chip set to this CBSA
 *   country:<code>         - country chip set to this country code
 *   cd:<state>:any         - CD chip state picked, "Any district"
 *   cd:<state>:state       - CD chip state picked, "Statewide only"
 *   cd:<state>:<district>  - CD chip state + specific district
 *
 * Multi-chip combinations are NOT precomputed — the SourcePicker
 * falls back to __all when more than one chip is active. Multi-chip
 * selection is rare enough that the explosion in key count isn't
 * worth the precision.
 *
 * __all uses the runtime's "default-visible" filter (NONE of the
 * umbrella geo tags). Hint cards are skipped throughout.
 */
import { CD_TAG, STATE_TAG, parseCdSourceId, parseStateSourceId } from "./congressional-districts";
import { METRO_TAG } from "./geographic-regions";
import { COUNTRY_TAG } from "./countries";
import { COUNTY_TAG } from "./county-sources";

/**
 * Subset of the library's source-meta shape this module needs.
 * library.json.ts widens to `unknown` after the synthetic-tag step;
 * callers narrow into this view before invoking computeTagCountsByGeo.
 */
export interface TagCountSourceMeta {
  /** All tags carried by the source (declared + synthetic). */
  tags?: string[];
  /** Skip hint cards — they're synthetic discoverability bridges
   *  and don't represent a real pickable source. */
  kind?: string;
}

/**
 * Is this tag a geo synthetic (umbrella OR per-entity)? We strip
 * these from the topical-count set — the geo chips already
 * surface them, and double-counting confuses users.
 */
export function isGeoSyntheticTag(tag: string): boolean {
  return (
    tag === CD_TAG ||
    tag === STATE_TAG ||
    tag === METRO_TAG ||
    tag === COUNTRY_TAG ||
    tag === COUNTY_TAG ||
    tag.startsWith(`${METRO_TAG}:`) ||
    tag.startsWith(`${COUNTRY_TAG}:`)
  );
}

/**
 * Is this source visible in the default landing view (no chip
 * engaged, no query)? Mirrors the runtime filter set:
 * passesCdFilter rejects CD/STATE-tagged sources, passesMetroFilter
 * rejects METRO-tagged sources, passesCountryFilter rejects
 * COUNTRY-tagged sources, passesCountyFilter rejects COUNTY-tagged
 * sources. Inverse = default-visible.
 */
export function isDefaultVisible(tags: readonly string[]): boolean {
  return (
    !tags.includes(CD_TAG) &&
    !tags.includes(STATE_TAG) &&
    !tags.includes(METRO_TAG) &&
    !tags.includes(COUNTRY_TAG) &&
    !tags.includes(COUNTY_TAG)
  );
}

/**
 * Build the per-geo-filter tag-count contingency table.
 * Shape: { [bucketKey]: { [topicalTag]: count } }.
 *
 * @param sourcesById  Library sources keyed by ID. Pass the same
 *                     map that library.json emits — hints can be
 *                     included (they'll be filtered out internally).
 * @returns A bucket-keyed dictionary of topical-tag-count maps.
 *          Always includes `__all`, even when empty.
 */
export function computeTagCountsByGeo(
  sourcesById: Record<string, TagCountSourceMeta>,
): Record<string, Record<string, number>> {
  const out: Record<string, Record<string, number>> = { __all: {} };
  const bump = (geoKey: string, tag: string): void => {
    const bucket = (out[geoKey] ??= {});
    bucket[tag] = (bucket[tag] ?? 0) + 1;
  };
  for (const [sid, meta] of Object.entries(sourcesById)) {
    if (meta.kind === "hint") continue;
    const tags = meta.tags ?? [];
    const topical = tags.filter((t) => !isGeoSyntheticTag(t));
    if (topical.length === 0) continue;
    // __all: default-visible sources only.
    if (isDefaultVisible(tags)) {
      for (const t of topical) bump("__all", t);
    }
    // metro:<cbsa> — for every per-CBSA tag the source carries.
    for (const t of tags) {
      if (t.startsWith(`${METRO_TAG}:`)) {
        const cbsa = t.slice(METRO_TAG.length + 1);
        for (const tt of topical) bump(`metro:${cbsa}`, tt);
      }
    }
    // country:<code> — for every per-country tag the source carries
    // (includes country-specific:USA for US national sources).
    for (const t of tags) {
      if (t.startsWith(`${COUNTRY_TAG}:`)) {
        const code = t.slice(COUNTRY_TAG.length + 1);
        for (const tt of topical) bump(`country:${code}`, tt);
      }
    }
    // CD-tagged: cd:<state>:any AND cd:<state>:<district>.
    // (passesCdFilter with district=specific surfaces ONLY that CD,
    // so per-CD buckets must NOT receive statewide series.)
    if (tags.includes(CD_TAG)) {
      const cdParsed = parseCdSourceId(sid);
      if (cdParsed) {
        for (const tt of topical) {
          bump(`cd:${cdParsed.state}:any`, tt);
          bump(`cd:${cdParsed.state}:${cdParsed.district}`, tt);
        }
      }
    }
    // STATE-tagged: cd:<state>:any AND cd:<state>:state.
    // (passesCdFilter with district=STATEWIDE_DISTRICT_CODE surfaces
    // only state-level for that state, so statewide series populate
    // the "state" bucket. They do NOT populate per-district buckets
    // because passesCdFilter with district=specific filters them out.)
    if (tags.includes(STATE_TAG)) {
      const stateParsed = parseStateSourceId(sid);
      if (stateParsed) {
        for (const tt of topical) {
          bump(`cd:${stateParsed.state}:any`, tt);
          bump(`cd:${stateParsed.state}:state`, tt);
        }
      }
    }
  }
  return out;
}
