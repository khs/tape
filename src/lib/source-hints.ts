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
 *   search results when the query matches a series we cover at that
 *   level. Clicking one engages the relevant chip + clears the
 *   search, surfacing the actual sources. None of the chip names or
 *   counts mention specific cities/states/counties — the hint says
 *   "unemployment is also available by US state, click [State] to
 *   drill in," not "click here to see Chicago unemployment."
 *
 * Output shape:
 *   Each hint is a synthetic source-like object with:
 *     - id:          "_hint/<level>" — leading underscore keeps it
 *                    out of any "real source" listing and sorts last
 *                    alphabetically.
 *     - kind:        "hint" (not "timeseries") — composer dispatches
 *                    on this to render the hint card instead of an
 *                    add-as-chart button.
 *     - chip:        Which composer chip the click handler engages
 *                    ("metro" | "country" | "state" | "county" |
 *                    "cd" | "maps-tab"). The "maps-tab" target is
 *                    for tract / block-group hints, which point at
 *                    the Maps composer tab since we don't ship
 *                    individual tract/BG sources, only choropleths.
 *     - searchText:  Lowercased haystack the composer's filter
 *                    matches. Includes every series name available
 *                    at this level (so "unemployment" matches the
 *                    metro hint, the state hint, and so on) plus
 *                    level-name synonyms (so "msa" matches metro).
 *     - tags:        Empty — hints never get classified as geo via
 *                    a synthetic tag, so they pass every chip
 *                    filter trivially and only the text search
 *                    can hide them.
 *
 * Filtering: the composer's filteredSources() drops hints when the
 * query is empty (no value in cluttering an unprompted browse).
 * That guard lives at the call site, not here.
 */

import type { CollectionEntry } from "astro:content";
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

/** Geo levels we emit hints for. Order matters: this is the order
 *  hints render in the composer's search results when multiple
 *  match. National-larger-than-local feels intuitive scanning down
 *  the list. */
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
  /** Display name on the card. Intentionally generic — never includes
   *  a specific city/state/county name. */
  name: string;
  /** One-paragraph blurb describing what this level offers + how to
   *  surface it. Includes the count of distinct geographies and the
   *  series available at the level. */
  description: string;
  /** Lowercased, space-separated haystack for the composer's
   *  text-search filter. */
  searchText: string;
  /** Which chip / composer surface the click handler engages. */
  chip: HintChip;
  /** Per-hint sort order — lower = higher up in the results.
   *  Country first (broadest), then state, CD, metro, county, then
   *  the choropleth-only tract / BG. Matches HintLevel ordering. */
  order: number;
  /** Empty list. Hints intentionally never carry any geo tag —
   *  exposing them to chip filters would mean they DISAPPEAR
   *  whenever the user engages a chip, which is the opposite of
   *  what we want (a chip-engaged user doesn't need the hint, but
   *  no-chip user does). */
  tags: string[];
}

/** Level-name synonyms baked into the searchText so a user typing
 *  the level itself (not the series) still finds the hint. e.g.
 *  typing "msa" surfaces the metro hint even though our display
 *  copy calls it "metropolitan area." */
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
  tract: ["tract", "census-tract", "neighborhood", "choropleth", "map"],
  bg: ["block-group", "block group", "bg", "choropleth", "map"],
};

/**
 * Series-name aliases. The composer's search is substring-based, so
 * a few aliases drive matches we'd otherwise miss — e.g. "jobs"
 * surfaces payrolls, "income" surfaces median household income.
 * Keys are the canonical series name we detect from source names;
 * values are extra haystack tokens.
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
  case_shiller: ["housing", "home prices"],
  home_prices: ["housing", "real estate"],
};

/** Detect the series a source covers from its display name + ID.
 *  Returns null when nothing matches — that source won't contribute
 *  to any hint's series list. Heuristic but cheap; we only run this
 *  at build time. */
function detectSeries(name: string, id: string): string | null {
  const hay = (name + " " + id).toLowerCase();
  if (hay.includes("unemployment")) return "unemployment";
  if (hay.includes("payroll")) return "payrolls";
  if (hay.includes("population")) return "population";
  if (
    hay.includes("spending") ||
    hay.includes("outlays") ||
    hay.includes("usaspending")
  )
    return "spending";
  if (hay.includes("household") && hay.includes("income"))
    return "household_income";
  if (hay.includes("bachelor")) return "bachelors_degree";
  if (hay.includes("gdp")) return "gdp";
  if (hay.includes("cpi") || hay.includes("inflation")) return "cpi";
  if (hay.includes("case-shiller") || hay.includes("case shiller"))
    return "case_shiller";
  if (hay.includes("home price") || hay.includes("home listing"))
    return "home_prices";
  return null;
}

