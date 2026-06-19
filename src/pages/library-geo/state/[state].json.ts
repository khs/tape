import type { APIRoute, GetStaticPaths } from "astro";
import { buildGeoBuckets } from "../../../lib/build-library-manifest";

/**
 * Per-state geo slice: the congressional-district + statewide sources for one
 * state. Loaded lazily by the composer when the user picks a state in the
 * "States & districts" chip (or a >=4-char query matches the state name), so a
 * California pick fetches ~2.5 MB instead of the 37 MB whole-geo block. See
 * src/lib/build-library-manifest.ts (buildGeoBuckets) + src/lib/library-loader.ts.
 */
export const prerender = true;

export const getStaticPaths: GetStaticPaths = async () => {
  const buckets = await buildGeoBuckets();
  return Object.keys(buckets.state).map((state) => ({ params: { state } }));
};

export const GET: APIRoute = async ({ params }) => {
  const buckets = await buildGeoBuckets();
  const sources = buckets.state[String(params.state)] ?? {};
  return new Response(JSON.stringify({ sources }), {
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "public, max-age=300",
    },
  });
};
