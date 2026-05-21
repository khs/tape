/**
 * Helpers for parsing county-level source IDs. Currently this is a
 * narrow slice — only the DMV-area BLS LAUS county-unemployment
 * series ship today — but the infrastructure is in place so future
 * county-level ACS / spending pipelines slot in without each YAML
 * having to declare a geo tag.
 *
 * Why this module exists: without it, county sources (e.g.
 * `bls/county_unemployment_alexandria_va`) flow into the composer's
 * default "Sources" tab alongside national-level series. That's
 * confusing — a user browsing US-macro sees Alexandria-County
 * unemployment mixed with the US national rate. Metro / CD / state
 * sources already get synthetic tags that hide them behind their
 * own drill-down chip; counties belong in the same pattern.
 *
 * Source-ID convention:
 *   - `bls/county_<series>_<county-slug>_<st>` where:
 *     - <series>: lowercase snake_case (unemployment, payrolls, ...)
 *     - <county-slug>: lowercase county name with spaces → underscores
 *       (e.g. "Prince George's" → "prince_georges", "Falls Church" →
 *       "falls_church")
 *     - <st>: 2-letter lowercase state code (validated against the
 *       US_STATES table — rejects accidental matches like "bls/
 *       county_foo_xy")
 */
import { US_STATES } from "./congressional-districts";

/**
 * Synthetic tag attached to county-level sources in library.json.ts.
 * The composer's default Sources view filters this OUT, just like
 * METRO_TAG / CD_TAG / STATE_TAG; the user surfaces them via the
 * geo drill-down or by typing the county name in the search field
 * (4+ characters anchored to the county slug).
 */
export const COUNTY_TAG = "us-county";

const STATE_CODE_SET = new Set(US_STATES.map((s) => s.code));

export interface ParsedCountySourceId {
  /** Pipeline that owns the source — only "bls" today. */
  pipeline: string;
  /** Two-letter uppercase state code. */
  state: string;
  /**
   * Series + county slug joined with an underscore — e.g.
   * "unemployment_alexandria". Callers that want to split further
   * can do so themselves; the composer only needs the whole string
   * for search matching.
   */
  slug: string;
}

/**
 * Parse a county source ID. Returns null when the ID isn't a county
 * source, so callers can fall through to other geo parsers (metro,
 * CD, state, country) on the same source.
 *
 * Tolerant of leading prefixes (composer's "+" inline-derived
 * shorthand, etc.) by checking only the part after the last "/".
 */
export function parseCountySourceId(
  id: string,
): ParsedCountySourceId | null {
  if (!id) return null;
  // bls/county_<series>_<county-slug>_<st> — anchor on the trailing
  // 2-letter state code, with everything between "county_" and the
  // state captured as the (series + county-slug) opaque blob.
  const m = id.match(/^bls\/county_(.+)_([a-z]{2})$/);
  if (!m) return null;
  // STATE_CODE_SET is lowercase (matches the YAML / pipeline-emitted
  // form); return uppercase for callers since 2-letter state codes
  // are conventionally uppercase in display contexts.
  const codeLower = m[2];
  if (!STATE_CODE_SET.has(codeLower)) return null;
  return { pipeline: "bls", state: codeLower.toUpperCase(), slug: m[1] };
}

/**
 * True iff the source ID parses as a county source.
 */
export function isCountySourceId(id: string): boolean {
  return parseCountySourceId(id) !== null;
}

/**
 * Tag list to merge into a source's tags. Emits one tag —
 * COUNTY_TAG itself — used as the master "hide from default view"
 * flag in compose.astro. (No per-county sub-tag yet; we only ship
 * 8 counties and a one-tier hide is enough. When the dataset
 * expands, add a per-state or per-county sub-tag here mirroring
 * metroTagsFor's two-tier pattern.)
 */
export function countyTagsFor(id: string): string[] {
  return parseCountySourceId(id) ? [COUNTY_TAG] : [];
}
