import { describe, it, expect } from "vitest";
import {
  METRO_TAG,
  parseMetroSourceId,
  isMetroSourceId,
  metroTagsFor,
} from "./geographic-regions";

describe("parseMetroSourceId", () => {
  it("parses a usaspending metro ID", () => {
    expect(parseMetroSourceId("usaspending/metro_35620")).toEqual({
      pipeline: "usaspending",
      series: "spending",
      cbsa: "35620",
    });
  });

  it("parses an acs_metro ID with a multi-word series", () => {
    expect(parseMetroSourceId("acs_metro/median_hh_income_19100")).toEqual({
      pipeline: "acs_metro",
      series: "median_hh_income",
      cbsa: "19100",
    });
  });

  it("parses a bls metro unemployment ID", () => {
    expect(parseMetroSourceId("bls/metro_unemployment_47900")).toEqual({
      pipeline: "bls",
      series: "unemployment",
      cbsa: "47900",
    });
  });

  it("maps a NOAA city-climate ID to its metro CBSA", () => {
    expect(parseMetroSourceId("noaa_climate/temperature_washington_dc")).toEqual({
      pipeline: "noaa_climate",
      series: "temperature",
      cbsa: "47900",
    });
    expect(parseMetroSourceId("noaa_climate/precipitation_new_orleans")).toEqual({
      pipeline: "noaa_climate",
      series: "precipitation",
      cbsa: "35380",
    });
    // a NOAA city not in the metro map → not a metro source
    expect(parseMetroSourceId("noaa_climate/temperature_anchorage")).toBeNull();
  });

  it("parses a bls metro payrolls ID", () => {
    expect(parseMetroSourceId("bls/metro_payrolls_16980")).toEqual({
      pipeline: "bls",
      series: "payrolls",
      cbsa: "16980",
    });
  });

  it("preserves leading zeros in the CBSA code", () => {
    // No real OMB CBSA codes start with 0, but the parser should not
    // strip them — CBSA codes are strings, not ints.
    expect(parseMetroSourceId("usaspending/metro_01234")?.cbsa).toBe("01234");
  });

  it("returns null for non-metro usaspending IDs", () => {
    expect(parseMetroSourceId("usaspending/district_va_08")).toBeNull();
    expect(parseMetroSourceId("usaspending/state_va")).toBeNull();
  });

  it("returns null for non-metro BLS IDs", () => {
    expect(parseMetroSourceId("bls/state_unemployment_va")).toBeNull();
    expect(parseMetroSourceId("bls/county_unemployment_arlington_va")).toBeNull();
    expect(parseMetroSourceId("bls/cpi_shelter")).toBeNull();
  });

  it("returns null for non-metro ACS IDs", () => {
    expect(parseMetroSourceId("acs_cd/bachelors_plus_va_08")).toBeNull();
  });

  it("returns null for empty / malformed input", () => {
    expect(parseMetroSourceId("")).toBeNull();
    expect(parseMetroSourceId("/")).toBeNull();
    expect(parseMetroSourceId("usaspending/metro_")).toBeNull();
    expect(parseMetroSourceId("usaspending/metro_35620x")).toBeNull();
    expect(parseMetroSourceId("usaspending/metro_356")).toBeNull(); // 3-digit
    expect(parseMetroSourceId("acs_metro/35620")).toBeNull(); // no series
  });

  it("rejects pipeline mismatches", () => {
    // The acs_metro pattern looks similar to the bls one (both
    // <thing>_<cbsa>), so make sure pipeline gates the regex.
    expect(parseMetroSourceId("fred/metro_unemployment_35620")).toBeNull();
  });
});

describe("isMetroSourceId", () => {
  it("returns true for metro sources", () => {
    expect(isMetroSourceId("usaspending/metro_35620")).toBe(true);
    expect(isMetroSourceId("acs_metro/population_19100")).toBe(true);
    expect(isMetroSourceId("bls/metro_payrolls_47900")).toBe(true);
  });

  it("returns false for non-metro sources", () => {
    expect(isMetroSourceId("fred/us_population")).toBe(false);
    expect(isMetroSourceId("yahoo/aapl")).toBe(false);
  });
});

describe("metroTagsFor", () => {
  it("emits the global tag plus a per-CBSA tag", () => {
    expect(metroTagsFor("usaspending/metro_35620")).toEqual([
      METRO_TAG,
      `${METRO_TAG}:35620`,
    ]);
  });

  it("returns an empty array for non-metro sources", () => {
    expect(metroTagsFor("fred/us_cpi")).toEqual([]);
  });
});

describe("legacy FRED metro-area IDs (regression for the 'unemployment' leak)", () => {
  // Five FRED sources predate the canonical `metro_<cbsa>` naming
  // convention and carry the DC-metro (Washington-Arlington-Alexandria,
  // CBSA 47900) data under bespoke filenames. Without an explicit
  // override they fall through every geo parser and surface in the
  // composer's default list — typing "unemployment" leaked
  // fred/dc_unemployment_rate alongside the US national rate.
  // The LEGACY_METRO_IDS map in geographic-regions.ts pins them to
  // CBSA 47900 so library.json synthesizes the right tags. These tests
  // lock that pinning down so a future move/rename doesn't silently
  // re-open the leak.
  // fred/dc_case_shiller intentionally absent: removed 2026-05-27
  // (third-party copyright). Leaving its parsing logic intact in
  // geographic-regions.ts via the legacy-mapping pattern means a
  // re-add would just plug back in, but the source itself is gone.
  const LEGACY_DC_IDS = [
    "fred/dc_unemployment_rate",
    "fred/dc_payrolls",
    "fred/dc_cpi",
    "fred/dc_median_listing",
  ];

  it.each(LEGACY_DC_IDS)(
    "parses %s as a metro source pinned to CBSA 47900",
    (id) => {
      const parsed = parseMetroSourceId(id);
      expect(parsed).not.toBeNull();
      expect(parsed!.cbsa).toBe("47900");
      // Pipeline tag is informational — the renderer uses it for
      // provenance but the composer's hide-by-default logic only
      // needs the cbsa for the metro:<cbsa> tag.
      expect(parsed!.pipeline).toBe("fred_series");
    },
  );

  it.each(LEGACY_DC_IDS)(
    "%s gets both METRO_TAG and metro:47900 from metroTagsFor",
    (id) => {
      expect(metroTagsFor(id)).toEqual([METRO_TAG, `${METRO_TAG}:47900`]);
    },
  );

  it.each(LEGACY_DC_IDS)("%s is recognized as a metro source", (id) => {
    expect(isMetroSourceId(id)).toBe(true);
  });

  it("doesn't accidentally match other fred/dc_* IDs that aren't metro-specific", () => {
    // A hypothetical national-level FRED series whose ID happens to
    // start with "dc_" shouldn't get auto-tagged. The override map
    // is closed-set; unrecognized IDs fall through to the regex
    // patterns (which won't match a non-cbsa filename) and return
    // null. The composer treats those as non-geo, US-national by
    // default — exactly what we want for an unknown series.
    expect(parseMetroSourceId("fred/dc_treasury_rate_unknown")).toBeNull();
    expect(isMetroSourceId("fred/dc_treasury_rate_unknown")).toBe(false);
  });
});
