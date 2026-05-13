import { defineConfig } from "astro/config";
import mdx from "@astrojs/mdx";
import sitemap from "@astrojs/sitemap";
import vercel from "@astrojs/vercel";
import tailwindcss from "@tailwindcss/vite";

// Production site URL. Used by Astro.site (for sitemap, canonical URLs,
// og:image absolute URLs) and anything else that needs an absolute origin.
//
// Resolution order (first set wins):
//   1. SITE_URL  - explicit override, e.g. when a custom domain ships
//   2. VERCEL_PROJECT_PRODUCTION_URL - Vercel-managed primary production URL
//      (auto-tracks once a custom domain is assigned to the project)
//   3. VERCEL_URL - per-deploy domain (e.g. preview branches, legible-markets.vercel.app)
//   4. undefined - dev fallback; BaseLayout uses request origin instead
//
// Without this, a deploy at <project>.vercel.app would bake meta-tag URLs
// pointing at a different domain (whatever default we'd hardcoded), so
// social-card crawlers would fetch from a non-existent host and get nothing.
function resolveSite() {
  if (process.env.SITE_URL) return process.env.SITE_URL;
  if (process.env.VERCEL_PROJECT_PRODUCTION_URL)
    return `https://${process.env.VERCEL_PROJECT_PRODUCTION_URL}`;
  if (process.env.VERCEL_URL) return `https://${process.env.VERCEL_URL}`;
  return undefined;
}

export default defineConfig({
  site: resolveSite(),
  // `output: "static"` with an adapter = hybrid: pages default to prerender,
  // individual pages can opt into server rendering via `export const prerender = false`.
  output: "static",
  adapter: vercel(),
  // sitemap() auto-generates /sitemap-index.xml + /sitemap-0.xml from every
  // prerendered route. SSR-only routes (/me/, /u/[slug], /custom/, /og.png,
  // /api/*) are excluded automatically — they're not in the static manifest.
  // We further exclude per-user / per-saved paths via the filter below since
  // those exist but aren't useful for search engines to crawl.
  integrations: [
    mdx(),
    sitemap({
      filter: (page) =>
        !page.includes("/me") &&
        !page.includes("/u/") &&
        !page.includes("/compose"),
    }),
  ],
  vite: {
    plugins: [tailwindcss()],
    server: {
      // Tell Vite not to watch the data tree (5,000+ JSON files that
      // never change during local dev — they're refreshed by the
      // weekly CI pipeline, not by anything that runs in `astro dev`).
      // Without this, dev-server startup balloons to >2 minutes and
      // hot-reload module fetches time out at 60s on first request.
      // Crosswalk cache is even bigger (~1GB of zips); never relevant
      // to the dev experience.
      watch: {
        ignored: [
          "**/public/data/**",
          "**/pipelines/_crosswalks/**",
          "**/pipelines/_crosswalks_cache/**",
          "**/public/data/_archive/**",
        ],
      },
    },
  },
});
