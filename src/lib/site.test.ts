import { describe, it, expect } from "vitest";
import { canonicalOrigin } from "./site";

describe("canonicalOrigin", () => {
  it("prefers the configured site origin, stripping its trailing slash", () => {
    // new URL("https://tape.io") stringifies with a trailing slash.
    const out = canonicalOrigin({
      site: new URL("https://tape.io"),
      url: new URL("https://whatever.vercel.app/source/fred/cpi_yoy/"),
    });
    expect(out).toBe("https://tape.io");
  });

  it("keeps a non-root site path but drops the trailing slash", () => {
    const out = canonicalOrigin({
      site: new URL("https://example.com/base/"),
      url: new URL("https://example.com/base/source/x/"),
    });
    expect(out).toBe("https://example.com/base");
  });

  it("falls back to the request origin when site is unset (dev)", () => {
    const out = canonicalOrigin({
      site: undefined,
      url: new URL("http://localhost:4321/source/fred/cpi_yoy/"),
    });
    expect(out).toBe("http://localhost:4321");
  });

  it("composes into an absolute citation URL (regression: no bare /source/...)", () => {
    const origin = canonicalOrigin({
      site: new URL("https://legible-markets.vercel.app"),
      url: new URL("https://legible-markets.vercel.app/source/fred/cpi_yoy/"),
    });
    const baseUrl = ""; // production BASE_URL "/" → "" after trailing-slash strip
    const canonicalUrl = `${origin}${baseUrl}/source/fred/cpi_yoy/`;
    expect(canonicalUrl).toBe(
      "https://legible-markets.vercel.app/source/fred/cpi_yoy/",
    );
    expect(canonicalUrl.startsWith("https://")).toBe(true);
  });
});
