import type { SourceData, TimeSeriesData, TimeSeriesPoint, TimeSeriesSummary } from "./data-types";
import type { DeltaWindow } from "./deltas";
import { windowStartMs } from "./deltas";
import fs from "node:fs";
import path from "node:path";

// Module-scoped cache. Warm serverless functions hit memory rather than
// re-fetching the same source JSON on every page render. Cold-start
// resets are cheap because each entry is ~10-100KB.
const dataCache = new Map<string, SourceData>();
const summaryCache = new Map<string, TimeSeriesSummary>();

/**
 * Load a Source's data JSON from public/data/.
 * `dataFile` is relative to public/ (e.g. "data/oil/wti_front.json").
 *
 * Dual-mode by necessity:
 *
 *  - At build time (astro build), the file is on disk under
 *    public/data/, so fs.readFileSync resolves directly. Fast and
 *    synchronous-ish.
 *
 *  - At Vercel function runtime, public/data/ is NOT inside the
 *    function bundle — it's served as static assets from the same
 *    deployment's CDN. We can't fs.readFileSync it; we have to fetch
 *    over HTTPS to the deployment's own URL. ~50ms per cold fetch,
 *    cached after that.
 *
 * Putting the data into the bundle is also possible (and how we used
 * to do it) but with ~5,000 source files now it'd blow past Vercel's
 * 250MB serverless-function-size limit. Fetch-from-static keeps the
 * function tiny.
 */
export async function loadSourceData(dataFile: string): Promise<SourceData> {
  const cached = dataCache.get(dataFile);
  if (cached) return cached;

  // Detect function-runtime context. VERCEL_REGION is only set when
  // executing inside a Vercel function — NOT during build (VERCEL=1
  // is set in both contexts, so it's unsuitable for this check). In
  // build / local-dev contexts, public/data/ is on disk so fs works.
  // In function-runtime context, public/data/ is stripped from the
  // bundle by the astro:build:done hook so we must HTTPS-fetch.
  const isServerless = !!process.env.VERCEL_REGION;
  let data: SourceData | null = null;

  if (!isServerless) {
    const fullPath = path.join(process.cwd(), "public", dataFile);
    try {
      const raw = fs.readFileSync(fullPath, "utf-8");
      data = JSON.parse(raw) as SourceData;
    } catch (err) {
      // Build / dev failure — let it propagate. Whoever called us is in
      // a context where the file should exist on disk and doesn't.
      throw err;
    }
  } else {
    // Serverless: fetch from this deployment's own static-asset origin.
    // Preference order:
    //   1. SITE_URL — explicit override (custom domain)
    //   2. VERCEL_PROJECT_PRODUCTION_URL — stable production hostname
    //      (set on production deploys, points at the canonical URL)
    //   3. VERCEL_URL — per-deployment hash hostname
    // All three should serve the same static assets, but the stable
    // production URL is what the rest of the world hits, so prefer it.
    const origin =
      process.env.SITE_URL ??
      (process.env.VERCEL_PROJECT_PRODUCTION_URL
        ? `https://${process.env.VERCEL_PROJECT_PRODUCTION_URL}`
        : process.env.VERCEL_URL
          ? `https://${process.env.VERCEL_URL}`
          : "");
    if (!origin) {
      throw new Error(
        `loadSourceData: no SITE_URL, VERCEL_PROJECT_PRODUCTION_URL, or VERCEL_URL in serverless env`,
      );
    }
    const url = `${origin}/${dataFile}`;
    try {
      const res = await fetch(url);
      if (!res.ok) {
        throw new Error(`HTTP ${res.status} from ${url}`);
      }
      data = (await res.json()) as SourceData;
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      throw new Error(`fetch failed: ${url} (${msg})`);
    }
  }
  if (data) dataCache.set(dataFile, data);
  return data!;
}

/**
 * Compact tile-summary loader, parallel to loadSourceData but reads
 * the .summary.json sibling file (produced by pipelines/build_summaries.py).
 *
 * Use this when tile-level rendering is all that's needed (level + delta
 * + sparkline per supported window). The full-data file is ~5-10x larger
 * and is only needed by the expanded chart dialog — which lazy-fetches
 * it client-side when the user clicks the tile.
 *
 * Resolution semantics mirror loadSourceData: filesystem read first
 * (works at build time and on local dev), HTTPS fetch fallback against
 * the deployment's own static-asset URL when the file isn't on disk
 * (i.e., serverless function context).
 */
