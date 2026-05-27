/**
 * Mobile vs. desktop runtime differentiator.
 *
 * The codebase already settled on `@media (max-width: 640px)` as the
 * mobile breakpoint — it's used across Chart.astro, ChartController,
 * index.astro, welcome.astro, 404.astro, EmailSignup, the chart-
 * detail tile, etc. This module exposes the SAME breakpoint to JS
 * so behavioral differences (e.g. SourcePicker's render scheduler:
 * sync on desktop, debounced on mobile) stay in lockstep with the
 * visual breakpoint.
 *
 * Why this and not `(hover: hover) and (pointer: fine)`: that check
 * was explicitly retired in commit 80a4c16d (2026-05-23) with the
 * note "By 2026 enough laptops ship with touchscreens that 'primary
 * input is touch' is no longer a reliable mobile signal." The width
 * breakpoint cleanly captures "small screen needs the mobile
 * experience" without classifying touch-laptop power users as mobile.
 *
 * Why a constant + helper instead of inlining: any future bump of
 * the breakpoint should be a one-file change. If you bump it here,
 * also bump every CSS `@media (max-width: 640px)` — they're the
 * companion half of the same decision.
 */

/** Pixel width at and below which we consider the viewport mobile. */
export const MOBILE_BREAKPOINT_PX = 640;

/**
 * Is the current viewport at or below the mobile breakpoint?
 *
 * SSR-safe: returns `false` when `window` is undefined (build /
 * prerender contexts have no viewport, so they default to "desktop"
 * behavior — the safer choice since the desktop flow tends to be
 * the eager / less-optimized one, and SSR output isn't interactive
 * anyway).
 *
 * NOT memoized — `matchMedia.matches` is already a fast getter,
 * and callers commonly want to react to viewport resize so caching
 * here would hide that. If a hot path needs to call this many
 * times per frame, the caller should memoize per-frame.
 */
export function isMobileViewport(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT_PX}px)`).matches;
}