/** Human-readable series labels for the hint description copy. */
const SERIES_LABELS: Record<string, string> = {
  unemployment: "unemployment rates",
  payrolls: "nonfarm payrolls",
  population: "population",
  spending: "federal spending",
  household_income: "median household income",
  bachelors_degree: "share with a bachelor's degree",
  gdp: "GDP",
  cpi: "CPI inflation",
  case_shiller: "Case-Shiller home price index",
  home_prices: "home prices",
};

/** What level a source belongs to, derived from its tags + ID
 *  patterns. Returns null for national / non-geographic sources. */
function detectLevel(
  id: string,
  tags: ReadonlyArray<string>,
): HintLevel | null {
  if (tags.includes(METRO_TAG)) return "metro";
  if (tags.includes(COUNTY_TAG)) return "county";
  if (tags.includes(STATE_TAG)) return "state";
  if (tags.includes(CD_TAG)) return "cd";
  // Country sources carry `country-specific:<CODE>` for the per-
  // country drill-down. The umbrella COUNTRY_TAG is only on foreign-
  // country sources (US-national gets country-specific:USA without
  // COUNTRY_TAG; we exclude US from the country hint by checking
  // COUNTRY_TAG itself rather than the per-code tag).
  if (tags.includes(COUNTRY_TAG)) return "country";
  return null;
}

/** Order in which hints render in search results. */
const LEVEL_ORDER: Record<HintLevel, number> = {
  country: 0,
  state: 1,
  cd: 2,
  metro: 3,
  county: 4,
  tract: 5,
  bg: 6,
};

/** Click target for each level. */
const LEVEL_CHIP: Record<HintLevel, HintChip> = {
  country: "country",
  state: "cd", // The States & districts chip surfaces state + CD together
  cd: "cd",
  metro: "metro",
  county: "county", // No dedicated county chip yet; placeholder
  tract: "maps-tab",
  bg: "maps-tab",
};

/** Display copy for each level (used in name + description). */
const LEVEL_DISPLAY: Record<HintLevel, { name: string; chipLabel: string }> = {
  country: {
    name: "by country / region",
    chipLabel: "Regions and countries",
  },
  state: { name: "by US state", chipLabel: "States & districts" },
  cd: {
    name: "by congressional district",
    chipLabel: "States & districts",
  },
  metro: { name: "by metro (MSA)", chipLabel: "US metro areas" },
  county: { name: "by US county", chipLabel: "search the county name" },
  tract: {
    name: "by census tract (choropleth map)",
    chipLabel: "Maps tab",
  },
  bg: {
    name: "by census block group (choropleth map)",
    chipLabel: "Maps tab",
  },
};

/** Convenience type: just the fields synthesizeSourceHints reads.
 *  Lets tests pass a minimal mock instead of full CollectionEntry. */
export interface SourceMetaForHints {
  id: string;
  name: string;
  tags: ReadonlyArray<string>;
}

/**
 * Build the list of hint entries to inject into library.json.
 *
 * Inputs:
 *   sources — every (post-synthetic-tag) source in the manifest.
 *   tractLevelsAvailable — whether we ship tract + block-group
 *     choropleths. Read from the choropleth registry; defaults true
 *     so tests that don't pass it still emit both hints (the data
 *     exists in this repo).
 *
 * Algorithm:
 *   1. Group sources by (level, series).
 *   2. For each level with at least one detected series, emit one
 *      hint summarizing that level's coverage.
 *   3. Always emit tract + bg hints when tractLevelsAvailable is
 *      true — those don't have source entries to count, but we still
 *      want to surface the choropleth path.
 *
 * Pure + sync; safe to call at build time inside library.json.ts.
 */
