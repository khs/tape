/**
 * "Did you mean this geographic level?" hint entries injected into
 * library.json.
 *
 * Why these exist:
 *   The composer's default Sources tab hides per-geography series
 *   behind their drill-down chips — typing "unemployment" surfaces
 *   only the US national rate, not the 393 metros / 51 states / 8
 *   counties / 6 foreign countries we also have unemployment data
 *   for. The chip-hide is correct (no one wants 393 metros dumped
 *   into the same list as the national series), but it leaves a
 *   discoverability gap: a first-time visitor has no way to know
 *   the local data exists unless they happen to engage the right
 *   chip first.
 *
 *   The hints are synthetic "see also" cards that show up in the
 *   search results when the query matches a SPECIFIC series we
 *   cover at that level. Clicking one engages the relevant chip +
 *   clears the search, surfacing the actual sources. None of the
 *   hint copy mentions specific cities/states/counties — the hint
 *   says "Unemployment rate — by US metro area," not "click here
 *   to see Chicago unemployment."
 *
 *   One hint per (series, level): so a user searching "home prices"
 *   gets "Case-Shiller home price index — by MSA" + "Median home
 *   listing price — by MSA," not a mega-hint listing every series
 *   the metro level happens to cover. That matches how users think
 *   about the catalog ("does this data exist for my topic at this
 *   geographic granularity?") rather than how it's pipeline-organized.
 *
 * Output shape:
 *   Each hint is a synthetic source-like object with:
 *     - id:          "_hint/<level>__<series>" — leading underscore
 *                    keeps it out of any "real source" listing.
 *     - kind:        "hint" — composer dispatches on this to render
 *                    the hint card instead of an add-as-chart button.
 *     - chip:        Which composer chip the click handler engages
 *                    ("metro" | "country" | "state" | "county" |
 *                    "cd" | "maps-tab"). "maps-tab" handles tract /
 *                    block-group hints since those levels are
 *                    map-only.
 *     - searchText:  Lowercased haystack the composer's filter
 *                    matches. Includes the series name, series
 *                    aliases (jobs → payrolls), and level-name
 *                    synonyms (msa → metro).
 *     - tags:        Empty — hints never get classified as geo via
 *                    a synthetic tag, so they pass every chip
 *                    filter trivially.
 *
 * Filtering: the composer's filteredSources() drops hints when the
 * query is empty (no value in cluttering an unprompted browse).
 * That guard lives at the call site, not here.
 */

import { COUNTY_TAG } from "./county-sources";
import { COUNTRY_TAG } from "./countries";
import { METRO_TAG } from "./geographic-regions";
import { CD_TAG, STATE_TAG } from "./congressional-districts";
import { parseMetroSourceId } from "./geographic-regions";
import { parseStateSourceId, parseCdSourceId } from "./congressional-districts";
import { parseCountySourceId } from "./county-sources";
import { parseCountrySourceId } from "./countries";

/**
 * The chip / surface a hint click should engage. "maps-tab" handles
 * the tract + block-group cases where there's no per-source picker —
 * the user has to switch composer tabs entirely to surface the data.
 */
export type HintChip =
  | "metro"
  | "country"
  | "state"
  | "county"
  | "cd"
  | "maps-tab";

/** Geo levels we emit hints for. Order matters for the sort; lower
 *  index = renders higher in the search results. */
export type HintLevel =
  | "country"
  | "state"
  | "cd"
  | "metro"
  | "county"
  | "tract"
  | "bg";

export interface SourceHint {
  id: string;
  kind: "hint";
  /** Display name on the card — pattern: "<Series label> — by
   *  <level name>". Intentionally generic; never includes a
   *  specific city / state / county name. */
  name: string;
  /** Short blurb describing what the series IS + at what geographic
   *  granularity + how to surface it. No specific geo names. */
  description: string;
  /** Lowercased haystack for the composer's text-search filter. */
  searchText: string;
  /** Which chip / composer surface the click handler engages. */
  chip: HintChip;
  /** Sort key: pure level priority (LEVEL_ORDER). Ties broken by
   *  alphabetical name compare at the call site — keeps level
   *  ordering primary while reading naturally within a level. */
  order: number;
  /** Empty list. Hints intentionally never carry any geo tag —
   *  exposing them to chip filters would mean they DISAPPEAR
   *  whenever the user engages a chip, which is the opposite of
   *  what we want. */
  tags: string[];
}