export async function loadSourceSummary(dataFile: string): Promise<TimeSeriesSummary | null> {
  const summaryFile = dataFile.replace(/\.json$/, ".summary.json");
  const cached = summaryCache.get(summaryFile);
  if (cached) return cached;

  // Same dual-mode detection as loadSourceData: function runtime is the
  // only context where public/* isn't on disk (we strip it from the
  // bundle in astro:build:done), so VERCEL_REGION is the cleanest
  // signal. Anywhere else (local dev, astro build, even Vercel CI
  // during build) the fs read works.
  const isServerless = !!process.env.VERCEL_REGION;
  let data: TimeSeriesSummary | null = null;
  if (!isServerless) {
    const fullPath = path.join(process.cwd(), "public", summaryFile);
    try {
      const raw = fs.readFileSync(fullPath, "utf-8");
      data = JSON.parse(raw) as TimeSeriesSummary;
    } catch (err) {
      const code = (err as NodeJS.ErrnoException).code;
      // ENOENT means there's no .summary.json for this source — fine,
      // summaries are optional. Any other fs error propagates.
      if (code !== "ENOENT") throw err;
      return null;
    }
  } else {
    const origin =
      process.env.SITE_URL ??
      (process.env.VERCEL_PROJECT_PRODUCTION_URL
        ? `https://${process.env.VERCEL_PROJECT_PRODUCTION_URL}`
        : process.env.VERCEL_URL
          ? `https://${process.env.VERCEL_URL}`
          : "");
    if (!origin) return null;
    const url = `${origin}/${summaryFile}`;
    try {
      const res = await fetch(url);
      if (!res.ok) return null;
      data = (await res.json()) as TimeSeriesSummary;
    } catch {
      return null;
    }
  }
  if (data) summaryCache.set(summaryFile, data);
  return data;
}

// Window definitions for in-memory summary computation. Mirrors the
// DELTA_WINDOWS / DELTA_DAYS in deltas.ts so we don't have a circular
// import. The "ytd" key is handled specially below.
const SUMMARY_WINDOWS_DAYS: Record<string, number> = {
  "1w": 7,
  "1m": 30,
  "1y": 365,
  "5y": 1825,
  "10y": 3650,
  "30y": 10950,
  "50y": 18250,
};
const SUMMARY_SPARK_POINTS = 30;

/**
 * Compute per-window sparks + priors from a full timeseries.
 * Used when we already have full data server-side (op'd / derived
 * charts) and need to bake summary-shape data into the client payload.
 *
 * For single-source non-derived charts, prefer `loadSourceSummary`
 * which reads the pre-computed .summary.json directly — no need to
 * load the full series at all.
 */
export function computeSummaryFromPoints(
  fullPoints: TimeSeriesPoint[],
  supportedDeltas: readonly string[],
): {
  latest: TimeSeriesPoint;
  priors: Record<string, TimeSeriesPoint>;
  sparks: Record<string, TimeSeriesPoint[]>;
} | null {
  if (fullPoints.length === 0) return null;
  const latest = fullPoints[fullPoints.length - 1];
  const latestMs = new Date(latest.t).getTime();
  const priors: Record<string, TimeSeriesPoint> = {};
  const sparks: Record<string, TimeSeriesPoint[]> = {};
  for (const window of supportedDeltas) {
    let startMs: number;
    if (window === "ytd") {
      const y = new Date(latest.t).getUTCFullYear();
      startMs = Date.UTC(y, 0, 1);
    } else {
      const days = SUMMARY_WINDOWS_DAYS[window];
      if (days === undefined) continue;
      startMs = latestMs - days * 86400000;
    }
    // Prior: last point at-or-before startMs
    let prior: TimeSeriesPoint | null = null;
    for (const p of fullPoints) {
      const t = new Date(p.t).getTime();
      if (t <= startMs) prior = p;
      else break;
    }
    if (prior && prior.t !== latest.t) priors[window] = prior;
    // Spark: uniformly sampled subset within [startMs, latestMs]
    const startIdx = fullPoints.findIndex(
      (p) => new Date(p.t).getTime() >= startMs,
    );
    if (startIdx === -1) continue;
    const sliced = fullPoints.slice(startIdx);
    if (sliced.length <= SUMMARY_SPARK_POINTS) {
      sparks[window] = sliced;
    } else {
      const indices: number[] = [];
      for (let i = 0; i < SUMMARY_SPARK_POINTS; i++) {
        indices.push(
          Math.round((i * (sliced.length - 1)) / (SUMMARY_SPARK_POINTS - 1)),
        );
      }
      sparks[window] = indices.map((idx) => sliced[idx]);
    }
  }
  return { latest, priors, sparks };
}

/**
 * Find the point in a timeseries closest to N days before the most recent point.
 * Returns null if the series doesn't extend back that far.
 */
export function findPriorPoint(
  data: TimeSeriesData,
  window: DeltaWindow,
): { t: string; v: number } | null {
  if (data.points.length === 0) return null;
  const last = data.points[data.points.length - 1];
  // windowStartMs handles YTD (anchors to Jan 1) and trailing windows
  // (subtracts DELTA_DAYS) in one call.
  const targetMs = windowStartMs(new Date(last.t).getTime(), window);

  if (new Date(data.points[0].t).getTime() > targetMs) return null;

  // Find closest point at or before target
  let best = data.points[0];
  for (const p of data.points) {
    if (new Date(p.t).getTime() <= targetMs) {
      best = p;
    } else {
      break;
    }
  }
  return best;
}

export function currentPoint(
  data: TimeSeriesData,
): { t: string; v: number } | null {
  if (data.points.length === 0) return null;
  return data.points[data.points.length - 1];
}
