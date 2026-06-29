import { describe, it, expect } from "vitest";
import { computeSummaryFromPoints } from "./load-data";
import fixture from "./__fixtures__/summary-parity.json";

// CROSS-LANGUAGE PARITY GATE.
//
// The per-window prior + spark math lives in two implementations that must
// agree to the byte: Python (pipelines/build_summaries.py:build_summary, which
// writes every source's .summary.json) and TypeScript
// (src/lib/load-data.ts:computeSummaryFromPoints, used for derived / op'd charts
// that have no precomputed summary). If they drift, a derived chart's tile would
// silently disagree with the same source's standalone tile.
//
// The fixture is the Python implementation's output on a set of edge-case
// series, emitted by pipelines/emit_summary_parity_fixture.py. Here we recompute
// from the identical inputs with the TS implementation and require an exact
// match. CI also regenerates the fixture and `git diff`s it, so a Python-only
// change that isn't mirrored here fails too. To refresh after an intentional
// change: `python pipelines/emit_summary_parity_fixture.py`.
type Pts = Parameters<typeof computeSummaryFromPoints>[0];

describe("summary parity (TS computeSummaryFromPoints == Python build_summary)", () => {
  it("covers a representative spread of cases", () => {
    // Guard against the fixture silently emptying out (e.g. a broken emitter).
    expect(fixture.cases.length).toBeGreaterThanOrEqual(6);
  });

  for (const c of fixture.cases) {
    it(`matches Python output for "${c.name}"`, () => {
      const out = computeSummaryFromPoints(c.input.points as Pts, fixture.windows);
      expect(out).not.toBeNull();
      if (!out) return;
      // latest / priors / sparks are the cross-language computed surface.
      expect(out.latest).toEqual(c.expected.latest);
      expect(out.priors).toEqual(c.expected.priors);
      expect(out.sparks).toEqual(c.expected.sparks);
    });
  }
});
