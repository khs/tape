# New data source — checklist

When pulling from a data provider for the first time (a new
website, a new pipeline, a new series-ID convention), work through
this list. The order matters — early steps catch class-of-bug
problems that retroactive audits can't.

The whole list takes ~30-60 min for a familiar provider, longer
for a new one. Worth the friction: the May 2026 federal-spending
bug (where four FRED series IDs were labeled as their NIPA-line
neighbors) would have been caught at step 8.

## Before you write any code

1. **What's the provider's authoritative human label for each
   series?** Find the endpoint, web page, or documentation table
   that returns / displays the official name. You'll need this
   for the audit script in step 8.

   Examples we already have:
   - FRED: `https://fred.stlouisfed.org/series/<ID>` HTML `<title>`
   - World Bank: `api.worldbank.org/v2/indicator/<CODE>?format=json`
   - Yahoo: `query1.finance.yahoo.com/v8/finance/chart/<TICKER>` →
     `meta.longName`

2. **What's the identifier convention?** Series ID? Indicator code
   + country? Variable + geography? Note whether the identifier is
   self-describing (e.g., `LAUCN515100000000003` encodes county
   FIPS 51510) or opaque (e.g., `W823RC1Q027SBEA`).

3. **What's the rate-limit / auth situation?** Does it require an
   API key? Does it block User-Agent strings? Are the public CSV
   endpoints separate from the JSON API? Document this in the
   pipeline file's docstring.

4. **What license applies?** Public domain? CC BY? Custom terms?
   Add to `provenance.license` on every source YAML. License
   strings are visible in chart citation blocks.

## Pipeline

5. **Write `pipelines/<provider>.py`** following the structure of
   the existing ones (e.g., `fred_series.py`). Pattern:
   - Dataclass `<Provider>Spec(series_id, name, unit, ...)`
   - `SPECS: list[<Provider>Spec]` — the catalog
   - `fetch_series(spec)` — one fetch
   - `main()` loop with optional `argv` filter to fetch a subset

   Use `common.write_timeseries()` to write the JSON so the schema
   stays consistent.

6. **Canonical-unit invariant.** Currency series store values in
   **billions** USD; counts store **raw**. If the provider
   publishes in millions, your pipeline divides by 1000 (or
   multiplies by 1000 for thousand-counts that should be raw).
   See `pipelines/rescale_currency_to_billions.py` for the
   established convention.

## Source YAMLs

