import { describe, expect, it } from "vitest";
import {
  CD_TAG,
  STATE_TAG,
  STATEWIDE_DISTRICT_CODE,
  US_STATES,
  formatCdShortLabel,
  formatDistrictLabel,
  parseCdSourceId,
  parseStateSourceId,
  stateNameFor,
} from "./congressional-districts";

describe("parseCdSourceId", () => {
  it("parses usaspending district IDs", () => {
    expect(parseCdSourceId("usaspending/district_tx_01")).toEqual({
      state: "tx",
      district: "01",
    });
    expect(parseCdSourceId("usaspending/district_ny_26")).toEqual({
      state: "ny",
      district: "26",
    });
  });

  it("parses at-large districts (single-district states)", () => {
    expect(parseCdSourceId("usaspending/district_ak_al")).toEqual({
      state: "ak",
      district: "al",
    });
    expect(parseCdSourceId("usaspending/district_wy_al")).toEqual({
      state: "wy",
      district: "al",
    });
  });

  it("parses DC's 98 (non-voting delegate) code", () => {
    expect(parseCdSourceId("usaspending/district_dc_98")).toEqual({
      state: "dc",
      district: "98",
    });
  });

  it("parses acs_cd IDs across all series prefixes", () => {
    expect(parseCdSourceId("acs_cd/bachelors_plus_tx_01")).toEqual({
      state: "tx",
      district: "01",
    });
    expect(parseCdSourceId("acs_cd/median_hh_income_va_08")).toEqual({
      state: "va",
      district: "08",
    });
    expect(parseCdSourceId("acs_cd/population_ca_52")).toEqual({
      state: "ca",
      district: "52",
    });
    expect(parseCdSourceId("acs_cd/poverty_count_fl_28")).toEqual({
      state: "fl",
      district: "28",
    });
  });

  it("parses fec House-spending district IDs", () => {
    expect(parseCdSourceId("fec/house_spending_tx_07")).toEqual({
      state: "tx",
      district: "07",
    });
    expect(parseCdSourceId("fec/house_spending_ca_52")).toEqual({
      state: "ca",
      district: "52",
    });
    // At-large + DC delegate share the same al/98 coding as the other
    // CD providers, so FEC spending buckets alongside ACS / USAspending
    // data for the very same seat in the drill-down.
    expect(parseCdSourceId("fec/house_spending_wy_al")).toEqual({
      state: "wy",
      district: "al",
    });
    expect(parseCdSourceId("fec/house_spending_dc_98")).toEqual({
      state: "dc",
      district: "98",
    });
  });

  it("does NOT treat the FEC national total as a CD", () => {
    // fec/house_spending_us_total is the nationwide sum — "us" is not a
    // state code, so it must stay in the general browse, not the chip.
    expect(parseCdSourceId("fec/house_spending_us_total")).toBeNull();
  });

  it("rejects state-level (non-CD) IDs", () => {
    expect(parseCdSourceId("usaspending/state_tx")).toBeNull();
    expect(parseCdSourceId("usaspending/state_dc")).toBeNull();
    expect(parseCdSourceId("fred/state_population_tx")).toBeNull();
    expect(parseCdSourceId("bls/state_unemployment_ca")).toBeNull();
  });

  it("rejects unrelated source IDs", () => {
    expect(parseCdSourceId("fred/us_real_gdp")).toBeNull();
    expect(parseCdSourceId("yahoo/wti_crude")).toBeNull();
    expect(parseCdSourceId("yahoo_marketcap/aapl_mc")).toBeNull();
    expect(parseCdSourceId("worldbank_gdp_raw/usa_gdp")).toBeNull();
  });

  it("rejects malformed IDs that nearly match", () => {
    // Wrong prefix
    expect(parseCdSourceId("usaspending/cd_tx_01")).toBeNull();
    // State code too long
    expect(parseCdSourceId("usaspending/district_tex_01")).toBeNull();
    // District code too short
    expect(parseCdSourceId("usaspending/district_tx_1")).toBeNull();
    // Trailing junk
    expect(parseCdSourceId("usaspending/district_tx_01_extra")).toBeNull();
  });
});

