/**
 * Regression guard for the "foreign country source leaks into the default
 * source list" class of bug.
 *
 * The source picker hides per-country sources behind the "Countries &
 * regions" chip by synthesizing COUNTRY_TAG from parseCountrySourceId in the
 * library manifest. If a per-country provider's id prefix is missing from
 * that parser, every one of its sources silently shows up in the default
 * list (this happened to owid_co2, owid_energy, and countries_gdp). This
 * test walks the real source tree and asserts that every source under a
 * per-country provider is parser-recognized — except the USA + World
 * entities, which stay visible by deliberate convention.
 */
import { describe, it, expect } from "vitest";
import { sourceIds } from "./corpus";
import { parseCountrySourceId } from "../src/lib/countries";

// Providers whose sources are each about a specific foreign country / region.
const COUNTRY_PROVIDERS = [
  "countries/",
  "countries_gdp/",
  "countries_relative/",
  "oecd/",
  "owid_co2/",
  "owid_energy/",
  "worldbank_gdp_raw/",
  "worldbank_extended/",
  "treasury_tic/",
];

// Entities that intentionally STAY in the default list (parseCountrySourceId
// returns null for them on purpose, since the audience is US-focused): the
// USA itself, the World aggregate, and treasury_tic's grand_total. Matches
// the token whether it sits at the end of the id (countries_gdp/usa,
// owid_co2/co2_world) or as the iso3 prefix (oecd/usa_cpi_yoy).
const STAYS_VISIBLE = /(?:^|\/|_)(usa|world|united_states|grand_total)(?:_|$)/;

describe("no foreign country source leaks into the default list", () => {
  it("every per-country provider source is parser-recognized (or a visible US/World entity)", () => {
    const leaks: string[] = [];
    for (const id of sourceIds()) {
      if (!COUNTRY_PROVIDERS.some((p) => id.startsWith(p))) continue;
      if (STAYS_VISIBLE.test(id)) continue;
      if (!parseCountrySourceId(id)) leaks.push(id);
    }
    expect(
      leaks,
      `These per-country sources are NOT hidden behind the geo chip (add their ` +
        `provider prefix to parseCountrySourceId in src/lib/countries.ts):\n` +
        leaks.sort().join("\n"),
    ).toEqual([]);
  });
});
