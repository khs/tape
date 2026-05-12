import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    // Only run tests in src/lib. Astro components (.astro) need a much heavier
    // setup (HTML rendering, etc.) and we get most of the bang for the buck
    // from testing the pure-TS library code that the components consume.
    include: ["src/lib/**/*.test.ts", "tests/**/*.test.ts"],
    globals: false,
    environment: "node",
  },
  resolve: {
    // Mirror Astro's `astro:content` import shim for the small subset of tests
    // that need it. If a test reaches for astro:content we'd add a stub here.
  },
});
