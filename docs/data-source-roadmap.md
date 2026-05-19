# Data-source roadmap

After the May 2026 brainstorm of "what else do DC econ/policy
people cite," this file captures the decisions + concrete next
steps for the providers we want to add. Each entry has the API
endpoint, license, auth situation, and an implementation note —
enough that picking one up later is a 30-60 minute exercise.

The new-data-source checklist
(`docs/new-data-source-checklist.md`) is the protocol; this file
is the queue + status.

## Status

### Shipped

- **Zillow Research** — ZHVI + ZORI for the US + 12 largest metros.
  `pipelines/zillow.py`, 26 source YAMLs, audit at
  `scripts/audit_zillow_indexes.py` (structural — Zillow has no
  "official label" API endpoint). Charts on the Housing dashboard.

### Queued — clean-API, fastest to ship next

#### BEA (Bureau of Economic Analysis)

Free API key (36 chars) — sign up at
`https://apps.bea.gov/API/signup/index.cfm`. Returns JSON.

Key datasets to pull:
- **State GDP**: dataset `Regional`, table `SAGDP2N` (current dollars)
  or `SAGDP9N` (chained 2017 dollars). Geo dimension by state FIPS.
- **State personal income**: dataset `Regional`, table `SAINC1`
  (annual) or `SQINC1` (quarterly).
- **NIPA Tables**: dataset `NIPA`, table series like `T10101` for
  the headline national GDP breakdown. Better detail than the
  individual W-series FRED sources for federal-budget pieces.

URL shape:
```
https://apps.bea.gov/api/data/?UserID=<KEY>
  &method=GetData
  &datasetname=Regional
  &TableName=SAGDP2N
  &GeoFIPS=STATE
  &LineCode=1
  &Year=ALL
  &ResultFormat=JSON
```

Audit: hit `GetParameterValues` to enumerate official table titles
+ line descriptions, compare to YAML labels. Same shape as
`audit_fred_series.py`.

Estimated implementation: 60-90 min for state GDP + state personal
income coverage.

#### OWID (Our World in Data)

No auth. CSV downloads at `https://ourworldindata.org/grapher/<slug>.csv`
for any chart on the site. Plus the data catalog at
`https://docs.owid.io/projects/etl/api/`.

OWID is unusual: it's a META-source that aggregates + harmonizes
hundreds of other providers' data. Use it for series we'd
otherwise have to write a dedicated pipeline for.

Curated picks for our user (DC econ/policy):

| OWID slug | What it is | Why it matters |
|---|---|---|
| `co-emissions-per-capita` | CO2 emissions per person, by country | Climate-policy debates |
| `share-electricity-renewables` | Renewable share of electricity by country | Energy transition |
| `population-growth-rates` | Annual population growth by country | Demographics |
| `life-expectancy` | Life expectancy at birth by country | Common cross-country anchor |
| `corruption-perception-index` | Transparency International's CPI | Institutions |
| `military-expenditure-as-share-of-gdp` | SIPRI military spending / GDP | Defense policy |
| `share-of-population-using-the-internet` | Internet penetration | Digital divide |
| `gdp-per-capita-worldbank` | GDP per capita, harmonized WB | Income comparisons |
| `share-of-the-population-living-in-extreme-poverty` | World Bank poverty headcount | Development |
| `child-mortality` | Under-5 mortality rate | Development |
| `total-fertility-rate` | Births per woman | Demographics |
| `share-of-population-with-completed-tertiary-education` | College attainment | Education policy |
| `homicide-rates` | Homicides per 100k by country | Public-safety comparison |
| `share-of-the-labor-force-employed-in-agriculture` | Ag employment share | Structural change |
| `r-and-d-expenditure-as-a-share-of-gdp` | R&D spending / GDP | Innovation policy |

Pipeline: a single `pipelines/owid.py` with a list of slugs to
fetch. Each CSV download is one source per (slug, country).
Audit: OWID's per-chart API at `/api/v1/charts/<id>` returns the
canonical name; compare to YAML.

Estimated implementation: 90 min for the 15 series above × ~30
countries each = ~450 sources, auto-generated.

#### ECB Statistical Data Warehouse

SDMX REST API at `https://sdw-wsrest.ecb.europa.eu/service/data/<flow>/<key>`.
No auth. Supports JSON output via Accept header.

Key flows:
- `BSI` (balance sheet items — euro area monetary aggregates)
- `EXR` (exchange rates)
- `IRS` (interest rates)
- `MNA` (national accounts)
- `STS` (short-term statistics)

URL shape (CSV for easier parsing):
```
https://sdw-wsrest.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A?
  format=csvdata
```

Estimated implementation: 60 min for the headline euro-area
macro series (M3, HICP, deposit/lending rates, EUR/USD).

