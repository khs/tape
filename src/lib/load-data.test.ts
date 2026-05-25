import { describe, it, expect } from "vitest";
import {
  isServerlessRuntime,
  resolveServerlessOrigin,
  snapshotAt,
  currentPoint,
  findPriorPoint,
  computeSummaryFromPoints,
} from "./load-data";
import type { TimeSeriesData, TimeSeriesPoint } from "./data-types";

/** Build a minimal TimeSeriesData around a points list, for the
 *  helper tests below. The non-points fields are placeholders — none of
 *  the functions under test look at them. */
function tsd(points: TimeSeriesPoint[]): TimeSeriesData {
  return {
    id: "test/series",
    name: "Test series",
    kind: "timeseries",
    lastUpdated: "2025-01-01",
    points,
  };
}

// These tests lock down the env-detection logic in load-data.ts. Two
// production outages came out of getting this wrong:
//
//   1. (cdf057db) Gated serverless-mode on process.env.VERCEL, which is
//      set at BOTH build and runtime. That made prerendered routes try
//      to fetch from a not-yet-live URL during astro build.
//   2. (cdf057db, lingering) Preferred VERCEL_URL (per-deploy hash
//      hostname) as the fetch origin. On team accounts those hostnames
//      are gated behind Vercel deployment-protection → HTTP 401 on
//      cross-Function fetches from the same deployment. Production
//      page rendered "Data unavailable" on every chart until 157e9fb3.
//
// The asserts below would have caught both bugs before they shipped.

describe("isServerlessRuntime", () => {
  it("is false when no Vercel env vars are set (local dev / non-Vercel CI)", () => {
    expect(isServerlessRuntime({})).toBe(false);
  });

  it("is false when VERCEL=1 alone is set (build time, not function runtime)", () => {
    // Regression test for cdf057db. VERCEL=1 is set at BOTH build and
    // runtime; if we treat it as a serverless signal, prerender breaks.
    expect(isServerlessRuntime({ VERCEL: "1" })).toBe(false);
  });

  it("is false at build time on Vercel CI (VERCEL=1 + VERCEL_URL set, no VERCEL_REGION)", () => {
    // Vercel sets VERCEL_URL during build too — only VERCEL_REGION is
    // unique to running Functions.
    expect(
      isServerlessRuntime({
        VERCEL: "1",
        VERCEL_URL: "tape-abc.vercel.app",
        VERCEL_ENV: "production",
      }),
    ).toBe(false);
  });

  it("is true when VERCEL_REGION is set (running inside a deployed Function)", () => {
    expect(isServerlessRuntime({ VERCEL_REGION: "iad1" })).toBe(true);
  });

  it("treats any non-empty VERCEL_REGION as serverless (not just specific regions)", () => {
    expect(isServerlessRuntime({ VERCEL_REGION: "fra1" })).toBe(true);
    expect(isServerlessRuntime({ VERCEL_REGION: "dev1" })).toBe(true);
  });
});

describe("resolveServerlessOrigin", () => {
  it("returns null when nothing is set", () => {
    expect(resolveServerlessOrigin({})).toBe(null);
  });

  it("prefers SITE_URL (verbatim, including scheme) over all Vercel vars", () => {
    expect(
      resolveServerlessOrigin({
        SITE_URL: "https://tape.com",
        VERCEL_PROJECT_PRODUCTION_URL: "tape.vercel.app",
        VERCEL_URL: "tape-abc.vercel.app",
      }),
    ).toBe("https://tape.com");
  });

  it("prefers VERCEL_PROJECT_PRODUCTION_URL over VERCEL_URL (regression: 157e9fb3)", () => {
    // The per-deploy VERCEL_URL on team accounts is gated by Vercel
    // SSO auth → 401 on cross-Function fetches. The stable production
    // URL is what we actually want to hit, so preference order
    // matters.
    expect(
      resolveServerlessOrigin({
        VERCEL_PROJECT_PRODUCTION_URL: "tape.vercel.app",
        VERCEL_URL: "tape-1i2umj3hh-team-projects.vercel.app",
      }),
    ).toBe("https://tape.vercel.app");
  });

  it("falls back to VERCEL_URL as a last resort (preview deploys etc.)", () => {
    expect(
      resolveServerlessOrigin({
        VERCEL_URL: "tape-pr-42-team.vercel.app",
      }),
    ).toBe("https://tape-pr-42-team.vercel.app");
  });

  it("prepends https:// to bare hostnames from VERCEL_* vars", () => {
    expect(
      resolveServerlessOrigin({
        VERCEL_PROJECT_PRODUCTION_URL: "host.example.com",
      }),
    ).toBe("https://host.example.com");
  });

  it("uses SITE_URL as-is without scheme massaging (caller's responsibility)", () => {
    // Trusted explicit override; we don't try to be clever about it.
    expect(
      resolveServerlessOrigin({ SITE_URL: "https://x.com/sub-path" }),
    ).toBe("https://x.com/sub-path");
  });
});

