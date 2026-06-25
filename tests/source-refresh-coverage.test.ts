/**
 * Enforces the standing rule "every data source must auto-renew": every
 * provider dir under src/content/sources/ must be refreshed by a run step in a
 * scheduled workflow (refresh-data.yml weekly, or refresh-demographics.yml
 * monthly), OR be explicitly listed in NOT_AUTO_REFRESHED with a reason.
 *
 * Why a test and not just a checklist line: the metro federal layer shipped
 * four providers with NO refresh wiring, and a recon found ~15 pre-existing
 * providers in the same state. A convention you "tell yourself" doesn't catch
 * that; this does — a new unwired provider fails CI + the deploy gate.
 */
import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";

const ROOT = process.cwd();
const SOURCES = path.join(ROOT, "src", "content", "sources");
const WORKFLOWS = ["refresh-data.yml", "refresh-demographics.yml"].map((f) =>
  path.join(ROOT, ".github", "workflows", f),
);

/** Providers that DELIBERATELY do not auto-renew, each with the reason. Adding
 *  an entry here is a conscious decision that this source can't or shouldn't be
 *  on a schedule. Everything else MUST be wired into a workflow. */
const NOT_AUTO_REFRESHED: Record<string, string> = {
  ssa: "manual XLSX — SSA Trustees tables are DataDome-blocked from CI (like cbo's manual path)",
  guttmacher: "hand-entered (APC + MAPS abortion figures; no machine-readable feed)",
  elections: "one-shot historical (MEDSL past-election results; re-run by hand after an election)",
  fec: "no fetch pipeline (per-cycle FEC campaign-finance data; rebuilt manually each cycle)",
};

/** Providers whose refreshing pipeline FILE differs from both the dir name and
 *  the YAML `pipeline:` field (so the run-step match needs the real filename). */
const PIPELINE_ALIAS: Record<string, string> = {
  worldbank_gdp_raw: "worldbank_gdp", // raw country GDP written by worldbank_gdp.py
  yahoo_futures: "yahoo_quotes", // the refresh-data "Yahoo quotes (… futures)" step
};

function readWorkflows(): { run: Set<string>; staged: Set<string> } {
  const run = new Set<string>();
  const staged = new Set<string>();
  for (const wf of WORKFLOWS) {
    const txt = fs.readFileSync(wf, "utf8");
    for (const m of txt.matchAll(/python pipelines\/(\w+)\.py/g)) run.add(m[1]);
    for (const m of txt.matchAll(/for dir in ([^;]+);/g))
      for (const d of m[1].trim().split(/\s+/)) staged.add(d);
  }
  return { run, staged };
}

function pipelineField(dir: string): string {
  const d = path.join(SOURCES, dir);
  const yaml = fs.readdirSync(d).find((f) => f.endsWith(".yaml"));
  if (!yaml) return "";
  for (const line of fs.readFileSync(path.join(d, yaml), "utf8").split("\n")) {
    const m = /^pipeline:\s*(\S+)/.exec(line);
    if (m) return m[1].trim();
  }
  return "";
}

describe("every data-source provider auto-renews via a refresh workflow", () => {
  const { run, staged } = readWorkflows();
  const providers = fs
    .readdirSync(SOURCES, { withFileTypes: true })
    .filter((e) => e.isDirectory())
    .map((e) => e.name);

  const isAuto = (p: string): boolean =>
    staged.has(p) || run.has(pipelineField(p)) || run.has(PIPELINE_ALIAS[p] ?? "");

  it("parsed the workflows and the source corpus", () => {
    expect(providers.length).toBeGreaterThan(30);
    expect(run.size).toBeGreaterThan(10);
    expect(staged.size).toBeGreaterThan(10);
  });

  it("wires every provider into a workflow (or explicitly exempts it)", () => {
    const orphans = providers.filter((p) => !isAuto(p) && !(p in NOT_AUTO_REFRESHED));
    expect(
      orphans,
      "These providers don't auto-renew. Add a run step + a staging-loop entry " +
        "in refresh-data.yml (weekly) or refresh-demographics.yml (monthly), or " +
        "add to NOT_AUTO_REFRESHED with a reason",
    ).toEqual([]);
  });

  it("keeps the exemption list honest (entries exist and are genuinely unwired)", () => {
    for (const p of Object.keys(NOT_AUTO_REFRESHED)) {
      expect(providers, `exempt provider '${p}' no longer exists — remove it`).toContain(p);
      expect(isAuto(p), `'${p}' is now wired — drop it from NOT_AUTO_REFRESHED`).toBe(false);
    }
  });
});
