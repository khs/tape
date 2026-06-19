import type { APIRoute } from "astro";
import { buildGeoBuckets } from "../../lib/build-library-manifest";

/**
 * County / QCEW-jurisdiction geo slice (one small file — ~35 sources). County
 * sources have no chip; they surface only via a >=4-char name query
 * (passesCountyFilter), so the composer loads this once when any such query is
 * active. See src/lib/build-library-manifest.ts + src/lib/library-loader.ts.
 */
export const prerender = true;

export const GET: APIRoute = async () => {
  const buckets = await buildGeoBuckets();
  return new Response(JSON.stringify({ sources: buckets.county }), {
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "public, max-age=300",
    },
  });
};
