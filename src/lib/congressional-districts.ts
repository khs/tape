/**
 * Helpers for the composer's "Congressional district" drill-down picker.
 *
 * The composer's source-pickers (Sources tab, cc-modal, ds-modal) hide
 * congressional-district sources by default because there are ~2,200 of
 * them (435 districts × ~5 series each: USAspending federal spending +
 * ACS bachelor's-plus / median household income / population / poverty
 * count). Surfacing them at the same level as the ~150 country / sector
 * / single-name sources would drown out everything else.
 *
 * Instead, a dedicated "Congressional district" chip on each picker
 * gates them: when active, a State dropdown appears; once a state is
 * picked, a District dropdown appears; once a district is picked, only
 * that district's sources show. State-picked-but-no-district shows all
 * districts of that state, so the user can scan a state's series before
 * narrowing.
 *
 * Source-ID conventions this module recognizes:
 *   - `usaspending/district_<st>_<dst>`   (federal spending per CD)
 *   - `acs_cd/<series>_<st>_<dst>`        (ACS demographic series per CD)
 * where `<st>` is the lowercase 2-letter state code and `<dst>` is a
 * 2-character district code (`01`–`53`, `al` for at-large, `98` for DC's
 * non-voting delegate).
 *
 * The `congressional-district` tag is synthesized at library-manifest
 * build time (see `src/pages/library.json.ts`) so source YAMLs don't
 * need to be touched. The composer relies on tag-membership for the
 * filter toggle, but uses {@link parseCdSourceId} for the state /
 * district narrowing (which doesn't fit the existing AND-across-tags
 * model — you can't say "tag is `tx` AND `01`" without ambiguity, and
 * we'd rather keep the existing tag plumbing simple).
 */

/** Tag synthesized onto every congressional-district source. */
export const CD_TAG = "congressional-district";

/**
 * Tag synthesized onto every state-level source. State-level data lives
 * under the same "States & districts" drill-down chip as CDs because
 * users picking a state want to see both scopes side-by-side (a senator
 * cares about the whole state, a representative about one district, and
 * an analyst usually about both). Recognized source-ID patterns:
 *   - `usaspending/state_<st>` (federal spending per state)
 *   - `fred/state_<series>_<st>` (population, etc.)
 *   - `bls/state_<series>_<st>` (employment, unemployment)
 */
export const STATE_TAG = "us-state";

/**
 * Special district-dropdown value meaning "show this state's state-level
 * series instead of its congressional-district series". Used as the
 * district code in the composer's drill-down state when the user picks
 * "Statewide" from the District dropdown. Chosen to be impossible to
 * confuse with any real district code (no real district uses double-
 * underscore-prefixed strings).
 */
export const STATEWIDE_DISTRICT_CODE = "__state__";

/**
 * US states + DC, ordered alphabetically by display name. Codes are
 * lowercased to match the source-ID convention. DC is treated as a
 * "state" here because `district_dc_98` and `acs_cd/*_dc_98` exist
 * (the at-large delegate seat).
 */
export const US_STATES: ReadonlyArray<{ code: string; name: string }> = [
  { code: "al", name: "Alabama" },
  { code: "ak", name: "Alaska" },
  { code: "az", name: "Arizona" },
  { code: "ar", name: "Arkansas" },
  { code: "ca", name: "California" },
  { code: "co", name: "Colorado" },
  { code: "ct", name: "Connecticut" },
  { code: "de", name: "Delaware" },
  { code: "dc", name: "District of Columbia" },
  { code: "fl", name: "Florida" },
  { code: "ga", name: "Georgia" },
  { code: "hi", name: "Hawaii" },
  { code: "id", name: "Idaho" },
  { code: "il", name: "Illinois" },
  { code: "in", name: "Indiana" },
  { code: "ia", name: "Iowa" },
  { code: "ks", name: "Kansas" },
  { code: "ky", name: "Kentucky" },
  { code: "la", name: "Louisiana" },
  { code: "me", name: "Maine" },
  { code: "md", name: "Maryland" },
  { code: "ma", name: "Massachusetts" },
  { code: "mi", name: "Michigan" },
  { code: "mn", name: "Minnesota" },
  { code: "ms", name: "Mississippi" },
  { code: "mo", name: "Missouri" },
  { code: "mt", name: "Montana" },
  { code: "ne", name: "Nebraska" },
  { code: "nv", name: "Nevada" },
  { code: "nh", name: "New Hampshire" },
  { code: "nj", name: "New Jersey" },
  { code: "nm", name: "New Mexico" },
  { code: "ny", name: "New York" },
  { code: "nc", name: "North Carolina" },
  { code: "nd", name: "North Dakota" },
  { code: "oh", name: "Ohio" },
  { code: "ok", name: "Oklahoma" },
  { code: "or", name: "Oregon" },
  { code: "pa", name: "Pennsylvania" },
  { code: "ri", name: "Rhode Island" },
  { code: "sc", name: "South Carolina" },
  { code: "sd", name: "South Dakota" },
  { code: "tn", name: "Tennessee" },
  { code: "tx", name: "Texas" },
  { code: "ut", name: "Utah" },
  { code: "vt", name: "Vermont" },
  { code: "va", name: "Virginia" },
  { code: "wa", name: "Washington" },
  { code: "wv", name: "West Virginia" },
  { code: "wi", name: "Wisconsin" },
  { code: "wy", name: "Wyoming" },
];

