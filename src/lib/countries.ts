/**
 * Helpers for the composer's "Countries & regions" drill-down chip.
 *
 * Non-US country data (Yahoo country ETFs, World Bank country GDPs,
 * Treasury TIC foreign holdings, OECD per-country series, World Bank
 * extended deep-dives + regional aggregates) lives across many
 * pipelines but isn't relevant to the typical US-focused workflow.
 * Surfacing all of it in the default source list would drown out the
 * domestic data anyone reaching for the composer is most likely
 * looking for.
 *
 * Architecturally mirrors src/lib/congressional-districts.ts: a
 * synthetic tag (`COUNTRY_TAG`) gets injected at library.json build
 * time onto every parseable country source, the composer hides those
 * by default, and a "Countries & regions" chip with a country
 * dropdown surfaces them on demand.
 *
 * USA and the World aggregate intentionally do NOT get the tag — they
 * stay in the default list because the site's core audience is
 * US-focused and the World aggregate is widely-referenced shorthand
 * for global benchmarks.
 */

/** Tag synthesized onto every non-US country / non-US region source. */
export const COUNTRY_TAG = "country-specific";

/**
 * Special "country" dropdown value meaning "show all individual
 * countries plus regional aggregates" — same role as
 * STATEWIDE_DISTRICT_CODE in congressional-districts.ts.
 */
export const COUNTRIES_ALL_VALUE = "__all__";

// ----------------------------------------------------------------
// Country + region display registry
// ----------------------------------------------------------------

/**
 * ISO3 country codes → display names. Covers every country we touch
 * across the Yahoo country-ETF, World Bank, Treasury TIC, and OECD
 * pipelines. USA is included for reference but the parser explicitly
 * skips it so it doesn't get the COUNTRY_TAG.
 */
export const COUNTRY_REGISTRY: ReadonlyArray<{ code: string; name: string }> = [
  // G7 + major economies
  { code: "USA", name: "United States" },
  { code: "JPN", name: "Japan" },
  { code: "DEU", name: "Germany" },
  { code: "GBR", name: "United Kingdom" },
  { code: "FRA", name: "France" },
  { code: "ITA", name: "Italy" },
  { code: "CAN", name: "Canada" },
  { code: "CHN", name: "China" },
  { code: "IND", name: "India" },
  { code: "BRA", name: "Brazil" },
  { code: "RUS", name: "Russia" },
  { code: "AUS", name: "Australia" },
  { code: "MEX", name: "Mexico" },
  { code: "KOR", name: "South Korea" },
  // Other OECD members
  { code: "AUT", name: "Austria" },
  { code: "BEL", name: "Belgium" },
  { code: "CHE", name: "Switzerland" },
  { code: "CHL", name: "Chile" },
  { code: "COL", name: "Colombia" },
  { code: "CRI", name: "Costa Rica" },
  { code: "CZE", name: "Czechia" },
  { code: "DNK", name: "Denmark" },
  { code: "ESP", name: "Spain" },
  { code: "EST", name: "Estonia" },
  { code: "FIN", name: "Finland" },
  { code: "GRC", name: "Greece" },
  { code: "HUN", name: "Hungary" },
  { code: "IRL", name: "Ireland" },
  { code: "ISL", name: "Iceland" },
  { code: "ISR", name: "Israel" },
  { code: "LTU", name: "Lithuania" },
  { code: "LUX", name: "Luxembourg" },
  { code: "LVA", name: "Latvia" },
  { code: "NLD", name: "Netherlands" },
  { code: "NOR", name: "Norway" },
  { code: "NZL", name: "New Zealand" },
  { code: "POL", name: "Poland" },
  { code: "PRT", name: "Portugal" },
  { code: "SVK", name: "Slovakia" },
  { code: "SVN", name: "Slovenia" },
  { code: "SWE", name: "Sweden" },
  { code: "TUR", name: "Türkiye" },
  // Non-OECD but tracked via Treasury TIC + other pipelines
  { code: "ARE", name: "United Arab Emirates" },
  { code: "BMU", name: "Bermuda" },
  { code: "CYM", name: "Cayman Islands" },
  { code: "HKG", name: "Hong Kong" },
  { code: "KWT", name: "Kuwait" },
  { code: "PER", name: "Peru" },
  { code: "PHL", name: "Philippines" },
  { code: "SAU", name: "Saudi Arabia" },
  { code: "SGP", name: "Singapore" },
  { code: "SLV", name: "El Salvador" },
  { code: "THA", name: "Thailand" },
  { code: "TWN", name: "Taiwan" },
  { code: "ZAF", name: "South Africa" },
];

