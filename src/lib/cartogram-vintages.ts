import { readFileSync } from "node:fs";
import { join } from "node:path";

// Server-only (build-time) helper: the list of population-vintage years for which
// a state cartogram exists, from the manifest scripts/build_cartogram.mjs writes
// (public/maps/us-states-cartogram-vintages.json). ChartMap's frontmatter bakes
// this into a data attribute so the client can snap a map's displayed vintage to
// the nearest cartogram. Memoized — the manifest doesn't change during a build.
let cache: number[] | null = null;

export function stateCartogramVintages(): number[] {
  if (cache) return cache;
  try {
    const raw = readFileSync(
      join(process.cwd(), "public", "maps", "us-states-cartogram-vintages.json"),
      "utf8",
    );
    const parsed = JSON.parse(raw);
    cache = Array.isArray(parsed) ? parsed.filter((y) => Number.isFinite(y)) : [];
  } catch {
    cache = []; // manifest absent (cartograms not built) → no vintage matching
  }
  return cache;
}
