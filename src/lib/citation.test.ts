import { describe, it, expect } from "vitest";
import { buildCitation, buildCitationLines, type CitationInput } from "./citation";

const base: CitationInput = {
  title: "US unemployment rate",
  providers: ["FRED"],
  asOf: "2026-03-31",
  url: "https://tape.io/source/fred/us_unemployment/",
  today: "2026-05-15",
};

describe("buildCitation — joined plain text", () => {
  it("includes title, provider, as-of, retrieval, URL in order", () => {
    const out = buildCitation(base);
    // Title comes first, quoted.
    expect(out.indexOf('"US unemployment rate." Tape.')).toBe(0);
    // Provider follows.
    expect(out).toContain("Data: FRED.");
    // As-of follows providers.
    expect(out).toContain("Data through 2026-03-31.");
    // Retrieval line carries today's date + URL.
    expect(out).toContain("Retrieved 2026-05-15 from https://tape.io/source/fred/us_unemployment/.");
  });

  it("omits Data line when no providers", () => {
    const out = buildCitation({ ...base, providers: [] });
    expect(out).not.toContain("Data:");
  });

  it("omits Data line when providers contain only falsy strings", () => {
    // filter(Boolean) drops empty / null entries.
    const out = buildCitation({ ...base, providers: ["", ""] });
    expect(out).not.toContain("Data:");
  });

  it("omits as-of when missing", () => {
    const out = buildCitation({ ...base, asOf: undefined });
    expect(out).not.toContain("Data through");
  });

  it("joins multiple providers with semicolons", () => {
    const out = buildCitation({ ...base, providers: ["FRED", "Yahoo Finance"] });
    expect(out).toContain("Data: FRED; Yahoo Finance.");
  });

  it("includes license line when set", () => {
    const out = buildCitation({ ...base, license: "Public domain (US govt)" });
    expect(out).toContain("License: Public domain (US govt).");
  });

  it("omits license line when unset", () => {
    const out = buildCitation(base);
    expect(out).not.toContain("License:");
  });
});

describe("buildCitationLines — array form", () => {
  it("returns one entry per non-empty line", () => {
    const lines = buildCitationLines(base);
    // Sequence with no license: title, providers, as-of, retrieval.
    expect(lines.length).toBe(4);
    expect(lines[0]).toMatch(/^"US unemployment rate\." Tape\./);
    expect(lines[1]).toBe("Data: FRED.");
    expect(lines[2]).toBe("Data through 2026-03-31.");
    expect(lines[3]).toMatch(/^Retrieved 2026-05-15 /);
  });

  it("drops both data + as-of lines when both are missing", () => {
    const lines = buildCitationLines({
      ...base,
      asOf: undefined,
      providers: [],
    });
    // Only title + retrieval lines remain.
    expect(lines.length).toBe(2);
    expect(lines[0]).toMatch(/^"US unemployment rate\." Tape\./);
    expect(lines[1]).toMatch(/^Retrieved 2026-05-15 /);
  });

  it("expands to 5 lines when license is set", () => {
    const lines = buildCitationLines({
      ...base,
      license: "CC-BY-4.0",
    });
    // title + data + as-of + license + retrieval.
    expect(lines.length).toBe(5);
    expect(lines[3]).toBe("License: CC-BY-4.0.");
  });
});
