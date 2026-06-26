import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { resolveTileNoteMeta } from "./tile-note";

const ctx = {
  inlineMaps: { cr451EKd: { title: "Foreign-born share by county" } },
  inlineCharts: { ab12: { title: "My custom ratio" } },
  libraryCharts: [{ id: "us-macro/cpi", title: "Consumer Price Index" }],
};

describe("resolveTileNoteMeta", () => {
  it("inline MAP: resolves the real title from inlineMaps + flags it a map (the reported bug)", () => {
    const m = resolveTileNoteMeta("inlinemap:cr451EKd", ctx);
    expect(m.title).toBe("Foreign-born share by county");
    expect(m.isMap).toBe(true);
    expect(m.noun).toBe("map");
    // The bug was surfacing the raw ref as the "default title".
    expect(m.title).not.toContain("inlinemap:");
  });

  it("inline CHART: resolves the title from inlineCharts + noun 'chart'", () => {
    const m = resolveTileNoteMeta("inline:ab12", ctx);
    expect(m.title).toBe("My custom ratio");
    expect(m.isMap).toBe(false);
    expect(m.noun).toBe("chart");
  });

  it("library chart: resolves the catalog title + noun 'chart'", () => {
    const m = resolveTileNoteMeta("us-macro/cpi", ctx);
    expect(m.title).toBe("Consumer Price Index");
    expect(m.isMap).toBe(false);
    expect(m.noun).toBe("chart");
  });

  it("class: when its entry exists, a ref NEVER surfaces the raw id as the title", () => {
    expect(resolveTileNoteMeta("inlinemap:cr451EKd", ctx).title).not.toMatch(/^inlinemap:/);
    expect(resolveTileNoteMeta("inline:ab12", ctx).title).not.toMatch(/^inline:/);
    expect(resolveTileNoteMeta("us-macro/cpi", ctx).title).not.toBe("us-macro/cpi");
  });

  it("class: an inlinemap: ref is labeled a map even when the entry is missing", () => {
    // Keeps the modal copy ("Edit map note") correct for a dangling ref.
    const missing = resolveTileNoteMeta("inlinemap:gone", { inlineMaps: {} });
    expect(missing.isMap).toBe(true);
    expect(missing.noun).toBe("map");
  });

  it("falls back to the ref only as a last resort (no entry found)", () => {
    expect(resolveTileNoteMeta("inlinemap:gone", {}).title).toBe("inlinemap:gone");
    expect(resolveTileNoteMeta("inline:gone", {}).title).toBe("inline:gone");
    expect(resolveTileNoteMeta("unknown/chart", {}).title).toBe("unknown/chart");
  });

  it("handles undefined context fields without throwing", () => {
    expect(() => resolveTileNoteMeta("inlinemap:x", {})).not.toThrow();
    expect(resolveTileNoteMeta("inline:x", { inlineCharts: undefined }).title).toBe("inline:x");
    expect(resolveTileNoteMeta("lib/x", { libraryCharts: undefined }).title).toBe("lib/x");
  });
});

describe("wiring: the composer note modal uses resolveTileNoteMeta", () => {
  // Guards against reverting to the inline `libChart?.title ?? chartId` lookup
  // that surfaced the raw ref and always said "chart".
  const compose = fs.readFileSync(
    path.join(process.cwd(), "src", "pages", "compose.astro"),
    "utf8",
  );

  it("imports resolveTileNoteMeta from composer/tile-note", () => {
    expect(compose).toMatch(
      /import\s*\{[^}]*\bresolveTileNoteMeta\b[^}]*\}\s*from\s*["'][^"']*tile-note["']/,
    );
  });

  it("calls it to populate the note modal", () => {
    expect(compose).toMatch(/resolveTileNoteMeta\(/);
  });
});
