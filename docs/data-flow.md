# Tape — Data flow through the Python pipelines

> A complete description of how information moves from external providers,
> through the `pipelines/` Python programs, into committed data + content,
> and out to the rendered site. Written 2026-06-03 as a from-scratch read of
> the codebase. Companion to `docs/new-data-source-checklist.md` (how to add
> a provider) and `docs/data-source-roadmap.md` (what's queued).

---

## 1. The big picture in one paragraph

External APIs and CSVs → **ingest pipelines** write per-series JSON to
`public/data/<provider>/<id>.json` (and, for newer providers, the matching
source YAML to `src/content/sources/<provider>/`) → **content generators**
scaffold any missing source/chart/dashboard YAML from those data files →
**index builders** walk the whole data tree to emit `source_index.json`,
per-source `.summary.json` tiles, and `generators-index.json` → **trim**
shrinks each data file to its displayed window → **audits** gate the result
against provider-authoritative labels and house-style copy → the workflow
**commits `public/data/` + generated YAML to `main`**, which triggers a
Vercel deploy → at build/runtime the **Astro/TypeScript layer** reads the
committed data and renders tiles, dialogs, maps, and source pages.
Separately, after each refresh the **alert evaluator** reads user rules from
Supabase, checks them against the fresh data on disk, and dispatches emails.

The Python half owns everything up to "committed data + YAML." The
TypeScript half (documented elsewhere) owns rendering. The contract between
them is the on-disk shape of `public/data/**/*.json` (the `SourceData`
interface in `src/lib/data-types.ts`) plus the source/chart/dashboard schemas
in `src/content/config.ts`.

---

## 2. The data lifecycle (run order)

Every scheduled refresh runs the same eight-stage pipeline. The stages are
identical across both GitHub workflows and the local runner; only the *set of
ingest pipelines* in stage 1 differs (market data weekly, demographics
monthly).

```
1. INGEST      fetch external → write public/data/<provider>/<id>.json
                                (+ src/content/sources YAML for newer providers)
2. GENERATE    scaffold missing source/chart/dashboard YAML from the data files
3. SUMMARIZE   build_summaries.py → <id>.summary.json tiles + source_index.json
4. CATALOG     _generate_generators_index.py → public/generators-index.json
5. TRIM        trim_source_data.py → cut each data file to its displayed window
6. AUDIT       audit_all_sources.py --strict   (labels vs provider truth)
               fix_source_descriptions.py + audit_source_descriptions.py --strict (copy)
7. ALERTS      check_alerts.py → Supabase rules vs on-disk data → alert_triggers
               dispatch_alert_emails.py → email digests → mark notified
8. COMMIT      race-safe overlay commit of public/data + generated YAML to main
```

Three ordering constraints are load-bearing:

- **`sec_shares.py` before `yahoo_marketcap.py`** — market cap = price ×
  shares-outstanding, and shares come from the SEC EDGAR JSONs that
  `sec_shares.py` writes. Running marketcap first uses stale/missing shares.
- **`yahoo_quotes.py` before `countries_relative.py`** — the latter divides
  country-ETF series by VT, both written by the former.
- **`census_acs_cd.py` before `derive_acs_state_from_cd.py` and
  `census_acs_choropleth_derive_state.py`** — the per-state series and state
  map snapshots are *derived from* the per-CD data on disk, no API
  call. The *direct* state map fetch then runs last to override
  derivation gaps (Connecticut 2022's planning-region tract GEOIDs, DC's
  missing aggregates).
- **`build_summaries.py` before `trim_source_data.py`** — summaries must see
  the full history before trimming throws the deep tail away.

### The race-safe commit (stage 8)

Both workflows run for 15 min – 4 hr, during which other commits can land on
`main`. The commit step therefore:

1. snapshots the data dirs it owns to a tmp location,
2. `git reset --hard origin/main` (discards the stale `src/` from its initial
   checkout — this prevents the May-2026 incident where `reset --soft`
   silently reverted hand-edited `src/` files under a "data refresh" message),
3. **overlays** the snapshot back with `cp -r "$tmp/data/." public/data/` —
   *non-destructively*, never `rm -rf public/data` (the June-2026 incident:
   wiping + restoring-only-the-snapshot deleted four whole providers that a
   concurrent push had added),
4. rebuilds `source_index.json` + `generators-index.json` from the merged
   tree so a provider added mid-run stays indexed,
5. stages only the explicit data + generated-YAML paths, commits, pushes;
   retries up to 5× on a lost push race.

**Lesson encoded here:** when merging an auto-refresh commit, always
`git diff --stat <merge>^ <merge> -- public/data` and check for deletions. An
index-count drop is *not* automatically benign.

---

## 3. Shared infrastructure (`pipelines/common.py`, `_env.py`, `_cache.py`)

`common.py` is imported by nearly every ingest pipeline and defines the
on-disk contract:

- `write_timeseries(pipeline, series_id, name, points, unit, projections=None, merge=True)`
  → writes `public/data/<pipeline>/<series_id>.json` as `kind:"timeseries"`.
  **Merge-on-write is the default:** new points are unioned with on-disk
  points keyed by timestamp `t`, newer wins — so history survives even if an
  upstream API truncates its window. `projections` (vintage_date → points)
  merge the same way for forecast-bearing series. Pipelines that fully
  re-derive each run pass `merge=False`.
- `write_curve(...)` → `kind:"curve"` with `snapshots` keyed/merged by `asOf`
  (forward curves).
- `cached_get(url, ttl_seconds, ...)` — HTTP GET with a SHA-256-keyed on-disk
  TTL cache under `pipelines/_response_cache/` (gitignored). Lazy-imports
  `requests`.
- Constants: `REPO_ROOT`, `DATA_ROOT` (= `public/data`), `CACHE_ROOT`.

`_env.py` — one `load_dotenv()` call, imported for side effect so `.env` keys
are available locally; a no-op in CI (keys arrive via Actions `env:` secrets).

`_cache.py` — a *second*, bucket-based cache (`pipelines/_cache/<bucket>/`)
used for expensive immutable fetches (ACS vintages, Zillow CSVs, SSA HTML)
with very large `max_age_days`. Note: `common.cached_get` and `_cache` are two
separate caching systems — a small piece of accidental duplication.

A few pipelines (`bea.py`, `fec_house_spending.py`, `noaa_climate.py`)
deliberately read their API key by regex from `.env` rather than via `_env`,
because those providers pass the key as a URL query param — the pipelines
never log the key-bearing URL.

---

## 4. Ingest pipelines by provider family

Each entry is **source → transform → output**. All currency aggregates are
stored in **billions USD**, counts **raw**; see §8.

### FRED family — `public/data/fred/`
- **`fred_series.py`** — the public `fredgraph.csv` endpoint (no key, via
  `curl`). Hundreds of `FredSpec` rows: macro rates, inflation, labor,
  housing, credit, monetary, fiscal-by-function, FX, agriculture, DC-metro,
  and per-state population / govt-employment / tax / building-permits /
  business-formation. Transforms: optional server-side `transformation`
  (pc1/pca/chg), thousands→raw count guard, `scale` for millions→billions
  (the G.19 consumer-credit family is published in millions). Also probes the
  series page for label drift. Copyright-gated by `audit_fred_copyright.py` —
  S&P/Case-Shiller/VIX/UMich/ICE-BofA etc. are intentionally **not** ingested.
- **`_fetch_new_fred.py`, `_fetch_ai_datacenter.py`** — one-off batch fetchers
  for specific expansion batches.

### Yahoo Finance family
- **`yahoo_quotes.py`** (`public/data/yahoo/`) — daily adjusted close for ~200
  tickers (equities, ETFs, futures front-month, FX, crypto), `period="max"`.
- **`yahoo_marketcap.py`** (`public/data/yahoo_marketcap/`) — market cap =
  unadjusted close × shares-outstanding (shares from `sec_shares` JSONs, with
  a yfinance fallback), stored in billions. Runs *after* `sec_shares.py`.
  `TSM` excluded (ADR ratio).
- **`yahoo_futures.py`** (`public/data/yahoo_futures/`) — forward curves for
  WTI/Brent/NatGas/VIX + ag commodities. `points` = monthly-averaged spot;
  `projections` = date-keyed snapshots of the forward curve (capped at 90
  rolling vintages).
- **`sec_shares.py`** (`public/data/sec_shares/`) — SEC EDGAR XBRL
  CompanyFacts (no key, descriptive User-Agent), `EntityCommonStockShares
  Outstanding`. Hand-curated `TICKER_TO_CIK`. Raw share counts.
- **`countries_relative.py`** (`public/data/countries_relative/`) — *derives*,
  no fetch: country ETFs ÷ VT, indexed to 100 at first overlap. After
  `yahoo_quotes`.

### World Bank family (public API, no key)
- **`worldbank_gdp.py`** — real GDP for 11 countries + world; emits both
  *share of world GDP %* (`public/data/worldbank_gdp/`) and raw GDP in
  billions (`public/data/worldbank_gdp_raw/`).
- **`worldbank_extended.py`** — many indicators × entities (China deep-dive,
  regional aggregates, ~50 country deep-dives). Writes **both** data JSON
  *and* source YAML. CC BY 4.0.

### US federal economic agencies
- **`bea.py`** (`public/data/bea/` + county to `public/data/acs_county/`) —
  BEA Regional API (`BEA_API_KEY`). State GDP / real GDP / personal income →
  billions; per-capita income raw; `county`/`choropleth` sub-command writes
  per-vintage county per-capita income. `UNIT_MULT` is a power-of-10; never
  logs the key-bearing URL.
- **`bls.py`** (`public/data/bls/`) — BLS Public Data API (no key). CPI
  components, JOLTS, all-state LAUS unemployment + CES payrolls, DC-metro
  county unemployment. Thousands→raw.
- **`bls_metro.py`** — per-CBSA unemployment + payrolls, driven by
  `_crosswalks/cbsa_metro.csv`; writes data + YAML.
- **`cbo.py`** (`public/data/cbo/`) — **operator-driven, no fetch** (CBO is
  behind DataDome). Parses operator-supplied XLSX in `pipelines/cbo_data/`
  (gitignored): Budget Outlook projections + Historical actuals, 4 %-of-GDP
  series with `projections`.
- **`ssa.py`** (`public/data/ssa/`) — SSA Trustees Report HTML tables
  (anti-bot 403 → falls back to operator HTML in `pipelines/ssa_data/`).
  OASDI intermediate-cost projections.
- **`treasury_tic.py`** (`public/data/treasury_tic/`) — Treasury TIC text
  file: foreign holdings of US Treasuries by ~37 countries, monthly, billions.
- **`usaspending.py`** (`public/data/usaspending/`) — USAspending.gov
  `spending_by_geography` (no key), per FY since FY2008. State + CD federal
  spending → billions.
- **`usaspending_metro.py`** — county-level rolled up to CBSA via
  `_crosswalks/county_to_cbsa.csv`; data + YAML.
- **`cms_nhe.py`** (`public/data/cms_nhe/`) — CMS National Health Expenditure
  ZIP. Per-capita national health spending (raw USD, `merge=False`).

### US states — energy, health, education, crime, climate, agriculture, water
- **`eia_prices.py`** (`public/data/eia_prices/`) — EIA API v2 (`EIA_API_KEY`).
  State electricity ¢/kWh + residential nat-gas $/MCF.
- **`eia_state_energy.py`** (`public/data/eia_state_energy/` + YAML) — EIA v2
  net generation by fuel, thousand-MWh→TWh. YAML emitted inline (Plan 7).
- **`cdc_health.py`** (`public/data/cdc_health/` + YAML) — CDC Socrata
  (`data.cdc.gov`, no key). Life expectancy, age-adjusted death rates,
  leading-cause death rates. Public-use aggregates only — never restricted
  micro-data.
- **`naep_scores.py`** (`public/data/naep/` + YAML) — NCES NAEP `GetAdhocData`
  (no key). Grade-4/8 math+reading scale scores. YAML emitted inline (Plan 7).
- **`edu_spending.py`** (`public/data/edu_spending/` + YAML) — Urban Institute
  Education Data Portal (NCES CCD F-33, no key). Per-pupil current spending =
  spending / enrollment. YAML emitted inline (Plan 7).
- **`fbi_crime.py`** (`public/data/fbi_crime/` + YAML) — FBI CDE summarized API
  (`cde.ucr.cjis.gov`, no key). Murder / violent / property rate per 100k =
  12 monthly counts ÷ population.
- **`fec_house_spending.py`** (`public/data/fec/` + YAML) — FEC
  `api.open.fec.gov` (`DATAGOV_API_KEY`). House candidate disbursements per CD
  per 2-yr cycle (1990–2024), millions USD. Redistricting-aware district
  coding + seeded default annotations. **Manual, on-demand** (not in the
  scheduled workflows — House finance updates biennially; a full re-fetch
  takes ~80 min of rate-limit backoff).
- **`noaa_climate.py`** (`public/data/noaa_climate/` + YAML) — NOAA NCEI CDO v2
  GSOY (`NOAA_API_KEY` as header token). Annual avg temp °F + precip inches for
  18 metro airport stations (deliberately station-level, not state-averaged).
- **`usda_nass.py`** (`public/data/usda_nass/` + YAML) — USDA NASS QuickStats
  (`NASS_API_KEY`). Corn/soy/wheat yield/production/price. Stores price +
  quantity separately and emits a `combineHint` so the composer *derives*
  value (price × quantity) rather than storing it.
- **`usgs_water.py`** (`public/data/usgs_water/` + YAML) — **not an API**;
  parses version-controlled USGS CSVs in `pipelines/_usgs_raw/`. By-sector
  withdrawals (2015) + total trend (1985–2015).
- **`zillow.py`** (`public/data/zillow/`) — Zillow Research public CSVs (no
  key). ZHVI + ZORI, national + 12 metros. YAML via `_generate_zillow_sources.py`.
- **`oecd.py`** (`public/data/oecd/`) — OECD SDMX REST (no key). Harmonized
  unemployment, CPI YoY, govt debt/deficit, life expectancy, health spending.
- **`owid_co2.py`** (`public/data/owid_co2/` + YAML) — Our World in Data CO2
  CSV (no key, CC BY 4.0). 9 indicators × 21 entities.

### Census ACS family (`CENSUS_API_KEY`; indicators/parsers shared from `census_acs_cd.py`)
- **`census_acs_cd.py`** (`public/data/acs_cd/`) — tract-level ACS5 (2010–2022)
  aggregated to stable 118th-Congress districts via
  `_crosswalks/tract20xx_to_cd118.csv` (counts sum; median HH income
  recomputed from B19001 bins). Uses `_cache`, permanent for old vintages.
- **`census_acs_national.py`** (`public/data/acs_national/`) — same indicators
  at `us:1`.
- **`census_acs_metro.py`** — same indicators at CBSA geography; data + YAML.
- **`census_acs_labor.py`** (`public/data/acs_labor/` + YAML) — ACS1 S2301
  unemployment by race / Hispanic origin. YAML emitted inline (Plan 7).
- **`census_acs_choropleth.py`** — **cross-sectional snapshots** (not
  timeseries) for maps: per (indicator, vintage, geo) a `{values:{GEOID:v}}`
  file → `public/data/acs_{state,county,tract,block_group}/`.
- **`census_acs_choropleth_derive_state.py`** — derives state map
  snapshots from on-disk `acs_state` timeseries (no API key).
- **`derive_acs_state_from_cd.py`** — aggregates per-CD ACS into per-state
  timeseries (counts sum; medians population-weighted).
- **`census_govfin.py`** (`public/data/census_govfin/` + YAML) — Census
  `timeseries/govsstatefin`. State revenue/expenditure aggregates, $1,000s→
  billions (DC excluded — not a state government). YAML emitted inline
  (Plan 7).

---

## 5. Content generators / scaffolders (write YAML/MDX, not data JSON)

These bridge "data exists on disk" → "the site knows about it." All are
idempotent (skip-if-exists), which is what keeps YAML in parity with data
after every refresh.

- **`_generate_acs_sources.py` / `_generate_acs_national_sources.py`** — scan
  `acs_cd` / `acs_national` data → write `src/content/sources/acs_cd|acs_national/`.
- **`_generate_zillow_sources.py`** — scan `zillow` data → zillow source YAMLs.
- **`_scaffold_*.py`** (state_govemp, persona_sources — both emit into the
  hand-curated `fred/` dir) — iterate their pipeline's data files, emit one
  source YAML each. The five per-provider scaffolds (eia_state_energy, naep,
  edu_spending, census_govfin, acs_labor) were folded into their pipelines
  (Plan 7, 2026-06): those now emit YAML inline, overwrite-always, with the
  dirs staged by the refresh workflows. New providers emit YAML inline; see
  docs/new-data-source-checklist.md step 7.
- **`_generate_content.py`** — one-off source+chart YAML generator for a
  library expansion (with a cadence→`supportedDeltas` helper).
- **`_generate_state_tract_charts.py` / `_generate_state_bg_charts.py`** —
  per-state map **chart** YAMLs under `src/content/charts/state-*-maps/`.
- **`_generate_state_atlas_dashboards.py`** — 4 regional "State Atlas"
  **dashboard** MDX files.
- **`_backfill_tags.py` / `backfill_source_tags.py`** — rule-based `tags:` on
  chart / source YAMLs.

---

## 6. Index / summary builders + crosswalks

These are the cross-provider aggregates the front end depends on.

- **`build_summaries.py`** — walks every `public/data/**/*.json`, writes a
  compact `<id>.summary.json` sibling (latest + priors + downsampled sparks
  per delta window) **and** accumulates `public/data/source_index.json` =
  `{"data/<rel>.json": [firstT, lastT]}`. `library.json.ts` reads that one
  index file for every source's coverage dates instead of opening ~35k data
  files — this fixed a ~6.5-minute prerender bottleneck. **If this script
  doesn't run, every source silently loses its coverage range.**
- **`_generate_generators_index.py`** — walks all source YAMLs, groups
  geo-sibling sources into templates → `public/generators-index.json` for the
  composer's Generators tab.
- **`build_crosswalks.py`** — Census block-relationship files →
  `_crosswalks/tract{2010,2020}_to_cd118.csv` (tract→118th-CD weights).
  Consumed by `census_acs_cd.py`.
- **`build_cbsa_metro_crosswalk.py`** — Census CBSA delineation →
  `_crosswalks/cbsa_metro.csv` + `county_to_cbsa.csv`. Consumed by the metro
  pipelines and the generators index.
- **`build_state_tract_topo.py`** — Census TIGER shapefiles → per-state
  TopoJSON (via `mapshaper`), cached in `_tract_topo_cache/`. Feeds the
  map chart YAMLs.

Crosswalk builders are run rarely/manually (their inputs are decennial), not
in the scheduled refresh.

---

## 7. Audits / validation

Run `--strict` in CI (stage 6), lenient locally.

- **`scripts/audit_all_sources.py`** — top-level runner. Chains the
  per-provider label audits (`audit_fred_series`, `audit_worldbank_indicators`,
  `audit_yahoo_tickers`, plus census_govfin/acs_labor/eia/naep/edu/zillow),
  each comparing our YAML `name` against the provider's authoritative title
  and exiting 1 on drift. This is the gate that prevents the May-2026
  label-mismap class of bug.
- **`audit_fred_copyright.py`** — FRED copyright status (PRE-APPROVAL /
  CITATION-REQUIRED / PUBLIC-DOMAIN); gates which series may be ingested.
- **`audit_source_descriptions.py`** — flags implementation-leak vocabulary
  and undefined acronyms in user-facing copy; `fix_source_descriptions.py`
  auto-rewrites to house style first.
- **`audit_source_scales.py`** — flags value/unit/style mismatches that
  `derive.ts` would compute wrong (raw dollars labeled billions, etc.).
- **`_audit_chart_sources.py` / `_audit_orphans.py`** — broken chart→source
  references; orphan YAML or data.
- **`pipelines/test_*.py`** (unittest) — `test_common` (merge/cache),
  `test_check_alerts`, `test_dispatch_alert_emails`, `test_audit_source_scales`,
  `test_generators_index`, `test_source_corpus` (corpus-wide YAML invariants,
  incl. the `world`-tag = cross-country-aggregates-only rule), and the
  `test_about_page_coverage` / `test_welcome_page_coverage` guards that force
  every new provider onto the About + Welcome pages.

Separately, `scripts/audit-source-data.mjs` (npm `prebuild`) fails the *site*
build if any chart references a missing data file — the safety net for the
data-loss class of incident.

---

## 8. Canonical unit conventions

Enforced at write time in each ingest pipeline; the front end (`derive.ts`)
hard-assumes them.

- **Currency aggregates → billions USD.** BEA `value × 10^UNIT_MULT / 1e9`;
  usaspending / worldbank / marketcap `/1e9`; census_govfin `/1e6` (from
  $1,000s); FRED `scale=1e-3` for millions-published series (G.19
  consumer-credit family). Retro-fix: `rescale_currency_to_billions.py`.
- **Counts → raw** (not thousands). FRED/BLS multiply "thousands"-labeled
  series ×1000 and relabel to a natural noun. Exceptions pinned in
  `fred_series.ALREADY_RAW_DESPITE_THOUSANDS` (ICSA, CCSA). Retro-fix:
  `rescale_counts_to_raw.py`.
- **Per-capita / price / rate / index / score → stored raw** (per-capita
  income, $/bu, ¢/kWh, per-100k rates, scale scores).
- `unitClass` (currency/count/rate/index/ratio/price) on each source drives
  `combineOpFormatting` in `derive.ts`. Backfilled by `backfill_unit_class.py`.

**Operating rule:** any "this number looks 1000× off" report is almost
certainly a pipeline-scale regression, not a math bug.

---

## 9. Alerts (runtime, post-refresh)

- **`check_alerts.py`** — reads `alert_rules` from Supabase (`SUPABASE_URL` +
  `SUPABASE_SERVICE_ROLE_KEY`, REST via urllib). For each active rule it loads
  the source's full series from disk (`load_observations`, or
  `load_derived_observations` for `A op B` aligned by date) and does a
  **windowed evaluation**: it walks every observation since the rule's
  `last_value_t` with a rolling `prev` seeded from `last_value_seen`, so a
  daily-series crossing mid-week isn't missed. Conditions: gt/gte/lt/lte/
  crosses_above/crosses_below/change_above. On fire → POST `alert_triggers`;
  always PATCH `last_value_seen`/`last_value_t`. Idempotent (skips when the
  latest observation date is unchanged). Security: a `SAFE_SOURCE_ID` regex +
  path-confinement, because `source_id` comes from a user-writable table and
  the service role bypasses RLS.
