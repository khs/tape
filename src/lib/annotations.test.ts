import { describe, it, expect } from "vitest";
import {
  parseAnnotationLines,
  formatAnnotationLines,
  annotationsHiddenSummary,
  annotationsOutOfRangeSummary,
  type Annotation,
} from "./annotations";

describe("parseAnnotationLines", () => {
  it("returns empty for empty input", () => {
    expect(parseAnnotationLines("")).toEqual([]);
  });

  it("parses a single line", () => {
    const out = parseAnnotationLines("2008-09-15: Lehman collapse");
    expect(out).toEqual([{ date: "2008-09-15", label: "Lehman collapse" }]);
  });

  it("parses multiple lines", () => {
    const text = [
      "2008-09-15: Lehman collapse",
      "2020-03-15: COVID lockdown",
      "2022-03-16: Fed pivot",
    ].join("\n");
    const out = parseAnnotationLines(text);
    expect(out.length).toBe(3);
    expect(out[1]).toEqual({ date: "2020-03-15", label: "COVID lockdown" });
  });

  it("skips blank lines and # comments", () => {
    const text = [
      "# annotations for the GFC",
      "",
      "2008-09-15: Lehman collapse",
      "  ",
      "# COVID era",
      "2020-03-15: COVID lockdown",
    ].join("\n");
    expect(parseAnnotationLines(text).length).toBe(2);
  });

  it("parses position suffix", () => {
    const out = parseAnnotationLines("2020-03-15: COVID lockdown | below");
    expect(out[0]).toEqual({
      date: "2020-03-15",
      label: "COVID lockdown",
      position: "below",
    });
  });

  it("ignores unknown position tokens but keeps label text", () => {
    const out = parseAnnotationLines("2020-03-15: COVID lockdown | sideways");
    // sideways isn't valid → falls through; the "|" stays in label.
    expect(out[0].label).toBe("COVID lockdown | sideways");
    expect(out[0].position).toBeUndefined();
  });

  it("calls onError for missing colon", () => {
    const errs: string[] = [];
    parseAnnotationLines("missing colon here", (n, _line, reason) =>
      errs.push(`L${n}: ${reason}`),
    );
    expect(errs).toContain("L1: missing colon between date and label");
  });

  it("calls onError for bad date", () => {
    const errs: string[] = [];
    parseAnnotationLines("not-a-date: Lehman", (n, _line, reason) =>
      errs.push(`L${n}: ${reason}`),
    );
    expect(errs[0]).toContain("not a YYYY-MM-DD date");
  });

  it("calls onError for empty label", () => {
    const errs: string[] = [];
    parseAnnotationLines("2008-09-15: ", (n, _line, reason) =>
      errs.push(`L${n}: ${reason}`),
    );
    expect(errs[0]).toContain("empty label");
  });

  it("preserves a label containing a colon", () => {
    // The split happens at the FIRST colon, so e.g.
    // "2020-03-15: WHO: pandemic declared" → date 2020-03-15,
    // label "WHO: pandemic declared".
    const out = parseAnnotationLines("2020-03-15: WHO: pandemic declared");
    expect(out[0]).toEqual({
      date: "2020-03-15",
      label: "WHO: pandemic declared",
    });
  });
});

describe("formatAnnotationLines", () => {
  it("returns empty string for empty array", () => {
    expect(formatAnnotationLines([])).toBe("");
  });

  it("round-trips through parse + format unchanged for simple cases", () => {
    const original: Annotation[] = [
      { date: "2008-09-15", label: "Lehman collapse" },
      { date: "2020-03-15", label: "COVID lockdown" },
    ];
    const text = formatAnnotationLines(original);
    expect(parseAnnotationLines(text)).toEqual(original);
  });

  it("round-trips position suffix", () => {
    const original: Annotation[] = [
      { date: "2008-09-15", label: "Lehman collapse", position: "above" },
      { date: "2020-03-15", label: "COVID lockdown", position: "below" },
    ];
    const text = formatAnnotationLines(original);
    expect(parseAnnotationLines(text)).toEqual(original);
  });
});

