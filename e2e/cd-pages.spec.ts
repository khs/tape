import { test, expect } from "@playwright/test";

// Congressional-district landing pages (prerendered, one per current
// district). VA-08 is the canonical specimen — it also has a hand-built
// preset dashboard (va-08.mdx) so its data is battle-tested.
test.describe("CD landing page /cd/va-08/", () => {
  test("renders the district dashboard with healthy tiles", async ({
    page,
  }) => {
    await page.goto("/cd/va-08/");
    await expect(page.locator("h1")).toContainText("VA-08");
    expect(
      await page.locator("button.chart-tile").count(),
    ).toBeGreaterThanOrEqual(8);
    await expect(page.getByText("Data unavailable")).toHaveCount(0);
    // Sibling-district nav interlinks the state's other pages.
    expect(
      await page.locator(".cd-siblings-list a").count(),
    ).toBeGreaterThanOrEqual(1);
  });

  test("defunct pre-2020-census districts have no page", async ({ page }) => {
    const resp = await page.goto("/cd/ca-53/");
    expect(resp, "navigation should produce a response").not.toBeNull();
    expect(resp!.status()).toBe(404);
  });
});
