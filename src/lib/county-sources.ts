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

/**
 * Known county slugs we ship today, longest-first so multi-word slugs
 * ("prince_georges", "falls_church") match before any shorter prefix
 * could collide. The pipeline normalizes county names to lowercase
 * snake_case (`Prince George's County` → `prince_georges`).
 *
 * Why a registry rather than a regex: the slug between "county_" and
 * the state code is `<series>_<county>`. Without knowing the set of
 * county slugs we'd have to assume the series is a single token, which
 * fails for hypothetical multi-token series like "labor_force". With
 * this registry the parser can match the county slug exactly and treat
 * the leading portion as the series, regardless of token count on
 * either side. Update this when adding a new county YAML.
 *
 * Sorted longest-first at module load so the matching loop short-
 * circuits on the most specific slug first.
 */
const COUNTY_SLUGS: ReadonlyArray<string> = [
  "prince_georges",
  "prince_william",
  "falls_church",
  "alexandria",
  "arlington",
  "fairfax",
  "loudoun",
  "montgomery",
].sort((a, b) => b.length - a.length);

export interface ParsedCountySourceId {
  /** Pipeline that owns the source — only "bls" today. */
  pipeline: string;
  /** Two-letter uppercase state code. */
  state: string;
  /**
   * Series + county slug joined with an underscore — e.g.
   * "unemployment_alexandria". Preserved for back-compat with older
   * callers; new code should prefer the split `series` + `countyName`
   * fields below.
   */
  slug: string;
  /**
   * Series prefix portion of the slug (e.g. "unemployment") — what
   * data the source measures, independent of which county. May be
   * empty if the slug consists of only a county name.
   */
  series: string;
  /**
   * County-name portion of the slug, in lowercase snake_case
   * (e.g. "alexandria", "prince_georges"). When present, callers
   * doing search-overrides on a county-tagged source should match
   * against THIS rather than the full slug — otherwise a query
   * matching the series ("unemployment") would surface every
   * county source, which is the leak this field exists to prevent.
   *
   * Falls back to the full slug when none of the known county
   * slugs match — defensive; an unrecognized county still passes
   * the COUNTY_TAG synthesis (via the regex match above) so the
   * composer keeps hiding it from the default list, but the
   * search-unlock heuristic loses precision.
   */
  countyName: string;
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
  const slug = m[1];
  // Split the slug into <series>_<countyName> by walking the known
  // county registry longest-first. Bare county slugs (no series
  // prefix) match with empty series.
  let series = "";
  let countyName = slug;
  for (const c of COUNTY_SLUGS) {
    if (slug === c) {
      series = "";
      countyName = c;
      break;
    }
    if (slug.endsWith("_" + c)) {
      countyName = c;
      series = slug.slice(0, slug.length - c.length - 1);
      break;
    }
  }
  return {
    pipeline: "bls",
    state: codeLower.toUpperCase(),
    slug,
    series,
    countyName,
  };
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

// ---------------------------------------------------------------------------
// QCEW jurisdiction sources (pipelines/bls_qcew.py)
// ---------------------------------------------------------------------------
// QCEW ships DC-metro jobs/wages for 8 county-equivalents PLUS the Washington
// MSA. They're all sub-national jurisdiction detail that must NOT pollute the
// default Sources list (the bug: "Alexandria, VA — average weekly wage" and
// friends showing up unsearched), so they reuse the COUNTY_TAG hide-by-default
// flag and the same name-anchored search-unlock as county sources. The MSA is
// not literally a county, but COUNTY_TAG here means "hide this sub-national geo
// until the user types its name"; that's exactly the behaviour we want for it.
//
// Source-ID convention: `bls/qcew_<metric>_<area-slug>` where <metric> is one
// of employment / avg_weekly_wage / federal_employment and <area-slug> is one
// of the keys below. The map's VALUE is the search-unlock name: the substring
// a user types (>= UNLOCK_QUERY_MIN_CHARS) to surface the otherwise-hidden
// series. None of the names contains a metric word, so typing a series name
// ("employment") can't surface every area — the same leak-guard the county
// search-unlock enforces. KEEP IN SYNC with bls_qcew.py's AREAS (a
// corpus test in county-sources.test.ts fails if a shipped qcew_* YAML's slug
// isn't registered here).
const QCEW_AREA_NAMES: Record<string, string> = {
  dc_metro: "washington metro",
  prince_georges_md: "prince georges",
  prince_william_va: "prince william",
  montgomery_md: "montgomery",
  alexandria_va: "alexandria",
  arlington_va: "arlington",
  fairfax_va: "fairfax",
  loudoun_va: "loudoun",
  dc: "district of columbia",
};

// Longest slug first so "dc_metro" matches before "dc" (and any future
// shared prefixes resolve to the most specific area).
const QCEW_SLUGS: ReadonlyArray<string> = Object.keys(QCEW_AREA_NAMES).sort(
  (a, b) => b.length - a.length,
);

export interface ParsedQcewSourceId {
  /** Metric segment: employment | avg_weekly_wage | federal_employment. */
  metric: string;
  /** Area slug, e.g. "alexandria_va", "dc", "dc_metro". */
  areaSlug: string;
  /** Search-unlock name (e.g. "alexandria", "washington metro") — what a
   *  user types to surface the hidden source. Match against THIS, not the
   *  metric, so a series-name query doesn't surface every area. */
  areaName: string;
}

/**
 * Parse a QCEW jurisdiction source ID, or null when it isn't one (so callers
 * can fall through to other geo parsers).
 */
export function parseQcewSourceId(id: string): ParsedQcewSourceId | null {
  if (!id) return null;
  const m = id.match(/^bls\/qcew_(.+)$/);
  if (!m) return null;
  const rest = m[1]; // <metric>_<area-slug>
  for (const slug of QCEW_SLUGS) {
    if (rest === slug) {
      return { metric: "", areaSlug: slug, areaName: QCEW_AREA_NAMES[slug] };
    }
    if (rest.endsWith("_" + slug)) {
      return {
        metric: rest.slice(0, rest.length - slug.length - 1),
        areaSlug: slug,
        areaName: QCEW_AREA_NAMES[slug],
      };
    }
  }
  return null;
}

/** True iff the source ID parses as a QCEW jurisdiction source. */
export function isQcewSourceId(id: string): boolean {
  return parseQcewSourceId(id) !== null;
}
