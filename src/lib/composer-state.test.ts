import { describe, it, expect } from "vitest";
import {
  encodeComposedState,
  decodeComposedState,
  COMPOSER_STATE_VERSION,
} from "./composer-state";

describe("encode → decode round-trip", () => {
  it("preserves a minimal flat-charts state", () => {
    const enc = encodeComposedState({
      title: "Test",
      charts: ["us-macro/cpi", "us-macro/unemployment"],
    });
    const dec = decodeComposedState(enc);
    expect(dec.ok).toBe(true);
    if (dec.ok) {
      expect(dec.state.v).toBe(COMPOSER_STATE_VERSION);
      expect(dec.state.title).toBe("Test");
      expect(dec.state.charts).toEqual(["us-macro/cpi", "us-macro/unemployment"]);
    }
  });

  it("preserves a sectioned state with overrides and inline charts", () => {
    const enc = encodeComposedState({
      title: "Sectioned",
      defaultDelta: "5y",
      sections: [
        { title: "First", charts: ["a", "b"] },
        { title: "Second", charts: ["inline:abc123"] },
      ],
      chartOverrides: {
        a: { title: "Custom A", blurb: "hello" },
      },
      inlineCharts: {
        "inline:abc123": {
          title: "Ratio",
          sources: ["fred/x", "fred/y"],
          op: "divide",
          scale: "log",
        },
      },
    });
    const dec = decodeComposedState(enc);
    expect(dec.ok).toBe(true);
    if (dec.ok) {
      expect(dec.state.sections).toHaveLength(2);
      expect(dec.state.chartOverrides?.a?.title).toBe("Custom A");
      expect(dec.state.inlineCharts?.["inline:abc123"]?.scale).toBe("log");
      expect(dec.state.inlineCharts?.["inline:abc123"]?.op).toBe("divide");
    }
  });

  it("round-trips inline derived sources (inlineSources) including tags", () => {
    const enc = encodeComposedState({
      title: "Derived",
      sections: [{ title: "S", charts: ["derived:d1"] }],
      inlineSources: {
        "derived:d1": {
          op: "divide",
          a: "fred/gdp",
          b: "fred/pop",
          name: "GDP per capita",
          tags: ["custom", "macro"],
        },
      },
    });
    const dec = decodeComposedState(enc);
    expect(dec.ok).toBe(true);
    if (dec.ok) {
      expect(dec.state.inlineSources?.["derived:d1"]).toEqual({
        op: "divide",
        a: "fred/gdp",
        b: "fred/pop",
        name: "GDP per capita",
        tags: ["custom", "macro"],
      });
    }
  });

  it("round-trips inline maps (inlineMaps) with bbox + colour options", () => {
    const enc = encodeComposedState({
      title: "Maps",
      sections: [{ title: "S", charts: ["inlinemap:m1"] }],
      inlineMaps: {
        "inlinemap:m1": {
          title: "Poverty by county",
          geo: "county",
          indicator: "poverty_rate",
          vintage: "2022",
          bbox: [-125, 24, -66, 50],
          colorScheme: "reds",
          colorScale: "log",
          blurb: "Share below the poverty line.",
        },
      },
    });
    const dec = decodeComposedState(enc);
    expect(dec.ok).toBe(true);
    if (dec.ok) {
      const m = dec.state.inlineMaps?.["inlinemap:m1"];
      expect(m?.bbox).toEqual([-125, 24, -66, 50]);
      expect(m?.colorScheme).toBe("reds");
      expect(m?.colorScale).toBe("log");
      expect(m?.geo).toBe("county");
      expect(m?.vintage).toBe("2022");
    }
  });

  it("preserves a section fixedRange (pinned start/end window)", () => {
    const enc = encodeComposedState({
      title: "Pinned",
      sections: [
        {
          title: "S",
          charts: ["a"],
          fixedRange: { start: "2008-01-01", end: "2012-12-31" },
        },
      ],
    });
    const dec = decodeComposedState(enc);
    expect(dec.ok).toBe(true);
    if (dec.ok) {
      expect(dec.state.sections?.[0]?.fixedRange).toEqual({
        start: "2008-01-01",
        end: "2012-12-31",
      });
    }
  });

  it("strips undefined fields so encoding stays compact", () => {
    const enc1 = encodeComposedState({ title: "x", charts: ["a"] });
    const enc2 = encodeComposedState({
      title: "x",
      charts: ["a"],
      description: undefined,
      defaultDelta: undefined,
    });
    expect(enc1).toBe(enc2);
  });
});

