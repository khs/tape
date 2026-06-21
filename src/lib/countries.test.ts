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
  canonicalCountryTitle,
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

    it("hides every non-US OECD country (no foreign OECD in the default list)", () => {
      // The default source list must never contain a foreign OECD series —
      // they belong behind the "Countries & regions" chip. Spot-check the
      // major economies; each must parse to a non-null country code.
      for (const [slug, code] of [
        ["jpn", "JPN"], ["fra", "FRA"], ["gbr", "GBR"],
        ["mex", "MEX"], ["ita", "ITA"], ["kor", "KOR"], ["aus", "AUS"],
      ] as const) {
        expect(parseCountrySourceId(`oecd/${slug}_cpi_yoy`)?.code, slug).toBe(code);
      }
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

  describe("owid_co2/<metric>_<entity> branch", () => {
    it("hides a plain-country series (the leak the user reported)", () => {
      expect(parseCountrySourceId("owid_co2/co2_australia")).toEqual({
        code: "AUS",
        name: "Australia",
      });
    });

    it("parses every metric prefix by matching the entity suffix", () => {
      // The metric prefix varies in token count; the entity is always the
      // suffix. All of these must resolve to South Korea.
      for (const id of [
        "owid_co2/co2_south_korea",
        "owid_co2/per_capita_south_korea",
        "owid_co2/coal_co2_south_korea",
        "owid_co2/energy_per_capita_south_korea",
        "owid_co2/share_global_co2_south_korea",
      ]) {
        expect(parseCountrySourceId(id)?.code, id).toBe("KOR");
      }
    });

    it("does not let a short entity swallow a longer one (longest-first)", () => {
      expect(parseCountrySourceId("owid_co2/co2_south_africa")?.code).toBe("ZAF");
      expect(parseCountrySourceId("owid_co2/co2_united_kingdom")?.code).toBe(
        "GBR",
      );
    });

    it("maps the EU aggregate to its region code", () => {
      expect(parseCountrySourceId("owid_co2/co2_european_union")?.code).toBe(
        "EUU",
      );
    });

    it("keeps United States + World in the default list (null)", () => {
      expect(parseCountrySourceId("owid_co2/co2_united_states")).toBeNull();
      expect(parseCountrySourceId("owid_co2/per_capita_united_states")).toBeNull();
      expect(parseCountrySourceId("owid_co2/co2_world")).toBeNull();
      expect(parseCountrySourceId("owid_co2/share_global_co2_world")).toBeNull();
    });
  });

  describe("countries_gdp/<slug> branch (leak fix)", () => {
    it("hides foreign GDP-share series (countries_gdp leaked into default)", () => {
      // countries_gdp/mexico = "Mexico real-GDP share of world" — was leaking
      // because the parser only knew the countries/ sibling.
      expect(parseCountrySourceId("countries_gdp/mexico")?.code).toBe("MEX");
      expect(parseCountrySourceId("countries_gdp/uk")?.code).toBe("GBR");
      expect(parseCountrySourceId("countries_gdp/south_korea")?.code).toBe("KOR");
    });

    it("keeps USA + world visible (null)", () => {
      expect(parseCountrySourceId("countries_gdp/usa")).toBeNull();
      expect(parseCountrySourceId("countries_gdp/world")).toBeNull();
    });
  });

  describe("owid_energy/<metric>_<entity> branch (leak fix)", () => {
    it("hides foreign renewable-share series (owid_energy sibling of owid_co2)", () => {
      expect(
        parseCountrySourceId("owid_energy/renewable_electricity_share_china")?.code,
      ).toBe("CHN");
      expect(
        parseCountrySourceId("owid_energy/renewable_electricity_share_south_korea")
          ?.code,
      ).toBe("KOR");
    });

    it("keeps United States + World visible (null)", () => {
      expect(
        parseCountrySourceId(
          "owid_energy/renewable_electricity_share_united_states",
        ),
      ).toBeNull();
      expect(
        parseCountrySourceId("owid_energy/renewable_electricity_share_world"),
      ).toBeNull();
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

describe("canonicalCountryTitle (self-heal stale slug titles)", () => {
  const uaeSrc = ["worldbank_extended/population_uae"];
  it("corrects the stale title-cased slug to the country name", () => {
    expect(canonicalCountryTitle("Uae", uaeSrc)).toBe("United Arab Emirates");
    expect(canonicalCountryTitle("Uae", ["treasury_tic/uae"])).toBe(
      "United Arab Emirates",
    );
  });
  it("preserves an all-caps acronym, a real name, and renames", () => {
    expect(canonicalCountryTitle("UAE", uaeSrc)).toBe("UAE");
    expect(canonicalCountryTitle("United Arab Emirates", uaeSrc)).toBe(
      "United Arab Emirates",
    );
    expect(canonicalCountryTitle("Emirates", uaeSrc)).toBe("Emirates");
  });
  it("leaves correct single-word names alone (title === name)", () => {
    // France's name IS "France", so the Title-Case word equals the name and is
    // returned untouched (and would be correct regardless).
    expect(canonicalCountryTitle("France", ["worldbank_gdp/france"])).toBe(
      "France",
    );
  });
  it("no-ops on multi-source charts and non-country sources", () => {
    expect(
      canonicalCountryTitle("Uae", ["worldbank_extended/population_uae", "x/y"]),
    ).toBe("Uae");
    expect(canonicalCountryTitle("Foo", ["fred/unrate"])).toBe("Foo");
  });
});
