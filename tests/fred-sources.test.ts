/**
 * fred source YAMLs are GENERATED from pipelines/fred_sources.yaml (the single
 * metadata catalog). This gate asserts every fred YAML still equals what the
 * catalog would generate, and that the catalog + YAML set are 1:1 — so a hand
 * edit to a generated YAML (which would silently drift from the catalog, and
 * be lost on the next regenerate) fails CI. Regenerate with
 * `python pipelines/_generate_fred_sources.py --write`.
 *
 * Mirrors expand() in _generate_fred_sources.py: only kind/pipeline/dataFile
 * are derived; everything else (incl. provenance) is stored in the catalog.
 */
import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import yaml from "js-yaml";

const ROOT = process.cwd();
const CATALOG = join(ROOT, "pipelines", "fred_sources.yaml");
const FRED = join(ROOT, "src", "content", "sources", "fred");

type Row = Record<string, unknown>;

function outId(series: string, transformation?: string): string {
  return transformation ? `${series}_${transformation.toUpperCase()}` : series;
}

function expand(row: Row): Row {
  const oid = outId(row.series as string, row.transformation as string | undefined);
  const m: Row = {};
  m.name = row.name;
  if ("shortName" in row) m.shortName = row.shortName;
  m.description = row.description;
  m.kind = "timeseries";
  m.pipeline = "fred_series";
  m.dataFile = `data/fred/${oid}.json`;
  for (const k of ["supportedDeltas", "unit", "formatting", "emphasis",
    "provenance", "tags", "unitClass", "hidden"]) {
    if (k in row) m[k] = row[k];
  }
  return m;
}

/** Deterministic, key-order-independent serialization for deep comparison. */
function stable(v: unknown): string {
  if (Array.isArray(v)) return `[${v.map(stable).join(",")}]`;
  if (v && typeof v === "object") {
    return `{${Object.keys(v as object).sort()
      .map((k) => `${k}:${stable((v as Row)[k])}`).join(",")}}`;
  }
  return JSON.stringify(v);
}

describe("fred sources are generated from the catalog (no drift)", () => {
  const cat = yaml.load(readFileSync(CATALOG, "utf-8")) as Record<string, Row>;

  it("every YAML equals generated(catalog); catalog + YAMLs are 1:1", () => {
    const bad: string[] = [];
    const yamls = new Set(
      readdirSync(FRED).filter((f) => f.endsWith(".yaml")).map((f) => f.slice(0, -5)),
    );
    for (const [slug, row] of Object.entries(cat)) {
      if (row.component) continue; // fetch-only, no YAML
      if (!yamls.has(slug)) {
        bad.push(`catalog '${slug}' has no YAML`);
        continue;
      }
      yamls.delete(slug);
      const cur = yaml.load(readFileSync(join(FRED, `${slug}.yaml`), "utf-8"));
      if (stable(cur) !== stable(expand(row))) {
        bad.push(`'${slug}': YAML != generated from catalog (run --write)`);
      }
    }
    for (const orphan of yamls) bad.push(`YAML '${orphan}' has no catalog row`);
    expect(bad, bad.slice(0, 30).join("\n")).toEqual([]);
  });
});
