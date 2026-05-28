/**
 * Canonical-origin helper.
 *
 * One place to turn the running request into the site's absolute origin
 * (scheme + host, no trailing slash) so every page builds the same
 * absolute URLs — canonical links, OG/JSON-LD URLs, and the per-source
 * citation block that a reader copies into a memo.
 *
 * Resolution order matches the rest of the app:
 *   1. `Astro.site` — set in production via astro.config's `resolveSite()`
 *      (SITE_URL → VERCEL_PROJECT_PRODUCTION_URL → VERCEL_URL). This is the
 *      stable public origin we want citations to point at.
 *   2. `Astro.url.origin` — the request origin. Used in `astro dev` (where
 *      `site` is unset) so local previews still produce working links.
 *
 * Why this exists: the source page was emitting a *relative* citation URL
 * ("Retrieved 2026-05-28 from /source/fred/cpi_yoy/") because it only had
 * `BASE_URL`. Citations must be absolute to be useful when pasted off-site.
 * Centralizing the derivation means the eventual tape.io cutover is a
 * single `SITE_URL` change, not a hunt through string concatenations.
 */

/** Minimal structural slice of `AstroGlobal` this helper needs. Keeping
 *  it narrow lets unit tests pass a plain object instead of constructing a
 *  full Astro context. `Astro` satisfies it structurally. */
export interface SiteContext {
  /** Configured public origin. `undefined` in dev where `site` is unset. */
  site?: URL | undefined;
  /** The current request URL. `.origin` is the dev fallback. */
  url: URL;
}

/**
 * Absolute site origin with no trailing slash — e.g. "https://tape.io" or
 * "http://localhost:4321". Prefer the configured `site`; fall back to the
 * request origin in dev.
 *
 * `new URL("https://tape.io").toString()` yields a trailing slash, so we
 * strip it; `URL.origin` never has one, so the strip is a harmless no-op
 * on the fallback path.
 */
export function canonicalOrigin(ctx: SiteContext): string {
  const fromSite = ctx.site?.toString();
  return (fromSite ?? ctx.url.origin).replace(/\/$/, "");
}
