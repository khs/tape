import { describe, it, expect } from "vitest";
import {
  buildCitation,
  buildCitationLines,
  citationRetrievalUrl,
  type CitationInput,
} from "./citation";

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

describe("citationRetrievalUrl — chart citation 'retrieved from' target", () => {
  const fallback = () => "https://x.test/custom/?d=ENCODED";
  const call = (surface: string) =>
    citationRetrievalUrl({
      surface,
      origin: "https://x.test",
      href: "https://x.test/custom/?d=STATE&delta=5y",
      composeSingleChart: fallback,
    });

  it("cites the full href (query intact) for a composed /custom/ dashboard", () => {
    // The ?d= state IS the dashboard — stripping it would cite an empty composer.
    expect(call("custom")).toBe("https://x.test/custom/?d=STATE&delta=5y");
  });

  it("cites the full href for the per-chart detail page", () => {
    expect(call("chart")).toBe("https://x.test/custom/?d=STATE&delta=5y");
  });

  it("builds the canonical /u/<slug>/ URL for a saved dashboard", () => {
    expect(call("u-my-econ-board")).toBe("https://x.test/u/my-econ-board/");
  });

  it("builds the canonical /<slug>/ URL for a preset dashboard", () => {
    expect(call("us-macro")).toBe("https://x.test/us-macro/");
  });

  it("falls back to a single-chart /custom/ URL for the source page", () => {
    expect(call("source")).toBe("https://x.test/custom/?d=ENCODED");
  });

  it("falls back to a single-chart /custom/ URL for an embed", () => {
    expect(call("embed")).toBe("https://x.test/custom/?d=ENCODED");
  });

  it("falls back to a single-chart /custom/ URL when surface is unknown/empty", () => {
    expect(call("")).toBe("https://x.test/custom/?d=ENCODED");
  });

  it("only invokes the (costly) compose thunk on the fallback path", () => {
    let calls = 0;
    const counted = () => {
      calls++;
      return "https://x.test/custom/?d=Z";
    };
    citationRetrievalUrl({
      surface: "us-macro",
      origin: "https://x.test",
      href: "https://x.test/us-macro/",
      composeSingleChart: counted,
    });
    expect(calls).toBe(0); // dashboard branch — never composed
    citationRetrievalUrl({
      surface: "source",
      origin: "https://x.test",
      href: "https://x.test/source/fred/cpi/",
      composeSingleChart: counted,
    });
    expect(calls).toBe(1); // fallback branch — composed once
  });
});
