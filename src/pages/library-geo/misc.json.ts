import type { APIRoute } from "astro";
import { buildGeoBuckets } from "../../lib/build-library-manifest";

/**
 * Residual geo slice: any hidden-by-default source that no entity parser
 * claimed (should be ~empty). Emitted unconditionally so the client's
 * id→entity fallback (geoEntityForSourceId returning null → load misc) never
 * hits a 404. See src/lib/build-library-manifest.ts + src/lib/library-loader.ts.
 */
export const prerender = true;

export const GET: APIRoute = async () => {
  const buckets = await buildGeoBuckets();
  return new Response(JSON.stringify({ sources: buckets.misc }), {
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "public, max-age=300",
    },
  });
};
