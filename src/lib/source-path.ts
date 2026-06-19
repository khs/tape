/**
 * Helpers for the /source/<id>/ route, which is a `[...id]` catch-all. A
 * source ID like "ssa/oasdi_workers_per_beneficiary" must map to the path
 * "ssa/oasdi_workers_per_beneficiary" with the slash kept as a REAL path
 * separator. Two failure modes these guard against:
 *
 *  - Building the link with `encodeURIComponent(id)` turns the provider/
 *    series slash into "%2F", which the router keeps as ONE literal segment,
 *    so the page can't resolve the source ("Source not found: ssa%2Foasdi…"
 *    — the alerts "See chart" iframe shipped exactly this bug). Use
 *    `sourceIdToPath`, which encodes each SEGMENT but preserves the "/".
 *  - A page receiving an already percent-encoded id param should still
 *    resolve it; `pathToSourceId` decodes defensively. Source IDs are
 *    slug-like (no literal "%"), so decoding an already-decoded id is a
 *    no-op — making the lookup robust to however the link was built.
 */

/**
 * Build the path portion of `/source/<…>/` for a source ID, preserving the
 * provider/series slash as a path separator (encodes per-segment).
 */
export function sourceIdToPath(id: string): string {
  return id.split("/").map(encodeURIComponent).join("/");
}

/**
 * Normalize a `[...id]` route param back to a source ID, decoding a
 * percent-encoded form when present. Safe (no-op) on an already-decoded id;
 * returns the raw value unchanged if it contains a malformed escape.
 */
export function pathToSourceId(param: string): string {
  if (!param.includes("%")) return param;
  try {
    return decodeURIComponent(param);
  } catch {
    return param;
  }
}