/** Level-name synonyms baked into the searchText so a user typing
 *  the level itself (not the series) still finds the hint. */
const LEVEL_SYNONYMS: Record<HintLevel, string[]> = {
  country: ["country", "international", "world", "foreign", "global"],
  state: ["state", "statewide", "us-state"],
  cd: [
    "congressional",
    "district",
    "cd",
    "house",
    "representative",
    "us-cd",
  ],
  metro: ["metro", "msa", "metropolitan", "city", "urban"],
  county: ["county", "counties", "dmv", "local"],
  tract: ["tract", "census-tract", "neighborhood", "map", "map"],
  bg: ["block-group", "block group", "bg", "map", "map"],
};

/**
 * Series-name aliases. The composer's search is substring-based, so
 * aliases drive matches we'd otherwise miss — e.g. "jobs" surfaces
 * payrolls + unemployment, "income" surfaces median household income.
 */
const SERIES_ALIASES: Record<string, string[]> = {
  unemployment: ["jobs", "labor", "joblessness"],
  payrolls: ["jobs", "employment", "labor"],
  population: ["demographics", "people"],
  spending: ["outlays", "budget", "federal"],
  household_income: ["income", "median", "household"],
  bachelors_degree: ["education", "college", "bachelors"],
  gdp: ["output", "economy", "growth"],
  cpi: ["inflation", "prices"],
  case_shiller: ["housing", "home prices", "homes"],
  home_prices: ["housing", "real estate", "listings", "home prices"],
  poverty_rate: ["poverty", "income"],
  foreign_born: ["foreign-born", "immigrant", "demographics"],
};

/** Human-readable series labels — what appears in the hint name +
 *  description. The pattern is "<noun phrase that names the
 *  series>" — case-cleaned at hint-build time. */
const SERIES_LABELS: Record<string, string> = {
  unemployment: "Unemployment rate",
  payrolls: "Nonfarm payroll employment",
  population: "Population",
  spending: "Federal spending",
  household_income: "Median household income",
  bachelors_degree: "Share with a bachelor's degree",
  gdp: "GDP",
  cpi: "CPI inflation",
  case_shiller: "Case-Shiller home price index",
  home_prices: "Median home listing price",
  poverty_rate: "Poverty rate",
  foreign_born: "Foreign-born population",
};

/** Short series descriptions — paired with the level name + count
 *  to build each hint's description string. Same words you'd see
 *  on a real source's YAML description, minus the geo specifics. */
const SERIES_DESCRIPTIONS: Record<string, string> = {
  unemployment: "Headline unemployment rate, monthly, from BLS LAUS",
  payrolls: "Nonfarm payroll employment, monthly, from BLS CES",
  population: "Total resident population",
  spending: "Federal outlays, annual, from USAspending",
  household_income: "Median household income (current dollars), annual",
  bachelors_degree:
    "Share of adults 25+ with a bachelor's degree or higher, ACS 5-year estimates",
  gdp: "Gross domestic product (current USD), annual, from the World Bank",
  cpi: "Consumer price index, annual % change",
  case_shiller: "S&P/Case-Shiller home price index, monthly, from FRED",
  home_prices:
    "Median single-family home listing price, monthly, from FRED/Realtor.com",
  poverty_rate: "Share of population below the federal poverty line, ACS",
  foreign_born:
    "Share of residents born outside the United States, ACS",
};

/** Detect the series a source covers from its display name + ID.
 *  Returns null when nothing matches — that source won't contribute
 *  to any hint. */
function detectSeries(name: string, id: string): string | null {
  const hay = (name + " " + id).toLowerCase();
  if (hay.includes("unemployment")) return "unemployment";
  if (hay.includes("payroll")) return "payrolls";
  if (hay.includes("case-shiller") || hay.includes("case shiller"))
    return "case_shiller";
  if (
    hay.includes("median home listing") ||
    hay.includes("home listing") ||
    (hay.includes("home price") && !hay.includes("case-shiller"))
  )
    return "home_prices";
  if (hay.includes("household") && hay.includes("income"))
    return "household_income";
  if (hay.includes("bachelor")) return "bachelors_degree";
  if (hay.includes("gdp")) return "gdp";
  if (hay.includes("cpi") || hay.includes("inflation")) return "cpi";
  if (hay.includes("poverty")) return "poverty_rate";
  if (hay.includes("foreign-born") || hay.includes("foreign born"))
    return "foreign_born";
  if (
    hay.includes("spending") ||
    hay.includes("outlays") ||
    hay.includes("usaspending")
  )
    return "spending";
  if (hay.includes("population")) return "population";
  return null;
}

