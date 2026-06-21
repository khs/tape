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
  resolveDashboardDefault,
  effectiveChart,
  isVisibleChart,
  type ResolvedSection,
  type ResolvedChart,
} from "./resolve-dashboard";
import type { DeltaWindow } from "./deltas";
import type { InlineChart } from "./composer-state";
import type { CollectionEntry } from "astro:content";

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
  it("returns [] for map charts regardless of any sources", () => {
    // Map charts don't bind to time-series sources at all;
    // they reference a (geo, indicator, vintage) tuple. Even if some
    // future hand-crafted chart YAML attached a sources[] to a
    // map chart, the resolver should still report no time
    // windows so the dashboard-level pill computation doesn't try
    // to surface useless delta buttons.
    const section = sectionWith([
      makeChart("map", [["1y", "10y"]]),
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

  it("mixes map + time-series in the same dashboard correctly", () => {
    const section = sectionWith([
      makeChart("line", [["1y", "10y"]]),
      makeChart("map"),
      makeChart("line", [["1m", "1y"]]),
    ]);
    const result = perChartSupportedDeltas([section]);
    expect(result).toHaveLength(3);
    expect(result[0]).toEqual(["1y", "10y"]);
    expect(result[1]).toEqual([]); // map
    expect(result[2]).toEqual(["1m", "1y"]);
  });
});

describe("dashboardSupportedDeltas", () => {
  it("falls back to the full window list when every chart is map", () => {
    // A dashboard with nothing but heatmaps would otherwise produce
    // an empty pill row, which the layout's window-selector renders
    // as a bare gap. The fallback to the full DELTA_WINDOWS keeps
    // the pills visible (even though clicking them has no effect
    // on snapshot maps) and prevents the layout from breaking on
    // an otherwise-valid configuration.
    const section = sectionWith([
      makeChart("map"),
      makeChart("map"),
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

  it("excludes map charts from the union but still uses other charts", () => {
    const section = sectionWith([
      makeChart("line", [["1y", "10y"]]),
      makeChart("map"),
    ]);
    const supported = dashboardSupportedDeltas([section]);
    // "max" (all time) is appended for any dashboard with a time-series chart.
    expect(supported).toEqual(["1y", "10y", "max"]);
  });

  it("appends the universal 'max' window for time-series dashboards", () => {
    // No source declares "max", but every series can show all of its history,
    // so the dashboard window selector must offer it (mirrors the per-chart
    // dialog pill row). It sorts last, after the declared windows.
    const section = sectionWith([makeChart("line", [["1y", "5y"]])]);
    const supported = dashboardSupportedDeltas([section]);
    expect(supported).toContain("max");
    expect(supported[supported.length - 1]).toBe("max");
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

describe("resolveDashboardDefault", () => {
  // Lives on the hot path of every dashboard render — picks which
  // pill is highlighted on first paint and which window the tile
  // descriptor renders against.

  it("preserves the requested default when it's in the supported list", () => {
    expect(resolveDashboardDefault("5y", ["1m", "1y", "5y", "10y"])).toBe(
      "5y",
    );
  });

  it("falls back to closestSupported when the requested window is missing", () => {
    // Asked for 1m but only have 1y+; the closest log-day-distance
    // match wins.
    expect(resolveDashboardDefault("1m", ["1y", "5y", "10y"])).toBe("1y");
  });

  it("defaults to 1m when no request was passed", () => {
    // The signed-in home page passes undefined to mean "no preference".
    expect(resolveDashboardDefault(undefined, ["1m", "1y"])).toBe("1m");
  });

  it("when 1m isn't supported and no request is given, falls back via closestSupported", () => {
    // Defaults to 1m → not supported → closest is 1y.
    expect(resolveDashboardDefault(undefined, ["1y", "5y"])).toBe("1y");
  });
});

describe("effectiveChart", () => {
  // Merges an override on top of base chart data. Chart-edit (composer
  // edits to charts already in the library) ships overrides through
  // this, so regressions here silently re-mute curator edits.

  it("returns the base data verbatim when no override is provided", () => {
    const base = { title: "CPI", render: "line", blurb: "x" } as
      unknown as CollectionEntry<"charts">["data"];
    const resolved = { chart: { data: base } } as unknown as ResolvedChart;
    expect(effectiveChart(resolved)).toEqual(base);
  });

  it("returns the base when override is undefined or an empty object", () => {
    const base = { title: "CPI", render: "line" } as
      unknown as CollectionEntry<"charts">["data"];
    const resolved = { chart: { data: base } } as unknown as ResolvedChart;
    expect(effectiveChart(resolved, undefined)).toEqual(base);
    expect(effectiveChart(resolved, {})).toEqual(base);
  });

  it("override fields take precedence over base", () => {
    const base = {
      title: "Original",
      blurb: "old blurb",
      render: "line",
    } as unknown as CollectionEntry<"charts">["data"];
    const resolved = { chart: { data: base } } as unknown as ResolvedChart;
    const out = effectiveChart(resolved, {
      title: "Custom",
      blurb: "new blurb",
    });
    expect(out.title).toBe("Custom");
    expect(out.blurb).toBe("new blurb");
    expect(out.render).toBe("line"); // untouched field passes through
  });

  it("does NOT mutate the input resolved.chart.data", () => {
    // Composer is allowed to render the same chart multiple times with
    // different overrides; mutating base would cross-contaminate.
    const base = { title: "Base" } as
      unknown as CollectionEntry<"charts">["data"];
    const resolved = { chart: { data: base } } as unknown as ResolvedChart;
    effectiveChart(resolved, { title: "Overridden" });
    expect(base.title).toBe("Base");
  });

  it("override can set fields the base doesn't have", () => {
    const base = { title: "x", render: "line" } as
      unknown as CollectionEntry<"charts">["data"];
    const resolved = { chart: { data: base } } as unknown as ResolvedChart;
    const out = effectiveChart(resolved, {
      blurb: "new blurb",
      // tags is also valid per the schema
      tags: ["a", "b"],
    });
    expect(out.blurb).toBe("new blurb");
    expect(out.tags).toEqual(["a", "b"]);
  });
});

describe("isVisibleChart", () => {
  // Three call sites depend on the contract: chart/[...id], source/
  // [...id], library.json.ts. The rules:
  //   - non-deprecated → visible
  //   - deprecated + no aliasOf → hidden
  //   - deprecated + aliasOf → visible (slug stays alive, points at
  //     the successor)

  function makeChart(
    data: Record<string, unknown>,
  ): CollectionEntry<"charts"> {
    return { data } as unknown as CollectionEntry<"charts">;
  }

  it("returns true for a non-deprecated chart", () => {
    expect(isVisibleChart(makeChart({ render: "line" }))).toBe(true);
  });

  it("returns false for a deprecated chart with no aliasOf", () => {
    // Slug is reserved (nothing else can claim it) but the chart
    // doesn't appear in catalogs.
    expect(
      isVisibleChart(makeChart({ render: "line", deprecated: true })),
    ).toBe(false);
  });

  it("returns true for a deprecated chart that has an aliasOf successor", () => {
    // Old saved-dashboard URLs keep working — the slug resolves to its
    // successor chart, and the alias entry stays in catalogs.
    expect(
      isVisibleChart(
        makeChart({ render: "line", deprecated: true, aliasOf: "new-chart" }),
      ),
    ).toBe(true);
  });

  it("treats deprecated: false as visible (explicit non-deprecation)", () => {
    expect(
      isVisibleChart(makeChart({ render: "line", deprecated: false })),
    ).toBe(true);
  });

  it("treats deprecated: undefined as visible (the typical case)", () => {
    expect(isVisibleChart(makeChart({ render: "line" }))).toBe(true);
  });

  it("ignores aliasOf when deprecated isn't true (no early-return on aliasOf alone)", () => {
    // aliasOf alone, without deprecated:true, isn't a real scenario in
    // production — but the predicate shouldn't misfire on it.
    expect(
      isVisibleChart(makeChart({ render: "line", aliasOf: "x" })),
    ).toBe(true);
  });
});

describe("resolveChart — exact-rebuild substitution", () => {
  // rate × its-own-denominator should resolve to the exact numerator
  // count source, not the rounding-drifted product. VA-08 figures: the
  // share is stored at 1 dp (31.0%), so 0.310 × 566,046 = 175,474 — but
  // the true count is 175,568. Substitution must show 175,568.
  const RATE = "acs_cd/pct_bachelors_va_08";
  const DENOM = "acs_cd/adults_25plus_va_08";
  const NUM = "acs_cd/bachelors_plus_va_08";
  const entries: Record<string, { id: string; data: Record<string, unknown> }> = {
    [RATE]: {
      id: RATE,
      data: {
        kind: "timeseries",
        dataFile: `data/${RATE}.json`,
        supportedDeltas: ["5y", "10y"],
        formatting: { style: "percent", decimals: 1 },
        unitClass: "rate",
        derivedFrom: { numerator: NUM, denominator: DENOM, scale: 100 },
      },
    },
    [DENOM]: {
      id: DENOM,
      data: {
        kind: "timeseries",
        dataFile: `data/${DENOM}.json`,
        supportedDeltas: ["5y", "10y"],
        formatting: { style: "number", decimals: 0 },
        unitClass: "count",
      },
    },
    [NUM]: {
      id: NUM,
      data: {
        kind: "timeseries",
        dataFile: `data/${NUM}.json`,
        supportedDeltas: ["5y", "10y"],
        formatting: { style: "number", decimals: 0 },
        unitClass: "count",
      },
    },
  };
  const pointsByFile: Record<string, number> = {
    [`data/${RATE}.json`]: 31.0,
    [`data/${DENOM}.json`]: 566046,
    [`data/${NUM}.json`]: 175568,
  };

  async function wireMocks() {
    const { getEntry } = await import("astro:content");
    (getEntry as unknown as ReturnType<typeof vi.fn>).mockImplementation(
      (_collection: string, id: string) =>
        Promise.resolve(entries[id] ?? undefined),
    );
    const { loadSourceData } = await import("./load-data");
    (loadSourceData as unknown as ReturnType<typeof vi.fn>).mockImplementation(
      (dataFile: string) =>
        Promise.resolve({
          kind: "timeseries",
          points: [{ t: "2022-12-31", v: pointsByFile[dataFile] ?? 0 }],
        }),
    );
  }

  it("collapses rate × its-own-denominator to the exact numerator source", async () => {
    await wireMocks();
    const inlineCharts: Record<string, InlineChart> = {
      "inline:reb00001": {
        title: "VA-08 adults 25+ with a bachelor's",
        sources: [RATE, DENOM],
        op: "multiply",
        normalize: "raw",
        render: "line",
      },
    };
    const resolved = await resolveChart(
      "inline:reb00001",
      inlineCharts,
      undefined,
      undefined,
    );
    expect(resolved).not.toBeNull();
    const data = resolved!.chart.data as unknown as {
      sources: string[];
      op?: string;
    };
    // Collapsed to the single exact source, op dropped.
    expect(data.sources).toEqual([NUM]);
    expect(data.op).toBeUndefined();
    // The preloaded series is the exact count (175,568), NOT the product
    // 175,474 the multiply engine would have computed from the rounded rate.
    const preloaded = (resolved as unknown as {
      preloaded?: Record<string, { points: { v: number }[] }>;
    }).preloaded;
    expect(preloaded?.[NUM]?.points[0].v).toBe(175568);
  });

  it("does NOT substitute when the multiply uses an unrelated denominator", async () => {
    await wireMocks();
    const OTHER = "fred/us_population";
    entries[OTHER] = {
      id: OTHER,
      data: {
        kind: "timeseries",
        dataFile: `data/${OTHER}.json`,
        supportedDeltas: ["5y", "10y"],
        formatting: { style: "number", decimals: 0 },
        unitClass: "count",
      },
    };
    pointsByFile[`data/${OTHER}.json`] = 333000000;
    const inlineCharts: Record<string, InlineChart> = {
      "inline:reb00002": {
        title: "rate × unrelated",
        sources: [RATE, OTHER],
        op: "multiply",
        normalize: "raw",
        render: "line",
      },
    };
    const resolved = await resolveChart(
      "inline:reb00002",
      inlineCharts,
      undefined,
      undefined,
    );
    expect(resolved).not.toBeNull();
    const data = resolved!.chart.data as unknown as {
      sources: string[];
      op?: string;
    };
    // Genuine product — both operands kept, op preserved.
    expect(data.sources).toEqual([RATE, OTHER]);
    expect(data.op).toBe("multiply");
  });

  it("does NOT preload full points for a simple multi-source chart", async () => {
    await wireMocks();
    // Two real sources, no op, no fixed range: the lean path. Chart.astro
    // loads each source's .summary.json rather than inlining the full series,
    // so saved/composed dashboards stop shipping the entire daily history.
    const inlineCharts: Record<string, InlineChart> = {
      "inline:lean0001": {
        title: "two counts",
        sources: [NUM, DENOM],
        normalize: "raw",
        render: "line",
      },
    };
    const resolved = await resolveChart(
      "inline:lean0001",
      inlineCharts,
      undefined,
      undefined,
    );
    expect(resolved).not.toBeNull();
    const preloaded = (resolved as unknown as {
      preloaded?: Record<string, unknown>;
    }).preloaded;
    expect(preloaded ?? {}).toEqual({});
    // Sources still resolve so Chart.astro can summary-load them.
    const data = resolved!.chart.data as unknown as { sources: string[] };
    expect(data.sources).toEqual([NUM, DENOM]);
  });
});
