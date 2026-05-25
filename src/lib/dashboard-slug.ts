/**
 * Custom-URL slug validation for saved dashboards.
 *
 * Used by /me/ and the home page's "Set URL" button. The renderer
 * prompts the user, then runs the typed slug through `validateSlug`;
 * on null it submits to Supabase, on a string it shows that string as
 * an alert and leaves the prompt alone.
 *
 * Rules locked in here:
 *   - 3–60 characters (avoids 1–2 char clobbering of reserved paths
 *     and keeps URLs reasonable).
 *   - Lowercase letters, digits, and dashes only.
 *   - Cannot start or end with a dash (prevents " -foo-" style URLs
 *     and avoids the rare CDN edge that 404s on leading-dash paths).
 *   - Cannot collide with a reserved path (the routes-table list
 *     below, plus the few public-file basenames the build ships).
 *
 * Extracted from src/lib/render-saved-dashboards.ts so the rules can
 * be unit-tested. The renderer imports both `RESERVED_SLUGS` (for
 * occasional debug-display use) and `validateSlug` directly.
 */

/**
 * Slugs that must NOT be claimable as a custom dashboard URL.
 *
 * Two categories:
 *   1. Route prefixes the site itself uses — claiming these as a
 *      custom dashboard would shadow the real page.
 *   2. Public-file basenames the build emits at the URL root — these
 *      live at /library.json, /favicon.ico, etc. Allowing them as
 *      dashboard slugs would create routing conflicts.
 */
export const RESERVED_SLUGS: ReadonlySet<string> = new Set([
  // Route prefixes
  "me",
  "compose",
  "custom",
  "api",
  "auth",
  "u",
  "admin",
  "settings",
  "login",
  "logout",
  "signin",
  "signout",
  // Build-emitted root paths
  "_astro",
  "library.json",
  "favicon.ico",
  "robots.txt",
  "sitemap.xml",
]);

/** Min characters for a valid slug. */
export const MIN_SLUG_LENGTH = 3;
/** Max characters for a valid slug. Keeps URLs reasonable + dodges
 *  Postgres/Index limits in the saved_dashboards.slug column. */
export const MAX_SLUG_LENGTH = 60;

/**
 * Validate a custom slug. Returns null when valid, or a user-facing
 * error string explaining the failure.
 *
 * Error copy is the source of truth — the renderer shows the string
 * verbatim in an alert(), so tweaks here change what the user sees.
 */
export function validateSlug(s: string): string | null {
  if (!s) return "Custom URL can't be empty.";
  if (s.length < MIN_SLUG_LENGTH) {
    return `Custom URL must be at least ${MIN_SLUG_LENGTH} characters.`;
  }
  if (s.length > MAX_SLUG_LENGTH) {
    return `Custom URL must be ${MAX_SLUG_LENGTH} characters or fewer.`;
  }
  // Anchored regex: starts with [a-z0-9], may have [a-z0-9-] in the
  // middle, must end with [a-z0-9]. Single-char strings only pass if
  // they're [a-z0-9] — but the length check above rejects them first.
  if (!/^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/.test(s)) {
    return "Custom URL must be lowercase letters, digits, and dashes — and can't start or end with a dash.";
  }
  if (RESERVED_SLUGS.has(s)) return `"${s}" is a reserved URL.`;
  return null;
}

/**
 * HTML-escape a string for safe injection into an `innerHTML` template.
 * The 4 entities here are the standard XSS-prevention set (no need to
 * escape "'" because templates always use double quotes).
 *
 * Lives alongside validateSlug because both are pure helpers used by
 * render-saved-dashboards.ts and both benefit from the same unit-
 * test harness.
 */
export function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
