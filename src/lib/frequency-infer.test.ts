/**
 * Lockdown tests for the frequency inferer that powers the
 * "Absolute change >" hint on /alerts/. The bucket boundaries
 * directly inform the copy a user sees when picking that
 * condition — a regression here ships wrong cadence info to
 * everyone.
 */
import { describe, test, expect } from "vitest";
import {
  frequencyBucket,
  selectFrequencySpark,
  medianSpacingDays,
  inferFrequency,
  type SparkPoint,
} from "./frequency-infer";

/** Build n points spaced `stepDays` apart, starting at 2020-01-01. */
function series(n: number, stepDays: number): SparkPoint[] {
  const out: SparkPoint[] = [];
  const start = new Date("2020-01-01T00:00:00Z").getTime();
  const dayMs = 24 * 60 * 60 * 1000;
  for (let i = 0; i < n; i++) {
    const d = new Date(start + i * stepDays * dayMs);
    out.push({ t: d.toISOString().slice(0, 10), v: i });
  }
  return out;
}

describe("frequencyBucket", () => {
  test.each<[number, string]>([
    [1, "daily"],
    [2, "daily"],
    [3, "weekly"],
    [7, "weekly"],
    [9, "weekly"],
    [10, "monthly"],
    [30, "monthly"],
    [80, "monthly"],
    [81, "quarterly"],
    [180, "quarterly"],
    [181, "annual"],
    [365, "annual"],
    [400, "annual"],
    [401, "multi-year"],
    [1000, "multi-year"],
  ])("%d days → '%s'", (days, expected) => {
    expect(frequencyBucket(days)).toBe(expected);
  });
  test("non-positive / non-finite returns 'unknown'", () => {
    expect(frequencyBucket(0)).toBe("unknown");
    expect(frequencyBucket(-1)).toBe("unknown");
    expect(frequencyBucket(NaN)).toBe("unknown");
    expect(frequencyBucket(Infinity)).toBe("unknown");
  });
});

describe("medianSpacingDays", () => {
  test("returns the median for evenly spaced points", () => {
    expect(medianSpacingDays(series(10, 7))).toBe(7);
  });
  test("ignores zero-gap (duplicate-date) points", () => {
    const points: SparkPoint[] = [
      { t: "2020-01-01", v: 1 },
      { t: "2020-01-01", v: 2 }, // duplicate — ignored
      { t: "2020-01-08", v: 3 },
      { t: "2020-01-15", v: 4 },
    ];
    expect(medianSpacingDays(points)).toBe(7);
  });
  test("outlier gap doesn't move the median", () => {
    // 4 gaps of 7 days + 1 huge holiday gap of 90. Median stays 7.
    const points: SparkPoint[] = [
      { t: "2020-01-01", v: 1 },
      { t: "2020-01-08", v: 2 },
      { t: "2020-01-15", v: 3 },
      { t: "2020-04-15", v: 4 }, // 90-day gap
      { t: "2020-04-22", v: 5 },
      { t: "2020-04-29", v: 6 },
    ];
    expect(medianSpacingDays(points)).toBe(7);
  });
  test("returns null for empty / single-point input", () => {
    expect(medianSpacingDays([])).toBeNull();
    expect(medianSpacingDays([{ t: "2020-01-01", v: 1 }])).toBeNull();
  });
});

describe("selectFrequencySpark", () => {
  test("prefers the largest window with raw resolution", () => {
    // 1y is the largest non-downsampled window — should win over
    // shorter raw windows and over 5y (which is at the cap).
    const sparks: Record<string, SparkPoint[]> = {
      "1m": series(4, 7),
      "1y": series(12, 30),
      "5y": series(30, 60), // 30 points = downsample cap, skip
      "10y": series(30, 120), // also at cap
    };
    expect(selectFrequencySpark(sparks)).toBe(sparks["1y"]);
  });
  test("falls through to shorter windows when long ones are all downsampled", () => {
    const sparks: Record<string, SparkPoint[]> = {
      "1m": series(22, 1.5), // 22 daily-ish points
      "ytd": series(100, 2), // already at downsample cap (>= 30)
      "1y": series(30, 12), // also at cap
    };
    expect(selectFrequencySpark(sparks)).toBe(sparks["1m"]);
  });
  test("returns null when no window has enough points", () => {
    const sparks: Record<string, SparkPoint[]> = {
      "1w": [],
      "1m": [{ t: "2020-01-01", v: 1 }],
      "1y": [
        { t: "2020-01-01", v: 1 },
        { t: "2020-04-01", v: 2 },
      ],
    };
    expect(selectFrequencySpark(sparks)).toBeNull();
  });
  test("returns null when sparks is undefined", () => {
    expect(selectFrequencySpark(undefined)).toBeNull();
  });
});

describe("inferFrequency (end-to-end)", () => {
  test("CPI YoY-style monthly series → monthly bucket", () => {
    // 12 monthly points across a year — what summary.json ships
    // for a typical FRED monthly series.
    const sparks = { "1y": series(12, 30) };
    expect(inferFrequency(sparks)).toEqual({
      bucket: "monthly",
      days: 30,
      daysExact: 30,
    });
  });
  test("daily series → daily bucket from the 1m spark", () => {
    // 1m has ~22 daily points; longer windows are at the cap.
    const sparks: Record<string, SparkPoint[]> = {
      "1m": series(22, 1),
      "1y": series(30, 12),
    };
    const got = inferFrequency(sparks);
    expect(got?.bucket).toBe("daily");
    expect(got?.days).toBe(1);
  });
  test("weekly series → weekly bucket", () => {
    const sparks: Record<string, SparkPoint[]> = {
      "1m": series(4, 7),
      "1y": series(20, 18), // 20 points = raw; spacing 18 days
    };
    const got = inferFrequency(sparks);
    // 1y wins (larger raw), and 18-day spacing buckets to monthly,
    // NOT weekly — lock that down so we know how the boundary
    // behaves on irregular series.
    expect(got?.bucket).toBe("monthly");
    expect(got?.days).toBe(18);
  });
  test("annual series → annual bucket", () => {
    // 30y window with 30 points = downsampled, skipped. 10y also
    // at cap. 5y with 5 yearly points becomes the winner.
    const sparks: Record<string, SparkPoint[]> = {
      "5y": series(5, 365),
      "10y": series(30, 122),
      "30y": series(30, 365),
    };
    const got = inferFrequency(sparks);
    expect(got?.bucket).toBe("annual");
  });
  test("returns null when no usable spark is available", () => {
    expect(inferFrequency({})).toBeNull();
    expect(inferFrequency(undefined)).toBeNull();
  });
});