// ---------- Pure data-helper tests ----------
//
// snapshotAt / currentPoint / findPriorPoint / computeSummaryFromPoints
// are pure functions over TimeSeriesData — no filesystem or fetch. They
// sit on the hot path of bar-chart rendering, the tile summary
// derivation for derived charts, and the prior-point arrow on every
// tile. A regression in any of them silently corrupts every chart that
// renders without crashing.

describe("snapshotAt", () => {
  const POINTS: TimeSeriesPoint[] = [
    { t: "2020-01-01", v: 1 },
    { t: "2020-06-01", v: 2 },
    { t: "2021-01-01", v: 3 },
    { t: "2022-01-01", v: 4 },
    { t: "2023-06-15", v: 5 },
  ];

  it("returns null when the series has no points", () => {
    expect(snapshotAt(tsd([]), "2020-01-01")).toBeNull();
    expect(snapshotAt(tsd([]))).toBeNull();
  });

  it("returns the latest point when asOf is undefined", () => {
    // Same shape as the source's summary `latest` field, just computed
    // from the full points array.
    expect(snapshotAt(tsd(POINTS))).toEqual({ t: "2023-06-15", v: 5 });
  });

  it("returns the exact point when asOf matches a date in the series", () => {
    expect(snapshotAt(tsd(POINTS), "2021-01-01")).toEqual({
      t: "2021-01-01",
      v: 3,
    });
  });

  it("returns the latest at-or-before point when asOf falls between dates", () => {
    // 2020-12-31 sits between 2020-06-01 (v=2) and 2021-01-01 (v=3).
    // The walk-from-back contract says: return the latest point whose
    // date is ≤ asOf, so v=2.
    expect(snapshotAt(tsd(POINTS), "2020-12-31")).toEqual({
      t: "2020-06-01",
      v: 2,
    });
  });

  it("returns the latest point when asOf is after the entire series", () => {
    expect(snapshotAt(tsd(POINTS), "2099-01-01")).toEqual({
      t: "2023-06-15",
      v: 5,
    });
  });

  it("returns null when asOf is before the series starts", () => {
    // The source isn't yet defined at the requested anchor — bar
    // renderer drops it from the chart.
    expect(snapshotAt(tsd(POINTS), "2019-01-01")).toBeNull();
  });
});

describe("currentPoint", () => {
  it("returns null for empty points", () => {
    expect(currentPoint(tsd([]))).toBeNull();
  });

  it("returns the last point regardless of values", () => {
    // Lexical string compare on ISO dates works for monotonic series;
    // currentPoint trusts the points to be in chronological order
    // (which the pipeline guarantees on ingest).
    const result = currentPoint(
      tsd([
        { t: "2020-01-01", v: 100 },
        { t: "2021-01-01", v: -5 },
        { t: "2022-01-01", v: 42 },
      ]),
    );
    expect(result).toEqual({ t: "2022-01-01", v: 42 });
  });
});

describe("findPriorPoint", () => {
  const POINTS: TimeSeriesPoint[] = [
    { t: "2018-01-01", v: 10 },
    { t: "2019-01-01", v: 20 },
    { t: "2020-01-01", v: 30 },
    { t: "2021-01-01", v: 40 },
    { t: "2022-01-01", v: 50 },
    { t: "2023-01-01", v: 60 },
    { t: "2024-01-01", v: 70 },
  ];

  it("returns null for empty points", () => {
    expect(findPriorPoint(tsd([]), "1y")).toBeNull();
  });

  it("returns the point ~1 year before the latest for a 1y window", () => {
    // Latest = 2024-01-01. 1y = 365 days before = 2023-01-02; the
    // at-or-before point is 2023-01-01.
    expect(findPriorPoint(tsd(POINTS), "1y")).toEqual({
      t: "2023-01-01",
      v: 60,
    });
  });

  it("returns the point ~5 years before the latest for a 5y window", () => {
    // Latest = 2024-01-01. 5y = 1825 days before ≈ 2019-01-02; the
    // at-or-before point is 2019-01-01.
    expect(findPriorPoint(tsd(POINTS), "5y")).toEqual({
      t: "2019-01-01",
      v: 20,
    });
  });

  it("returns null when the series doesn't go back far enough", () => {
    // 10y window from 2024 wants 2014, but series starts 2018.
    expect(findPriorPoint(tsd(POINTS), "10y")).toBeNull();
  });

  it("anchors YTD to Jan 1 of the latest point's year", () => {
    const ytdPoints: TimeSeriesPoint[] = [
      { t: "2023-12-15", v: 100 },
      { t: "2024-01-01", v: 110 },
      { t: "2024-03-15", v: 115 },
      { t: "2024-06-01", v: 120 },
    ];
    // Latest = 2024-06-01. YTD start = 2024-01-01. At-or-before that
    // is 2024-01-01 itself.
    expect(findPriorPoint(tsd(ytdPoints), "ytd")).toEqual({
      t: "2024-01-01",
      v: 110,
    });
  });
});

