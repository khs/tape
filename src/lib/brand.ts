/**
 * Brand constants kept in one place so when the production URL changes from
 * the temporary Vercel hostname to the eventual custom domain, only this file
 * needs an edit. Used by both server-side renderers (OG image endpoint) and
 * the client-side chart-image exporter watermark.
 */

/**
 * The wordmark shown on share images and exported chart PNGs. Plain text,
 * no protocol — looks better as a small footer watermark than a full URL.
 */
export const SITE_BRAND_URL = "legiblemarkets.com";

/** The display name we use in titles and OG cards. */
export const SITE_BRAND_NAME = "Legible Markets";
