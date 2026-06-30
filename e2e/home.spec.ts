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

test.describe("index static (crawler view)", () => {
  // With JS off there's no redirect — this is exactly what search
  // crawlers and link unfurlers consume from /. The home page is now a
  // prerendered featured-dashboard launcher (preset nav, no inline chart
  // tiles), so we pin the featured section that ships in that HTML.
  test.use({ javaScriptEnabled: false });

  test("serves the featured-dashboard nav server-side", async ({ page }) => {
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Featured dashboards" }),
    ).toBeVisible();
    expect(
      await page.locator("[data-role='featured-tab']").count(),
    ).toBeGreaterThanOrEqual(5);
    await expect(page.getByText("Data unavailable")).toHaveCount(0);
  });
});
