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
