import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { track, isTrackingConfigured } from "./track";

describe("track — analytics is fire-and-forget + crash-safe", () => {
  it("track() never throws (no-ops on SSR / when PostHog is unconfigured)", () => {
    // vitest runs in the node environment (no window), so ensureInit short-
    // circuits and track() must return without touching posthog.
    expect(() => track("test_event", { a: 1, b: "x", c: true })).not.toThrow();
    expect(() => track("bare_event")).not.toThrow();
  });

  it("isTrackingConfigured returns a boolean", () => {
    expect(typeof isTrackingConfigured()).toBe("boolean");
  });
});

describe("track.ts source shape — posthog-js stays OFF the synchronous import path", () => {
  const src = fs.readFileSync(path.join(process.cwd(), "src", "lib", "track.ts"), "utf8");

  it("does NOT statically import posthog-js (the 188KB-on-every-chart-page regression)", () => {
    // A top-level `import posthog from "posthog-js"` pulls the whole bundle onto
    // the synchronous critical path of every page that mounts a chart. The fix
    // requires it be loaded lazily, so a static import here is the regression.
    expect(src).not.toMatch(/^\s*import\s+[^;]*\bfrom\s+["']posthog-js["']/m);
  });

  it("loads posthog-js via a dynamic import()", () => {
    expect(src).toMatch(/import\(\s*["']posthog-js["']\s*\)/);
  });
});
