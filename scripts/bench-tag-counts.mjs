// Benchmark: how long would it take to make tag-chip counts also
// react to the 4-char unlock-by-name pattern (typing "virgin" surfaces
// VA-tagged sources)?
//
// The proposed runtime would walk every source on every keystroke
// once the query crosses 4 chars, applying the same passes*Filter
// logic the picker already uses. This script measures that cost
// against the real production library.json so we know whether it's
// safe to ship synchronously or needs a debounce / web-worker.
//
// Runs against dist/client/library.json (built artifact) — closest
// possible match to what users actually load.
//
// NOTE: since the lean/geo split (src/lib/build-library-manifest.ts),
// dist/client/library.json is the LEAN slice (~visible-by-default sources
// only); the ~28.9k hidden geo sources live in per-entity files under
// dist/client/library-geo/. So this now measures the lean-walk cost, not the
// full post-geo-load set. To benchmark the worst case, merge the geo slices
// into the source map first (or point LIB_PATH at a concatenation).
//
// Usage:  node scripts/bench-tag-counts.mjs
import { readFileSync } from "node:fs";
import { performance } from "node:perf_hooks";

const LIB_PATH = "dist/client/library.json";
const ITERATIONS = 200; // per scenario
const WARMUP = 20;

// Constants — mirror the runtime values in src/lib/.
const METRO_TAG = "metro";
const COUNTRY_TAG = "country-specific";
const CD_TAG = "congressional-district";
const STATE_TAG = "us-state";
const COUNTY_TAG = "us-county";
const UNLOCK_MIN_CHARS = 4;

// Hardcoded US_STATES name list (just the names we need for unlock).
// In the runtime this comes from src/lib/congressional-districts.ts;
// here we hardcode a representative subset matching the alphabetical
// loop the runtime does. For the benchmark we only need the loop
// shape + comparable string lengths.
const US_STATE_NAMES = [
  "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
  "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
  "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana",
  "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota",
  "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
  "New Hampshire", "New Jersey", "New Mexico", "New York",
  "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon",
  "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota",
  "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington",
  "West Virginia", "Wisconsin", "Wyoming",
];

function isGeoTag(tag) {
  if (
    tag === CD_TAG ||
    tag === STATE_TAG ||
    tag === METRO_TAG ||
    tag === COUNTRY_TAG ||
    tag === COUNTY_TAG
  )
    return true;
  return (
    tag.startsWith(`${METRO_TAG}:`) || tag.startsWith(`${COUNTRY_TAG}:`)
  );
}

// Mirrors the unlock-by-name set construction in source-filters.ts.
function unlockedMetrosForQuery(query, metros) {
  if (query.length < UNLOCK_MIN_CHARS) return null;
  const matched = new Set();
  const ql = query.toLowerCase();
  for (const [code, entry] of Object.entries(metros ?? {})) {
    const hay = (entry.shortName + " " + entry.name).toLowerCase();
    if (hay.includes(ql)) matched.add(`${METRO_TAG}:${code}`);
  }
  return matched.size > 0 ? matched : null;
}

function unlockedCountriesForQuery(query, countries) {
  if (query.length < UNLOCK_MIN_CHARS) return null;
  const matched = new Set();
  const ql = query.toLowerCase();
  for (const [code, entry] of Object.entries(countries ?? {})) {
    if (entry.name.toLowerCase().includes(ql)) {
      matched.add(`${COUNTRY_TAG}:${code}`);
    }
  }
  return matched.size > 0 ? matched : null;
}

function unlockedStatesForQuery(query) {
  if (query.length < UNLOCK_MIN_CHARS) return null;
  const matched = new Set();
  const ql = query.toLowerCase();
  for (const name of US_STATE_NAMES) {
    if (name.toLowerCase().includes(ql)) matched.add(name);
  }
  return matched.size > 0 ? matched : null;
}

