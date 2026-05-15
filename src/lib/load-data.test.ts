import { describe, it, expect } from "vitest";
import { isServerlessRuntime, resolveServerlessOrigin } from "./load-data";

// These tests lock down the env-detection logic in load-data.ts. Two
// production outages came out of getting this wrong:
//
//   1. (cdf057db) Gated serverless-mode on process.env.VERCEL, which is
//      set at BOTH build and runtime. That made prerendered routes try
//      to fetch from a not-yet-live URL during astro build.
//   2. (cdf057db, lingering) Preferred VERCEL_URL (per-deploy hash
//      hostname) as the fetch origin. On team accounts those hostnames
//      are gated behind Vercel deployment-protection → HTTP 401 on
//      cross-Function fetches from the same deployment. Production
//      page rendered "Data unavailable" on every chart until 157e9fb3.
//
// The asserts below would have caught both bugs before they shipped.

describe("isServerlessRuntime", () => {
  it("is false when no Vercel env vars are set (local dev / non-Vercel CI)", () => {
    expect(isServerlessRuntime({})).toBe(false);
  });

  it("is false when VERCEL=1 alone is set (build time, not function runtime)", () => {
    // Regression test for cdf057db. VERCEL=1 is set at BOTH build and
    // runtime; if we treat it as a serverless signal, prerender breaks.
    expect(isServerlessRuntime({ VERCEL: "1" })).toBe(false);
  });

  it("is false at build time on Vercel CI (VERCEL=1 + VERCEL_URL set, no VERCEL_REGION)", () => {
    // Vercel sets VERCEL_URL during build too — only VERCEL_REGION is
    // unique to running Functions.
    expect(
      isServerlessRuntime({
        VERCEL: "1",
        VERCEL_URL: "tape-abc.vercel.app",
        VERCEL_ENV: "production",
      }),
    ).toBe(false);
  });

  it("is true when VERCEL_REGION is set (running inside a deployed Function)", () => {
    expect(isServerlessRuntime({ VERCEL_REGION: "iad1" })).toBe(true);
  });

  it("treats any non-empty VERCEL_REGION as serverless (not just specific regions)", () => {
    expect(isServerlessRuntime({ VERCEL_REGION: "fra1" })).toBe(true);
    expect(isServerlessRuntime({ VERCEL_REGION: "dev1" })).toBe(true);
  });
});

describe("resolveServerlessOrigin", () => {
  it("returns null when nothing is set", () => {
    expect(resolveServerlessOrigin({})).toBe(null);
  });

  it("prefers SITE_URL (verbatim, including scheme) over all Vercel vars", () => {
    expect(
      resolveServerlessOrigin({
        SITE_URL: "https://tape.com",
        VERCEL_PROJECT_PRODUCTION_URL: "tape.vercel.app",
        VERCEL_URL: "tape-abc.vercel.app",
      }),
    ).toBe("https://tape.com");
  });

  it("prefers VERCEL_PROJECT_PRODUCTION_URL over VERCEL_URL (regression: 157e9fb3)", () => {
    // The per-deploy VERCEL_URL on team accounts is gated by Vercel
    // SSO auth → 401 on cross-Function fetches. The stable production
    // URL is what we actually want to hit, so preference order
    // matters.
    expect(
      resolveServerlessOrigin({
        VERCEL_PROJECT_PRODUCTION_URL: "tape.vercel.app",
        VERCEL_URL: "tape-1i2umj3hh-team-projects.vercel.app",
      }),
    ).toBe("https://tape.vercel.app");
  });

  it("falls back to VERCEL_URL as a last resort (preview deploys etc.)", () => {
    expect(
      resolveServerlessOrigin({
        VERCEL_URL: "tape-pr-42-team.vercel.app",
      }),
    ).toBe("https://tape-pr-42-team.vercel.app");
  });

  it("prepends https:// to bare hostnames from VERCEL_* vars", () => {
    expect(
      resolveServerlessOrigin({
        VERCEL_PROJECT_PRODUCTION_URL: "host.example.com",
      }),
    ).toBe("https://host.example.com");
  });

  it("uses SITE_URL as-is without scheme massaging (caller's responsibility)", () => {
    // Trusted explicit override; we don't try to be clever about it.
    expect(
      resolveServerlessOrigin({ SITE_URL: "https://x.com/sub-path" }),
    ).toBe("https://x.com/sub-path");
  });
});