const COUNTRY_NAME_BY_CODE: Record<string, string> = Object.fromEntries(
  COUNTRY_REGISTRY.map((c) => [c.code, c.name]),
);

/**
 * Regional aggregates published by the World Bank (worldbank_extended
 * pipeline). Treated as "country-like entities" in the composer's
 * chip drill-down so users can filter to e.g. "Sub-Saharan Africa" the
 * same way they filter to a single country.
 */
export const REGION_REGISTRY: ReadonlyArray<{ code: string; name: string }> = [
  { code: "SSF", name: "Sub-Saharan Africa" },
  { code: "EUU", name: "European Union" },
  { code: "ECS", name: "Europe & Central Asia" },
  { code: "LCN", name: "Latin America & Caribbean" },
  { code: "MEA", name: "Middle East & North Africa" },
  { code: "NAC", name: "North America" },
  { code: "SAS", name: "South Asia" },
  { code: "EAS", name: "East Asia & Pacific" },
];

const REGION_NAME_BY_CODE: Record<string, string> = Object.fromEntries(
  REGION_REGISTRY.map((r) => [r.code, r.name]),
);

// ----------------------------------------------------------------
// Per-pipeline ID parsers
// ----------------------------------------------------------------

/**
 * Yahoo country-ETF tickers → ISO3 codes. Used for two pipelines that
 * key off the same ETF symbol: yahoo/<ticker> (raw daily price) and
 * countries_relative/<ticker> (the country ETF / VT ratio derivation).
 */
const ETF_TO_COUNTRY: Record<string, string> = {
  EWA: "AUS",
  EWC: "CAN",
  EWG: "DEU",
  EWJ: "JPN",
  EWU: "GBR",
  EWW: "MEX",
  EWY: "KOR",
  EWZ: "BRA",
  FXI: "CHN",
  INDA: "IND",
};

/**
 * Treasury TIC source slug → ISO3 code. The TIC pipeline lowercases +
 * underscore-joins country names, so e.g. "United Kingdom" → "uk".
 */
const TIC_SLUG_TO_COUNTRY: Record<string, string> = {
  japan: "JPN",
  uk: "GBR",
  china: "CHN",
  belgium: "BEL",
  canada: "CAN",
  luxembourg: "LUX",
  cayman_islands: "CYM",
  france: "FRA",
  ireland: "IRL",
  taiwan: "TWN",
  switzerland: "CHE",
  singapore: "SGP",
  hong_kong: "HKG",
  norway: "NOR",
  india: "IND",
  brazil: "BRA",
  saudi_arabia: "SAU",
  south_korea: "KOR",
  germany: "DEU",
  mexico: "MEX",
  netherlands: "NLD",
  australia: "AUS",
  sweden: "SWE",
  israel: "ISR",
  spain: "ESP",
  italy: "ITA",
  bermuda: "BMU",
  philippines: "PHL",
  uae: "ARE",
  thailand: "THA",
  kuwait: "KWT",
  poland: "POL",
  chile: "CHL",
  colombia: "COL",
  peru: "PER",
  el_salvador: "SLV",
};

/**
 * worldbank_gdp + worldbank_gdp_raw source slugs → ISO3 codes. The
 * pipeline writes lowercase country name slugs (australia, japan, etc.)
 * for the source-YAML side, with "usa" and "world" as special cases.
 */
const WB_GDP_SLUG_TO_COUNTRY: Record<string, string> = {
  australia: "AUS",
  brazil: "BRA",
  canada: "CAN",
  china: "CHN",
  germany: "DEU",
  india: "IND",
  japan: "JPN",
  mexico: "MEX",
  south_korea: "KOR",
  uk: "GBR",
};

