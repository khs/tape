import { defineConfig } from "astro/config";
import mdx from "@astrojs/mdx";
import sitemap from "@astrojs/sitemap";
import vercel from "@astrojs/vercel";
import tailwindcss from "@tailwindcss/vite";
import { rm, stat } from "node:fs/promises";
import path from "node:path";

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

// Bake build metadata into the client bundle so the admin diagnostic
// page can report which commit + environment is actually running.
// Astro exposes any `PUBLIC_*` env var to client code via
// `import.meta.env.PUBLIC_*`; we set them on process.env here so the
// values are read once at build time, not per request.
//
// VERCEL_GIT_COMMIT_SHA + VERCEL_ENV are populated by Vercel during
// every build. Locally they're unset, so the fallbacks read "dev" so
// the diagnostic report still has SOMETHING to show.
process.env.PUBLIC_BUILD_SHA =
  process.env.VERCEL_GIT_COMMIT_SHA ?? "dev";
process.env.PUBLIC_BUILD_ENV =
  process.env.VERCEL_ENV ?? "dev";
process.env.PUBLIC_BUILD_TIME = new Date().toISOString();

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
    // Strip public/data/ out of the Vercel SSR function bundle. The
    // node-file-tracer that ships with @astrojs/vercel sees the
    // fs.readFileSync(process.cwd() + "/public/" + ...) calls in
    // load-data.ts and conservatively bundles the whole public/data
    // tree into the function (~290MB). That's redundant with the
    // static-assets copy of the same files (served from the same
    // deployment's CDN) AND blows past Vercel's 250MB serverless-
    // function size limit.
    //
    // load-data.ts is now async and falls back to fetch() against the
    // deployment's static assets when fs.readFileSync ENOENTs at
    // runtime, so deleting these files from the bundle is safe.
    //
    // The adapter's own `excludeFiles` option only accepts literal
    // file paths (one entry per file), not globs — useless for a
    // 5,000-file tree. So we do the strip in a build:done hook.
    {
      name: "strip-data-from-function",
      hooks: {
        "astro:build:done": async ({ logger }) => {
          // .vercel/output/functions/_render.func/public/data is the
          // only path we know we want to drop. If a future Vercel
          // adapter version changes the function folder name, the
          // rm-with-force will no-op silently rather than crash.
          const projectRoot = process.cwd();
          const candidates = [
            path.join(projectRoot, ".vercel/output/functions/_render.func/public/data"),
            path.join(projectRoot, ".vercel/output/functions/_render.func/pipelines"),
          ];
          for (const target of candidates) {
            try {
              const s = await stat(target);
              if (!s.isDirectory()) continue;
              await rm(target, { recursive: true, force: true });
              logger.info(`stripped from function bundle: ${path.relative(projectRoot, target)}`);
            } catch (e) {
              // ENOENT is the expected case when the path simply
              // wasn't bundled this time — nothing to strip.
              if (e && e.code !== "ENOENT") {
                logger.warn(`could not strip ${target}: ${e}`);
              }
            }
          }
        },
      },
    },
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
