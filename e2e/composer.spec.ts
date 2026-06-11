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
});