7. **Emit the YAML inline from the pipeline** (the standard since
   Plan 7, 2026-06). The ingest pipeline writes one source YAML per
   series right where it writes the data file — a local
   `write_yaml(...)` called next to `common.write_timeseries(...)`.
   Pattern exemplars: `pipelines/usgs_water.py`, `usda_nass.py`,
   `census_acs_metro.py`, `bls_metro.py`. Conventions:

   - **Overwrite-always.** The YAML dir is owned by the pipeline; a
     refresh regenerates every file. Never hand-edit a YAML in an
     inline-owned dir — the next refresh clobbers it. Fixes belong
     in the emitter (names/descriptions) or in shared post-passes
     (`fix_source_descriptions.py` normalizes copy on every refresh).
   - **Emit only for data that landed.** Call the emitter after the
     data file is written (min-points checks, suppressed cells
     skipped), so YAML ↔ data parity holds by construction — no
     separate dir-scan needed.
   - **Stage the dir in the refresh workflows.** Inline YAML reaches
     main only if `src/content/sources/<provider>` is in the commit
     step's YAML-dir list — which appears in THREE places per
     workflow (snapshot loop, restore loop, `git add` loop) in
     `refresh-demographics.yml`, plus the equivalent block in
     `refresh-data.yml` for weekly-cadence providers. Update every
     occurrence; a dir missing from the list means its refreshed
     YAML silently never commits.

   **Legacy patterns — do NOT use for new providers:** one-shot
   `_scaffold_<provider>.py` scripts (duplicate the pipeline's
   series inventory in a second file — the old ones carried literal
   "keep in lockstep" comments — and need a manual re-run whenever
   coverage changes) and standalone `_generate_*.py` source
   generators (`_generate_acs_sources.py` /
   `_generate_acs_national_sources.py` remain for the ACS family:
   they're workflow-integrated and serve ~18k files across several
   pipelines, so folding them is riskier than it's worth today).

   Hand-typed YAMLs remain fine for small fixed catalogs (~150 or
   fewer series, e.g. `fred/`, `cms_nhe`); beyond that — or whenever
   the pipeline already iterates a catalog — inline emission wins.

## Audit (the bit that prevents May 2026 recurrences)

8. **Write `scripts/audit_<provider>_<units>.py`** following the
   established pattern (FRED, World Bank, Yahoo). The script must:
   - Read every YAML in `src/content/sources/<provider>/`
   - Extract the identifier from `provenance.series` (or filename)
   - Hit the provider's authoritative endpoint from step 1
   - Compare YAML `name` to provider's official label via the
     standard token-overlap heuristic (see existing scripts)
   - Cache results in `scripts/_<provider>_audit_cache.json`
   - Support `--strict` (exit 1 on mismatches), `--json`,
     `--no-cache`, `--workers N`

9. **Add an `ALLOWLIST` dict** to the audit for known-good
   colloquial deviations from the provider's formal label (e.g.,
   "Core PCE" vs "Personal Consumption Expenditures Excluding
   Food and Energy Chain-Type Price Index"). Each entry is a
   deliberate promise that you reviewed the YAML against the
   provider's series page.

10. **Wire the audit into `scripts/audit_all_sources.py`** so
    `audit_all_sources.py --strict` runs your provider too.

11. **Wire `audit_all_sources.py --strict` into the data-refresh
    workflows** (it's already in `.github/workflows/refresh-data.yml`
    and `refresh-demographics.yml` — your new provider gets that
    coverage automatically once you add it to step 10).

## Verify

12. **Run the audit on a clean cache** with `python scripts/audit_<provider>.py --no-cache`.
    Mismatches should be zero. Real mismatches → fix the YAML.
    Cosmetic divergences from the provider's formal label → add
    to `ALLOWLIST` with a one-line note.

13. **Sanity-spot-check a few series values.** The audit catches
    LABEL bugs but not VALUE-magnitude bugs (the series is fine but
    in millions when the YAML says billions, etc.). Pick 3-5
    series with values you can predict (GDP ≈ $25T; unemployment
    ≈ 4%; etc.) and confirm the last data point looks right.

## After it ships

14. **Add the provider to `docs/fred-series-audit.md`** — that file
    is the canonical audit-retro write-up. Future-you reads it
    when adding the next provider.

15. **Sample-check after each data refresh.** The CI gate stops
    label drift, but quarterly you should still eyeball the
    rendered dashboard tooltips of any chart you newly added.

## Pipelines that DON'T have audit scripts yet, and why

These are pipeline-generated label sources where the pipeline's
mapping IS the audit (a YAML is correct iff the pipeline that
emitted it is correct):

- **`bls`** (902 YAMLs) — `pipelines/bls.py` looks up county/state
  FIPS from a fixed table and constructs the YAML name from that.
  The labels are correct by construction. Audit risk = bug in
  `bls.py`'s FIPS → name mapping.
- **`acs_cd`, `acs_metro`, `acs_state`, `acs_national`** (~18k
  YAMLs) — `_generate_acs_sources.py` etc. write the YAMLs from
  the data files; the data files come from `census_acs_*.py`'s
  hand-typed INDICATORS list. Audit risk = bug in the INDICATORS
  list's variable-code → human-name mapping.
- **`usaspending`** (878 YAMLs) — `usaspending.py` writes
  per-district / per-state YAMLs from a fixed geo table. Audit
  risk = wrong FIPS → name pairing.
- **`treasury_tic`** (37 YAMLs) — country-keyed transparently. Low
  audit risk; YAML labels are just country names.
- **`usda_nass`** (377 YAMLs) — `usda_nass.py` constructs each YAML name
  from the row's own commodity + geography (`state_name`) and stores the
  authoritative QuickStats `short_desc` verbatim in `provenance.series`.
  Correct by construction; audit risk = a bug in the commodity-label or
  unit-routing map. Guarded by the `get_counts` preflight (caught corn's
  GRAIN requirement + the planted-vs-harvested-acre yield split) and a
  duplicate-`(geo, year)` counter that must read 0 on write.
- **`cms_nhe`** (2 YAMLs) — `cms_nhe.py` parses CMS's NHE summary CSV
  (Table 1) and reads two rows from the *per-capita section only*. It
  anchors to the "National Health Expenditures (Per Capita Amount)"
  section header — so the recurring "Personal Health Care" label resolves
  to the per-capita value, not the aggregate / %-change / %-distribution
  rows that carry the identical label — and raises if the section header,
  a wanted row, or the year header is missing, or if a parsed value falls
  outside the $1k–$100k per-capita sanity band. Those asserts ARE the
  audit: a CMS table reformat fails the refresh instead of silently
  mislabelling. Hand-written YAMLs (2 series). The ZIP URL is year-pinned
  (`...cy-1960-2024.zip`); since the data is annual, it's a manual
  bump-and-rerun when CMS publishes a new vintage, not a weekly refresh.
- **`cdc_health`** (~150 YAMLs) — `cdc_health.py` fetches via
  data.cdc.gov Socrata endpoints (CDC's public-use aggregates) and
  constructs YAML names from CDC's own column labels. Correct by
  construction; audit risk = a bug in the indicator → human-name map.
  Guarded by an in-pipeline shape check on the Socrata response.
- **`usgs_water`** (~480 YAMLs) — `usgs_water.py` parses the USGS
  National Water-Use Survey XLSX into per-state per-sector totals.
  Labels are constructed from the source XLSX column headers + a
  per-state lookup; correct by construction. Audit risk = an XLSX
  column-header reshuffle (USGS releases every 5 years so this is
  detected at the next vintage rather than incrementally).

For each of these, the right audit is "diff what the pipeline
WOULD generate today against what's checked in." A `--dry-run`
mode on the generators would surface drift cheaply. That's a
future enhancement.

## OECD (157 YAMLs)

`pipelines/oecd.py` fetches via OECD's SDMX-style API. Series
codes are nested (dataset + multiple dimensions); there's no
single "Series" page returning a human label. Adding an audit
here means parsing OECD's dataset-structure XML, which is more
involved than the FRED / WB pattern. Currently relying on the
pipeline's spec list being correct. Open ticket.

---

## TL;DR for "I just want to add a series to FRED"

1. Look up the FRED series page (`fred.stlouisfed.org/series/<ID>`)
   and copy the official title.
2. Add a `FredSpec(<ID>, <title-derived-name>, <unit>)` to
   `pipelines/fred_series.py`.
3. Run `python pipelines/fred_series.py <ID>` to fetch the data.
4. Create `src/content/sources/fred/<slug>.yaml` with `name` =
   common-English version of the FRED title.
5. Run `python scripts/audit_fred_series.py`. Fix anything it flags.
6. Open the PR.

Total time for step 1-6 on a known provider: 5-10 min.
