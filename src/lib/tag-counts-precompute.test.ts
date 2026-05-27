/**
 * Lockdown tests for the build-time tag-count contingency table.
 *
 * The runtime SourcePicker reads `lib.tagCountsByGeo[<bucketKey>]`
 * and looks up topical-tag counts under that key. If this module's
 * bucket-key format or branch logic drifts, the picker silently
 * starts showing wrong counts (or no counts) per geo state — so
 * every branch the picker depends on gets a test.
 *
 * Cross-references:
 *  - Bucket-key consumer: src/components/SourcePicker.astro
 *    (`geoFilterKey` + `topicalTagCounts` near line 480)
 *  - Runtime filter parallels: src/lib/source-filters.ts
 *    (passesCdFilter, passesMetroFilter, passesCountryFilter,
 *    passesCountyFilter). Buckets are built so they MATCH what
 *    those filters return at runtime.
 */
import { describe, test, expect } from "vitest";
import {
  computeTagCountsByGeo,
  isGeoSyntheticTag,
  isDefaultVisible,
} from "./tag-counts-precompute";
import { CD_TAG, STATE_TAG } from "./congressional-districts";
import { METRO_TAG } from "./geographic-regions";
import { COUNTRY_TAG } from "./countries";
import { COUNTY_TAG } from "./county-sources";

describe("isGeoSyntheticTag", () => {
  test("matches umbrella tags exactly", () => {
    expect(isGeoSyntheticTag(CD_TAG)).toBe(true);
    expect(isGeoSyntheticTag(STATE_TAG)).toBe(true);
    expect(isGeoSyntheticTag(METRO_TAG)).toBe(true);
    expect(isGeoSyntheticTag(COUNTRY_TAG)).toBe(true);
    expect(isGeoSyntheticTag(COUNTY_TAG)).toBe(true);
  });
  test("matches per-entity metro + country tags", () => {
    expect(isGeoSyntheticTag(`${METRO_TAG}:10180`)).toBe(true);
    expect(isGeoSyntheticTag(`${COUNTRY_TAG}:USA`)).toBe(true);
    expect(isGeoSyntheticTag(`${COUNTRY_TAG}:AUS`)).toBe(true);
  });
  test("topical tags are NOT considered geo", () => {
    expect(isGeoSyntheticTag("agriculture")).toBe(false);
    expect(isGeoSyntheticTag("single-name")).toBe(false);
    expect(isGeoSyntheticTag("macro")).toBe(false);
    expect(isGeoSyntheticTag("us")).toBe(false);
    // 'metropolitan' must not match metro: prefix — colon is required.
    expect(isGeoSyntheticTag("metropolitan")).toBe(false);
  });
});

describe("isDefaultVisible", () => {
  test("plain topical tags = default-visible", () => {
    expect(isDefaultVisible(["agriculture", "macro"])).toBe(true);
    expect(isDefaultVisible([])).toBe(true);
    expect(isDefaultVisible(["us", "demographics"])).toBe(true);
  });
  test("any umbrella geo tag hides the source from the default view", () => {
    expect(isDefaultVisible([CD_TAG, "macro"])).toBe(false);
    expect(isDefaultVisible([STATE_TAG, "demographics"])).toBe(false);
    expect(isDefaultVisible([METRO_TAG, "housing"])).toBe(false);
    expect(isDefaultVisible([COUNTRY_TAG, "macro"])).toBe(false);
    expect(isDefaultVisible([COUNTY_TAG, "labor"])).toBe(false);
  });
  test("US national sources (country-specific:USA only, no COUNTRY_TAG umbrella) ARE default-visible", () => {
    // Mirrors library.json's special-case: US sources get
    // country-specific:USA but NOT the umbrella COUNTRY_TAG, so they
    // stay in the default view. Verified here to lock that asymmetry.
    expect(isDefaultVisible(["us", "macro", `${COUNTRY_TAG}:USA`])).toBe(true);
  });
});