describe("annotationsHiddenSummary", () => {
  // Standard window day-lengths the composer / ChartController also use.
  // Kept here as a fixture so the test doesn't depend on deltas.ts —
  // the production caller wires DELTA_DAYS in.
  const WINDOWS = [
    { key: "1w", days: 7 },
    { key: "1m", days: 31 },
    { key: "1y", days: 365 },
    { key: "5y", days: 365 * 5 },
    { key: "10y", days: 365 * 10 },
    { key: "30y", days: 365 * 30 },
    { key: "50y", days: 365 * 50 },
  ] as const;

  // 2026-05-21 in epoch ms — anchors all "ago" math so test results
  // don't drift over real-world time. Matches today's reference date.
  const NOW_MS = new Date("2026-05-21T00:00:00Z").getTime();
  const ms = (iso: string) => new Date(iso).getTime();

  it("returns count=0 with no recommendation when annotations is empty/undefined", () => {
    expect(
      annotationsHiddenSummary(
        undefined,
        [ms("2025-01-01"), ms("2026-05-21")],
        WINDOWS,
        NOW_MS,
      ),
    ).toEqual({ count: 0, recommendedKey: null });
    expect(
      annotationsHiddenSummary(
        [],
        [ms("2025-01-01"), ms("2026-05-21")],
        WINDOWS,
        NOW_MS,
      ),
    ).toEqual({ count: 0, recommendedKey: null });
  });

  it("returns count=0 when every annotation is inside the window", () => {
    const anns: Annotation[] = [
      { date: "2026-01-15", label: "Tariffs announced" },
      { date: "2026-03-01", label: "March CPI" },
    ];
    expect(
      annotationsHiddenSummary(
        anns,
        [ms("2025-05-21"), ms("2026-05-21")],
        WINDOWS,
        NOW_MS,
      ),
    ).toEqual({ count: 0, recommendedKey: null });
  });

  it("counts annotations older than the window and recommends the smallest sufficient window", () => {
    const anns: Annotation[] = [
      { date: "2008-09-15", label: "Lehman" },
      { date: "2020-03-15", label: "COVID" },
    ];
    // Window is the trailing 1 year — both annotations fall outside.
    // The 1y window's lookback (365d) doesn't cover Lehman (~17.7y
    // ago); 5y doesn't either (~17.7y > 5y); 10y doesn't (~17.7y > 10y);
    // 30y does. So that's the recommended window.
    const out = annotationsHiddenSummary(
      anns,
      [ms("2025-05-21"), ms("2026-05-21")],
      WINDOWS,
      NOW_MS,
    );
    expect(out.count).toBe(2);
    expect(out.recommendedKey).toBe("30y");
  });

  it("recommends the smallest, not the widest, sufficient window", () => {
    const anns: Annotation[] = [{ date: "2024-06-01", label: "Election day" }];
    // ~2024-06-01 is ~1.97y ago from 2026-05-21. 1y is too short, but
    // 5y is wide enough — and 10y / 30y / 50y also are. The smallest
    // sufficient window (5y) should win.
    const out = annotationsHiddenSummary(
      anns,
      [ms("2026-05-01"), ms("2026-05-21")],
      WINDOWS,
      NOW_MS,
    );
    expect(out.count).toBe(1);
    expect(out.recommendedKey).toBe("5y");
  });

  it("returns count without a recommendation when no window is wide enough", () => {
    // Annotation is ~76 years ago — older than the widest standard
    // window (50y). The user can reach it via a custom fixedRange or
    // a long-enough source, but no standard pill helps. Surface the
    // count, omit the suggestion.
    const anns: Annotation[] = [
      { date: "1950-06-01", label: "Korean War starts" },
    ];
    const out = annotationsHiddenSummary(
      anns,
      [ms("2025-05-21"), ms("2026-05-21")],
      WINDOWS,
      NOW_MS,
    );
    expect(out.count).toBe(1);
    expect(out.recommendedKey).toBeNull();
  });

  it("omits the recommendation when every off-window annotation is in the future", () => {
    // Annotation date > endMs (the user typed a future date). No
    // trailing-past window helps. Future-dated annotation handling
    // is rare but shouldn't crash the helper.
    const anns: Annotation[] = [
      { date: "2030-01-01", label: "Future event" },
    ];
    const out = annotationsHiddenSummary(
      anns,
      [ms("2025-05-21"), ms("2026-05-21")],
      WINDOWS,
      NOW_MS,
    );
    expect(out.count).toBe(1);
    expect(out.recommendedKey).toBeNull();
  });

  it("uses the oldest off-window annotation to pick the recommendation", () => {
    // Two off-window annotations of very different ages; the
    // recommendation must cover the OLDEST (binding constraint).
    const anns: Annotation[] = [
      { date: "2024-06-01", label: "Election" }, // ~2y ago
      { date: "2008-09-15", label: "Lehman" }, // ~17.7y ago
    ];
    const out = annotationsHiddenSummary(
      anns,
      [ms("2026-05-01"), ms("2026-05-21")],
      WINDOWS,
      NOW_MS,
    );
    expect(out.count).toBe(2);
    expect(out.recommendedKey).toBe("30y");
  });

  it("works with an unsorted windowDaysList (sorts internally)", () => {
    // Production passes windows in sorted order via DELTA_DAYS, but
    // the helper shouldn't assume that — pre-sort defensively.
    const shuffled = [
      { key: "50y", days: 365 * 50 },
      { key: "1y", days: 365 },
      { key: "10y", days: 365 * 10 },
      { key: "5y", days: 365 * 5 },
    ];
    const anns: Annotation[] = [
      { date: "2024-06-01", label: "Election" },
    ];
    const out = annotationsHiddenSummary(
      anns,
      [ms("2026-05-01"), ms("2026-05-21")],
      shuffled,
      NOW_MS,
    );
    expect(out.recommendedKey).toBe("5y");
  });
});

