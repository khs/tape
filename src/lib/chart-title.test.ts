import { describe, it, expect } from "vitest";
import {
  deriveAutoTitle,
  isTitleAuto,
  type SourceForTitle,
  type SourceLookup,
} from "./chart-title";

// Tiny in-memory source catalog matching the shape compose.astro
// passes through. shortName-first preference lets the test verify
// the right field wins.
const SOURCES: Record<string, SourceForTitle> = {
  "fred/dgs10": {
    name: "US 10-year Treasury yield",
    shortName: "10Y",
  },
  "fred/dgs2": {
    name: "US 2-year Treasury yield",
    shortName: "2Y",
  },
  "fred/cpi_yoy": {
    name: "CPI year-over-year (US, all urban consumers)",
    shortName: "CPI YoY",
  },
  // A source without a shortName — verifies the name fallback.
  "usaspending/total": {
    name: "Total federal outlays",
  },
  // A source missing both name + shortName — verifies the id fallback.
  "weird/no-meta": {},
};

const lookup: SourceLookup = (sid) => SOURCES[sid];

describe("deriveAutoTitle", () => {
  it("returns empty string when no sources are picked", () => {
    expect(deriveAutoTitle([], null, lookup)).toBe("");
    expect(deriveAutoTitle([], "divide", lookup)).toBe("");
  });

  it("uses shortName-first for a single source", () => {
    // "10Y" reads better than "US 10-year Treasury yield" in a tile.
    expect(deriveAutoTitle(["fred/dgs10"], null, lookup)).toBe("10Y");
  });

  it("falls back to name when shortName is missing", () => {
    expect(deriveAutoTitle(["usaspending/total"], null, lookup)).toBe(
      "Total federal outlays",
    );
  });

  it("falls back to the source id when both name and shortName are missing", () => {
    expect(deriveAutoTitle(["weird/no-meta"], null, lookup)).toBe(
      "weird/no-meta",
    );
  });

  it("falls back to the source id when the source isn't in the lookup", () => {
    expect(deriveAutoTitle(["unknown/source"], null, lookup)).toBe(
      "unknown/source",
    );
  });

  it("composes 'A / B' for divide on two sources", () => {
    expect(
      deriveAutoTitle(["fred/dgs10", "fred/dgs2"], "divide", lookup),
    ).toBe("10Y / 2Y");
  });

  it("composes 'A + B' for sum on two sources", () => {
    expect(
      deriveAutoTitle(["fred/dgs10", "fred/dgs2"], "sum", lookup),
    ).toBe("10Y + 2Y");
  });

  it("composes 'A − B' for diff with the Unicode minus (not the hyphen)", () => {
    // U+2212, not U+002D. Same legibility rationale as axis labels.
    const result = deriveAutoTitle(
      ["fred/dgs10", "fred/dgs2"],
      "diff",
      lookup,
    );
    expect(result).toBe("10Y − 2Y");
    expect(result).toContain("−");
    expect(result).not.toContain("- 2Y");
  });

  it("preserves argument order for non-commutative ops", () => {
    // divide and diff produce different titles when the user swaps.
    expect(
      deriveAutoTitle(["fred/dgs2", "fred/dgs10"], "divide", lookup),
    ).toBe("2Y / 10Y");
    expect(
      deriveAutoTitle(["fred/dgs2", "fred/dgs10"], "diff", lookup),
    ).toBe("2Y − 10Y");
  });

  it("ignores op for single-source charts (the op is meaningless there)", () => {
    expect(deriveAutoTitle(["fred/dgs10"], "divide", lookup)).toBe("10Y");
    expect(deriveAutoTitle(["fred/dgs10"], "sum", lookup)).toBe("10Y");
  });

  it("uses ' + '-joined names for 2-source no-op charts", () => {
    // Matches the hover-merge format so merge-built titles keep
    // tracking on further source adds. (Verified by isTitleAuto.)
    expect(
      deriveAutoTitle(["fred/dgs10", "fred/dgs2"], null, lookup),
    ).toBe("10Y + 2Y");
  });

  it("uses ' + '-joined names for 3+ source charts regardless of op", () => {
    // op only kicks in for exactly 2 sources; the schema enforces
    // this in the composer. With 3+ sources, fall back to the joined
    // list, ignoring op.
    expect(
      deriveAutoTitle(
        ["fred/dgs10", "fred/dgs2", "fred/cpi_yoy"],
        null,
        lookup,
      ),
    ).toBe("10Y + 2Y + CPI YoY");
    expect(
      deriveAutoTitle(
        ["fred/dgs10", "fred/dgs2", "fred/cpi_yoy"],
        "divide",
        lookup,
      ),
    ).toBe("10Y + 2Y + CPI YoY");
  });
});

describe("isTitleAuto", () => {
  it("returns true for an empty title regardless of sources", () => {
    expect(isTitleAuto("", [], null, lookup)).toBe(true);
    expect(isTitleAuto("", ["fred/dgs10"], null, lookup)).toBe(true);
  });

  it("returns true when title equals what deriveAutoTitle would produce", () => {
    // Fresh "10Y" chart — the title matches the auto-derive, so
    // source-changes should keep updating it.
    expect(isTitleAuto("10Y", ["fred/dgs10"], null, lookup)).toBe(true);
    // op'd auto-derived title also tracks.
    expect(
      isTitleAuto(
        "10Y / 2Y",
        ["fred/dgs10", "fred/dgs2"],
        "divide",
        lookup,
      ),
    ).toBe(true);
  });

  it("returns false when the title has been customized", () => {
    // A title that's nothing like the auto-derive is clearly user-typed.
    expect(
      isTitleAuto("Long-rates regime", ["fred/dgs10"], null, lookup),
    ).toBe(false);
  });

  it("returns false when the source set was swapped and the title is now stale", () => {
    // User started on 10Y (auto-title was "10Y"), swapped to CPI YoY.
    // The title "10Y" no longer matches what deriveAutoTitle returns
    // for the CURRENT sources, so it's effectively custom-relative to
    // the new set — the composer locks it down.
    expect(
      isTitleAuto("10Y", ["fred/cpi_yoy"], null, lookup),
    ).toBe(false);
  });

  it("flips back to true after the user clears the field", () => {
    // Real-world flow: title was "My custom name", user backspaces
    // it down to "". The composer treats empty as "auto again".
    expect(
      isTitleAuto("", ["fred/dgs10"], null, lookup),
    ).toBe(true);
  });

  it("recognizes hover-merge 'A + B' titles as auto so merges keep tracking", () => {
    // The hover-merge feature labels new merged charts as "A + B"
    // using shortName-first. deriveAutoTitle uses the same convention,
    // so the merge-built title is treated as auto and keeps tracking
    // on subsequent source-list edits. (Originally a real bug: the
    // pre-fix derive used " vs. " for 2-source no-op, so merge
    // titles failed the auto check and never tracked.)
    expect(
      isTitleAuto("10Y + 2Y", ["fred/dgs10", "fred/dgs2"], null, lookup),
    ).toBe(true);
  });
});
