/**
 * Pre-build data audit: refuses to let the build proceed if a source
 * that's referenced by a chart has too little data to render anything
 * meaningful.
 *
 * Why: chart tiles silently render blank when the underlying source
 * has 0 or 1 data points (no second point to draw a line to, no
 * second point to compute a delta against). A blank tile in
 * production looks like a bug to the user but ships green because
 * `astro build` doesn't validate data — only schemas.
 *
 * This script:
 *   1. Walks src/content/sources/<pipeline>/*.yaml — every source's
 *      schema + its `dataFile` path.
 *   2. Walks src/content/charts/<folder>/*.yaml — collects the set of
 *      source IDs actually referenced by at least one non-deprecated
 *      chart.
 *   3. For each REFERENCED source, opens its data file under public/
 *      and counts points.
 *   4. Fails the build (exit 1) if any referenced source has fewer
 *      than 2 points, or has no data file on disk.
 *   5. Prints a short warnings list for UNREFERENCED sources with too
 *      little data — non-fatal, just a hygiene signal for whoever's
 *      auditing the library.
 *
 * Hooked into npm's `prebuild` so it runs before `astro build` both
 * locally and on Vercel. Pure Node, no Python, so Vercel doesn't need
 * a Python runtime in its build image.
 *
 * Skip with `SKIP_DATA_AUDIT=1 npm run build` if you really need to
 * cut a build with known-bad data (e.g. a force-push of brand-only
 * changes during an outage).
 */
import { promises as fs } from "node:fs";
import { resolve, relative, join, sep } from "node:path";
import { fileURLToPath } from "node:url";
import yaml from "js-yaml";

// Resolve repo root from this file's location so the script works
// regardless of cwd (Vercel runs from the project root, but local
// runs may differ).
const HERE = fileURLToPath(import.meta.url);
const ROOT = resolve(HERE, "..", "..");
const SOURCES_DIR = join(ROOT, "src", "content", "sources");
const CHARTS_DIR = join(ROOT, "src", "content", "charts");
const PUBLIC_DIR = join(ROOT, "public");

// Minimum points a referenced source must carry to ship. 2 lets a
// chart draw a single segment + compute a single delta. Anything
// shorter renders blank or as an unreadable dot.
const MIN_POINTS_FOR_CHART = 2;

if (process.env.SKIP_DATA_AUDIT === "1") {
  console.log("[data-audit] SKIP_DATA_AUDIT=1 set — bypassing pre-build data audit.");
  process.exit(0);
}

/** Recursively list every .yaml file under root. */
async function listYamls(root) {
  const out = [];
  async function walk(dir) {
    let entries;
    try {
      entries = await fs.readdir(dir, { withFileTypes: true });
    } catch (e) {
      if (e.code === "ENOENT") return;
      throw e;
    }
    for (const entry of entries) {
      const p = join(dir, entry.name);
      if (entry.isDirectory()) {
        await walk(p);
      } else if (entry.isFile() && entry.name.endsWith(".yaml")) {
        out.push(p);
      }
    }
  }
  await walk(root);
  return out;
}

/** Read+parse a YAML file. Throws with a useful path on parse error. */
async function readYaml(path) {
  const text = await fs.readFile(path, "utf-8");
  try {
    return yaml.load(text);
  } catch (e) {
    throw new Error(`YAML parse failed: ${path}\n  ${e.message}`);
  }
}

/** A source ID is its path under src/content/sources/ minus the .yaml,
 * with directory separators normalized to "/" — matches what
 * library.json.ts uses as the content-collection entry ID. */
function sourceIdFromPath(yamlPath) {
  const rel = relative(SOURCES_DIR, yamlPath);
  return rel.replace(/\.yaml$/, "").split(sep).join("/");
}
function chartIdFromPath(yamlPath) {
  const rel = relative(CHARTS_DIR, yamlPath);
  return rel.replace(/\.yaml$/, "").split(sep).join("/");
}

