/**
 * Property-based fuzz of the composed-dashboard decode boundary — the single
 * most attacker-exposed parser in the app: it takes a base64 blob straight off
 * a shared `?d=` / `?state=` URL (or a saved-dashboard row) and turns it into a
 * rendered dashboard for a logged-in viewer. The 2026-06 security audit cleared
 * it (tagged DecodeResult, no throw, Zod-validated, no prototype-pollution
 * vector); this hammers it with 1000s of adversarial inputs so a future edit
 * can't silently regress those guarantees.
 *
 * Out of scope (covered by the audit, not here): the missing max-count bound on
 * sections/charts/inlineCharts — a DoS/cost finding, not a decode-safety one.
 */
import { describe, it, expect } from "vitest";
import fc from "fast-check";
import { decodeComposedState, encodeComposedState } from "../src/lib/composer-state";

/** Re-create the URL-safe base64 that decodeComposedState expects, so we can
 *  feed it ARBITRARY payloads (not just well-formed states). */
function toLink(value: unknown): string {
  const b64 = Buffer.from(new TextEncoder().encode(JSON.stringify(value))).toString("base64");
  return b64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

describe("decodeComposedState fuzz (untrusted shared-link input)", () => {
  it("never throws on an arbitrary raw string", () => {
    fc.assert(
      fc.property(fc.string(), (raw) => {
        const r = decodeComposedState(raw);
        expect(typeof r.ok).toBe("boolean");
        if (!r.ok) expect(typeof r.reason).toBe("string");
      }),
      { numRuns: 2000 },
    );
  });

  it("never throws on arbitrary JSON encoded as a link", () => {
    fc.assert(
      fc.property(fc.jsonValue(), (value) => {
        expect(typeof decodeComposedState(toLink(value)).ok).toBe("boolean");
      }),
      { numRuns: 2000 },
    );
  });

  it("never pollutes Object.prototype, even with __proto__/constructor payloads", () => {
    const polluters = fc.oneof(
      fc.constant({ v: 1, ["__proto__"]: { polluted: true } }),
      fc.constant({ v: 1, constructor: { prototype: { polluted: true } } }),
      fc.constant({ v: 1, sections: [{ ["__proto__"]: { polluted: true } }] }),
      fc.constant({ v: 1, inlineCharts: { ["__proto__"]: { polluted: true } } }),
      fc.dictionary(fc.constantFrom("__proto__", "constructor", "prototype", "v"), fc.jsonValue()),
    );
    fc.assert(
      fc.property(polluters, (payload) => {
        decodeComposedState(toLink(payload));
        expect((Object.prototype as Record<string, unknown>).polluted).toBeUndefined();
        expect(({} as Record<string, unknown>).polluted).toBeUndefined();
      }),
      { numRuns: 500 },
    );
  });

  it("round-trips any valid composed state (encode -> decode -> ok)", () => {
    const validState = fc.record({
      title: fc.option(fc.string(), { nil: undefined }),
      charts: fc.option(fc.array(fc.string()), { nil: undefined }),
      sections: fc.option(
        fc.array(
          fc.record({ title: fc.string(), charts: fc.array(fc.string(), { minLength: 1 }) }),
        ),
        { nil: undefined },
      ),
    });
    fc.assert(
      fc.property(validState, (partial) => {
        const r = decodeComposedState(encodeComposedState(partial as Parameters<typeof encodeComposedState>[0]));
        expect(r.ok).toBe(true);
      }),
      { numRuns: 500 },
    );
  });

  it("rejects states exceeding the DoS count caps, accepts within-cap", () => {
    const section = () => ({ title: "x", charts: ["a"] });
    const over: unknown[] = [
      { v: 1, sections: Array.from({ length: 101 }, section) }, // > MAX_SECTIONS
      { v: 1, charts: Array.from({ length: 301 }, (_, i) => String(i)) }, // > MAX_CHARTS
      {
        v: 1,
        inlineCharts: Object.fromEntries(
          Array.from({ length: 301 }, (_, i) => [String(i), { title: "x", sources: ["a"] }]),
        ),
      }, // > MAX_INLINE_ENTRIES
    ];
    for (const payload of over) expect(decodeComposedState(toLink(payload)).ok).toBe(false);
    expect(
      decodeComposedState(toLink({ v: 1, sections: Array.from({ length: 100 }, section) })).ok,
    ).toBe(true);
  });
});
