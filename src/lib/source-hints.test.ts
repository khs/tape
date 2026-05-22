import { describe, it, expect } from "vitest";
import { synthesizeSourceHints, type SourceMetaForHints } from "./source-hints";
import { METRO_TAG } from "./geographic-regions";
import { CD_TAG, STATE_TAG } from "./congressional-districts";
import { COUNTY_TAG } from "./county-sources";
import { COUNTRY_TAG } from "./countries";

// Minimal source factory — only the fields detectLevel + detectSeries
// read. Real library.json entries carry many more fields (formatting,
// dataFile, etc.), but the hint builder doesn't.
function src(
  id: string,
  name: string,
  tags: ReadonlyArray<string>,
): SourceMetaForHints {
  return { id, name, tags };
}

describe("synthesizeSourceHints — overall shape", () => {
  it("returns an empty list when no sources at any geo level", () => {
    // National sources only → no hints. (We deliberately pass
    // tractLevelsAvailable=false too, since defaulted true would
    // emit the tract+BG hints regardless of input.)
    const hints = synthesizeSourceHints(
      [
        src("fred/cpi", "CPI", []),
        src("fred/us_10y", "US 10-year Treasury yield", ["us"]),
      ],
      false,
    );
    expect(hints).toEqual([]);
  });

  it("emits tract and block-group hints even with no sources, when tractLevelsAvailable=true", () => {
    // The choropleth machinery doesn't have per-source rows; the
    // hint surfaces the Maps-tab pathway regardless of input.
    const hints = synthesizeSourceHints([], true);
    const ids = hints.map((h) => h.id).sort();
    expect(ids).toEqual(["_hint/bg", "_hint/tract"]);
  });

  it("emits hints in country → state → cd → metro → county → tract → bg order", () => {
    const hints = synthesizeSourceHints(
      [
        src("bls/county_unemployment_arlington_va", "Arlington unemployment", [
          COUNTY_TAG,
        ]),
        src("bls/metro_unemployment_47900", "Metro unemployment", [
          METRO_TAG,
          `${METRO_TAG}:47900`,
        ]),
        src("bls/state_unemployment_va", "Virginia unemployment", [
          STATE_TAG,
        ]),
        src("usaspending/district_va_08", "VA-08 spending", [CD_TAG]),
        src("worldbank_gdp/germany", "Germany GDP", [COUNTRY_TAG]),
      ],
      true,
    );
    expect(hints.map((h) => h.id)).toEqual([
      "_hint/country",
      "_hint/state",
      "_hint/cd",
      "_hint/metro",
      "_hint/county",
      "_hint/tract",
      "_hint/bg",
    ]);
  });

  it("every hint carries the synthetic 'hint' kind and empty tags", () => {
    const hints = synthesizeSourceHints(
      [
        src("bls/state_unemployment_va", "VA unemployment", [STATE_TAG]),
      ],
      false,
    );
    for (const h of hints) {
      expect(h.kind).toBe("hint");
      expect(h.tags).toEqual([]);
    }
  });

  it("every hint id starts with the `_hint/` prefix", () => {
    const hints = synthesizeSourceHints(
      [
        src("bls/state_unemployment_va", "VA unemployment", [STATE_TAG]),
        src("worldbank_gdp/germany", "Germany GDP", [COUNTRY_TAG]),
      ],
      true,
    );
    for (const h of hints) {
      expect(h.id.startsWith("_hint/")).toBe(true);
    }
  });
});