- **`dispatch_alert_emails.py`** — reads pending triggers (`notified_at IS
  NULL`), groups by owner, sends one digest each via Resend *or* Postmark,
  stamps `notified_at`. Retry cap → sentinel drop; repeated failures
  auto-pause the rule.

**Critical:** alerts run **only** from the GitHub workflows. The local runner
deliberately omits them — `.env`'s service-role key is the *production* key,
so a laptop run would email real users and advance each rule's `last_value_t`
against prod, making the scheduled run skip the very observations it needs.

---

## 10. One-shot / maintenance scripts

Not part of the refresh; run by hand when needed.

- `rescale_currency_to_billions.py` / `rescale_counts_to_raw.py` —
  retroactive unit normalization of existing data + YAML.
- `backfill_unit_class.py` / `backfill_source_tags.py` — backfill `unitClass`
  and `tags` onto source YAMLs.
- `trim_source_data.py` — trim each data file to its longest declared
  `supportedDeltas` window × 1.1 (runs in every refresh, after summaries).
- `fix_source_descriptions.py` — in-place copy rewriter (runs in every
  refresh, before the strict description audit).
- `_normalize_source_licenses.py` — fills/normalizes `provenance.license` per
  the per-pipeline canonical strings.
- `classify_charts_for_cuts.py` — flags wrapper charts as KEEP vs CUT for
  catalog trimming.

