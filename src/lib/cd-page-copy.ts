/**
 * Copy for the /cd/<district>/ landing pages.
 *
 * KELLER WRITES THE BLURBS. Per his explicit direction, the per-page
 * prose is NOT generated: there are exactly two hand-written markdown
 * blocks — one for districts in multi-district states, one for
 * single-district (at-large) states — slotted into every page. While a
 * blurb is an empty string the page simply renders without that block,
 * so the route can ship before the copy lands.
 *
 * Markdown subset per src/lib/markdown.ts. The tokens {{SHORT}} (e.g.
 * "VA-08") and {{LONG}} (e.g. "Virginia's 8th congressional district")
 * are replaced before rendering, so the constant text can reference the
 * district naturally. {{COMPOSER_URL}} expands to the page's build-time
 * composer link (/compose/?d=<encoded state>) with this district's
 * charts pre-entered — base64url payload, so it's safe inside a
 * markdown [text](url) construct.
 */

/** Blurb for districts in multi-district states (e.g. VA-08). */
export const CD_BLURB_MULTI_DISTRICT =
  "This is the area that is currently {{LONG}} over time: no sudden " +
  "jumps because of redistricting. The American Community Survey " +
  "publishes five-year rolling estimates, so this is better for " +
  "tracking slow changes than dramatic shifts. To put {{SHORT}} beside " +
  "other districts, states, or metros, or add indicators this page " +
  "leaves out, open it in [the composer]({{COMPOSER_URL}}).";

/** Blurb for at-large districts (single-district states, e.g. WY-AL). */
export const CD_BLURB_AT_LARGE = "";

/** Substitute the district tokens into a blurb. */
export function fillCdBlurb(
  blurb: string,
  short: string,
  long: string,
  composerUrl: string,
): string {
  return blurb
    .replaceAll("{{SHORT}}", short)
    .replaceAll("{{LONG}}", long)
    .replaceAll("{{COMPOSER_URL}}", composerUrl);
}

/**
 * <title> for the landing page. Template-computed (counts + names),
 * no generated prose.
 */
export function cdPageTitle(short: string): string {
  return `${short} — economic & demographic dashboard — Tape`;
}

/**
 * Meta description. Names the headline indicators + the count of the
 * rest; all computed.
 */
export function cdMetaDescription(
  short: string,
  long: string,
  indicatorCount: number,
): string {
  return (
    `Median household income, home values, education, and ` +
    `${indicatorCount} more indicators for ${long} (${short}), ` +
    `charted from Census ACS data. Citable, embeddable, and updated ` +
    `with each ACS release.`
  );
}
