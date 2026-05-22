/**
 * Auto-title derivation for charts in the composer.
 *
 * When a user picks sources for a custom chart, the title field auto-
 * fills with a sensible default derived from the source set. The
 * default keeps tracking the source set on subsequent edits IFF the
 * user hasn't typed a custom title — once they have, we stop
 * overwriting their intent.
 *
 * Two pure functions live here:
 *
 *   deriveAutoTitle(sources, op): the suggested title for a given
 *     source list + op. Single-source charts get the source's name;
 *     two-source op'd charts get "A {/,+,−} B"; everything else gets
 *     a " + "-joined list (matches the hover-merge "A + B" format so
 *     merge-built titles keep tracking on further source adds).
 *
 *   isTitleAuto(title, sources, op): "is this title still the
 *     auto-derived default?". Returns true when the title is empty
 *     (treat as "give me the default") or when it equals what
 *     deriveAutoTitle would produce right now. The composer reads
 *     this on modal open to decide whether to enable source-change
 *     title-tracking; an empty result locks the title in place.
 *
 * Pure + sync so it's easy to unit-test (see chart-title.test.ts).
 * The composer's source catalog (library.json) is passed in via the
 * `sourceLookup` parameter rather than imported, again for testability.
 */

export type ChartTitleOp = "divide" | "sum" | "diff" | null | undefined;

/** A minimal source-metadata shape for title formatting. The composer
 *  has the full library.json source object; we only need the names. */
export interface SourceForTitle {
  name?: string;
  shortName?: string;
}

/** Lookup signature the deriver uses to find source metadata. The
 *  composer wires this to the library.json source map; tests can
 *  pass a plain object. */
export type SourceLookup = (
  sourceId: string,
) => SourceForTitle | undefined;

/** Compose a "A op B" title with the canonical Unicode symbol. The
 *  diff symbol is U+2212 MINUS SIGN, not U+002D HYPHEN-MINUS — same
 *  reason chart axes use it: the typographic minus survives small font
 *  sizes that swallow the ASCII hyphen. */
function opSymbol(op: NonNullable<ChartTitleOp>): string {
  switch (op) {
    case "divide":
      return "/";
    case "sum":
      return "+";
    case "diff":
      return "−";
  }
}

/** Build the auto-title from sources + op. See module docstring for
 *  the format rules. Returns "" when no sources are picked (caller
 *  shows the input's placeholder copy instead). */
export function deriveAutoTitle(
  sources: ReadonlyArray<string>,
  op: ChartTitleOp,
  lookup: SourceLookup,
): string {
  if (sources.length === 0) return "";
  const names = sources.map((sid) => {
    const s = lookup(sid);
    // shortName first: chart titles get displayed in tight tile +
    // dialog headers, where "CPI YoY" reads better than the source's
    // longer descriptive name. Fall back to name, then to the id when
    // metadata is unavailable.
    return s?.shortName ?? s?.name ?? sid;
  });
  if (names.length === 1) return names[0];
  if (op && names.length === 2) {
    return `${names[0]} ${opSymbol(op)} ${names[1]}`;
  }
  return names.join(" + ");
}

/** Is the current title still the auto-derived default for the given
 *  sources + op? Used by the composer to decide whether subsequent
 *  source-change events should refresh the title or leave it alone.
 *  Empty title is always considered auto (the user has effectively
 *  asked for the default). */
export function isTitleAuto(
  currentTitle: string,
  sources: ReadonlyArray<string>,
  op: ChartTitleOp,
  lookup: SourceLookup,
): boolean {
  if (currentTitle === "") return true;
  return currentTitle === deriveAutoTitle(sources, op, lookup);
}
