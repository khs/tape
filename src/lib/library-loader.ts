/**
 * Shared client-side loader for the chart-library manifest.
 *
 * The lean /library.json (charts + visible-by-default sources + hint cards +
 * lookups + tagCountsByGeo, ~2 MB) is fetched once and cached on `window` so
 * every consumer — the composer page, each SourcePicker island, the alerts
 * page — reads ONE object instead of each refetching + reparsing ~40 MB.
 *
 * The heavy geo block (/library-geo.json: ~28.9k CD / state / metro / county /
 * country sources, ~37 MB) is fetched lazily by `ensureGeoSources` and
 * `Object.assign`-ed into that same shared object's `.sources`. Because every
 * consumer holds the same object reference, a geo load triggered by any one of
 * them (e.g. the user engages a geo chip in one SourcePicker) becomes visible
 * by-reference to all of them — the composer can then resolve the picked geo
 * source's metadata without its own fetch.
 *
 * See src/pages/library.json.ts + library-geo.json.ts (the split) and
 * src/lib/build-library-manifest.ts (the shared build + partition predicate).
 */

/** Minimal structural view of a library source. Deliberately has NO index
 *  signature so each consumer's richer LibrarySource type stays assignable to
 *  it (an index signature would block that). The merge only touches the map,
 *  not individual source internals. */
export interface SharedLibrarySource {
  id?: string;
  tags?: string[];
  kind?: string;
}

/** Minimal structural view of the manifest — just the `sources` map the geo
 *  merge mutates plus the split flag. No index signature, for the same
 *  assignability reason as SharedLibrarySource. */
export interface SharedLibraryPayload {
  sources?: Record<string, SharedLibrarySource>;
  /** Present + true on the post-split manifest — tells consumers a
   *  /library-geo.json companion exists and geo sources are lazy-loaded. */
  geoSplit?: boolean;
}

type LibraryWindow = Window & {
  __tapeLib?: Promise<SharedLibraryPayload>;
  /** Per-geo-entity in-flight/settled fetches, keyed by `${kind}/${code}`
   *  (or `county` / `misc`). */
  __tapeGeo?: Map<string, Promise<void>>;
  /** Entity keys whose sources were successfully merged into the shared
   *  object. Distinct from __tapeGeo so a FAILED fetch (removed from
   *  __tapeGeo so it can retry) is never mistaken for loaded. */
  __tapeGeoLoaded?: Set<string>;
};

function baseUrl(): string {
  return (import.meta.env.BASE_URL || "/").replace(/\/$/, "");
}

/**
 * Fetch (and window-cache) the lean library manifest. Rejects on a non-OK
 * response or network error — callers that prefer graceful degradation should
 * `.catch` to a `{ sources: {} }` fallback (the SourcePicker does); the
 * composer lets the rejection surface so it can show a "failed to load" notice.
 * All callers share the SAME resolved object.
 */
export function getSharedLibrary<T = SharedLibraryPayload>(): Promise<T> {
  const w = window as LibraryWindow;
  if (!w.__tapeLib) {
    w.__tapeLib = (async () => {
      const r = await fetch(`${baseUrl()}/library.json`);
      if (!r.ok) throw new Error(`library.json status=${r.status}`);
      return (await r.json()) as SharedLibraryPayload;
    })();
  }
  return w.__tapeLib as unknown as Promise<T>;
}

import { geoEntityForSourceId, type GeoEntity, type GeoEntityKind } from "./geo-entity";

function geoState(): { inflight: Map<string, Promise<void>>; loaded: Set<string> } {
  const w = window as LibraryWindow;
  if (!w.__tapeGeo) w.__tapeGeo = new Map();
  if (!w.__tapeGeoLoaded) w.__tapeGeoLoaded = new Set();
  return { inflight: w.__tapeGeo, loaded: w.__tapeGeoLoaded };
}

function entityKey(kind: GeoEntityKind, code: string): string {
  return kind === "county" ? kind : `${kind}/${code}`;
}

function entityUrl(kind: GeoEntityKind, code: string): string {
  const b = baseUrl();
  return kind === "county"
    ? `${b}/library-geo/county.json`
    : `${b}/library-geo/${kind}/${encodeURIComponent(code)}.json`;
}

/** Has this entity's slice already been merged into the shared object? */
export function isGeoEntityLoaded(kind: GeoEntityKind, code: string): boolean {
  return geoState().loaded.has(entityKey(kind, code));
}

/** Are ALL of these entities loaded? Empty list → true (nothing to wait on). */
export function allGeoEntitiesLoaded(entities: readonly GeoEntity[]): boolean {
  const { loaded } = geoState();
  return entities.every((e) => loaded.has(entityKey(e.kind, e.code)));
}

/**
 * Lazily fetch one per-entity geo slice (/library-geo/<kind>/<code>.json) and
 * merge its sources into the shared library object. Idempotent + window-cached
 * per entity, so concurrent callers (multiple SourcePicker instances, the
 * composer, alerts) share one fetch and the merge is visible by-reference to
 * all of them. NEVER rejects: on failure it logs AND drops the cache entry so
 * the next attempt retries (a transient flap must not permanently disable an
 * entity — see the review note that the old single-promise cache could stick).
 */
export function ensureGeoEntity(
  lib: SharedLibraryPayload,
  kind: GeoEntityKind,
  code: string,
): Promise<void> {
  const key = entityKey(kind, code);
  const { inflight, loaded } = geoState();
  if (loaded.has(key)) return Promise.resolve();
  const existing = inflight.get(key);
  if (existing) return existing;
  const p = (async () => {
    try {
      const r = await fetch(entityUrl(kind, code));
      if (!r.ok) throw new Error(`${entityUrl(kind, code)} status=${r.status}`);
      const data = (await r.json()) as { sources?: Record<string, SharedLibrarySource> };
      if (data.sources) {
        if (!lib.sources) lib.sources = {};
        Object.assign(lib.sources, data.sources);
      }
      loaded.add(key);
    } catch (e) {
      console.warn("[library-loader] geo entity load failed:", key, e);
      inflight.delete(key); // allow a later attempt to retry
    }
  })();
  inflight.set(key, p);
  return p;
}

/** Load several entities concurrently. Resolves once all settle (each merges
 *  or degrades on its own; the call never rejects). */
export async function ensureGeoEntities(
  lib: SharedLibraryPayload,
  entities: readonly GeoEntity[],
): Promise<void> {
  await Promise.all(entities.map((e) => ensureGeoEntity(lib, e.kind, e.code)));
}

/**
 * Ensure the slice containing a specific source id is loaded — used by the
 * composer + alerts when a saved composition / alert references a geo source
 * missing from the lean manifest. Maps id → entity via the shared resolver
 * (src/lib/geo-entity.ts), falling back to the `misc` slice when no parser
 * claims the id (mirrors the server's bucketing).
 */
export function ensureGeoForSourceId(
  lib: SharedLibraryPayload,
  id: string,
): Promise<void> {
  const e = geoEntityForSourceId(id);
  // No entity parser claims this id → it's an unplaceable geo source, which
  // the lean manifest already carries (de-geo'd, see library.json.ts). It's
  // therefore already in the shared object; nothing extra to fetch.
  if (!e) return Promise.resolve();
  return ensureGeoEntity(lib, e.kind, e.code);
}