// The proposed query-aware tag-count recompute. Runs on every
// keystroke once the query has 4+ chars (or any keystroke if we want
// it to react to search text too). Walks every source, applies
// the same gates the picker applies to filteredSources, accumulates
// counts.
function queryAwareTagCounts(query, lib) {
  const sources = lib.sources ?? {};
  const unlockMetros = unlockedMetrosForQuery(query, lib.metros);
  const unlockCountries = unlockedCountriesForQuery(query, lib.countries);
  const unlockStates = unlockedStatesForQuery(query);
  const counts = new Map();
  for (const id of Object.keys(sources)) {
    const src = sources[id];
    if (src.kind === "hint") continue;
    const tags = src.tags ?? [];
    // Apply default-visibility unless a relevant unlock fires.
    let visible = true;
    if (tags.includes(METRO_TAG) || tags.some((t) => t.startsWith(`${METRO_TAG}:`))) {
      if (!unlockMetros) visible = false;
      else visible = tags.some((t) => unlockMetros.has(t));
    }
    if (visible && tags.includes(COUNTRY_TAG)) {
      if (!unlockCountries) visible = false;
      else visible = tags.some((t) => unlockCountries.has(t));
    }
    if (visible && (tags.includes(CD_TAG) || tags.includes(STATE_TAG))) {
      // Cheaper proxy for state-name unlock — match query against
      // any 2-letter state code in the id. Real runtime parses the
      // ID via parseCdSourceId; here we approximate by string scan.
      if (!unlockStates) visible = false;
      // (We skip the exact ID-parse check in the bench — the loop
      // cost is dominated by the per-source tag walk; the parse is
      // a tiny constant overhead. This is close enough.)
    }
    if (visible && tags.includes(COUNTY_TAG)) {
      if (query.length < UNLOCK_MIN_CHARS) visible = false;
    }
    if (!visible) continue;
    // Also enforce the global text-match against searchText, since
    // the runtime does too. This is the dominant cost for non-unlock
    // queries.
    if (query) {
      const hay = src.searchText ?? "";
      if (!hay.includes(query.toLowerCase())) continue;
    }
    // Accumulate topical tags.
    for (const t of tags) {
      if (isGeoTag(t)) continue;
      counts.set(t, (counts.get(t) ?? 0) + 1);
    }
  }
  return counts;
}

// Bench harness — runs N iterations of fn, returns array of ms.
function bench(label, fn, iterations) {
  // Warmup so JIT settles.
  for (let i = 0; i < WARMUP; i++) fn();
  const samples = [];
  for (let i = 0; i < iterations; i++) {
    const t0 = performance.now();
    fn();
    samples.push(performance.now() - t0);
  }
  samples.sort((a, b) => a - b);
  const mean = samples.reduce((s, v) => s + v, 0) / samples.length;
  const median = samples[Math.floor(samples.length / 2)];
  const p95 = samples[Math.floor(samples.length * 0.95)];
  const p99 = samples[Math.floor(samples.length * 0.99)];
  const max = samples[samples.length - 1];
  console.log(
    `${label.padEnd(38)} ` +
      `mean=${mean.toFixed(2)}ms ` +
      `median=${median.toFixed(2)}ms ` +
      `p95=${p95.toFixed(2)}ms ` +
      `p99=${p99.toFixed(2)}ms ` +
      `max=${max.toFixed(2)}ms`,
  );
}

console.log(`Loading ${LIB_PATH}...`);
const lib = JSON.parse(readFileSync(LIB_PATH, "utf-8"));
console.log(`Sources: ${Object.keys(lib.sources).length}`);
console.log(`Metros: ${Object.keys(lib.metros ?? {}).length}`);
console.log(`Countries: ${Object.keys(lib.countries ?? {}).length}`);
console.log(`Iterations per scenario: ${ITERATIONS} (after ${WARMUP} warmup)\n`);

// Scenarios — each represents one keystroke that the picker would
// need to react to. Pick a representative mix: short queries (below
// the unlock threshold), exact 4-char unlocks, and longer queries.
bench("empty query (no walk needed today)", () => queryAwareTagCounts("", lib), ITERATIONS);
bench("3-char query (below unlock)", () => queryAwareTagCounts("gdp", lib), ITERATIONS);
bench("4-char query: 'virg' (unlock fires)", () => queryAwareTagCounts("virg", lib), ITERATIONS);
bench("5-char query: 'virgi'", () => queryAwareTagCounts("virgi", lib), ITERATIONS);
bench("6-char query: 'virgin'", () => queryAwareTagCounts("virgin", lib), ITERATIONS);
bench("7-char query: 'virgini'", () => queryAwareTagCounts("virgini", lib), ITERATIONS);
bench("8-char query: 'virginia'", () => queryAwareTagCounts("virginia", lib), ITERATIONS);
bench("4-char query: 'abil' (Abilene metro)", () => queryAwareTagCounts("abil", lib), ITERATIONS);
bench("4-char query: 'germ' (Germany country)", () => queryAwareTagCounts("germ", lib), ITERATIONS);
bench("4-char query: 'xxxx' (no matches)", () => queryAwareTagCounts("xxxx", lib), ITERATIONS);
bench("long query: 'unemployment rate'", () => queryAwareTagCounts("unemployment rate", lib), ITERATIONS);
