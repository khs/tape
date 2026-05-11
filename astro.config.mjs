import { defineConfig } from "astro/config";
import mdx from "@astrojs/mdx";
import vercel from "@astrojs/vercel";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  // Production site URL. Used by Astro.site (for sitemap, canonical URLs,
  // og:image absolute URLs) and by anything generating links into our own
  // domain. Override via env (`SITE_URL`) when deploying to a custom domain.
  site: process.env.SITE_URL ?? "https://legiblemarkets.com",
  // `output: "static"` with an adapter = hybrid: pages default to prerender,
  // individual pages can opt into server rendering via `export const prerender = false`.
  output: "static",
  adapter: vercel(),
  integrations: [mdx()],
  vite: {
    plugins: [tailwindcss()],
  },
});
