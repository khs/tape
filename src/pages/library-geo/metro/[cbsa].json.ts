import type { APIRoute, GetStaticPaths } from "astro";
import { buildGeoBuckets } from "../../../lib/build-library-manifest";

/**
 * Per-metro geo slice: the sources for one CBSA (~16 sources, ~20 KB). Loaded
 * lazily when the user picks a metro in the composer's "US metro areas" chip
 * (or a >=4-char query matches the metro name) — vs the 9 MB whole-metro
 * category. See src/lib/build-library-manifest.ts + src/lib/library-loader.ts.
 */
export const prerender = true;

export const getStaticPaths: GetStaticPaths = async () => {
  const buckets = await buildGeoBuckets();
  return Object.keys(buckets.metro).map((cbsa) => ({ params: { cbsa } }));
};

export const GET: APIRoute = async ({ params }) => {
  const buckets = await buildGeoBuckets();
  const sources = buckets.metro[String(params.cbsa)] ?? {};
  return new Response(JSON.stringify({ sources }), {
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "public, max-age=300",
    },
  });
};
