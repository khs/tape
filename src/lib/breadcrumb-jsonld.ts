/**
 * Build a schema.org BreadcrumbList object for inline JSON-LD.
 *
 * Takes an ordered list of {name, url} crumbs (site root first, current
 * page last) and returns the graph object. Emit it with:
 *
 *   <script is:inline type="application/ld+json"
 *           set:html={jsonForScript(breadcrumbList(items))} />
 *
 * Earns the breadcrumb rich result in Google SERPs, where the indexed
 * URL otherwise shows as a bare path. Uses only relative-position + name
 * + item URL, so it is not gated on any specific domain (the caller
 * passes already-absolute URLs built from canonicalOrigin()).
 */
export function breadcrumbList(
  items: ReadonlyArray<{ name: string; url: string }>,
): Record<string, unknown> {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items.map((it, i) => ({
      "@type": "ListItem",
      position: i + 1,
      name: it.name,
      item: it.url,
    })),
  };
}