describe("synthesizeSourceHints — series detection drives searchText", () => {
  it("metro unemployment source produces a hint whose searchText includes 'unemployment'", () => {
    // The original user-reported bug: searching 'unemployment'
    // returned a county source. After the fix it returns just
    // national + the hint cards. The hint's searchText must
    // contain the series name so the composer's substring match
    // surfaces it on that query.
    const hints = synthesizeSourceHints(
      [
        src("bls/metro_unemployment_47900", "DC metro unemployment", [
          METRO_TAG,
        ]),
      ],
      false,
    );
    expect(hints).toHaveLength(1);
    expect(hints[0].chip).toBe("metro");
    expect(hints[0].searchText).toContain("unemployment");
  });

  it("aggregates multiple series at the same level into one hint description", () => {
    const hints = synthesizeSourceHints(
      [
        src("bls/metro_unemployment_47900", "DC unemployment", [METRO_TAG]),
        src("bls/metro_payrolls_47900", "DC payrolls", [METRO_TAG]),
        src("usaspending/metro_47900", "DC metro federal spending", [
          METRO_TAG,
        ]),
      ],
      false,
    );
    const metro = hints.find((h) => h.id === "_hint/metro");
    expect(metro).toBeDefined();
    // All three series should appear in description copy.
    expect(metro!.description).toMatch(/unemployment/);
    expect(metro!.description).toMatch(/payrolls/);
    expect(metro!.description).toMatch(/federal spending/);
    // And in searchText so any of the three queries surfaces the
    // same hint.
    expect(metro!.searchText).toContain("unemployment");
    expect(metro!.searchText).toContain("payrolls");
    expect(metro!.searchText).toContain("spending");
  });

  it("series aliases land in searchText (jobs → payrolls/unemployment)", () => {
    // The composer's filter is plain substring — aliases make sure
    // a user typing 'jobs' surfaces the relevant hint even though
    // none of our source NAMES contain that word.
    const hints = synthesizeSourceHints(
      [
        src("bls/state_payrolls_va", "VA payrolls", [STATE_TAG]),
      ],
      false,
    );
    expect(hints[0].searchText).toContain("jobs");
  });

  it("level synonyms land in searchText (msa → metro)", () => {
    const hints = synthesizeSourceHints(
      [
        src("bls/metro_unemployment_47900", "DC unemployment", [METRO_TAG]),
      ],
      false,
    );
    expect(hints[0].searchText).toContain("msa");
    expect(hints[0].searchText).toContain("metropolitan");
  });
});

describe("synthesizeSourceHints — description copy", () => {
  it("never includes a specific city, state, or county name in the description", () => {
    // The point of the hint is to advertise the geo level
    // generically. If we leak "Alexandria", "Detroit", "California"
    // into the description we'd be doing the opposite — surfacing
    // a single specific row. The regex below is a heuristic but
    // catches the common leaks.
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
      "47900", // CBSA codes
      "va-08",
    ];
    const hints = synthesizeSourceHints(
      [
        src("bls/metro_unemployment_47900", "DC metro unemployment", [
          METRO_TAG,
        ]),
        src("bls/county_unemployment_alexandria_va", "Alexandria unemp", [
          COUNTY_TAG,
        ]),
        src("bls/state_unemployment_va", "Virginia unemployment", [STATE_TAG]),
        src("worldbank_gdp/germany", "Germany GDP", [COUNTRY_TAG]),
      ],
      true,
    );
    for (const h of hints) {
      const lower = h.description.toLowerCase();
      for (const word of FORBIDDEN) {
        expect(lower).not.toContain(word);
      }
    }
  });

  it("metro hint description mentions the count of metros", () => {
    // Three distinct CBSAs across two series → description should
    // say "3 tracked." Distinct-geo count means we count cbsas, not
    // (cbsa × series) source rows.
    const hints = synthesizeSourceHints(
      [
        src("bls/metro_unemployment_10180", "MSA 10180 unemployment", [METRO_TAG]),
        src("bls/metro_payrolls_10180", "MSA 10180 payrolls", [METRO_TAG]),
        src("bls/metro_unemployment_47900", "MSA 47900 unemployment", [METRO_TAG]),
        src("bls/metro_unemployment_35620", "MSA 35620 unemployment", [METRO_TAG]),
      ],
      false,
    );
    expect(hints[0].description).toMatch(/3 tracked/);
  });

  it("county hint instructs typing the name rather than engaging a chip", () => {
    // We don't have a county chip yet (8 counties total, all
    // DMV-area). The hint description has to tell the user the
    // right action — type the county name — not point at a chip
    // that doesn't exist.
    const hints = synthesizeSourceHints(
      [
        src("bls/county_unemployment_arlington_va", "Arlington unemp", [
          COUNTY_TAG,
        ]),
      ],
      false,
    );
    expect(hints[0].chip).toBe("county");
    expect(hints[0].description).toMatch(/county name/i);
  });

  it("tract + bg hints point users at the Maps tab", () => {
    const hints = synthesizeSourceHints([], true);
    const tract = hints.find((h) => h.id === "_hint/tract");
    const bg = hints.find((h) => h.id === "_hint/bg");
    expect(tract?.chip).toBe("maps-tab");
    expect(tract?.description).toMatch(/Maps tab/i);
    expect(bg?.chip).toBe("maps-tab");
    expect(bg?.description).toMatch(/Maps tab/i);
  });
});

