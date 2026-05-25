/**
 * Tests for the preset-classification logic. The renderer in
 * src/pages/compose.astro calls these in its hot path; the rules
 * are tight and easy to misread, so locking them down here is
 * cheap insurance.
 */
import { describe, it, expect } from "vitest";
import {
  classifyPreset,
  filterUsablePresets,
  formatPresetCount,
  type PresetDef,
} from "./generator-presets";

describe("classifyPreset", () => {
  it("returns present + total + usable for a fully-covered preset", () => {
    const preset: PresetDef = {
      label: "G7",
      codes: ["usa", "japan", "germany", "uk", "france", "italy", "canada"],
      total: 7,
    };
    const avail = new Set(preset.codes);
    expect(classifyPreset(preset, avail)).toEqual({
      present: 7,
      total: 7,
      usable: true,
    });
  });

  it("counts only entities that are in the available set", () => {
    const preset: PresetDef = {
      label: "BRICS",
      codes: ["china", "india", "brazil", "russia", "south_africa"],
      total: 5,
    };
    const avail = new Set(["china", "india", "brazil"]); // 3 of 5
    expect(classifyPreset(preset, avail)).toMatchObject({
      present: 3,
      total: 5,
    });
  });

  it("preserves total when codes is partial against intent", () => {
    // Simulates the case where Russia data was dropped from the
    // index entirely: preset.codes only has 4 items, but `total`
    // remains 5 (the canonical BRICS membership).
    const preset: PresetDef = {
      label: "BRICS",
      codes: ["china", "india", "brazil", "south_africa"],
      total: 5,
    };
    const avail = new Set(preset.codes);
    const r = classifyPreset(preset, avail);
    expect(r.present).toBe(4);
    expect(r.total).toBe(5); // not 4 — total is intent, not codes
    expect(r.usable).toBe(true); // 4 * 2 = 8 >= 5
  });

  it("falls back to codes.length when total is omitted", () => {
    // Region presets (metro / state by Census region) don't define
    // a separate total — codes IS the canonical list.
    const preset: PresetDef = {
      label: "Northeast (states)",
      codes: ["ME", "NH", "VT", "MA", "RI", "CT", "NY", "NJ", "PA"],
      // total omitted
    };
    const r = classifyPreset(preset, new Set(preset.codes));
    expect(r.total).toBe(9);
  });

  it("uses present * 2 >= total for the half-coverage rule", () => {
    const make = (present: number, total: number): PresetDef => ({
      label: "x",
      codes: Array.from({ length: present }, (_, i) => `c${i}`),
      total,
    });
    // Odd-total edge: 5-member group surfaces at 3/5, hides at 2/5
    expect(classifyPreset(make(3, 5), new Set(["c0", "c1", "c2"])).usable).toBe(true);
    expect(classifyPreset(make(2, 5), new Set(["c0", "c1"])).usable).toBe(false);
    // Even total: 4-member group at 2/4 still passes (exactly half)
    expect(classifyPreset(make(2, 4), new Set(["c0", "c1"])).usable).toBe(true);
    // 1-member at 1/1 trivially passes
    expect(classifyPreset(make(1, 1), new Set(["c0"])).usable).toBe(true);
    // Zero-overlap always fails
    expect(classifyPreset(make(0, 5), new Set()).usable).toBe(false);
  });

  it("treats codes outside availableEntities as not present", () => {
    const preset: PresetDef = {
      label: "Nordics",
      codes: ["norway", "sweden", "finland", "denmark", "iceland"],
      total: 5,
    };
    const avail = new Set(["norway", "sweden", "atlantis"]); // atlantis ignored
    expect(classifyPreset(preset, avail).present).toBe(2);
  });
});

describe("filterUsablePresets", () => {
  it("returns only presets that pass the half-coverage rule", () => {
    const presets: Record<string, PresetDef> = {
      g7: {
        label: "G7",
        codes: ["usa", "japan", "germany", "uk", "france", "italy", "canada"],
        total: 7,
      },
      brics_thin: {
        // Only 1 of 5 BRICS members available — should be dropped.
        label: "BRICS",
        codes: ["china"],
        total: 5,
      },
      nordics_half: {
        // 3 of 5 — should pass (3 * 2 = 6 >= 5)
        label: "Nordics",
        codes: ["norway", "sweden", "finland"],
        total: 5,
      },
    };
    const avail = new Set([
      "usa", "japan", "germany", "uk", "france", "italy", "canada",
      "china", "norway", "sweden", "finland",
    ]);
    const result = filterUsablePresets(presets, avail);
    const keys = result.map((p) => p.key);
    expect(keys).toContain("g7");
    expect(keys).toContain("nordics_half");
    expect(keys).not.toContain("brics_thin");
  });

  it("preserves the input dict's insertion order", () => {
    const presets: Record<string, PresetDef> = {
      first: { label: "A", codes: ["x"], total: 1 },
      second: { label: "B", codes: ["y"], total: 1 },
      third: { label: "C", codes: ["z"], total: 1 },
    };
    const result = filterUsablePresets(presets, new Set(["x", "y", "z"]));
    expect(result.map((p) => p.key)).toEqual(["first", "second", "third"]);
  });

  it("includes present + total on each emitted entry", () => {
    const presets: Record<string, PresetDef> = {
      g7: {
        label: "G7",
        codes: ["usa", "japan", "germany", "uk", "france", "italy", "canada"],
        total: 7,
      },
    };
    const avail = new Set(["usa", "japan", "germany", "uk"]); // 4 of 7
    const [r] = filterUsablePresets(presets, avail);
    expect(r).toEqual({ key: "g7", label: "G7", present: 4, total: 7 });
  });

  it("returns empty array when every preset fails the rule", () => {
    const presets: Record<string, PresetDef> = {
      g7: { label: "G7", codes: ["usa"], total: 7 }, // 1 of 7, fails
      brics: { label: "BRICS", codes: ["china", "india"], total: 5 }, // 2 of 5, fails
    };
    const result = filterUsablePresets(presets, new Set(["usa", "china", "india"]));
    expect(result).toEqual([]);
  });
});

describe("formatPresetCount", () => {
  it("renders the X/Y format the dropdown attaches to each option", () => {
    expect(formatPresetCount({ present: 4, total: 5, usable: true })).toBe(
      "(4/5)",
    );
    expect(formatPresetCount({ present: 7, total: 7, usable: true })).toBe(
      "(7/7)",
    );
    expect(formatPresetCount({ present: 0, total: 12, usable: false })).toBe(
      "(0/12)",
    );
  });
});
