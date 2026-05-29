/**
 * Tests for the chart pill-row thinning rules.
 *
 * These functions live on the hot path of every chart render. The
 * "1M pill on monthly CPI" regression motivated the rules — a regression
 * test of the rule means the next renderer rewrite can't accidentally
 * re-surface single-dot windows.
 */
import { describe, it, expect } from "vitest";
import type { DeltaWindow } from "./deltas";
import {
  MIN_POINTS_FOR_WINDOW,
  pointsInDeltaWindow,
  filterSupportedDeltas,
  type SourceForWindowCount,
} from "./delta-window-points";

/** Build a SourceForWindowCount with a fake summary spark of `n`
 *  points for the named window. The actual entries don't matter — the
 *  function only reads `.length`. */
function withSpark(win: string, n: number): SourceForWindowCount {
  return { summary: { sparks: { [win]: new Array(n).fill(null) } } };
}

/** Build a SourceForWindowCount with daily points spanning `days` days
 *  ending at `endDate`. Useful for exercising the data.points fallback
 *  when no summary spark is available. */
function withDailyPoints(
  endDate: string,
  days: number,
): SourceForWindowCount {
  const end = new Date(endDate).getTime();
  const pts: Array<{ t: string }> = [];
  for (let i = days - 1; i >= 0; i--) {
    pts.push({
      t: new Date(end - i * 86_400_000).toISOString().slice(0, 10),
    });
  }
  return { data: { points: pts } };
}

describe("pointsInDeltaWindow", () => {
  it("returns Infinity for ytd (calendar window, opt-out of filtering)", () => {
    // The pill row keeps ytd visible even in January when it has 1-2
    // points; readers parse "YTD on Jan 5th" naturally.
    expect(pointsInDeltaWindow(withSpark("ytd", 1), "ytd")).toBe(Infinity);
    expect(pointsInDeltaWindow({}, "ytd")).toBe(Infinity);
  });

  it("returns Infinity when neither summary spark nor data points are loaded", () => {
    // Be permissive — let the renderer fall back. Without this guard
    // every pill would get filtered out on first paint when the data
    // hasn't fetched yet.
    expect(pointsInDeltaWindow({}, "1m")).toBe(Infinity);
    expect(pointsInDeltaWindow({ summary: {} }, "1m")).toBe(Infinity);
    expect(pointsInDeltaWindow({ data: { points: [] } }, "1m")).toBe(
      Infinity,
    );
  });

  it("uses summary spark length when available (preferred path)", () => {
    expect(pointsInDeltaWindow(withSpark("1m", 5), "1m")).toBe(5);
    expect(pointsInDeltaWindow(withSpark("1y", 30), "1y")).toBe(30);
    expect(pointsInDeltaWindow(withSpark("5y", 30), "5y")).toBe(30);
  });

  it("counts points in the data.points fallback window when no spark exists", () => {
    // 60 daily points ending 2024-06-30. 30-day window from latest
    // (= 2024-06-30) starts at 2024-05-31 → 30 points qualify
    // (May 31 + Jun 1-29 + Jun 30).
    const source = withDailyPoints("2024-06-30", 60);
    expect(pointsInDeltaWindow(source, "1m")).toBe(31);
  });

  it("data.points window respects DELTA_DAYS — 1y = 365 days", () => {
    // Series of 200 daily points — fewer than 365, so all qualify
    // for 1y.
    const source = withDailyPoints("2024-06-30", 200);
    expect(pointsInDeltaWindow(source, "1y")).toBe(200);
  });

  it("data.points window can return 1 or 2 (the regression-trigger case)", () => {
    // Monthly cadence: 13 points spaced ~30 days apart ending today.
    // 1M window catches only the latest 1-2 points — the bug that
    // motivated the filter.
    const pts: Array<{ t: string }> = [];
    const end = new Date("2024-06-30").getTime();
    for (let i = 12; i >= 0; i--) {
      pts.push({
        t: new Date(end - i * 30 * 86_400_000).toISOString().slice(0, 10),
      });
    }
    const source: SourceForWindowCount = { data: { points: pts } };
    expect(pointsInDeltaWindow(source, "1m")).toBeLessThanOrEqual(2);
  });

  it("prefers the summary spark over data.points when both are present", () => {
    // Reality: when ingestion ships both, the spark is authoritative
    // for the count because it's what the tile actually renders.
    const source: SourceForWindowCount = {
      summary: { sparks: { "1m": [null, null, null] } },
      data: { points: withDailyPoints("2024-06-30", 60).data!.points },
    };
    // Spark length wins → 3, not 31.
    expect(pointsInDeltaWindow(source, "1m")).toBe(3);
  });
});

