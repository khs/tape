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

// --full: deep-scan every source's data file (order, summary drift,
// point counts) instead of only chart-referenced ones. Costs minutes —
// runs in CI, not in the Vercel prebuild.
const FULL_SCAN = process.argv.includes("--full");

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

/**
 * Returns a human-readable problem string when a points array is not
 * strictly ascending by date (duplicates count as a violation too —
 * the same merge bug that duplicates also misorders), else null.
 */
function pointOrderIssue(points) {
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1]?.t;
    const b = points[i]?.t;
    if (typeof a !== "string" || typeof b !== "string") continue;
    if (b < a) return `points out of order (… ${a} then ${b})`;
    if (b === a) return `duplicate point date ${b}`;
  }
  return null;
}

/**
 * Derive a "sibling cohort" key so we can flag a country/geo series that
 * has frozen years behind the rest of its family. The geo code is the
 * leading 2-3 letter token of the name part:
 *   oecd/jpn_cpi_yoy      → oecd::cpi_yoy      (siblings: usa_, can_, …)
 *   oecd/nor_gov_debt_…   → oecd::gov_debt_…   (siblings: the other OECD)
 *   edu_spending/ny_perpupil → edu_spending::perpupil
 * Names whose leading token is a real word ("median_listing_price") or
 * whose geo code trails (fred state series) don't match — they have no
 * leading-geo cohort and return null. The >=3-member + threshold guards
 * downstream keep false positives near zero.
 */
function cohortKeyFor(id) {
  const slash = id.indexOf("/");
  if (slash < 0) return null;
  const pipeline = id.slice(0, slash);
  const name = id.slice(slash + 1);
  const m = name.match(/^([a-z]{2,3})_(.+)$/);
  if (!m) return null;
  return `${pipeline}::${m[2]}`;
}

/** Last (most recent) point date of a parsed data file, or null. */
function lastPointDate(parsed) {
  const pts = parsed?.points;
  if (!Array.isArray(pts) || pts.length === 0) return null;
  const t = pts[pts.length - 1]?.t;
  return typeof t === "string" ? t : null;
}

/**
 * If a sibling .summary.json exists, check its latest.t matches the
 * data file's final point. Returns a problem string or null. A missing
 * summary file is fine (not every pipeline writes one).
 */
