/**
 * Preset-classification logic for the Composer's Generators tab.
 *
 * The Generators tab lets a reader pick a geography + indicator
 * template (e.g. "state population (2022)") and a SUBSET of entities
 * to chart — either "all available," a canned preset (G7 / BRICS /
 * Northeast metros / etc.), or a custom list. This module is the
 * pure-function half of the preset side.
 *
 * Extracted from src/pages/compose.astro's `renderGenPresets` so
 * the rules below can be unit-tested without a DOM. The compose
 * page imports `classifyPreset` and `filterUsablePresets` at module
 * scope and threads them into its render loop unchanged.
 *
 * Rule summary (per author requests, 2026):
 *
 *   - Half-coverage rule: a preset is only "usable" when at least
 *     half of its canonical members have data for the currently-
 *     selected template. Half here means `present * 2 >= total` —
 *     integer comparison so a 5-member group surfaces at 3/5 but
 *     hides at 2/5 cleanly.
 *
 *   - "X/Y" labels: the dropdown's option text shows
 *     "<label> (<present>/<total>)". Total is the canonical group
 *     size (G7 = 7, BRICS = 5, Top 12 metros = 12) — independent
 *     of whether all members happen to be in our data set today.
 *     Falls back to codes.length when the preset doesn't declare a
 *     separate total (the regional metro / state presets that
 *     define themselves by the live data).
 */

/**
 * Shape of a preset as it lives in the generators-index.json file.
 * `total` is optional — older presets and region-defined presets
 * (where codes IS the canonical list) omit it.
 */
export interface PresetDef {
  label: string;
  codes: readonly string[];
  /** Canonical group size. Defaults to codes.length when absent. */
  total?: number;
}

/**
 * Result of classifying one preset against a set of currently-
 * available entities. Carries the present + total counts the
 * renderer needs, plus a `usable` flag the renderer uses to filter
 * the dropdown and to decide whether the Preset radio greys out.
 */
export interface PresetClassification {
  /** How many members of this preset are present in the available set. */
  present: number;
  /** Canonical (intent) group size for this preset. */
  total: number;
  /** Whether the preset passes the half-coverage rule. */
  usable: boolean;
}

/**
 * Classify one preset against the set of entity codes the current
 * template has data for. Pure: no DOM access, no side effects.
 *
 * The half-coverage rule is `present * 2 >= total` (integer
 * comparison, avoids float-rounding on odd totals).
 */
export function classifyPreset(
  preset: PresetDef,
  availableEntities: ReadonlySet<string>,
): PresetClassification {
  const present = preset.codes.filter((c) => availableEntities.has(c)).length;
  const total = preset.total ?? preset.codes.length;
  const usable = present * 2 >= total;
  return { present, total, usable };
}

/**
 * Filter a preset dict (`{ key: PresetDef }`) down to entries the
 * renderer should actually display in the dropdown — those that
 * pass the half-coverage rule against the current template's
 * available entity set. Order preserved from the input (callers
 * rely on Map / Object insertion order for the dropdown layout).
 *
 * Returns an array of `{ key, label, present, total }` tuples
 * rather than a dict — the renderer iterates this directly into
 * <option> elements.
 */
export interface UsablePreset {
  key: string;
  label: string;
  present: number;
  total: number;
}

export function filterUsablePresets(
  presets: Record<string, PresetDef>,
  availableEntities: ReadonlySet<string>,
): UsablePreset[] {
  const out: UsablePreset[] = [];
  for (const [key, preset] of Object.entries(presets)) {
    const { present, total, usable } = classifyPreset(preset, availableEntities);
    if (usable) {
      out.push({ key, label: preset.label, present, total });
    }
  }
  return out;
}

/**
 * Format the "(present/total)" suffix attached to each option's
 * label in the dropdown. Pulled out so the renderer + this lib's
 * tests format identically.
 */
export function formatPresetCount(p: PresetClassification): string {
  return `(${p.present}/${p.total})`;
}