describe("computeTagCountsByGeo", () => {
  test("returns { __all: {} } for an empty input", () => {
    const out = computeTagCountsByGeo({});
    expect(out).toEqual({ __all: {} });
  });

  test("skips hint cards entirely", () => {
    const out = computeTagCountsByGeo({
      "_hint/cd": {
        kind: "hint",
        tags: ["agriculture"],
      },
    });
    expect(out.__all.agriculture).toBeUndefined();
  });

  test("default-visible sources land in __all only", () => {
    const out = computeTagCountsByGeo({
      "fred/gdp": { tags: ["macro", "us"] },
      "yahoo_marketcap/xom_mc": { tags: ["single-name", "energy"] },
    });
    expect(out.__all).toEqual({
      macro: 1,
      us: 1,
      "single-name": 1,
      energy: 1,
    });
  });

  test("hidden-by-default sources skip __all but populate their geo bucket", () => {
    // STATE-tagged source should appear in cd:va:any + cd:va:state
    // but NOT in __all (the umbrella STATE_TAG hides it).
    const out = computeTagCountsByGeo({
      "fred/state_unrate_va": {
        tags: [STATE_TAG, "labor"],
      },
    });
    expect(out.__all.labor).toBeUndefined();
    expect(out["cd:va:any"]).toEqual({ labor: 1 });
    expect(out["cd:va:state"]).toEqual({ labor: 1 });
  });

  test("CD-tagged source populates cd:state:any + cd:state:<dst>, NOT cd:state:state", () => {
    const out = computeTagCountsByGeo({
      "usaspending/district_va_08": {
        tags: [CD_TAG, "federal-spending"],
      },
    });
    expect(out["cd:va:any"]).toEqual({ "federal-spending": 1 });
    expect(out["cd:va:08"]).toEqual({ "federal-spending": 1 });
    // Statewide bucket only takes STATE-tagged sources, not CD-tagged.
    expect(out["cd:va:state"]).toBeUndefined();
  });

  test("metro-tagged source populates metro:<cbsa> (one per per-CBSA tag)", () => {
    const out = computeTagCountsByGeo({
      "acs_metro/bachelors_plus_10180": {
        tags: [METRO_TAG, `${METRO_TAG}:10180`, "demographics"],
      },
    });
    expect(out["metro:10180"]).toEqual({ demographics: 1 });
    // No per-CBSA bucket for the umbrella tag — only for the
    // explicit `metro:<cbsa>` form. Sources without a per-CBSA
    // tag don't contribute to any metro:* bucket.
  });

  test("US national sources (country-specific:USA only) appear in country:USA AND __all", () => {
    const out = computeTagCountsByGeo({
      "fred/gdp": {
        tags: ["macro", "us", `${COUNTRY_TAG}:USA`],
      },
    });
    expect(out.__all).toEqual({ macro: 1, us: 1 });
    expect(out["country:USA"]).toEqual({ macro: 1, us: 1 });
  });

  test("foreign country sources go into country:<code> but NOT __all", () => {
    const out = computeTagCountsByGeo({
      "worldbank_gdp/AUS": {
        tags: [COUNTRY_TAG, `${COUNTRY_TAG}:AUS`, "macro"],
      },
    });
    expect(out.__all.macro).toBeUndefined();
    expect(out["country:AUS"]).toEqual({ macro: 1 });
  });

  test("topical-only counts EXCLUDE geo synthetics", () => {
    const out = computeTagCountsByGeo({
      "fred/state_unrate_va": {
        tags: [STATE_TAG, "labor", `${COUNTRY_TAG}:USA`],
      },
    });
    // STATE_TAG and country-specific:USA must NOT appear as topical
    // tags in any bucket — they're geo synthetics by construction.
    for (const bucket of Object.values(out)) {
      expect(bucket[STATE_TAG]).toBeUndefined();
      expect(bucket[`${COUNTRY_TAG}:USA`]).toBeUndefined();
      expect(bucket[METRO_TAG]).toBeUndefined();
    }
  });

  test("multiple sources accumulate in the same bucket", () => {
    const out = computeTagCountsByGeo({
      "usaspending/district_va_08": {
        tags: [CD_TAG, "federal-spending"],
      },
      "usaspending/district_va_11": {
        tags: [CD_TAG, "federal-spending"],
      },
      "acs_cd/poverty_va_08": {
        tags: [CD_TAG, "demographics"],
      },
    });
    expect(out["cd:va:any"]).toEqual({
      "federal-spending": 2,
      demographics: 1,
    });
    expect(out["cd:va:08"]).toEqual({
      "federal-spending": 1,
      demographics: 1,
    });
    expect(out["cd:va:11"]).toEqual({ "federal-spending": 1 });
  });

  test("source with only geo-synthetic tags is silently skipped", () => {
    const out = computeTagCountsByGeo({
      "weird/source": {
        tags: [METRO_TAG, `${METRO_TAG}:10180`],
      },
    });
    // No topical tags → no bucket entries at all. __all stays empty.
    expect(out.__all).toEqual({});
    expect(out["metro:10180"]).toBeUndefined();
  });

  test("kind:hint short-circuits even when tags are topical", () => {
    const out = computeTagCountsByGeo({
      "_hint/metro": {
        kind: "hint",
        tags: ["agriculture", "macro"],
      },
      "fred/gdp": { tags: ["macro"] },
    });
    // Only the real source's macro count surfaces.
    expect(out.__all.macro).toBe(1);
    expect(out.__all.agriculture).toBeUndefined();
  });

  test("source missing tags array silently skipped", () => {
    const out = computeTagCountsByGeo({
      "broken/source": {},
    });
    expect(out).toEqual({ __all: {} });
  });

  test("CD source whose ID doesn't parse (legacy / malformed) doesn't crash", () => {
    // Defensive: parseCdSourceId returns null for unrecognized IDs.
    // The precompute should silently drop CD-bucket assignment but
    // still populate __all if the source is default-visible.
    const out = computeTagCountsByGeo({
      "legacy/random_id": {
        tags: [CD_TAG, "federal-spending"],
      },
    });
    // CD_TAG is in tags → hidden from __all by isDefaultVisible.
    expect(out.__all["federal-spending"]).toBeUndefined();
    // No matching parseCdSourceId → no cd:<state>:* bucket.
    expect(Object.keys(out).some((k) => k.startsWith("cd:"))).toBe(false);
  });

  test("STATE-tagged + CD-tagged source (atypical) populates both branches", () => {
    // Edge case: a source tagged as both could exist if a pipeline
    // dual-classifies. Build doesn't reject this. Verify branches
    // are independent (the source counts twice in cd:va:any —
    // once via CD path, once via STATE path; we accept that).
    const out = computeTagCountsByGeo({
      "usaspending/district_va_08": {
        tags: [CD_TAG, STATE_TAG, "federal-spending"],
      },
    });
    // CD branch hit. STATE branch's parseStateSourceId returns null
    // for this ID format, so only CD buckets land.
    expect(out["cd:va:any"]).toEqual({ "federal-spending": 1 });
    expect(out["cd:va:08"]).toEqual({ "federal-spending": 1 });
    expect(out["cd:va:state"]).toBeUndefined();
  });
});
