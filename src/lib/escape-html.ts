/**
 * Canonical HTML-escaper — the single source of truth for escaping strings
 * injected into innerHTML templates and HTML attributes.
 *
 * Escapes all FIVE XSS-relevant characters, including the apostrophe (`'`), so
 * it is correct for BOTH double- and single-quoted attribute contexts. Several
 * former per-file copies escaped only four (omitting `'`) on the assumption
 * that templates always use double quotes — true today, but a latent gap the
 * moment someone writes a single-quoted attribute. Consolidating on the 5-char
 * version closes that class of bug everywhere at once.
 *
 * Every former copy (dashboard-slug, markdown, BaseLayout, SourcePicker,
 * ChartController, compose, alerts, me/diagnostics) now imports from here.
 */
export function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