describe("filterSupportedDeltas", () => {
  const ALL_WINDOWS: readonly DeltaWindow[] = [
    "1w",
    "1m",
    "ytd",
    "1y",
    "5y",
    "10y",
    "30y",
    "50y",
  ];

  it("returns the input unchanged when every source has plenty of points", () => {
    // All sources have 30+ points for every window — nothing thins.
    const richSource: SourceForWindowCount = {
      summary: {
        sparks: Object.fromEntries(
          ALL_WINDOWS.filter((w) => w !== "ytd").map((w) => [
            w,
            new Array(30).fill(null),
          ]),
        ),
      },
    };
    expect(filterSupportedDeltas(ALL_WINDOWS, [richSource])).toEqual(
      ALL_WINDOWS,
    );
  });

  it("drops a short window when any source has <3 points", () => {
    // A "1m" pill with 2 points on one source — the regression case.
    // The pill should drop because a longer window (1y, 5y, …) exists.
    const monthlySource: SourceForWindowCount = {
      summary: {
        sparks: {
          "1m": [null, null], // 2 points — fails the >=3 rule
          "1y": new Array(12).fill(null),
          "5y": new Array(60).fill(null),
        },
      },
    };
    const result = filterSupportedDeltas(
      ["1m", "1y", "5y"],
      [monthlySource],
    );
    expect(result).toEqual(["1y", "5y"]);
  });

  it("always keeps the longest window even when it has <3 points", () => {
    // A series that's brand-new — even its longest available window
    // has only 2 points. The pill row would otherwise be empty.
    const newSource: SourceForWindowCount = {
      summary: {
        sparks: {
          "1m": [null],
          "1y": [null, null],
        },
      },
    };
    const result = filterSupportedDeltas(["1m", "1y"], [newSource]);
    // Longest (1y) is preserved even though it's < 3 points.
    expect(result).toContain("1y");
    expect(result.length).toBeGreaterThan(0);
  });

  it("keeps ytd when its emptiness can't be measured (no latest date → permissive)", () => {
    // YTD is a calendar window we don't point-count. With no `latest`
    // on the summary (and no full points), we can't tell whether the
    // current year has data, so we stay permissive and keep the pill.
    const unknownLatest: SourceForWindowCount = {
      summary: {
        sparks: {
          "1m": new Array(30).fill(null),
          "1y": new Array(250).fill(null),
        },
      },
    };
    const result = filterSupportedDeltas(
      ["1m", "ytd", "1y"],
      [unknownLatest],
    );
    expect(result).toContain("ytd");
  });

  it("keeps a sparse ytd when the latest observation is in the current year", () => {
    // A current series whose latest point is March of this year: ytd is
    // sparse but non-empty, so it reads naturally and stays.
    const now = new Date("2026-05-29T00:00:00Z");
    const current: SourceForWindowCount = {
      summary: {
        latest: { t: "2026-03-01" },
        sparks: { "1m": new Array(30).fill(null) },
      },
    };
    const result = filterSupportedDeltas(
      ["ytd", "5y"],
      [current],
      MIN_POINTS_FOR_WINDOW,
      now,
    );
    expect(result).toContain("ytd");
  });

  it("drops a zero-point ytd when the latest observation predates the current year", () => {
    // Stale/annual series: latest point is 2021, today is 2026, so the
    // ytd window has no data. It should drop so the default escalates to
    // the next-larger window that does. The other windows here are
    // unmeasurable (no sparks/points), so they stay — ytd is the lone drop.
    const now = new Date("2026-05-29T00:00:00Z");
    const staleAnnual: SourceForWindowCount = {
      summary: { latest: { t: "2021-01-01" } },
    };
    const result = filterSupportedDeltas(
      ["1m", "ytd", "5y"],
      [staleAnnual],
      MIN_POINTS_FOR_WINDOW,
      now,
    );
    expect(result).not.toContain("ytd");
    expect(result).toEqual(["1m", "5y"]);
  });

  it("drops ytd if ANY source lacks current-year data (shared pill row)", () => {
    const now = new Date("2026-05-29T00:00:00Z");
    const current: SourceForWindowCount = {
      summary: { latest: { t: "2026-04-01" } },
    };
    const staleAnnual: SourceForWindowCount = {
      summary: { latest: { t: "2021-01-01" } },
    };
    const result = filterSupportedDeltas(
      ["ytd", "5y"],
      [current, staleAnnual],
      MIN_POINTS_FOR_WINDOW,
      now,
    );
    expect(result).not.toContain("ytd");
  });

  it("detects an empty ytd from full points when no summary is present", () => {
    // Full-data renders (no tile summary) must still detect an empty ytd
    // via the last point's date.
    const now = new Date("2026-05-29T00:00:00Z");
    const fullStale: SourceForWindowCount = {
      data: {
        points: [{ t: "2019-01-01" }, { t: "2020-01-01" }, { t: "2021-01-01" }],
      },
    };
    const result = filterSupportedDeltas(
      ["ytd", "5y"],
      [fullStale],
      MIN_POINTS_FOR_WINDOW,
      now,
    );
    expect(result).not.toContain("ytd");
  });

  it("drops a window only if EVERY source agrees it has data — multi-source rule", () => {
    // Source A has plenty of 1m data, source B has 1 point. The
    // shared pill row would render a window that's blank for B, so
    // 1m should drop.
    const rich: SourceForWindowCount = {
      summary: { sparks: { "1m": new Array(30).fill(null), "1y": new Array(365).fill(null) } },
    };
    const sparse: SourceForWindowCount = {
      summary: { sparks: { "1m": [null], "1y": new Array(365).fill(null) } },
    };
    const result = filterSupportedDeltas(["1m", "1y"], [rich, sparse]);
    expect(result).toEqual(["1y"]);
  });

  it("respects a custom minPoints threshold", () => {
    // For a chart that demands ≥10 points per window:
    const source: SourceForWindowCount = {
      summary: {
        sparks: {
          "1m": new Array(8).fill(null), // < 10
          "1y": new Array(50).fill(null),
        },
      },
    };
    const result = filterSupportedDeltas(["1m", "1y"], [source], 10);
    expect(result).toEqual(["1y"]);
  });

  it("uses the documented default minPoints constant (3)", () => {
    // Sanity: the exported constant matches the filter's default.
    expect(MIN_POINTS_FOR_WINDOW).toBe(3);
  });

  it("empty perSource list keeps all windows (no sources to filter against)", () => {
    expect(filterSupportedDeltas(["1m", "1y"], [])).toEqual(["1m", "1y"]);
  });

  it("single-element supported list survives the filter (longest = only)", () => {
    const source: SourceForWindowCount = {
      summary: { sparks: { "1y": [null] } },
    };
    expect(filterSupportedDeltas(["1y"], [source])).toEqual(["1y"]);
  });
});
