import { test, expect } from "@playwright/test";

test.describe("front door", () => {
  test("anonymous visitors on / are routed to /welcome/", async ({ page }) => {
    await page.goto("/");
    // index.astro's pre-paint script: signed-out → replace() to
    // /welcome/, unconditionally. This IS the intended anonymous flow.
    await page.waitForURL("**/welcome/");
    await expect(page.locator("h1").first()).toContainText(
      "Research dashboards",
    );
  });
});

test.describe("index SSR (crawler view)", () => {
  // With JS off there's no redirect — this is exactly what search
  // crawlers and link unfurlers consume from /, so the SSR'd hero +
  // tiles are worth pinning even though browsers bounce to /welcome/.
  test.use({ javaScriptEnabled: false });

  test("serves the hero and chart tiles server-side", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("h1").first()).toContainText(
      "See the economy clearly",
    );
    expect(
      await page.locator("button.chart-tile").count(),
    ).toBeGreaterThanOrEqual(5);
    await expect(page.getByText("Data unavailable")).toHaveCount(0);
  });
});
