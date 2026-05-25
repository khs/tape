/**
 * Tests for the bar-snapshot resolver.
 *
 * This is the helper page renderers ([...slug].astro, custom.astro,
 * u/[slug].astro, embed/chart/[...id].astro) call to build the
 * Map<chartId, BarSnapshotEntry[]> their JSX needs. The fan-out logic
 * is small but the swallow-on-error contract is load-bearing: a single
 * misnamed source MUST NOT crash a whole page render. The tests below
 * lock that down without touching the filesystem — `loadSourceData` is
 * mocked so we can drive it through happy, missing, and curve-kind
 * branches deterministically.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import type { SourceData } from "./data-types";

// Mock `./load-data` BEFORE importing the module under test, so the
// resolver picks up the mocked binding. `snapshotAt` stays as the real
// implementation — it's pure and we want the integration through it.
vi.mock("./load-data", async () => {
  const actual =
    await vi.importActual<typeof import("./load-data")>("./load-data");
  return {
    ...actual,
    loadSourceData: vi.fn<(dataFile: string) => Promise<SourceData>>(),
  };
});

import { loadSourceData } from "./load-data";
import {
  resolveBarSnapshot,
  resolveBarSnapshots,
} from "./resolve-bar-snapshots";

const mockedLoad = vi.mocked(loadSourceData);

/** Build a minimal TimeSeriesData. The resolver only reads kind +
 *  points; the rest are placeholders. */
function tsd(id: string, points: { t: string; v: number }[]): SourceData {
  return {
    id,
    name: id,
    kind: "timeseries",
    lastUpdated: "2025-01-01",
    points,
  };
}

/** Build a minimal CurveData — used to verify the resolver skips
 *  non-timeseries shapes cleanly. */
function curve(id: string): SourceData {
  return {
    id,
    name: id,
    kind: "curve",
    lastUpdated: "2025-01-01",
    snapshots: [],
  };
}

beforeEach(() => {
  mockedLoad.mockReset();
});

describe("resolveBarSnapshot", () => {
  it("returns one entry per timeseries source with its latest value when barAsOf is undefined", async () => {
    mockedLoad.mockImplementation(async (df) => {
      if (df === "data/a.json")
        return tsd("a", [
          { t: "2024-01-01", v: 1 },
          { t: "2024-06-01", v: 2 },
        ]);
      if (df === "data/b.json")
        return tsd("b", [
          { t: "2024-01-01", v: 10 },
          { t: "2024-06-01", v: 20 },
        ]);
      throw new Error("unexpected dataFile " + df);
    });
    const result = await resolveBarSnapshot([
      { id: "a", data: { dataFile: "data/a.json" } },
      { id: "b", data: { dataFile: "data/b.json" } },
    ]);
    expect(result).toEqual([
      { sourceId: "a", value: 2, date: "2024-06-01" },
      { sourceId: "b", value: 20, date: "2024-06-01" },
    ]);
  });

  it("snapshots every source at the same barAsOf date", async () => {
    // Two sources with different cadence — same anchor date should
    // pick each one's at-or-before point independently.
    mockedLoad.mockImplementation(async (df) => {
      if (df === "data/a.json")
        return tsd("a", [
          { t: "2022-01-01", v: 1 },
          { t: "2023-01-01", v: 2 },
          { t: "2024-01-01", v: 3 },
        ]);
      if (df === "data/b.json")
        return tsd("b", [
          { t: "2022-06-01", v: 10 },
          { t: "2023-06-01", v: 20 },
          { t: "2024-06-01", v: 30 },
        ]);
      throw new Error("unexpected dataFile " + df);
    });
    const result = await resolveBarSnapshot(
      [
        { id: "a", data: { dataFile: "data/a.json" } },
        { id: "b", data: { dataFile: "data/b.json" } },
      ],
      "2023-09-01",
    );
    // a: at-or-before 2023-09-01 is 2023-01-01 (v=2).
    // b: at-or-before 2023-09-01 is 2023-06-01 (v=20).
    expect(result).toEqual([
      { sourceId: "a", value: 2, date: "2023-01-01" },
      { sourceId: "b", value: 20, date: "2023-06-01" },
    ]);
  });

  it("silently drops sources whose load throws (file-not-found, parse error)", async () => {
    // Promise per the contract: better a 9-bar chart than a 500 on the
    // whole page when one source's JSON is missing.
    mockedLoad.mockImplementation(async (df) => {
      if (df === "data/a.json") return tsd("a", [{ t: "2024-01-01", v: 1 }]);
      throw new Error("ENOENT: data/missing.json");
    });
    const result = await resolveBarSnapshot([
      { id: "a", data: { dataFile: "data/a.json" } },
      { id: "missing", data: { dataFile: "data/missing.json" } },
    ]);
    expect(result).toEqual([
      { sourceId: "a", value: 1, date: "2024-01-01" },
    ]);
  });

  it("silently drops sources whose earliest point is after barAsOf", async () => {
    // The source isn't defined at the requested anchor — drop it so
    // the chart renders without that bar, rather than displaying a
    // phantom 0-height bar or crashing.
    mockedLoad.mockImplementation(async (df) => {
      if (df === "data/a.json")
        return tsd("a", [
          { t: "2024-01-01", v: 1 },
          { t: "2024-06-01", v: 2 },
        ]);
      throw new Error("unexpected dataFile " + df);
    });
    const result = await resolveBarSnapshot(
      [{ id: "a", data: { dataFile: "data/a.json" } }],
      "2022-01-01",
    );
    expect(result).toEqual([]);
  });

  it("skips curve-kind sources cleanly (no crash on yield curves / futures curves)", async () => {
    // Curve data lacks a points[] of the same shape; the resolver's
    // kind === "timeseries" guard is the safety. Without it the bar
    // chart page that accidentally references a curve source crashes.
    mockedLoad.mockImplementation(async (df) => {
      if (df === "data/yield_curve.json") return curve("yield_curve");
      if (df === "data/cpi.json")
        return tsd("cpi", [{ t: "2024-01-01", v: 3.2 }]);
      throw new Error("unexpected dataFile " + df);
    });
    const result = await resolveBarSnapshot([
      { id: "yield_curve", data: { dataFile: "data/yield_curve.json" } },
      { id: "cpi", data: { dataFile: "data/cpi.json" } },
    ]);
    expect(result).toEqual([
      { sourceId: "cpi", value: 3.2, date: "2024-01-01" },
    ]);
  });

  it("returns an empty array for an empty source list", async () => {
    const result = await resolveBarSnapshot([]);
    expect(result).toEqual([]);
    // Confirms no fetch was attempted.
    expect(mockedLoad).not.toHaveBeenCalled();
  });
});