describe("formatDistrictLabel", () => {
  it("strips leading zero on 2-digit districts", () => {
    expect(formatDistrictLabel("tx", "01")).toBe("1");
    expect(formatDistrictLabel("ca", "07")).toBe("7");
  });

  it("keeps 2-digit districts >= 10", () => {
    expect(formatDistrictLabel("tx", "12")).toBe("12");
    expect(formatDistrictLabel("ca", "52")).toBe("52");
  });

  it("renders at-large as 'At-large'", () => {
    expect(formatDistrictLabel("ak", "al")).toBe("At-large");
    expect(formatDistrictLabel("wy", "al")).toBe("At-large");
  });

  it("renders DC's 98 as 'Delegate'", () => {
    expect(formatDistrictLabel("dc", "98")).toBe("Delegate");
  });
});

describe("formatCdShortLabel", () => {
  it("uppercases state + district code", () => {
    expect(formatCdShortLabel("tx", "01")).toBe("TX-01");
    expect(formatCdShortLabel("ak", "al")).toBe("AK-AL");
    expect(formatCdShortLabel("dc", "98")).toBe("DC-98");
  });
});

describe("stateNameFor + US_STATES table", () => {
  it("includes all 50 states plus DC", () => {
    expect(US_STATES).toHaveLength(51);
  });

  it("resolves codes to display names", () => {
    expect(stateNameFor("tx")).toBe("Texas");
    expect(stateNameFor("dc")).toBe("District of Columbia");
    expect(stateNameFor("ca")).toBe("California");
  });

  it("falls back to uppercased code for unknown inputs", () => {
    expect(stateNameFor("xx")).toBe("XX");
  });
});

describe("CD_TAG sentinel", () => {
  it("is the literal string the composer + library.json synthesize", () => {
    // Pin the constant so a typo on one side breaks the test rather
    // than silently breaking the drill-down at runtime.
    expect(CD_TAG).toBe("congressional-district");
  });
});

describe("STATE_TAG sentinel", () => {
  it("is the literal string the composer + library.json synthesize", () => {
    expect(STATE_TAG).toBe("us-state");
  });

  it("differs from CD_TAG", () => {
    // The two tags drive different visibility scopes (district vs
    // state-level) and must never collide.
    expect(STATE_TAG).not.toBe(CD_TAG);
  });
});

describe("STATEWIDE_DISTRICT_CODE", () => {
  it("uses a sentinel string that no real district code could match", () => {
    // Real district codes are 2 chars ("01"–"53", "al", "98"). The
    // statewide sentinel must NOT pass a 2-char-only regex so the
    // CD parser can't false-positive on it. Underscore prefix is
    // intentional.
    expect(STATEWIDE_DISTRICT_CODE.startsWith("__")).toBe(true);
    expect(STATEWIDE_DISTRICT_CODE).not.toMatch(/^[a-z0-9]{2}$/);
  });
});

