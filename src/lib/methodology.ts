/**
 * Per-pipeline "how to reproduce" methodology.
 *
 * Sources whose data is a direct fetch-and-store passthrough don't need
 * this — the provenance grid (provider / series ID / upstream URL /
 * license) on the source page already tells a reader everything. But for
 * series we MANIPULATE — aggregate, disambiguate, rescale, derive a rate,
 * remap geographies — the stored number isn't obviously the raw upstream
 * value, and a careful reader (or auditor) deserves to see exactly how we
 * got from the API response to the chart.
 *
 * This registry is keyed by the source YAML's `pipeline` field. Only the
 * providers doing non-trivial manipulation have an entry; SourceMethodology
 * renders nothing when {@link getMethodology} returns null. The per-source
 * specifics (the exact series identifier, the upstream URL, the unit) come
 * from the source's own provenance — this registry holds only the
 * per-pipeline method, so it stays DRY across a provider's many series and
 * can't drift from one source to the next.
 *
 * The authoritative, always-current method is the pipeline source file
 * itself, linked via {@link repoFileUrl}. Prose can paraphrase; the code
 * is ground truth.
 */

export interface ProviderMethodology {
  /** Upstream provider / program, spelled out. */
  upstream: string;
  /** One line on how the raw data is accessed (endpoint / portal / file). */
  access: string;
  /** Ordered transformation steps: raw upstream response → stored value. */
  steps: string[];
  /** Things a reproducer must know to match our numbers (boundary changes,
   *  dirty upstream codes, participation gaps, …). Omitted when none. */
  caveats?: string[];
  /** How the value ends up stored (canonical unit / scaling note). */
  storedAs?: string;
  /** Repo-relative path to the pipeline that produces these sources.
   *  Linked on the page — the code is the ground-truth method. */
  pipelineFile: string;
  /** Exact local command to regenerate the data. */
  runCommand: string;
}

/**
 * Public repository. The pipeline file is the authoritative, always-current
 * description of the method, so every methodology card links to it. Pinned
 * to the default branch (latest method) rather than a commit SHA — the data
 * refreshes on a schedule, and `main` is what produced the current numbers.
 */
export const REPO_BLOB_BASE = "https://github.com/khs/tape/blob/main";

/** Build a GitHub link to a repo-relative pipeline file. */
export function repoFileUrl(pipelineFile: string): string {
  return `${REPO_BLOB_BASE}/${pipelineFile}`;
}

/**
 * Methodology by `pipeline` field. Add an entry when a new provider does
 * something beyond a direct fetch-and-store — the source pages pick it up
 * automatically.
 */
