import { defineConfig, devices } from "@playwright/test";

// E2E suite. Runs against a DEPLOYED site (default: production) — there is
// deliberately no webServer config: the dev machine can't hold a full local
// build (CI is the build gate), so the suite is wired as a post-deploy check
// (.github/workflows/post-deploy-e2e.yml), mirroring the smoke test's
// trigger. Run locally with:
//
//   npx playwright test                                   (against prod)
//   PLAYWRIGHT_BASE_URL=https://... npx playwright test   (other target)
//
// HARD RULE: tests stay read-only against production — anonymous browsing
// only. No sign-in, no saves, no alert creation, nothing that writes.
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  retries: process.env.CI ? 2 : 1,
  reporter: process.env.CI
    ? [["list"], ["html", { open: "never" }]]
    : [["list"]],
  // Generous per-test budget: tests run over the public internet against
  // serverless cold starts + county-level topojson paints.
  timeout: 60_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL:
      process.env.PLAYWRIGHT_BASE_URL ?? "https://legible-markets.vercel.app",
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } },
    },
  ],
});
