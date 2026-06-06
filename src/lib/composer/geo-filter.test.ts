import { describe, it, expect } from "vitest";
import { createComposerGeoFilters } from "./geo-filter";
import {
  CD_TAG,
  STATE_TAG,
  STATEWIDE_DISTRICT_CODE,
} from "../congressional-districts";
import { METRO_TAG } from "../geographic-regions";
import { COUNTRY_TAG } from "../countries";
import { COUNTY_TAG } from "../county-sources";
import type { SourceFiltersLibrary } from "../source-filters";

// Fixture library: one metro (Abilene/CBSA 12345) and one country (Australia).
const LIB: SourceFiltersLibrary = {
  metros: { "12345": { shortName: "Abilene", name: "Abilene, TX" } },
  countries: { AUS: { name: "Australia" } },
};
const mk = (lib: SourceFiltersLibrary | null = LIB) =>
  createComposerGeoFilters(() => lib);

// Representative sources (IDs match the real parser formats).
const NON_GEO = { id: "fred/cpi", tags: ["inflation"] };
const STATE_TX = { id: "bls/state_unemployment_tx", tags: [STATE_TAG] };
const STATE_VA = { id: "bls/state_unemployment_va", tags: [STATE_TAG] };
const CD_TX_07 = { id: "usaspending/district_tx_07", tags: [CD_TAG] };
const CD_VA_08 = { id: "usaspending/district_va_08", tags: [CD_TAG] };
const METRO_SRC = { id: "zillow/rent_12345", tags: [`${METRO_TAG}:12345`, "real-estate"] };
// Country sources carry the BARE country-specific tag (the filter keys off it),
// plus the per-country tag for the drill-down.
const COUNTRY_SRC = { id: "worldbank/gdp_aus", tags: [COUNTRY_TAG, `${COUNTRY_TAG}:AUS`, "world"] };
const COUNTY_SRC = { id: "bls/county_unemployment_alexandria_va", tags: [COUNTY_TAG] };

const OFF = new Set<string>();
const ON = new Set<string>([CD_TAG]);

describe("composer passesCdFilter — chip OFF", () => {
  const f = mk();
  it("non-geo sources always pass", () => {
    expect(f.passesCdFilter(NON_GEO.id, NON_GEO.tags, OFF, null, null, "")).toBe(true);
    expect(f.passesCdFilter(METRO_SRC.id, METRO_SRC.tags, OFF, null, null, "")).toBe(true);
  });
  it("geo sources fail without a state-name unlock", () => {
    expect(f.passesCdFilter(STATE_TX.id, STATE_TX.tags, OFF, null, null, "")).toBe(false);
    expect(f.passesCdFilter(CD_TX_07.id, CD_TX_07.tags, OFF, null, null, "")).toBe(false);
  });
  it("a >=4-char state-name query unlocks that state's geo sources", () => {
    expect(f.passesCdFilter(STATE_TX.id, STATE_TX.tags, OFF, null, null, "Texas")).toBe(true);
    expect(f.passesCdFilter(CD_TX_07.id, CD_TX_07.tags, OFF, null, null, "Texas")).toBe(true);
    expect(f.passesCdFilter(STATE_VA.id, STATE_VA.tags, OFF, null, null, "Texas")).toBe(false);
  });
  it("a <4-char query does not unlock", () => {
    expect(f.passesCdFilter(STATE_TX.id, STATE_TX.tags, OFF, null, null, "Tex")).toBe(false);
  });
});

describe("composer passesCdFilter — chip ON, no state (the gate)", () => {
  const f = mk();
  it("shows NOTHING until a state is picked (empty-list gate)", () => {
    expect(f.passesCdFilter(NON_GEO.id, NON_GEO.tags, ON, null, null, "")).toBe(false);
    expect(f.passesCdFilter(STATE_TX.id, STATE_TX.tags, ON, null, null, "")).toBe(false);
    expect(f.passesCdFilter(CD_TX_07.id, CD_TX_07.tags, ON, null, null, "Texas")).toBe(false);
  });
});

