/**
 * Tests for custom-URL slug validation + HTML escaping helpers.
 *
 * These are tiny pure helpers, but they sit on the security perimeter
 * (escapeHtml protects against XSS injected into a dashboard title)
 * and the user-facing copy is the source of truth that the renderer
 * surfaces verbatim in an alert. A regression in the rule set would
 * either let a user claim "/library.json" as a custom URL (routing
 * collision) or block a perfectly fine slug.
 */
import { describe, it, expect } from "vitest";
import {
  validateSlug,
  escapeHtml,
  RESERVED_SLUGS,
  MIN_SLUG_LENGTH,
  MAX_SLUG_LENGTH,
} from "./dashboard-slug";

describe("validateSlug", () => {
  it("returns null for typical valid slugs", () => {
    expect(validateSlug("my-dashboard")).toBeNull();
    expect(validateSlug("us-macro-2024")).toBeNull();
    expect(validateSlug("cpi")).toBeNull();
    expect(validateSlug("a1b2c3")).toBeNull();
  });

  it("rejects empty strings with a specific message", () => {
    expect(validateSlug("")).toBe("Custom URL can't be empty.");
  });

  it("rejects too-short slugs (< MIN_SLUG_LENGTH)", () => {
    expect(validateSlug("a")).toContain("at least");
    expect(validateSlug("ab")).toContain("at least");
    // The threshold is in the message, so the actual constant needs
    // to be reflected if it ever changes.
    expect(validateSlug("ab")).toContain(String(MIN_SLUG_LENGTH));
  });

  it("accepts slugs at exactly MIN_SLUG_LENGTH", () => {
    // "abc" — three chars, valid per the regex.
    expect(validateSlug("abc")).toBeNull();
  });

  it("rejects too-long slugs (> MAX_SLUG_LENGTH)", () => {
    const tooLong = "a".repeat(MAX_SLUG_LENGTH + 1);
    expect(validateSlug(tooLong)).toContain("or fewer");
    expect(validateSlug(tooLong)).toContain(String(MAX_SLUG_LENGTH));
  });

  it("accepts slugs at exactly MAX_SLUG_LENGTH", () => {
    const atMax = "a".repeat(MAX_SLUG_LENGTH);
    expect(validateSlug(atMax)).toBeNull();
  });

  it("rejects slugs with uppercase letters", () => {
    expect(validateSlug("My-Dashboard")).toContain("lowercase");
    expect(validateSlug("USA")).toContain("lowercase");
  });

  it("rejects slugs with spaces or underscores", () => {
    expect(validateSlug("my dashboard")).toContain("lowercase");
    expect(validateSlug("my_dashboard")).toContain("lowercase");
  });

  it("rejects slugs starting or ending with a dash", () => {
    expect(validateSlug("-my-dashboard")).toContain("can't start or end");
    expect(validateSlug("my-dashboard-")).toContain("can't start or end");
    expect(validateSlug("-abc-")).toContain("can't start or end");
  });

  it("allows dashes in the middle, even consecutive ones", () => {
    // Some users like "x--y" — the rule only blocks leading/trailing.
    expect(validateSlug("a-b")).toBeNull();
    expect(validateSlug("a--b")).toBeNull();
    expect(validateSlug("a-b-c-d-e")).toBeNull();
  });

  it("rejects each reserved slug with a specific quoted-name message", () => {
    // Spot-check the categories: route prefix + public-file basename.
    // "me", "u", "api" are too short to pass the length check first;
    // pick slugs that get to the reserved check.
    expect(validateSlug("compose")).toContain("reserved URL");
    expect(validateSlug("admin")).toContain("reserved URL");
    expect(validateSlug("login")).toContain("reserved URL");
    // The message quotes the offending slug back so the user sees
    // exactly what they typed.
    expect(validateSlug("compose")).toContain('"compose"');
  });

  it("rejects all entries in RESERVED_SLUGS", () => {
    // Lockdown: every member of the set is rejected by validateSlug.
    // A regression in the set membership would loosen this.
    // Filter to entries that would otherwise pass the regex (length 3+,
    // lowercase, no leading/trailing dash) — "u" is too short to be a
    // candidate-by-regex, for instance, so it gets caught by the
    // length check, not the reserved check.
    const candidates = Array.from(RESERVED_SLUGS).filter(
      (s) =>
        s.length >= MIN_SLUG_LENGTH &&
        s.length <= MAX_SLUG_LENGTH &&
        !s.startsWith("-") &&
        !s.endsWith("-") &&
        /^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/.test(s),
    );
    expect(candidates.length).toBeGreaterThan(0);
    for (const slug of candidates) {
      expect(validateSlug(slug)).toContain("reserved URL");
    }
  });

  it("includes the routing-critical reserved paths", () => {
    // These are load-bearing: if any of these were removed from the
    // set, a user could create a dashboard that shadows a real page.
    expect(RESERVED_SLUGS.has("me")).toBe(true);
    expect(RESERVED_SLUGS.has("compose")).toBe(true);
    expect(RESERVED_SLUGS.has("custom")).toBe(true);
    expect(RESERVED_SLUGS.has("api")).toBe(true);
    expect(RESERVED_SLUGS.has("auth")).toBe(true);
    expect(RESERVED_SLUGS.has("u")).toBe(true);
  });

  it("includes admin / settings / login / logout (avoid impersonation pages)", () => {
    expect(RESERVED_SLUGS.has("admin")).toBe(true);
    expect(RESERVED_SLUGS.has("settings")).toBe(true);
    expect(RESERVED_SLUGS.has("login")).toBe(true);
    expect(RESERVED_SLUGS.has("logout")).toBe(true);
    expect(RESERVED_SLUGS.has("signin")).toBe(true);
    expect(RESERVED_SLUGS.has("signout")).toBe(true);
  });

  it("includes build-emitted root paths (library.json, favicon.ico, etc.)", () => {
    expect(RESERVED_SLUGS.has("_astro")).toBe(true);
    expect(RESERVED_SLUGS.has("library.json")).toBe(true);
    expect(RESERVED_SLUGS.has("favicon.ico")).toBe(true);
    expect(RESERVED_SLUGS.has("robots.txt")).toBe(true);
    expect(RESERVED_SLUGS.has("sitemap.xml")).toBe(true);
  });

  it("rejects numeric-only slugs >= MIN_SLUG_LENGTH (allowed by regex, must be a-z0-9)", () => {
    // The regex permits purely numeric strings. The composer doesn't
    // ban them, so the validator shouldn't either. Lock the current
    // behavior in.
    expect(validateSlug("123")).toBeNull();
    expect(validateSlug("2024")).toBeNull();
  });

  it("orders checks: empty < length < format < reserved", () => {
    // Knowing the order matters for predictable error copy:
    //   - "" → empty message
    //   - "ab" → too short (not format)
    //   - "A" → too short (length check fires before format)
    //   - "AAA" → format (lowercase) check, not reserved
    expect(validateSlug("")).toContain("empty");
    expect(validateSlug("ab")).toContain("at least");
    expect(validateSlug("A")).toContain("at least"); // length wins
    expect(validateSlug("AAA")).toContain("lowercase"); // format wins
  });
});

