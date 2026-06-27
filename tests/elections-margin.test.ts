/**
 * Every election-margin choropleth is a (Dem - Rep) / total * 100 value, which
 * is mathematically bounded to [-100, 100]. A value outside that range means a
 * vote double-count slipped into the pipeline.
 *
 * The 2024 presidential county map shipped 297 impossible margins (|margin|>100)
 * because MEDSL countypres rows were summed across BOTH the per-voting-mode rows
 * AND the per-county "TOTAL" row, double-counting each candidate. The fix
 * (pipelines/elections.py: TOTAL-when-present, else sum non-TOTAL) restored the
 * bound; this gate keeps every committed margin file inside it.
 */
import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";

const DATA = path.join(process.cwd(), "public", "data");
const DIRS = ["acs_county", "acs_state"];

const files: string[] = [];
for (const d of DIRS) {
  const dir = path.join(DATA, d);
  if (!fs.existsSync(dir)) continue;
  for (const f of fs.readdirSync(dir)) {
    if (/margin/i.test(f) && f.endsWith(".json")) files.push(path.join(d, f));
  }
}

describe("election-margin choropleths stay within +/-100pp (vote double-count guard)", () => {
  it("found the margin choropleth files", () => {
    expect(files.length).toBeGreaterThan(20);
  });

  for (const rel of files) {
    it(`${rel}: every margin is in [-100, 100]`, () => {
      const j = JSON.parse(fs.readFileSync(path.join(DATA, rel), "utf8"));
      const values: Record<string, number> = j.values ?? {};
      const offenders = Object.entries(values)
        .filter(([, v]) => !Number.isFinite(v) || Math.abs(v) > 100.0001)
        .slice(0, 5);
      expect(offenders).toEqual([]);
    });
  }
});
