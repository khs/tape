/**
 * Shared loaders for the corpus-walking data-integrity + freshness suites.
 *
 * These read the REAL data tree (public/data) and content YAML directly
 * from disk (not via astro:content, which needs the Astro runtime). To
 * stay fast enough for a CI merge gate we never parse all ~34k source
 * YAMLs: source-ID existence comes from file PATHS (no parse), and we only
 * open the data files + YAMLs of sources actually referenced by a live
 * chart (~450). The ~38k choropleth files and the unreferenced long tail
 * are left to scripts/audit-source-data.mjs --full (the CI deep scan).
 *
 * NOT a *.test.ts file, so vitest does not run it as a suite — it is only
 * imported by the suites in this directory.
 */
import { readFileSync, readdirSync, existsSync } from "node:fs";
import { join, relative, sep } from "node:path";
import yaml from "js-yaml";

// `npm test` runs from the repo root, so cwd is the canonical anchor.
export const ROOT = process.cwd();
const SOURCES_DIR = join(ROOT, "src", "content", "sources");
const CHARTS_DIR = join(ROOT, "src", "content", "charts");
const DASHBOARDS_DIR = join(ROOT, "src", "content", "dashboards");
const PUBLIC_DIR = join(ROOT, "public");

/** The canonical delta-window keys a summary's priors/sparks may use. */
export const DELTA_WINDOWS = new Set([
  "1w", "1m", "ytd", "1y", "5y", "10y", "30y", "50y",
]);

export interface Point {
  t: string;
  v: number;
}
export interface Chart {
  id: string;
  data: Record<string, unknown>;
}
export interface SourceRef {
  id: string;
  data: Record<string, unknown>;
  dataFile: string | undefined;
}

function walk(dir: string, ext: string): string[] {
  const out: string[] = [];
  if (!existsSync(dir)) return out;
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) out.push(...walk(p, ext));
    else if (e.isFile() && e.name.endsWith(ext)) out.push(p);
  }
  return out;
}

function idFromPath(file: string, baseDir: string): string {
  return relative(baseDir, file)
    .replace(/\.(yaml|mdx|md)$/, "")
    .split(sep)
    .join("/");
}

export function readYaml(file: string): Record<string, unknown> {
  return (yaml.load(readFileSync(file, "utf-8")) ?? {}) as Record<string, unknown>;
}
export function readJson(file: string): Record<string, unknown> {
  return JSON.parse(readFileSync(file, "utf-8")) as Record<string, unknown>;
}

// ---- Source IDs (existence only — no parse, fast) -----------------------
let _sourceIds: Set<string> | null = null;
export function sourceIds(): Set<string> {
  if (!_sourceIds) {
    _sourceIds = new Set(
      walk(SOURCES_DIR, ".yaml").map((f) => idFromPath(f, SOURCES_DIR)),
    );
  }
  return _sourceIds;
}
export function sourcePath(id: string): string {
  return join(SOURCES_DIR, ...id.split("/")) + ".yaml";
}

// ---- Charts + dashboards (parse all — only ~550 + ~21) ------------------
let _charts: Chart[] | null = null;
export function charts(): Chart[] {
  if (!_charts) {
    _charts = walk(CHARTS_DIR, ".yaml").map((f) => ({
      id: idFromPath(f, CHARTS_DIR),
      data: readYaml(f),
    }));
  }
  return _charts;
}
let _dashboards: Chart[] | null = null;
export function dashboards(): Chart[] {
  if (!_dashboards) {
    _dashboards = [];
    for (const ext of [".mdx", ".md"]) {
      for (const f of walk(DASHBOARDS_DIR, ext)) {
        const text = readFileSync(f, "utf-8").replace(/\r\n/g, "\n");
        const m = text.match(/^---\n([\s\S]*?)\n---/);
        const data = (m ? (yaml.load(m[1]) ?? {}) : {}) as Record<string, unknown>;
        _dashboards.push({ id: idFromPath(f, DASHBOARDS_DIR), data });
      }
    }
  }
  return _dashboards;
}

