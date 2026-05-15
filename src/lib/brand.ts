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
  "mailto:keller.scholl@gmail.com?subject=Legible%20Markets%20Enterprise%20Inquiry";
