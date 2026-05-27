/**
 * Tests for source-filters.ts — the helper logic that gates which
 * sources show up in every source-picker UI.
 *
 * These functions used to live as closures inside compose.astro,
 * untested. Lifting them to a lib + locking down the matrix here
 * means the (chip-active, query, source-tags) combinatorics can't
 * silently drift the next time a rendering refactor touches them.
 *
 * The test fixtures use the real lib helpers (METRO_TAG,
 * COUNTRY_TAG, CD_TAG, STATE_TAG, COUNTY_TAG) so a rename in any
 * of those propagates a test failure rather than silent passes.
 */
import { describe, it, expect } from "vitest";
import {
  passesMetroFilter,
  passesCountryFilter,
  passesCdFilter,
  passesCountyFilter,
  unlockedStatesForQuery,
  unlockedMetrosForQuery,
  unlockedCountriesForQuery,
  UNLOCK_QUERY_MIN_CHARS,
  type SourceFiltersLibrary,
} from "./source-filters";
import { METRO_TAG } from "./geographic-regions";
import { COUNTRY_TAG } from "./countries";
import { CD_TAG, STATE_TAG, STATEWIDE_DISTRICT_CODE } from "./congressional-districts";
import { COUNTY_TAG } from "./county-sources";

const SAMPLE_LIB: SourceFiltersLibrary = {
  metros: {
    "10180": { shortName: "Abilene", name: "Abilene, TX" },
    "12060": { shortName: "Atlanta", name: "Atlanta-Sandy Springs, GA" },
    "14460": { shortName: "Boston", name: "Boston-Cambridge, MA-NH" },
  },
  countries: {
    AUS: { name: "Australia" },
    CAN: { name: "Canada" },
    JPN: { name: "Japan" },
    EUU: { name: "European Union" },
  },
};

describe("unlockedStatesForQuery", () => {
  it("returns null for queries below the 4-char threshold", () => {
    expect(unlockedStatesForQuery("")).toBeNull();
    expect(unlockedStatesForQuery("tex")).toBeNull();
    expect(unlockedStatesForQuery("ca")).toBeNull();
  });

  it("matches a state name (case-insensitive); state codes are lowercase", () => {
    // US_STATES code field is lowercase (matches pipeline-emitted IDs).
    const result = unlockedStatesForQuery("Texas");
    expect(result).not.toBeNull();
    expect(result?.has("tx")).toBe(true);
  });

  it("matches lowercase queries against state names", () => {
    const result = unlockedStatesForQuery("texas");
    expect(result?.has("tx")).toBe(true);
  });

  it("matches substrings of state names", () => {
    // "york" matches New York
    const result = unlockedStatesForQuery("york");
    expect(result?.has("ny")).toBe(true);
  });

  it("matches multiple states when the query hits more than one", () => {
    // "new" matches New Hampshire, New Jersey, New Mexico, New York
    const result = unlockedStatesForQuery("new ");
    expect(result?.size).toBeGreaterThan(1);
    expect(result?.has("ny")).toBe(true);
    expect(result?.has("nj")).toBe(true);
  });

  it("returns null when no state matches", () => {
    expect(unlockedStatesForQuery("xyzzy")).toBeNull();
  });

  it("UNLOCK_QUERY_MIN_CHARS is 4 (lockdown for the constant value)", () => {
    expect(UNLOCK_QUERY_MIN_CHARS).toBe(4);
  });
});

describe("unlockedMetrosForQuery", () => {
  it("returns null below the 4-char threshold", () => {
    expect(unlockedMetrosForQuery("Abi", SAMPLE_LIB)).toBeNull();
    expect(unlockedMetrosForQuery("Atl", SAMPLE_LIB)).toBeNull();
  });

  it("matches a metro's shortName + returns the tag-formatted code", () => {
    const result = unlockedMetrosForQuery("Abilene", SAMPLE_LIB);
    expect(result?.has(`${METRO_TAG}:10180`)).toBe(true);
  });

  it("matches a metro's full name", () => {
    // Atlanta-Sandy Springs has "Sandy Springs" in the full name.
    const result = unlockedMetrosForQuery("Sandy", SAMPLE_LIB);
    expect(result?.has(`${METRO_TAG}:12060`)).toBe(true);
  });

  it("returns null when no metro matches", () => {
    expect(unlockedMetrosForQuery("Xeno", SAMPLE_LIB)).toBeNull();
  });

  it("returns null when lib.metros is missing", () => {
    expect(unlockedMetrosForQuery("Abilene", {})).toBeNull();
  });
});

