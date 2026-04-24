import { defineConfig } from "astro/config";
import mdx from "@astrojs/mdx";
import vercel from "@astrojs/vercel";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  // `output: "static"` with an adapter = hybrid: pages default to prerender,
  // individual pages can opt into server rendering via `export const prerender = false`.
  output: "static",
  adapter: vercel(),
  integrations: [mdx()],
  vite: {
    plugins: [tailwindcss()],
  },
});
