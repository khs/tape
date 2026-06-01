import { describe, it, expect } from "vitest";
import { existsSync } from "node:fs";
import { join } from "node:path";
import {
  METHODOLOGY,
  getMethodology,
  repoFileUrl,
  REPO_BLOB_BASE,
} from "./methodology";

// vitest runs from the repo root, so pipeline paths resolve directly.
const REPO_ROOT = process.cwd();

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
      expect(m.pipelineFile, `${key}.pipelineFile`).toMatch(/^pipelines\/.+\.py$/);
      // The run command must actually invoke the linked pipeline, so the
      // "Run it" line on the card matches the "Source code" link.
      expect(m.runCommand, `${key}.runCommand`).toContain(m.pipelineFile);
    }
  });

  it("every pipelineFile exists on disk", () => {
    // Catches a renamed/moved pipeline that would 404 the source-code link
    // and signal a stale methodology entry.
    for (const [key, m] of Object.entries(METHODOLOGY)) {
      const abs = join(REPO_ROOT, m.pipelineFile);
      expect(existsSync(abs), `${key}: ${m.pipelineFile} not found`).toBe(true);
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

  it("repoFileUrl builds a GitHub blob link to the default branch", () => {
    expect(repoFileUrl("pipelines/fec_house_spending.py")).toBe(
      `${REPO_BLOB_BASE}/pipelines/fec_house_spending.py`,
    );
  });
});
