import type { SourceData, TimeSeriesData } from "./data-types";
import type { DeltaWindow } from "./deltas";
import { windowStartMs } from "./deltas";
import fs from "node:fs";
import path from "node:path";

// Module-scoped cache. Warm serverless functions hit memory rather than
// re-fetching the same source JSON on every page render. Cold-start
// resets are cheap because each entry is ~10-100KB.
const dataCache = new Map<string, SourceData>();

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

  // Try local filesystem first. Works during build and in any context
  // where the data file is on disk (local dev, the prerendering step).
  const fullPath = path.join(process.cwd(), "public", dataFile);
  let data: SourceData | null = null;
  try {
    const raw = fs.readFileSync(fullPath, "utf-8");
    data = JSON.parse(raw) as SourceData;
  } catch (err) {
    const code = (err as NodeJS.ErrnoException).code;
    if (code !== "ENOENT") throw err;
    // ENOENT in serverless context — the data file isn't bundled with
    // the function. Fall back to HTTPS fetch against the deployment's
    // own static assets. VERCEL_URL is the per-deployment hostname
    // (the same code that produced this function was deployed with
    // the matching data files).
    const origin = process.env.VERCEL_URL
      ? `https://${process.env.VERCEL_URL}`
      : process.env.SITE_URL ?? "http://localhost:4321";
    const url = `${origin}/${dataFile}`;
    const res = await fetch(url);
    if (!res.ok) {
      throw new Error(`loadSourceData fetch failed: ${url} -> ${res.status}`);
    }
    data = (await res.json()) as SourceData;
  }
  dataCache.set(dataFile, data);
  return data;
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
