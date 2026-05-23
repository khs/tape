/**
 * Smoke-tests for the special-tract-name lookup. The data is hand-
 * curated so the tests aren't trying to verify correctness of the
 * geographic identification — they're lockdown tests on the
 * lookup-function shape + a handful of high-confidence entries to
 * catch accidental key mutations during future edits.
 */
import { describe, it, expect } from "vitest";
import {
  SPECIAL_TRACT_NAMES,
  specialTractName,
} from "./special-tract-names";

describe("specialTractName", () => {
  it("returns the curated name for a known DMV GEOID", () => {
    expect(specialTractName("11001980000")).toBe("National Mall");
    expect(specialTractName("51013980100")).toBe(
      "Arlington National Cemetery + Pentagon",
    );
    expect(specialTractName("51107980100")).toBe(
      "Dulles International Airport (IAD)",
    );
  });

  it("returns null for an unknown GEOID", () => {
    // A made-up GEOID — not in the table.
    expect(specialTractName("99999999999")).toBeNull();
  });

  it("returns null for an empty string", () => {
    expect(specialTractName("")).toBeNull();
  });

  it("returns null for a populated-tract GEOID (no entry)", () => {
    // A real tract from Arlington (51013) that's a regular
    // residential tract — won't be in the special-name table because
    // it's not 9800-series. Should fall through cleanly.
    expect(specialTractName("51013100100")).toBeNull();
  });

  it("never collides keys with non-special tract numbers", () => {
    // Every entry's chars 5-6 must be '98' — the special-use marker.
    // This catches accidental typos like '98010' vs '90810' that
    // would otherwise silently mis-attribute a non-9800 tract.
    for (const geoid of Object.keys(SPECIAL_TRACT_NAMES)) {
      expect(geoid.slice(5, 7)).toBe("98");
      expect(geoid).toMatch(/^\d{11}$/);
    }
  });

  it("each entry's value is a non-empty human-readable string", () => {
    for (const [geoid, name] of Object.entries(SPECIAL_TRACT_NAMES)) {
      expect(name.length).toBeGreaterThan(0);
      // No trailing/leading whitespace (would render odd in tooltips).
      expect(name).toBe(name.trim());
      // No "Census Tract" prefix — that'd defeat the purpose of the
      // override. The whole point is to REPLACE the generic name.
      expect(name).not.toMatch(/^Census Tract/i);
      // Sanity: should look like a place name, not a GEOID.
      expect(name).not.toMatch(/^\d+$/);
      void geoid;
    }
  });
});