async function summaryLatestDrift(dataFullPath, points) {
  const summaryPath = dataFullPath.replace(/\.json$/, ".summary.json");
  let raw;
  try {
    raw = await fs.readFile(summaryPath, "utf-8");
  } catch (e) {
    if (e.code === "ENOENT") return null;
    throw e;
  }
  let summary;
  try {
    summary = JSON.parse(raw);
  } catch {
    return `summary file is not valid JSON: ${summaryPath}`;
  }
  const latestT = summary?.latest?.t;
  const lastT = points[points.length - 1]?.t;
  if (typeof latestT !== "string" || typeof lastT !== "string") return null;
  if (latestT !== lastT) {
    return `summary latest (${latestT}) != data file's last point (${lastT})`;
  }
  return null;
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
      tags: Array.isArray(data.tags) ? data.tags.filter((t) => typeof t === "string") : [],
      kind: typeof data.kind === "string" ? data.kind : undefined,
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
  /** Members of country/geo sibling cohorts, for the staleness pass.
   *  @type {{ id: string, cohortKey: string, lastT: string }[]} */
  const cohortMembers = [];

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
    // 3a-order. Point-order + summary-consistency checks (the
    // bea/personal_income_virginia class: a pipeline merge bug
    // concatenated two date ranges, so the file's LAST element — and
    // therefore the .summary.json "latest" — was a decade stale while
    // newer data sat earlier in the array). Renderers and summaries
    // both assume ascending t; violating that ships silently-wrong
    // numbers, which is worse than a missing tile.
    const orderIssue = pointOrderIssue(parsed.points);
    if (orderIssue) {
      failures.push({
        id: sid,
        reason: `${orderIssue} in ${src.dataFile} — pipeline merge/append bug; the summary "latest" is untrustworthy`,
        charts: refs,
      });
    } else if (nHist > 0) {
      const drift = await summaryLatestDrift(fullPath, parsed.points);
      if (drift) {
        failures.push({
          id: sid,
          reason: `${drift} — regenerate the .summary.json (stale latest serves wrong numbers)`,
          charts: refs,
        });
      }
    }
    // Capture for the cohort-staleness pass (after the loop). Referenced
    // sources are read here in fast mode, so chart-shipping cohorts
    // (e.g. the G7 cpi_yoy family behind countries/g7_inflation) are
    // covered on every prebuild.
    const cohortKey = cohortKeyFor(sid);
    const lastT = lastPointDate(parsed);
    if (cohortKey && lastT) cohortMembers.push({ id: sid, cohortKey, lastT });
  }

  // 3b. Topical-tag-pill guard — a fast local mirror of the
  // build-time invariant in src/pages/library.json.ts. That guard
  // throws (failing `astro build`, and therefore the Vercel deploy)
  // when a topical tag pill would render with count 0 in the
  // SourcePicker's default view — i.e. every source carrying the tag
  // is hidden behind a geo chip. This exact failure shipped once
  // (the `tax` tag added only to us-state-tagged tax sources) because
  // this prebuild audit didn't check it and a full `astro build` is
  // the only other thing that does. Replicated here so the cheap
  // prebuild catches the class.
  //
  // Geo-detection here is intentionally a SUBSET of library.json's
  // synthesis (declared umbrella tags + the CD/STATE/COUNTY id
  // patterns; metro/country synthesis is data-driven and skipped).
  // Under-detecting hidden sources can only produce false NEGATIVES
  // (a pill we miss that the full build still catches) — never false
  // positives that would block a good deploy. That's the safe
  // direction for a fast gate.
  const CD_TAG = "congressional-district";
  const STATE_TAG = "us-state";
  const METRO_TAG = "metro";
  const COUNTRY_TAG = "country-specific";
  const COUNTY_TAG = "us-county";
  // ID patterns that cause library.json.ts to synthesize an umbrella
  // geo tag even when the YAML doesn't declare one. Ported from
  // src/lib/{congressional-districts,county-sources}.ts.
  const CD_ID = [
    /^usaspending\/district_[a-z]{2}_[a-z0-9]{2}$/,
    /^acs_cd\/[a-z0-9_]+_[a-z]{2}_[a-z0-9]{2}$/,
  ];
  const STATE_ID = [
    /^usaspending\/state_[a-z]{2}$/,
    /^(?:fred|bls)\/state_.+_[a-z]{2}$/,
    /^acs_state\/.+_[a-z]{2}$/,
  ];
  // (No COUNTY_ID pattern: county sources are NOT hidden by default —
  // see isHiddenByDefault below. If county-level mass-classification
  // is ever needed, mirror the CD/STATE pattern here.)
  const matchesAny = (id, res) => res.some((re) => re.test(id));
  // Mirror library.json.ts isHiddenByDefault: CD/STATE/METRO/COUNTRY
  // (NOT county) hide a source from the default list.
  const isHiddenByDefault = (id, tags) =>
    tags.includes(CD_TAG) ||
    tags.includes(STATE_TAG) ||
    tags.includes(METRO_TAG) ||
    tags.includes(COUNTRY_TAG) ||
    matchesAny(id, CD_ID) ||
    matchesAny(id, STATE_ID);
  // Mirror library.json.ts isGeoSynthetic: umbrellas + per-entity
  // metro:/country-specific: tags are NOT topical pills.
  const isGeoSynthetic = (t) =>
    t === CD_TAG ||
    t === STATE_TAG ||
    t === METRO_TAG ||
    t === COUNTRY_TAG ||
    t === COUNTY_TAG ||
    t.startsWith(`${METRO_TAG}:`) ||
    t.startsWith(`${COUNTRY_TAG}:`);

  const tagsSeenAnywhere = new Set();
  const tagsWithVisibleSource = new Set();
  for (const [id, src] of sourceIndex) {
    if (src.kind === "hint") continue;
    const tags = src.tags ?? [];
    const visible = !isHiddenByDefault(id, tags);
    for (const t of tags) {
      if (isGeoSynthetic(t)) continue;
      tagsSeenAnywhere.add(t);
      if (visible) tagsWithVisibleSource.add(t);
    }
  }
  for (const t of tagsSeenAnywhere) {
    if (!tagsWithVisibleSource.has(t)) {
      failures.push({
        id: `tag:${t}`,
        reason:
          `topical tag pill '${t}' would render with count 0 — every ` +
          `source carrying it is hidden behind a geo chip. Add the tag ` +
          `to at least one national/default-visible source, or drop it. ` +
          `(This mirrors the build-time guard in library.json.ts that ` +
          `fails the Vercel deploy.)`,
        charts: [],
      });
    }
  }

  // 3c. Quarantine scan — the usaspending/metro_* class: a source YAML
  // exists but its data file doesn't, so the picker offers a source
  // whose tile can never load. Policy (Keller, 2026-06-11): broken
  // UNREFERENCED sources must not silently degrade — hide them from
  // the pickers AND flag them loudly until fixed or removed.
  //
  // Cheap full-catalog pass: one fs.stat per source (no JSON parsing),
  // so it runs on every prebuild. The generated quarantine file is
  // consumed by library.json.ts, which drops the ids from the
  // manifest; the file is committed so `astro dev` (which skips
  // prebuild) sees the same state, and any change to it shows up in
  // git diff — that's the durable, visible flag.
  /** @type {Record<string, string>} */
  const quarantine = {};
  for (const [id, src] of sourceIndex) {
    if (referencedBy.has(id)) continue; // referenced = hard-fail path above
    if (!src.dataFile) {
      quarantine[id] = "source YAML has no dataFile field";
      continue;
    }
    try {
      await fs.stat(join(PUBLIC_DIR, src.dataFile));
    } catch (e) {
      if (e.code === "ENOENT") {
        quarantine[id] = `data file missing: ${src.dataFile}`;
        continue;
      }
      throw e;
    }
  }
  const quarantineIds = Object.keys(quarantine).sort();
  if (!FULL_SCAN) {
    // Fast/prebuild mode is the canonical generator for the
    // quarantine file (CI --full is report-only so the two modes
    // can't fight over its contents).
    const qPath = join(ROOT, "src", "lib", "quarantined-sources.json");
    const qPayload = {
      "//": "GENERATED by scripts/audit-source-data.mjs (prebuild) — do not edit. Sources whose data file is missing; library.json.ts hides them from the pickers until the data is fixed or the YAML is removed.",
      ids: Object.fromEntries(quarantineIds.map((id) => [id, quarantine[id]])),
    };
    await fs.writeFile(qPath, JSON.stringify(qPayload, null, 2) + "\n", "utf-8");
  }
  for (const id of quarantineIds) {
    // ::warning:: renders as an annotation in GitHub Actions logs.
    console.log(`::warning::[data-audit] QUARANTINED (hidden from pickers): ${id} — ${quarantine[id]}`);
  }

  // 3d. --full deep scan (CI): JSON-parse every unreferenced source's
  // data file and apply the same order/summary/point-count checks the
  // referenced loop enforces. Report-only — broken unreferenced
  // sources warn loudly rather than block, per the hide-and-flag
  // policy. Costs minutes, which is why it lives in CI, not prebuild.
  if (FULL_SCAN) {
    let deepIssues = 0;
    for (const [id, src] of sourceIndex) {
      if (referencedBy.has(id)) continue;
      if (!src.dataFile || quarantine[id]) continue;
      let parsed;
      try {
        parsed = JSON.parse(await fs.readFile(join(PUBLIC_DIR, src.dataFile), "utf-8"));
      } catch {
        console.log(`::warning::[data-audit/full] ${id}: data file unreadable or invalid JSON (${src.dataFile})`);
        deepIssues++;
        continue;
      }
      if (!parsed || !Array.isArray(parsed.points)) {
        console.log(`::warning::[data-audit/full] ${id}: no points array (${src.dataFile})`);
        deepIssues++;
        continue;
      }
      const orderIssue = pointOrderIssue(parsed.points);
      if (orderIssue) {
        console.log(`::warning::[data-audit/full] ${id}: ${orderIssue} (${src.dataFile})`);
        deepIssues++;
        continue;
      }
      if (parsed.points.length > 0) {
        const drift = await summaryLatestDrift(join(PUBLIC_DIR, src.dataFile), parsed.points);
        if (drift) {
          console.log(`::warning::[data-audit/full] ${id}: ${drift}`);
          deepIssues++;
        }
      }
      // Feed unreferenced sources into the cohort pass too, so an
      // unreferenced-but-stale outlier (e.g. oecd/nor_gov_debt_pct_gdp,
      // frozen at 2021 while its OECD siblings reach 2025) surfaces in
      // CI even though it ships no chart today.
      const cohortKey = cohortKeyFor(id);
      const lastT = lastPointDate(parsed);
      if (cohortKey && lastT) cohortMembers.push({ id, cohortKey, lastT });
    }
    console.log(`[data-audit/full] deep scan: ${deepIssues} issue${deepIssues === 1 ? "" : "s"} across unreferenced sources.`);
  }

  // 3e. Cohort-relative staleness. Country/geo sibling series should
  // advance together; a member whose last point is far behind its
  // cohort's most-recent sibling is a silent upstream break — the file
  // is well-formed and ordered (passes every check above) but ships a
  // chart frozen years in the past. This catches the class the
  // structural checks can't see: correctly-ordered, internally
  // consistent, but stale (oecd/jpn_cpi_yoy frozen at 2021 inside
  // countries/g7_inflation while every other G7 line runs to 2026).
  //
  // WARN, don't block: the heuristic is cohort-relative, and we don't
  // want a legitimately-late single-country report to wedge a deploy.
  // The threshold (~13 months) is well past normal release lag, so a
  // hit is a real freeze, not a country reporting a quarter behind.
  const COHORT_STALE_MS = 400 * 24 * 60 * 60 * 1000; // ~13 months
  const MIN_COHORT = 3;
  // Known-and-accepted cohort outliers: unreferenced series whose upstream
  // genuinely stopped (no successor), so the staleness warning is expected
  // recurring noise, not a new break. Unlike the vitest freshness gate this
  // --full pass had no allowlist, so a permanently-retired member would warn
  // on every CI run and blend a real future freeze into the noise. Keep tiny.
  /** @type {Record<string, string>} */
  const AUDIT_COHORT_ALLOWLIST = {
    "oecd/nor_gov_debt_pct_gdp":
      "OECD dropped Norway from the EO gross-debt series; no successor (retired).",
    "oecd/tur_life_expectancy":
      "OECD DF_LE for Turkey has a pre-2017 vintage discontinuity and lags ~1yr; retired (unreferenced).",
  };
  /** @type {Map<string, typeof cohortMembers>} */
  const byCohort = new Map();
  for (const m of cohortMembers) {
    if (!byCohort.has(m.cohortKey)) byCohort.set(m.cohortKey, []);
    byCohort.get(m.cohortKey).push(m);
  }
  for (const [key, members] of byCohort) {
    if (members.length < MIN_COHORT) continue;
    let maxMs = -Infinity;
    let maxT = "";
    for (const m of members) {
      const ms = Date.parse(m.lastT);
      if (!Number.isNaN(ms) && ms > maxMs) { maxMs = ms; maxT = m.lastT; }
    }
    if (maxMs === -Infinity) continue;
    for (const m of members) {
      const ms = Date.parse(m.lastT);
      if (Number.isNaN(ms)) continue;
      if (maxMs - ms > COHORT_STALE_MS) {
        if (AUDIT_COHORT_ALLOWLIST[m.id]) {
          console.log(
            `[data-audit] cohort outlier (allowlisted, accepted): ${m.id} (${AUDIT_COHORT_ALLOWLIST[m.id]})`,
          );
          continue;
        }
        const behindDays = Math.round((maxMs - ms) / 86400000);
        const reason =
          `data ends ${m.lastT}, ${behindDays} days behind its cohort ` +
          `'${key}' (most recent sibling ends ${maxT}) — likely a silent ` +
          `upstream pipeline break shipping a stale chart`;
        warnings.push({ id: m.id, reason });
        // ::warning:: renders as a GitHub Actions annotation, like the
        // quarantine flags above, so CI surfaces it loudly.
        console.log(`::warning::[data-audit] STALE COHORT OUTLIER: ${m.id} — ${reason}`);
      }
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