/** A live chart still shows in the UI: not deprecated, or deprecated-with-alias. */
export function isLiveChart(c: Chart): boolean {
  return !(c.data.deprecated === true && !c.data.aliasOf);
}

function chartSourceIds(c: Chart): string[] {
  const out: string[] = [];
  for (const key of ["sources", "rightAxisSources"]) {
    const arr = c.data[key];
    if (Array.isArray(arr)) {
      for (const s of arr) if (typeof s === "string") out.push(s);
    }
  }
  return out;
}

/** Source IDs referenced by at least one LIVE chart (the data that ships). */
let _refIds: Set<string> | null = null;
export function referencedSourceIds(): Set<string> {
  if (!_refIds) {
    _refIds = new Set();
    for (const c of charts()) {
      if (!isLiveChart(c)) continue;
      for (const s of chartSourceIds(c)) _refIds.add(s);
    }
  }
  return _refIds;
}

/** Referenced sources that have a YAML on disk (parsed). */
let _refSources: SourceRef[] | null = null;
export function referencedSources(): SourceRef[] {
  if (!_refSources) {
    _refSources = [];
    for (const id of referencedSourceIds()) {
      const p = sourcePath(id);
      if (!existsSync(p)) continue; // dangling refs are caught separately
      const data = readYaml(p);
      _refSources.push({
        id,
        data,
        dataFile: typeof data.dataFile === "string" ? data.dataFile : undefined,
      });
    }
  }
  return _refSources;
}

// ---- Data files ---------------------------------------------------------
export function dataPath(dataFile: string): string {
  return join(PUBLIC_DIR, ...dataFile.split("/"));
}
export function summaryPath(dataFile: string): string {
  return dataPath(dataFile).replace(/\.json$/, ".summary.json");
}
export function isTimeseries(d: Record<string, unknown>): boolean {
  return Array.isArray(d.points);
}
export function points(d: Record<string, unknown>): Point[] {
  return Array.isArray(d.points) ? (d.points as Point[]) : [];
}
export function lastPoint(d: Record<string, unknown>): Point | null {
  const p = points(d);
  return p.length ? p[p.length - 1] : null;
}

/** Median day-gap between consecutive points (series cadence), or null. */
export function medianCadenceDays(pts: Point[]): number | null {
  if (!pts || pts.length < 2) return null;
  const gaps: number[] = [];
  for (let i = 1; i < pts.length; i++) {
    const a = Date.parse(pts[i - 1].t);
    const b = Date.parse(pts[i].t);
    if (!Number.isNaN(a) && !Number.isNaN(b) && b > a) gaps.push((b - a) / 86_400_000);
  }
  if (!gaps.length) return null;
  gaps.sort((x, y) => x - y);
  return gaps[Math.floor(gaps.length / 2)];
}

export const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

/**
 * "Sibling cohort" key for cross-country/geo series, so we can flag a
 * member that froze years behind the rest of its family (the
 * oecd/jpn_cpi_yoy signature). The geo code is the leading 2-3-letter
 * token of the name part: oecd/jpn_cpi_yoy -> oecd::cpi_yoy. Series whose
 * leading token is a real word ("median_listing_price") or whose geo code
 * trails (acs_cd/..._va_08, edu_spending/state_perpupil_ny) have no
 * leading-geo cohort and return null. Mirrors cohortKeyFor in
 * scripts/audit-source-data.mjs.
 */
export function cohortKeyFor(id: string): string | null {
  const slash = id.indexOf("/");
  if (slash < 0) return null;
  const pipeline = id.slice(0, slash);
  const name = id.slice(slash + 1);
  const m = name.match(/^([a-z]{2,3})_(.+)$/);
  return m ? `${pipeline}::${m[2]}` : null;
}
