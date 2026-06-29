import { describe, it, expect } from "vitest";
import {
  buildCitation,
  buildCitationLines,
  buildApaCitation,
  buildChicagoCitation,
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

describe("buildApaCitation — APA 7th edition", () => {
  it("formats author, version year, italic title, [Data set], publisher, retrieval (no terminal period)", () => {
    const c = buildApaCitation(base);
    expect(c.id).toBe("apa");
    expect(c.plain).toBe(
      "FRED. (2026). US unemployment rate [Data set]. Tape. " +
        "Retrieved May 15, 2026, from https://tape.io/source/fred/us_unemployment/",
    );
    // APA does NOT end with a period after the URL.
    expect(c.plain.endsWith("/")).toBe(true);
    // Only the title is italic.
    const italic = c.segments.filter((s) => s.italic).map((s) => s.text);
    expect(italic).toEqual(["US unemployment rate"]);
  });

  it("uses the data-through YEAR (not the retrieval year) for the date", () => {
    // asOf 2026-03-31 → (2026); even though retrieval is 2026, prove it reads asOf.
    const c = buildApaCitation({ ...base, asOf: "2019-12-31" });
    expect(c.plain).toContain("(2019).");
    expect(c.plain).toContain("Retrieved May 15, 2026, from");
  });

  it("falls back to the retrieval year when asOf is missing", () => {
    const c = buildApaCitation({ ...base, asOf: undefined });
    expect(c.plain).toContain("(2026).");
  });

  it("uses (n.d.) when neither asOf nor a parseable today is present", () => {
    const c = buildApaCitation({ ...base, asOf: undefined, today: "" });
    expect(c.plain).toContain("(n.d.).");
    // No retrieval date → drop the date, keep the URL.
    expect(c.plain).toContain("Retrieved from https://tape.io/source/fred/us_unemployment/");
  });

  it("joins two providers with an ampersand", () => {
    const c = buildApaCitation({ ...base, providers: ["FRED", "Yahoo Finance"] });
    expect(c.plain.startsWith("FRED & Yahoo Finance. (2026).")).toBe(true);
  });

  it("uses a serial comma before the ampersand for three providers", () => {
    const c = buildApaCitation({
      ...base,
      providers: ["FRED", "Yahoo Finance", "World Bank"],
    });
    expect(c.plain.startsWith("FRED, Yahoo Finance, & World Bank. (2026).")).toBe(true);
  });

  it("moves the (italic) title to the author position when no provider", () => {
    const c = buildApaCitation({ ...base, providers: [] });
    expect(c.plain).toBe(
      "US unemployment rate [Data set]. (2026). Tape. " +
        "Retrieved May 15, 2026, from https://tape.io/source/fred/us_unemployment/",
    );
    expect(c.segments[0]).toEqual({ text: "US unemployment rate", italic: true });
  });
});

describe("buildChicagoCitation — Chicago 17th edition", () => {
  it("formats author, quoted title, roman website, Accessed date, terminal period", () => {
    const c = buildChicagoCitation(base);
    expect(c.id).toBe("chicago");
    expect(c.plain).toBe(
      'FRED. "US unemployment rate." Tape. Accessed May 15, 2026. ' +
        "https://tape.io/source/fred/us_unemployment/.",
    );
    // Chicago ENDS with a period after the URL (opposite of APA).
    expect(c.plain.endsWith("/.")).toBe(true);
    // Website name is roman, not italic → no italic spans at all.
    expect(c.segments.some((s) => s.italic)).toBe(false);
    // "Accessed", not "Retrieved".
    expect(c.plain).toContain("Accessed May 15, 2026.");
    expect(c.plain).not.toContain("Retrieved");
  });

  it("joins two providers with 'and'", () => {
    const c = buildChicagoCitation({ ...base, providers: ["FRED", "Yahoo Finance"] });
    expect(c.plain.startsWith('FRED and Yahoo Finance. "US unemployment rate."')).toBe(true);
  });

  it("uses a serial comma before 'and' for three providers", () => {
    const c = buildChicagoCitation({
      ...base,
      providers: ["FRED", "Yahoo Finance", "World Bank"],
    });
    expect(c.plain.startsWith('FRED, Yahoo Finance, and World Bank. "US unemployment rate."')).toBe(
      true,
    );
  });

  it("starts with the quoted title when no provider", () => {
    const c = buildChicagoCitation({ ...base, providers: [] });
    expect(c.plain).toBe(
      '"US unemployment rate." Tape. Accessed May 15, 2026. ' +
        "https://tape.io/source/fred/us_unemployment/.",
    );
  });

  it("drops the Accessed clause when today is unparseable", () => {
    const c = buildChicagoCitation({ ...base, today: "" });
    expect(c.plain).not.toContain("Accessed");
    expect(c.plain).toBe(
      'FRED. "US unemployment rate." Tape. https://tape.io/source/fred/us_unemployment/.',
    );
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
