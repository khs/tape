import type { APIRoute, GetStaticPaths } from "astro";
import { buildGeoBuckets } from "../../../lib/build-library-manifest";

/**
 * Per-country geo slice: the sources for one foreign country / region code.
 * Loaded lazily when the user picks an entry in the composer's "Regions and
 * countries" chip (or a >=4-char query matches the name). US-national sources
 * stay in the lean /library.json (they are visible by default), so they never
 * appear here. See src/lib/build-library-manifest.ts + src/lib/library-loader.ts.
 */
export const prerender = true;

export const getStaticPaths: GetStaticPaths = async () => {
  const buckets = await buildGeoBuckets();
  return Object.keys(buckets.country).map((code) => ({ params: { code } }));
};

export const GET: APIRoute = async ({ params }) => {
  const buckets = await buildGeoBuckets();
  const sources = buckets.country[String(params.code)] ?? {};
  return new Response(JSON.stringify({ sources }), {
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "public, max-age=300",
    },
  });
};