---

## 11. Orchestration summary

| | Weekly (`refresh-data.yml`) | Monthly (`refresh-demographics.yml`) | Local (`run-data-refresh-local.sh`) |
|---|---|---|---|
| Cadence | Sun 06:00 UTC | 1st of month 06:00 UTC | manual, one command |
| Ingest set | market data (FRED, Yahoo, WB-GDP, BLS, CBO, OECD, TIC, USAspending, EIA) | Census ACS (CD/metro/national/map), WB-extended, USAspending-metro, BLS-metro, state annual sets | both sets |
| Runtime | ~15 min | ~3–4 hr clean, less on cache hits | full sequence |
| Alerts | yes | yes | **no** (prod-Supabase safety) |
| Commit | race-safe overlay | race-safe overlay (+ owns the `acs_*` YAML dirs) | none (you commit by hand) |

Pipelines run with `continue-on-error` so one flaky provider doesn't block the
rest. **Not in any workflow** (manual on-demand): `fec_house_spending.py`,
`sec_shares.py`/`yahoo_futures.py` in the weekly set are in the local runner
but check the YAML; the crosswalk/topo builders; and all one-shots.

---

## 12. Notes for the next maintainer

- The two caching systems (`common.cached_get` vs `_cache.py`) do the same job
  with different key schemes. Consolidating them would remove a footgun.
- Newer providers write their source YAML inline (good — atomic with the
  data); older ACS-family providers split data-ingest from a separate
  `_generate_*`/`_scaffold_*` step. The inline pattern is the one to copy.
- `source_index.json` and `generators-index.json` are *committed* aggregates
  the Vercel build does not regenerate. If you hand-edit data, rebuild them.
- The SSR source pages (`/source/<id>/`) are not exercised by `astro build` —
  verify rendering by curling prod after deploy, not just by a green build.
