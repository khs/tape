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
      charts: ["us-macro/cpi", "us-macro/nasdaq"],
    });
    const dec = decodeComposedState(enc);
    expect(dec.ok).toBe(true);
    if (dec.ok) {
      expect(dec.state.v).toBe(COMPOSER_STATE_VERSION);
      expect(dec.state.title).toBe("Test");
      expect(dec.state.charts).toEqual(["us-macro/cpi", "us-macro/nasdaq"]);
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
