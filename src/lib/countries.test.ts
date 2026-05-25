/**
 * Tests for the country / region parsing + lookup helpers.
 *
 * These functions sit on the hot path of:
 *   - Library JSON synthesis (tagging a source as country-specific)
 *   - Composer's "Regions and countries" chip filter
 *   - Source-page country-attribution display
 *
 * Each branch of parseCountrySourceId handles a different pipeline's
 * naming convention (Yahoo ETF tickers, WB-GDP slugs, OECD ISO3,
 * Treasury TIC slugs, World-Bank-Extended slugs). A test per branch
 * locks the mapping down so a slug rename in a pipeline gets caught
 * before it breaks country attribution.
 */
import { describe, it, expect } from "vitest";
import {
  parseCountrySourceId,
  countryNameFor,
  isRegionCode,
} from "./countries";

describe("parseCountrySourceId", () => {
  describe("yahoo/<etf> branch", () => {
    it("maps single-country ETF tickers to their country", () => {
      // Tickers are lowercase in source IDs (Astro slug lowering);
      // the parser uppercases before the lookup so EWA, ewa, EwA
      // all resolve identically.
      expect(parseCountrySourceId("yahoo/ewa")).toEqual({
        code: "AUS",
        name: "Australia",
      });
      expect(parseCountrySourceId("yahoo/fxi")).toEqual({
        code: "CHN",
        name: "China",
      });
      expect(parseCountrySourceId("yahoo/inda")).toEqual({
        code: "IND",
        name: "India",
      });
    });

    it("returns null for non-country ETFs (broad-market baskets)", () => {
      // VT (Total World), VEA, EEM aren't in ETF_TO_COUNTRY because
      // they don't represent a single country. Should return null
      // so they stay in the default source list instead of being
      // attributed to one country.
      expect(parseCountrySourceId("yahoo/vt")).toBeNull();
      expect(parseCountrySourceId("yahoo/vea")).toBeNull();
      expect(parseCountrySourceId("yahoo/eem")).toBeNull();
    });

    it("returns null for FRED + other non-yahoo paths that happen to share a suffix", () => {
      expect(parseCountrySourceId("fred/ewa_made_up")).toBeNull();
      expect(parseCountrySourceId("yahoo/spy")).toBeNull(); // SPY isn't in the table
    });
  });

  describe("worldbank_gdp[_raw]/<slug> branch", () => {
    it("maps country slugs to ISO3 + name", () => {
      expect(parseCountrySourceId("worldbank_gdp_raw/germany")).toEqual({
        code: "DEU",
        name: "Germany",
      });
      expect(parseCountrySourceId("worldbank_gdp_raw/japan")).toEqual({
        code: "JPN",
        name: "Japan",
      });
      expect(parseCountrySourceId("worldbank_gdp_raw/uk")).toEqual({
        code: "GBR",
        name: "United Kingdom",
      });
    });

    it("returns null for usa + world (stay in default list)", () => {
      // Per the parser docstring: USA + World are deliberately
      // excluded so the chip filter doesn't hide them from the
      // base library view.
      expect(parseCountrySourceId("worldbank_gdp_raw/usa")).toBeNull();
      expect(parseCountrySourceId("worldbank_gdp_raw/world")).toBeNull();
    });
  });

  describe("treasury_tic/<slug> branch", () => {
    it("maps foreign-country slugs to ISO3", () => {
      expect(parseCountrySourceId("treasury_tic/japan")).toEqual({
        code: "JPN",
        name: "Japan",
      });
      expect(parseCountrySourceId("treasury_tic/cayman_islands")).toEqual({
        code: "CYM",
        name: "Cayman Islands",
      });
    });

    it("returns null for grand_total (aggregate, stays in default list)", () => {
      expect(parseCountrySourceId("treasury_tic/grand_total")).toBeNull();
    });
  });

  describe("oecd/<iso3>_<series> branch", () => {
    it("extracts the iso3 prefix from the slug", () => {
      expect(parseCountrySourceId("oecd/can_cpi_yoy")).toEqual({
        code: "CAN",
        name: "Canada",
      });
      expect(parseCountrySourceId("oecd/deu_gov_debt_pct_gdp")).toEqual({
        code: "DEU",
        name: "Germany",
      });
    });

    it("returns null for usa-prefixed slugs", () => {
      // USA OECD entries stay in the default list — same rule as
      // worldbank_gdp.
      expect(parseCountrySourceId("oecd/usa_cpi_yoy")).toBeNull();
    });

    it("returns null for unrecognized iso3 prefixes", () => {
      // The match requires the 3-letter prefix be in COUNTRY_NAME_BY_CODE;
      // "xyz" obviously isn't, so this should fall through to the
      // final null return.
      expect(parseCountrySourceId("oecd/xyz_something")).toBeNull();
    });
  });

  describe("worldbank_extended/<indicator>_<entity> branch", () => {
    it("matches entity-slug suffixes longest-first", () => {
      // south_africa is a 12-char slug and would mis-parse as
      // africa (region) if the suffix-search didn't go longest-
      // first. Locks down the sort order.
      expect(
        parseCountrySourceId("worldbank_extended/co2_per_capita_south_africa"),
      ).toEqual({ code: "ZAF", name: "South Africa" });
    });

    it("returns regional aggregate codes for WB region slugs", () => {
      // worldbank_extended ships per-region aggregates under slugs
      // like _europe_eu, _africa_ssf. They map to region codes
      // (not country codes).
      const result = parseCountrySourceId(
        "worldbank_extended/gdp_current_usd_europe_eu",
      );
      expect(result?.code).toBe("EUU");
    });
  });

  describe("unknown / malformed IDs", () => {
    it("returns null for empty string", () => {
      expect(parseCountrySourceId("")).toBeNull();
    });

    it("returns null for fred non-country sources", () => {
      expect(parseCountrySourceId("fred/us_cpi")).toBeNull();
      expect(parseCountrySourceId("fred/fed_funds")).toBeNull();
    });

    it("returns null for state-level sources", () => {
      expect(parseCountrySourceId("acs_state/population_va")).toBeNull();
      expect(parseCountrySourceId("bls/state_unemployment_tx")).toBeNull();
    });

    it("returns null for ids without a recognized prefix", () => {
      expect(parseCountrySourceId("totally/made/up")).toBeNull();
      expect(parseCountrySourceId("notapipeline/germany")).toBeNull();
    });
  });
});

