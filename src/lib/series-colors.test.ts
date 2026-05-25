/**
 * Lockdown tests for the multi-series color palette.
 *
 * Tiny module but a lot of UI depends on it — Chart.astro multi-source
 * tiles, dialog plots, dual-axis renderers, the composer's tile
 * preview. A regression in the modular-arithmetic wrap-around or the
 * palette order is hard to catch by eye when a chart has 4 lines and
 * not 12, but breaks the moment a curator stress-tests at 10+.
 */
import { describe, it, expect } from "vitest";
import { SERIES_COLORS, seriesColor } from "./series-colors";

describe("SERIES_COLORS", () => {
  it("ships exactly 10 colors", () => {
    // 10 is the documented ceiling: past it, color encoding stops
    // working as a discriminator regardless of palette. Bumping
    // this number means re-running the visual stress-test in the
    // composer.
    expect(SERIES_COLORS).toHaveLength(10);
  });

  it("every color is a 7-char hex string starting with #", () => {
    for (const c of SERIES_COLORS) {
      expect(c).toMatch(/^#[0-9A-Fa-f]{6}$/);
    }
  });

  it("colors are unique — no duplicate would collide in legends", () => {
    expect(new Set(SERIES_COLORS).size).toBe(SERIES_COLORS.length);
  });

  it("preserves the first 6 colors in their original positions", () => {
    // Per the file's own comment: "The first 6 are the original
    // palette and are preserved in order so existing curated charts
    // don't change colors when a new series is added." This test
    // locks that in — a reorder of the first 6 would silently
    // change colors on every dashboard.
    expect(SERIES_COLORS.slice(0, 6)).toEqual([
      "#0F766E", // teal
      "#B45309", // ochre
      "#7C3AED", // violet
      "#0284C7", // blue
      "#DB2777", // magenta
      "#65A30D", // olive
    ]);
  });
});

describe("seriesColor", () => {
  it("returns palette[i] for indices in range", () => {
    expect(seriesColor(0)).toBe(SERIES_COLORS[0]);
    expect(seriesColor(5)).toBe(SERIES_COLORS[5]);
    expect(seriesColor(9)).toBe(SERIES_COLORS[9]);
  });

  it("wraps with modular arithmetic past index 9", () => {
    // The wrap is the safety net for >10-series charts. Without it
    // the renderer would receive `undefined` and Plot would draw
    // black lines.
    expect(seriesColor(10)).toBe(SERIES_COLORS[0]);
    expect(seriesColor(11)).toBe(SERIES_COLORS[1]);
    expect(seriesColor(19)).toBe(SERIES_COLORS[9]);
    expect(seriesColor(20)).toBe(SERIES_COLORS[0]);
  });

  it("returns a string for any non-negative integer", () => {
    // Spot-check a few large indices — no implementation panic.
    expect(typeof seriesColor(100)).toBe("string");
    expect(typeof seriesColor(1000)).toBe("string");
  });
});
