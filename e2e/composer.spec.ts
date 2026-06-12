import { test, expect } from "@playwright/test";

// Read-only composer checks: boot + search. Nothing here signs in,
// saves, or creates alerts — anonymous browsing only.
test.describe("composer /compose/", () => {
  test("boots, loads the library, and search returns source cards", async ({
    page,
  }) => {
    await page.goto("/compose/");
    const search = page.locator("input.source-picker-search").first();
    await expect(search).toBeVisible();
    // library.json is a large manifest; first fetch can be slow.
    await search.fill("unemployment");
    const cards = page.locator(".source-picker-card");
    await expect(cards.first()).toBeVisible({ timeout: 30_000 });
    expect(await cards.count()).toBeGreaterThanOrEqual(1);
  });

  // Accessibility: the composer's modals (wireModalFocusTraps in
  // compose.astro) must keep Tab focus inside an open modal and restore
  // focus to the trigger on close. Shipped 2026-06-10 but never
  // runtime-verified (the browser froze on /compose that session); this
  // locks the behavior in against regressions. Read-only: the
  // "+ Custom chart" button opens the cc-modal with no sign-in/write.
  test("custom-chart modal traps Tab focus and restores it on close", async ({
    page,
  }) => {
    await page.goto("/compose/");
    const trigger = page.locator('[data-role="open-custom-chart"]');
    await expect(trigger).toBeVisible({ timeout: 30_000 });
    await trigger.click();

    const modal = page.locator('[data-role="cc-modal"]');
    await expect(modal).toBeVisible();

    // On open, focus lands inside the modal (it focuses its title input).
    expect(
      await modal.evaluate((m) => m.contains(document.activeElement)),
    ).toBe(true);

    // Tab from the LAST focusable must wrap back into the modal rather
    // than escape to the page behind it.
    await modal.evaluate((m) => {
      const sel =
        'a[href],button:not([disabled]),input:not([disabled]),' +
        'select:not([disabled]),textarea:not([disabled]),' +
        '[tabindex]:not([tabindex="-1"])';
      const f = [...m.querySelectorAll<HTMLElement>(sel)].filter(
        (el) => el.getClientRects().length > 0,
      );
      f[f.length - 1]?.focus();
    });
    await page.keyboard.press("Tab");
    expect(
      await modal.evaluate((m) => m.contains(document.activeElement)),
    ).toBe(true);

    // Escape closes the modal and restores focus to the trigger button.
    await page.keyboard.press("Escape");
    await expect(modal).toBeHidden();
    expect(await trigger.evaluate((t) => t === document.activeElement)).toBe(
      true,
    );
  });
});