export const METHODOLOGY: Record<string, ProviderMethodology> = {
  fec: {
    upstream: "Federal Election Commission — OpenFEC API",
    access:
      "GET api.open.fec.gov/v1/candidates/totals?office=H&cycle=<YYYY> (api.data.gov key), paginated over all House candidates",
    steps: [
      "Fetch every House candidate's financial totals for each even-year election cycle, 2008–2024.",
      "Sum `disbursements` (money actually spent) across all candidates, grouped by (state, district).",
      "Disambiguate FEC's `district` field: code \"00\" is the genuine at-large seat for single-member states (AK, DE, ND, SD, VT, WY in every cycle; MT through 2020) and the non-voting delegate seat for DC — but in multi-district states it's just spending FEC couldn't assign to a district. Keep the real seats (coded \"al\" / \"98\"); drop the unassigned residual.",
      "Drop impossible district numbers (> 53, above any state's real count) and any series that never recorded real spending.",
      "Convert dollars to millions (÷ 1e6) and record one point per cycle — a deliberate 2-year cadence, not monthly.",
    ],
    caveats: [
      "District numbers reflect the boundaries in effect that cycle. Redistricting redrew them after the 2010 and 2020 censuses, so a seat numbered N before 2012 / 2022 is a different geographic area than the same number after — charts of a district mark those boundary years.",
      "The small residual of spending FEC couldn't place in a valid district is included in the national total but in no per-district series, so districts sum to slightly less than the national line.",
    ],
    storedAs: "millions USD per cycle",
    pipelineFile: "pipelines/fec_house_spending.py",
    runCommand: "python pipelines/fec_house_spending.py",
  },

  bea: {
    upstream: "Bureau of Economic Analysis — Regional Economic Accounts",
    access:
      "GET apps.bea.gov/api/data (BEA API key); tables SAGDP2/SAGDP9 (state GDP), SAINC1 (state personal income), CAINC1 (county per-capita income)",
    steps: [
      "Fetch the regional table for every state (or county) across all available years.",
      "Apply each datum's `UNIT_MULT` — the power-of-ten exponent BEA returns alongside the value — to recover the actual figure.",
      "Convert currency to the site's canonical unit, billions of USD (per-capita income stays in dollars).",
      "Drop combined-area and placeholder rows (non-positive values) that BEA includes for completeness.",
    ],
    caveats: [
      "County per-capita personal income is published here as a choropleth map layer (public/data/acs_county/…), not as a per-county time series.",
    ],
    storedAs: "billions USD (per-capita income in USD)",
    pipelineFile: "pipelines/bea.py",
    runCommand: "python pipelines/bea.py        # pass `county` for the county-income map",
  },

  fred_series: {
    upstream: "Federal Reserve Bank of St. Louis — FRED",
    access:
      "GET fredgraph.csv?id=<SERIES_ID> — the keyless CSV download for the series ID shown above",
    steps: [
      "Download the series CSV and parse (date, value) rows, discarding FRED's \".\" missing-value markers.",
      "For a small set of currency series reported in millions (e.g. consumer-credit aggregates), rescale to the site's canonical billions (÷ 1e3) so they combine correctly with other dollar series.",
      "Store points as-reported otherwise; any chart-level transform (year-over-year %, index) is applied at view time, not baked into the data.",
    ],
    caveats: [
      "Most FRED series are stored exactly as published — only the unit-scale normalization above is applied, and only where the source's stored unit says so.",
      "We use only the official keyless CSV (or the FRED API with a key); FRED's terms prohibit scraping or mirroring the catalog, so there is no bulk copy.",
    ],
    storedAs: "as published (dollar aggregates normalized to billions USD)",
    pipelineFile: "pipelines/fred_series.py",
    runCommand: "python pipelines/fred_series.py",
  },

  noaa_climate: {
    upstream: "NOAA National Centers for Environmental Information — Climate Data Online",
    access:
      "GET ncei.noaa.gov/cdo-web/api/v2/data (NOAA token header); GSOY (Global Summary of the Year) dataset, one long-record station per city",
    steps: [
      "For each major city's primary GHCND weather station (shown above), fetch annual GSOY records, paginated in decade-sized chunks to stay under the API's per-request cap.",
      "Take annual mean temperature and annual total precipitation for each year.",
      "Convert NOAA's metric reporting (tenths of °C, millimetres) to °F and inches.",
    ],
    caveats: [
      "Each city is one representative long-record (usually airport) station, registered to its metro area (MSA) so it appears under the metro picker — it is a station, not a metro-wide average.",
    ],
    storedAs: "°F (temperature), inches (precipitation)",
    pipelineFile: "pipelines/noaa_climate.py",
    runCommand: "python pipelines/noaa_climate.py",
  },

  fbi_crime: {
    upstream: "FBI Crime Data Explorer (Uniform Crime Reporting)",
    access:
      "GET cde.ucr.cjis.gov/LATEST/summarized/<geo>/<offense> — the keyless data-explorer backend — per state and nationally",
    steps: [
      "Fetch summarized monthly offense counts plus the population denominator for each year and offense (murder/homicide, violent, property).",
      "Sum the 12 monthly counts into an annual total per offense.",
      "Compute the rate per 100,000 people = annual count ÷ population × 100,000, which is the stored series.",
    ],
    caveats: [
      "Murder is the headline because it is the least sensitive to reporting differences; other offense categories can move with how diligently incidents are reported.",
      "Counts depend on which agencies reported to the FBI that year — participation gaps (notably some recent years) can shift rates independent of real change.",
      "The per-capita rate is stored; multiply by the population to recover the raw count.",
    ],
    storedAs: "offenses per 100,000 people",
    pipelineFile: "pipelines/fbi_crime.py",
    runCommand: "python pipelines/fbi_crime.py",
  },

  acs_cd: {
    upstream: "US Census Bureau — American Community Survey (ACS) 5-year estimates",
    access: "Census ACS API (Census API key); tract-level tables fetched per vintage",
    steps: [
      "Fetch tract-level ACS estimates for each vintage (2010-boundary tracts through 2021, 2020-boundary tracts from 2022 on).",
      "Aggregate tracts to stable 118th-Congress districts using population-weighted crosswalks (built from Census block-assignment + tract-relationship files), so every vintage lands on the same district boundaries.",
      "Counts (population, poverty, foreign-born, …) sum across each district's tracts; median household income is recomputed from the B19001 income-bin distribution for a true district-level median rather than an average of tract medians.",
      "Rate indicators (e.g. bachelor's-plus share) are derived as numerator ÷ universe × 100; the underlying count and universe are also kept as their own series.",
    ],
    caveats: [
      "Every vintage is mapped to current (118th-Congress) boundaries so a district is comparable over time — these are not the contemporaneous districts where lines have since changed.",
    ],
    storedAs: "people (counts), percent (derived rate indicators)",
    pipelineFile: "pipelines/census_acs_cd.py",
    runCommand: "CENSUS_API_KEY=<key> python pipelines/census_acs_cd.py",
  },
};

/**
 * Methodology for a source's `pipeline`, or null when the pipeline does a
 * plain fetch-and-store (no reproduce card needed — provenance covers it).
 */
export function getMethodology(
  pipeline: string | undefined | null,
): ProviderMethodology | null {
  if (!pipeline) return null;
  return METHODOLOGY[pipeline] ?? null;
}
