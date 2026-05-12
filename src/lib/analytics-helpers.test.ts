import { describe, it, expect } from "vitest";
import { packSourceIds } from "./analytics-helpers";

describe("packSourceIds", () => {
  it("joins a small list of unique IDs with commas", () => {
    expect(packSourceIds(["a", "b", "c"])).toBe("a,b,c");
  });

  it("preserves insertion order", () => {
    // Order matters because we use packed strings as aggregation keys
    // downstream — reshuffling them would split a single funnel into many.
    expect(packSourceIds(["c", "a", "b"])).toBe("c,a,b");
  });

  it("deduplicates repeated IDs", () => {
    expect(packSourceIds(["a", "b", "a", "c", "b"])).toBe("a,b,c");
  });

  it("returns empty string for empty input", () => {
    expect(packSourceIds([])).toBe("");
  });

  it("truncates with '+N more' when exceeding the 240-char budget", () => {
    // 20-char IDs × 20 = 400 chars + separators. Should truncate.
    const ids = Array.from({ length: 20 }, (_, i) =>
      `source_${String(i).padStart(13, "x")}`,
    );
    const out = packSourceIds(ids);
    expect(out.length).toBeLessThanOrEqual(240);
    expect(out).toMatch(/\+\d+more$/);
  });

  it("doesn't truncate a small list that fits", () => {
    expect(packSourceIds(["short", "ids"])).toBe("short,ids");
    expect(packSourceIds(["short", "ids"])).not.toMatch(/\+\d+more/);
  });
});
