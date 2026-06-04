/**
 * Tests for the county/city name disambiguator.
 *
 * The 6 documented collisions are nailed down case-by-case so a
 * future rewrite (e.g. switching the bucket key, changing the FIPS
 * threshold, replacing the suffix copy) gets caught before it ships.
 * Map tooltips are silent failures: nobody catches "Fairfax"
 * appearing twice unless they look closely at the right map.
 */
import { describe, it, expect } from "vitest";
import {
  disambiguateCountyCityNames,
  isIndependentCityGeoid,
} from "./disambiguate-county-city";

describe("isIndependentCityGeoid", () => {
  it("returns true for VA independent cities (county-FIPS >= 510)", () => {
    // Richmond city, Roanoke city, Fairfax city, Falls Church city
    expect(isIndependentCityGeoid("51760")).toBe(true);
    expect(isIndependentCityGeoid("51770")).toBe(true);
    expect(isIndependentCityGeoid("51600")).toBe(true);
    expect(isIndependentCityGeoid("51610")).toBe(true);
  });

  it("returns true for MD Baltimore city and MO St. Louis city", () => {
    expect(isIndependentCityGeoid("24510")).toBe(true);
    expect(isIndependentCityGeoid("29510")).toBe(true);
  });

  it("returns false for regular counties (county-FIPS < 510)", () => {
    // Fairfax County (059), Baltimore County (005), St. Louis County (189)
    expect(isIndependentCityGeoid("51059")).toBe(false);
    expect(isIndependentCityGeoid("24005")).toBe(false);
    expect(isIndependentCityGeoid("29189")).toBe(false);
    // Common low FIPS
    expect(isIndependentCityGeoid("06001")).toBe(false); // Alameda CA
    expect(isIndependentCityGeoid("51001")).toBe(false); // Accomack VA
  });

  it("returns false for non-5-digit GEOIDs (tract, block-group, state)", () => {
    // 11-digit tract GEOID, even with a high last-3 digits, is not a
    // 5-digit county-level id.
    expect(isIndependentCityGeoid("51059920100")).toBe(false);
    expect(isIndependentCityGeoid("51")).toBe(false); // bare state FIPS
    expect(isIndependentCityGeoid("")).toBe(false);
  });

  it("returns false at the upper threshold boundary (>840)", () => {
    // 850+ are unused at the county level; treat as non-city to stay
    // conservative on the suffix.
    expect(isIndependentCityGeoid("51999")).toBe(false);
  });
});

