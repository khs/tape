import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { embedNeedsController, SELF_WIRING_RENDERS } from "./chart-render";

describe("embedNeedsController — only line charts need the ChartController island", () => {
  it("line (explicit) needs the controller", () => {
    expect(embedNeedsController("line")).toBe(true);
  });

  it("unset render is treated as line and needs the controller", () => {
    expect(embedNeedsController(undefined)).toBe(true);
    expect(embedNeedsController(null)).toBe(true);
  });

  it("bar + map self-wire and must NOT get the controller (the welcome-page perf bug)", () => {
    // The bug: the embed mounted ChartController for every render type, shipping
    // ~290KB of dead JS (PostHog + composer-state + the controller) on bar/map
    // embeds where ChartBar/ChartMap already self-wire.
    expect(embedNeedsController("bar")).toBe(false);
    expect(embedNeedsController("map")).toBe(false);
  });

  it("class: every self-wiring render type skips the controller", () => {
    for (const r of SELF_WIRING_RENDERS) {
      expect(embedNeedsController(r)).toBe(false);
    }
  });

  it("an unknown/future render type defaults to getting the controller (safe direction)", () => {
    // Deny-list: only known self-wiring types are dropped; anything else still
    // gets the controller rather than silently rendering unwired.
    expect(embedNeedsController("sankey")).toBe(true);
  });

  it("SELF_WIRING_RENDERS stays in sync with SectionChart's self-wiring dispatch", () => {
    expect([...SELF_WIRING_RENDERS].sort()).toEqual(["bar", "map"]);
  });
});

describe("wiring: the chart embed gates <ChartController /> through embedNeedsController", () => {
  // The helper is inert if the embed page stops calling it (reverting to an
  // inline `render !== "bar"` check, or dropping the gate, reintroduces the bug).
  const embed = fs.readFileSync(
    path.join(process.cwd(), "src", "pages", "embed", "chart", "[...id].astro"),
    "utf8",
  );

  it("imports embedNeedsController from chart-render", () => {
    expect(embed).toMatch(
      /import\s*\{[^}]*\bembedNeedsController\b[^}]*\}\s*from\s*["'][^"']*chart-render["']/,
    );
  });

  it("mounts <ChartController /> only behind embedNeedsController(...)", () => {
    expect(embed).toMatch(/embedNeedsController\([^)]*\)\s*&&\s*<ChartController/);
  });
});
