import { describe, it, expect } from "vitest";
import { synthesizeSourceHints, type SourceMetaForHints } from "./source-hints";
import { METRO_TAG } from "./geographic-regions";
import { CD_TAG, STATE_TAG } from "./congressional-districts";
import { COUNTY_TAG } from "./county-sources";
import { COUNTRY_TAG } from "./countries";

// Minimal source factory — only the fields detectLevel + detectSeries
// read.
function src(
  id: string,
  name: string,
  tags: ReadonlyArray<string>,
): SourceMetaForHints {
  return { id, name, tags };
}

describe("synthesizeSourceHints — overall shape", () => {
  it("returns an empty list when no recognizable sources at any geo level", () => {
    const hints = synthesizeSourceHints(
      [
        src("fred/cpi", "CPI", []),
        src("fred/us_10y", "US 10-year Treasury yield", ["us"]),
      ],
      false,
    );
    expect(hints).toEqual([]);
  });

  it("emits the map-only tract + bg hints with mapLevelsAvailable=true", () => {
    // Tract / BG have no per-source rows (map-only); the
    // hint set comes from CHOROPLETH_SERIES regardless of input.
    const hints = synthesizeSourceHints([], true);
    // tract: 4 indicators × 1 level + bg: 2 indicators × 1 level = 6.
    expect(hints.length).toBe(6);
    expect(hints.every((h) => h.id.startsWith("_hint/tract") || h.id.startsWith("_hint/bg"))).toBe(true);
  });

  it("emits one hint per (level, series) pair — not one mega-hint per level", () => {
    // Two metro sources, two different series → two metro hints.
    // (This is the whole point of the per-series refactor — one
    // mega-hint per level lost the home-prices-by-MSA signal.)
    const hints = synthesizeSourceHints(
      [
        src("bls/metro_unemployment_47900", "Metro unemployment", [METRO_TAG]),
        src("fred/dc_case_shiller", "DC Case-Shiller", [METRO_TAG]),
      ],
      false,
    );
    expect(hints.length).toBe(2);
    expect(hints.map((h) => h.id).sort()).toEqual([
      "_hint/metro__case_shiller",
      "_hint/metro__unemployment",
    ]);
  });

  it("every hint carries kind='hint' and empty tags", () => {
    const hints = synthesizeSourceHints(
      [src("bls/state_unemployment_va", "VA unemployment", [STATE_TAG])],
      false,
    );
    for (const h of hints) {
      expect(h.kind).toBe("hint");
      expect(h.tags).toEqual([]);
    }
  });

  it("ids follow the `_hint/<level>__<series>` shape", () => {
    const hints = synthesizeSourceHints(
      [
        src("bls/state_unemployment_va", "VA unemployment", [STATE_TAG]),
        src("worldbank_gdp/germany", "Germany GDP", [COUNTRY_TAG]),
      ],
      false,
    );
    for (const h of hints) {
      expect(h.id).toMatch(/^_hint\/[a-z]+__[a-z_]+$/);
    }
  });

  it("sorts by level priority (country → state → cd → metro → county → tract → bg)", () => {
    const hints = synthesizeSourceHints(
      [
        src("bls/county_unemployment_arlington_va", "Arlington unemp", [COUNTY_TAG]),
        src("bls/metro_unemployment_47900", "Metro unemp", [METRO_TAG]),
        src("bls/state_unemployment_va", "VA unemp", [STATE_TAG]),
        src("usaspending/district_va_08", "VA-08 spending", [CD_TAG]),
        src("worldbank_extended/unemployment_chn", "China unemployment", [COUNTRY_TAG]),
      ],
      true,
    );
    // Just look at the level prefix of each id, in render order.
    const levelSeq = hints.map((h) => h.id.split("__")[0].replace("_hint/", ""));
    // Country should appear before state; state before cd; cd before metro; etc.
    expect(levelSeq.indexOf("country")).toBeLessThan(levelSeq.indexOf("state"));
    expect(levelSeq.indexOf("state")).toBeLessThan(levelSeq.indexOf("cd"));
    expect(levelSeq.indexOf("cd")).toBeLessThan(levelSeq.indexOf("metro"));
    expect(levelSeq.indexOf("metro")).toBeLessThan(levelSeq.indexOf("county"));
    expect(levelSeq.indexOf("county")).toBeLessThan(levelSeq.indexOf("tract"));
    expect(levelSeq.indexOf("tract")).toBeLessThan(levelSeq.indexOf("bg"));
  });
});