/**
 * Set of 2-letter state codes recognized by parsers in this module. Built
 * once from US_STATES so callers can cheaply validate a candidate code.
 */
const STATE_CODE_SET = new Set(US_STATES.map((s) => s.code));

/**
 * Parse a state-level source ID into its state code, or return null if
 * the ID isn't a recognized state-level series.
 *
 * Recognized patterns:
 *   - `usaspending/state_<st>`              — federal spending per state
 *   - `fred/state_<series>_<st>`            — FRED state-level series
 *     (e.g. `fred/state_population_tx`)
 *   - `bls/state_<series>_<st>`             — BLS state-level series
 *     (e.g. `bls/state_unemployment_tx`)
 *
 * The trailing 2 chars are validated against the US_STATES table so
 * an unrelated ID that happens to end in two letters (`bls/state_foo_xy`)
 * won't false-positive.
 */
export function parseStateSourceId(id: string): { state: string } | null {
  // usaspending/state_<st> (no series segment)
  let m = id.match(/^usaspending\/state_([a-z]{2})$/);
  if (m && STATE_CODE_SET.has(m[1])) return { state: m[1] };
  // fred|bls /state_<series>_<st> — non-greedy series, anchored 2-letter
  // tail. STATE_CODE_SET filter rejects accidental matches.
  m = id.match(/^(?:fred|bls)\/state_.+_([a-z]{2})$/);
  if (m && STATE_CODE_SET.has(m[1])) return { state: m[1] };
  return null;
}

/**
 * Parse a CD source ID into its state/district components, or return
 * null if the ID isn't a congressional-district series. The exact ID
 * patterns this recognizes are documented in the module header.
 */
export function parseCdSourceId(
  id: string,
): { state: string; district: string } | null {
  // usaspending/district_<st>_<dst>
  if (id.startsWith("usaspending/district_")) {
    const m = id.match(/^usaspending\/district_([a-z]{2})_([a-z0-9]{2})$/);
    if (m) return { state: m[1], district: m[2] };
    return null;
  }
  // acs_cd/<series>_<st>_<dst>. All ACS data we carry is district-level
  // so any `acs_cd/...` ID that ends with the (state)_(dst) suffix
  // qualifies. The `[a-z0-9_]+` series component is greedy but the
  // anchored 2+2 suffix forces it to leave the last two segments.
  if (id.startsWith("acs_cd/")) {
    const m = id.match(/^acs_cd\/[a-z0-9_]+_([a-z]{2})_([a-z0-9]{2})$/);
    if (m) return { state: m[1], district: m[2] };
    return null;
  }
  return null;
}

/**
 * Human-readable district label for the dropdown:
 *   - STATEWIDE_DISTRICT_CODE → "Statewide"  (state-level series)
 *   - "al"   → "At-large"
 *   - DC 98  → "Delegate"
 *   - "01"   → "1"     (strip leading zero so districts read like the
 *                        common "TX-1" / "CA-12" naming convention)
 *   - other  → as-is
 */
export function formatDistrictLabel(state: string, district: string): string {
  if (district === STATEWIDE_DISTRICT_CODE) return "Statewide";
  if (district === "al") return "At-large";
  if (state === "dc" && district === "98") return "Delegate";
  if (/^0\d$/.test(district)) return district.slice(1);
  return district;
}

/**
 * "TX-12" / "AK-AL" / "DC-98" style short label used on CD source
 * cards so the user can see at a glance which district a source
 * belongs to without parsing the long form name.
 */
export function formatCdShortLabel(state: string, district: string): string {
  return `${state.toUpperCase()}-${district.toUpperCase()}`;
}

/**
 * Look up a state's display name from its 2-letter code. Falls back to
 * the uppercased code for codes not in the table (defensive — shouldn't
 * happen for any real CD source).
 */
export function stateNameFor(code: string): string {
  return US_STATES.find((s) => s.code === code)?.name ?? code.toUpperCase();
}