describe("computeSummaryFromPoints", () => {
  it("returns null when the points list is empty", () => {
    expect(computeSummaryFromPoints([], ["1w", "1y"])).toBeNull();
  });

  it("emits latest + priors keyed by the requested windows", () => {
    // Daily-ish points spanning ~2 years. The 1y prior should land
    // ~365 days before the latest; the 1m prior ~30 days before.
    const points: TimeSeriesPoint[] = [];
    const start = new Date("2022-01-01").getTime();
    for (let i = 0; i < 800; i++) {
      const d = new Date(start + i * 86400000).toISOString().slice(0, 10);
      points.push({ t: d, v: i });
    }
    const result = computeSummaryFromPoints(points, ["1m", "1y"]);
    expect(result).not.toBeNull();
    if (!result) return;
    expect(result.latest).toBe(points[points.length - 1]);
    // 1y prior: index 799-365 = 434, value 434.
    expect(result.priors["1y"]?.v).toBe(434);
    // 1m prior: index 799-30 = 769, value 769.
    expect(result.priors["1m"]?.v).toBe(769);
  });

  it("omits the prior when it would equal the latest (very short series)", () => {
    // Two points within 1 week. The 1y prior would equal latest →
    // dropped, because the descriptor "no change since last year" is
    // misleading when "last year" is the same datapoint.
    const points: TimeSeriesPoint[] = [
      { t: "2024-01-01", v: 100 },
      { t: "2024-01-05", v: 105 },
    ];
    const result = computeSummaryFromPoints(points, ["1y"]);
    expect(result).not.toBeNull();
    expect(result?.priors["1y"]).toBeUndefined();
  });

  it("ships the full slice as the spark when it's already short", () => {
    // Series shorter than SUMMARY_SPARK_POINTS (30) — no downsample;
    // every point makes it into the spark.
    const points: TimeSeriesPoint[] = Array.from({ length: 10 }, (_, i) => ({
      t: new Date(Date.UTC(2024, 0, i + 1)).toISOString().slice(0, 10),
      v: i,
    }));
    const result = computeSummaryFromPoints(points, ["1m"]);
    expect(result?.sparks["1m"]?.length).toBeGreaterThan(0);
    expect(result?.sparks["1m"]?.length).toBeLessThanOrEqual(10);
  });

  it("downsamples to exactly 30 points when the slice is longer", () => {
    // 365 daily points + a 1y window → spark is uniformly sampled
    // down to SUMMARY_SPARK_POINTS = 30 entries. The contract is:
    // first and last sampled are first and last of the slice.
    const points: TimeSeriesPoint[] = [];
    const start = new Date("2023-01-01").getTime();
    for (let i = 0; i < 365; i++) {
      const d = new Date(start + i * 86400000).toISOString().slice(0, 10);
      points.push({ t: d, v: i });
    }
    const result = computeSummaryFromPoints(points, ["1y"]);
    const spark = result?.sparks["1y"];
    expect(spark?.length).toBe(30);
    // First sampled point ≥ window start (latest - 365 days); last
    // sampled point is the latest.
    expect(spark?.[spark.length - 1]).toBe(points[points.length - 1]);
  });

  it("skips windows that aren't in the SUMMARY_WINDOWS_DAYS table", () => {
    // "3w" isn't in SUMMARY_WINDOWS_DAYS. The function should silently
    // omit it from priors + sparks rather than throw or emit garbage.
    const points: TimeSeriesPoint[] = [
      { t: "2023-01-01", v: 1 },
      { t: "2024-01-01", v: 2 },
    ];
    const result = computeSummaryFromPoints(points, ["3w", "1y"]);
    expect(result?.priors["3w"]).toBeUndefined();
    expect(result?.sparks["3w"]).toBeUndefined();
    // 1y prior still gets computed.
    expect(result?.priors["1y"]).toBeDefined();
  });

  it("anchors ytd window to Jan 1 of the latest's year, not 183 days back", () => {
    // YTD's special-case branch — without it the spark would slip
    // half a year off in mid-summer (DELTA_DAYS["ytd"] = 183, the
    // nominal value).
    const points: TimeSeriesPoint[] = [
      { t: "2023-06-01", v: 0 },
      { t: "2023-12-31", v: 10 },
      { t: "2024-01-01", v: 20 },
      { t: "2024-04-01", v: 30 },
      { t: "2024-07-01", v: 40 },
    ];
    const result = computeSummaryFromPoints(points, ["ytd"]);
    // Prior = last point at-or-before 2024-01-01 = 2024-01-01 itself.
    // 2024-01-01 != latest (2024-07-01) so it's emitted.
    expect(result?.priors["ytd"]).toEqual({ t: "2024-01-01", v: 20 });
    // Spark starts at the YTD boundary (Jan 1), not at midsummer.
    expect(result?.sparks["ytd"]?.[0]?.t).toBe("2024-01-01");
  });
});
