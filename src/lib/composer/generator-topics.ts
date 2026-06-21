/**
 * Topic grouping for the composer's Generators tab.
 *
 * The generators catalog (public/generators-index.json) is a flat per-locality
 * list of templates. Readers want related indicators together — every water
 * withdrawal in one group, every NAEP score in another, etc. Rather than a
 * hand-maintained list per locality level (which goes stale the moment a new
 * provider ships), topicForTemplate classifies a template by id PATTERN, so a
 * new `usgs_water_*` or `naep_*` template lands in the right group automatically.
 * Revisit the patterns only when a genuinely new subject area arrives.
 *
 * Used by generators.ts to render the template <select> as <optgroup>s.
 */

export interface TopicGroup {
  id: string;
  label: string;
}

/** Display order of the groups in the dropdown. */
export const GENERATOR_TOPICS: readonly TopicGroup[] = [
  { id: "population", label: "Population & demographics" },
  { id: "income", label: "Income & poverty" },
  { id: "housing", label: "Housing" },
  { id: "labor", label: "Labor & jobs" },
  { id: "education", label: "Education" },
  { id: "health", label: "Health & mortality" },
  { id: "water", label: "Water use" },
  { id: "energy", label: "Energy" },
  { id: "agriculture", label: "Agriculture" },
  { id: "government", label: "Government & fiscal" },
  { id: "other", label: "Other" },
];

/**
 * Map a generator template id to a topic id. Order matters: the first matching
 * rule wins, so narrower subjects (water, education) are tested before broader
 * ones (labor, population). Falls back to "other".
 */
export function topicForTemplate(id: string): string {
  const s = id.toLowerCase();
  const has = (...needles: string[]) => needles.some((n) => s.includes(n));

  if (has("usgs_water")) return "water";
  if (has("usda_nass")) return "agriculture";
  if (has("eia_")) return "energy";
  if (has("naep", "edu_spending", "bachelors", "masters")) return "education";
  if (has("cdc_health", "uninsured", "insurance_universe", "disability"))
    return "health";
  if (
    has(
      "zillow", "building_permits", "median_home_value", "median_gross_rent",
      "median_year_built", "owner_occupied", "renter_occupied", "broadband",
      "no_vehicle", "total_vehicle",
    )
  )
    return "housing";
  if (has("census_govfin", "usaspending", "taxrev", "business_apps", "govemp"))
    return "government";
  if (
    has(
      "bls_", "acs_labor", "payrolls", "unemploy", "labor_force", "workers_",
      "commute", "wfh", "emp_pop", "lfpr", "employed", "industry",
    )
  )
    return "labor";
  if (
    has(
      "median_hh_income", "households_above", "households_below",
      "households_total_income", "gini", "poverty",
    )
  )
    return "income";
  if (
    has(
      "population", "median_age", "foreign_born", "veterans", "movers",
      "born_same_state", "mobility", "under_18", "65_plus",
    )
  )
    return "population";
  return "other";
}
