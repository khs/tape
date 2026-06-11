import { test, expect } from "@playwright/test";
import { expectHorizontallyCentered } from "./helpers";

test.describe("preset dashboard /us-macro/", () => {
  test("renders sections and tiles without data errors", async ({ page }) => {
    await page.goto("/us-macro/");
    await expect(page.locator("h1")).toContainText("US Macro");
    expect(
      await page.locator("button.chart-tile").count(),
    ).toBeGreaterThanOrEqual(10);
    await expect(page.getByText("Data unavailable")).toHaveCount(0);
  });

  test("window pills switch the dashboard window", async ({ page }) => {
    await page.goto("/us-macro/");
    // us-macro's defaultDelta is 5y, so the 1y pill starts inactive.
    // Retry the click+assert pair: on a cold load the click can land
    // before the pill's listener is wired (hydration race).
    const pill = page.locator('[data-dashboard-window="1y"]').first();
    await expect(pill).toBeVisible();
    await expect(async () => {
      await pill.click();
      await expect(pill).toHaveAttribute("aria-pressed", "true", {
        timeout: 1_000,
      });
    }).toPass({ timeout: 20_000 });
  });

  test("chart tile click-out opens a centered dialog; Escape closes it", async ({
    page,
  }) => {
    await page.goto("/us-macro/");
    await page.locator("button.chart-tile").first().click();
    const dialog = page.locator("dialog.chart-dialog[open]");
    await expect(dialog).toBeVisible();
    await expectHorizontallyCentered(page, dialog);
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
  });
});

test.describe("saved dashboard /u/<slug>/ (SSR + Supabase read path)", () => {
  // The seeded walkthrough row — public-but-unlisted, stable slug.
  test("renders the walkthrough with charts and a map tile", async ({
    page,
  }) => {
    await page.goto("/u/mgdd5BpIul/");
    await expect(page.locator("h1")).toContainText("Walkthrough");
    await expect(page.locator("button.chart-tile").first()).toBeVisible();
    await expect(page.locator(".map-tile").first()).toBeVisible();
    await expect(page.getByText("Data unavailable")).toHaveCount(0);
  });
});