describe("synthesizeSourceHints — per-series hint copy", () => {
  it("name is '<Series label> — by <level name>'", () => {
    const hints = synthesizeSourceHints(
      [src("fred/dc_case_shiller", "DC Case-Shiller", [METRO_TAG])],
      false,
    );
    expect(hints).toHaveLength(1);
    expect(hints[0].name).toBe(
      "Case-Shiller home price index — by US metro area (MSA)",
    );
  });

  it("description reads like a real source description, minus the geo specifics", () => {
    // The construction pattern: "<series-descriptive prefix>. Available
    // for each <level>. <N> <levels> tracked. <chip instruction>."
    // This is the literal user requirement — the hint's wording
    // should mirror the way the real source's description reads.
    const hints = synthesizeSourceHints(
      [
        src("bls/state_unemployment_va", "VA unemployment", [STATE_TAG]),
      ],
      false,
    );
    const desc = hints[0].description;
    expect(desc).toMatch(/Headline unemployment rate/);
    expect(desc).toMatch(/Available for each US state/);
    expect(desc).toMatch(/Click the States & districts chip/);
  });

  it("home prices at MSA level produces a 'home prices — by MSA' hint that mentions Case-Shiller", () => {
    // The user-reported gap: typing "home prices" should make it
    // obvious that MSA-level data exists. This test pins that
    // discoverability path end-to-end: the hint exists, names the
    // series, names the level, and the searchText is hit by the
    // "home prices" query the user would actually type.
    const hints = synthesizeSourceHints(
      [src("fred/dc_case_shiller", "DC Case-Shiller", [METRO_TAG])],
      false,
    );
    expect(hints).toHaveLength(1);
    expect(hints[0].name).toContain("Case-Shiller");
    expect(hints[0].name).toContain("MSA");
    // "home prices" — substring search should match the hint.
    expect(hints[0].searchText).toContain("home prices");
  });

  it("includes the distinct-geo count in the description when known", () => {
    const hints = synthesizeSourceHints(
      [
        src("bls/metro_unemployment_10180", "MSA 10180", [METRO_TAG]),
        src("bls/metro_unemployment_47900", "MSA 47900", [METRO_TAG]),
        src("bls/metro_unemployment_35620", "MSA 35620", [METRO_TAG]),
      ],
      false,
    );
    expect(hints[0].description).toMatch(/3 metro areas tracked/);
  });

  it("never includes a specific city, state, or county name in the description", () => {
    // Locks in the user-stated invariant: no geo specifics ever
    // leak into the hint text. Catches sloppy template strings
    // that pulled the source's name verbatim instead of a clean
    // SERIES_DESCRIPTIONS lookup.
    const FORBIDDEN = [
      "alexandria",
      "arlington",
      "detroit",
      "chicago",
      "germany",
      "japan",
      "california",
      "virginia",
      "texas",
      "washington",
      "47900",
      "va-08",
    ];
    const hints = synthesizeSourceHints(
      [
        src("bls/metro_unemployment_47900", "DC metro unemployment", [METRO_TAG]),
        src("bls/county_unemployment_alexandria_va", "Alexandria unemp", [COUNTY_TAG]),
        src("bls/state_unemployment_va", "Virginia unemployment", [STATE_TAG]),
        src("worldbank_gdp/germany", "Germany GDP", [COUNTRY_TAG]),
        src("fred/dc_case_shiller", "DC Case-Shiller", [METRO_TAG]),
      ],
      true,
    );
    for (const h of hints) {
      const lower = (h.description + " " + h.name).toLowerCase();
      for (const word of FORBIDDEN) {
        expect(lower, `"${word}" leaked into hint ${h.id}`).not.toContain(word);
      }
    }
  });

  it("county hint description says 'type the county name' (no chip exists yet)", () => {
    const hints = synthesizeSourceHints(
      [src("bls/county_unemployment_arlington_va", "Arlington unemp", [COUNTY_TAG])],
      false,
    );
    expect(hints[0].chip).toBe("county");
    expect(hints[0].description).toMatch(/county name/i);
  });

  it("tract + bg hints point users at the Maps tab", () => {
    const hints = synthesizeSourceHints([], true);
    const tractHint = hints.find((h) => h.id.startsWith("_hint/tract"));
    const bgHint = hints.find((h) => h.id.startsWith("_hint/bg"));
    expect(tractHint?.chip).toBe("maps-tab");
    expect(tractHint?.description).toMatch(/Maps tab/);
    expect(bgHint?.chip).toBe("maps-tab");
    expect(bgHint?.description).toMatch(/Maps tab/);
  });
});