describe("decode error handling", () => {
  it("returns ok=false with reason='empty' for empty input", () => {
    expect(decodeComposedState(null)).toEqual(
      expect.objectContaining({ ok: false, reason: "empty" }),
    );
    expect(decodeComposedState("")).toEqual(
      expect.objectContaining({ ok: false, reason: "empty" }),
    );
  });

  it("returns ok=false with reason='invalid-encoding' for malformed base64", () => {
    // Valid base64url but JSON.parse will fail on the decoded string.
    const garbage = "bm90LWpzb24"; // base64url("not-json")
    const dec = decodeComposedState(garbage);
    expect(dec.ok).toBe(false);
    if (!dec.ok) expect(dec.reason).toBe("invalid-encoding");
  });

  it("returns ok=false with reason='wrong-version' when v doesn't match", () => {
    // Hand-craft a base64url of `{v: 999}` to simulate a future-version
    // composition link being opened by a currently-deployed renderer.
    const enc = Buffer.from(JSON.stringify({ v: 999, charts: ["a"] }))
      .toString("base64")
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=+$/, "");
    const dec = decodeComposedState(enc);
    expect(dec.ok).toBe(false);
    if (!dec.ok) expect(dec.reason).toBe("wrong-version");
  });

  it("returns ok=false with reason='invalid-shape' for missing required fields", () => {
    // No `v` at all → schema validation fails. Not a version mismatch
    // (which requires a numeric `v` that's different); this is straight
    // shape rejection.
    const enc = Buffer.from(JSON.stringify({ charts: ["a"] }))
      .toString("base64")
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=+$/, "");
    const dec = decodeComposedState(enc);
    expect(dec.ok).toBe(false);
    if (!dec.ok) expect(dec.reason).toBe("invalid-shape");
  });

  it("rejects sections with zero charts", () => {
    // Section schema requires charts: z.array(z.string()).min(1).
    const enc = encodeComposedState({
      title: "Bad",
      sections: [{ title: "Empty", charts: [] }],
    });
    const dec = decodeComposedState(enc);
    expect(dec.ok).toBe(false);
  });
});

describe("URL-safety of encoded output", () => {
  it("contains no characters that need percent-encoding in a query value", () => {
    const enc = encodeComposedState({
      title: "Hello, world! 100% / 50%",
      description: "Symbols: + / = & ? #",
      charts: ["a"],
    });
    // base64url alphabet = [A-Za-z0-9_-]
    expect(enc).toMatch(/^[A-Za-z0-9_-]+$/);
  });

  it("has no padding (=)", () => {
    const enc = encodeComposedState({ title: "x", charts: ["a"] });
    expect(enc).not.toContain("=");
  });
});

// ---------------------------------------------------------------------------
// TEMPORARY parity guard for the chartOverride schema unification (Plan 5).
// The composer URL-state chartOverride field set is now shared with the
// dashboard content schema via src/lib/chart-schema.ts. Before this change a
// forked preset kept only title/defaultDelta/blurb and dropped the rest, so a
// forked dashboard rendered DIFFERENTLY from the source preset. These tests
// pin the new behavior: a fully-specified override survives the encode→decode
// round-trip with every field intact, so what's displayed after a fork
// matches the preset. CULL once this is live on Vercel and verified there.
// ---------------------------------------------------------------------------
describe("Plan 5 — chartOverride round-trip fidelity (TEMPORARY)", () => {
  it("keeps COMPOSER_STATE_VERSION at 1 (the change is additive)", () => {
    // A version bump would force a re-fork of every existing saved/shared
    // link via the wrong-version banner. Adding optional fields doesn't
    // warrant that. If this ever legitimately needs to bump, delete this
    // assertion deliberately — don't bump casually.
    expect(COMPOSER_STATE_VERSION).toBe(1);
  });

  it("preserves every chartOverride field through a fork round-trip", () => {
    const enc = encodeComposedState({
      title: "Forked",
      charts: ["us-macro/cpi"],
      chartOverrides: {
        "us-macro/cpi": {
          title: "Custom title",
          render: "bar",
          defaultDelta: "5y",
          blurb: "Custom blurb",
          sources: ["fred/x", "fred/y"],
          emphasis: "change",
          normalize: "dual-axis",
          scale: "log",
          seriesLabels: ["X", "Y"],
          percentDisplay: "decimal",
          transform: "yoy_pct",
          annotations: [
            { date: "2020-03-01", label: "COVID", position: "above" },
          ],
          shading: ["recessions", "president_party"],
          barOrientation: "horizontal",
          barSort: "asc",
          barAsOf: "2024-01-01",
        },
      },
    });
    const dec = decodeComposedState(enc);
    expect(dec.ok).toBe(true);
    if (dec.ok) {
      // Deep-equality: NOTHING is silently dropped. This is the regression
      // guard for the old lossy fork (which kept only 3 of these 16 fields).
      expect(dec.state.chartOverrides?.["us-macro/cpi"]).toEqual({
        title: "Custom title",
        render: "bar",
        defaultDelta: "5y",
        blurb: "Custom blurb",
        sources: ["fred/x", "fred/y"],
        emphasis: "change",
        normalize: "dual-axis",
        scale: "log",
        seriesLabels: ["X", "Y"],
        percentDisplay: "decimal",
        transform: "yoy_pct",
        annotations: [
          { date: "2020-03-01", label: "COVID", position: "above" },
        ],
        shading: ["recessions", "president_party"],
        barOrientation: "horizontal",
        barSort: "asc",
        barAsOf: "2024-01-01",
      });
    }
  });

  it("still accepts the old minimal override shape (backward compatible)", () => {
    // A v1 link created before the unification carried only these fields.
    const enc = encodeComposedState({
      title: "Old",
      charts: ["a"],
      chartOverrides: { a: { title: "T", defaultDelta: "1y", blurb: "B" } },
    });
    const dec = decodeComposedState(enc);
    expect(dec.ok).toBe(true);
    if (dec.ok) {
      expect(dec.state.chartOverrides?.a).toEqual({
        title: "T",
        defaultDelta: "1y",
        blurb: "B",
      });
    }
  });
});
