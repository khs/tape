/**
 * The composer's "library" payload — the shape of /library.json (the
 * pregenerated charts + the source catalog + the metro / country indexes)
 * and the loader that fetches it.
 *
 * Extracted from compose.astro (Plan 2d). The live `library` value stays a
 * local `let` in compose.astro for now; this module owns its TYPE plus the
 * fetch, so the other extracted feature modules can import the type without
 * depending on the page module. The only outward type deps are DeltaWindow
 * and Annotation, both already shared lib modules.
 */
import type { DeltaWindow } from "../deltas";
import type { Annotation } from "../annotations";
import { getSharedLibrary } from "../library-loader";

export type LibraryChart = {
  id: string;
  title: string;
  tags: string[];
  sources: string[];
  defaultDelta?: DeltaWindow;
  // Fields needed by the promote-library-to-inline path so library
  // charts can be opened in the custom-chart modal for full editing.
  // Optional because the schema marks them all optional too — older
  // library.json snapshots may not carry them.
  normalize?: "raw" | "rebase" | "dual-axis";
  scale?: "linear" | "log";
  rightAxisSources?: string[];
  op?: "divide" | "sum" | "diff";
  blurb?: string;
  searchText?: string;
};

export type LibrarySource = {
  id: string;
  name: string;
  shortName?: string;
  description?: string;
  kind?: string;
  supportedDeltas?: DeltaWindow[];
  unit?: string;
  // Editorial annotations seeded onto a chart created from this source
  // (e.g. FEC per-district redistricting notes). Carried in library.json.
  defaultAnnotations?: Annotation[];
};

export type MetroEntry = { shortName: string; name: string };
export type CountryEntry = { name: string };

export type LibraryPayload = {
  charts: LibraryChart[];
  sources: Record<string, LibrarySource>;
  // Metros that appear in at least one source on disk. Empty/absent
  // when the metro pipelines haven't run yet — the chip stays hidden.
  metros?: Record<string, MetroEntry>;
  // The synthetic tag prefix the server attaches to metro sources.
  // Kept in the payload so the composer doesn't have to hardcode it
  // separately from the library lib.
  metroTag?: string;
  // Country / region codes (ISO3 for countries, WB region codes for
  // aggregates) present in at least one source. Empty/absent when
  // the country pipelines haven't produced any non-US country data.
  countries?: Record<string, CountryEntry>;
  // Synthetic tag prefix for country / region sources. Used for the
  // umbrella tag (`country-specific`) and per-country tags
  // (`country-specific:JPN`, etc.) the server attaches.
  countryTag?: string;
};

// `_baseUrl` is retained for call-site compatibility (compose.astro passes it
// positionally) but ignored: getSharedLibrary derives the base from
// import.meta.env.BASE_URL and, crucially, returns the SAME window-cached
// object the SourcePicker islands use. That shared reference is what lets a
// geo-block load triggered inside a picker (ensureGeoSources) become visible
// to the composer's `library.sources` without the composer fetching anything.
export async function loadLibrary(_baseUrl?: string): Promise<LibraryPayload> {
  return getSharedLibrary<LibraryPayload>();
}