/** What level a source belongs to, derived from its tags.
 *  Returns null for national / non-geographic sources. */
function detectLevel(
  tags: ReadonlyArray<string>,
): HintLevel | null {
  if (tags.includes(METRO_TAG)) return "metro";
  if (tags.includes(COUNTY_TAG)) return "county";
  if (tags.includes(STATE_TAG)) return "state";
  if (tags.includes(CD_TAG)) return "cd";
  if (tags.includes(COUNTRY_TAG)) return "country";
  return null;
}

const LEVEL_ORDER: Record<HintLevel, number> = {
  country: 0,
  state: 1,
  cd: 2,
  metro: 3,
  county: 4,
  tract: 5,
  bg: 6,
};

const LEVEL_CHIP: Record<HintLevel, HintChip> = {
  country: "country",
  state: "cd",
  cd: "cd",
  metro: "metro",
  county: "county",
  tract: "maps-tab",
  bg: "maps-tab",
};

const LEVEL_DISPLAY: Record<
  HintLevel,
  { name: string; chipLabel: string; geoNoun: string }
> = {
  country: {
    name: "country / region",
    chipLabel: "Regions and countries",
    geoNoun: "country",
  },
  state: {
    name: "US state",
    chipLabel: "States & districts",
    geoNoun: "state",
  },
  cd: {
    name: "congressional district",
    chipLabel: "States & districts",
    geoNoun: "district",
  },
  metro: {
    name: "US metro area (MSA)",
    chipLabel: "US metro areas",
    geoNoun: "metro area",
  },
  county: {
    name: "US county",
    chipLabel: "search the county name",
    geoNoun: "county",
  },
  tract: {
    name: "census tract",
    chipLabel: "Maps tab",
    geoNoun: "tract",
  },
  bg: {
    name: "census block group",
    chipLabel: "Maps tab",
    geoNoun: "block group",
  },
};

/** Map-only levels: tract and block group. We don't ship
 *  per-source rows for these (they're maps, not time
 *  series), so we hand-list the series available rather than
 *  detecting them from a sources iteration. */
const CHOROPLETH_SERIES: Record<"tract" | "bg", ReadonlyArray<string>> = {
  // From src/content/charts/state-tract-maps/ — 50 states × 4 indicators each.
  tract: ["bachelors_degree", "foreign_born", "household_income", "poverty_rate"],
  // From src/content/charts/state-bg-maps/ — block groups are a finer
  // geography that ACS only publishes for a subset of indicators.
  bg: ["bachelors_degree", "household_income"],
};

/** Convenience type: just the fields synthesizeSourceHints reads. */
export interface SourceMetaForHints {
  id: string;
  name: string;
  tags: ReadonlyArray<string>;
}

/**
 * Build the list of hint entries to inject into library.json. One
 * hint per (level, series) pair we detect, plus the hand-listed
 * tract + bg map hints.
 *
 * `mapLevelsAvailable` defaults true; pass false in tests
 * that want only the real-data hints.
 */
