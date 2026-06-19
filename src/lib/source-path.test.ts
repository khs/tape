import { describe, expect, it } from "vitest";
import { sourceIdToPath, pathToSourceId } from "./source-path";

describe("sourceIdToPath", () => {
  it("preserves the provider/series slash as a path separator", () => {
    // The regression this guards: encodeURIComponent(id) would turn this
    // into "ssa%2Foasdi_workers_per_beneficiary", which the /source/[...id]
    // route keeps as one literal segment → "Source not found".
    expect(sourceIdToPath("ssa/oasdi_workers_per_beneficiary")).toBe(
      "ssa/oasdi_workers_per_beneficiary",
    );
    expect(sourceIdToPath("bls/qcew_employment_dc")).toBe(
      "bls/qcew_employment_dc",
    );
  });

  it("encodes special characters WITHIN a segment but keeps the slashes", () => {
    expect(sourceIdToPath("a b/c+d")).toBe("a%20b/c%2Bd");
  });
});

describe("pathToSourceId", () => {
  it("decodes a percent-encoded slash back to a source ID", () => {
    expect(pathToSourceId("ssa%2Foasdi_workers_per_beneficiary")).toBe(
      "ssa/oasdi_workers_per_beneficiary",
    );
  });

  it("is a no-op on an already-decoded id (no '%')", () => {
    expect(pathToSourceId("ssa/oasdi_workers_per_beneficiary")).toBe(
      "ssa/oasdi_workers_per_beneficiary",
    );
    expect(pathToSourceId("bls/qcew_employment_dc")).toBe(
      "bls/qcew_employment_dc",
    );
  });

  it("round-trips with an encoded id (the exact bug) and with sourceIdToPath", () => {
    const id = "ssa/oasdi_workers_per_beneficiary";
    expect(pathToSourceId(encodeURIComponent(id))).toBe(id);
    expect(pathToSourceId(sourceIdToPath(id))).toBe(id);
  });

  it("returns the raw value on a malformed escape", () => {
    expect(pathToSourceId("ssa%ZZ")).toBe("ssa%ZZ");
  });
});
