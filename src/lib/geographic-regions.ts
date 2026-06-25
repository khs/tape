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
  // fhfa/hpi_<cbsa>  (hpi_po_<cbsa> reserved for purchase-only)
  {
    pipeline: "fhfa",
    rx: /^(hpi(?:_po)?)_(\d{5})$/,
  },
  // bea/<series>_<cbsa> metro income (state bea ids use word suffixes, not 5 digits)
  {
    pipeline: "bea",
    rx: /^([a-z][a-z0-9_]*?)_(\d{5})$/,
  },
];

/**
 * Hand-curated map of source IDs whose filenames predate the
 * `metro_<cbsa>` naming convention but represent metro-area data.
 * Without these entries the sources would fall through every geo
 * parser and surface as "national" in the composer's default list —
 * e.g. searching "unemployment" would mix DC-metro unemployment in
 * with the US national rate.
 *
 * Today this is just the original FRED-sourced Washington-Arlington-
 * Alexandria MSA series (CBSA 47900) that shipped before the metro
 * pipeline got a uniform ID scheme. When adding a new "legacy metro"
 * series, prefer the canonical pattern (`<pipeline>/metro_<cbsa>` or
 * the existing FRED CBSA-prefixed conventions) over extending this
 * registry; this is a back-compat shim, not the primary path.
 *
 * The series field is purely informational — internal callers read
 * the cbsa for tag synthesis, not the series name. Kept for symmetry
 * with the parsed shape the regex patterns produce.
 */
const LEGACY_METRO_IDS: Record<
  string,
  { pipeline: string; series: string; cbsa: string }
> = {
  "fred/dc_unemployment_rate": {
    pipeline: "fred_series",
    series: "unemployment_rate",
    cbsa: "47900",
  },
  "fred/dc_payrolls": {
    pipeline: "fred_series",
    series: "payrolls",
    cbsa: "47900",
  },
  "fred/dc_cpi": {
    // Retired (audit #6): hidden source, frozen at 2017. Kept here so
    // the legacy id still maps to the metro for any saved dashboard.
    pipeline: "fred_series",
    series: "cpi",
    cbsa: "47900",
  },
  "bls/cpi_washington_metro": {
    // Live successor to fred/dc_cpi: Washington-Arlington-Alexandria
    // CBSA CPI via BLS (CUURS35ASA0). Tagged to the same metro so it
    // surfaces under the DC metro chip.
    pipeline: "bls",
    series: "cpi",
    cbsa: "47900",
  },
  "fred/dc_median_listing": {
    pipeline: "fred_series",
    series: "median_listing",
    cbsa: "47900",
  },
};

/**
 * NOAA city-climate sources (pipeline `noaa_climate`) are slugged by city
 * name (e.g. `temperature_washington_dc`) rather than CBSA, because each
 * is a single long-record airport station — the canonical reading for its
 * metro, not an areal MSA aggregate. This map registers each city to its
 * metro's CBSA so the climate series surface under the composer's
 * "Metro area" drill-down alongside the ACS/BLS metro data. Keep in sync
 * with CITIES in pipelines/noaa_climate.py.
 */
const NOAA_CITY_CBSA: Record<string, string> = {
  washington_dc: "47900", new_york: "35620", chicago: "16980",
  los_angeles: "31080", houston: "26420", miami: "33100",
  atlanta: "12060", boston: "14460", seattle: "42660",
  denver: "19740", phoenix: "38060", dallas: "19100",
  san_francisco: "41860", minneapolis: "33460", detroit: "19820",
  philadelphia: "37980", san_diego: "41740", new_orleans: "35380",
};

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
  // Legacy overrides take precedence — these IDs are hardcoded and
  // wouldn't match any of the regex patterns below.
  const legacy = LEGACY_METRO_IDS[sourceId];
  if (legacy) return { ...legacy };
  const slash = sourceId.indexOf("/");
  let pipeline = "";
  let slug = sourceId;
  if (slash >= 0) {
    pipeline = sourceId.slice(0, slash);
    slug = sourceId.slice(slash + 1);
  }
  // NOAA city-climate: name-slugged (<metric>_<city>) → metro CBSA lookup.
  if (!pipeline || pipeline === "noaa_climate") {
    const nm = /^(temperature|precipitation)_(.+)$/.exec(slug);
    if (nm) {
      const cbsa = NOAA_CITY_CBSA[nm[2]];
      if (cbsa) return { pipeline: "noaa_climate", series: nm[1], cbsa };
    }
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
