/**
 * Sitemap for the per-source citation pages (/source/<id>/).
 *
 * Why a custom endpoint: source pages are SSR (`prerender = false` in
 * src/pages/source/[...id].astro) because there are ~38k sources — far too many
 * to statically generate. @astrojs/sitemap only lists prerendered routes, so it
 * can't see them, and its `serialize` hook can only transform routes that
 * already exist (it can't add new URLs). Result: the citation pages — which
 * carry full JSON-LD Dataset metadata + canonical links and are built to be
 * indexable entry points — were absent from the sitemap entirely.
 *
 * This emits a standalone sitemap listing the subset of source pages that are
 * actually REFERENCED by a visible library chart — the curated, content-rich
 * ones worth crawling — rather than all ~38k (most are per-CD / per-metro
 * variants with thin standalone value). robots.txt advertises this file
 * alongside the auto-generated /sitemap-index.xml.
 *
 * Prerendered: the referenced-source set is build-time content, so this becomes
 * a static /sitemap-sources.xml at build (no per-request SSR).
 */
import type { APIRoute } from "astro";
import { getCollection } from "astro:content";
import { isVisibleChart } from "../lib/resolve-dashboard";
import { canonicalOrigin } from "../lib/site";
import { escapeHtml } from "../lib/escape-html";

export const prerender = true;

export const GET: APIRoute = async (context) => {
  const origin = canonicalOrigin({ site: context.site, url: context.url });

  // Every source referenced by a visible (non-deprecated) library chart. Map
  // charts count too — their data sources have citation pages like any other.
  const charts = await getCollection("charts");
  const ids = new Set<string>();
  for (const chart of charts) {
    if (!isVisibleChart(chart)) continue;
    for (const sid of chart.data.sources ?? []) ids.add(sid);
  }

  // Deterministic order so the generated file is byte-stable build-to-build.
  const locs = [...ids]
    .sort()
    .map((id) => `  <url><loc>${escapeHtml(`${origin}/source/${id}/`)}</loc></url>`)
    .join("\n");

  const xml =
    `<?xml version="1.0" encoding="UTF-8"?>\n` +
    `<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n` +
    `${locs}\n` +
    `</urlset>\n`;

  return new Response(xml, {
    headers: {
      "Content-Type": "application/xml; charset=utf-8",
      "Cache-Control": "public, max-age=3600",
    },
  });
};