describe("unlockedCountriesForQuery", () => {
  it("returns null below the 4-char threshold", () => {
    expect(unlockedCountriesForQuery("Aus", SAMPLE_LIB)).toBeNull();
  });

  it("matches a country name (case-insensitive)", () => {
    const result = unlockedCountriesForQuery("Australia", SAMPLE_LIB);
    expect(result?.has(`${COUNTRY_TAG}:AUS`)).toBe(true);
  });

  it("matches a region name", () => {
    const result = unlockedCountriesForQuery("European", SAMPLE_LIB);
    expect(result?.has(`${COUNTRY_TAG}:EUU`)).toBe(true);
  });

  it("returns null when no country matches", () => {
    expect(unlockedCountriesForQuery("Xyzlandia", SAMPLE_LIB)).toBeNull();
  });

  it("returns null when lib.countries is missing", () => {
    expect(unlockedCountriesForQuery("Australia", {})).toBeNull();
  });
});

describe("passesMetroFilter", () => {
  describe("chip active (selectedCbsa set)", () => {
    it("keeps sources with the matching metro:<cbsa> tag", () => {
      const tags = [METRO_TAG, `${METRO_TAG}:10180`, "labor"];
      expect(passesMetroFilter(tags, "10180", "", SAMPLE_LIB)).toBe(true);
    });

    it("drops sources with a different metro tag", () => {
      const tags = [METRO_TAG, `${METRO_TAG}:12060`];
      expect(passesMetroFilter(tags, "10180", "", SAMPLE_LIB)).toBe(false);
    });

    it("drops non-metro sources when a CBSA is active", () => {
      const tags = ["macro", "rates"];
      expect(passesMetroFilter(tags, "10180", "", SAMPLE_LIB)).toBe(false);
    });

    it("ignores the query when a CBSA is explicitly active", () => {
      // Even if the query "matches" another metro, an active chip
      // overrides — the user picked THIS metro, show only that.
      const tags = [METRO_TAG, `${METRO_TAG}:12060`];
      expect(
        passesMetroFilter(tags, "10180", "Atlanta", SAMPLE_LIB),
      ).toBe(false);
    });
  });

  describe("chip inactive (selectedCbsa null)", () => {
    it("non-metro sources always pass", () => {
      const tags = ["macro", "rates", "fred"];
      expect(passesMetroFilter(tags, null, "", SAMPLE_LIB)).toBe(true);
      expect(passesMetroFilter(tags, null, "anything", SAMPLE_LIB)).toBe(true);
    });

    it("metro-tagged sources are HIDDEN without a query", () => {
      const tags = [METRO_TAG, `${METRO_TAG}:10180`];
      expect(passesMetroFilter(tags, null, "", SAMPLE_LIB)).toBe(false);
    });

    it("metro-tagged sources unlock via a name-matching query", () => {
      const tags = [METRO_TAG, `${METRO_TAG}:10180`];
      expect(passesMetroFilter(tags, null, "Abilene", SAMPLE_LIB)).toBe(true);
    });

    it("metro-tagged sources stay hidden for short queries (< 4 chars)", () => {
      // "Abi" is below the threshold even though it'd match.
      const tags = [METRO_TAG, `${METRO_TAG}:10180`];
      expect(passesMetroFilter(tags, null, "Abi", SAMPLE_LIB)).toBe(false);
    });

    it("metro-tagged sources stay hidden when the query matches a DIFFERENT metro", () => {
      const tags = [`${METRO_TAG}:10180`];
      // "Atlanta" unlocks 12060, not 10180 — Abilene source still hidden.
      expect(passesMetroFilter(tags, null, "Atlanta", SAMPLE_LIB)).toBe(false);
    });

    it("recognizes sources with ONLY a per-CBSA tag (no umbrella METRO_TAG)", () => {
      // Zillow et al. — the umbrella was missing in older code; check
      // we don't false-pass these as "non-metro" without a query.
      const tags = [`${METRO_TAG}:10180`, "real-estate"];
      expect(passesMetroFilter(tags, null, "", SAMPLE_LIB)).toBe(false);
    });
  });
});

