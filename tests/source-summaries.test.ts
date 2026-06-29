/**
 * Missing-summary gate.
 *
 * Every timeseries source rendered as a tile relies on a <id>.summary.json
 * sibling next to its data file — the low-fi payload the tile shows before the
 * full series lazy-loads on dialog open (the tile-payload Phase 2 work in
 * src/lib/load-data.ts: loadSourceSummary). If a referenced source ships its
 * data .json but no .summary.json, the tile's first paint is broken/empty.
 *
 * This gate fails a merge if any source referenced by a live chart has a
 * timeseries data file with no summary sibling. Non-timeseries sources (map /
 * choropleth FeatureCollections) don't get summaries and are skipped; a missing
 * DATA file is a separate concern (the quarantine audit), so we skip those too.
 */
import { describe, it, expect } from "vitest";
import { existsSync } from "node:fs";
import {
  referencedSources,
  dataPath,
  summaryPath,
  readJson,
  isTimeseries,
} from "./corpus";

describe("source summaries (referenced tiles)", () => {
  // Walks every referenced source and stats two files apiece. Fast alone
  // (~0.6s) but it competes for disk I/O against the rest of the suite under
  // vitest's parallel workers, where it has blown past the 5s default. Give it
  // headroom so a busy CI box can't flake this gate.
  it("every referenced timeseries source has a .summary.json sibling", () => {
    const missing: string[] = [];
    for (const s of referencedSources()) {
      if (!s.dataFile) continue;
      const dp = dataPath(s.dataFile);
      if (!existsSync(dp)) continue; // missing data file — quarantine audit's job
      if (!isTimeseries(readJson(dp))) continue; // maps don't get summaries
      if (!existsSync(summaryPath(s.dataFile))) missing.push(s.id);
    }
    expect(
      missing,
      `\nReferenced timeseries sources missing their .summary.json sibling (the ` +
        `tile low-fi payload — first paint will be empty). Regenerate summaries ` +
        `for:\n  ${missing.join("\n  ")}\n`,
    ).toEqual([]);
    // Corpus walk + two stats per source: fast alone (~0.6s) but flakes past the
    // 5s default under parallel-suite I/O contention. Give it headroom.
  }, 30000);
});
