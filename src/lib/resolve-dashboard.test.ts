import { describe, it, expect, vi } from "vitest";
// astro:content is a virtual module Astro provides at build time;
// the test runner doesn't have it. Mock the surface that
// resolve-dashboard.ts touches so we can test the pure functions
// downstream of those imports.
vi.mock("astro:content", () => ({
  getEntry: vi.fn(),
}));
// load-data also imports from elsewhere; resolve-dashboard pulls
// loadSourceData from it, but the pure helpers we test here never
// call it. Stub to keep the module graph clean.
vi.mock("./load-data", () => ({
  loadSourceData: vi.fn(),
}));
import {
  perChartSupportedDeltas,
  dashboardSupportedDeltas,
  type ResolvedSection,
  type ResolvedChart,
} from "./resolve-dashboard";
import type { DeltaWindow } from "./deltas";

// Helper: build a minimum-viable ResolvedChart for tests. We only
// touch chart.data.render and source.data.supportedDeltas, so the
// rest is filled with sensible empties via `as unknown as` to keep
// the cast surface small without requiring Astro's full
// CollectionEntry shape.
function makeChart(
  render: string,
  sourceSupportedDeltas: DeltaWindow[][] = [],
): ResolvedChart {
  return {
    chart: { data: { render } } as unknown as ResolvedChart["chart"],
    sources: sourceSupportedDeltas.map(
      (deltas) =>
        ({ data: { supportedDeltas: deltas } } as unknown as
          ResolvedChart["sources"][number]),
    ),
  };
}

function sectionWith(charts: ResolvedChart[]): ResolvedSection {
  return { title: null, charts };
}

describe("perChartSupportedDeltas", () => {
  it("returns [] for choropleth charts regardless of any sources", () => {
    // Choropleth charts don't bind to time-series sources at all;
    // they reference a (geo, indicator, vintage) tuple. Even if some
    // future hand-crafted chart YAML attached a sources[] to a
    // choropleth chart, the resolver should still report no time
    // windows so the dashboard-level pill computation doesn't try
    // to surface useless delta buttons.
    const section = sectionWith([
      makeChart("choropleth", [["1y", "10y"]]),
    ]);
    expect(perChartSupportedDeltas([section])).toEqual([[]]);
  });

  it("returns the intersection of sources' supportedDeltas for time-series charts", () => {
    const section = sectionWith([
      makeChart("line", [
        ["1m", "1y", "10y"], // source A supports these
        ["1y", "10y", "30y"], // source B supports these
      ]),
    ]);
    // Intersection: only 1y + 10y are supported by both.
    expect(perChartSupportedDeltas([section])[0]).toEqual(["1y", "10y"]);
  });

  it("mixes choropleth + time-series in the same dashboard correctly", () => {
    const section = sectionWith([
      makeChart("line", [["1y", "10y"]]),
      makeChart("choropleth"),
      makeChart("line", [["1m", "1y"]]),
    ]);
    const result = perChartSupportedDeltas([section]);
    expect(result).toHaveLength(3);
    expect(result[0]).toEqual(["1y", "10y"]);
    expect(result[1]).toEqual([]); // choropleth
    expect(result[2]).toEqual(["1m", "1y"]);
  });
});

describe("dashboardSupportedDeltas", () => {
  it("falls back to the full window list when every chart is choropleth", () => {
    // A dashboard with nothing but heatmaps would otherwise produce
    // an empty pill row, which the layout's window-selector renders
    // as a bare gap. The fallback to the full DELTA_WINDOWS keeps
    // the pills visible (even though clicking them has no effect
    // on snapshot maps) and prevents the layout from breaking on
    // an otherwise-valid configuration.
    const section = sectionWith([
      makeChart("choropleth"),
      makeChart("choropleth"),
    ]);
    const supported = dashboardSupportedDeltas([section]);
    // Should include some standard windows in the fallback.
    expect(supported.length).toBeGreaterThan(0);
    expect(supported).toContain("1y");
  });

  it("takes the union of supported deltas across charts", () => {
    // Chart A only supports 1y + 10y; Chart B only supports 5y + 30y.
    // The dashboard pill set should include all four.
    const section = sectionWith([
      makeChart("line", [["1y", "10y"]]),
      makeChart("line", [["5y", "30y"]]),
    ]);
    const supported = dashboardSupportedDeltas([section]);
    expect(supported).toContain("1y");
    expect(supported).toContain("5y");
    expect(supported).toContain("10y");
    expect(supported).toContain("30y");
  });

  it("excludes choropleth charts from the union but still uses other charts", () => {
    const section = sectionWith([
      makeChart("line", [["1y", "10y"]]),
      makeChart("choropleth"),
    ]);
    const supported = dashboardSupportedDeltas([section]);
    expect(supported).toEqual(["1y", "10y"]);
  });
});