describe("passesCountryFilter", () => {
  describe("chip active (selectedCountryCode set)", () => {
    it("keeps sources with the matching country tag", () => {
      const tags = [COUNTRY_TAG, `${COUNTRY_TAG}:AUS`];
      expect(passesCountryFilter(tags, "AUS", "", SAMPLE_LIB)).toBe(true);
    });

    it("drops sources for a different country", () => {
      const tags = [COUNTRY_TAG, `${COUNTRY_TAG}:CAN`];
      expect(passesCountryFilter(tags, "AUS", "", SAMPLE_LIB)).toBe(false);
    });

    it("drops non-country sources", () => {
      const tags = ["macro"];
      expect(passesCountryFilter(tags, "AUS", "", SAMPLE_LIB)).toBe(false);
    });
  });

  describe("chip inactive (selectedCountryCode null)", () => {
    it("non-country sources always pass", () => {
      expect(passesCountryFilter(["macro"], null, "", SAMPLE_LIB)).toBe(true);
    });

    it("country sources hidden without a name-matching query", () => {
      const tags = [COUNTRY_TAG, `${COUNTRY_TAG}:AUS`];
      expect(passesCountryFilter(tags, null, "", SAMPLE_LIB)).toBe(false);
      expect(passesCountryFilter(tags, null, "Aus", SAMPLE_LIB)).toBe(false);
    });

    it("country sources unlock via a ≥ 4-char name-matching query", () => {
      const tags = [COUNTRY_TAG, `${COUNTRY_TAG}:AUS`];
      expect(passesCountryFilter(tags, null, "Australia", SAMPLE_LIB)).toBe(true);
    });

    it("query matching a different country doesn't leak others through", () => {
      const tags = [COUNTRY_TAG, `${COUNTRY_TAG}:AUS`];
      expect(passesCountryFilter(tags, null, "Canada", SAMPLE_LIB)).toBe(false);
    });
  });
});