/**
 * worldbank_extended entity slugs → codes (countries OR region codes).
 * Source IDs in that pipeline look like:
 *   worldbank_extended/gdp_current_usd_china
 *   worldbank_extended/population_africa_ssf
 *   worldbank_extended/life_expectancy_europe_eu
 * The trailing entity slug is one of these keys.
 */
const WB_EXTENDED_ENTITY_SLUG: Record<string, string> = {
  china: "CHN",
  africa_ssf: "SSF",
  europe_eu: "EUU",
  europe_central_asia: "ECS",
  latam: "LCN",
  mena: "MEA",
  north_america: "NAC",
  south_asia: "SAS",
  east_asia_pacific: "EAS",
};

/**
 * Parse a source ID to determine whether it's a country / region
 * source, and which country / region it represents. Returns null for
 * unrecognized IDs and for USA + World (those stay in the default
 * source list, not hidden behind the chip).
 */
export function parseCountrySourceId(
  id: string,
): { code: string; name: string } | null {
  // yahoo/<TICKER> for country ETFs.
  let m = id.match(/^yahoo\/([A-Z]+)$/);
  if (m) {
    const code = ETF_TO_COUNTRY[m[1]];
    if (code) return { code, name: COUNTRY_NAME_BY_CODE[code] ?? code };
  }
  // countries_relative/<TICKER> — same ETF ticker convention.
  m = id.match(/^countries_relative\/([A-Z]+)$/);
  if (m) {
    const code = ETF_TO_COUNTRY[m[1]];
    if (code) return { code, name: COUNTRY_NAME_BY_CODE[code] ?? code };
  }
  // worldbank_gdp/<slug> and worldbank_gdp_raw/<slug>. USA + world are
  // skipped (stay in default list).
  m = id.match(/^worldbank_gdp(?:_raw)?\/(\w+)$/);
  if (m) {
    const slug = m[1];
    if (slug === "usa" || slug === "world") return null;
    const code = WB_GDP_SLUG_TO_COUNTRY[slug];
    if (code) return { code, name: COUNTRY_NAME_BY_CODE[code] ?? code };
  }
  // treasury_tic/<slug>. grand_total is an aggregate, not a country —
  // skip so it stays in the default list as a "world" indicator.
  m = id.match(/^treasury_tic\/(\w+)$/);
  if (m) {
    const slug = m[1];
    if (slug === "grand_total") return null;
    const code = TIC_SLUG_TO_COUNTRY[slug];
    if (code) return { code, name: COUNTRY_NAME_BY_CODE[code] ?? code };
  }
  // oecd/<iso3>_<series>. The first 3 chars (lowercased) of the slug
  // are the ISO3 country code. USA is excluded.
  m = id.match(/^oecd\/([a-z]{3})_/);
  if (m) {
    const iso3 = m[1].toUpperCase();
    if (iso3 === "USA") return null;
    if (COUNTRY_NAME_BY_CODE[iso3]) {
      return { code: iso3, name: COUNTRY_NAME_BY_CODE[iso3] };
    }
  }
  // worldbank_extended/<indicator>_<entity>. Match against the
  // entity-slug suffix table.
  m = id.match(/^worldbank_extended\/(.+)$/);
  if (m) {
    const slug = m[1];
    for (const [entitySlug, code] of Object.entries(WB_EXTENDED_ENTITY_SLUG)) {
      if (slug.endsWith(`_${entitySlug}`)) {
        const name =
          COUNTRY_NAME_BY_CODE[code] ?? REGION_NAME_BY_CODE[code] ?? code;
        return { code, name };
      }
    }
  }
  return null;
}

/**
 * Display-name lookup. Handles country ISO3s + region codes.
 * Falls back to the code itself if unrecognized.
 */
export function countryNameFor(code: string): string {
  return COUNTRY_NAME_BY_CODE[code] ?? REGION_NAME_BY_CODE[code] ?? code;
}

/**
 * Returns true if the given code is a regional aggregate rather than a
 * single country. Used by the dropdown renderer to optionally style
 * regions differently from individual countries.
 */
export function isRegionCode(code: string): boolean {
  return code in REGION_NAME_BY_CODE;
}
