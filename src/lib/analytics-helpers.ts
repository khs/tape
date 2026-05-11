/**
 * Client-side helpers for the Vercel-analytics custom-event payloads.
 *
 * Vercel Web Analytics caps each property value at ~256 chars, and the free
 * tier's event budget makes it expensive to spam many one-source-per-event
 * payloads. So we batch source IDs into a single comma-joined string and
 * truncate with a "+N more" suffix when the list overflows.
 *
 * 240-char budget leaves headroom under the 256 cap for safety. With typical
 * source IDs (`yahoo/ewj`, `worldbank_gdp_raw/world`) averaging ~15 chars,
 * this comfortably fits ~15 sources before truncation.
 */
const MAX_LEN = 240;

/**
 * Returns a comma-joined list of unique source IDs, truncated with a "+N
 * more" indicator if the joined string would exceed MAX_LEN. Order is
 * preserved (deterministic for reproducible aggregation), duplicates removed.
 */
export function packSourceIds(sources: readonly string[]): string {
  const seen: string[] = [];
  const dedupeSet = new Set<string>();
  for (const s of sources) {
    if (!dedupeSet.has(s)) {
      dedupeSet.add(s);
      seen.push(s);
    }
  }
  let acc = "";
  let included = 0;
  for (const s of seen) {
    const next = acc ? `${acc},${s}` : s;
    // Reserve ~16 chars for a potential "+N more" suffix on the next iter.
    if (next.length > MAX_LEN - 16 && included > 0) break;
    acc = next;
    included++;
  }
  const remaining = seen.length - included;
  if (remaining > 0) acc += `,+${remaining}more`;
  return acc;
}