async function main() {
  const t0 = Date.now();

  // 1. Index sources by id + dataFile.
  const sourceYamls = await listYamls(SOURCES_DIR);
  /** @type {Map<string, { dataFile?: string, path: string }>} */
  const sourceIndex = new Map();
  for (const path of sourceYamls) {
    const id = sourceIdFromPath(path);
    let data;
    try {
      data = await readYaml(path);
    } catch (e) {
      console.error(`[data-audit] ${e.message}`);
      process.exit(1);
    }
    if (!data || typeof data !== "object") continue;
    sourceIndex.set(id, {
      dataFile: typeof data.dataFile === "string" ? data.dataFile : undefined,
      path,
    });
  }

  // 2. Find sources referenced by at least one non-deprecated chart.
  const chartYamls = await listYamls(CHARTS_DIR);
  /** @type {Map<string, string[]>} */
  const referencedBy = new Map();
  for (const path of chartYamls) {
    let data;
    try {
      data = await readYaml(path);
    } catch (e) {
      console.error(`[data-audit] ${e.message}`);
      process.exit(1);
    }
    if (!data || typeof data !== "object") continue;
    // Skip charts that are deprecated WITHOUT an alias — they're
    // hidden from the UI and not worth gating deploys on.
    if (data.deprecated === true && !data.aliasOf) continue;
    const chartId = chartIdFromPath(path);
    const srcs = Array.isArray(data.sources) ? data.sources : [];
    for (const sid of srcs) {
      if (typeof sid !== "string") continue;
      if (!referencedBy.has(sid)) referencedBy.set(sid, []);
      referencedBy.get(sid).push(chartId);
    }
  }

  // 3. For each referenced source, count points in its data file.
  /** @type {{ id: string, reason: string, charts: string[] }[]} */
  const failures = [];
  /** @type {{ id: string, reason: string }[]} */
  const warnings = [];

  // Iterate only the REFERENCED sources for the hard-fail check.
  // Skipping data-file reads for the other ~20k YAMLs cuts the audit
  // from ~4 minutes to a couple seconds. Composer-only sources can
  // still render blank if a user picks them, but that's a softer
  // failure mode than shipping a chart YAML with no data.
  for (const sid of referencedBy.keys()) {
    const src = sourceIndex.get(sid);
    const refs = referencedBy.get(sid) ?? [];
    if (!src) {
      // Chart YAML references a source ID that has no source YAML on
      // disk — same broken-ref check that _audit_chart_sources.py
      // does in Python land, kept here so the prebuild gate catches it
      // too.
      failures.push({
        id: sid,
        reason: "no source YAML on disk for this ID",
        charts: refs,
      });
      continue;
    }
    if (!src.dataFile) {
      failures.push({
        id: sid,
        reason: "source YAML is missing a dataFile field",
        charts: refs,
      });
      continue;
    }
    const fullPath = join(PUBLIC_DIR, src.dataFile);
    let raw;
    try {
      raw = await fs.readFile(fullPath, "utf-8");
    } catch (e) {
      if (e.code === "ENOENT") {
        failures.push({
          id: sid,
          reason: `data file missing: ${src.dataFile}`,
          charts: refs,
        });
        continue;
      }
      throw e;
    }
    let parsed;
    try {
      parsed = JSON.parse(raw);
    } catch (e) {
      failures.push({
        id: sid,
        reason: `data file is not valid JSON: ${src.dataFile} (${e.message})`,
        charts: refs,
      });
      continue;
    }
    if (!parsed || typeof parsed !== "object" || !Array.isArray(parsed.points)) {
      failures.push({
        id: sid,
        reason: `data file has no points array: ${src.dataFile}`,
        charts: refs,
      });
      continue;
    }
    // Count BOTH historical points and projection-vintage points.
    // Forecast-UI sources like the SSA OASDI cost/GDP series can be
    // projection-only (their parent page on ssa.gov is structured
    // without a historical section) — that's a valid dashed-line
    // render, not the "blank tile" failure mode the audit was
    // originally guarding against. Counting only `points.length`
    // would false-fail those, so we sum across the projections map
    // too. The renderer copes with `points.length === 0` as long as
    // there's at least one projection vintage to draw.
    const nHist = parsed.points.length;
    let nProj = 0;
    if (parsed.projections && typeof parsed.projections === "object") {
      for (const arr of Object.values(parsed.projections)) {
        if (Array.isArray(arr)) nProj += arr.length;
      }
    }
    const total = nHist + nProj;
    if (total < MIN_POINTS_FOR_CHART) {
      failures.push({
        id: sid,
        reason: `only ${nHist} historical point${nHist === 1 ? "" : "s"} + ${nProj} projection point${nProj === 1 ? "" : "s"} (need at least ${MIN_POINTS_FOR_CHART} total to render a chart)`,
        charts: refs,
      });
    }
  }

  // 4. Report + fail.
  const elapsed = ((Date.now() - t0) / 1000).toFixed(1);
  if (warnings.length > 0) {
    console.log(`[data-audit] ${warnings.length} hygiene warning${warnings.length === 1 ? "" : "s"}:`);
    for (const w of warnings.slice(0, 20)) {
      console.log(`  - ${w.id}: ${w.reason}`);
    }
    if (warnings.length > 20) console.log(`  …and ${warnings.length - 20} more`);
  }
  if (failures.length > 0) {
    console.error(`[data-audit] BUILD BLOCKED: ${failures.length} referenced source${failures.length === 1 ? "" : "s"} can't render a chart.`);
    for (const f of failures) {
      console.error(`  - ${f.id}: ${f.reason}`);
      for (const c of f.charts.slice(0, 3)) console.error(`      referenced by chart: ${c}`);
      if (f.charts.length > 3) console.error(`      …and ${f.charts.length - 3} more chart(s)`);
    }
    console.error(
      `[data-audit] Fix the data, retire the chart, or set SKIP_DATA_AUDIT=1 if this is intentional.`,
    );
    process.exit(1);
  }
  const refCount = referencedBy.size;
  console.log(
    `[data-audit] OK in ${elapsed}s — ${sourceIndex.size} sources scanned, ${refCount} referenced, ${warnings.length} warning${warnings.length === 1 ? "" : "s"}.`,
  );
}

main().catch((e) => {
  console.error(`[data-audit] unexpected failure: ${e.stack ?? e.message ?? e}`);
  process.exit(1);
});
