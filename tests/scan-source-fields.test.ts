/**
 * Locks scanSourceFields (the fast path in scripts/audit-source-data.mjs) to
 * the exact {dataFile, kind, tags} js-yaml would produce for the source-YAML
 * shapes in the repo. A one-time full-corpus diff (35,896 files, 0 mismatches)
 * proved equivalence at ship time; this guards future edits to the scanner.
 */
import { describe, it, expect } from "vitest";
import { scanSourceFields } from "../scripts/_scan_source_fields.mjs";

describe("scanSourceFields", () => {
  it("block tags, 2-space indent (acs_cd shape)", () => {
    const y =
      "name: X\nkind: timeseries\ndataFile: data/acs_cd/x.json\n" +
      "tags:\n  - government\n  - us\n  - labor\nunitClass: count\n";
    expect(scanSourceFields(y)).toEqual({
      dataFile: "data/acs_cd/x.json", kind: "timeseries",
      tags: ["government", "us", "labor"],
    });
  });

  it("block tags, 0-indent (fred generated shape)", () => {
    const y = "name: X\nkind: timeseries\ndataFile: data/fred/X.json\ntags:\n- macro\n- us\n";
    expect(scanSourceFields(y)).toEqual({
      dataFile: "data/fred/X.json", kind: "timeseries", tags: ["macro", "us"],
    });
  });

  it("inline tags", () => {
    const y = "kind: timeseries\ndataFile: data/x.json\ntags: [equity-index, large-stocks]\n";
    expect(scanSourceFields(y)).toEqual({
      dataFile: "data/x.json", kind: "timeseries", tags: ["equity-index", "large-stocks"],
    });
  });

  it("no tags field -> empty array", () => {
    expect(scanSourceFields("kind: curve\ndataFile: data/curve.json\n")).toEqual({
      dataFile: "data/curve.json", kind: "curve", tags: [],
    });
  });

  it("empty inline tags -> empty array", () => {
    expect(scanSourceFields("kind: timeseries\ndataFile: data/x.json\ntags: []\n")!.tags).toEqual([]);
  });

  it("strips quotes on dataFile/kind/tags", () => {
    const y = "kind: \"timeseries\"\ndataFile: \"data/x.json\"\ntags:\n  - \"macro\"\n  - 'us'\n";
    expect(scanSourceFields(y)).toEqual({
      dataFile: "data/x.json", kind: "timeseries", tags: ["macro", "us"],
    });
  });

  it("block tags stop at the next top-level key", () => {
    const y = "kind: timeseries\ndataFile: data/x.json\ntags:\n  - a\n  - b\nunitClass: count\nhidden: true\n";
    expect(scanSourceFields(y)!.tags).toEqual(["a", "b"]);
  });

  it("returns null (fallback to js-yaml) when dataFile or kind is absent", () => {
    expect(scanSourceFields("name: X\ndataFile: data/x.json\n")).toBeNull();
    expect(scanSourceFields("name: X\nkind: timeseries\n")).toBeNull();
  });
});
