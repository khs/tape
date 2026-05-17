/**
 * Helpers for parsing geographic-region source IDs (Metropolitan
 * Statistical Areas; intended to grow to congressional districts and
 * counties when those pipelines wire up).
 *
 * Source-ID conventions written by the metro pipelines:
 *   - "usaspending/metro_<cbsa>"                  (e.g. usaspending/metro_35620)
 *   - "acs_metro/<series>_<cbsa>"                 (e.g. acs_metro/bachelors_plus_35620)
 *   - "bls/metro_<series>_<cbsa>"                 (e.g. bls/metro_unemployment_35620)
 *
 * CBSA codes are 5-digit OMB codes; we accept any 5-digit numeric
 * suffix to stay forward-compatible with OMB renumberings.
 */

/**
 * Synthetic tag prepended to metro sources in library.json.ts so the
 * composer's tag filter and the Metro chip can both find them.
 * Per-metro tags follow the pattern METRO_TAG + ":" + <cbsa>, e.g.
 * "metro:35620" — distinct from chart-author tags so the metro dropdown
 * is the only UI that surfaces them.
 */
export const METRO_TAG = "metro";

export interface ParsedMetroSourceId {
  /** "usaspending", "acs_metro", or "bls" */
  pipeline: string;
  /** Series within the pipeline, e.g. "spending", "bachelors_plus",
   * "unemployment", "payrolls". For usaspending (single series per
   * metro) we return "spending" for symmetry. */
  series: string;
  /** 5-digit CBSA code as a string (preserves leading zeros). */
  cbsa: string;
}

const PATTERNS: Array<{
  pipeline: string;
  /** Regex over the part after "<pipeline>/". Captures (series, cbsa). */
  rx: RegExp;
  /** Override for the captured series when the file pattern doesn't carry
   * a series prefix (usaspending has one series per metro). */
  defaultSeries?: string;
}> = [
  // usaspending/metro_<cbsa>
  {
    pipeline: "usaspending",
    rx: /^metro_(\d{5})$/,
    defaultSeries: "spending",
  },
  // acs_metro/<series>_<cbsa>
  {
    pipeline: "acs_metro",
    rx: /^([a-z][a-z0-9_]*?)_(\d{5})$/,
  },
  // bls/metro_<series>_<cbsa>
  {
    pipeline: "bls",
    rx: /^metro_([a-z][a-z0-9_]*?)_(\d{5})$/,
  },
];

/**
 * Parse a source ID against the metro-source patterns above. Returns
 * null when the ID isn't a metro source — caller can fall back to other
 * geo parsers (district / county / state) as those land.
 *
 * Tolerant of leading "+" / inline-derived prefixes the composer uses for
 * derived sources by checking only the trailing portion after the last
 * "/". For unprefixed IDs (no "/"), we treat the entire ID as the
 * file-relative slug — the composer's source IDs from library.json.ts
 * always carry the "<pipeline>/" prefix, but unit tests and helper code
 * may pass just the slug.
 */
export function parseMetroSourceId(
  sourceId: string,
): ParsedMetroSourceId | null {
  if (!sourceId) return null;
  const slash = sourceId.indexOf("/");
  let pipeline = "";
  let slug = sourceId;
  if (slash >= 0) {
    pipeline = sourceId.slice(0, slash);
    slug = sourceId.slice(slash + 1);
  }
  for (const p of PATTERNS) {
    if (pipeline && pipeline !== p.pipeline) continue;
    const m = p.rx.exec(slug);
    if (!m) continue;
    if (p.defaultSeries) {
      return { pipeline: p.pipeline, series: p.defaultSeries, cbsa: m[1] };
    }
    return { pipeline: p.pipeline, series: m[1], cbsa: m[2] };
  }
  return null;
}

/**
 * True iff this source ID is recognized as a metro source. Convenience
 * wrapper for callers that don't need the parsed fields.
 */
export function isMetroSourceId(sourceId: string): boolean {
  return parseMetroSourceId(sourceId) !== null;
}

/**
 * Tag list to merge into a source's tags when the source is a metro
 * source. Returns an empty array for non-metro sources. Callers
 * (library.json.ts) concatenate this with the YAML-declared tags so
 * the composer's existing tag-filter machinery surfaces metros without
 * any extra plumbing.
 *
 * Emits two tags:
 *   - METRO_TAG ("metro") — used by the "Metro area" chip group filter
 *   - `${METRO_TAG}:${cbsa}` — used to filter to a single metro
 */
export function metroTagsFor(sourceId: string): string[] {
  const parsed = parseMetroSourceId(sourceId);
  if (!parsed) return [];
  return [METRO_TAG, `${METRO_TAG}:${parsed.cbsa}`];
}
