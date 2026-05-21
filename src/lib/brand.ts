/**
 * Brand constants kept in one place so when the production URL changes from
 * the temporary Vercel hostname to the eventual custom domain, only this file
 * needs an edit. Used by both server-side renderers (OG image endpoint) and
 * the client-side chart-image exporter watermark.
 */

/**
 * The wordmark shown on share images and exported chart PNGs. Plain text,
 * no protocol — looks better as a small footer watermark than a full URL.
 * Update when the production custom domain ships.
 */
export const SITE_BRAND_URL = "tape.io";

/** The display name we use in titles and OG cards. */
export const SITE_BRAND_NAME = "Tape";

/**
 * Where the "Inquire about enterprise" CTA points — a Notion form or
 * similar lightweight intake surface. Swap this string when the real
 * intake URL is ready; falls back to a mailto so the link is never
 * dead while the form is being set up.
 *
 * Used by /enterprise/, the /me/ account section, and the footer link
 * — keeping the URL central means one edit when the form moves.
 */
export const ENTERPRISE_INQUIRY_URL =
  "mailto:keller.scholl@gmail.com?subject=Tape%20Enterprise%20Inquiry";

/**
 * Date of the most recent user-visible feature ship.
 *
 * Surfaced under the Account section on /me/ and the home page as
 * "Tape was last updated <date>" so returning visitors can tell at a
 * glance whether anything new is worth looking at. Pair the bump with
 * a corresponding edit to the walkthrough dashboard (src/content/
 * dashboards/walkthrough.mdx) so the walkthrough always exercises the
 * latest feature set.
 *
 * Format: ISO YYYY-MM-DD (no time, no timezone — site-wide it's
 * displayed via toLocaleDateString in en-US so the user sees their
 * locale's date convention).
 *
 * Bump-protocol: whenever you ship a feature the user would want to
 * see exercised in the walkthrough, edit this constant + add the
 * feature to the walkthrough dashboard in the same commit.
 */
export const LAST_FEATURE_UPDATE = "2026-05-21";
// Note: the May 21 date covers the smart-dispatch alert UX (acknowledge,
// auto-pause), the request-fallback + Unicode-minus polish, the
// walkthrough wiring, and the US row added to Countries vs. world.
// Bump again on the next user-visible feature.

/**
 * Slug of the walkthrough preset dashboard. Lives at /walkthrough/
 * and is also auto-saved as "Tutorial" the first time a user signs
 * in. Centralized here so the home page + /me/ link can change in
 * lockstep if the slug ever moves.
 */
export const WALKTHROUGH_DASHBOARD_SLUG = "walkthrough";