#### SSA (Social Security Administration)

Open data portal at `https://www.ssa.gov/data/`. Annual XLSX files
for OASDI Beneficiaries by Congressional District + by ZIP + by
State/County. No API.

Key file: `https://www.ssa.gov/policy/docs/factsheets/cong_stats/
2025/cd-data.xlsx` (one row per congressional district).

Estimated implementation: 45 min for CD-level beneficiary counts +
total payments (our user has the VA-08 dashboard angle already).

#### USPTO PatentsView (or successor — migrating to data.uspto.gov on March 20, 2026)

Note the migration. As of May 2026 either URL may be live; check
before implementing.

PatentsView API: `https://search.patentsview.org/api/v1/patent/`.
Bulk annual datasets at `https://patentsview.org/data/annualized`
(CSV).

Useful angle for DC-policy: per-state patent counts per year,
per-firm patent assignments, inventor-location distribution.

Estimated implementation: 60 min for state-level annual counts +
maybe top-20 firms.

### Queued — XLSX-wrangling, slower

#### CBO

NO API. Bulk XLSX downloads only. Two key files:
- Historical Budget Data:
  `https://www.cbo.gov/system/files/<YYYY-MM>/51134-<YYYY-MM>-Historical-Budget-Data.xlsx`
- Budget + Economic Outlook projections:
  `https://www.cbo.gov/system/files/<YYYY-MM>/51119-<YYYY-MM>-budget-projections.xlsx`
  (published each February + August)

Implementation requires `openpyxl` for XLSX parsing. The harder
part is the multi-vintage forecast pattern — see the "Forecast UI"
proposal below.

Estimated implementation: 2-3 hours including the multi-vintage
ingest. This is the biggest of the queued providers.

#### CMS National Health Expenditure

NO API. XLSX downloads from
`https://www.cms.gov/data-research/statistics-trends-and-reports/
national-health-expenditure-data/historical` and `.../projected`.

Files include:
- NHE 1960-2023 by source (private/public/Medicare/Medicaid/etc.)
- NHE projections 2024-2032

XLSX has the standard "table with merged header rows" pattern that
needs careful parsing.

Estimated implementation: 90 min for the headline NHE table +
sponsor-share table.

### Queued — partial-API, requires more care

#### HMDA

Two paths:
- **CFPB HMDA Data Browser API** at
  `https://ffiec.cfpb.gov/data-browser/api`: query-style endpoint
  with filters for year + geography. Returns CSV/JSON.
- **Bulk CSV downloads** at
  `https://www.consumerfinance.gov/data-research/hmda/historic-data/`:
  full LAR (loan-level application records). Multi-GB per year.

We want the **aggregated, tract-level summaries** — Urban Institute
has these pre-aggregated at
`https://datacatalog.urban.org/dataset/home-mortgage-disclosure-act-neighborhood-summary-files-census-tract-level`
which is much cleaner than the raw LAR.

Estimated implementation: 2 hours for the Urban tract summaries
ingest. Aligns with the choropleth feature (per-tract data).

#### CDC WONDER (mortality)

XML POST API at `https://wonder.cdc.gov/controller/datarequest/<dataset_id>`.
Free, no auth. BUT: "Only national data are accessible to API
queries for data from the National Vital Statistics System" — you
can't filter by state/county via API.

Useful for headline national series: deaths by underlying cause,
by age, by race. Limited geographic granularity through the API.

Estimated implementation: 2 hours including the XML-payload
construction. Lower priority because of the geographic limitation.

#### FBI UCR / Crime Data Explorer

API at `https://api.usa.gov/crime/fbi/cde/` — requires a free
`api.data.gov` key. Sign-up at `https://api.data.gov/signup/`.

NIBRS data (incident-level) available 1991-present. Coverage
varies by agency — only ~70% of US population is in NIBRS-
reporting jurisdictions as of 2024. The summary UCR (1960-2020)
has full coverage but coarser detail.

Note: politically sensitive. Treat with caveats in chart blurbs.

Estimated implementation: 90 min for state-level annual violent
+ property crime rates.

#### NCES (National Center for Education Statistics)

CCD = K-12. IPEDS = postsecondary. Both are bulk CSV/XLSX, no API.

CCD files at `https://nces.ed.gov/ccd/files.asp`. Standard format:
one file per (year, dataset). Enrollment, finance (NPEFS), staff.

Estimated implementation: 90 min for enrollment + per-pupil
spending by state. Lower priority unless education policy becomes
a topic.

### Documented as "polling," but mostly behind paywalls

- **Conference Board** (CCI, LEI) — Data Central portal, member-
  only for full series. UMich Sentiment is a free alternative
  (already in FRED).