describe("passesCdFilter", () => {
  describe("chip inactive (cdState null)", () => {
    it("non-geo sources always pass", () => {
      expect(passesCdFilter("fred/cpi", ["macro"], null, null, "")).toBe(true);
    });

    it("CD sources hidden without a state-matching query", () => {
      const tags = [CD_TAG];
      expect(
        passesCdFilter("government/va_08_outlays", tags, null, null, ""),
      ).toBe(false);
      expect(
        passesCdFilter("government/va_08_outlays", tags, null, null, "Virg"),
      ).toBe(false);
    });

    it("CD sources unlock via a ≥ 4-char state-name query", () => {
      // CD source IDs follow `usaspending/district_<st>_<dst>` or
      // `acs_cd/<series>_<st>_<dst>` — see parseCdSourceId.
      const tags = [CD_TAG];
      expect(
        passesCdFilter("usaspending/district_va_08", tags, null, null, "Virginia"),
      ).toBe(true);
    });

    it("state-level sources unlock via state-name query", () => {
      // State source IDs follow `acs_state/<series>_<st>` —
      // see parseStateSourceId.
      const tags = [STATE_TAG];
      expect(
        passesCdFilter("acs_state/population_va", tags, null, null, "Virginia"),
      ).toBe(true);
    });
  });

  describe("chip active (cdState set)", () => {
    // State codes in the pipeline + US_STATES are lowercase; cdState
    // matches that convention.
    it("non-geo sources fail", () => {
      expect(passesCdFilter("fred/cpi", ["macro"], "va", null, "")).toBe(false);
    });

    it("statewide pick: state-level for the picked state passes", () => {
      const tags = [STATE_TAG];
      expect(
        passesCdFilter("acs_state/population_va", tags, "va", STATEWIDE_DISTRICT_CODE, ""),
      ).toBe(true);
    });

    it("statewide pick: CD sources fail", () => {
      const tags = [CD_TAG];
      expect(
        passesCdFilter("usaspending/district_va_08", tags, "va", STATEWIDE_DISTRICT_CODE, ""),
      ).toBe(false);
    });

    it("statewide pick: state-level for different state fails", () => {
      const tags = [STATE_TAG];
      expect(
        passesCdFilter("acs_state/population_tx", tags, "va", STATEWIDE_DISTRICT_CODE, ""),
      ).toBe(false);
    });

    it("specific-CD pick: matching CD source passes", () => {
      const tags = [CD_TAG];
      expect(
        passesCdFilter("usaspending/district_va_08", tags, "va", "08", ""),
      ).toBe(true);
    });

    it("specific-CD pick: different CD source fails", () => {
      const tags = [CD_TAG];
      expect(
        passesCdFilter("usaspending/district_va_11", tags, "va", "08", ""),
      ).toBe(false);
    });

    it("specific-CD pick: state-level source fails (not a CD)", () => {
      const tags = [STATE_TAG];
      expect(
        passesCdFilter("acs_state/population_va", tags, "va", "08", ""),
      ).toBe(false);
    });

    it("'any district' pick (cdDistrict=null): both state-level + CDs of that state pass", () => {
      expect(
        passesCdFilter("acs_state/population_va", [STATE_TAG], "va", null, ""),
      ).toBe(true);
      expect(
        passesCdFilter("usaspending/district_va_08", [CD_TAG], "va", null, ""),
      ).toBe(true);
    });

    it("'any district' pick: sources for a different state fail", () => {
      expect(
        passesCdFilter("acs_state/population_tx", [STATE_TAG], "va", null, ""),
      ).toBe(false);
      expect(
        passesCdFilter("usaspending/district_tx_03", [CD_TAG], "va", null, ""),
      ).toBe(false);
    });
  });
});

describe("passesCountyFilter", () => {
  it("non-county sources always pass", () => {
    expect(passesCountyFilter("fred/cpi", ["macro"], "")).toBe(true);
    expect(passesCountyFilter("fred/cpi", ["macro"], "alex")).toBe(true);
  });

  it("county sources hidden without a query (< 4 chars)", () => {
    const tags = [COUNTY_TAG];
    expect(passesCountyFilter("bls/county_unemployment_alexandria_va", tags, "")).toBe(false);
    expect(passesCountyFilter("bls/county_unemployment_alexandria_va", tags, "ale")).toBe(false);
  });

  it("county sources unlock via a ≥ 4-char county-name query", () => {
    const tags = [COUNTY_TAG];
    expect(
      passesCountyFilter("bls/county_unemployment_alexandria_va", tags, "alex"),
    ).toBe(true);
    expect(
      passesCountyFilter("bls/county_unemployment_alexandria_va", tags, "Alexandria"),
    ).toBe(true);
  });

  it("a query that doesn't match the county NAME doesn't leak the source", () => {
    // The whole point of the rule: query "unemployment" matches the
    // SERIES name (and would pass the global text filter) but must
    // NOT pass the county gate — that'd surface every county we
    // ship under any series query.
    const tags = [COUNTY_TAG];
    expect(
      passesCountyFilter("bls/county_unemployment_alexandria_va", tags, "unemployment"),
    ).toBe(false);
  });

  it("a single county-name query matches all counties with that token", () => {
    // "prince" matches both Prince George's County + Prince William.
    const tags = [COUNTY_TAG];
    expect(
      passesCountyFilter("bls/county_unemployment_prince_georges_md", tags, "prince"),
    ).toBe(true);
    expect(
      passesCountyFilter("bls/county_unemployment_prince_william_va", tags, "prince"),
    ).toBe(true);
  });
});
