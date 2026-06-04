/**
 * Hand-curated lookup of 9800-series census-tract GEOIDs to colloquial
 * names of the named feature each tract covers.
 *
 * Census's TIGER boundary file labels every tract just "Census Tract
 * <number>" — no semantic content. For the special-purpose 9800-series
 * tracts (military bases, parks, airports, monumental land, etc.) the
 * bare number is useless to a reader: hovering on a hatched polygon
 * and reading "Census Tract 9801 — special land use (no resident
 * population, no ACS data)" doesn't tell them they're looking at the
 * Pentagon.
 *
 * This table maps a small starter set of GEOIDs to their everyday
 * names. The map tooltip uses this to label hatched tracts
 * with their recognizable identity:
 *
 *   without:  Census Tract 9801 — special land use (no resident...)
 *   with:     Arlington National Cemetery + Pentagon — special land use...
 *
 * Curation method:
 *   1. Extract every 9800-series tract's centroid from the per-state
 *      topojsons via mapshaper (-each cx=this.centroidX cy=...).
 *   2. For each tract centroid, find the nearest well-known landmark
 *      from a hand-built lat/long list. Sources: Wikipedia coordinates
 *      and OSM Nominatim queries (done one-off during curation; no
 *      runtime API). Threshold ≈ 0.05° (~3 miles) for confident
 *      matches.
 *   3. Verify the bbox of the tract overlaps the landmark's location;
 *      reject the few cases where the centroid match looked close but
 *      the landmark wasn't actually inside the tract polygon.
 *
 * Coverage today: DMV (8 entries) + a handful of nationally-recognizable
 * military bases and parks (~8 entries). 16 total. Designed to be
 * extended easily — when a new chart ships for a new region, run the
 * centroid script and add the recognizable features.
 *
 * Many landmarks don't get an entry here because they're inside
 * REGULAR (populated) census tracts, not 9800-series. Examples
 * (verified): Fort Belvoir, Fort Meade, Joint Base Andrews, Joshua
 * Tree, Yellowstone, Yosemite, Camp Pendleton, Camp Lejeune. These
 * sit in tracts that have ACS data because they have on-base housing,
 * so they're colored normally rather than hatched.
 *
 * GEOID format: state(2) + county(3) + tract(6), 11 digits total. The
 * "98" prefix on the tract portion (chars 5-6) is the special-use
 * marker.
 */
export const SPECIAL_TRACT_NAMES: Record<string, string> = {
  // ---- DC ----
  // National Mall + monumental core. Includes the Mall itself, the
  // Capitol grounds, and most of the Smithsonian buildings.
  "11001980000": "National Mall",

  // ---- Virginia ----
  // Pentagon + Arlington National Cemetery + Fort Myer. Single tract
  // covers all three; the entire space is restricted federal land.
  "51013980100": "Arlington National Cemetery + Pentagon",
  // Reagan National Airport (DCA) — direct centroid match.
  "51013980200": "Reagan National Airport (DCA)",
  // Dulles International Airport (IAD) — direct centroid match in
  // Loudoun County. The eastern approach corridor is in the
  // neighboring Fairfax tract (51059980200).
  "51107980100": "Dulles International Airport (IAD)",
  // CIA Headquarters (Langley) + George Washington Memorial Parkway
  // corridor. Direct centroid match.
  "51059980300": "CIA Headquarters (Langley)",
  // NASA Wallops Flight Facility — Eastern Shore of Virginia, on
  // Wallops Island. The bare Wallops main station + Chincoteague NWR
  // straddle two tracts; this one carries the launch facilities.
  "51001980200": "NASA Wallops Flight Facility",

  // ---- Maryland ----
  // Baltimore/Washington International (BWI) Airport — Anne Arundel
  // County, direct centroid match.
  "24003980000": "BWI Airport",
  // Assateague Island National Seashore — the Maryland portion of
  // the barrier-island park. The Virginia (Chincoteague NWR) portion
  // is in a populated tract since the visitor center is staffed.
  "24047980000": "Assateague Island National Seashore",

  // ---- National (lower confidence; centroid matches in the 0.05-0.20
  // degree range, verified against published military-base /
  // national-park boundaries) ----
  "08059980800": "Denver Federal Center",
  "12009980000": "NASA Kennedy Space Center",
  "30035980000": "Glacier National Park",
  "37051980100": "Fort Liberty (formerly Fort Bragg)",
  "48027980002": "Fort Cavazos (formerly Fort Hood)",
  "48029980002": "Joint Base San Antonio",
  "04005980000": "Grand Canyon National Park",
  "06071980100": "Twentynine Palms MCAGCC",
};

/**
 * Look up a curated colloquial name for a 9800-series tract GEOID.
 * Returns null when no entry exists; callers should fall back to the
 * topology's "Census Tract NNNN" name in that case.
 *
 * No validation on the input format — the GEOID may be 11 digits
 * (tract) or 12 (block-group) or anything else; non-matches return
 * null cleanly.
 */
export function specialTractName(geoid: string): string | null {
  return SPECIAL_TRACT_NAMES[geoid] ?? null;
}