describe("composer passesCdFilter — chip ON, state picked", () => {
  const f = mk();
  it("district unset ('Any') → state-level + CDs of that state", () => {
    expect(f.passesCdFilter(STATE_TX.id, STATE_TX.tags, ON, "tx", null, "")).toBe(true);
    expect(f.passesCdFilter(CD_TX_07.id, CD_TX_07.tags, ON, "tx", null, "")).toBe(true);
    expect(f.passesCdFilter(STATE_VA.id, STATE_VA.tags, ON, "tx", null, "")).toBe(false);
    expect(f.passesCdFilter(CD_VA_08.id, CD_VA_08.tags, ON, "tx", null, "")).toBe(false);
    expect(f.passesCdFilter(NON_GEO.id, NON_GEO.tags, ON, "tx", null, "")).toBe(false);
  });
  it("district = STATEWIDE → only state-level for that state", () => {
    expect(f.passesCdFilter(STATE_TX.id, STATE_TX.tags, ON, "tx", STATEWIDE_DISTRICT_CODE, "")).toBe(true);
    expect(f.passesCdFilter(CD_TX_07.id, CD_TX_07.tags, ON, "tx", STATEWIDE_DISTRICT_CODE, "")).toBe(false);
  });
  it("district = specific CD → only that CD", () => {
    expect(f.passesCdFilter(CD_TX_07.id, CD_TX_07.tags, ON, "tx", "07", "")).toBe(true);
    expect(f.passesCdFilter(CD_VA_08.id, CD_VA_08.tags, ON, "tx", "07", "")).toBe(false);
    expect(f.passesCdFilter(STATE_TX.id, STATE_TX.tags, ON, "tx", "07", "")).toBe(false);
  });
});

describe("composer passesMetroFilter", () => {
  const f = mk();
  it("selected CBSA narrows to that CBSA's sources only", () => {
    expect(f.passesMetroFilter(METRO_SRC.tags, "12345", "")).toBe(true);
    expect(f.passesMetroFilter(METRO_SRC.tags, "99999", "")).toBe(false);
    expect(f.passesMetroFilter(NON_GEO.tags, "12345", "")).toBe(false);
  });
  it("no selection: non-metro passes, metro needs a name unlock", () => {
    expect(f.passesMetroFilter(NON_GEO.tags, null, "")).toBe(true);
    expect(f.passesMetroFilter(METRO_SRC.tags, null, "")).toBe(false);
    expect(f.passesMetroFilter(METRO_SRC.tags, null, "Abilene")).toBe(true);
    expect(f.passesMetroFilter(METRO_SRC.tags, null, "Abil")).toBe(true);
    expect(f.passesMetroFilter(METRO_SRC.tags, null, "Abi")).toBe(false); // <4
  });
});

describe("composer passesCountryFilter", () => {
  const f = mk();
  it("selected country narrows; otherwise non-country passes + name unlock", () => {
    expect(f.passesCountryFilter(COUNTRY_SRC.tags, "AUS", "")).toBe(true);
    expect(f.passesCountryFilter(NON_GEO.tags, "AUS", "")).toBe(false);
    expect(f.passesCountryFilter(NON_GEO.tags, null, "")).toBe(true);
    expect(f.passesCountryFilter(COUNTRY_SRC.tags, null, "")).toBe(false);
    expect(f.passesCountryFilter(COUNTRY_SRC.tags, null, "Australia")).toBe(true);
  });
});

describe("composer passesCountyFilter", () => {
  const f = mk();
  it("counties are hidden by default; a name query surfaces them", () => {
    expect(f.passesCountyFilter(NON_GEO.id, NON_GEO.tags, "")).toBe(true);
    expect(f.passesCountyFilter(COUNTY_SRC.id, COUNTY_SRC.tags, "")).toBe(false);
    expect(f.passesCountyFilter(COUNTY_SRC.id, COUNTY_SRC.tags, "alex")).toBe(true);
    expect(f.passesCountyFilter(COUNTY_SRC.id, COUNTY_SRC.tags, "zzzz")).toBe(false);
  });
});

describe("library getter + per-query memo", () => {
  it("reads the library via the getter (no metros → no metro unlock)", () => {
    const empty = mk({});
    expect(empty.passesMetroFilter(METRO_SRC.tags, null, "Abilene")).toBe(false);
    const full = mk(LIB);
    expect(full.passesMetroFilter(METRO_SRC.tags, null, "Abilene")).toBe(true);
  });
  it("repeated calls with the same query are stable (memo correctness)", () => {
    const f = mk();
    for (let i = 0; i < 3; i++) {
      expect(f.passesMetroFilter(METRO_SRC.tags, null, "Abilene")).toBe(true);
      expect(f.passesCountryFilter(COUNTRY_SRC.tags, null, "Australia")).toBe(true);
    }
    // query changes invalidate the cache
    expect(f.passesMetroFilter(METRO_SRC.tags, null, "Boston")).toBe(false);
    expect(f.passesMetroFilter(METRO_SRC.tags, null, "Abilene")).toBe(true);
  });
});
