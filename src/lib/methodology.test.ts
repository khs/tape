import { describe, it, expect } from "vitest";
import { METHODOLOGY, getMethodology } from "./methodology";

describe("methodology registry", () => {
  it("every entry is well-formed", () => {
    for (const [key, m] of Object.entries(METHODOLOGY)) {
      expect(m.upstream.trim().length, `${key}.upstream`).toBeGreaterThan(0);
      expect(m.access.trim().length, `${key}.access`).toBeGreaterThan(0);
      expect(m.steps.length, `${key}.steps`).toBeGreaterThan(0);
      m.steps.forEach((s, i) =>
        expect(s.trim().length, `${key}.steps[${i}]`).toBeGreaterThan(0),
      );
      (m.caveats ?? []).forEach((c, i) =>
        expect(c.trim().length, `${key}.caveats[${i}]`).toBeGreaterThan(0),
      );
    }
  });

  it("no entry leaks internal repo paths or run commands", () => {
    // Guards Plan 8: methodology cards must not expose pipeline file paths
    // or local run commands publicly. Re-grep guard at the data level.
    for (const [key, m] of Object.entries(METHODOLOGY)) {
      const blob = JSON.stringify(m);
      expect(blob, `${key} mentions a pipelines/*.py path`).not.toMatch(
        /pipelines\/[\w-]+\.py/,
      );
      expect(blob, `${key} mentions a python run command`).not.toMatch(
        /python\s+pipelines/,
      );
    }
  });

  it("getMethodology resolves known pipelines and rejects the rest", () => {
    expect(getMethodology("fec")).toBe(METHODOLOGY.fec);
    // FRED's `pipeline` field is `fred_series`, not `fred` — guard the key.
    expect(getMethodology("fred_series")).toBe(METHODOLOGY.fred_series);
    expect(getMethodology(undefined)).toBeNull();
    expect(getMethodology(null)).toBeNull();
    // Passthrough providers intentionally have no entry (no card renders).
    expect(getMethodology("yahoo")).toBeNull();
    expect(getMethodology("definitely_not_a_pipeline")).toBeNull();
  });
});
