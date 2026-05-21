import { describe, expect, it } from "vitest";
import {
  COUNTY_TAG,
  parseCountySourceId,
  isCountySourceId,
  countyTagsFor,
} from "./county-sources";

describe("parseCountySourceId", () => {
  it("parses a single-word county VA source", () => {
    const out = parseCountySourceId("bls/county_unemployment_arlington_va");
    expect(out).toEqual({
      pipeline: "bls",
      state: "VA",
      slug: "unemployment_arlington",
    });
  });

  it("parses a single-word county MD source", () => {
    const out = parseCountySourceId("bls/county_unemployment_montgomery_md");
    expect(out).toEqual({
      pipeline: "bls",
      state: "MD",
      slug: "unemployment_montgomery",
    });
  });

  it("parses a multi-word county slug (Prince George's)", () => {
    // The pipeline normalizes "Prince George's County, MD" to
    // prince_georges_md — multi-word counties keep their interior
    // underscores. The state captures the trailing 2 letters; the
    // slug is everything between "county_" and the state code.
    const out = parseCountySourceId(
      "bls/county_unemployment_prince_georges_md",
    );
    expect(out).toEqual({
      pipeline: "bls",
      state: "MD",
      slug: "unemployment_prince_georges",
    });
  });

  it("parses a multi-word county slug (Falls Church)", () => {
    const out = parseCountySourceId(
      "bls/county_unemployment_falls_church_va",
    );
    expect(out).toEqual({
      pipeline: "bls",
      state: "VA",
      slug: "unemployment_falls_church",
    });
  });

  it("returns null for non-bls pipelines", () => {
    // The county pattern is currently bls-only. ACS-county, FRED-county,
    // etc. would need new pipeline entries; until then they're not
    // recognized and stay outside the COUNTY_TAG umbrella.
    expect(
      parseCountySourceId("acs_county/poverty_arlington_va"),
    ).toBeNull();
    expect(
      parseCountySourceId("fred/county_unemployment_arlington_va"),
    ).toBeNull();
  });

  it("returns null when the trailing 2 letters aren't a real state", () => {
    // Anchor: rejects accidental matches. Two-letter strings that aren't
    // state codes (e.g. "zz") fail the STATE_CODE_SET membership check.
    expect(parseCountySourceId("bls/county_unemployment_foo_zz")).toBeNull();
  });

  it("returns null for state-level source IDs (no `county_` prefix)", () => {
    expect(parseCountySourceId("bls/state_unemployment_va")).toBeNull();
  });

  it("returns null for metro source IDs", () => {
    expect(parseCountySourceId("bls/metro_unemployment_31080")).toBeNull();
  });

  it("returns null for the empty string", () => {
    expect(parseCountySourceId("")).toBeNull();
  });

  it("returns null when the source ID has no slash", () => {
    expect(parseCountySourceId("county_unemployment_arlington_va")).toBeNull();
  });
});

describe("isCountySourceId", () => {
  it("returns true for a recognized county source", () => {
    expect(isCountySourceId("bls/county_unemployment_arlington_va")).toBe(true);
  });

  it("returns false for non-county sources", () => {
    expect(isCountySourceId("fred/cpi")).toBe(false);
    expect(isCountySourceId("bls/state_unemployment_va")).toBe(false);
    expect(isCountySourceId("")).toBe(false);
  });
});

describe("countyTagsFor", () => {
  it("returns [COUNTY_TAG] for a county source", () => {
    expect(countyTagsFor("bls/county_unemployment_arlington_va")).toEqual([
      COUNTY_TAG,
    ]);
  });

  it("returns an empty array for non-county sources", () => {
    expect(countyTagsFor("fred/cpi")).toEqual([]);
    expect(countyTagsFor("yahoo/aapl")).toEqual([]);
    expect(countyTagsFor("bls/state_unemployment_va")).toEqual([]);
    // Negative regression: the source that caused the original bug
    // report (Alexandria + Arlington leaking into general search).
    expect(countyTagsFor("bls/county_unemployment_alexandria_va")).toEqual([
      COUNTY_TAG,
    ]);
  });
});

describe("COUNTY_TAG exported value", () => {
  it("is the canonical us-county string", () => {
    // External callers (compose.astro filter, library.json.ts manifest
    // emission) compare against this exact string. A rename here without
    // updating those would silently turn off the county-source hide.
    expect(COUNTY_TAG).toBe("us-county");
  });
});
