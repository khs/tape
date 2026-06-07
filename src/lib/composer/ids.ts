/**
 * Inline / inline-map / derived chart-id prefixes + their predicates.
 *
 * Lifted verbatim from compose.astro's script scope (Plan 2d) so the feature
 * modules extracted from the page (share, sources-tab, cc-modal, ds-modal,
 * maps, generators) can share one definition instead of re-deriving the
 * prefixes. Pure string helpers — no DOM, store, or library coupling.
 */
export const INLINE_PREFIX = "inline:";
export const INLINEMAP_PREFIX = "inlinemap:";
export const DERIVED_PREFIX = "derived:";

export function isDerivedId(id: string): boolean {
  return id.startsWith(DERIVED_PREFIX);
}
export function isInlineId(id: string): boolean {
  return id.startsWith(INLINE_PREFIX);
}
export function isInlineMapId(id: string): boolean {
  return id.startsWith(INLINEMAP_PREFIX);
}
