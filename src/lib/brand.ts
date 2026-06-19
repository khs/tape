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
 * Where the "Ask about enterprise" CTA points — a Notion form or
 * similar lightweight intake surface.
 *
 * 2026-05-31: swapped from a mailto placeholder to Keller's Calendly.
 * Patrick-McKenzie-style: don't make prospects email-and-wait when
 * you can give them a 30-minute slot they can self-book.
 *
 * Used by /enterprise/, the /me/ account section, and the footer link
 * — keeping the URL central means one edit when the link moves.
 */
export const ENTERPRISE_INQUIRY_URL =
  "https://calendly.com/keller-scholl/30min";

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
 * DEPRECATED (2026-06-19): the /me/ + /about/ "last updated" stamps now use
 * the BUILD/deploy date (computed at prerender time, so it auto-advances
 * every deploy and can't go stale). This constant is no longer rendered
 * anywhere — kept only for the changelog notes below. Don't wire new UI to
 * it; there is nothing to hand-bump.
 */
export const LAST_FEATURE_UPDATE = "2026-05-29";
// 2026-05-21 covered: smart-dispatch alert UX (acknowledge,
// auto-pause), the request-fallback + Unicode-minus polish, the
// walkthrough wiring, the US row added to Countries vs. world, the
// `render: "bar"` snapshot chart type (with `barOrientation` /
// `barSort` / `barAsOf` knobs), and four new walkthrough sections
// (many-lines-on-one-axis, annotations + period shading, bar
// snapshots).
// 2026-05-22 adds: every signed-in user now gets a Walkthrough row
// in their /me/ list that is a LIVE reference to /walkthrough/
// (`presetRef` on the saved row, resolved at render time), so
// updates to the canonical walkthrough propagate automatically.
// Bump again on the next user-visible feature.

/**
 * Slug of the walkthrough preset dashboard. Lives at /walkthrough/
 * and is also auto-saved as "Tutorial" the first time a user signs
 * in. Centralized here so the home page + /me/ link can change in
 * lockstep if the slug ever moves.
 */
export const WALKTHROUGH_DASHBOARD_SLUG = "walkthrough";

/**
 * localStorage key for the user's pinned default-dashboard slug.
 *
 * Used by index.astro (the redirect pre-paint + the in-page hero)
 * and u/[slug].astro (the unpin button + the "pinned home view"
 * notice). One typo on either side silently breaks the pin
 * round-trip — keeping the literal in one place enforces parity.
 */
export const DEFAULT_DASHBOARD_SLUG_KEY = "tape:default-dashboard-slug";
