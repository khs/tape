export interface TimeSeriesPoint {
  t: string; // ISO date (YYYY-MM-DD) or ISO timestamp
  v: number;
}

export interface TimeSeriesData {
  id: string;
  name: string;
  kind: "timeseries";
  unit?: string;
  lastUpdated: string;
  points: TimeSeriesPoint[];
}

export interface CurvePoint {
  tenor: string; // e.g. "M1", "M2", "Y1"
  tenorMonths: number;
  v: number;
}

export interface CurveSnapshot {
  asOf: string; // ISO date
  points: CurvePoint[];
}

export interface CurveData {
  id: string;
  name: string;
  kind: "curve";
  unit?: string;
  lastUpdated: string;
  snapshots: CurveSnapshot[]; // most recent last
}

export type SourceData = TimeSeriesData | CurveData;

/**
 * Compact tile-summary representation of a timeseries source. Produced
 * by `pipelines/build_summaries.py` as <id>.summary.json siblings to
 * the full-data <id>.json. ~5KB vs the full file's typical ~30-50KB.
 *
 * Use case: a chart tile only needs latest + prior + a downsampled
 * sparkline for each delta window. The expanded chart dialog still
 * needs full data, but that gets lazy-fetched on dialog open. This
 * separation keeps initial page payloads small and Vercel bandwidth
 * scaling sane as the source library grows.
 *
 * Windows are the full DELTA_WINDOWS set ("1w" through "50y" plus
 * "ytd"); the renderer pulls whichever ones the source's supportedDeltas
 * declares are valid. Sparser windows naturally have fewer spark points.
 */
export interface TimeSeriesSummary {
  id: string;
  name: string;
  kind: "timeseries";
  unit?: string;
  lastUpdated: string;
  latest: TimeSeriesPoint;
  priors: Partial<Record<string, TimeSeriesPoint>>;
  sparks: Partial<Record<string, TimeSeriesPoint[]>>;
}
