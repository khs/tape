/**
 * Tests for the mobile/desktop viewport differentiator.
 *
 * The breakpoint number lives in BOTH this module AND every CSS
 * `@media (max-width: 640px)` rule in the codebase. If they drift,
 * the JS path takes different actions than the CSS layout suggests
 * the user is in. The constant test below is the canary — if it
 * fails because the constant moved, audit the CSS rules at the
 * same time.
 */
import { describe, test, expect, vi, afterEach } from "vitest";
import { MOBILE_BREAKPOINT_PX, isMobileViewport } from "./viewport";

describe("MOBILE_BREAKPOINT_PX", () => {
  test("matches the codebase-wide CSS @media breakpoint", () => {
    // CSS files use `@media (max-width: 640px)` throughout. If we
    // ever bump this, run a `grep` for `max-width: 640px` and bump
    // both at once — otherwise the JS scheduler will diverge from
    // the visual layout the user is looking at.
    expect(MOBILE_BREAKPOINT_PX).toBe(640);
  });
});

describe("isMobileViewport (SSR / no-window)", () => {
  const origWindow = globalThis.window;
  afterEach(() => {
    if (origWindow === undefined) {
      delete (globalThis as { window?: unknown }).window;
    } else {
      (globalThis as { window?: unknown }).window = origWindow;
    }
  });

  test("returns false when window is undefined", () => {
    delete (globalThis as { window?: unknown }).window;
    expect(isMobileViewport()).toBe(false);
  });
});

describe("isMobileViewport (browser-shaped)", () => {
  const origWindow = globalThis.window;
  afterEach(() => {
    if (origWindow === undefined) {
      delete (globalThis as { window?: unknown }).window;
    } else {
      (globalThis as { window?: unknown }).window = origWindow;
    }
  });

  test("returns true when matchMedia reports match", () => {
    const matchMedia = vi.fn((query: string) => ({
      matches: query === `(max-width: ${MOBILE_BREAKPOINT_PX}px)`,
      media: query,
    }));
    (globalThis as { window?: unknown }).window = { matchMedia };
    expect(isMobileViewport()).toBe(true);
    expect(matchMedia).toHaveBeenCalledWith(
      `(max-width: ${MOBILE_BREAKPOINT_PX}px)`,
    );
  });

  test("returns false when matchMedia reports no match", () => {
    const matchMedia = vi.fn(() => ({ matches: false, media: "" }));
    (globalThis as { window?: unknown }).window = { matchMedia };
    expect(isMobileViewport()).toBe(false);
  });
});