describe("countryNameFor", () => {
  it("resolves country ISO3 codes to display names", () => {
    expect(countryNameFor("USA")).toBe("United States");
    expect(countryNameFor("DEU")).toBe("Germany");
    expect(countryNameFor("JPN")).toBe("Japan");
  });

  it("resolves region codes to region names", () => {
    expect(countryNameFor("EUU")).toBe("European Union");
    expect(countryNameFor("SSF")).toBe("Sub-Saharan Africa");
  });

  it("falls back to the code itself when unknown", () => {
    // Important fallback — even an unrecognized code should at
    // least render *something* readable, not undefined / blank.
    expect(countryNameFor("XYZ")).toBe("XYZ");
    expect(countryNameFor("")).toBe("");
  });
});

describe("isRegionCode", () => {
  it("returns true for WB regional aggregate codes", () => {
    expect(isRegionCode("EUU")).toBe(true);
    expect(isRegionCode("SSF")).toBe(true);
    expect(isRegionCode("NAC")).toBe(true);
  });

  it("returns false for country ISO3 codes", () => {
    expect(isRegionCode("USA")).toBe(false);
    expect(isRegionCode("DEU")).toBe(false);
    expect(isRegionCode("JPN")).toBe(false);
  });

  it("returns false for unknown codes", () => {
    expect(isRegionCode("XYZ")).toBe(false);
    expect(isRegionCode("")).toBe(false);
  });
});
