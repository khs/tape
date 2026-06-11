import { test, expect } from "@playwright/test";
import { expectHorizontallyCentered } from "./helpers";

// Regression suite for commit 8d12c8ae36: the map expand dialog is a
// JS-created node, so its CSS must live in a global (unscoped) style
// block. When it regressed to scoped, EVERY rule was silently dead in
// production — the dialog opened pinned to the corner and "Full screen"
// toggled a class no rule matched. No HTML-level smoke test can see
// that; only a real browser can.
test.describe("map expand dialog", () => {
  test("click-out centers; Full screen fills the viewport; exit restores", async ({
    page,
  }) => {
    await page.goto("/walkthrough/");
    const tile = page.locator(".map-tile").first();
    await tile.scrollIntoViewIfNeeded();
    // The tile canvas paints lazily — wait for a live SVG before clicking.
    await expect(tile.locator(".map-canvas svg")).toBeVisible({
      timeout: 30_000,
    });
    await tile.click();

    const dialog = page.locator("#map-expand-dialog");
    await expect(dialog).toBeVisible();
    await expect(
      dialog.locator(".map-dialog-canvas-wrap svg").last(),
    ).toBeVisible({ timeout: 30_000 });
    await expectHorizontallyCentered(page, dialog);

    // Full screen: the dialog must hit BOTH viewport boundaries
    // (100vw × 100vh by design; the map letterboxes inside).
    await dialog.locator(".map-dialog-fullscreen").click();
    await expect(
      dialog.locator(".map-dialog-canvas-wrap svg").last(),
    ).toBeVisible({ timeout: 30_000 });
    const vp = page.viewportSize()!;
    await expect
      .poll(
        async () => {
          const box = await dialog.boundingBox();
          if (!box) return "no box";
          const fillsWidth = box.width >= vp.width * 0.99;
          const fillsHeight = box.height >= vp.height * 0.99;
          return fillsWidth && fillsHeight
            ? "fills viewport"
            : `only ${Math.round(box.width)}x${Math.round(box.height)} of ${vp.width}x${vp.height}`;
        },
        { timeout: 10_000 },
      )
      .toBe("fills viewport");

    // Exit full screen: back to a centered, non-fullscreen dialog.
    await dialog.locator(".map-dialog-fullscreen").click();
    await expect(
      dialog.locator(".map-dialog-canvas-wrap svg").last(),
    ).toBeVisible({ timeout: 30_000 });
    await expect
      .poll(async () => (await dialog.boundingBox())?.width ?? 0, {
        timeout: 10_000,
      })
      .toBeLessThan(vp.width);
    await expectHorizontallyCentered(page, dialog);

    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
  });
});
