export interface TimeSeriesPoint {
  t: string; // ISO date (YYYY-MM-DD) or ISO timestamp
  v: number;
}

/**
 * Forward-looking projections, keyed by vintage date (the date the
 * forecast was published — "YYYY-MM" or "YYYY-MM-DD"). Each entry's
 * array is the full forecast as of that vintage, ordered chronologically
 * with the same shape as historical `points`.
 *
 * Multiple vintages can coexist on a single source so a future "as of"
 * picker (Phase 3) can show "what the forecast looked like in Feb 2024".
 *
 * Use cases this covers today:
 *   - CBO Budget & Economic Outlook (Feb + Aug releases each year)
 *   - SSA Trustees Report (annual, intermediate-cost projection)
 *   - Yahoo / NYMEX futures curves (snapshotted per pipeline run; the
 *     curve at expiry T is recorded with `t = T's mid-month date`)
 *   - CMS NHE projections (annual)
 *
 * Renderer default (Phase 2): pick the latest vintage by key sort, draw
 * its points as a dashed extension of the historical line. Earlier
 * vintages are stored but not rendered until Phase 3 ships the picker.
 */
export type Projections = Record<string, TimeSeriesPoint[]>;

export interface TimeSeriesData {
  id: string;
  name: string;
  kind: "timeseries";
  unit?: string;
  lastUpdated: string;
  points: TimeSeriesPoint[];
  projections?: Projections;
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
  /**
   * The most recent projection vintage, baked into the summary so the
   * tile sparkline can show a forward-looking dashed extension without
   * a full-data fetch. Older vintages live in the full data file's
   * `projections` map and are loaded lazily on dialog open.
   *
   * Absent when the source has no projections.
   */
  latestProjection?: {
    vintage: string;
    points: TimeSeriesPoint[];
  };
}