describe("synthesizeSourceHints — chip routing", () => {
  it.each([
    ["metro", METRO_TAG, "_hint/metro"],
    ["country", COUNTRY_TAG, "_hint/country"],
    ["state", STATE_TAG, "_hint/state"],
    ["county", COUNTY_TAG, "_hint/county"],
    ["cd", CD_TAG, "_hint/cd"],
  ] as const)("emits a %s hint when at least one source carries the matching tag", (level, tag, expectedId) => {
    // Each geo level has its own tag. A single source with that tag
    // (plus a recognized series name) is enough to surface the
    // level's hint.
    const hints = synthesizeSourceHints(
      [
        src(`fake/${level}_unemployment_x`, "Fake unemployment", [tag]),
      ],
      false,
    );
    const got = hints.find((h) => h.id === expectedId);
    expect(got).toBeDefined();
  });

  it("the 'state' hint engages the CD chip (combined States & districts surface)", () => {
    // The composer puts statewide + per-CD sources behind the same
    // chip; engaging it surfaces both. So both the state hint and
    // the cd hint route to the same chip target.
    const hints = synthesizeSourceHints(
      [
        src("bls/state_unemployment_va", "VA unemployment", [STATE_TAG]),
      ],
      false,
    );
    expect(hints[0].chip).toBe("cd");
  });
});

describe("synthesizeSourceHints — regression for the 'unemployment' search leak", () => {
  // The class-of-bug this whole feature targets: a user types
  // "unemployment", every county/metro/state source is correctly
  // hidden by the chip filter, and they have no way to discover
  // the local data exists. The hints fill that gap. These
  // assertions lock down that the hints DO match the same query
  // that triggered the leak, so the discoverability story works
  // end-to-end.
  it("every geo level we cover with unemployment data emits a hint whose searchText matches 'unemployment'", () => {
    const hints = synthesizeSourceHints(
      [
        src("bls/state_unemployment_va", "VA unemployment", [STATE_TAG]),
        src("bls/metro_unemployment_47900", "MSA unemployment", [METRO_TAG]),
        src("bls/county_unemployment_arlington_va", "Arlington unemp", [
          COUNTY_TAG,
        ]),
        src(
          "worldbank_extended/cpi_inflation_china",
          "China CPI inflation",
          [COUNTRY_TAG],
        ),
        src(
          "worldbank_extended/unemployment_germany",
          "Germany unemployment",
          [COUNTRY_TAG],
        ),
      ],
      false,
    );
    // Each level should have a hint whose searchText is hit by
    // the literal "unemployment" substring.
    const levels = ["state", "metro", "county", "country"] as const;
    for (const lvl of levels) {
      const h = hints.find((hh) => hh.id === `_hint/${lvl}`);
      expect(h, `expected a hint for ${lvl}`).toBeDefined();
      expect(h!.searchText).toContain("unemployment");
    }
  });
});
