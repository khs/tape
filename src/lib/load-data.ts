import type { SourceData, TimeSeriesData } from "./data-types";
import type { DeltaWindow } from "./deltas";
import { windowStartMs } from "./deltas";
import fs from "node:fs";
import path from "node:path";

/**
 * Load a Source's data JSON from public/data/ at build time.
 * dataFile is relative to public/ (e.g. "data/oil/wti_front.json").
 */
export function loadSourceData(dataFile: string): SourceData {
  const fullPath = path.join(process.cwd(), "public", dataFile);
  const raw = fs.readFileSync(fullPath, "utf-8");
  return JSON.parse(raw) as SourceData;
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
