/**
 * Pure helpers for the choropleth year-slider's vintage discovery.
 *
 * Extracted from ChartMap.astro so the (fragile) filename-parsing and
 * multi-shard intersection logic can be unit-tested without rendering a map.
 * The map's expanded dialog offers a slider over the vintages these functions
 * return; getting the set wrong shows the wrong years or an empty/misaligned
 * slider, so it's worth locking down. The election maps (pres_margin_<year>,
 * 13 state frames / 7 county frames) lean on this heavily.
 */

/** Regex matching `<indicator>_<YYYY>.json`, capturing the 4-digit year.
 *  The indicator is regex-escaped so an indicator containing metacharacters
 *  can't widen the match (and, e.g., `pres_margin` never matches
 *  `pres_margin_county_2024.json` — the `_county` segment blocks the
 *  immediate `_<YYYY>`). */
export function indicatorVintageRe(indicator: string): RegExp {
  const esc = indicator.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`^${esc}_(\\d{4})\\.json$`);
}

/** Sorted (ascending) 4-digit vintages among `files` for `indicator`.
 *  Non-matching files (other indicators, summaries, the manifest) are ignored. */
export function pickVintages(files: string[], indicator: string): string[] {
  const re = indicatorVintageRe(indicator);
  const out: string[] = [];
  for (const f of files) {
    const m = f.match(re);
    if (m) out.push(m[1]);
  }
  return out.sort();
}

/** Collapse per-shard vintage lists (tract / block-group are sharded by
 *  state) into the slider's offered set. Normally the INTERSECTION — a year
 *  is only offered if every shard has it, so scrubbing never renders a
 *  partial-coverage map. But if any shard is entirely empty (a state we don't
 *  carry), fall back to the sorted UNION so the slider still steps through
 *  whatever exists (the renderer handles per-state gaps). Single-file geos
 *  (state / county) pass a one-element array and get that list back. */
export function combineShardVintages(perShard: string[][]): string[] {
  if (perShard.length === 0) return [];
  if (perShard.some((a) => a.length === 0)) {
    const union = new Set<string>();
    perShard.forEach((a) => a.forEach((v) => union.add(v)));
    return [...union].sort();
  }
  let acc = perShard[0];
  for (let i = 1; i < perShard.length; i++) {
    const s = new Set(perShard[i]);
    acc = acc.filter((v) => s.has(v));
  }
  return acc;
}

/** The vintage a slider at integer `index` selects, clamped into range.
 *  `vintages` must be the sorted list from the functions above. Returns null
 *  for an empty list. Clamping keeps a stale/out-of-range index (older saved
 *  dashboard, fewer vintages than before) from reading off the end. */
export function vintageAtIndex(
  vintages: readonly string[],
  index: number,
): string | null {
  if (vintages.length === 0) return null;
  const i = Math.max(0, Math.min(vintages.length - 1, Math.round(index)));
  return vintages[i];
}
