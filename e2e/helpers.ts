import { expect, type Locator, type Page } from "@playwright/test";

/**
 * Assert a modal is horizontally centered in the viewport (gap on the
 * left ≈ gap on the right, and neither gap is zero). This is the cheap,
 * robust form of "the dialog is not pinned to an edge" — the exact bug
 * class where Tailwind's `* { margin: 0 }` preflight defeats a native
 * <dialog>'s UA `margin: auto` centering (see commit 8d12c8ae36).
 */
export async function expectHorizontallyCentered(
  page: Page,
  dialog: Locator,
  tolerance = 30,
): Promise<void> {
  const box = await dialog.boundingBox();
  const vp = page.viewportSize();
  expect(box, "dialog should have a bounding box").not.toBeNull();
  expect(vp, "page should have a viewport").not.toBeNull();
  const leftGap = box!.x;
  const rightGap = vp!.width - (box!.x + box!.width);
  expect(
    Math.abs(leftGap - rightGap),
    `left gap ${leftGap}px vs right gap ${rightGap}px`,
  ).toBeLessThanOrEqual(tolerance);
  expect(leftGap, "dialog pinned to the left edge").toBeGreaterThan(0);
}