describe("annotationsOutOfRangeSummary", () => {
  it("returns empty when annotations or sources are missing", () => {
    expect(annotationsOutOfRangeSummary([], [])).toEqual({
      offBefore: [],
      offAfter: [],
      unionStart: null,
      unionEnd: null,
    });
    expect(
      annotationsOutOfRangeSummary(undefined, [
        { firstObservation: "2000-01-01", lastObservation: "2026-05-01" },
      ]),
    ).toEqual({
      offBefore: [],
      offAfter: [],
      unionStart: null,
      unionEnd: null,
    });
    expect(
      annotationsOutOfRangeSummary(
        [{ date: "2010-01-01", label: "x" }],
        [],
      ),
    ).toEqual({
      offBefore: [],
      offAfter: [],
      unionStart: null,
      unionEnd: null,
    });
  });

  it("returns empty when sources have no observed-date metadata at all", () => {
    // Without firstObservation / lastObservation we can't decide
    // reachability — better to stay silent than guess.
    const anns: Annotation[] = [{ date: "1900-01-01", label: "very old" }];
    const out = annotationsOutOfRangeSummary(anns, [{}, {}]);
    expect(out).toEqual({
      offBefore: [],
      offAfter: [],
      unionStart: null,
      unionEnd: null,
    });
  });

  it("flags annotations predating every source's firstObservation", () => {
    const anns: Annotation[] = [
      { date: "1950-06-01", label: "Korean War" },
      { date: "2010-05-01", label: "Greek bailout" }, // in-range
    ];
    const sources = [
      { firstObservation: "2003-12-31", lastObservation: "2026-04-30" },
      { firstObservation: "2008-01-01", lastObservation: "2026-05-01" },
    ];
    const out = annotationsOutOfRangeSummary(anns, sources);
    // Union spans the widest range: min(first) to max(last).
    expect(out.unionStart).toBe("2003-12-31");
    expect(out.unionEnd).toBe("2026-05-01");
    expect(out.offBefore.map((a) => a.date)).toEqual(["1950-06-01"]);
    expect(out.offAfter).toEqual([]);
  });

  it("flags annotations postdating every source's lastObservation", () => {
    const anns: Annotation[] = [
      { date: "2030-01-01", label: "Future event" },
      { date: "2020-03-15", label: "COVID" }, // in-range
    ];
    const sources = [
      { firstObservation: "2003-12-31", lastObservation: "2026-04-30" },
    ];
    const out = annotationsOutOfRangeSummary(anns, sources);
    expect(out.unionEnd).toBe("2026-04-30");
    expect(out.offAfter.map((a) => a.date)).toEqual(["2030-01-01"]);
    expect(out.offBefore).toEqual([]);
  });

  it("uses the UNION across sources (one source extending further widens the range)", () => {
    const anns: Annotation[] = [
      { date: "1980-06-01", label: "Volcker shock" }, // before second source, in range of first
    ];
    const sources = [
      // Long-range source — its data goes back to 1962, so the
      // annotation is reachable via this source's coverage.
      { firstObservation: "1962-01-02", lastObservation: "2026-05-01" },
      // Short-range source — wouldn't cover 1980 alone.
      { firstObservation: "2010-01-01", lastObservation: "2026-04-30" },
    ];
    const out = annotationsOutOfRangeSummary(anns, sources);
    expect(out.unionStart).toBe("1962-01-02"); // min wins
    expect(out.offBefore).toEqual([]); // 1980 IS reachable
    expect(out.offAfter).toEqual([]);
  });

  it("handles a source with one-sided coverage (firstObservation only, no last)", () => {
    // Partial metadata is allowed; we still flag annotations against
    // whatever side we have.
    const anns: Annotation[] = [
      { date: "1900-01-01", label: "very old" },
      { date: "2050-01-01", label: "very future" },
    ];
    const out = annotationsOutOfRangeSummary(anns, [
      { firstObservation: "2000-01-01" },
    ]);
    expect(out.unionStart).toBe("2000-01-01");
    expect(out.unionEnd).toBeNull();
    expect(out.offBefore.map((a) => a.date)).toEqual(["1900-01-01"]);
    // No lastObservation → we don't flag the future-dated annotation.
    expect(out.offAfter).toEqual([]);
  });
});