describe("escapeHtml", () => {
  it("escapes the 5 XSS-relevant characters", () => {
    expect(escapeHtml("<")).toBe("&lt;");
    expect(escapeHtml(">")).toBe("&gt;");
    expect(escapeHtml("&")).toBe("&amp;");
    expect(escapeHtml('"')).toBe("&quot;");
    expect(escapeHtml("'")).toBe("&#39;");
  });

  it("escapes & first so other escapes don't get double-escaped", () => {
    // If & were escaped last, "<" → "&lt;" → "&amp;lt;". The current
    // implementation escapes & first so this can't happen.
    expect(escapeHtml("<")).toBe("&lt;"); // not "&amp;lt;"
    expect(escapeHtml('&"')).toBe("&amp;&quot;");
    expect(escapeHtml("&amp;")).toBe("&amp;amp;"); // intended: re-escape an already-escaped string
  });

  it("escapes a real XSS attempt cleanly", () => {
    expect(escapeHtml('<script>alert("x")</script>')).toBe(
      "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;",
    );
  });

  it("leaves safe characters alone", () => {
    expect(escapeHtml("My Dashboard 2024")).toBe("My Dashboard 2024");
    expect(escapeHtml("a/b?c=1")).toBe("a/b?c=1");
    expect(escapeHtml("résumé €")).toBe("résumé €");
  });

  it("returns empty string for empty input", () => {
    expect(escapeHtml("")).toBe("");
  });

  it("escapes single quotes too (safe in single-quoted attributes)", () => {
    // The canonical escaper (src/lib/escape-html.ts) escapes ' as well, so it's
    // correct for single-quoted attribute contexts, not just double-quoted ones.
    expect(escapeHtml("'")).toBe("&#39;");
    expect(escapeHtml("it's mine")).toBe("it&#39;s mine");
  });
});