describe("parseStateSourceId", () => {
  it("parses usaspending/state_<st>", () => {
    expect(parseStateSourceId("usaspending/state_tx")).toEqual({ state: "tx" });
    expect(parseStateSourceId("usaspending/state_dc")).toEqual({ state: "dc" });
    expect(parseStateSourceId("usaspending/state_wy")).toEqual({ state: "wy" });
  });

  it("parses FRED state-level series", () => {
    expect(parseStateSourceId("fred/state_population_tx")).toEqual({ state: "tx" });
    expect(parseStateSourceId("fred/state_population_ca")).toEqual({ state: "ca" });
  });

  it("parses BLS state-level series", () => {
    expect(parseStateSourceId("bls/state_unemployment_tx")).toEqual({ state: "tx" });
    expect(parseStateSourceId("bls/state_payrolls_ca")).toEqual({ state: "ca" });
  });

  it("parses Census state-government-finance series", () => {
    expect(parseStateSourceId("census_govfin/state_totexp_ca")).toEqual({ state: "ca" });
    expect(parseStateSourceId("census_govfin/state_welfexp_tx")).toEqual({ state: "tx" });
    expect(parseStateSourceId("census_govfin/state_hwyexp_wy")).toEqual({ state: "wy" });
  });

  it("does NOT treat census_govfin national totals as state-level", () => {
    // `census_govfin/us_<series>` is the US aggregate — it must stay
    // default-visible, not get gated behind the state chip.
    expect(parseStateSourceId("census_govfin/us_totexp")).toBeNull();
    expect(parseStateSourceId("census_govfin/us_totrev")).toBeNull();
  });

  it("parses ACS race-unemployment state series + spares the US ones", () => {
    expect(parseStateSourceId("acs_labor/state_black_ca")).toEqual({ state: "ca" });
    expect(parseStateSourceId("acs_labor/state_hispanic_tx")).toEqual({ state: "tx" });
    expect(parseStateSourceId("acs_labor/state_total_dc")).toEqual({ state: "dc" });
    expect(parseStateSourceId("acs_labor/us_black")).toBeNull();
    expect(parseStateSourceId("acs_labor/us_total")).toBeNull();
  });

  it("parses EIA state energy-generation series + spares the US ones", () => {
    expect(parseStateSourceId("eia_state_energy/state_wind_tx")).toEqual({ state: "tx" });
    expect(parseStateSourceId("eia_state_energy/state_hydro_wa")).toEqual({ state: "wa" });
    expect(parseStateSourceId("eia_state_energy/state_all_ca")).toEqual({ state: "ca" });
    expect(parseStateSourceId("eia_state_energy/us_wind")).toBeNull();
    expect(parseStateSourceId("eia_state_energy/us_all")).toBeNull();
  });

  it("parses NAEP + per-pupil education series + spares the US ones", () => {
    expect(parseStateSourceId("naep/state_mathg8_ca")).toEqual({ state: "ca" });
    expect(parseStateSourceId("naep/state_readg4_ms")).toEqual({ state: "ms" });
    expect(parseStateSourceId("edu_spending/state_perpupil_ny")).toEqual({ state: "ny" });
    expect(parseStateSourceId("naep/us_mathg8")).toBeNull();
    expect(parseStateSourceId("edu_spending/us_perpupil")).toBeNull();
  });

  it("rejects CD-level IDs (those belong to parseCdSourceId)", () => {
    expect(parseStateSourceId("usaspending/district_tx_01")).toBeNull();
    expect(parseStateSourceId("acs_cd/bachelors_plus_tx_01")).toBeNull();
  });

  it("rejects unrelated source IDs", () => {
    expect(parseStateSourceId("fred/us_real_gdp")).toBeNull();
    expect(parseStateSourceId("yahoo/wti_crude")).toBeNull();
  });

  it("rejects IDs ending in 2 chars that aren't real state codes", () => {
    // Defensive: a hypothetical bls/state_foo_xy must NOT be treated as
    // state-level data just because the regex matches structurally.
    expect(parseStateSourceId("bls/state_foo_xy")).toBeNull();
    expect(parseStateSourceId("fred/state_thing_zz")).toBeNull();
  });

  it("parses acs_state/<series>_<st>", () => {
    expect(parseStateSourceId("acs_state/bachelors_plus_tx")).toEqual({ state: "tx" });
    expect(parseStateSourceId("acs_state/median_hh_income_ca")).toEqual({ state: "ca" });
    expect(parseStateSourceId("acs_state/population_dc")).toEqual({ state: "dc" });
    expect(parseStateSourceId("acs_state/poverty_count_wy")).toEqual({ state: "wy" });
  });

  it("rejects acs_state IDs that end in a non-state code", () => {
    // Same defensive guard as fred/bls — acs_state must end in a real
    // 2-letter state code, not just any 2 letters.
    expect(parseStateSourceId("acs_state/bachelors_plus_xy")).toBeNull();
  });
});

describe("formatDistrictLabel — statewide", () => {
  it("renders the statewide sentinel as 'Statewide'", () => {
    expect(formatDistrictLabel("tx", STATEWIDE_DISTRICT_CODE)).toBe("Statewide");
    expect(formatDistrictLabel("ca", STATEWIDE_DISTRICT_CODE)).toBe("Statewide");
  });
});
