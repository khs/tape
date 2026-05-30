# FRED series-label audit + prevention

## Background

In May 2026 a customer-visible bug landed on
`/federal-budget/`: the "Federal spending by function" chart's
hover tooltip showed implausibly small values for some series
(Social Security read as ~$38B annualized vs the real ~$1.6T,
nondefense read as ~$12T vs the real ~$0.8T). The root cause
turned out to be **four mis-mapped FRED series IDs** in our source
YAMLs:

| Our label | Was pointing at | What that series actually is | Should have been |
|---|---|---|---|
| federal_social_security | W825RC1Q027SBEA | Unemployment insurance | W823RC1Q027SBEA |
| federal_medicare | W823RC1Q027SBEA | Social security | W824RC1Q027SBEA |
| federal_medicaid | W824RC1Q027SBEA | Medicare | W729RC1Q027SBEA |
| federal_nondefense_spending | W068RCQ027SBEA | TOTAL government (fed + state + local) | FNDEFX |

The data files were exactly the data FRED publishes under those
series IDs — the bug was entirely in the human labels we attached
to them. Every plot, hover tooltip, citation, and "Open in
composer" downstream of those labels was wrong as a result.

## How it happened

The pipeline + content-collection setup has **three independent
places where a series label can be typed**, and nothing in the
build, test, or audit pipeline cross-checked any of them against
FRED's authoritative title:

1. **`pipelines/fred_series.py`'s `FredSpec` list.** A
   human-typed `(series_id, label, unit)` tuple. The pipeline
   fetches the data and writes it to
   `public/data/fred/<series_id>.json` — the label never reaches
   the data file at all (only the name from `write_timeseries`
   does, but that name doesn't get verified either).

2. **`src/content/sources/fred/<x>.yaml`'s `name`,
   `description`, and `provenance.series` fields.** Another set
   of human-typed strings. The YAML's `dataFile` points at the
   on-disk JSON from step 1, but YAML name vs JSON name vs
   FRED's actual title — no equality check.

3. **`src/content/charts/<topic>/<x>.yaml`'s `title` and
   `blurb`.** A third human-typed label, displayed in the
   dashboard. Disconnected from FRED entirely.

A label-typo at any of the three layers produces a visible-but-
wrong chart. The audit scripts that existed (data-file
not-empty, JSON-schema validation, etc.) all passed because the
**data was real** — it just wasn't what the labels claimed.

The specific incident: someone (almost certainly me) added W823
/ W824 / W825 + their labels to `FredSpec` while scaffolding the
federal-budget topic. The labels were chosen by guessing at the
NIPA Table 3.12 line order (W82X looks like a contiguous block,
so the naive ordering is "W821 = SS, W822 = SS-A, W823 = SS-B,
W824 = Medicare-A, W825 = Medicare-B, …"). The actual FRED
mapping is "W823 = Social security, W824 = Medicare,
W825 = Unemployment, W729 = Medicaid" — not contiguous, not in
the order I guessed. Nothing pushed back on the wrong labels
because nothing was checking.

## What's in place now

### 1. `scripts/audit_fred_series.py`

Probes FRED's series page for every YAML in
`src/content/sources/fred/`, extracts the official title from
the `<title>` tag, and compares it to the YAML's `name` via a
token-overlap heuristic. Mismatches are reported with the
offending file, the FRED ID, the YAML's claimed name, and FRED's
official title.

- `python scripts/audit_fred_series.py` — human report
- `python scripts/audit_fred_series.py --strict` — exit 1 on
  any mismatches (for CI use)
- `python scripts/audit_fred_series.py --json` — machine output

Known-good shorthand pairs (Core PCE = "Personal Consumption
Expenditures Excluding Food and Energy Chain-Type Price Index",
U-6 = the long BLS formula, etc.) are hardcoded in `ALLOWLIST`.
Every entry there is a deliberate promise that someone reviewed
the YAML against FRED's series page.

### 2. Wired into both data-refresh workflows

`refresh-data.yml` and `refresh-demographics.yml` both now run
`audit_fred_series.py --strict` after the data fetch but before
the commit. A new FRED series whose label drifted from FRED's
title fails the workflow — the bad commit never reaches main.

### 3. Pipeline self-check

`pipelines/fred_series.py` itself now probes FRED's official
title for each `FredSpec` it processes and warns at end-of-run
if the spec's `name` shares zero identifying tokens with FRED's
title. Non-fatal at this layer (partial fetches are useful),
but it surfaces drift loudly in the workflow logs.

## How to add a new FRED series safely

1. Look up the FRED series page (`fred.stlouisfed.org/series/<ID>`)
   and copy the **exact title** as your reference.
2. Add the `FredSpec` to `pipelines/fred_series.py` with a `name`
   that uses common-parlance words from the FRED title.
3. Create the source YAML in `src/content/sources/fred/` with the
   same `name`. The `provenance.series` MUST match the ID.
4. Run `python scripts/audit_fred_series.py` locally — it should
   pass with 0 mismatches.
5. If your YAML uses a deliberate shorthand (like "Core PCE")
   that the audit token-check flags as a mismatch, add the series
   ID to `ALLOWLIST` in `scripts/audit_fred_series.py` with a one-
   line note explaining the equivalence.
6. Open the PR; CI runs the audit as part of the data-refresh
   workflows.

## Audit results from the May 2026 sweep

After fixing the four federal-spending mismaps, I ran the audit
across all 145 FRED source YAMLs (the count at the time of the
May 2026 sweep; as of the spring-26 expansion the FRED set has
grown to 420 YAMLs — see `docs/fred-copyright-audit.md` for the
current bucketing). Beyond the four already known, three more
turned out to need label corrections:

- **`federal_subsidies`** had been pointing at W994 ("Net lending
  or net borrowing, NIPAs: Private") instead of B096 ("Federal
  government current expenditures: Subsidies"). Fixed.
- **`recession_probability_ny_fed`** claimed the NY Fed yield-
  curve model but RECPROUSM156N is actually the Chauvet-Piger
  smoothed probability — a different model with a different
  underlying signal. Renamed the YAML's name + description to
  match what the series actually is. The data was correct, just
  attributed to the wrong methodology.
- **`us_retail_gasoline`** claimed "all grades avg" but GASREGW
  is regular-grade only (all-grades-average is GASALLW). Fixed
  the name.
- **`ppi_semiconductor`** claimed NAICS 334413 ("Semiconductor and
  Related Device Manufacturing") but PCU33443344 is NAICS 3344
  ("Semiconductor and Other Electronic Component Manufacturing")
  — the broader subsector. Fixed the description to match.

After all fixes: 0 likely mismatches across 145 YAMLs.