describe("disambiguateCountyCityNames", () => {
  it("disambiguates all 6 documented county/independent-city collisions", () => {
    const entries = [
      { id: "24005", name: "Baltimore" }, // MD Baltimore County
      { id: "24510", name: "Baltimore" }, // MD Baltimore city
      { id: "29189", name: "St. Louis" }, // MO St. Louis County
      { id: "29510", name: "St. Louis" }, // MO St. Louis city
      { id: "51059", name: "Fairfax" }, // VA Fairfax County
      { id: "51600", name: "Fairfax" }, // VA Fairfax city
      { id: "51067", name: "Franklin" }, // VA Franklin County
      { id: "51620", name: "Franklin" }, // VA Franklin city
      { id: "51159", name: "Richmond" }, // VA Richmond County
      { id: "51760", name: "Richmond" }, // VA Richmond city (capital)
      { id: "51161", name: "Roanoke" }, // VA Roanoke County
      { id: "51770", name: "Roanoke" }, // VA Roanoke city
    ];
    const overrides = disambiguateCountyCityNames(entries);
    expect(overrides.get("24005")).toBe("Baltimore (county)");
    expect(overrides.get("24510")).toBe("Baltimore (city)");
    expect(overrides.get("29189")).toBe("St. Louis (county)");
    expect(overrides.get("29510")).toBe("St. Louis (city)");
    expect(overrides.get("51059")).toBe("Fairfax (county)");
    expect(overrides.get("51600")).toBe("Fairfax (city)");
    expect(overrides.get("51067")).toBe("Franklin (county)");
    expect(overrides.get("51620")).toBe("Franklin (city)");
    expect(overrides.get("51159")).toBe("Richmond (county)");
    expect(overrides.get("51760")).toBe("Richmond (city)");
    expect(overrides.get("51161")).toBe("Roanoke (county)");
    expect(overrides.get("51770")).toBe("Roanoke (city)");
    expect(overrides.size).toBe(12);
  });

  it("returns an empty map when there are no collisions", () => {
    // A typical state's worth of counties, all uniquely named.
    const entries = [
      { id: "06001", name: "Alameda" },
      { id: "06013", name: "Contra Costa" },
      { id: "06037", name: "Los Angeles" },
      { id: "06075", name: "San Francisco" },
    ];
    expect(disambiguateCountyCityNames(entries).size).toBe(0);
  });

  it("does NOT suffix single-occurrence independent cities (e.g. Falls Church)", () => {
    // Falls Church City is the only Falls Church in VA. The
    // disambiguator should leave it alone — adding " (city)" to the
    // sole occurrence reads awkwardly and the original code
    // explicitly skipped this case.
    const entries = [
      { id: "51610", name: "Falls Church City" },
      { id: "51059", name: "Fairfax" },
    ];
    expect(disambiguateCountyCityNames(entries).size).toBe(0);
  });

  it("does NOT collide names across states with the same name", () => {
    // Franklin appears as a county name in many states. Each instance
    // is unique within its state and shouldn't get suffixed.
    const entries = [
      { id: "12039", name: "Franklin" }, // Florida Franklin County
      { id: "13119", name: "Franklin" }, // Georgia Franklin County
      { id: "16059", name: "Franklin" }, // Idaho Franklin County
      { id: "39049", name: "Franklin" }, // Ohio Franklin County
    ];
    // All have unique state FIPS prefixes, so no in-state collision.
    expect(disambiguateCountyCityNames(entries).size).toBe(0);
  });

  it("ignores tract-level GEOIDs (11-digit) entirely", () => {
    // Two tracts with the same name in the same state should NOT be
    // flagged — tract names like "1.01" repeat across counties and
    // the suffix logic doesn't apply.
    const entries = [
      { id: "51059910100", name: "Census Tract 9101" },
      { id: "51059910101", name: "Census Tract 9101" },
    ];
    expect(disambiguateCountyCityNames(entries).size).toBe(0);
  });

  it("ignores empty or malformed entries", () => {
    const entries = [
      { id: "", name: "Fairfax" },
      { id: "51059", name: "" },
      { id: "51059", name: "Fairfax" },
      { id: "51600", name: "Fairfax" },
    ];
    // Only the two well-formed 5-digit entries collide.
    const overrides = disambiguateCountyCityNames(entries);
    expect(overrides.size).toBe(2);
    expect(overrides.get("51059")).toBe("Fairfax (county)");
    expect(overrides.get("51600")).toBe("Fairfax (city)");
  });

  it("is idempotent — running twice on an already-suffixed list doesn't double-suffix", () => {
    // The renderer can legitimately call this after a partial mutation
    // (e.g. dialog reopen). Names ending in ")" are passed through.
    const entries = [
      { id: "51059", name: "Fairfax (county)" },
      { id: "51600", name: "Fairfax (city)" },
    ];
    // Same state, same key after the suffix? No — keys differ because
    // names already differ. Empty result expected.
    const overrides = disambiguateCountyCityNames(entries);
    expect(overrides.size).toBe(0);
  });

  it("guard against double-suffix when only one entry was already suffixed", () => {
    // Asymmetric: pre-suffixed county + un-suffixed city. The city
    // should still be flagged (its peer's name is different so they
    // don't bucket together — and that's fine: it's already
    // disambiguated). Net: no override needed.
    const entries = [
      { id: "51059", name: "Fairfax (county)" },
      { id: "51600", name: "Fairfax" },
    ];
    expect(disambiguateCountyCityNames(entries).size).toBe(0);
  });

  it("only modifies the colliding pair within a state, not other names", () => {
    const entries = [
      { id: "51059", name: "Fairfax" }, // collides
      { id: "51600", name: "Fairfax" }, // collides
      { id: "51001", name: "Accomack" }, // unique
      { id: "51003", name: "Albemarle" }, // unique
    ];
    const overrides = disambiguateCountyCityNames(entries);
    expect(overrides.has("51059")).toBe(true);
    expect(overrides.has("51600")).toBe(true);
    expect(overrides.has("51001")).toBe(false);
    expect(overrides.has("51003")).toBe(false);
  });

  it("returns an empty map for an empty input list", () => {
    expect(disambiguateCountyCityNames([]).size).toBe(0);
  });
});
