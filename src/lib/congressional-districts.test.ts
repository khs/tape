import { describe, expect, it } from "vitest";
import {
  CD_TAG,
  STATE_TAG,
  STATEWIDE_DISTRICT_CODE,
  US_STATES,
  cdLongLabel,
  cdPageSlug,
  DEFUNCT_CD_KEYS,
  formatCdShortLabel,
  formatDistrictLabel,
  ordinal,
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

  it("parses elections House-margin district IDs (incl at-large + DC)", () => {
    expect(parseCdSourceId("elections/house_margin_tx_12")).toEqual({
      state: "tx",
      district: "12",
    });
    expect(parseCdSourceId("elections/house_margin_ak_al")).toEqual({
      state: "ak",
      district: "al",
    });
    expect(parseCdSourceId("elections/house_margin_dc_98")).toEqual({
      state: "dc",
      district: "98",
    });
    // State-level election margins are NOT congressional districts.
    expect(parseCdSourceId("elections/pres_margin_ca")).toBeNull();
    expect(parseCdSourceId("elections/sen_margin_oh")).toBeNull();
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

  it("parses BLS LAUS labor-force measures, incl. multi-underscore stems", () => {
    // The labor-force expansion adds stems like emp_pop_ratio / labor_force
    // whose internal underscores must not fool the `_([a-z]{2})$` capture —
    // greedy `.+` has to backtrack to leave the trailing state code.
    expect(parseStateSourceId("bls/state_employed_ca")).toEqual({ state: "ca" });
    expect(parseStateSourceId("bls/state_unemployed_wy")).toEqual({ state: "wy" });
    expect(parseStateSourceId("bls/state_labor_force_tx")).toEqual({ state: "tx" });
    expect(parseStateSourceId("bls/state_emp_pop_ratio_dc")).toEqual({ state: "dc" });
    expect(parseStateSourceId("bls/state_lfpr_ny")).toEqual({ state: "ny" });
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

  it("parses providers that scope by trailing 2-letter code without a state_ slug", () => {
    // These declare the us-state tag but slug the state as a bare 2-letter
    // tail (no `state_` prefix); before they were recognized here they were
    // unreachable in the picker (passesCdFilter rejects unparseable
    // state-tagged sources in every branch).
    expect(parseStateSourceId("cdc_health/all_causes_aadr_al")).toEqual({ state: "al" });
    expect(parseStateSourceId("eia_prices/electricity_price_ak")).toEqual({ state: "ak" });
    expect(parseStateSourceId("usda_nass/corn_price_az")).toEqual({ state: "az" });
    expect(parseStateSourceId("usgs_water/aquaculture_ar")).toEqual({ state: "ar" });
    expect(parseStateSourceId("nhtsa_fars/traffic_fatalities_tx")).toEqual({ state: "tx" });
    expect(parseStateSourceId("nhtsa_fars/traffic_fatality_rate_ms")).toEqual({ state: "ms" });
  });

  it("rejects the national siblings of those providers", () => {
    expect(parseStateSourceId("cdc_health/all_causes_aadr_us")).toBeNull();
    expect(parseStateSourceId("eia_prices/electricity_price_us")).toBeNull();
    expect(parseStateSourceId("usda_nass/corn_price_us")).toBeNull();
    expect(parseStateSourceId("usgs_water/aquaculture_us")).toBeNull();
    expect(parseStateSourceId("nhtsa_fars/traffic_fatalities_us")).toBeNull();
    expect(parseStateSourceId("nhtsa_fars/traffic_fatality_rate_us")).toBeNull();
  });

  it("parses BEA state series slugged with the full state name", () => {
    expect(parseStateSourceId("bea/gdp_alabama")).toEqual({ state: "al" });
    expect(parseStateSourceId("bea/gdp_new_hampshire")).toEqual({ state: "nh" });
    expect(parseStateSourceId("bea/gdp_district_of_columbia")).toEqual({ state: "dc" });
    // Longest-suffix wins: west_virginia must not be misread as virginia.
    expect(parseStateSourceId("bea/gdp_west_virginia")).toEqual({ state: "wv" });
    expect(parseStateSourceId("bea/gdp_virginia")).toEqual({ state: "va" });
    // arkansas must not be misread as kansas (underscore anchor).
    expect(parseStateSourceId("bea/gdp_arkansas")).toEqual({ state: "ar" });
  });

  it("rejects BEA county series (numeric FIPS tail, not a state name)", () => {
    expect(parseStateSourceId("bea/county_income_01001")).toBeNull();
  });

  it("parses elections state-margin IDs (pres/sen/gov), not House", () => {
    expect(parseStateSourceId("elections/pres_margin_ca")).toEqual({
      state: "ca",
    });
    expect(parseStateSourceId("elections/sen_margin_oh")).toEqual({
      state: "oh",
    });
    expect(parseStateSourceId("elections/gov_margin_va")).toEqual({
      state: "va",
    });
    // House margins are CD-level (parseCdSourceId), not state. A House
    // at-large id ends in _al, which must NOT false-match the state tail.
    expect(parseStateSourceId("elections/house_margin_ak_al")).toBeNull();
    expect(parseStateSourceId("elections/house_margin_tx_12")).toBeNull();
  });
});

describe("formatDistrictLabel — statewide", () => {
  it("renders the statewide sentinel as 'Statewide'", () => {
    expect(formatDistrictLabel("tx", STATEWIDE_DISTRICT_CODE)).toBe("Statewide");
    expect(formatDistrictLabel("ca", STATEWIDE_DISTRICT_CODE)).toBe("Statewide");
  });
});

/* ---- /cd/ landing-page helpers ---- */

describe("ordinal", () => {
  it("handles the standard suffixes", () => {
    expect(ordinal(1)).toBe("1st");
    expect(ordinal(2)).toBe("2nd");
    expect(ordinal(3)).toBe("3rd");
    expect(ordinal(4)).toBe("4th");
    expect(ordinal(8)).toBe("8th");
  });

  it("handles the 11/12/13 exceptions", () => {
    expect(ordinal(11)).toBe("11th");
    expect(ordinal(12)).toBe("12th");
    expect(ordinal(13)).toBe("13th");
  });

  it("handles 21+ correctly", () => {
    expect(ordinal(21)).toBe("21st");
    expect(ordinal(22)).toBe("22nd");
    expect(ordinal(23)).toBe("23rd");
    expect(ordinal(52)).toBe("52nd");
  });
});

describe("cdLongLabel", () => {
  it("renders numbered districts with the state name and ordinal", () => {
    expect(cdLongLabel("va", "08")).toBe(
      "Virginia's 8th congressional district",
    );
    expect(cdLongLabel("tx", "12")).toBe(
      "Texas's 12th congressional district",
    );
  });

  it("renders at-large districts", () => {
    expect(cdLongLabel("wy", "al")).toBe(
      "Wyoming's at-large congressional district",
    );
  });

  it("renders the DC delegate district", () => {
    expect(cdLongLabel("dc", "98")).toBe(
      "the District of Columbia's delegate district",
    );
  });
});

describe("cdPageSlug", () => {
  it("builds slugs consistently with short labels", () => {
    expect(cdPageSlug("va", "08")).toBe("va-08");
    expect(cdPageSlug("mt", "al")).toBe("mt-al");
  });
});

describe("DEFUNCT_CD_KEYS", () => {
  it("keys parse back out of real acs_cd source ids", () => {
    // Every defunct key must correspond to the <st>_<dst> tail that
    // parseCdSourceId extracts — guards against key-format drift
    // (e.g. wv_3 vs wv_03) silently disabling an exclusion.
    for (const key of DEFUNCT_CD_KEYS) {
      const id = `acs_cd/population_${key}`;
      const parsed = parseCdSourceId(id);
      expect(parsed, `defunct key ${key} should parse`).not.toBeNull();
      expect(`${parsed!.state}_${parsed!.district}`).toBe(key);
    }
  });

  it("does not exclude current districts", () => {
    expect(DEFUNCT_CD_KEYS.has("va_08")).toBe(false);
    expect(DEFUNCT_CD_KEYS.has("mt_01")).toBe(false);
  });
});