export function synthesizeSourceHints(
  sources: ReadonlyArray<SourceMetaForHints>,
  mapLevelsAvailable: boolean = true,
): SourceHint[] {
  // (level, series) → distinct geos. Drives the per-level count
  // in the description.
  const counts = new Map<string, Set<string>>();
  // (level, series) → true once we've seen at least one source.
  // Distinct from counts because some sources (e.g. fred/dc_payrolls
  // before the metro-override was added) don't parse to a geo id but
  // do contribute a (level, series) signal.
  const seen = new Map<string, { level: HintLevel; series: string }>();

  for (const s of sources) {
    const level = detectLevel(s.tags);
    if (level == null) continue;
    const series = detectSeries(s.name, s.id);
    if (series == null) continue;
    const key = `${level}::${series}`;
    seen.set(key, { level, series });
    let geoKey: string | null = null;
    if (level === "metro") {
      const p = parseMetroSourceId(s.id);
      if (p) geoKey = p.cbsa;
    } else if (level === "state") {
      const p = parseStateSourceId(s.id);
      if (p) geoKey = p.state;
    } else if (level === "cd") {
      const p = parseCdSourceId(s.id);
      if (p) geoKey = `${p.state}/${p.district}`;
    } else if (level === "county") {
      const p = parseCountySourceId(s.id);
      if (p) geoKey = `${p.state}/${p.countyName}`;
    } else if (level === "country") {
      const p = parseCountrySourceId(s.id);
      if (p) geoKey = p.code;
    }
    if (geoKey != null) {
      let set = counts.get(key);
      if (!set) {
        set = new Set();
        counts.set(key, set);
      }
      set.add(geoKey);
    }
  }

  const hints: SourceHint[] = [];
  for (const [key, { level, series }] of seen) {
    const count = counts.get(key)?.size ?? 0;
    hints.push(buildHint(level, series, count));
  }
  if (mapLevelsAvailable) {
    for (const level of ["tract", "bg"] as const) {
      for (const series of CHOROPLETH_SERIES[level]) {
        // Count placeholder: 50 (all states ship these). We don't
        // actually iterate the map chart YAMLs to derive a
        // real count — too tied to the per-state file layout — but
        // 50 is honest enough for the hint copy.
        hints.push(buildHint(level, series, 50));
      }
    }
  }
  // Sort: level priority first (so all unemployment hints group
  // country → state → cd → metro → county); within a level,
  // alphabetical by name so search results stack readably.
  hints.sort((a, b) => {
    if (a.order !== b.order) return a.order - b.order;
    return a.name.localeCompare(b.name);
  });
  return hints;
}

/** Build a single hint entry from a (level, series, count) tuple.
 *  Pulls all human-readable copy from SERIES_LABELS / SERIES_DESCRIPTIONS
 *  / LEVEL_DISPLAY so the structure stays consistent across hints. */
function buildHint(
  level: HintLevel,
  series: string,
  count: number,
): SourceHint {
  const label = SERIES_LABELS[series] ?? series.replace(/_/g, " ");
  const desc = SERIES_DESCRIPTIONS[series] ?? "";
  const display = LEVEL_DISPLAY[level];
  // English plural for the count phrase. "country" → "countries"
  // is the only awkward case; everything else takes a trailing s.
  const pluralNoun =
    display.geoNoun === "country"
      ? "countries"
      : `${display.geoNoun}s`;
  const countPhrase =
    count > 0
      ? ` ${count.toLocaleString()} ${count === 1 ? display.geoNoun : pluralNoun} tracked.`
      : "";
  const chipCopy =
    level === "county"
      ? "Type the county name in the search field to surface."
      : level === "tract" || level === "bg"
        ? "Open the Maps tab in the composer to add one."
        : `Click the ${display.chipLabel} chip to drill in.`;
  // The description's "Available for each <level>" uses the full
  // level-name string (e.g. "US state", "US metro area (MSA)") —
  // the geoNoun is only for the count phrase below where the
  // determiner already established the level. "Available for each
  // state" reads ambiguously without the country qualifier.
  const description = desc
    ? `${desc}. Available for each ${display.name}.${countPhrase} ${chipCopy}`
    : `Available for each ${display.name}.${countPhrase} ${chipCopy}`;
  // Sort key: level priority. Series alphabetical is the secondary
  // sort handled by the caller's comparator after order matches —
  // we don't try to fold it into a single numeric here because
  // character-code arithmetic across mixed string lengths overflows
  // the level-priority gap and reorders levels.
  const order = LEVEL_ORDER[level];
  const aliasTokens = SERIES_ALIASES[series] ?? [];
  const searchText = [
    series,
    label.toLowerCase(),
    desc.toLowerCase(),
    ...aliasTokens,
    ...LEVEL_SYNONYMS[level],
    "available",
    "by",
  ]
    .join(" ")
    .toLowerCase();
  return {
    id: `_hint/${level}__${series}`,
    kind: "hint",
    name: `${label} — by ${display.name}`,
    description,
    searchText,
    chip: LEVEL_CHIP[level],
    order,
    tags: [],
  };
}
