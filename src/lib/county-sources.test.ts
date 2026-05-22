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
      series: "unemployment",
      countyName: "arlington",
    });
  });

  it("parses a single-word county MD source", () => {
    const out = parseCountySourceId("bls/county_unemployment_montgomery_md");
    expect(out).toEqual({
      pipeline: "bls",
      state: "MD",
      slug: "unemployment_montgomery",
      series: "unemployment",
      countyName: "montgomery",
    });
  });

  it("parses a multi-word county slug (Prince George's)", () => {
    // The pipeline normalizes "Prince George's County, MD" to
    // prince_georges_md — multi-word counties keep their interior
    // underscores. The state captures the trailing 2 letters; the
    // slug is everything between "county_" and the state code.
    // countyName resolves to the multi-word slug; series strips it.
    const out = parseCountySourceId(
      "bls/county_unemployment_prince_georges_md",
    );
    expect(out).toEqual({
      pipeline: "bls",
      state: "MD",
      slug: "unemployment_prince_georges",
      series: "unemployment",
      countyName: "prince_georges",
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
      series: "unemployment",
      countyName: "falls_church",
    });
  });

  it("disambiguates Prince George's from Prince William (longest-first registry walk)", () => {
    // Both county slugs start with "prince_" — the registry is sorted
    // longest-first so the parser doesn't accidentally clip "Prince
    // William" to "prince" by matching against a shorter slug.
    expect(
      parseCountySourceId("bls/county_unemployment_prince_william_va")
        ?.countyName,
    ).toBe("prince_william");
    expect(
      parseCountySourceId("bls/county_unemployment_prince_georges_md")
        ?.countyName,
    ).toBe("prince_georges");
  });

  it("returns the full slug as countyName when the county isn't in the known registry", () => {
    // Defensive fallback: a county we haven't registered yet still
    // parses (so COUNTY_TAG synthesis works and the source stays
    // hidden by default), but countyName == slug so the search-
    // unlock heuristic loses precision until the registry is updated.
    const out = parseCountySourceId(
      "bls/county_unemployment_some_new_county_va",
    );
    expect(out).toEqual({
      pipeline: "bls",
      state: "VA",
      slug: "unemployment_some_new_county",
      series: "",
      countyName: "unemployment_some_new_county",
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

describe("search-unlock heuristic (regression for the 'unemployment' leak)", () => {
  // The composer's passesCountyFilter does:
  //   parsed.countyName.toLowerCase().includes(query.toLowerCase())
  // Earlier shipped behavior matched the WHOLE slug, which silently
  // bypassed the COUNTY_TAG hide-by-default: typing the series name
  // ("unemployment") caused every county source to surface alongside
  // the US national rate. The test below pins that fix down — the
  // series name MUST NOT match any of the eight counties we ship.
  //
  // This is a behavior contract, not just a parser invariant. If a
  // future refactor renames countyName or changes the match function,
  // the existing six counties' slugs would still pass parseCountySourceId
  // but the search-leak would silently re-appear. Asserting the
  // negative ("'unemployment' substring of countyName is false") catches
  // that class of regression at unit-test time, not at user-report time.
  const COUNTY_SOURCE_IDS = [
    "bls/county_unemployment_alexandria_va",
    "bls/county_unemployment_arlington_va",
    "bls/county_unemployment_fairfax_va",
    "bls/county_unemployment_falls_church_va",
    "bls/county_unemployment_loudoun_va",
    "bls/county_unemployment_montgomery_md",
    "bls/county_unemployment_prince_georges_md",
    "bls/county_unemployment_prince_william_va",
  ];

  it.each(COUNTY_SOURCE_IDS)(
    "searching 'unemployment' against %s county name does NOT match",
    (id) => {
      const parsed = parseCountySourceId(id);
      expect(parsed).not.toBeNull();
      // The literal regression: countyName must not contain the
      // series name. Were it to do so, passesCountyFilter would
      // surface the source on any 4+ char query that's a substring
      // of "unemployment".
      expect(parsed!.countyName.toLowerCase()).not.toContain("unemployment");
    },
  );

  it("searching by county name still matches its county", () => {
    // Positive control: the typed-name shortcut still works. The
    // hide-by-default exists so the user opts INTO county sources
    // by typing the county name; that path has to keep working.
    expect(
      parseCountySourceId(
        "bls/county_unemployment_alexandria_va",
      )?.countyName.toLowerCase(),
    ).toContain("alex");
    expect(
      parseCountySourceId(
        "bls/county_unemployment_prince_georges_md",
      )?.countyName.toLowerCase(),
    ).toContain("prince");
    expect(
      parseCountySourceId(
        "bls/county_unemployment_falls_church_va",
      )?.countyName.toLowerCase(),
    ).toContain("falls");
  });
});
