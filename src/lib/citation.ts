/**
 * Citation-block builder.
 *
 * Used by the chart dialog's "Copy citation" button, the per-chart page,
 * and the per-source page (/source/<id>/). One canonical format so the
 * citation a user copies from a tile-dialog matches the citation an
 * embedder reads off the source page.
 *
 * Format choice — intentionally plain text:
 *
 *   "<chart-or-source title>." <Site brand>.
 *   Data: <providers, semicolon-separated>.
 *   Data through <YYYY-MM-DD> (when known).
 *   Retrieved <YYYY-MM-DD> from <canonical URL>.
 *
 * Not Markdown, not BibTeX. The common paste target is a memo footnote
 * or Substack body — places where rich formatting gets eaten. The block
 * reads naturally as prose when concatenated onto a single line, and
 * degrades cleanly under line-break stripping.
 */
import { SITE_BRAND_NAME } from "./brand";

export interface CitationInput {
  /** Display title — chart title for chart citations, source name for source pages. */
  title: string;
  /** One or more upstream providers ("FRED", "Yahoo Finance", "World Bank"). Empty-safe. */
  providers: string[];
  /**
   * Latest data point's date as ISO YYYY-MM-DD. Captures the data
   * vintage shown in the chart, not the retrieval moment. Optional —
   * omit on snapshot-style sources where the as-of date is encoded
   * in the title itself ("2022 ACS").
   */
  asOf?: string;
  /** Canonical URL the citation should point at. Absolute or relative. */
  url: string;
  /**
   * Today's date, ISO YYYY-MM-DD. Pass explicitly so server-rendered
   * citation blocks don't capture render-time clock skew (a Vercel
   * function rendering at 23:59 UTC would otherwise stamp tomorrow's
   * date on the citation a US-coast user reads at 19:00 local).
   */
  today: string;
  /**
   * Optional license string from provenance.license. When set, surfaces
   * as a line in the citation. Helps embedders verify they're allowed
   * to reproduce the chart.
   */
  license?: string;
}

/**
 * The "Retrieved from" URL for a CHART citation. Prefers the actual
 * dashboard the chart is being viewed on; falls back to a /custom/
 * dashboard composed of just this chart when there is no hosting
 * dashboard, so the cited link always renders the chart.
 *
 * `surface` is the chart dialog's payload surface (= the page's
 * `dashboardSlug`):
 *   "custom"            → composed /custom/?d= dashboard — the state is
 *                         already in `href` (return it verbatim; do NOT
 *                         strip the query, which is the whole dashboard).
 *   "chart"             → per-chart detail page; `href` renders exactly it.
 *   "u-<slug>"          → saved dashboard → canonical /u/<slug>/ (stable
 *                         whether viewed on its own page or the home hero).
 *   "source" | "embed" | "" → no hosting dashboard → `composeSingleChart()`
 *                         (a /custom/?d=<just this chart> URL).
 *   anything else       → a preset dashboard slug → canonical /<slug>/.
 *
 * `composeSingleChart` is a thunk so the (often-unused) encode only runs
 * on the fallback path; it returns the absolute fallback URL.
 */
export function citationRetrievalUrl(args: {
  surface: string;
  origin: string;
  href: string;
  composeSingleChart: () => string;
}): string {
  const { surface, origin, href, composeSingleChart } = args;
  if (surface === "custom" || surface === "chart") return href;
  if (surface.startsWith("u-")) return `${origin}/u/${surface.slice(2)}/`;
  if (surface && surface !== "source" && surface !== "embed") {
    return `${origin}/${surface}/`;
  }
  return composeSingleChart();
}

/** Returns the citation as a single plain-text block (joined with spaces). */
export function buildCitation(input: CitationInput): string {
  const providers = input.providers.filter(Boolean);
  const lines: (string | null)[] = [
    `"${input.title}." ${SITE_BRAND_NAME}.`,
    providers.length > 0 ? `Data: ${providers.join("; ")}.` : null,
    input.asOf ? `Data through ${input.asOf}.` : null,
    input.license ? `License: ${input.license}.` : null,
    `Retrieved ${input.today} from ${input.url}.`,
  ];
  return lines.filter((x): x is string => x !== null).join(" ");
}

/**
 * Returns the citation as an ordered array of lines suitable for
 * rendering a multi-line block in HTML. Same fields as the joined
 * version. Empty lines (missing optional fields) are filtered out.
 */
export function buildCitationLines(input: CitationInput): string[] {
  const providers = input.providers.filter(Boolean);
  const lines: (string | null)[] = [
    `"${input.title}." ${SITE_BRAND_NAME}.`,
    providers.length > 0 ? `Data: ${providers.join("; ")}.` : null,
    input.asOf ? `Data through ${input.asOf}.` : null,
    input.license ? `License: ${input.license}.` : null,
    `Retrieved ${input.today} from ${input.url}.`,
  ];
  return lines.filter((x): x is string => x !== null);
}
