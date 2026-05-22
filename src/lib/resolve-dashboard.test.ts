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
  resolveChart,
  type ResolvedSection,
  type ResolvedChart,
} from "./resolve-dashboard";
import type { DeltaWindow } from "./deltas";
import type { InlineChart } from "./composer-state";

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

function sectionWith(
  charts: ResolvedChart[],
  overrides: Partial<Pick<ResolvedSection, "defaultDelta" | "fixedRange">> = {},
): ResolvedSection {
  return { title: null, charts, ...overrides };
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

describe("inline-chart synthesis carries presentation fields", () => {
  // Regression guard: the resolve-dashboard inline-chart synthesizer
  // used to drop `annotations`, `shading`, `transform`, `percentDisplay`,
  // and the bar fields when building the fake CollectionEntry it hands
  // to Chart.astro. The composer happily wrote them into
  // state.inlineCharts.<id> on save, but the renderer never saw them
  // again — user-typed annotations and picked shading bands silently
  // failed to render on inline charts. The schema in
  // composer-state.ts is the source of truth for what an InlineChart
  // can carry; this test asserts every visual field on the spec ends
  // up on the synthesized chart's data.
  it("copies annotations, shading, transform, percentDisplay, and bar fields through to chart.data", async () => {
    // Mock getEntry to return a valid source-shaped object so the
    // synthesis doesn't bail on "source not found".
    const { getEntry } = await import("astro:content");
    const fakeSource = {
      id: "fred/dgs10",
      data: {
        kind: "timeseries",
        dataFile: "data/fred/DGS10.json",
        supportedDeltas: ["1y", "5y", "10y", "30y", "50y"],
        formatting: { style: "percent", decimals: 2 },
      },
    };
    (getEntry as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      fakeSource,
    );
    // Mock loadSourceData since resolveSourceById fetches data points.
    // Return one point so the source survives the resolver's empty-check.
    const { loadSourceData } = await import("./load-data");
    (loadSourceData as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      kind: "timeseries",
      points: [{ t: "2025-01-01", v: 4.5 }],
    });
    const spec: InlineChart = {
      title: "10Y with annotations",
      sources: ["fred/dgs10"],
      render: "line",
      // Visual fields the synthesis used to drop:
      annotations: [
        { date: "2008-09-15", label: "Lehman" },
        { date: "2020-03-15", label: "COVID", position: "below" },
      ],
      shading: ["recessions", "fed_chairs"],
      transform: "yoy_pct",
      percentDisplay: "decimal",
      barOrientation: "horizontal",
      barSort: "desc",
      barAsOf: "2025-01-01",
    };
    const inlineCharts: Record<string, InlineChart> = {
      "inline:abc12345": spec,
    };
    const resolved = await resolveChart(
      "inline:abc12345",
      inlineCharts,
      undefined,
      undefined,
    );
    expect(resolved).not.toBeNull();
    const data = resolved!.chart.data as unknown as {
      title: string;
      annotations?: typeof spec.annotations;
      shading?: typeof spec.shading;
      transform?: typeof spec.transform;
      percentDisplay?: typeof spec.percentDisplay;
      barOrientation?: typeof spec.barOrientation;
      barSort?: typeof spec.barSort;
      barAsOf?: typeof spec.barAsOf;
    };
    // Title proves the synthesis ran at all (not just returning the
    // spec by accident).
    expect(data.title).toBe("10Y with annotations");
    // Every visual field should be carried through verbatim.
    expect(data.annotations).toEqual(spec.annotations);
    expect(data.shading).toEqual(spec.shading);
    expect(data.transform).toBe("yoy_pct");
    expect(data.percentDisplay).toBe("decimal");
    expect(data.barOrientation).toBe("horizontal");
    expect(data.barSort).toBe("desc");
    expect(data.barAsOf).toBe("2025-01-01");
  });
});

describe("ResolvedSection — per-section window overrides", () => {
  // These are interface-level checks: the dashboard renderers
  // (index.astro, [...slug].astro, u/[slug].astro, custom.astro) read
  // section.defaultDelta / section.fixedRange and pass them to the
  // Chart component as dashboardWindow / dashboardFixedRange. The
  // tests just confirm the ResolvedSection shape carries those fields
  // through; the runtime behavior lives in the templates.
  it("carries defaultDelta when set", () => {
    const section = sectionWith(
      [makeChart("line", [["1y", "10y", "30y"]])],
      { defaultDelta: "10y" },
    );
    expect(section.defaultDelta).toBe("10y");
    expect(section.fixedRange).toBeUndefined();
  });

  it("carries fixedRange when set", () => {
    const range = { start: "1990-01-01", end: "1999-12-31" };
    const section = sectionWith(
      [makeChart("line", [["10y", "30y"]])],
      { fixedRange: range },
    );
    expect(section.fixedRange).toEqual(range);
  });

  it("can carry both — renderer is responsible for precedence", () => {
    // The schema doesn't forbid setting both (e.g. while user is
    // mid-edit in the composer). The renderer picks fixedRange over
    // defaultDelta when both are present.
    const section = sectionWith(
      [makeChart("line", [["1y", "10y"]])],
      {
        defaultDelta: "10y",
        fixedRange: { start: "2000-01-01", end: "2009-12-31" },
      },
    );
    expect(section.defaultDelta).toBe("10y");
    expect(section.fixedRange).toEqual({
      start: "2000-01-01",
      end: "2009-12-31",
    });
  });
});