export function synthesizeSourceHints(
  sources: ReadonlyArray<SourceMetaForHints>,
  tractLevelsAvailable: boolean = true,
): SourceHint[] {
  // (level → series → count) accumulator. The count is informational
  // (drives the description copy), but counts of 0 are still useful —
  // they let us emit hints for levels we cover even if no individual
  // source has a name we recognize.
  const byLevel = new Map<HintLevel, Map<string, number>>();
  // Distinct geographies per level — drives the "<N> tracked"
  // count in the description. e.g. for metro we want the count of
  // CBSAs, not the count of (CBSA × series) source rows.
  const distinctGeos = new Map<HintLevel, Set<string>>();
  for (const s of sources) {
    const level = detectLevel(s.id, s.tags);
    if (level == null) continue;
    const series = detectSeries(s.name, s.id);
    if (series == null) continue;
    let byS = byLevel.get(level);
    if (!byS) {
      byS = new Map();
      byLevel.set(level, byS);
    }
    byS.set(series, (byS.get(series) ?? 0) + 1);
    // Pull the geo identifier from the source ID. Cheap parsing —
    // we already have the parsers; reuse them to deduplicate.
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
      let set = distinctGeos.get(level);
      if (!set) {
        set = new Set();
        distinctGeos.set(level, set);
      }
      set.add(geoKey);
    }
  }

  const hints: SourceHint[] = [];
  // Real-data hints (country / state / cd / metro / county).
  for (const [level, seriesMap] of byLevel) {
    const seriesList = [...seriesMap.keys()];
    if (seriesList.length === 0) continue;
    const display = LEVEL_DISPLAY[level];
    const labels = seriesList
      .map((s) => SERIES_LABELS[s] ?? s.replace(/_/g, " "))
      .sort();
    const geoCount = distinctGeos.get(level)?.size ?? 0;
    const countPhrase =
      geoCount > 0
        ? `${geoCount.toLocaleString()} tracked. `
        : "";
    const chipCopy =
      level === "county"
        ? // Deliberately no example county here — the hint's whole
          // point is to avoid naming any specific geography. Keep
          // this consistent with the test that scans for leaked
          // city/state names.
          "Type the county name in the search field to surface."
        : `Click the ${display.chipLabel} chip to drill in.`;
    const description =
      `Available ${display.name}: ${joinWithAnd(labels)}. ` +
      countPhrase +
      chipCopy;
    const aliasTokens = seriesList.flatMap((s) => SERIES_ALIASES[s] ?? []);
    const searchText = [
      ...seriesList,
      ...labels.map((l) => l.toLowerCase()),
      ...aliasTokens,
      ...LEVEL_SYNONYMS[level],
      "available",
      "by",
    ]
      .join(" ")
      .toLowerCase();
    hints.push({
      id: `_hint/${level}`,
      kind: "hint",
      name: `More data — ${display.name}`,
      description,
      searchText,
      chip: LEVEL_CHIP[level],
      order: LEVEL_ORDER[level],
      tags: [],
    });
  }
  // Tract + block-group choropleth hints (no source rows, hand-
  // emitted when those levels are available).
  if (tractLevelsAvailable) {
    for (const level of ["tract", "bg"] as const) {
      const display = LEVEL_DISPLAY[level];
      const description =
        level === "tract"
          ? "Census-tract-level data (ACS demographics, population, education) — rendered as choropleth maps. Open the Maps tab in the composer to add one."
          : "Block-group-level data (ACS demographics, population, education) — rendered as choropleth maps. Block groups are smaller than tracts, useful for very local stories. Open the Maps tab in the composer to add one.";
      const searchText = [
        "population",
        "demographics",
        "education",
        "bachelors degree",
        "household income",
        "acs",
        "census",
        ...LEVEL_SYNONYMS[level],
        "available",
        "by",
      ]
        .join(" ")
        .toLowerCase();
      hints.push({
        id: `_hint/${level}`,
        kind: "hint",
        name: `More data — ${display.name}`,
        description,
        searchText,
        chip: LEVEL_CHIP[level],
        order: LEVEL_ORDER[level],
        tags: [],
      });
    }
  }
  hints.sort((a, b) => a.order - b.order);
  return hints;
}

/** Format a list of strings as "a, b, and c" (Oxford comma).
 *  Pulled inline rather than imported from a util — keeps this
 *  module self-contained. */
function joinWithAnd(items: ReadonlyArray<string>): string {
  if (items.length === 0) return "";
  if (items.length === 1) return items[0];
  if (items.length === 2) return `${items[0]} and ${items[1]}`;
  return `${items.slice(0, -1).join(", ")}, and ${items[items.length - 1]}`;
}

/** Adapter for the library.json caller — it has full CollectionEntry
 *  objects + the synthetics it just computed. Lets the call site
 *  hand over its real shape without restructuring. */
export function hintsFromLibrary(
  entries: ReadonlyArray<{
    id: string;
    name: string;
    tags: ReadonlyArray<string>;
  }>,
  tractLevelsAvailable: boolean = true,
): SourceHint[] {
  return synthesizeSourceHints(entries, tractLevelsAvailable);
}

// Re-export the CollectionEntry shape for callers that want it.
export type SourceEntry = CollectionEntry<"sources">;
