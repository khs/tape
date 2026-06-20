import { describe, it, expect } from "vitest";
import {
  DELTA_WINDOWS,
  DELTA_DAYS,
  closestSupported,
  windowDays,
  windowStartMs,
  deltaPrior,
} from "./deltas";

describe("DELTA_WINDOWS / DELTA_DAYS", () => {
  it("ranks windows in ascending duration order", () => {
    // Every window in DELTA_WINDOWS comes before later windows in DELTA_DAYS.
    // YTD's nominal half-year duration is deliberately positioned between
    // 1m and 1y; verify that hasn't drifted.
    const days = DELTA_WINDOWS.map((w) => DELTA_DAYS[w]);
    for (let i = 1; i < days.length; i++) {
      expect(days[i]).toBeGreaterThan(days[i - 1]);
    }
  });
});

describe("closestSupported", () => {
  it("returns the want value verbatim when supported", () => {
    expect(closestSupported("1y", ["1m", "1y", "10y"])).toBe("1y");
  });

  it("falls back to the log-closest window when not supported", () => {
    // 1y is closer to 1m (log-scale) than to 30y.
    expect(closestSupported("1y", ["1m", "30y"])).toBe("1m");
    // 5y is closer to 10y than to 1m.
    expect(closestSupported("5y", ["1m", "10y"])).toBe("10y");
  });

  it("returns want unchanged when supported list is empty", () => {
    expect(closestSupported("1y", [])).toBe("1y");
  });

  it("handles a single-element supported list", () => {
    expect(closestSupported("1y", ["30y"])).toBe("30y");
  });
});

describe("windowDays", () => {
  it("returns the nominal day count for fixed-length windows", () => {
    expect(windowDays("1w")).toBe(7);
    expect(windowDays("1y")).toBe(365);
    expect(windowDays("10y")).toBe(3650);
  });

  it("YTD returns days elapsed since Jan 1 of the reference year", () => {
    // March 15 → 31 (Jan) + 28 (Feb non-leap) + 14 (Mar 1-14 before Mar 15)
    //         = 73 days from Jan 1 to Mar 15.
    const mar15_2025 = new Date(Date.UTC(2025, 2, 15));
    expect(windowDays("ytd", mar15_2025)).toBe(73);
  });

  it("YTD on January 1 still returns at least 1 (defensive)", () => {
    const jan1 = new Date(Date.UTC(2026, 0, 1));
    expect(windowDays("ytd", jan1)).toBe(1);
  });
});

describe("windowStartMs", () => {
  it("returns refMs minus the nominal day count for trailing windows", () => {
    const ref = Date.UTC(2025, 5, 15); // Jun 15 2025
    const oneMonthBack = windowStartMs(ref, "1m");
    expect(ref - oneMonthBack).toBe(30 * 86400000);
  });

  it("YTD always anchors at Jan 1 of the reference year, not days-back", () => {
    const ref = Date.UTC(2025, 5, 15); // Jun 15 2025
    const ytdStart = windowStartMs(ref, "ytd");
    expect(ytdStart).toBe(Date.UTC(2025, 0, 1));
  });
});

describe("max (all time)", () => {
  it("windowStartMs(max) floors at the min valid JS date so every point passes", () => {
    const start = windowStartMs(Date.UTC(2026, 0, 1), "max");
    expect(start).toBe(-8.64e15);
    // Must stay a valid Date everywhere downstream consumes it (not NaN).
    expect(Number.isNaN(new Date(start).getTime())).toBe(false);
  });

  it("windowDays(max) is the finite 200y sentinel, not the floor", () => {
    expect(windowDays("max")).toBe(365 * 200);
  });

  it("closestSupported treats max as universally supported", () => {
    expect(closestSupported("max", ["1y", "5y"])).toBe("max");
    expect(closestSupported("max", ["1m", "max"])).toBe("max");
    expect(closestSupported("max", [])).toBe("max");
  });

  it("keeps max last in DELTA_WINDOWS (ascending-order invariant holds)", () => {
    expect(DELTA_WINDOWS[DELTA_WINDOWS.length - 1]).toBe("max");
    expect(DELTA_DAYS.max).toBeGreaterThan(DELTA_DAYS["50y"]);
  });
});

describe("deltaPrior", () => {
  it("returns a Date matching windowStartMs", () => {
    const now = new Date(Date.UTC(2025, 5, 15));
    const prior = deltaPrior(now, "ytd");
    expect(prior.getTime()).toBe(Date.UTC(2025, 0, 1));
  });
});