describe("resolveBarSnapshots", () => {
  it("only resolves charts whose render === 'bar' — non-bar charts are silently skipped", async () => {
    // Real call site passes the full resolved-chart list. The helper
    // is supposed to filter on render === "bar" internally so callers
    // don't have to pre-filter.
    mockedLoad.mockImplementation(async () =>
      tsd("x", [{ t: "2024-01-01", v: 1 }]),
    );
    const result = await resolveBarSnapshots([
      {
        chart: { id: "line1", data: { render: "line" } },
        sources: [{ id: "x", data: { dataFile: "data/x.json" } }],
      },
      {
        chart: { id: "bar1", data: { render: "bar" } },
        sources: [{ id: "x", data: { dataFile: "data/x.json" } }],
      },
      {
        chart: { id: "choropleth1", data: { render: "choropleth" } },
        sources: [{ id: "x", data: { dataFile: "data/x.json" } }],
      },
    ]);
    expect(result.has("bar1")).toBe(true);
    expect(result.has("line1")).toBe(false);
    expect(result.has("choropleth1")).toBe(false);
    expect(result.size).toBe(1);
  });

  it("threads each chart's barAsOf through to the per-chart resolver", async () => {
    // Two bar charts with different barAsOf anchors on the same
    // source. Each should resolve to the right point in time.
    mockedLoad.mockImplementation(async () =>
      tsd("rates", [
        { t: "2020-01-01", v: 1.5 },
        { t: "2022-01-01", v: 3.0 },
        { t: "2024-01-01", v: 5.0 },
      ]),
    );
    const result = await resolveBarSnapshots([
      {
        chart: { id: "bar_2021", data: { render: "bar", barAsOf: "2021-06-01" } },
        sources: [{ id: "rates", data: { dataFile: "data/rates.json" } }],
      },
      {
        chart: { id: "bar_2024", data: { render: "bar", barAsOf: "2024-12-31" } },
        sources: [{ id: "rates", data: { dataFile: "data/rates.json" } }],
      },
    ]);
    expect(result.get("bar_2021")).toEqual([
      { sourceId: "rates", value: 1.5, date: "2020-01-01" },
    ]);
    expect(result.get("bar_2024")).toEqual([
      { sourceId: "rates", value: 5.0, date: "2024-01-01" },
    ]);
  });

  it("returns an empty map when no charts are bar-rendered", async () => {
    const result = await resolveBarSnapshots([
      {
        chart: { id: "line1", data: { render: "line" } },
        sources: [{ id: "x", data: { dataFile: "data/x.json" } }],
      },
    ]);
    expect(result.size).toBe(0);
  });

  it("returns an empty map for an empty chart list", async () => {
    const result = await resolveBarSnapshots([]);
    expect(result.size).toBe(0);
  });

  it("keys the map by chart id (not by source id or label)", async () => {
    // The page renderer plucks snapshots by chart id; if the key
    // semantics drifted (e.g. to source id), every bar chart would
    // render empty.
    mockedLoad.mockImplementation(async () =>
      tsd("src1", [{ t: "2024-01-01", v: 42 }]),
    );
    const result = await resolveBarSnapshots([
      {
        chart: { id: "my-chart-id", data: { render: "bar" } },
        sources: [{ id: "src1", data: { dataFile: "data/src1.json" } }],
      },
    ]);
    expect(Array.from(result.keys())).toEqual(["my-chart-id"]);
  });
});