- **Gallup** — most series subscription-only; some public via
  monthly polling releases.
- **AAII Investor Sentiment** — historical CSV at
  `https://www.aaii.com/sentimentsurvey/sent_results`, behind a
  free-account wall.
- **Pew Research** — topline numbers in PDFs, no API.
- **ISM PMI** — already in FRED (NAPMPI).

Plan: skip dedicated polling pipelines. Surface what we have via
FRED (UMich sentiment, ISM PMI). Add AAII if we get a paid feed
or scrape carefully.

## Implementation order suggestion

If shipping one provider per session:

1. **BEA** — clean API, state GDP closes a big DC-econ gap.
2. **OWID** — quick to add, ~450 sources surfaced in one batch.
3. **ECB** — clean API, opens the door to European econ comparisons.
4. **SSA** — supports the existing VA-08 angle directly.
5. **HMDA** — pairs with choropleth feature.
6. **CMS NHE** — supports healthcare-spending narratives.
7. **CBO** — biggest payoff for fiscal-policy work but tied to
   the Forecast UI proposal below.
8. **USPTO** — supports innovation-policy stories.
9. **NCES** — education-policy angle.
10. **FBI UCR + CDC WONDER** — politically sensitive, lower priority.

## Forecast UI — design proposal

**Goal (per user request):** treat forecast/projected data as a
first-class time-series, with two key features:
1. Visually distinguish historical from projected ranges.
2. "View as of date X" — show only the forecast that was current
   on date X (i.e., snapshot a particular forecast vintage).

### Data shape

Each forecast-bearing source gets two augmentations to its JSON
payload:

```json
{
  "id": "cbo_outlays_pct_gdp",
  "name": "Federal outlays / GDP — CBO baseline",
  "kind": "timeseries",
  "unit": "%",
  "points": [
    { "t": "1962-01-01", "v": 18.6 },
    ...
    { "t": "2025-09-30", "v": 23.4 }
  ],
  "projections": {
    "2024-02": [
      { "t": "2024-09-30", "v": 23.1 },
      { "t": "2025-09-30", "v": 23.6 },
      ...
      { "t": "2034-09-30", "v": 24.1 }
    ],
    "2024-08": [ ... ],
    "2025-02": [ ... ],
    "2026-02": [ ... ]
  }
}
```

- `points`: the historical series (what actually happened).
- `projections`: a map of `<vintage-date> → forecast array`. Each
  vintage carries the full 10-year (or whatever) forecast that was
  published on that date. Multiple vintages live side-by-side.

### Pipeline ingest

For each forecast-bearing CBO file (and similar for CMS NHE
projections, Federal Reserve SEP, etc.):
- Read the historical sheet → `points`
- Read each projection sheet, stamped with its release date →
  one entry in `projections`
- Re-fetch on schedule (CBO twice/year, SEP quarterly, etc.)

### Renderer behavior

Two UI surfaces:

1. **Tile / dialog default view.** Render historical + the LATEST
   projection vintage. The projection segment uses a dashed line
   and a 50% opacity fill below to make it visually distinct.

2. **"As of" picker** in the dialog. A date selector that lists
   the available projection vintages. Selecting one masks all
   forecasts published AFTER that date — showing what the user
   "would have seen" if they were looking at the data on that date.

### Schema changes needed

- `src/lib/data-types.ts`: add an optional `projections` field on
  `TimeSeriesData`.
- `src/components/Chart.astro`: when projections present, render
  the segment after `points`'s last timestamp with a dashed
  stroke. Default to latest vintage.
- `src/components/ChartController.astro`: dialog gets a new
  "Vintage" picker showing available projection vintages,
  similar to the year slider on choropleth dialogs.
- New chart-YAML field: `defaultProjectionVintage` (one of: "latest",
  "none", or a YYYY-MM key).

### Phasing

1. Phase 1: schema + storage. Pipelines write projections; renderer
   just renders points (no UI yet). Lets us land the data structure
   without breaking the existing render path.
2. Phase 2: render the latest projection as a dashed extension of
   the historical line. No picker yet.
3. Phase 3: vintage picker.

Phase 1 + 2 = ~1 week of work. Phase 3 = another week. None of
this is necessary to ship the CBO data; CBO can land as
historical-only first, with the projections-array stored but not
yet rendered.

### Open design questions

- How to handle multiple forecast SOURCES for the same series
  (CBO vs OMB vs Fed SEP for GDP, say)? Probably each is its own
  source; the composer's existing two-source overlay handles
  showing them together.
- How to handle uncertainty bands (CBO publishes 80% intervals)?
  Add a `projectionsBand` field with `{low, high}` arrays per
  vintage. Render as a translucent fill.

These can wait for Phase 4+.
