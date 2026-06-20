import { describe, it, expect } from "vitest";
import {
  pickVintages,
  combineShardVintages,
  vintageAtIndex,
  indicatorVintageRe,
} from "./map-vintages";

describe("pickVintages", () => {
  it("extracts + sorts 4-digit vintages for the indicator", () => {
    const files = [
      "pres_margin_2024.json",
      "pres_margin_1976.json",
      "pres_margin_2020.json",
    ];
    expect(pickVintages(files, "pres_margin")).toEqual(["1976", "2020", "2024"]);
  });

  it("ignores other indicators, summaries, and the manifest", () => {
    const files = [
      "pres_margin_2020.json",
      "poverty_rate_2020.json", // different indicator
      "pres_margin_2020.summary.json", // summary sibling
      "source_index.json",
      "pres_margin_20.json", // not 4 digits
      "pres_margin_2020.csv", // wrong extension
    ];
    expect(pickVintages(files, "pres_margin")).toEqual(["2020"]);
  });

  it("does NOT let a short indicator swallow a longer one's files", () => {
    // The election maps ship BOTH pres_margin (state) and
    // pres_margin_county (county). 'pres_margin' must not match the county
    // file (the `_county` segment blocks the immediate _<YYYY>).
    const files = ["pres_margin_2024.json", "pres_margin_county_2024.json"];
    expect(pickVintages(files, "pres_margin")).toEqual(["2024"]);
    expect(pickVintages(files, "pres_margin_county")).toEqual(["2024"]);
  });

  it("returns [] when nothing matches", () => {
    expect(pickVintages(["foo.json", "bar_2020.json"], "pres_margin")).toEqual([]);
  });
});

describe("indicatorVintageRe", () => {
  it("regex-escapes the indicator so metacharacters can't widen the match", () => {
    const re = indicatorVintageRe("a.b");
    expect("a.b_2020.json".match(re)?.[1]).toBe("2020");
    expect("axb_2020.json".match(re)).toBeNull(); // '.' is literal, not wildcard
  });
});

describe("combineShardVintages", () => {
  it("passes a single shard (state/county) straight through", () => {
    expect(combineShardVintages([["2000", "2020", "2024"]])).toEqual([
      "2000", "2020", "2024",
    ]);
  });

  it("intersects across shards (only years present in ALL)", () => {
    expect(
      combineShardVintages([
        ["2016", "2018", "2020", "2022"],
        ["2018", "2020", "2022"],
        ["2018", "2020"],
      ]),
    ).toEqual(["2018", "2020"]);
  });

  it("falls back to the sorted union when a shard is entirely empty", () => {
    expect(
      combineShardVintages([["2020", "2022"], [], ["2018", "2020"]]),
    ).toEqual(["2018", "2020", "2022"]);
  });

  it("returns [] for no shards", () => {
    expect(combineShardVintages([])).toEqual([]);
  });
});

describe("vintageAtIndex", () => {
  const vs = ["2000", "2004", "2008"];
  it("returns the vintage at a valid index", () => {
    expect(vintageAtIndex(vs, 0)).toBe("2000");
    expect(vintageAtIndex(vs, 2)).toBe("2008");
  });
  it("clamps an out-of-range index instead of reading off the end", () => {
    expect(vintageAtIndex(vs, 9)).toBe("2008");
    expect(vintageAtIndex(vs, -3)).toBe("2000");
  });
  it("rounds a fractional index", () => {
    expect(vintageAtIndex(vs, 1.4)).toBe("2004");
  });
  it("returns null for an empty list", () => {
    expect(vintageAtIndex([], 0)).toBeNull();
  });
});
