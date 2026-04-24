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
