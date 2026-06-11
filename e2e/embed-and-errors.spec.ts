import { test, expect } from "@playwright/test";

test.describe("embed", () => {
  test("embedded chart renders an SVG", async ({ page }) => {
    await page.goto("/embed/chart/us-macro/unemployment/");
    await expect(page.locator("svg").first()).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByText("Data unavailable")).toHaveCount(0);
  });
});

test.describe("error handling", () => {
  test("/custom without a payload responds 404 (soft-404)", async ({
    page,
  }) => {
    const resp = await page.goto("/custom");
    expect(resp, "navigation should produce a response").not.toBeNull();
    expect(resp!.status()).toBe(404);
  });
});