describe("synthesizeSourceHints — searchText match coverage", () => {
  it("series substring matches the hint's searchText", () => {
    const hints = synthesizeSourceHints(
      [src("bls/metro_unemployment_47900", "Metro unemp", [METRO_TAG])],
      false,
    );
    expect(hints[0].searchText).toContain("unemployment");
  });

  it("series aliases land in searchText (jobs → payrolls + unemployment)", () => {
    const hints = synthesizeSourceHints(
      [src("bls/state_payrolls_va", "VA payrolls", [STATE_TAG])],
      false,
    );
    expect(hints[0].searchText).toContain("jobs");
  });

  it("level synonyms land in searchText (msa → metro)", () => {
    const hints = synthesizeSourceHints(
      [src("bls/metro_unemployment_47900", "Metro unemp", [METRO_TAG])],
      false,
    );
    expect(hints[0].searchText).toContain("msa");
    expect(hints[0].searchText).toContain("metropolitan");
  });

  it("housing aliases on Case-Shiller surface for 'home prices' + 'housing' queries", () => {
    const hints = synthesizeSourceHints(
      [src("fred/dc_case_shiller", "DC Case-Shiller", [METRO_TAG])],
      false,
    );
    expect(hints[0].searchText).toContain("housing");
    expect(hints[0].searchText).toContain("home prices");
  });
});

describe("synthesizeSourceHints — regression for the 'unemployment' search leak", () => {
  it("every level with unemployment data emits an unemployment hint that matches the 'unemployment' query", () => {
    const hints = synthesizeSourceHints(
      [
        src("bls/state_unemployment_va", "VA unemployment", [STATE_TAG]),
        src("bls/metro_unemployment_47900", "MSA unemployment", [METRO_TAG]),
        src("bls/county_unemployment_arlington_va", "Arlington unemp", [COUNTY_TAG]),
        src("worldbank_extended/unemployment_germany", "Germany unemployment", [COUNTRY_TAG]),
      ],
      false,
    );
    const unemploymentHints = hints.filter((h) =>
      h.id.endsWith("__unemployment"),
    );
    expect(unemploymentHints.length).toBe(4);
    for (const h of unemploymentHints) {
      expect(h.searchText).toContain("unemployment");
    }
  });

  it("the home-prices-by-MSA discoverability path is intact", () => {
    // Same shape of regression test for the explicit user-reported
    // case: MSA-level home prices need a clearly-named hint.
    const hints = synthesizeSourceHints(
      [
        src("fred/dc_case_shiller", "Case-Shiller home prices", [METRO_TAG]),
        src("fred/dc_median_listing", "Median home listing price", [METRO_TAG]),
      ],
      false,
    );
    // Two distinct series → two hints.
    expect(hints).toHaveLength(2);
    const names = hints.map((h) => h.name);
    expect(names.some((n) => n.includes("Case-Shiller"))).toBe(true);
    expect(names.some((n) => n.includes("Median home listing"))).toBe(true);
    // Both should match "home prices" via the alias path.
    for (const h of hints) {
      expect(h.searchText).toContain("home prices");
    }
  });
});

describe("synthesizeSourceHints — chip routing", () => {
  it.each([
    ["metro", METRO_TAG, "metro"],
    ["country", COUNTRY_TAG, "country"],
    ["state", STATE_TAG, "cd"],
    ["county", COUNTY_TAG, "county"],
    ["cd", CD_TAG, "cd"],
  ] as const)(
    "a %s-tagged source routes its hint to the %s chip path",
    (_levelName, tag, expectedChip) => {
      const hints = synthesizeSourceHints(
        [src(`fake/${tag}_unemployment_x`, "Fake unemployment", [tag])],
        false,
      );
      expect(hints[0].chip).toBe(expectedChip);
    },
  );

  it("tract + bg hints route to the maps-tab", () => {
    const hints = synthesizeSourceHints([], true);
    for (const h of hints) {
      expect(h.chip).toBe("maps-tab");
    }
  });
});
