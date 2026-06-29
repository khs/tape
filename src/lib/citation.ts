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

// ---------------------------------------------------------------------------
// Style-specific citations (APA 7th, Chicago 17th)
//
// The plain "Recommended" format above is Tape's own readable block. These two
// build genuinely style-compliant strings so a reader pasting into an academic
// paper / footnote gets a citation that actually follows the manual, not an
// APA-flavored approximation.
//
// Field mapping (same for both styles):
//   author      = the data PRODUCER (provenance.provider, e.g. "FRED") — the
//                 originator of the dataset, which is who you cite as author.
//   title       = the dataset name.
//   site        = SITE_BRAND_NAME ("Tape") — the portal it was accessed from,
//                 i.e. the publisher (APA) / website (Chicago).
//   year        = the data-vintage year (asOf), falling back to the retrieval
//                 year, then "n.d." Datasets that update use the version year.
//   accessed    = today (the retrieval date). Both styles want a retrieval/
//                 access date for content designed to change over time.
//   url         = canonical source URL.
//
// License is intentionally omitted — neither style includes it (it lives in the
// Recommended block and the page's license chip instead).
// ---------------------------------------------------------------------------

export type CitationStyleId = "recommended" | "apa" | "chicago";

/** One run of citation text. `italic` spans render in <em>; the manuals
 *  italicize the dataset title (APA) / the website name (Chicago). */
export interface CitationSegment {
  text: string;
  italic?: boolean;
}

export interface StyledCitation {
  id: CitationStyleId;
  /** Toggle-button label. */
  label: string;
  /** Rich segments for HTML rendering (italics where the style requires). */
  segments: CitationSegment[];
  /** Flat text for clipboard copy (no markup — italics don't survive a paste). */
  plain: string;
}

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

/**
 * Format an ISO "YYYY-MM-DD" as "Month D, YYYY". Parsed by hand (not via
 * `new Date()`) so it can't drift a day in a non-UTC runtime — the same
 * timezone trap the approximated-note date hit. Returns null on a malformed
 * input so callers can omit the date cleanly.
 */
function longDate(iso: string | undefined | null): string | null {
  if (!iso) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return null;
  const [, y, mm, dd] = m;
  const monthIdx = Number(mm) - 1;
  if (monthIdx < 0 || monthIdx > 11) return null;
  return `${MONTH_NAMES[monthIdx]} ${Number(dd)}, ${y}`;
}

/** Four-digit year out of an ISO date, or null. */
function yearOf(iso: string | undefined | null): string | null {
  if (!iso) return null;
  const m = /^(\d{4})/.exec(iso);
  return m ? m[1] : null;
}

/** Drop a single trailing period so wrapping a title in quotes / a sentence
 *  can't produce ".." (e.g. a source name that already ends in a period). */
function trimTrailingPeriod(s: string): string {
  return s.replace(/\.\s*$/, "");
}

/** APA group-author join: "A", "A & B", "A, B, & C" (serial comma + ampersand). */
function joinAuthorsApa(authors: string[]): string {
  if (authors.length <= 1) return authors[0] ?? "";
  if (authors.length === 2) return `${authors[0]} & ${authors[1]}`;
  return `${authors.slice(0, -1).join(", ")}, & ${authors[authors.length - 1]}`;
}

/** Chicago group-author join: "A", "A and B", "A, B, and C". */
function joinAuthorsChicago(authors: string[]): string {
  if (authors.length <= 1) return authors[0] ?? "";
  if (authors.length === 2) return `${authors[0]} and ${authors[1]}`;
  return `${authors.slice(0, -1).join(", ")}, and ${authors[authors.length - 1]}`;
}

function segmentsToPlain(segments: CitationSegment[]): string {
  return segments.map((s) => s.text).join("");
}

/**
 * APA 7th-edition dataset citation:
 *   Author. (Year). *Title* [Data set]. Publisher. Retrieved Month D, YYYY, from URL
 * No-author fallback moves the title to the author position. Note APA puts NO
 * period after the closing URL.
 */
export function buildApaCitation(input: CitationInput): StyledCitation {
  const authors = input.providers.filter(Boolean);
  const title = trimTrailingPeriod(input.title);
  const year = yearOf(input.asOf) ?? yearOf(input.today) ?? "n.d.";
  const retrieved = longDate(input.today);
  const retrievalClause = retrieved
    ? `Retrieved ${retrieved}, from ${input.url}`
    : `Retrieved from ${input.url}`;

  const segments: CitationSegment[] = [];
  if (authors.length > 0) {
    segments.push({ text: `${joinAuthorsApa(authors)}. (${year}). ` });
    segments.push({ text: title, italic: true });
    segments.push({ text: ` [Data set]. ${SITE_BRAND_NAME}. ${retrievalClause}` });
  } else {
    // No author → title leads, then the year.
    segments.push({ text: title, italic: true });
    segments.push({ text: ` [Data set]. (${year}). ${SITE_BRAND_NAME}. ${retrievalClause}` });
  }
  return { id: "apa", label: "APA", segments, plain: segmentsToPlain(segments) };
}

/**
 * Chicago 17th-edition (notes–bibliography) citation for an online dataset:
 *   Author. "Title." Website. Accessed Month D, YYYY. URL.
 * Title in quotation marks (period inside the quote), "Accessed" wording, and
 * a terminal period after the URL (the opposite of APA).
 *
 * Website name is set ROMAN, not italic: CMOS 17 §14.206 italicizes a site
 * name only when it's the online counterpart of a printed publication. Tape
 * has no print counterpart, so roman is the manual-correct choice (matches
 * CMOS's own "Yale University" web examples). Hence Chicago has no italics.
 */
export function buildChicagoCitation(input: CitationInput): StyledCitation {
  const authors = input.providers.filter(Boolean);
  const title = trimTrailingPeriod(input.title);
  const accessed = longDate(input.today);
  const accessedClause = accessed ? `Accessed ${accessed}. ` : "";
  const lead =
    authors.length > 0
      ? `${joinAuthorsChicago(authors)}. "${title}." `
      : `"${title}." `;

  const segments: CitationSegment[] = [
    { text: `${lead}${SITE_BRAND_NAME}. ${accessedClause}${input.url}.` },
  ];
  return { id: "chicago", label: "Chicago", segments, plain: segmentsToPlain(segments) };
}
