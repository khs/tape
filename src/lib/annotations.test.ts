import { describe, it, expect } from "vitest";
import {
  parseAnnotationLines,
  formatAnnotationLines,
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
    parseAnnotationLines("missing colon here", (n, line, reason) =>
      errs.push(`L${n}: ${reason}`),
    );
    expect(errs).toContain("L1: missing colon between date and label");
  });

  it("calls onError for bad date", () => {
    const errs: string[] = [];
    parseAnnotationLines("not-a-date: Lehman", (n, line, reason) =>
      errs.push(`L${n}: ${reason}`),
    );
    expect(errs[0]).toContain("not a YYYY-MM-DD date");
  });

  it("calls onError for empty label", () => {
    const errs: string[] = [];
    parseAnnotationLines("2008-09-15: ", (n, line, reason) =>
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
